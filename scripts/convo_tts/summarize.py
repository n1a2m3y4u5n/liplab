"""측정 결과 → 사전 기준 판정(docs/listen-convo-tts-2026-10.md 6절). 파드와 맥 어디서나 돈다(표준 라이브러리만).

    python summarize.py WORK      → WORK/summary.json, 표준 출력에 요약"""
import json
import os
import statistics as st
import sys
from collections import Counter

W = sys.argv[1]


def load(p, default=None):
    try:
        return json.load(open(os.path.join(W, p), encoding="utf-8"))
    except (OSError, ValueError):
        return default


def jl(p):
    out = []
    try:
        for line in open(os.path.join(W, p), encoding="utf-8"):
            if line.strip():
                out.append(json.loads(line))
    except OSError:
        pass
    return out


def pct(v, q):
    v = sorted(v)
    if not v:
        return None
    k = (len(v) - 1) * q / 100
    lo, hi = int(k), min(int(k) + 1, len(v) - 1)
    return round(v[lo] + (v[hi] - v[lo]) * (k - lo), 3)


m1 = load("measure_server1.json", {}) or {}
m2 = load("measure_server2.json", {}) or {}
ph = m1.get("phases") or {}
out = {"criteria": {}, "report": {}}
C = out["criteria"]
R = out["report"]

# M1
peak1 = max([r[3] for r in m1.get("timeline") or [] if r[3] is not None] or [0])
peak2 = max([r[3] for r in m2.get("timeline") or [] if r[3] is not None] or [0])
C["M1"] = {"value_gib": round(peak1, 3), "limit": 3.3, "pass": 0 < peak1 <= 3.3}
by_phase = {}
for t, name, rss, hwm in m1.get("timeline") or []:
    if rss is not None:
        b = by_phase.setdefault(name, [0, 0])
        b[0] = max(b[0], rss)
        b[1] = max(b[1], hwm or 0)
R["server1_max_rss_by_phase_gib"] = {k: round(v[0], 3) for k, v in by_phase.items()}
R["server1_hwm_end_of_phase_gib"] = {k: (v.get("mem_end") or {}).get("VmHWM") for k, v in ph.items()}
R["server2_peak_vmhwm_gib"] = round(peak2, 3)
R["server2_phases"] = {k: {kk: vv for kk, vv in v.items() if kk in ("rows", "mem_end")} for k, v in (m2.get("phases") or {}).items()}

# L1·L2
p3 = (ph.get("P3_seq") or {}).get("rows") or []
p3s = [r["s"] for r in p3]
med = round(st.median(p3s), 3) if p3s else None
C["L1"] = {"median_s": med, "max_s": max(p3s) if p3s else None, "p90_s": pct(p3s, 90), "n": len(p3s),
           "status": dict(Counter(r["status"] for r in p3)), "pass": bool(p3s) and med <= 2.5 and max(p3s) <= 5.0}
p2 = ((ph.get("P2_first") or {}).get("rows") or [{}])[0]
C["L2"] = {"first_s": p2.get("s"), "status": p2.get("status"), "pass": p2.get("s") is not None and p2["s"] <= 6.0}
R["audio_ms_p3"] = [r.get("ms") for r in p3]
R["fly_estimate_x1.4"] = {"median_s": None if med is None else round(med * 1.4, 2), "max_s": None if not p3s else round(max(p3s) * 1.4, 2)}

# C1·C2
p4 = ph.get("P4_conc") or {}
allp4 = (p4.get("two") or []) + (p4.get("three") or []) + (p4.get("mixed") or [])
C["C1"] = {"status": dict(Counter(r["status"] for r in allp4)), "n": len(allp4),
           "pass": bool(allp4) and all(r["status"] == 200 for r in allp4)}
three = p4.get("three") or []
lim2 = None if med is None else round(3 * med + 1.0, 3)
last3 = max([r["s"] for r in three] or [None]) if three else None
C["C2"] = {"last_of_three_s": last3, "limit_s": lim2, "rows": [[r["s"], r["status"]] for r in three],
           "pass": bool(three) and lim2 is not None and last3 <= lim2}
R["P4"] = {k: [[r.get("kind", "sound"), r["status"], r["s"]] for r in v] for k, v in p4.items() if isinstance(v, list)}

# C3
p1 = (ph.get("P1_base") or {}).get("rows") or []
a1 = [r["s"] for r in p1 if r.get("kind") == "assess"]
p5 = ph.get("P5_gen") or {}
dur = [r["s"] for r in p5.get("during") or []]
lim3 = None if not (a1 and p3s) else round(st.median(a1) + max(p3s) + 0.5, 3)
C["C3"] = {"during_s": dur, "limit_s": lim3, "status": [r["status"] for r in p5.get("during") or []],
           "pass": bool(dur) and lim3 is not None and max(dur) <= lim3 and all(r["status"] == 200 for r in p5["during"])}
R["P1"] = [[r.get("kind"), r["status"], r["s"], r.get("method"), r.get("score")] for r in p1]
R["P5"] = {"gen_s": p5.get("gen_s"), "finished": p5.get("finished"), "kicks": p5.get("kicks")}

# Q1(서비스에 쓴 클립의 전체 점검)
js = jl("qa_served/judged.orig.jsonl")
tiers = Counter(r["tier"] for r in js)
n = len(js)
C["Q1"] = {"n": n, "tiers": dict(tiers), "pass_rate": round(tiers["pass"] / n, 4) if n else None,
           "fail_rate": round(tiers["fail"] / n, 4) if n else None,
           "pass": n > 0 and tiers["pass"] / n >= 0.90 and tiers["fail"] / n <= 0.02}
R["Q1_flags"] = dict(Counter(f for r in js for f in r.get("flags") or []))
R["Q1_nonpass"] = [{"voice": r["voice"], "key": r["key"], "hyp": r.get("hyp"), "per": r.get("per"), "dgop": r.get("dgop"),
                    "tier": r["tier"], "flags": r.get("flags")} for r in js if r["tier"] != "pass"]
R["Q1_per0_rate"] = round(sum(1 for r in js if r.get("per") == 0) / n, 4) if n else None
R["Q1_dgop_mean"] = round(st.mean([r["dgop"] for r in js if r.get("dgop") is not None]), 2) if n else None

# Q2(게이트 통과율)
tg = jl("qa_served/targets.jsonl")
tr = jl("qa_rejected/targets.jsonl")
ns, nr = len(tg), len(tr)
C["Q2"] = {"served": ns, "rejected": nr, "rate": round(ns / (ns + nr), 4) if ns + nr else None,
           "pass": (ns + nr) > 0 and ns / (ns + nr) >= 0.85}
R["Q2_cand"] = dict(Counter((t.get("gate") or {}).get("cand") for t in tg))
R["Q2_reject_flags"] = dict(Counter(f for t in tr for f in ((t.get("gate") or {}).get("flags") or [])))
jr = jl("qa_rejected/judged.orig.jsonl")
# 떨어진 클립의 전체 점검 등급(음절 시각 항목은 빼고 본다: 서버가 시각을 주지 않았으므로)
def tier_wo_syl(r):
    fl = [f for f in r.get("flags") or [] if ":syl_" not in f]
    t = "pass"
    for f in fl:
        k = f.split(":")[0]
        if k == "fail" or (k == "suspect" and t == "pass"):
            t = k
    return t
R["Q2_rejected_fullqa"] = dict(Counter(tier_wo_syl(r) for r in jr))
gate_vs = Counter()
for r in js:
    gate_vs[("gate_pass", r["tier"])] += 1
for r in jr:
    gate_vs[("gate_fail", tier_wo_syl(r))] += 1
R["gate_vs_fullqa"] = {f"{a}|{b}": v for (a, b), v in gate_vs.items()}

# Q3(문항 채택)
ci = load("cache_server1/convo_items.json", {}) or {}
items = (ci.get("items") or {})
stt = Counter(v.get("status") for v in items.values())
nf = 24
C["Q3"] = {"ready": stt["ready"], "rejected": stt["rejected"], "total_fixture": nf, "rate": round(stt["ready"] / nf, 4),
           "pass": stt["ready"] / nf >= 0.80}
R["Q3_avoid"] = dict(Counter(",".join(v.get("avoid_voices") or []) or "-" for v in items.values()))
R["Q3_build_s"] = sorted(v.get("build_s") for v in items.values() if v.get("build_s") is not None)
syn = [s for v in items.values() for s in (v.get("synth_s") or [])]
R["Q3_clip_synth_s"] = {"n": len(syn), "median": round(st.median(syn), 3) if syn else None, "p90": pct(syn, 90), "max": max(syn) if syn else None}
R["P6"] = (ph.get("P6_end") or {}).get("after"), (ph.get("P6_end") or {}).get("stage5")
R["P0"] = {k: (ph.get("P0_warmup") or {}).get(k) for k in ("http_s", "total_s", "loaded", "warm_ok", "mem_end")}

out["verdict"] = "통과" if all(v.get("pass") for v in C.values()) else "미달"
json.dump(out, open(os.path.join(W, "summary.json"), "w"), ensure_ascii=False, indent=1)
print("VERDICT", out["verdict"])
for k, v in C.items():
    print(k, "PASS" if v.get("pass") else "FAIL", json.dumps({kk: vv for kk, vv in v.items() if kk != "pass"}, ensure_ascii=False)[:300])
print("REPORT", json.dumps({k: R[k] for k in ("server2_peak_vmhwm_gib", "Q2_cand", "Q2_rejected_fullqa", "gate_vs_fullqa", "Q3_avoid",
                                              "Q3_clip_synth_s", "fly_estimate_x1.4", "P0")}, ensure_ascii=False)[:2000])
