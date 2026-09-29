"""말하기 3단계 자음 '앱 방향' 재측정 분석(2026-09-29 사전 등록, docs/speak-consonant-check.md).
파드 결과 out/app_dir.json(speak_app_direction_pod_eval.py)의 cons 행을 읽어 538·608 각각 짝(녹음 Y → 목표 X)마다
  - 주 지표: 같은 녹음 AUC(양성 = 제 문장의 Y 음소 D-GOP, 음성 = 바꾼 문장의 X 음소 D-GOP)
  - 보조 지표: 고정 목표 AUC(양성 = X를 맞게 낸 녹음의 X 음소, 음성 = Y 녹음을 X에 댄 값)와 문턱 0.05 통과율
과 화자 단위 부트스트랩 95% 구간(2,000번)을 내고, 사전 등록한 자음별 판정을 적용한다. 데이터는 저장소에 넣지 않는다.
    python scripts/speak_consonant_app_analyze.py out/app_dir.json [요약.json]
"""
import collections
import json
import sys

import numpy as np

B = 2000
THR = 0.05          # speak_curriculum.PROBE_DGOP_MIN
CRIT = 0.80
APP = [("ㄷ", "ㅅ"), ("ㄷ", "ㅈ"), ("ㅊ", "ㅈ"), ("ㅈ", "ㅊ"), ("ㄱ", "ㅎ"), ("ㅇ", "ㅎ")]
TENSE = [("ㅅ", "ㅆ"), ("ㅈ", "ㅉ"), ("ㅆ", "ㅅ"), ("ㅉ", "ㅈ")]
OLD = [("ㅅ", "ㄷ"), ("ㅈ", "ㄷ"), ("ㅎ", "ㄱ")]
BASE = [("ㅂ", "ㅁ"), ("ㅁ", "ㅂ"), ("ㅂ", "ㅍ"), ("ㅍ", "ㅂ"), ("ㄷ", "ㅌ"), ("ㅌ", "ㄷ"), ("ㄱ", "ㅋ"), ("ㅋ", "ㄱ")]
# 사전 등록한 자음별 판정: (이름, [(짝, 지표)]) — 지표 'same'은 같은 녹음 AUC(짝을 합쳐 한 AUC), 'fixed'는 고정 목표 AUC.
# 여러 항목이면 항목마다 0.80 이상이어야 통과(ㅈ의 두 짝은 합쳐 한 항목).
DECISIONS = [
    ("ㅅ", [([("ㄷ", "ㅅ")], "same")]),
    ("ㅈ", [([("ㄷ", "ㅈ"), ("ㅊ", "ㅈ")], "same")]),
    ("ㅊ", [([("ㅈ", "ㅊ")], "same")]),
    ("ㅎ", [([("ㄱ", "ㅎ")], "same"), ([("ㅇ", "ㅎ")], "fixed")]),
    ("ㅆ", [([("ㅅ", "ㅆ")], "same"), ([("ㅆ", "ㅅ")], "same")]),
    ("ㅉ", [([("ㅈ", "ㅉ")], "same"), ([("ㅉ", "ㅈ")], "same")]),
]


def auc(pos, neg):
    """Mann-Whitney AUC(동점 0.5). 순위합으로 O(n log n)."""
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    allv = np.concatenate([pos, neg])
    order = allv.argsort(kind="mergesort")
    ranks = np.empty(len(allv))
    sv = allv[order]
    i = 0
    while i < len(sv):
        j = i
        while j + 1 < len(sv) and sv[j + 1] == sv[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2 + 1
        i = j + 1
    r = ranks[:len(pos)].sum()
    return float((r - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def boot(pos, neg, seed=0):
    """pos·neg = [(화자, 값)]. 화자를 복원 추출해 AUC 분포의 2.5·97.5 백분위."""
    bp, bn = collections.defaultdict(list), collections.defaultdict(list)
    for s, v in pos:
        bp[s].append(v)
    for s, v in neg:
        bn[s].append(v)
    spk = sorted(set(bp) | set(bn))
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(B):
        pick = rng.choice(len(spk), len(spk), replace=True)
        p = [v for k in pick for v in bp.get(spk[k], ())]
        n = [v for k in pick for v in bn.get(spk[k], ())]
        if p and n:
            vals.append(auc(p, n))
    return (float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))) if vals else (float("nan"), float("nan"))


def load(path):
    d = json.load(open(path))
    err = [r for r in d if "error" in r]
    pairs, trues = collections.defaultdict(list), collections.defaultdict(list)
    for r in d:
        if "error" in r:
            continue
        for c in r["cons"]:
            c = dict(c, spk=r["spk"], group=r["group"])
            if c["kind"] == "pair":
                pairs[(r["group"], c["y"], c["x"])].append(c)
            elif c.get("dgop") is not None:
                trues[(r["group"], c["cons"])].append(c)
    return d, err, pairs, trues


def measure(pairs, trues, g, plist, kind, wi_only=False):
    rows = [c for p in plist for c in pairs.get((g,) + p, []) if c["alt"] is not None and (not wi_only or c["wi"])]
    if kind == "same":
        rows = [c for c in rows if c["same"] is not None]
        pos = [(c["spk"], c["same"]) for c in rows]
    else:
        xs = {p[1] for p in plist}
        pos = [(c["spk"], c["dgop"]) for x in xs for c in trues.get((g, x), []) if (not wi_only or c["wi"])]
    neg = [(c["spk"], c["alt"]) for c in rows]
    a = auc([v for _, v in pos], [v for _, v in neg])
    lo, hi = boot(pos, neg)
    out = {"n_pos": len(pos), "n_neg": len(neg), "spk": len({s for s, _ in pos + neg}), "auc": a, "ci": [lo, hi]}
    if kind == "fixed":
        out["pos_pass"] = float(np.mean([v >= THR for _, v in pos])) if pos else float("nan")
        out["neg_pass"] = float(np.mean([v >= THR for _, v in neg])) if neg else float("nan")
    return out


def fmt(m):
    s = f"n {m['n_neg']:4d}(양성 {m['n_pos']:4d}, 화자 {m['spk']:2d}) AUC {m['auc']:.3f} [{m['ci'][0]:.3f}, {m['ci'][1]:.3f}]"
    if "pos_pass" in m:
        s += f" | 0.05 통과: 맞게 낸 X {m['pos_pass']:.3f}, 대치 {m['neg_pass']:.3f}"
    return s


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "out/app_dir.json"
    d, err, pairs, trues = load(path)
    print(f"클립 {len(d)} 오류 {len(err)} | 538 {sum(r['group'] == '538' for r in d)} 608 {sum(r['group'] == '608' for r in d)}")
    summary = {"pairs": {}, "decisions": {}}
    for g in ("538", "608"):
        print(f"\n===== {g} =====")
        for title, plist in (("앱 방향(새 자음)", APP), ("된소리 두 방향", TENSE), ("9/28 방향 재확인", OLD), ("기준선(기존 3단계)", BASE)):
            print(f"-- {title}")
            for p in plist:
                key = f"{g}:{p[0]}→{p[1]}"
                ms = {} if p[0] == "ㅇ" else {"same": measure(pairs, trues, g, [p], "same")}
                ms["fixed"] = measure(pairs, trues, g, [p], "fixed")
                summary["pairs"][key] = ms
                label = "ㅎ 탈락(ㅇ→ㅎ)" if p[0] == "ㅇ" else f"{p[0]}→{p[1]}"
                if "same" in ms:
                    print(f"  {label:10s} 같은 녹음 {fmt(ms['same'])}")
                print(f"  {'' if 'same' in ms else label:10s} 고정 목표 {fmt(ms['fixed'])}")
        print("-- ㅎ 어절 첫머리만(보조)")
        for p, kind in (((("ㄱ", "ㅎ"),), "same"), ((("ㅇ", "ㅎ"),), "fixed")):
            m = measure(pairs, trues, g, list(p), kind, wi_only=True)
            summary["pairs"][f"{g}:{p[0][0]}→{p[0][1]}:wi:{kind}"] = m
            print(f"  {p[0][0]}→{p[0][1]} {kind} {fmt(m)}")
        print("-- 사전 등록 판정(주 지표 AUC >= 0.80)")
        for name, items in DECISIONS:
            res = []
            for plist, kind in items:
                m = measure(pairs, trues, g, plist, kind)
                res.append({"pairs": ["→".join(p) for p in plist], "kind": kind, **m})
            ok = all(r["auc"] >= CRIT for r in res)
            straddle = any(r["ci"][0] < CRIT <= r["ci"][1] or r["ci"][0] <= CRIT < r["ci"][1] for r in res)
            summary["decisions"][f"{g}:{name}"] = {"pass": ok, "ci_contains_080": straddle, "items": res}
            parts = "; ".join(f"{'+'.join(r['pairs'])} {r['kind']} {r['auc']:.3f} [{r['ci'][0]:.3f}, {r['ci'][1]:.3f}] n{r['n_neg']}"
                              for r in res)
            print(f"  {name}: {'통과' if ok else '미달'}{' (구간이 0.80 포함)' if straddle else ''} | {parts}")
    if len(sys.argv) > 2:
        json.dump(summary, open(sys.argv[2], "w"), ensure_ascii=False, indent=1)
