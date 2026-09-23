#!/usr/bin/env python
"""
고도화 축 C C-4 — 데이터 지각 공간에서 독화 난이도 지수와 최소대립쌍을 도출하고 규칙판과 비교한다.

계획서 §3.3 C-4는 "지각 공간에서 채점 계수와 함께 문장 독화 난이도 지수와 최소대립쌍도 도출"한다고 했다.
채점 계수(C-3)는 데이터 공간과 손코딩 계수의 자모 쌍 상관이 약해(자음 0.30, 모음 0.22) 규칙을 유지했다.
여기서는 같은 데이터 공간(실화자 입모양으로 만든 자모 시각 유사도)으로 세 가지를 만들고 규칙판과 맞춰 본다.

  ① 자모 혼동도: 같은 종류(자음·모음) 안에서 가장 닮은 두 자모와의 유사도 평균을 종류 안에서 0~1로 편다.
  ② 단어·문장 난이도(데이터판): 단어의 초성(무음 ㅇ 제외)·모음 혼동도 평균, 문장은 어절 평균.
     종성은 데이터 공간에 없어 넣지 않는다(적용 범위를 결과에 함께 적는다).
  ③ 최소대립쌍(데이터판): 단어 은행에서 초성이나 모음 한 자리만 다른 쌍을, 그 두 자모의 데이터 유사도로 줄 세운다.

비교: ②는 규칙 난이도·동구형이음 비율과 스피어만 상관(단어를 다시 뽑는 부트스트랩 95% 구간),
③은 "규칙상 같은 입모양 짝인가"를 데이터 유사도가 얼마나 가르는지(AUC)와 상위 쌍의 일치율.
표준 라이브러리만 쓰고 결정론적이다(부트스트랩 seed 고정).

  python scripts/c4_data_derived.py                          # 기본: backend/data/c_jamo_similarity.json(538 10화자)
  python scripts/c4_data_derived.py --sim <30화자판 json> --out <경로>

출력은 내부용이다. AI Hub 데이터에서 계산한 값이라 재배포 허용을 확인하기 전까지 공개 자원에 싣지 않는다.
"""
import argparse
import json
import os
import random
import re
import sys
from collections import Counter

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.join(os.path.dirname(_HERE), "backend")
sys.path.insert(0, _BACKEND)

import curriculum as C  # noqa: E402
import perceptual as P  # noqa: E402
from content_rules import (VISEME_MAP, _jamo_seq, same_viseme_group, viseme_signature,  # noqa: E402
                           is_hangul_word)

_DEFAULT_SIM = os.path.join(_BACKEND, "data", "c_jamo_similarity.json")
_DEFAULT_OUT = os.path.join(_BACKEND, "data", "c4_data_derived.json")
_BOOT = 1000
_SEED = 20260924


def _kind(ch):
    return "consonant" if "ㄱ" <= ch <= "ㅎ" else "vowel" if "ㅏ" <= ch <= "ㅣ" else None


def _pair_key(a, b):
    return "".join(sorted((a, b)))


# ── 통계(표준 라이브러리) ──
def _ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def _pearson(x, y):
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    return sxy / (sxx * syy) ** 0.5 if sxx > 0 and syy > 0 else float("nan")


def spearman(x, y):
    return _pearson(_ranks(x), _ranks(y))


def spearman_ci(x, y, boot=_BOOT, seed=_SEED):
    """스피어만 ρ와, 항목을 다시 뽑는 부트스트랩 95% 구간."""
    rho = spearman(x, y)
    rng = random.Random(seed)
    n = len(x)
    vals = []
    for _ in range(boot):
        idx = [rng.randrange(n) for _ in range(n)]
        v = spearman([x[i] for i in idx], [y[i] for i in idx])
        if v == v:  # NaN 제외
            vals.append(v)
    vals.sort()
    lo, hi = vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals)) - 1]
    return {"rho": round(rho, 3), "ci95": [round(lo, 3), round(hi, 3)], "n": n}


def auc(scores, labels):
    """양성(label=1)의 점수가 음성보다 클 확률(동점 절반). 맨-휘트니 U / (n1·n0)."""
    r = _ranks(scores)
    n1 = sum(labels)
    n0 = len(labels) - n1
    if not n1 or not n0:
        return None
    s1 = sum(ri for ri, l in zip(r, labels) if l)
    return round((s1 - n1 * (n1 + 1) / 2) / (n1 * n0), 3)


# ── ① 자모 혼동도 ──
def jamo_confusability(sim):
    nb = {}
    for key, s in sim.items():
        a, b = key[0], key[1]
        nb.setdefault(a, []).append(s)
        nb.setdefault(b, []).append(s)
    raw = {j: sum(sorted(v, reverse=True)[:2]) / min(2, len(v)) for j, v in nb.items()}
    out = {}
    for kind in ("consonant", "vowel"):
        js = [j for j in raw if _kind(j) == kind]
        lo, hi = min(raw[j] for j in js), max(raw[j] for j in js)
        for j in js:
            out[j] = round((raw[j] - lo) / (hi - lo), 3) if hi > lo else 0.5
    return out


# ── ② 단어·문장 난이도 ──
def word_data_difficulty(word, conf):
    seq = _jamo_seq(word)
    if not seq:
        return None, 0, 0
    slots = [(i % 3, j) for i, j in enumerate(seq) if i % 3 != 2]     # 초성·모음(종성 제외)
    slots = [(pos, j) for pos, j in slots if not (pos == 0 and j == "ㅇ")]  # 무음 초성 ㅇ
    have = [conf[j] for _, j in slots if j in conf]
    if not have:
        return None, 0, len(slots)
    return round(sum(have) / len(have), 3), len(have), len(slots)


def _sentence_words(text):
    return [w for w in (re.sub(r"[^가-힣\s]", " ", text or "").split()) if is_hangul_word(w)]


def sentence_data_difficulty(text, conf):
    ds = [d for d, _, _ in (word_data_difficulty(w, conf) for w in _sentence_words(text)) if d is not None]
    return round(sum(ds) / len(ds), 3) if ds else None


def closure_sentences():
    out = []
    for it in C.CLOSURE_ITEMS:
        disp, ans = it.get("display") or "", it.get("answer") or ""
        if "___" in disp and ans:
            out.append(disp.replace("___", ans))
    return list(dict.fromkeys(out))


# ── ③ 최소대립쌍 ──
def one_slot_pairs(words):
    """초성이나 모음 한 자리만 다른 단어쌍(표기 자모 기준). 종성 차이는 데이터에 없어 뺀다."""
    by_len = {}
    for w in words:
        seq = _jamo_seq(w)
        if seq:
            by_len.setdefault(len(seq), []).append((w, seq))
    out = []
    for group in by_len.values():
        # 한 자리를 비운 키로 버킷팅(O(단어수 × 자리수))
        buckets = {}
        for w, seq in group:
            for i in range(len(seq)):
                if i % 3 == 2:
                    continue
                key = (i, tuple(seq[:i]), tuple(seq[i + 1:]))
                buckets.setdefault(key, []).append((w, seq[i]))
        for (i, _, _), ws in buckets.items():
            for x in range(len(ws)):
                for y in range(x + 1, len(ws)):
                    (a, ja), (b, jb) = ws[x], ws[y]
                    if ja != jb:
                        out.append({"a": a, "b": b, "slot": "onset" if i % 3 == 0 else "vowel", "ja": ja, "jb": jb})
    return out


def main(args):
    sim_doc = json.load(open(args.sim, encoding="utf-8"))
    sim = sim_doc["jamo_similarity"]
    conf = jamo_confusability(sim)

    words = [w for w in dict.fromkeys(x["word"] for x in C.WORD_BANK) if is_hangul_word(w)]
    sig_count = Counter(viseme_signature(w) for w in words)

    # ② 단어
    rows = []
    cov_have = cov_all = 0
    for w in words:
        d, nh, na = word_data_difficulty(w, conf)
        cov_have += nh
        cov_all += na
        rule = P.word_difficulty(w, sig_count)
        if d is not None and rule:
            rows.append({"word": w, "data": d, "rule": rule["difficulty"], "homophene_ratio": rule["homophene_ratio"],
                         "invisibility": rule["invisibility"]})
    word_cmp = {
        "vs_rule_difficulty": spearman_ci([r["data"] for r in rows], [r["rule"] for r in rows]),
        "vs_homophene_ratio": spearman_ci([r["data"] for r in rows], [r["homophene_ratio"] for r in rows]),
        "vs_invisibility": spearman_ci([r["data"] for r in rows], [r["invisibility"] for r in rows]),
        "jamo_coverage": round(cov_have / cov_all, 3) if cov_all else None,
    }

    # ② 문장(문맥 추론 문항의 빈칸을 정답으로 채운 문장)
    srows = []
    for s in closure_sentences():
        d = sentence_data_difficulty(s, conf)
        r = P.sentence_difficulty(s, sig_count).get("difficulty")
        if d is not None and r is not None:
            srows.append({"text": s, "data": d, "rule": r})
    sent_cmp = {"vs_rule_difficulty": spearman_ci([r["data"] for r in srows], [r["rule"] for r in srows])}

    # ③ 최소대립쌍
    pairs = []
    for p in one_slot_pairs(words):
        s = sim.get(_pair_key(p["ja"], p["jb"]))
        if s is None:
            continue
        p["data_similarity"] = s
        p["rule_same_looking"] = bool(same_viseme_group(p["ja"], p["jb"]))
        pairs.append(p)
    pairs.sort(key=lambda p: (-p["data_similarity"], p["a"], p["b"]))
    k = max(1, len(pairs) // 10)
    top = pairs[:k]
    n_rule = sum(p["rule_same_looking"] for p in pairs)
    pair_cmp = {
        "n_candidates": len(pairs),
        "rule_same_looking_share": round(n_rule / len(pairs), 3) if pairs else None,
        "auc_data_similarity_for_rule_same_looking": auc([p["data_similarity"] for p in pairs],
                                                        [int(p["rule_same_looking"]) for p in pairs]),
        "top10pct_rule_agreement": round(sum(p["rule_same_looking"] for p in top) / len(top), 3) if top else None,
        "by_slot": {},
    }
    for slot in ("onset", "vowel"):
        ps = [p for p in pairs if p["slot"] == slot]
        pair_cmp["by_slot"][slot] = {
            "n": len(ps),
            "auc": auc([p["data_similarity"] for p in ps], [int(p["rule_same_looking"]) for p in ps]),
        }

    # 자모 수준: 규칙상 같은 입모양 짝을 데이터 유사도가 얼마나 가르나(단어 빈도 가중 없이).
    # same_viseme_group은 입 안쪽 자음(입모양 6·7·8·10)을 한 무리로 보므로, 자음에서는 사실상 '입술 닫힘 대 나머지'를
    # 가르는 문제다. 그래서 같은 입모양 번호끼리만 같다고 보는 엄격 기준과, 입 안쪽 무리 안에서만 본 값을 함께 낸다.
    jkeys = [(k2, s) for k2, s in sim.items()]
    inside = {6, 7, 8, 10}
    jamo_auc = {}
    for kind in ("consonant", "vowel"):
        ks = [(k2, s) for k2, s in jkeys if _kind(k2[0]) == kind]
        row = {"rule_group": auc([s for _, s in ks], [int(same_viseme_group(k2[0], k2[1])) for k2, _ in ks]),
               "strict_viseme": auc([s for _, s in ks], [int(VISEME_MAP.get(k2[0]) == VISEME_MAP.get(k2[1])) for k2, _ in ks])}
        if kind == "consonant":
            ins = [(k2, s) for k2, s in ks if VISEME_MAP.get(k2[0]) in inside and VISEME_MAP.get(k2[1]) in inside]
            row["strict_within_inside"] = auc([s for _, s in ins],
                                              [int(VISEME_MAP.get(k2[0]) == VISEME_MAP.get(k2[1])) for k2, _ in ins])
            row["n_inside_pairs"] = len(ins)
        jamo_auc[kind] = row
    ins_pairs = [p for p in pairs if p["slot"] == "onset"
                 and VISEME_MAP.get(p["ja"]) in inside and VISEME_MAP.get(p["jb"]) in inside]
    pair_cmp["onset_strict_within_inside"] = {
        "n": len(ins_pairs),
        "auc": auc([p["data_similarity"] for p in ins_pairs],
                   [int(VISEME_MAP.get(p["ja"]) == VISEME_MAP.get(p["jb"])) for p in ins_pairs]),
    }

    out = {
        "meta": {"kind": "c4-data-derived", "sim_source": sim_doc.get("meta", {}).get("source"),
                 "sim_path": os.path.relpath(args.sim, os.path.dirname(_HERE)),
                 "bootstrap": _BOOT, "seed": _SEED,
                 "note": "내부용. AI Hub 데이터 유래라 공개 자원에 싣지 않는다. 종성은 데이터 공간에 없어 빠졌다."},
        "jamo_confusability": dict(sorted(conf.items(), key=lambda kv: -kv[1])),
        "validation": {"word": word_cmp, "sentence": sent_cmp, "pairs": pair_cmp, "jamo_same_viseme_auc": jamo_auc},
        "top_data_pairs": [{k2: p[k2] for k2 in ("a", "b", "slot", "ja", "jb", "data_similarity", "rule_same_looking")}
                           for p in pairs[:40]],
        "data_only_lookalikes": [{k2: p[k2] for k2 in ("a", "b", "ja", "jb", "data_similarity")}
                                 for p in pairs if not p["rule_same_looking"]][:20],
        "rule_lookalikes_data_sees_apart": [{k2: p[k2] for k2 in ("a", "b", "ja", "jb", "data_similarity")}
                                            for p in reversed(pairs) if p["rule_same_looking"]][:20],
        "words": sorted(rows, key=lambda r: -r["data"]),
        "sentences": sorted(srows, key=lambda r: -r["data"]),
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")
    v = out["validation"]
    print(f"단어 {len(rows)}개(자모 적용률 {word_cmp['jamo_coverage']}) · 문장 {len(srows)}개 · 한 자리 차이 쌍 {len(pairs)}개")
    print(f"단어 데이터 난이도 vs 규칙 난이도 ρ={v['word']['vs_rule_difficulty']}")
    print(f"  vs 동구형이음 비율 ρ={v['word']['vs_homophene_ratio']}  vs 비가시성 ρ={v['word']['vs_invisibility']}")
    print(f"문장 데이터 난이도 vs 규칙 난이도 ρ={v['sentence']['vs_rule_difficulty']}")
    print(f"쌍: 규칙상 같은 입모양 비율 {pair_cmp['rule_same_looking_share']}, AUC {pair_cmp['auc_data_similarity_for_rule_same_looking']},"
          f" 상위 10% 일치 {pair_cmp['top10pct_rule_agreement']}, 자리별 {pair_cmp['by_slot']}")
    print(f"자모 수준 AUC {jamo_auc} → {args.out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="C-4 데이터 지각 공간 → 난이도·최소대립쌍 도출과 규칙판 비교")
    ap.add_argument("--sim", default=_DEFAULT_SIM, help="자모 시각 유사도 JSON(c_jamo_similarity.json 형식)")
    ap.add_argument("--out", default=_DEFAULT_OUT)
    main(ap.parse_args())
