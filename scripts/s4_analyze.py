"""S4 채점 모델 증류 판정(docs/scorer-distill-2026-10.md 7절). 맥에서 numpy만으로 돈다.

    python scripts/s4_analyze.py RESULTS_DIR [요약.json]

RESULTS_DIR(파드에서 받은 것, 저장소 밖): e1_teacher.jsonl, e1_{H,X}.jsonl(가중치 전용 int8), e1_{H,X}_fp32.jsonl, e1_{H,X}_dyn8.jsonl,
e2_teacher.json, e2_{H,X}.json, dev_teacher.jsonl, dev_{H,X}.jsonl, lat_*.json, export_{H,X}.json, train_{H,X}.json.
교사 기준값은 10/6 CPU int8 점수(REF, dgop_full.jsonl)다.
"""
import collections
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "backend"))
import speak_consonant_app_analyze as CA  # noqa: E402

REF = os.environ.get("S4_REF", os.path.expanduser(
    "~/Downloads/liplab-lab/data/pod_runs/20261006_35zrgz6wvrqiho/sc/out/dgop_full.jsonl"))
TEACHER_AUC608 = 0.9034
DROP = 0.01
WP_MAX = 0.05
SIZE_MAX = 105e6
LAT_MAX = 3.0
PASS = 65.0
B = 2000


def hangul(s):
    return re.sub(r"[^가-힣]", "", s or "")


def auc(pos, neg):
    return CA.auc(pos, neg)


def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8")] if os.path.exists(p) else None


def key(r):
    return (r["set"], r["clip"], r["target"], r["kind"])


def e1_rows(rows, field="raw"):
    """10/7 규칙(한글만 남긴 목표가 자기 문장과 같은 diff 제외)을 적용한 (set, spk, clip, label, value). 실패는 0."""
    own = {(r["set"], r["clip"]): r["target"] for r in rows if r["kind"] == "same"}
    out = []
    for r in rows:
        if r["set"] not in ("538", "608") or r["kind"] not in ("same", "diff"):
            continue
        if r["kind"] == "diff" and hangul(r["target"]) == hangul(own[(r["set"], r["clip"])]):
            continue
        v = r.get(field)
        out.append({"set": r["set"], "spk": r["spk"], "clip": r["clip"], "target": r["target"],
                    "label": "own" if r["kind"] == "same" else "other", "v": 0.0 if v is None else float(v),
                    "failed": v is None})
    return out


def sel(rows, st, label):
    return [r["v"] for r in rows if r["set"] == st and r["label"] == label]


def matched_tau(rows, ref_rows):
    """교사(65점)의 자기 문장 합친 불합격 비율과 같아지는 학생 원점수 분위수."""
    q = float(np.mean([r["v"] < PASS for r in ref_rows if r["label"] == "own"]))
    own = np.array([r["v"] for r in rows if r["label"] == "own"])
    tau = float(np.quantile(own, q, method="inverted_cdf"))
    return tau, q, float(np.mean(own < tau))


def boot_auc_diff(stu, ref, st="608", seed=0):
    """같은 행끼리 짝지은 화자 부트스트랩: 학생 AUC − 교사 AUC."""
    rk = {(r["clip"], r["target"], r["label"]): r["v"] for r in ref if r["set"] == st}
    by = collections.defaultdict(list)
    for r in stu:
        if r["set"] != st:
            continue
        k = (r["clip"], r["target"], r["label"])
        if k in rk:
            by[r["spk"]].append((r["label"], r["v"], rk[k]))
    spk = sorted(by)
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(B):
        pick = rng.choice(len(spk), len(spk), replace=True)
        rows = [x for i in pick for x in by[spk[i]]]
        ps = [x[1] for x in rows if x[0] == "own"]; ns = [x[1] for x in rows if x[0] == "other"]
        pt = [x[2] for x in rows if x[0] == "own"]; nt = [x[2] for x in rows if x[0] == "other"]
        if ps and ns:
            vals.append(auc(ps, ns) - auc(pt, nt))
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]


def half(spk):
    import zlib
    return zlib.crc32(spk.encode()) % 2


def cons_decisions(path):
    if not os.path.exists(path):
        return None
    d, err, pairs, trues = CA.load(path)
    out = {"n_clips": len(d), "errors": len(err)}
    items = [("ㅅ", [("ㄷ", "ㅅ")], "same"), ("ㅈ", [("ㄷ", "ㅈ"), ("ㅊ", "ㅈ")], "same"), ("ㅊ", [("ㅈ", "ㅊ")], "same"),
             ("ㅎ", [("ㄱ", "ㅎ")], "same"), ("ㅎ탈락", [("ㅇ", "ㅎ")], "fixed")]
    for g in ("538", "608"):
        for name, plist, kind in items:
            m = CA.measure(pairs, trues, g, plist, kind)
            out[f"{g}:{name}"] = {"auc": round(m["auc"], 4), "ci": [round(x, 4) for x in m["ci"]], "n_neg": m["n_neg"]}
        for p in (("ㅋ", "ㄱ"), ("ㅍ", "ㅂ")):
            m = CA.measure(pairs, trues, g, [p], "same")
            out[f"{g}:{p[0]}→{p[1]}(보고)"] = {"auc": round(m["auc"], 4), "ci": [round(x, 4) for x in m["ci"]], "n_neg": m["n_neg"]}
    keys = [f"{g}:{n}" for g in ("538", "608") for n, _, _ in items]
    out["min"] = min(out[k]["auc"] for k in keys)
    out["pass"] = all(out[k]["auc"] >= 0.80 for k in keys)
    return out


def calib_from_dev(dev_t, dev_s):
    """보고만: 개발 자료에서 교사 앵커 원점수가 놓인 분위수의 학생 원점수를 학생 앵커로(분위수 맞추기)."""
    import dgop
    cal = json.load(open(os.path.join(os.path.dirname(HERE), "backend", "data", "dgop_calibration_ours.json")))
    tk = {key(r): r.get("raw") for r in dev_t}
    pairs = [(tk[key(r)], r.get("raw")) for r in dev_s if key(r) in tk and tk[key(r)] is not None and r.get("raw") is not None]
    t = np.array([p[0] for p in pairs]); s = np.array([p[1] for p in pairs])
    raws = []
    for r_anchor in cal["severity_medians"]:
        q = float(np.mean(t <= r_anchor))
        raws.append(float(np.quantile(s, min(max(q, 0.0), 1.0))))
    out = dgop.fit_calibration(raws, cal["display_targets"], source="S4 학생: 개발 자료 분위수 맞추기")
    return out


def main(R, out_json=None):
    ref_raw = load_jsonl(REF)
    ref = e1_rows(ref_raw, "score")         # 교사 기준(10/6 CPU int8 표시 점수)
    ref_by = {(r["set"], r["clip"], r["target"], r["label"]): r for r in ref}
    res = {"ref": {"608_auc": round(auc(sel(ref, "608", "own"), sel(ref, "608", "other")), 4),
                   "538_auc": round(auc(sel(ref, "538", "own"), sel(ref, "538", "other")), 4),
                   "n608_own": len(sel(ref, "608", "own")), "n608_other": len(sel(ref, "608", "other")),
                   "n538_other": len(sel(ref, "538", "other")),
                   "own_fail65": round(float(np.mean([r["v"] < PASS for r in ref if r["label"] == "own"])), 4),
                   "608_wp65": round(float(np.mean(np.array(sel(ref, "608", "other")) >= PASS)), 4)}}
    # 다리
    tb = load_jsonl(f"{R}/e1_teacher.jsonl")
    if tb:
        tbr = e1_rows(tb, "score")
        d = [abs(r["v"] - ref_by[(r["set"], r["clip"], r["target"], r["label"])]["v"]) for r in tbr
             if (r["set"], r["clip"], r["target"], r["label"]) in ref_by]
        a = auc(sel(tbr, "608", "own"), sel(tbr, "608", "other"))
        res["bridge"] = {"n": len(d), "frac_le_0.5": round(float(np.mean(np.array(d) <= 0.5)), 4), "max": round(float(max(d)), 2),
                         "608_auc": round(a, 4), "auc_diff": round(a - res["ref"]["608_auc"], 4)}
        res["bridge"]["ok"] = res["bridge"]["frac_le_0.5"] >= 0.99 and abs(res["bridge"]["auc_diff"]) <= 0.002
    # 고르기
    dev_t = load_jsonl(f"{R}/dev_teacher.jsonl")
    res["select"] = {}
    for init in ("H", "X"):
        dev_s = load_jsonl(f"{R}/dev_{init}.jsonl")
        if not (dev_t and dev_s):
            continue
        tk = {key(r): r for r in dev_t}
        diffs, aucs = [], []
        for r in dev_s:
            t = tk.get(key(r))
            if t is None:
                continue
            diffs.append(abs((r.get("raw") or 0.0) - (t.get("raw") or 0.0)))
        for cond in ("clean", "mod", "sev"):
            own = [r.get("raw") or 0.0 for r in dev_s if r["cond"] == cond and r["kind"] == "same"]
            oth = [r.get("raw") or 0.0 for r in dev_s if r["cond"] == cond and r["kind"] == "diff"]
            aucs.append(auc(own, oth))
        res["select"][init] = {"mad_raw": round(float(np.mean(diffs)), 4), "n": len(diffs), "auc_mean_clean_mod_sev": round(float(np.mean(aucs)), 4)}
    if len(res["select"]) == 2:
        h, x = res["select"]["H"], res["select"]["X"]
        if h["mad_raw"] != x["mad_raw"]:
            res["selected"] = "H" if h["mad_raw"] < x["mad_raw"] else "X"
        else:
            res["selected"] = "H" if h["auc_mean_clean_mod_sev"] >= x["auc_mean_clean_mod_sev"] else "X"
    # 학생별 기준
    res["students"] = {}
    for init in ("H", "X"):
        s = {}
        for var, fn in (("w8", f"e1_{init}.jsonl"), ("fp32", f"e1_{init}_fp32.jsonl"), ("dyn8", f"e1_{init}_dyn8.jsonl")):
            rows = load_jsonl(f"{R}/{fn}")
            if not rows:
                continue
            er = e1_rows(rows, "raw")
            a608 = auc(sel(er, "608", "own"), sel(er, "608", "other"))
            tau, q, got = matched_tau(er, ref)
            wp538 = float(np.mean(np.array(sel(er, "538", "other")) >= tau))
            wp608 = float(np.mean(np.array(sel(er, "608", "other")) >= tau))
            v = {"608_auc": round(a608, 4), "C1_pass": a608 >= TEACHER_AUC608 - DROP,
                 "auc_diff_vs_ref": round(a608 - res["ref"]["608_auc"], 4),
                 "tau": round(tau, 2), "q": round(q, 4), "own_fail_at_tau": round(got, 4),
                 "538_wp_tau": round(wp538, 4), "C2_pass": wp538 <= WP_MAX, "608_wp_tau": round(wp608, 4),
                 "538_auc": round(auc(sel(er, "538", "own"), sel(er, "538", "other")), 4),
                 "failed_rows": int(sum(r["failed"] for r in er))}
            if var == "w8":
                v["auc_diff_ci"] = [round(x, 4) for x in boot_auc_diff(er, ref)]
                for hh in (0, 1):
                    o = [r["v"] for r in er if r["set"] == "608" and r["label"] == "own" and half(r["spk"]) == hh]
                    n = [r["v"] for r in er if r["set"] == "608" and r["label"] == "other" and half(r["spk"]) == hh]
                    ro = [r["v"] for r in ref if r["set"] == "608" and r["label"] == "own" and half(r["spk"]) == hh]
                    rn = [r["v"] for r in ref if r["set"] == "608" and r["label"] == "other" and half(r["spk"]) == hh]
                    v[f"608_auc_half{hh}"] = [round(auc(o, n), 4), round(auc(ro, rn), 4)]
                # 학생 표시 점수(보고만)
                dev_s = load_jsonl(f"{R}/dev_{init}.jsonl")
                if dev_t and dev_s:
                    import dgop
                    cal = calib_from_dev(dev_t, dev_s)
                    disp = [dict(r, d=dgop.calibrate_score(r["v"], cal)) for r in er]
                    dd = [abs(r["d"] - ref_by[(r["set"], r["clip"], r["target"], r["label"])]["v"]) for r in disp
                          if (r["set"], r["clip"], r["target"], r["label"]) in ref_by]
                    v["display"] = {"anchors": cal["anchors"], "mean_absdiff_vs_teacher": round(float(np.mean(dd)), 2),
                                    "p95_absdiff": round(float(np.percentile(dd, 95)), 2),
                                    "own_fail65": round(float(np.mean([r["d"] < PASS for r in disp if r["label"] == "own"])), 4),
                                    "608_own_fail65": round(float(np.mean([r["d"] < PASS for r in disp if r["set"] == "608" and r["label"] == "own"])), 4),
                                    "538_wp65": round(float(np.mean([r["d"] >= PASS for r in disp if r["set"] == "538" and r["label"] == "other"])), 4),
                                    "608_wp65": round(float(np.mean([r["d"] >= PASS for r in disp if r["set"] == "608" and r["label"] == "other"])), 4)}
            s[var] = v
        # fp32 대 int8 원점수 차
        w8r, fpr = load_jsonl(f"{R}/e1_{init}.jsonl"), load_jsonl(f"{R}/e1_{init}_fp32.jsonl")
        if w8r and fpr:
            fk = {key(r): r.get("raw") for r in fpr}
            dd = [abs((r.get("raw") or 0) - (fk[key(r)] or 0)) for r in w8r if key(r) in fk]
            s["w8_vs_fp32_raw"] = {"mean": round(float(np.mean(dd)), 3), "p95": round(float(np.percentile(dd, 95)), 3), "max": round(float(max(dd)), 2)}
        s["C3"] = cons_decisions(f"{R}/e2_{init}.json")
        ex = json.load(open(f"{R}/export_{init}.json")) if os.path.exists(f"{R}/export_{init}.json") else None
        if ex:
            s["size"] = ex["sizes"]
            s["C4_pass"] = ex["sizes"]["w8"] <= SIZE_MAX
            s["params"] = ex.get("params")
        lat = {}
        for t in (1, 2, 4):
            for var in ("w8", "dyn8"):
                p = f"{R}/lat_{init}_{var}_t{t}.json"
                if os.path.exists(p):
                    L = json.load(open(p))
                    lat[f"{var}_t{t}"] = {"median": round(L["median"], 3), "p95": round(L["p95"], 3), "max": round(L["max"], 3),
                                          "fwd_median": round(L["fwd_median"], 3) if L.get("fwd_median") else None, "cpu": L["cpu"]}
        s["latency"] = lat
        if "w8_t2" in lat:
            s["C5_pass"] = lat["w8_t2"]["p95"] <= LAT_MAX
        tr = f"{R}/train_{init}.json"
        if os.path.exists(tr):
            s["train"] = json.load(open(tr))
        if "w8" in s:
            s["all_pass"] = bool(s["w8"]["C1_pass"] and s["w8"]["C2_pass"] and (s["C3"] or {}).get("pass") and s.get("C4_pass")
                                 and s.get("C5_pass"))
        res["students"][init] = s
    res["teacher_C3"] = cons_decisions(f"{R}/e2_teacher.json")
    for t in (1, 2, 4):
        p = f"{R}/lat_teacher_cpu_t{t}.json"
        if os.path.exists(p):
            L = json.load(open(p))
            res.setdefault("teacher_latency", {})[f"t{t}"] = {"median": round(L["median"], 3), "p95": round(L["p95"], 3), "cpu": L["cpu"]}
    print(json.dumps(res, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    if out_json:
        json.dump(res, open(out_json, "w"), ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    return res


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
