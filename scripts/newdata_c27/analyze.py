#!/usr/bin/env python
"""범주 27 새 화자 판정(docs/newdata-c27-judgments-2026-10.md 2·4·5절, 3절은 보고만). 맥에서 파드 결과만 읽고 집계만 낸다.

  ~/Downloads/liplab/backend/.venv/bin/python scripts/newdata_c27/analyze.py RUN_DIR [--out X.json]

RUN_DIR = liplab-lab/data/pod_runs/<날짜>_<파드>/c27 (out/jobs.json, out/trim.jsonl, out/s18_features_*.csv, outb/trim_bridge.jsonl).
"""
import argparse
import json
import math
import os
import sys
from collections import Counter, defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, HERE)
import s18_confirm_newspk as S18  # noqa: E402
import scoring_608_newspk as N  # noqa: E402
from scoring_analyses_1006 import auc, ff, wp  # noqa: E402

LAB = os.path.expanduser("~/Downloads/liplab-lab")
NS_RUN = f"{LAB}/data/pod_runs/20261009_o11jkbqreech6s/ns"
RUN1 = f"{LAB}/data/pod_runs/20261006_uoqtuk2pyq0nty/s13"
EXPLORE = f"{LAB}/data/newdata_c27/explore.json"
T_PRIME, T_G, T_3, S18_THR = 61.0, 61.2, 58, 0.251
B = 2000


def jl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8")]


def r4(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), 4)


def boot(rows, stat, seed=0):
    return N.boot(rows, stat, seed)


def metric(rows, stat):
    return [r4(stat(rows))] + boot(rows, stat)


def group_of(clip):
    return "02-01" if "-02-01-" in clip else ("02-02" if "-02-02-" in clip else "other")


def c27_rows(run):
    rows = []
    for j in jl(f"{run}/out/trim.jsonl"):
        lab = {"same": "own", "diff": "other", "sub": "sub"}[j["kind"]]
        rows.append({"spk": j["spk"], "clip": j["clip"], "label": lab, "dg": j.get("score") if j.get("score") is not None else 0.0,
                     "err": int(j.get("score") is None), "phones": j.get("phones") or [], "pair": j.get("pair"), "grp": group_of(j["clip"])})
    return rows


def bridge_trim(run):
    ref = {(j["clip"], j["target"], j["kind"]): j.get("score") for j in jl(f"{NS_RUN}/out/dgop_new.jsonl") if j["set"] == "538"}
    d, miss = [], 0
    for j in jl(f"{run}/outb/trim_bridge.jsonl"):
        k = (j["clip"], j["target"], j["kind"])
        if k not in ref:
            miss += 1
            continue
        d.append(abs((j.get("score") or 0.0) - (ref[k] or 0.0)))
    return {"n": len(d), "missing": miss, "max": r4(max(d)) if d else None, "ok": bool(d and miss == 0 and max(d) <= 0.1)}


def rows538_new():
    return [{"spk": r["spk"], "label": r["label"], "dg": r["dg_new"]} for r in N.new_rows() if r["set"] == "538" and r["label"] in ("own", "other")]


def fa_s(rs, t):
    return wp([r["dg"] for r in rs if r["label"] == "other"], t)


def fr_s(rs, t):
    return ff([r["dg"] for r in rs if r["label"] == "own"], t)


def p1(rows, by_grp):
    r538 = rows538_new()
    out = {"t_prime": T_PRIME,
           "608_FA_t": metric(rows, lambda q: fa_s(q, T_PRIME)), "608_FR_t": metric(rows, lambda q: fr_s(q, T_PRIME)),
           "608_FA_65": metric(rows, lambda q: fa_s(q, 65)), "608_FR_65": metric(rows, lambda q: fr_s(q, 65)),
           "538_FA_t": r4(fa_s(r538, T_PRIME)), "538_FA_65": r4(fa_s(r538, 65)),
           "by_group": {g: {"FA_t": r4(fa_s(rs, T_PRIME)), "FR_t": r4(fr_s(rs, T_PRIME)), "n_own": sum(r["label"] == "own" for r in rs)}
                        for g, rs in by_grp.items()}}
    out["pass"] = bool(out["608_FA_t"][0] <= 0.05 and out["538_FA_t"] <= 0.05)
    return out


def p2(run):
    p, head = S18.frozen()
    br = S18.bridge(f"{run}/out/s18_features_bridge.csv", ref=f"{RUN1}/out/s18_features_new.csv")
    rows = [r for r in S18.load(f"{run}/out/s18_features_new.csv") if S18.stratum(r) == "P27"]
    r538 = [r for r in S18.load(f"{RUN1}/out/s18_features_new.csv") if r["set"] == "538"]
    m = S18.metrics(rows, head, S18_THR)
    m_dg = S18.metrics(rows, lambda r: r["dg"], 65.0)
    ci = S18.boot(rows, head, S18_THR)
    m538 = S18.metrics(r538, head, S18_THR)
    grp = {}
    for g in ("02-01", "02-02"):
        rs = [r for r in rows if group_of(r["clip"]) == g]
        if rs:
            mm = S18.metrics(rs, head, S18_THR)
            grp[g] = {k: r4(v) if isinstance(v, float) else v for k, v in mm.items()}
    out = {"bridge": br, "thr": S18_THR, "P27": {k: r4(v) if isinstance(v, float) else v for k, v in m.items()}, "P27_ci": ci,
           "P27_dgop65_b675975": {k: r4(v) if isinstance(v, float) else v for k, v in m_dg.items()},
           "538_run1": {k: r4(v) if isinstance(v, float) else v for k, v in m538.items()}, "by_group": grp}
    out["pass"] = bool(br["ok"] and m["auc"] >= 0.92 and m["wp"] <= 0.05 and m538["wp"] <= 0.05)
    out["result"] = ("보류(다리)" if not br["ok"] else "통과" if out["pass"] else "실패")
    return out


def k_samples(rows, label, k, n=1000, seed=1):
    rng = np.random.default_rng(seed)
    by = defaultdict(list)
    for r in rows:
        if r["label"] == label:
            by[r["spk"]].append(r["dg"])
    out = {}
    for s in sorted(by):
        x = np.array(by[s])
        if len(x) < k:
            continue
        out[s] = np.array([x[rng.choice(len(x), k, replace=False)].mean() for _ in range(n)])
    return out


def p4(rows):
    c1 = {"tG": T_G, "608_FA": metric(rows, lambda q: fa_s(q, T_G)), "608_FR": metric(rows, lambda q: fr_s(q, T_G)),
          "608_FR_65": metric(rows, lambda q: fr_s(q, 65)),
          "dFR_tG_minus_65": metric(rows, lambda q: fr_s(q, T_G) - fr_s(q, 65))}
    c1["pass"] = bool(c1["608_FA"][0] <= 0.05 and c1["dFR_tG_minus_65"][2] < 0)
    so3, sw3, sw1 = k_samples(rows, "other", 3), k_samples(rows, "own", 3), k_samples(rows, "own", 1)
    spks = sorted(set(so3) & set(sw3) & set(sw1))
    fa3 = np.array([(so3[s] >= T_3).mean() for s in spks])
    fr3 = np.array([(sw3[s] < T_3).mean() for s in spks])
    fr1 = np.array([(sw1[s] < 65).mean() for s in spks])
    rng = np.random.default_rng(0)
    idx = [rng.choice(len(spks), len(spks), replace=True) for _ in range(B)]

    def ci(arr):
        bs = [float(np.mean(arr[i])) for i in idx]
        return [r4(np.mean(arr)), r4(np.percentile(bs, 2.5)), r4(np.percentile(bs, 97.5))]
    c2 = {"t3": T_3, "n_spk": len(spks), "608_FA_k3": ci(fa3), "608_FR_k3": ci(fr3), "608_FR_k1_65": ci(fr1), "dFR_k3_minus_k1_65": ci(fr3 - fr1)}
    c2["pass"] = bool(c2["608_FA_k3"][0] <= 0.05 and c2["dFR_k3_minus_k1_65"][2] < 0)
    t_same = 57
    gap = {"same_strictness": t_same, "608_FA": metric(rows, lambda q: fa_s(q, t_same)), "608_FR": metric(rows, lambda q: fr_s(q, t_same))}
    return {"gap_at_57": gap, "C1": c1, "C2": c2}


def p3_report(rows):
    ex = json.load(open(EXPLORE))
    p0 = ex["P3"]["p0"]["0.05"]
    sys.path.insert(0, os.path.join(os.path.dirname(SCRIPTS), "backend"))
    from phone_reliability import final_syllable_start

    def vals(ph):
        key = "dgop" if ph and "dgop" in ph[0] else "naive"
        cut = final_syllable_start([p.get("token") or "" for p in ph])
        return [p[key] for i, p in enumerate(ph) if i < cut and p.get("aligned") and p.get("scorable") and not p.get("silent_h")
                and p.get(key) is not None]

    def hold(r, tau=0.05, z=3.0):
        v = vals(r["phones"])
        if r["dg"] < 65 or not v:
            return False
        m = len(v)
        return sum(x < tau for x in v) > m * p0 + z * math.sqrt(m * p0 * (1 - p0))
    out = {}
    for lab in ("own", "sub"):
        base = [r for r in rows if r["label"] == lab and r["dg"] >= 65]
        out[lab] = {"n_pass": len(base), "held": r4(sum(hold(r) for r in base) / len(base)) if base else None}
    out["rule"] = "N(0.05, 3.0)"
    out["sub_pass_now"] = r4(np.mean([r["dg"] >= 65 for r in rows if r["label"] == "sub"])) if any(r["label"] == "sub" for r in rows) else None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--out", default=os.path.join(LAB, "data", "newdata_c27", "report.json"))
    a = ap.parse_args()
    J = json.load(open(f"{a.run}/out/jobs.json", encoding="utf-8"))
    rows_all = c27_rows(a.run)
    rows = [r for r in rows_all if r["label"] in ("own", "other")]
    by_grp = defaultdict(list)
    for r in rows:
        by_grp[r["grp"]].append(r)
    own = [r for r in rows if r["label"] == "own"]
    info = {"select": J.get("select"), "n_spk": len({r["spk"] for r in own}), "n_own": len(own), "n_other": sum(r["label"] == "other" for r in rows),
            "n_sub": sum(r["label"] == "sub" for r in rows_all), "errors": sum(r["err"] for r in rows_all),
            "own_by_group": {g: sum(r["label"] == "own" for r in rs) for g, rs in by_grp.items()},
            "own_per_spk": sorted(Counter(r["spk"] for r in own).values())}
    enough = info["n_spk"] >= 10 and info["n_own"] >= 100
    btrim = bridge_trim(a.run)
    out = {"info": info, "enough": enough, "bridge_trim": btrim, "auc_trim": r4(auc([r["dg"] for r in own], [r["dg"] for r in rows if r["label"] == "other"]))}
    if enough:
        out["P1"] = p1(rows, by_grp)
        out["P1"]["result"] = "보류(다리)" if not btrim["ok"] else ("통과" if out["P1"]["pass"] else "실패")
        out["P2"] = p2(a.run)
        out["P4"] = p4(rows)
        for c in ("C1", "C2"):
            out["P4"][c]["result"] = "보류(다리)" if not btrim["ok"] else ("통과" if out["P4"][c]["pass"] else "실패")
        out["P3_report"] = p3_report(rows_all)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(out, open(a.out, "w"), ensure_ascii=False, indent=1, default=lambda x: x.item() if hasattr(x, "item") else str(x))
    print(json.dumps(out, ensure_ascii=False, indent=1, default=lambda x: x.item() if hasattr(x, "item") else str(x)))


if __name__ == "__main__":
    main()
