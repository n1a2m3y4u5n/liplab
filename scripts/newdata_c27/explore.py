#!/usr/bin/env python
"""범주 27 확인 전에 기존 자료만으로 하는 탐색(docs/newdata-c27-judgments-2026-10.md 3·4절). 새 자료를 읽지 않는다. 집계만 낸다.

  ~/Downloads/liplab/backend/.venv/bin/python scripts/newdata_c27/explore.py [--out X.json]

P3 낮은 음소 개수 규칙: speak_phoneme_floor.py와 같은 덤프·같은 음소 고르기(끝 음절 뺌), 538·608 모든 화자(탐색).
P4 같은 엄격도 격차 후보: 끝 자르기 판 점수, 608 범주 28 33명(10/7 V2 15명 + 10/9 새 18명), 538 1,200클립(10/6 600 + 10/9 새 21명 600).
"""
import argparse
import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)
LAB = os.environ.get("LIPLAB_LAB", os.path.expanduser("~/Downloads/liplab-lab"))
OUTDIR = os.path.join(LAB, "data", "newdata_c27")

# ───────────────────────── P3 ─────────────────────────
TAUS = (0.05, 0.2, 0.5)
ZS = (2.0, 3.0)
P3_CANDS = [(t, z) for t in TAUS for z in ZS]


def p3_rows():
    import speak_phoneme_floor as F

    def make(group, kind, spk, half, score, mean_vals, min_vals):
        return {"group": group, "kind": kind, "spk": spk, "half": half, "score": float(score), "vals": list(min_vals),
                "mean": sum(mean_vals) / len(mean_vals) if mean_vals else 0.0, "min": min(min_vals) if min_vals else None}
    F.make = make
    return F.load()


def p0_of(rows, tau):
    """538 자기 문장(맞게 말함)의 끝 음절 뺀 음소 가운데 tau 미만 비율(모든 538 자기 문장 합침)."""
    v = [x for r in rows if r["group"] == "538" and r["kind"] == "own" for x in r["vals"]]
    return float(np.mean(np.array(v) < tau))


def holds(r, tau, z, p0):
    """지금 합격(≥ 65)인 시도에서 낮은 음소 개수 L이 m·p0 + z·√(m·p0·(1−p0))보다 크면 보류."""
    if r["score"] < 65.0 or not r["vals"]:
        return False
    m = len(r["vals"])
    L = sum(x < tau for x in r["vals"])
    return L > m * p0 + z * math.sqrt(m * p0 * (1 - p0))


def p3_metrics(rows, cand, p0):
    tau, z = cand
    out = {}
    for g in ("538", "608"):
        res = {}
        for kind in ("own", "sub"):
            base = [r for r in rows if r["group"] == g and r["kind"] == kind and r["score"] >= 65.0]
            res[kind] = (sum(holds(r, tau, z, p0) for r in base) / len(base)) if base else None
            res["n_" + kind] = len(base)
        out[g] = {"FH": res["own"], "CS": res["sub"], "NG": res["sub"] - res["own"], "n_own_pass": res["n_own"], "n_sub_pass": res["n_sub"]}
    return out


def p3_ok(m):
    return m["538"]["FH"] <= 0.03 and m["608"]["FH"] <= 0.08 and m["538"]["CS"] >= 0.30 and m["608"]["NG"] >= 0


def p3():
    rows = p3_rows()
    p0 = {t: p0_of(rows, t) for t in TAUS}
    res, passing = {}, []
    for c in P3_CANDS:
        m = p3_metrics(rows, c, p0[c[0]])
        res[f"N({c[0]},{c[1]})"] = {g: {k: (round(v, 4) if isinstance(v, float) else v) for k, v in d.items()} for g, d in m.items()}
        if p3_ok(m):
            passing.append((m["538"]["NG"], -m["538"]["FH"], c))
    pick = max(passing)[2] if passing else None
    n = defaultdict(lambda: [0, set()])
    for r in rows:
        k = f"{r['group']}_{r['kind']}"
        n[k][0] += 1
        n[k][1].add(r["spk"])
    return {"p0": {str(t): round(v, 5) for t, v in p0.items()}, "candidates": res,
            "pick": None if pick is None else {"tau": pick[0], "z": pick[1], "p0": round(p0[pick[0]], 5)},
            "verdict": "통과 후보 있음" if pick else "실패(탐색)",
            "counts": {k: [v[0], len(v[1])] for k, v in sorted(n.items())}}


# ───────────────────────── P4 ─────────────────────────
GRID01 = np.round(np.arange(0, 100.0001, 0.1), 1)


def p4_rows():
    import scoring_608_newspk as N
    old = [r for r in N.old_rows("trim") if r["label"] in ("own", "other") and r["set"] in ("538", "608")]
    new = [{**r, "dg": r["dg_new"]} for r in N.new_rows() if r["label"] in ("own", "other") and r["set"] in ("538", "608")]
    rows = [{"set": r["set"], "spk": f"{r['set']}:{r['spk']}", "label": r["label"], "dg": float(r["dg"])} for r in old + new]
    return rows


def fa(rows, st, t):
    v = np.array([r["dg"] for r in rows if r["set"] == st and r["label"] == "other"])
    return float((v >= t).mean())


def fr(rows, st, t):
    v = np.array([r["dg"] for r in rows if r["set"] == st and r["label"] == "own"])
    return float((v < t).mean())


def k_samples(rows, st, label, k, n=1000, seed=1):
    """KSC remedies.r2와 같은 모의: 화자마다 같은 라벨의 서로 다른 행 k개 평균을 n번(np.random.default_rng(seed), 화자 이름 순)."""
    rng = np.random.default_rng(seed)
    by = defaultdict(list)
    for r in rows:
        if r["set"] == st and r["label"] == label:
            by[r["spk"]].append(r["dg"])
    out = {}
    for s in sorted(by):
        x = np.array(by[s])
        if len(x) < k:
            continue
        out[s] = np.array([x[rng.choice(len(x), k, replace=False)].mean() for _ in range(n)])
    return out


def k_rate(samp, t, label):
    """화자별 비율의 평균(화자 가중 같음). own은 불합격(< t), other는 합격(≥ t)."""
    vals = [((m < t).mean() if label == "own" else (m >= t).mean()) for m in samp.values()]
    return float(np.mean(vals))


def p4():
    rows = p4_rows()
    tG = next(float(g) for g in GRID01 if fa(rows, "608", g) <= 0.05 and fa(rows, "538", g) <= 0.05)
    t_same = next(t for t in range(0, 101) if fa(rows, "538", t) <= 0.05)
    res = {"n": {f"{st}_{lab}": sum(r["set"] == st and r["label"] == lab for r in rows) for st in ("538", "608") for lab in ("own", "other")},
           "spk": {st: len({r["spk"] for r in rows if r["set"] == st}) for st in ("538", "608")},
           "same_strictness_538": t_same,
           "at_same_strictness": {"608_FA": round(fa(rows, "608", t_same), 4), "608_FR": round(fr(rows, "608", t_same), 4)},
           "app65": {"608_FA": round(fa(rows, "608", 65), 4), "608_FR": round(fr(rows, "608", 65), 4), "538_FA": round(fa(rows, "538", 65), 4),
                     "538_FR": round(fr(rows, "538", 65), 4)},
           "C1_tG": tG, "C1_at_tG": {"608_FA": round(fa(rows, "608", tG), 4), "608_FR": round(fr(rows, "608", tG), 4),
                                     "538_FA": round(fa(rows, "538", tG), 4), "538_FR": round(fr(rows, "538", tG), 4)}}
    thr = {}
    for k in (1, 3):
        s608o = k_samples(rows, "608", "other", k)
        s538o = k_samples(rows, "538", "other", k)
        thr[k] = next(t for t in range(0, 101) if k_rate(s608o, t, "other") <= 0.05 and k_rate(s538o, t, "other") <= 0.05)
        s608w = k_samples(rows, "608", "own", k)
        res[f"C2_k{k}"] = {"thr": thr[k], "608_FA": round(k_rate(s608o, thr[k], "other"), 4), "608_FR": round(k_rate(s608w, thr[k], "own"), 4),
                           "538_FA": round(k_rate(s538o, thr[k], "other"), 4)}
    s608w1 = k_samples(rows, "608", "own", 1)
    res["C2_k1_at65_608_FR_speaker_mean"] = round(k_rate(s608w1, 65, "own"), 4)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(OUTDIR, "explore.json"))
    a = ap.parse_args()
    out = {"P3": p3(), "P4": p4()}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(out, open(a.out, "w"), ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
