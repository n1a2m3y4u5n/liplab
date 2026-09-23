"""축 C 소규모 실증 — 실제 입모양 데이터로 지각 공간을 만들고 손코딩 지각 공간과 비교한다(numpy만).

데이터: AI Hub 538 10화자 300문장의 MediaPipe 블렌드셰이프(bs/*.json)와 wav2vec2 강제정렬 음절 구간
(d/spans.jsonl, build_cd v2). CTC 구간은 1~3프레임으로 짧아(피크성) 그대로 평균하면 거의 변별되지
않았다(c_jamo_similarity.json: 모든 쌍 0.99 안팎). 그래서
  ① 음절 창을 이웃 음절과의 중간점까지 넓히고, 앞 35%=초성 구간, 30~70%=모음 구간으로 나눈다,
  ② 입 주변 27차원(train_lipread.MOUTH_KEYS)을 화자별로 z-정규화한다(화자 차이 제거),
  ③ 화자·대본 분리 폴드(folds.py)로 평가한다.
분석: (a) 비심(입모양 그룹) 분리도 — 학습 화자 중심점 기준 최근접 분류 정확도 대 최빈 기준선,
      (b) 데이터 공간(LDA, 학습 화자로 적합)의 자모 중심점 거리와 손코딩 지각 공간 거리(perceptual_space)의
          스피어만 상관, (c) 데이터에서 가장 헷갈리는 자모 쌍.
사용: python c_perceptual_demo.py --run DATA/pod_runs/<run> --backend <liplab backend> --out c_demo.json
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict

import numpy as np

CHO = list("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ")
JUNG = list("ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ")


def decompose(ch):
    o = ord(ch) - 0xAC00
    if not (0 <= o < 11172):
        return None, None
    return CHO[o // 588], JUNG[(o % 588) // 28]


def load_bs(path, keys):
    d = json.load(open(path, encoding="utf-8"))
    names = d.get("bs_names") or []
    idx = [names.index(k) for k in keys if k in names]
    fr = d.get("frames") or []
    if not fr or len(idx) != len(keys):
        return None
    return np.array([[f["bs"][i] for i in idx] for f in fr], dtype=float)


def spearman(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    ra, rb = a.argsort().argsort(), b.argsort().argsort()
    return float(np.corrcoef(ra, rb)[0, 1])


def lda_fit(X, y, dim):
    classes = sorted(set(y))
    mu = X.mean(0)
    Sw = np.zeros((X.shape[1], X.shape[1]))
    Sb = np.zeros_like(Sw)
    for c in classes:
        Xc = X[np.array(y) == c]
        mc = Xc.mean(0)
        Sw += (Xc - mc).T @ (Xc - mc)
        Sb += len(Xc) * np.outer(mc - mu, mc - mu)
    Sw += 1e-3 * np.eye(len(Sw)) * np.trace(Sw) / len(Sw)
    w, V = np.linalg.eig(np.linalg.solve(Sw, Sb))
    order = np.argsort(-w.real)[:dim]
    return V[:, order].real


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--backend", required=True)
    ap.add_argument("--tools", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    sys.path.insert(0, a.backend)
    sys.path.insert(0, a.tools)
    from engine import VISEME_MAP
    import perceptual_space as PS
    import folds as FO
    from train_lipread import MOUTH_KEYS

    segs = []   # (spk, kind, jamo, viseme, feat)
    frames_by_spk = defaultdict(list)
    rows = [json.loads(l) for l in open(os.path.join(a.run, "d", "spans.jsonl"), encoding="utf-8")]
    clip_bs = {}
    for r in rows:
        p = os.path.join(a.run, "bs", r["clip"] + ".json")
        if not os.path.exists(p) or r.get("flagged"):
            continue
        X = load_bs(p, MOUTH_KEYS)
        if X is None:
            continue
        clip_bs[r["clip"]] = X
        frames_by_spk[r["spk"]].append(X)
    stats = {s: (np.concatenate(v).mean(0), np.concatenate(v).std(0) + 1e-6) for s, v in frames_by_spk.items()}
    for r in rows:
        X = clip_bs.get(r["clip"])
        if X is None:
            continue
        mu, sd = stats[r["spk"]]
        Z = (X - mu) / sd
        chars = [c for c in r.get("chars") or [] if len(c) == 3]
        for i, (ch, s, e) in enumerate(chars):
            ini, med = decompose(ch)
            if ini is None:
                continue
            left = (chars[i - 1][2] + s) / 2 if i > 0 else max(0, s - 3)
            right = (e + chars[i + 1][1]) / 2 if i + 1 < len(chars) else e + 3
            span = max(right - left, 3)
            on = Z[int(left):int(np.ceil(left + 0.35 * span)) + 1]
            vo = Z[int(left + 0.3 * span):int(np.ceil(left + 0.7 * span)) + 1]
            if ini != "ㅇ" and len(on):
                segs.append((r["spk"], "C", ini, VISEME_MAP.get(ini), on.mean(0)))
            if len(vo):
                segs.append((r["spk"], "V", med, VISEME_MAP.get(med), vo.mean(0)))

    man = [(l.split("\t")[0], l.split("\t")[1], l.split("\t")[2].rstrip("\n"))
           for l in open(os.path.join(a.run, "manifest.tsv"), encoding="utf-8") if l.count("\t") >= 2]
    folds = FO.make_folds(man, n_folds=5)
    out = {"n_segments": len(segs), "n_clips": len(clip_bs), "speakers": len(stats), "folds": len(folds)}

    for kind, name in (("C", "consonant"), ("V", "vowel")):
        S = [s for s in segs if s[1] == kind and s[3] is not None and 1 <= s[3] <= 13]
        # (a) 비심 분리도: 학습 화자 중심점 최근접 분류(화자·대본 분리 폴드)
        acc, base, bal, n = [], [], [], 0
        for f in folds:
            tr = [s for s in S if s[0] in f["train"]]
            te = [s for s in S if s[0] in f["test"]]
            if not tr or not te:
                continue
            cls = sorted({s[3] for s in tr})
            cen = {c: np.mean([s[4] for s in tr if s[3] == c], 0) for c in cls}
            maj = Counter(s[3] for s in tr).most_common(1)[0][0]
            pred = [min(cls, key=lambda c: np.linalg.norm(s[4] - cen[c])) for s in te]
            hit = sum(p == s[3] for p, s in zip(pred, te))
            acc.append(hit / len(te)); base.append(np.mean([s[3] == maj for s in te])); n += len(te)
            rec = [np.mean([p == c for p, s in zip(pred, te) if s[3] == c]) for c in cls if any(s[3] == c for s in te)]
            bal.append(float(np.mean(rec)))
        # (b) LDA 공간의 자모 중심점 거리 대 손코딩 거리
        jcount = Counter(s[2] for s in S)
        jamos = sorted(j for j, c in jcount.items() if c >= 20)
        X = np.array([s[4] for s in S if s[2] in jamos]); y = [s[2] for s in S if s[2] in jamos]
        W = lda_fit(X, y, dim=min(6, len(jamos) - 1))
        P = X @ W
        cen = {j: P[np.array(y) == j].mean(0) for j in jamos}
        if kind == "C":
            syms, Sim = PS.similarity_matrix([j for j in PS.CONSONANTS if j in jamos])
        else:
            syms, Sim = PS.vowel_similarity_matrix([j for j in PS.VOWELS if j in jamos])
        dd, hh, pairs = [], [], []
        for i in range(len(syms)):
            for k in range(i + 1, len(syms)):
                dd.append(float(np.linalg.norm(cen[syms[i]] - cen[syms[k]])))
                hh.append(float(1 - Sim[i, k]))
                pairs.append((syms[i], syms[k], dd[-1]))
        pairs.sort(key=lambda t: t[2])
        out[name] = {
            "segments": len(S), "viseme_classes": sorted({s[3] for s in S}),
            "nearest_centroid_acc": round(float(np.mean(acc)), 4) if acc else None,
            "majority_baseline": round(float(np.mean(base)), 4) if base else None,
            "balanced_acc": round(float(np.mean(bal)), 4) if bal else None,
            "balanced_chance": round(1.0 / len({s[3] for s in S}), 4),
            "jamos_used": syms,
            "spearman_data_vs_handcoded": round(spearman(dd, hh), 4) if len(dd) > 2 else None,
            "closest_pairs_in_data": [f"{p[0]}-{p[1]}" for p in pairs[:8]],
        }
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("C_DEMO_OK", json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
