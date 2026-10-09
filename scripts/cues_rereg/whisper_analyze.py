"""속삭임 거부(조화성 규칙) 재등록 판정, 녹음 없이 판정하는 부분(A). 사전 등록 docs/speak-cues-rereg-2026-10.md 3절.

  python whisper_analyze.py explore RAW.jsonl.gz PARAMS.json          o608·v538 절반 0·합성 시드 0으로 후보 고르기(3.3절)
  python whisper_analyze.py confirm RAW.jsonl.gz PARAMS.json OUT.json n608·v538 절반 1·합성 시드 1로 판정(PARAMS 고정)

설계 R(k 2, θ 0.3, 바닥 10백분위)의 유성 표본 조건에 관문 하나를 더한다: c2 ≥ θ2(두 주기 지연 선명도) 또는 cpp ≥ κ(버퍼 켑스트럼 봉우리).
출력은 집계만.
"""
import gzip, json, math, os, sys
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import speak_loop_port as lp     # noqa: E402

GAINS = ("-12", "-6", "6")
R = {"k": 2.0, "theta": 0.3, "pct": 10.0}
GRID = [None] + [("c2", t) for t in (0.3, 0.4, 0.5, 0.6, 0.7)] + [("cpp", t) for t in (12.0, 14.0, 16.0, 18.0)]
WH_SEL = ("whisper_w1", "whisper_w3", "breath")       # C2 판정 대상(W2·기식 유성은 보고만)


def load(path):
    return [r for r in (json.loads(l) for l in gzip.open(path, "rt", encoding="utf-8")) if "error" not in r]


def trace_of(r, g):
    return [{"t": t, "rms": rms, "hz": hz, "clarity": c1, "c2": c2, "cpp": cp} for t, rms, hz, c1, c2, cp in r["s10"][g]["trace"]]


def flags(tr, gate):
    F = lp.floor_rms(tr, R["pct"])
    out = []
    for p in tr:
        v = p["rms"] >= R["k"] * F and p["hz"] > 0 and p["clarity"] >= R["theta"]
        if v and gate is not None:
            x = p[gate[0]]
            v = x is not None and x >= gate[1]
        out.append(bool(v))
    return out


def design(tr, gate):
    F = lp.floor_rms(tr, R["pct"])
    fl = flags(tr, gate)
    dv = lp.longest_run([p["t"] for p in tr], fl)
    vr = [p["rms"] for p, f in zip(tr, fl) if f]
    L = 20 * math.log10(float(np.median(vr))) if vr else None
    snr = (L - 20 * math.log10(F)) if L is not None else None
    return {"L": L, "dv": dv, "stage0": bool(dv >= 1.2 and snr is not None and snr >= 12.0), "long": dv >= 2.0}


def mean(v):
    return round(float(np.mean(v)), 4) if len(v) else None


def c1(rows, gate):
    res = {id(r): {g: design(trace_of(r, g), gate) for g in ("0",) + GAINS} for r in rows}
    base = defaultdict(list)
    for r in rows:
        for g, x in res[id(r)].items():
            if x["L"] is not None and x["dv"] >= 0.3:
                base[(r["spk"], g)].append(x["L"])
    B = {k: float(np.median(v)) for k, v in base.items()}

    def judg(r, g):
        x = res[id(r)][g]
        jb = lp.judge_with_baseline(x, B.get((r["spk"], g)))
        return (x["stage0"], jb["loud"], jb["soft"])

    same = tot = 0
    for r in rows:
        j0 = judg(r, "0")
        for g in GAINS:
            for a, b in zip(j0, judg(r, g)):
                same += a == b
                tot += 1
    return {"n_clips": len(rows), "n_spk": len({r["spk"] for r in rows}), "rate": round(same / tot, 4) if tot else None,
            "stage0_pass_0dB": mean([res[id(r)]["0"]["stage0"] for r in rows])}


def c3(rows, gate):
    tot = hit = 0
    per = defaultdict(lambda: [0, 0])
    for r in rows:
        tr = trace_of(r, "0")
        for n, v in zip(lp.nucleus_flags(tr), flags(tr, gate)):
            if n:
                tot += 1
                hit += v
                per[r["spk"]][0] += v
                per[r["spk"]][1] += 1
    spk = sorted(a / b for a, b in per.values() if b)
    return {"n_samples": tot, "rate": round(hit / tot, 4) if tot else None, "n_spk": len(spk),
            "spk_median": round(float(np.median(spk)), 4) if spk else None, "spk_min": round(spk[0], 4) if spk else None,
            "spk_below_0.8": sum(1 for s in spk if s < 0.8)}


def c2(syn, gate):
    out = {}
    for kind in sorted({r["kind"] for r in syn}):
        rs = [r for r in syn if r["kind"] == kind]
        d = [design(trace_of(r, "0"), gate) for r in rs]
        out[kind] = {"n": len(rs), "stage0": mean([x["stage0"] for x in d]), "long": mean([x["long"] for x in d]),
                     "cur_stage0": mean([r["s10"]["0"]["cur"]["stage0"] for r in rs])}
    out["max_selected"] = max(out[k]["stage0"] for k in WH_SEL)
    return out


def evaluate(rows, phase, gate):
    if phase == "explore":
        s608 = [r for r in rows if r["set"] == "o608"]
        s538 = [r for r in rows if r["set"] == "v538" and r["half"] == 0]
        syn = [r for r in rows if r["set"] == "syn" and r["seed"] == 0]
    else:
        s608 = [r for r in rows if r["set"] == "n608"]
        s538 = [r for r in rows if r["set"] == "v538" and r["half"] == 1]
        syn = [r for r in rows if r["set"] == "syn" and r["seed"] == 1]
    e = {"gate": gate, "C1_538": c1(s538, gate), "C1_608": c1(s608, gate), "C2": c2(syn, gate),
         "C3_608": c3(s608, gate), "C3_538_report": c3(s538, gate)}
    e["pass"] = {"C1_538": (e["C1_538"]["rate"] or 0) >= 0.95, "C1_608": (e["C1_608"]["rate"] or 0) >= 0.95,
                 "C2": all(e["C2"][k]["stage0"] <= 0.05 for k in WH_SEL),
                 "C3": (e["C3_608"]["rate"] or 0) >= 0.80, "C4": e["C2"]["voiced"]["stage0"] >= 0.95}
    e["all_pass"] = all(e["pass"].values())
    return e


def brief(e):
    return {"gate": e["gate"], "C1_538": e["C1_538"]["rate"], "C1_608": e["C1_608"]["rate"],
            "C2": {k: e["C2"][k]["stage0"] for k in e["C2"] if k != "max_selected"}, "C3_608": e["C3_608"]["rate"],
            "C3_538": e["C3_538_report"]["rate"], "pass": e["pass"]}


def main():
    cmd = sys.argv[1]
    rows = load(sys.argv[2])
    if cmd == "explore":
        ev = [evaluate(rows, "explore", g) for g in GRID]
        # 3.3절 규칙: C1 두 개 ≥ 0.95, C3 ≥ 0.85(여유), C4 ≥ 0.95를 지키는 후보 가운데 C2 최댓값(W1·W3·숨소리)이 가장 작은 것,
        # 같으면 C3가 높은 것. 그런 후보가 없으면 실패로 적고 C3 ≥ 0.80만 지키는 후보로 같은 규칙(기록용).
        def keep(e, c3min):
            return e["pass"]["C1_538"] and e["pass"]["C1_608"] and e["pass"]["C4"] and (e["C3_608"]["rate"] or 0) >= c3min
        cand = [e for e in ev if e["gate"] is not None and keep(e, 0.85)]
        why = "C1·C4와 C3 ≥ 0.85를 지키는 후보 가운데 C2 최댓값 최소"
        if not cand:
            cand = [e for e in ev if e["gate"] is not None and keep(e, 0.80)]
            why = "C3 ≥ 0.85 후보 없음, C3 ≥ 0.80 후보 가운데(기록용)"
        if not cand:
            cand = [e for e in ev if e["gate"] is not None]
            why = "C1·C3·C4를 지키는 후보 없음, 전체에서(기록용)"
        cand.sort(key=lambda e: (e["C2"]["max_selected"], -(e["C3_608"]["rate"] or 0)))
        ch = cand[0]
        ok_explore = bool(ch["all_pass"] and keep(ch, 0.85))
        out = {"chosen": ch["gate"], "why": why, "explore_pass": ok_explore, "grid": [brief(e) for e in ev], "chosen_detail": ch}
        json.dump(out, open(sys.argv[3], "w"), ensure_ascii=False, indent=1)
        print("WHISPER_EXPLORE_OK", json.dumps({"chosen": ch["gate"], "why": why, "explore_pass": ok_explore}, ensure_ascii=False))
    elif cmd == "confirm":
        prm = json.load(open(sys.argv[3]))
        gate = tuple(prm["chosen"]) if prm["chosen"] else None
        e = evaluate(rows, "confirm", gate)
        ref = evaluate(rows, "confirm", None)
        out = {"gate": gate, "explore_pass": prm["explore_pass"], "confirm": e, "R_without_gate_report": brief(ref),
               "partA_pass": bool(prm["explore_pass"] and e["all_pass"])}
        json.dump(out, open(sys.argv[4], "w"), ensure_ascii=False, indent=1)
        print("WHISPER_CONFIRM_OK", json.dumps({"partA_pass": out["partA_pass"], **brief(e)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
