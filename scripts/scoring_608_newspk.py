"""608 새 화자(KSC 10/8~9 받기, 범주 28 18명)로 말하기 채점 결정 확인(docs/scoring-608-newspk-2026-10.md). 맥에서 점수 파일만 읽는다.

    python3 scripts/scoring_608_newspk.py frozen              옛 자료(10/7 정제본 V2·538 10/6)만으로 고정값을 낸다(새 화자 점수를 읽지 않음)
    python3 scripts/scoring_608_newspk.py build RUN_DIR       파드 결과 → 문장별 CSV(저장소 밖, liplab-lab/data/scores_newspk608_2026-10-09/)
    python3 scripts/scoring_608_newspk.py report [OUT.json]   다리·판정(N1~N7)·합친 값

RUN_DIR: liplab-lab/data/pod_runs/<날짜>_<파드>/ns(out/dgop_old.jsonl, dgop_new.jsonl, tscore.jsonl). 저장소에는 집계만 적는다.
"""
import collections
import csv
import hashlib
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import scoring_608_recut as RC  # noqa: E402

SA = RC.SA
auc, ff, wp, jl, hangul, sid_of = SA.auc, SA.ff, SA.wp, RC.jl, RC.hangul, RC.sid_of
LAB = RC.LAB
NEWROOT = f"{LAB}/data/scores_newspk608_2026-10-09"
V2 = f"{RC.OUTROOT}/V2"
RC_RUN = f"{LAB}/data/pod_runs/20261007_kcs2amnnqa24d7/rc"
KSC = os.path.expanduser("~/Downloads/KSC2026/liplab/data/expand")
S13 = f"{LAB}/data/pod_runs/20261006_uoqtuk2pyq0nty/s13/out"
PASS = 65.0
B = 2000
GRID01 = np.round(np.arange(0, 100.0001, 0.1), 1)


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def boot(rows, stat, seed=0):
    """화자 부트스트랩 95% 구간(세트 안에서 화자 복원 추출, 뽑힌 화자의 모든 행). 10/7 RC.boot과 같다."""
    return RC.boot(rows, stat, seed)


def metric(rs, fn):
    return [round(float(fn(rs)), 4)] + boot(rs, fn)


# ───────────────────────── 옛 자료(고정값의 출처) ─────────────────────────
def old_rows(ver):
    """ver='old': 10/7 V2 CSV(b675975, own·other·cohort·noise). ver='trim': 끝 자르기 판 own·other(538 10/6 600클립 R_trim50,
    608 V2 = 10/7 D11 trim_report와 같은 행 고르기)."""
    if ver == "old":
        SA.D = V2
        return [r for r in SA.joined()]
    rows = []
    for j in jl(f"{RC.FV}/merged/main.jsonl"):
        if j["set"] == "538" and j["variant"] == "R_trim50":
            for t in j["targets"]:
                rows.append({"set": "538", "spk": j["spk"], "half": j["half"], "clip": j["clip"],
                             "label": "own" if t["kind"] == "same" else "other", "dg": t["score"] if t["score"] is not None else 0.0})
    cs = RC.cut_sets(RC_RUN)
    rec = {}
    for f in (f"{RC.FV}/merged/main.jsonl", f"{RC.FV}/mainfix.jsonl"):
        for j in jl(f):
            if j["set"] == "608" and j["variant"] == "R_trim50":
                rec[j["clip"]] = j
    drop, acc = cs["drop"]["V2"], cs["acc"]
    for clip, j in rec.items():
        if clip in drop or clip in acc:
            continue
        own = hangul([t for t in j["targets"] if t["kind"] == "same"][0]["target"])
        for t in j["targets"]:
            if t["kind"] == "diff" and hangul(t["target"]) == own:
                continue
            rows.append({"set": "608", "spk": j["spk"], "half": j["half"], "clip": clip, "label": "own" if t["kind"] == "same" else "other",
                         "dg": t["score"] if t["score"] is not None else 0.0})
    own = {j["clip"]: hangul(j["target"]) for j in jl(f"{RC_RUN}/out/dgop_full_recut.jsonl")
           if j["set"] == "608" and j["clip"] in acc and j["kind"] == "same"}
    for j in jl(f"{RC_RUN}/out/trim_recut.jsonl"):
        if j["set"] != "608" or j["clip"] not in acc or j["kind"] not in ("same", "diff"):
            continue
        if j["kind"] == "diff" and hangul(j["target"]) == own[j["clip"]]:
            continue
        rows.append({"set": "608", "spk": j["spk"], "half": RC.half_of(j["spk"]), "clip": j["clip"],
                     "label": "own" if j["kind"] == "same" else "other", "dg": j.get("score") if j.get("score") is not None else 0.0})
    return rows


def cmd_frozen():
    os.makedirs(NEWROOT, exist_ok=True)
    out = {}
    for ver in ("old", "trim"):
        rows = [r for r in old_rows(ver) if r["label"] in ("own", "other")]
        h0 = [r for r in rows if r["half"] == 0]
        o538 = [r["dg"] for r in h0 if r["set"] == "538" and r["label"] == "other"]
        t21 = next(float(g) for g in GRID01 if wp(o538, g) <= 0.05)
        tb = SA.lowest_threshold(GRID01, lambda x: x["dg"], h0)
        all538 = [r["dg"] for r in rows if r["set"] == "538" and r["label"] == "other"]
        t_same = next(t for t in range(0, 101) if wp(all538, t) <= 0.05)
        out[ver] = {"t21_h0_538": t21, "t_both_h0": tb, "t_same_strictness_538all": t_same,
                    "n": {"538_own": sum(r["set"] == "538" and r["label"] == "own" for r in rows),
                          "608_own": sum(r["set"] == "608" and r["label"] == "own" for r in rows),
                          "608_spk": len({r["spk"] for r in rows if r["set"] == "608"})}}
    out["s1_params"] = json.load(open(f"{V2}/s1_params.json"))
    p15 = json.load(open(f"{V2}/s15_params.json"))
    out["s15_params"] = {k: v for k, v in p15.items() if not k.startswith("ecdf")}
    out["s15_noise_pass_V2"] = json.load(open(f"{V2}/s15_confirm.json"))["F1_noise_pass"]
    out["sha256"] = {"s1_params.json": sha(f"{V2}/s1_params.json"), "s15_params.json": sha(f"{V2}/s15_params.json")}
    json.dump(out, open(f"{NEWROOT}/frozen.json", "w"), ensure_ascii=False, indent=1, default=SA._np)
    print(json.dumps(out, ensure_ascii=False, indent=1, default=SA._np))


# ───────────────────────── 새 화자 행 ─────────────────────────
LABEL = {"same": "own", "diff": "other", "cohort": "cohort"}


def cmd_build(run):
    """파드 결과를 (세트, 클립, 목표, 종류)로 합친 문장별 CSV(점수·라벨·화자·문장 ID만, 저장소 밖)."""
    os.makedirs(NEWROOT, exist_ok=True)
    rows = {}
    for name, f in (("dg_old", "dgop_old.jsonl"), ("dg_new", "dgop_new.jsonl")):
        for j in jl(f"{run}/out/{f}"):
            k = (j["set"], j["clip"], j["target"], j["kind"])
            r = rows.setdefault(k, {"set": j["set"], "spk": j["spk"], "clip": j["clip"], "own_sid": "", "target_sid": sid_of(j["target"]),
                                    "label": LABEL[j["kind"]], "dg_old": "", "dg_new": "", "err_old": 0, "err_new": 0, "r0": "", "r0c": ""})
            if j.get("score") is None:
                r[name] = 0.0
                r["err_" + name[3:]] = 1
            else:
                r[name] = j["score"]
    for j in jl(f"{run}/out/tscore.jsonl"):
        r = rows[(j["set"], j["clip"], j["target"], j["kind"])]
        r["r0"], r["r0c"] = j["r0"], j["r0_c"]
    own = {(r["set"], r["clip"]): r["target_sid"] for r in rows.values() if r["label"] == "own"}
    for r in rows.values():
        r["own_sid"] = own[(r["set"], r["clip"])]
    fields = ["set", "spk", "clip", "own_sid", "target_sid", "label", "dg_old", "dg_new", "err_old", "err_new", "r0", "r0c"]
    RC.write_csv(f"{NEWROOT}/pairs.csv", list(rows.values()), fields)
    from collections import Counter
    print("BUILD_OK", dict(Counter((r["set"], r["label"]) for r in rows.values())),
          "errors", sum(r["err_old"] for r in rows.values()), sum(r["err_new"] for r in rows.values()))


def new_rows():
    out = []
    for r in RC.read_csv(f"{NEWROOT}/pairs.csv"):
        out.append({**r, "dg_old": float(r["dg_old"]), "dg_new": float(r["dg_new"]), "err_old": int(r["err_old"]), "err_new": int(r["err_new"]),
                    "r0": float(r["r0"]) if r["r0"] != "" else None, "r0c": float(r["r0c"]) if r["r0c"] != "" else None, "half": 1})
    return out


def as_dg(rows, field):
    return [{**r, "dg": r[field]} for r in rows]


def sel(rows, st, label=None):
    return [r for r in rows if r["set"] == st and (label is None or r["label"] == label)]


# ───────────────────────── 다리 ─────────────────────────
def bridges(rows):
    res = {}
    ksc = {j["clip"]: j["score"] for j in jl(f"{KSC}/pod_out/own_dgop.jsonl")}
    d = [abs(r["dg_old"] - ksc[r["clip"]]) for r in sel(rows, "608", "own")]
    res["B1"] = {"n": len(d), "frac_le_0.1": round(float(np.mean(np.array(d) <= 0.1)), 4), "median": float(np.median(d)), "max": float(max(d))}
    res["B1"]["ok"] = bool(res["B1"]["frac_le_0.1"] >= 0.95 and res["B1"]["median"] == 0)
    s13 = {(j["clip"], j["target"], j["kind"]): j.get("score") for j in jl(f"{S13}/dgop_full.jsonl") if j["set"] == "538"}
    new538 = {(j["clip"], j["target"], j["kind"]): j.get("score") for j in jl(f"{RUN}/out/dgop_old.jsonl") if j["set"] == "538" and j["kind"] != "cohort"}
    d = [abs((v or 0.0) - (s13[k] or 0.0)) for k, v in new538.items()]
    res["B2"] = {"n": len(d), "max": float(max(d)), "n_gt_0.1": int(sum(x > 0.1 for x in d)), "ok": bool(max(d) <= 0.1)}
    old10 = {(j["clip"], j["target"], j["kind"]): j.get("score") for j in jl(f"{RC.SC}/dgop_full.jsonl") if j["set"] == "608"}
    tr50 = {}
    for f in (f"{RC.FV}/merged/main.jsonl", f"{RC.FV}/mainfix.jsonl"):
        for j in jl(f):
            if j["set"] == "608" and j["variant"] == "R_trim50":
                for t in j["targets"]:
                    tr50[(j["clip"], t["target"], t["kind"])] = t["score"]
    b3 = []
    for name, src in (("old", old10), ("new", tr50)):
        for j in jl(f"{RUN}/out/dgop_{name}.jsonl"):
            if j["set"] == "bridge608":
                k = (j["clip"], j["target"], j["kind"])
                b3.append({"ver": name, "clip": j["clip"], "kind": j["kind"], "here": j.get("score"), "ref": src.get(k)})
    ok_old = all(x["ref"] is not None and abs(x["here"] - x["ref"]) <= 0.1 for x in b3 if x["ver"] == "old")
    ok_new = all(x["ref"] is not None and abs(x["here"] - x["ref"]) <= 0.1 for x in b3 if x["ver"] == "new")
    res["B3"] = {"rows": len(b3), "max_old": max(abs(x["here"] - x["ref"]) for x in b3 if x["ver"] == "old" and x["ref"] is not None),
                 "max_new": max(abs(x["here"] - x["ref"]) for x in b3 if x["ver"] == "new" and x["ref"] is not None), "ok_old": ok_old, "ok_new": ok_new}
    return res


# ───────────────────────── 판정 ─────────────────────────
def own_other(rs, st="608"):
    return [r for r in rs if r["set"] == st and r["label"] in ("own", "other")]


def n1_n3(rs, tag=""):
    r = own_other(rs)
    own = [x for x in r if x["label"] == "own"]
    p = 1 - ff([x["dg"] for x in own], PASS)
    ci = boot(own, lambda q: 100 * (1 - ff([x["dg"] for x in q], PASS)) - 5)
    v = int(round(100 * p - 5))
    by = collections.defaultdict(list)
    for x in own:
        by[x["spk"]].append(x["dg"] >= PASS)
    rates = sorted(round(float(np.mean(b)), 2) for b in by.values() if len(b) >= 13)
    n1 = {"pass65": round(p, 4), "rule_value": round(100 * p - 5, 2), "v": v, "ci": ci, "verdict": "그대로" if v >= 68 else "바뀜",
          "raise_to_76_supported": bool(ci[0] >= 76), "spk_passrate_n13plus": rates, "n_spk_n13plus": len(rates),
          "n_spk_below_68": sum(x < 0.68 for x in rates), "n_spk_below_76": sum(x < 0.76 for x in rates),
          "spk_passrate_all": sorted(round(float(np.mean(b)), 2) for b in by.values())}
    f = metric(r, RC.ff_of("dg", PASS))
    n3 = {"ff65": f, "verdict": "그대로" if f[1] > 0.10 else ("판정 불가" if f[0] > 0.10 else "바뀜")}
    basic = {"n_own": len(own), "n_other": len(r) - len(own), "n_spk": len({x["spk"] for x in r}), "auc": metric(r, RC.auc_of("dg")),
             "ff65": f, "wp65": metric(r, RC.wp_of("dg", PASS)), "median_own": round(float(np.median([x["dg"] for x in own])), 1)}
    return basic, n1, n3


def n2(rs, fz):
    t21, tb = fz["t21_h0_538"], fz["t_both_h0"]
    o538 = [x["dg"] for x in rs if x["set"] == "538" and x["label"] == "other"]
    r608 = own_other(rs)
    a = wp(o538, t21) <= 0.05
    b = wp([x["dg"] for x in r608 if x["label"] == "other"], t21) > 0.05
    c = wp(o538, tb) <= 0.05 and wp([x["dg"] for x in r608 if x["label"] == "other"], tb) <= 0.05
    r538 = own_other(rs, "538")
    res = {"t21": t21, "t_both": tb, "a_wp538_at_t21": metric(r538, RC.wp_of("dg", t21)), "b_wp608_at_t21": metric(r608, RC.wp_of("dg", t21)),
           "ff608_at_t21": metric(r608, RC.ff_of("dg", t21)), "c_wp538_at_tb": round(wp(o538, tb), 4), "c_wp608_at_tb": metric(r608, RC.wp_of("dg", tb)),
           "ff608_at_tb": metric(r608, RC.ff_of("dg", tb)), "wp608_at65": metric(r608, RC.wp_of("dg", PASS)), "wp538_at65": metric(r538, RC.wp_of("dg", PASS)),
           "a": bool(a), "b": bool(b), "c": bool(c)}
    res["verdict"] = "바뀜" if (c or not b) else "그대로"
    return res


def n4(rs, p):
    a1, a2 = SA.s1_scores(rs, p)

    def dec(name, r):
        if name == "A0":
            return r["dg"] >= PASS
        if name == "A1":
            z = a1(r)
            return r["dg"] >= PASS if z is None else z >= p["thr_a1"]
        if name == "A2":
            return a2(r) >= p["thr_a2"]
        return r["dg"] >= p[f"thr_a3_{r['set']}"]
    out = {}
    for m in ("A0", "A1", "A2", "A3"):
        d = {}
        for st in ("538", "608"):
            rr = own_other(rs, st)
            ffn = lambda q, m=m: 1 - float(np.mean([dec(m, x) for x in q if x["label"] == "own"]))      # noqa: E731
            wpn = lambda q, m=m: float(np.mean([dec(m, x) for x in q if x["label"] == "other"]))       # noqa: E731
            d[f"ff_{st}"], d[f"wp_{st}"] = metric(rr, ffn), metric(rr, wpn)
        by = collections.defaultdict(list)
        for x in sel(rs, "608", "own"):
            by[x["spk"]].append(dec(m, x))
        d["spk608_passrate_n13plus"] = sorted(round(float(np.mean(v)), 2) for v in by.values() if len(v) >= 13)
        d["criteria"] = {"ff608<=18%": d["ff_608"][0] <= 0.18, "wp538<=5%": d["wp_538"][0] <= 0.05, "wp608<=5%": d["wp_608"][0] <= 0.05}
        d["pass_all"] = all(d["criteria"].values())
        if m == "A1":
            d["no_cohort_clips"] = sum(a1(x) is None for x in rs if x["label"] in ("own", "other"))
        out[m] = d
    r608 = own_other(rs)
    out["A1_minus_A0_ff608"] = metric(r608, lambda q: float(np.mean([dec("A0", x) for x in q if x["label"] == "own"]))
                                      - float(np.mean([dec("A1", x) for x in q if x["label"] == "own"])))
    out["verdict"] = "확인 통과" if out["A1"]["pass_all"] else "확인 실패"
    return out


def n5(rs, p, noise_pass):
    f1, _ = SA.make_fusers(p)
    rr = [x for x in rs if x["label"] in ("own", "other") and x["r0c"] is not None]
    o = {}
    for st in ("538", "608"):
        q = [x for x in rr if x["set"] == st]
        o[st] = {"auc": metric(q, lambda z: auc([f1(x) for x in z if x["label"] == "own"], [f1(x) for x in z if x["label"] == "other"])),
                 "ff": metric(q, lambda z: ff([f1(x) for x in z if x["label"] == "own"], p["thr_f1"])),
                 "wp": metric(q, lambda z: wp([f1(x) for x in z if x["label"] == "other"], p["thr_f1"])),
                 "dg65_ff": round(ff([x["dg"] for x in q if x["label"] == "own"], PASS), 4),
                 "tr_auc": round(auc([x["r0c"] for x in q if x["label"] == "own"], [x["r0c"] for x in q if x["label"] == "other"]), 4)}
    c1 = o["608"]["auc"][0] >= 0.92
    c2 = o["608"]["ff"][0] <= o["608"]["dg65_ff"] - 0.05
    c3 = o["538"]["wp"][0] <= 0.05
    c4 = noise_pass == 0
    o["criteria"] = {"C1": c1, "C2": c2, "C3": c3, "C4_from_V2": c4, "C5": "미측정"}
    o["verdict"] = "바뀜(채택 후보, C5 미측정)" if (c1 and c2 and c3 and c4) else "그대로(실패)"
    return o


def n6(rs, B=2000, seed=0):
    rgrid = np.round(np.arange(0.5, 2.0001, 0.1), 2)
    res = {}
    for st in ("538", "608"):
        q = [x for x in own_other(rs, st) if x["r0"] is not None]
        by = collections.defaultdict(list)
        for x in q:
            by[x["spk"]].append(x)
        spks = sorted(by)

        def stats(sample):
            own = [x for x in sample if x["label"] == "own"]
            oth = [x for x in sample if x["label"] == "other"]
            a_d, a_t = auc([x["dg"] for x in own], [x["dg"] for x in oth]), auc([x["r0"] for x in own], [x["r0"] for x in oth])
            f_d, f_t = ff([x["dg"] for x in own], PASS), ff([x["r0"] for x in own], PASS)
            w_d, w_t = wp([x["dg"] for x in oth], PASS), wp([x["r0"] for x in oth], PASS)
            return [a_d, a_t, a_d - a_t, f_d, f_t, f_d - f_t, w_d, w_t, w_d - w_t] + [(f_d + r * w_d) - (f_t + r * w_t) for r in rgrid]
        pt = stats(q)
        rng = np.random.default_rng(seed)
        bs = np.array([stats([x for i in rng.choice(len(spks), len(spks), replace=True) for x in by[spks[i]]]) for _ in range(B)])
        lo, hi = np.nanpercentile(bs, 2.5, axis=0), np.nanpercentile(bs, 97.5, axis=0)
        names = ["auc_dgop", "auc_tr", "d_auc", "ff_dgop", "ff_tr", "d_ff", "wp_dgop", "wp_tr", "d_wp"]
        r_ = {n: [round(pt[i], 4), round(lo[i], 4), round(hi[i], 4)] for i, n in enumerate(names)}
        cost = {f"{rv:.1f}": [round(pt[9 + i], 4), round(lo[9 + i], 4), round(hi[9 + i], 4)] for i, rv in enumerate(rgrid)}
        r_["cost_diff"] = cost
        c = cost["1.0"]
        r_["verdict"] = "D-GOP 비용이 낮다" if c[2] < 0 else ("전사 경로 비용이 낮다" if c[1] > 0 else "판정 불가")
        res[st] = r_
    return res


def n7(rows):
    r = [x for x in rows if x["set"] == "608" and x["label"] in ("own", "other")]
    out = {}
    for name, f in (("R", "dg_old"), ("T", "dg_new")):
        q = as_dg(r, f)
        out[name] = {"auc": metric(q, RC.auc_of("dg")), "ff65": round(RC.ff_of("dg", PASS)(q), 4), "wp65": round(RC.wp_of("dg", PASS)(q), 4)}
    out["d_auc_T_minus_R"] = metric(r, lambda q: auc([x["dg_new"] for x in q if x["label"] == "own"], [x["dg_new"] for x in q if x["label"] == "other"])
                                    - auc([x["dg_old"] for x in q if x["label"] == "own"], [x["dg_old"] for x in q if x["label"] == "other"]))
    c2 = out["T"]["auc"][0] >= out["R"]["auc"][0] - 0.01
    c3 = out["T"]["ff65"] <= out["R"]["ff65"] + 0.02 and out["T"]["wp65"] <= 0.05
    out["C2"], out["C3"] = bool(c2), bool(c3)
    out["verdict"] = "그대로" if c2 and c3 else "바뀜"
    return out


def combined(rows, ver):
    old = [x for x in old_rows(ver) if x["set"] == "608" and x["label"] in ("own", "other")]
    new = as_dg([x for x in rows if x["set"] == "608" and x["label"] in ("own", "other")], "dg_old" if ver == "old" else "dg_new")
    rs = [{"spk": "V2:" + x["spk"], "label": x["label"], "dg": x["dg"], "set": "608"} for x in old] + \
         [{"spk": "N:" + x["spk"], "label": x["label"], "dg": x["dg"], "set": "608"} for x in new]
    basic, d1, d3 = n1_n3(rs)
    return {"basic": basic, "N1_v": d1["v"], "N1_ci": d1["ci"], "N3_ff65": d3["ff65"]}


def cmd_report(out_json=None):
    rows = new_rows()
    fz = json.load(open(f"{NEWROOT}/frozen.json"))
    res = {"bridges": bridges(rows), "errors": {"old": sum(x["err_old"] for x in rows), "new": sum(x["err_new"] for x in rows)}}
    for ver, f in (("trim", "dg_new"), ("old", "dg_old")):
        rs = as_dg(rows, f)
        basic, d1, d3 = n1_n3(rs)
        r538 = own_other(rs, "538")
        res[ver] = {"basic608": basic, "basic538": {"auc": metric(r538, RC.auc_of("dg")), "ff65": metric(r538, RC.ff_of("dg", PASS)),
                                                     "wp65": metric(r538, RC.wp_of("dg", PASS))},
                    "same_strictness57": {"ff608": metric(own_other(rs), RC.ff_of("dg", 57)), "wp608": metric(own_other(rs), RC.wp_of("dg", 57))},
                    "N1": d1, "N2": n2(rs, fz[ver]), "N3": d3, "N4_S1": n4(rs, fz["s1_params"]), "N6_S19": n6(rs),
                    "combined33": combined(rows, ver)}
        if ver == "old":
            p15 = json.load(open(f"{V2}/s15_params.json"))
            res[ver]["N5_S15"] = n5(rs, p15, fz["s15_noise_pass_V2"])
    res["N7_trim"] = n7(rows)
    txt = json.dumps(res, ensure_ascii=False, indent=1, default=SA._np)
    print(txt)
    open(out_json or f"{NEWROOT}/report.json", "w").write(txt)


RUN = None

if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "frozen":
        cmd_frozen()
    elif cmd == "build":
        cmd_build(sys.argv[2])
    elif cmd == "report":
        RUN = sys.argv[2]
        cmd_report(sys.argv[3] if len(sys.argv) > 3 else None)
    else:
        sys.exit(f"알 수 없는 명령 {cmd}")
