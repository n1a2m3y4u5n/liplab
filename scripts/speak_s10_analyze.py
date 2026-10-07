"""S10 판정: 크기 기준선(설계 R)과 문장 억양의 608 확인. 사전 등록 docs/speak-loudness-intonation-2026-10.md.

  python3 speak_s10_analyze.py explore RAW.jsonl.gz PARAMS.json     절반 0·합성 시드 0으로 후보 고르기(4.1절)
  python3 speak_s10_analyze.py confirm RAW.jsonl.gz PARAMS.json OUT.json   절반 1·합성 시드 1로 판정(PARAMS 고정)

numpy만 쓴다(맥). 클립별 원자료는 앱 저장소 밖에 두고, 출력 JSON은 집계만 담는다.
"""
import gzip, json, math, re, sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import speak_loop_port as lp     # noqa: E402

GAINS = ("-12", "-6", "6")
R0 = {"k": 2.0, "theta": 0.3, "pct": 10.0}
GRID = [{"k": k, "theta": th, "pct": p} for k in (2.0, 1.41, 1.0) for th in (0.3, 0.2) for p in (10.0, 5.0)]
WH = re.compile(r"(뭐|뭘|무엇|무슨|어디|언제|누구|누가|누굴|왜|어떻게|어떤|어느|몇|얼마)")


def mean(v):
    return round(float(np.mean(v)), 4) if len(v) else None


def load(path):
    rows = []
    for line in gzip.open(path, "rt", encoding="utf-8"):
        r = json.loads(line)
        if "error" not in r:
            rows.append(r)
    return rows


def trace_of(r, g):
    return [{"t": t, "rms": rms, "hz": hz, "clarity": cl} for t, rms, hz, cl in r["s10"][g]["trace"]]


# ── 크기·발성 ──
def r_results(r, prm):
    out = {}
    for g in ("0",) + GAINS:
        out[g] = lp.design_r({"trace": trace_of(r, g)}, prm["k"], prm["theta"], prm["pct"])
    return out


def c1(rows, prm):
    """판정 유지 비율(설계 R, 지금 규칙). 기준선 = 같은 화자·같은 크기 변화에서 Dv ≥ 0.3초인 클립의 L 중앙값."""
    res = {id(r): r_results(r, prm) for r in rows}
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
    same_c = 0
    per = {"stage0": [0, 0], "loud": [0, 0], "soft": [0, 0]}
    for r in rows:
        j0 = judg(r, "0")
        c0 = r["s10"]["0"]["cur"]
        cj0 = (c0["stage0"], c0["loud"], c0["soft"])
        for g in GAINS:
            j = judg(r, g)
            cg = r["s10"][g]["cur"]
            cj = (cg["stage0"], cg["loud"], cg["soft"])
            for n, (a, b) in enumerate(zip(j0, j)):
                same += a == b
                tot += 1
                per[("stage0", "loud", "soft")[n]][0] += a == b
                per[("stage0", "loud", "soft")[n]][1] += 1
            same_c += sum(a == b for a, b in zip(cj0, cj))
    rate0 = {k: round(v[0] / v[1], 4) if v[1] else None for k, v in per.items()}
    pass_rates = {k: mean([judg(r, "0")[i] for r in rows]) for i, k in enumerate(("stage0", "loud", "soft"))}
    return {"n_clips": len(rows), "n_spk": len({r["spk"] for r in rows}), "R": round(same / tot, 4) if tot else None,
            "cur": round(same_c / tot, 4) if tot else None, "R_by_judgment": rate0, "R_pass_rate_0dB": pass_rates}


def c2(rows, prm):
    out = {}
    for kind in ("whisper", "breath", "voiced"):
        rs = [r for r in rows if r["kind"] == kind]
        rr = [r_results(r, prm)["0"] for r in rs]
        out[kind] = {"n": len(rs), "R_stage0": mean([x["stage0"] for x in rr]), "R_long": mean([x["long"] for x in rr]),
                     "cur_stage0": mean([r["s10"]["0"]["cur"]["stage0"] for r in rs]),
                     "cur_long": mean([r["s10"]["0"]["cur"]["long"] for r in rs])}
    wb = [r for r in rows if r["kind"] in ("whisper", "breath")]
    out["whisper_breath_R_stage0"] = mean([r_results(r, prm)["0"]["stage0"] for r in wb])
    out["whisper_breath_cur_stage0"] = mean([r["s10"]["0"]["cur"]["stage0"] for r in wb])
    return out


def c3(rows, prm):
    tot = hit = 0
    per = defaultdict(lambda: [0, 0])
    miss = {"energy": 0, "pitch_range": 0, "clarity": 0}
    for r in rows:
        tr = trace_of(r, "0")
        nf = lp.nucleus_flags(tr)
        F = lp.floor_rms(tr, prm["pct"])
        vf = lp.voiced_flags(tr, prm["k"], prm["theta"], prm["pct"])
        for p, n, v in zip(tr, nf, vf):
            if not n:
                continue
            tot += 1
            hit += v
            per[r["spk"]][0] += v
            per[r["spk"]][1] += 1
            if not v:
                if p["rms"] < prm["k"] * F:
                    miss["energy"] += 1
                elif p["hz"] <= 0:
                    miss["pitch_range"] += 1
                else:
                    miss["clarity"] += 1
    spk = sorted(round(a / b, 3) for a, b in per.values() if b)
    return {"n_samples": tot, "rate": round(hit / tot, 4) if tot else None,
            "spk_median": float(np.median(spk)) if spk else None, "spk_below_0.8": sum(1 for s in spk if s < 0.8),
            "n_spk": len(spk), "miss": miss}


def sets(rows, half):
    s538 = [r for r in rows if r["set"] == "538" and r["half"] == half]
    s28 = [r for r in rows if r["set"] == "608c28" and r["half"] == half]
    s27 = [r for r in rows if r["set"] == "608pair" and r["half"] == half and r["ratio"] >= 0.6 and 0.4 <= r["dur"] <= 6.0]
    syn = [r for r in rows if r["set"] == "syn" and r["seed"] == half]
    return s538, s28, s27, syn


def evaluate(rows, half, prm):
    s538, s28, s27, syn = sets(rows, half)
    # 608 두 층은 화자 키가 달라(이니셜, 이니셜·성별·나이) 겹치지 않게 층 이름을 붙인다
    s608 = [dict(r, spk=f"{r['set']}:{r['spk']}") for r in s28 + s27]
    out = {"params": prm, "half": half,
           "C1_538": c1(s538, prm), "C1_608": c1(s608, prm), "C1_608c28": c1(s28, prm), "C1_608pair": c1(s27, prm),
           "C2": c2(syn, prm),
           "C3_608": c3(s608, prm), "C3_608c28": c3(s28, prm), "C3_608pair": c3(s27, prm), "C3_538_report": c3(s538, prm)}
    def ok(v, t, le=False):
        return v is not None and not (isinstance(v, float) and math.isnan(v)) and (v <= t if le else v >= t)
    out["pass"] = {"C1_538": ok(out["C1_538"]["R"], 0.95), "C1_608": ok(out["C1_608"]["R"], 0.95),
                   "C2": ok(out["C2"]["whisper_breath_R_stage0"], 0.05, le=True), "C3": ok(out["C3_608"]["rate"], 0.80)}
    out["all_pass"] = all(out["pass"].values())
    return out


# ── 억양 ──
def st(a, b):
    return 12 * math.log2(b / a) if a > 0 and b > 0 else 0.0


def med3(ps):
    return [float(np.median(ps[max(0, i - 1): i + 2])) for i in range(len(ps))]


def m0(ps):
    h = ps[: max(1, round(len(ps) * 0.3))]
    t = ps[int(len(ps) * 0.7):]
    return st(np.mean(h), np.mean(t))


def m2(ps, k=3):
    q = med3(ps)
    return st(np.median(q), np.median(q[-k:]))


def auc(pos, neg):
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    if not len(pos) or not len(neg):
        return None
    return float(((pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()) / (len(pos) * len(neg)))


def norm_text(t):
    return re.sub(r"[^가-힣0-9]", "", t)


def pair_rows(rows):
    """한 쌍의 평서·의문이 모두 잡히고 의문이 평서보다 뒤, 각각 0.4~6초, 유사도 0.6 이상. 의문사 의문문은 뺀다."""
    by = defaultdict(list)
    for r in rows:
        if r["set"] == "608pair" and r.get("form") in ("decl", "ques"):
            by[r["file"]].append(r)
    out = []
    for f, rs in by.items():
        rs.sort(key=lambda r: r["si"])
        for a, b in zip(rs, rs[1:]):
            if a["form"] != "decl" or b["form"] != "ques" or b["si"] != a["si"] + 1:
                continue
            if norm_text(a["text"]) != norm_text(b["text"]) or WH.search(b["text"]):
                continue
            if not all(x["ratio"] >= 0.6 and 0.4 <= x["dur"] <= 6.0 for x in (a, b)):
                continue
            if b["start"] <= a["start"]:
                continue
            out.append((a, b))
    return out


def octave_jump_rate(rows):
    n = j = 0
    for r in rows:
        ps = r.get("ps") or []
        for a, b in zip(ps, ps[1:]):
            n += 1
            j += abs(12 * math.log2(b / a)) >= 9
    return round(j / n, 4) if n else None


def intonation(rows, half):
    pairs = [(a, b) for a, b in pair_rows(rows) if half == "all" or a["half"] == half]
    decl = [a for a, _ in pairs if len(a["ps"]) >= 6]
    ques = [b for _, b in pairs if len(b["ps"]) >= 6]
    res = {"half": half, "n_pairs": len(pairs), "n_decl": len(decl), "n_ques": len(ques), "n_spk": len({a["spk"] for a, _ in pairs})}
    for name, f in (("M0", m0), ("M2", m2)):
        vd = [f(r["ps"]) for r in decl]
        vq = [f(r["ps"]) for r in ques]
        res[name] = {"auc": round(auc(vq, vd), 4) if vd and vq else None,
                     "decl_false_rise": round(float(np.mean(np.array(vd) > 1.33)), 4) if vd else None,
                     "ques_rise": round(float(np.mean(np.array(vq) > 1.33)), 4) if vq else None,
                     "decl_fall": round(float(np.mean(np.array(vd) < -1.33)), 4) if vd else None}
        both = [(f(a["ps"]), f(b["ps"])) for a, b in pairs if len(a["ps"]) >= 6 and len(b["ps"]) >= 6]
        res[name]["pair_ques_higher"] = round(float(np.mean([q > d for d, q in both])), 4) if both else None
    return res


def main():
    cmd = sys.argv[1]
    rows = load(sys.argv[2])
    if cmd == "explore":
        ev = [evaluate(rows, 0, prm) for prm in GRID]
        r0 = next(e for e in ev if e["params"] == R0)
        if r0["all_pass"]:
            chosen, why = R0, "R이 탐색 기준을 모두 넘음"
        else:
            ok = [e for e in ev if e["pass"]["C1_538"] and e["pass"]["C1_608"] and e["pass"]["C2"] and e["pass"]["C3"]]
            if ok:
                def dist(p):
                    return sum(p[k] != R0[k] for k in R0)
                ok.sort(key=lambda e: (dist(e["params"]), -(e["C3_608"]["rate"] or 0)))
                chosen, why = ok[0]["params"], "R 미달, 기준을 넘는 후보 가운데 R과 가장 가까운 것"
            else:
                cand = [e for e in ev if e["pass"]["C1_538"] and e["pass"]["C1_608"] and e["pass"]["C2"]] or ev
                cand.sort(key=lambda e: -(e["C3_608"]["rate"] or 0))
                chosen, why = cand[0]["params"], "기준을 모두 넘는 후보 없음, C1·C2를 지키는 후보 가운데 C3 최대(확인은 기록용)"
        brief = [{"params": e["params"], "C1_538": e["C1_538"]["R"], "C1_608": e["C1_608"]["R"],
                  "C2": e["C2"]["whisper_breath_R_stage0"], "C3_608": e["C3_608"]["rate"], "all_pass": e["all_pass"]} for e in ev]
        out = {"chosen": chosen, "why": why, "grid": brief, "R0_detail": r0,
               "chosen_detail": next(e for e in ev if e["params"] == chosen),
               "intonation_half0_descriptive": intonation(rows, 0)}
        json.dump(out, open(sys.argv[3], "w"), ensure_ascii=False, indent=1)
        print("S10_EXPLORE_OK", json.dumps({"chosen": chosen, "why": why}, ensure_ascii=False))
    elif cmd == "confirm":
        prm = json.load(open(sys.argv[3]))["chosen"]
        ev = evaluate(rows, 1, prm)
        it = intonation(rows, 1)
        it["keep"] = bool(it["M2"]["auc"] is not None and it["M2"]["auc"] >= 0.60 and it["M2"]["decl_false_rise"] <= 0.20)
        it["octave_jump_608pair_all"] = octave_jump_rate([r for r in rows if r["set"] == "608pair"])
        it["octave_jump_538_all"] = octave_jump_rate([r for r in rows if r["set"] == "538" and r["text"].endswith((".", "?"))])
        it_all = intonation(rows, "all")
        sex = {}
        for s in ("F", "M"):
            sub = [r for r in rows if r["set"] != "608pair" or r.get("sex") == s]
            sex[s] = intonation(sub, 1)
        out = {"loudness": ev, "intonation_half1": it, "intonation_all_report": it_all, "intonation_half1_by_sex": sex}
        json.dump(out, open(sys.argv[4], "w"), ensure_ascii=False, indent=1)
        print("S10_CONFIRM_OK", json.dumps({"loud_all_pass": ev["all_pass"], "pass": ev["pass"], "inton_keep": it["keep"],
                                            "M2": it["M2"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
