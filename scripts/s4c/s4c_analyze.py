"""S4 청크 주의 학생 판정(docs/scorer-stream-chunk-2026-10.md 5절). 10/7 `scripts/s4_analyze.py`의 함수를 그대로 쓰고,
두 학생 고르기(H·X) 없이 학생 하나(HC, 스트리밍 점수)를 C1~C4와 L1~L3으로 판정한다.

    python scripts/s4c/s4c_analyze.py RESULTS_DIR [요약.json]

RESULTS_DIR: e1_teacher.jsonl(다리 2), e1_HC.jsonl(stream:, 판정), e1_HC_full.jsonl(onnx: 전체 순전파, 보고만), e2_teacher.json,
e2_HC.json(stream:), e2_HC_full.json(보고만), export_HC.json, train_HC.json, stream_latency_HC.json(STREAM_APP 모드, L1~L3).
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import s4_analyze as A  # noqa: E402

L1_MED, L1_P95, L2_FACTOR, L3_P95 = 1.5, 3.0, 1.5, 2.0
SIZE_1007_H = 104.6e6


def e1_block(path, ref):
    rows = A.load_jsonl(path)
    if not rows:
        return None
    er = A.e1_rows(rows, "raw")
    a608 = A.auc(A.sel(er, "608", "own"), A.sel(er, "608", "other"))
    tau, q, got = A.matched_tau(er, ref)
    wp538 = float(np.mean(np.array(A.sel(er, "538", "other")) >= tau))
    return {"608_auc": round(a608, 4), "C1_pass": a608 >= A.TEACHER_AUC608 - A.DROP, "auc_diff_vs_ref": None,
            "tau": round(tau, 2), "q": round(q, 4), "own_fail_at_tau": round(got, 4), "538_wp_tau": round(wp538, 4),
            "C2_pass": wp538 <= A.WP_MAX, "608_wp_tau": round(float(np.mean(np.array(A.sel(er, "608", "other")) >= tau)), 4),
            "538_auc": round(A.auc(A.sel(er, "538", "own"), A.sel(er, "538", "other")), 4),
            "failed_rows": int(sum(r["failed"] for r in er)), "auc_diff_ci": [round(x, 4) for x in A.boot_auc_diff(er, ref)],
            "n_538_other": len(A.sel(er, "538", "other")), "n_608_own": len(A.sel(er, "608", "own"))}


def latency_block(path):
    if not os.path.exists(path):
        return None
    L = json.load(open(path, encoding="utf-8"))
    by = {int(k): v for k, v in L["by_length"].items()}
    l1 = all(v["stream_median"] <= L1_MED and v["stream_p95"] <= L1_P95 for v in by.values())
    l2 = by[30]["stream_median"] <= L2_FACTOR * by[10]["full_median"]
    d = [v["during_p95"] for v in by.values() if v.get("during_p95") is not None]
    l3 = bool(d) and max(d) <= L3_P95
    return {"by_length": by, "L1_pass": l1, "L2_pass": l2, "L2_value": [by[30]["stream_median"], L2_FACTOR * by[10]["full_median"]],
            "L3_pass": l3, "L3_value": max(d) if d else None, "cpu": L.get("cpu"), "chunk": L.get("chunk"), "threads": L.get("threads")}


def main(R, out_json=None):
    ref = A.e1_rows(A.load_jsonl(A.REF), "score")
    ref_by = {(r["set"], r["clip"], r["target"], r["label"]): r for r in ref}
    res = {"ref": {"608_auc": round(A.auc(A.sel(ref, "608", "own"), A.sel(ref, "608", "other")), 4),
                   "own_fail65": round(float(np.mean([r["v"] < A.PASS for r in ref if r["label"] == "own"])), 4)}}
    tb = A.load_jsonl(f"{R}/e1_teacher.jsonl")
    if tb:
        tbr = A.e1_rows(tb, "score")
        d = [abs(r["v"] - ref_by[(r["set"], r["clip"], r["target"], r["label"])]["v"]) for r in tbr
             if (r["set"], r["clip"], r["target"], r["label"]) in ref_by]
        a = A.auc(A.sel(tbr, "608", "own"), A.sel(tbr, "608", "other"))
        res["bridge"] = {"n": len(d), "n_ref": len(ref), "frac_le_0.5": round(float(np.mean(np.array(d) <= 0.5)), 4), "max": round(float(max(d)), 2),
                         "608_auc": round(a, 4), "auc_diff": round(a - res["ref"]["608_auc"], 4)}
        res["bridge"]["ok"] = res["bridge"]["frac_le_0.5"] >= 0.99 and abs(res["bridge"]["auc_diff"]) <= 0.002 and len(d) >= 0.99 * len(ref)
    s = {"stream": e1_block(f"{R}/e1_HC.jsonl", ref), "full_report_only": e1_block(f"{R}/e1_HC_full.jsonl", ref)}
    for k in ("stream", "full_report_only"):
        if s[k]:
            s[k]["auc_diff_vs_ref"] = round(s[k]["608_auc"] - res["ref"]["608_auc"], 4)
    s["C3"] = A.cons_decisions(f"{R}/e2_HC.json")
    s["C3_full_report_only"] = A.cons_decisions(f"{R}/e2_HC_full.json")
    ex = json.load(open(f"{R}/export_HC.json")) if os.path.exists(f"{R}/export_HC.json") else None
    if ex:
        s["size"] = ex["sizes"]
        s["C4_pass"] = ex["sizes"]["w8"] <= A.SIZE_MAX
        s["bridge1_size_ratio"] = round(ex["sizes"]["w8"] / SIZE_1007_H, 5)
        s["bridge1_ok"] = abs(s["bridge1_size_ratio"] - 1) <= 0.01
    s["latency"] = latency_block(f"{R}/stream_latency_HC.json")
    if os.path.exists(f"{R}/train_HC.json"):
        s["train"] = json.load(open(f"{R}/train_HC.json"))
    st = s["stream"] or {}
    lat = s["latency"] or {}
    crit = {"C1": st.get("C1_pass"), "C2": st.get("C2_pass"), "C3": (s["C3"] or {}).get("pass"), "C4": s.get("C4_pass"),
            "L1": lat.get("L1_pass"), "L2": lat.get("L2_pass"), "L3": lat.get("L3_pass")}
    valid = bool(res.get("bridge", {}).get("ok")) and bool(s.get("bridge1_ok"))
    s["criteria"] = crit
    s["verdict"] = "HOLD" if not valid else ("PASS" if all(bool(v) for v in crit.values()) else "FAIL")
    res["HC"] = s
    res["teacher_C3"] = A.cons_decisions(f"{R}/e2_teacher.json")
    print(json.dumps(res, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    if out_json:
        json.dump(res, open(out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1,
                  default=lambda o: o.item() if hasattr(o, "item") else str(o))
    return res


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
