"""문장 끝 모음 결함 판정(맥, docs/dgop-final-vowel-2026-10.md 4~6절의 계산을 그대로). 결과를 보기 전에 커밋한다.

    python analyze.py RUN_DIR [--half 0|1|all] [--json OUT.json]

RUN_DIR: 파드 결과(main.jsonl, tts.jsonl, hyp.jsonl, zeroth.jsonl). --half는 538·608의 화자 절반(서버 음성은 절반이 없어 늘 전체).
"""
import argparse
import glob
import json
import os
import statistics
import sys

import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("run")
ap.add_argument("--half", default="all")
ap.add_argument("--json", default="")
a = ap.parse_args()

PASS = 65.0
RATE_P10 = 4.08            # speak_cues.RATE_P10
TTS_TAIL = 0.150           # 서버 음성은 무손실 원본에서 말소리 끝 뒤 150 ms를 남겼다(docs/sound-qa-2026-10.md 5절)
LATE_S = 0.100             # 시각 기준: 끝 모음 시작이 말소리 끝 + 100 ms 이내
MARGINS = (0, 50, 150)


def rows(name):
    out = []
    for f in sorted(glob.glob(os.path.join(a.run, f"{name}*.jsonl"))):
        out += [json.loads(l) for l in open(f) if l.strip()]
    return out


def final_idx(ph):
    for i in range(len(ph) - 1, -1, -1):
        if ph[i][0].startswith("n:"):
            return i
    return None


def weak(ph, k=3, skip=None):
    """main._weak_phones와 같은 규칙(음소 [토큰, t0, t1, naive, silent_h]). skip 위치는 후보에서 뺀다(방법 M4)."""
    cand = [(i, p) for i, p in enumerate(ph) if p[0] != "|" and not p[4] and i != skip]
    if not cand:
        return []
    m = sum(p[3] for _, p in cand) / len(cand)
    out = []
    for i, p in sorted(cand, key=lambda x: x[1][3]):
        if p[3] < max(0.05, 0.6 * m):
            out.append(i)
        if len(out) >= k:
            break
    return out


def score_excl(ph, skip, cal):
    sc = [p[3] for i, p in enumerate(ph) if p[0] != "|" and i != skip]
    return calibrate(100.0 * sum(sc) / len(sc), cal) if sc else None


_cal = None


def calibrate(raw, cal):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend"))
    import dgop
    return dgop.calibrate_score(raw, cal)


def load_cal():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend", "data", "dgop_calibration_ours.json")
    return json.load(open(p))


def auc(pos, neg):
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    if not len(pos) or not len(neg):
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
        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1
        i = j + 1
    return float((ranks[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


METHODS = {"M0": ("R", "T"), "M1": ("Rp", "Tp"), "M3": ("R_con50", "T_con50"), "M4": ("R", "T")}
for m in MARGINS:
    METHODS[f"M2_{m}"] = (f"R_trim{m}", f"T_trim{m}")


def main_stats(main, cal):
    by = {}
    for r in main:
        if r.get("err") or (a.half != "all" and str(r["half"]) != a.half):
            continue
        by.setdefault((r["set"], r["variant"]), []).append(r)
    res = {}
    for meth, (vr, vt) in METHODS.items():
        for cond, v in (("R", vr), ("T", vt)):
            for st in ("538", "608"):
                L = by.get((st, v), [])
                if not L:
                    continue
                same, diff, late, fin_w, nuc_w, nuc_n, rates, slow, fin_nv = [], [], [], 0, 0, 0, {}, 0, []
                for r in L:
                    own = r["targets"][0]
                    ph = own["phones"]
                    fi = final_idx(ph)
                    skip = fi if meth == "M4" else None
                    s = score_excl(ph, fi, cal) if meth == "M4" else own["score"]
                    same.append(s)
                    for t in r["targets"][1:]:
                        diff.append(score_excl(t["phones"], final_idx(t["phones"]), cal) if meth == "M4" else t["score"])
                    se = r.get("speech_end_raw")
                    if se is not None and fi is not None:
                        late.append(ph[fi][1] - se)
                    w = weak(ph, skip=skip)
                    fin_w += (fi in w) if meth != "M4" else 0
                    nuc = [i for i, p in enumerate(ph) if p[0].startswith("n:") and i != fi]
                    nuc_n += len(nuc)
                    nuc_w += sum(1 for i in nuc if i in w)
                    if fi is not None:
                        fin_nv.append(ph[fi][3])
                    rp = own.get("rate") or {}
                    if rp.get("rate") is not None:
                        rates[r["clip"]] = rp["rate"]
                        slow += rp["rate"] < RATE_P10
                late = np.asarray(late)
                res[(meth, cond, st)] = {
                    "n": len(L), "auc": auc(same, diff),
                    "fail65": float(np.mean([x < PASS for x in same])), "pass65_diff": float(np.mean([x >= PASS for x in diff])),
                    "same_median": float(np.median(same)),
                    "late_frac": float(np.mean(late > LATE_S)) if len(late) else None,
                    "late_p95": float(np.percentile(late, 95)) if len(late) else None,
                    "late_median": float(np.median(late)) if len(late) else None,
                    "final_weak_rate": fin_w / len(L), "nuc_weak_rate": nuc_w / max(1, nuc_n),
                    "final_naive_median": float(np.median(fin_nv)) if fin_nv else None,
                    "slow_rate": slow / max(1, len(rates)), "rates": rates}
    # 빠르기 비: 같은 방법의 T 대 R, 그리고 M0 R 대비
    for meth in METHODS:
        for st in ("538", "608"):
            kr, kt, k0 = (meth, "R", st), (meth, "T", st), ("M0", "R", st)
            if kr in res and kt in res and k0 in res:
                rr, rt, r0 = res[kr]["rates"], res[kt]["rates"], res[k0]["rates"]
                ks = sorted(set(rr) & set(rt))
                res[kt]["rate_ratio_T_over_R"] = float(np.median([rt[k] / rr[k] for k in ks])) if ks else None
                ks0 = sorted(set(rt) & set(r0))
                res[kt]["rate_ratio_T_over_M0R"] = float(np.median([rt[k] / r0[k] for k in ks0])) if ks0 else None
                ks1 = sorted(set(rr) & set(r0))
                res[kr]["rate_ratio_R_over_M0R"] = float(np.median([rr[k] / r0[k] for k in ks1])) if ks1 else None
    for v in res.values():
        v.pop("rates", None)
    return res


def tts_stats(tts):
    by = {}
    for r in tts:
        if not r.get("err"):
            by.setdefault(r["variant"], []).append(r)
    out = {}
    for v, L in by.items():
        late, sc, yo_late = [], [], []
        for r in L:
            ph = r["phones"]
            fi = final_idx(ph)
            ref = r["dur_raw"] - TTS_TAIL
            d = ph[fi][1] - ref
            late.append(d)
            sc.append(r["score"])
            if ph[-1][0] == "n:ㅛ":
                yo_late.append(d)
        late = np.asarray(late)
        out[v] = {"n": len(L), "late_frac": float(np.mean(late > LATE_S)), "late_p95": float(np.percentile(late, 95)),
                  "late_median": float(np.median(late)), "yo_late_frac": float(np.mean(np.asarray(yo_late) > LATE_S)) if yo_late else None,
                  "score_mean": float(np.mean(sc))}
    return out


def hyp_stats(hyp):
    out = {}
    for r in hyp:
        if r.get("err"):
            continue
        k = (r["model"], r["variant"], "yo" if r["last_tok"] in ("n:ㅛ", "요") else "other")
        d = out.setdefault(k, {"n": 0, "last_frame": 0, "late": 0, "pmax_in": [], "pmax_after": []})
        d["n"] += 1
        fr = r.get("last_frames") or []
        d["last_frame"] += bool(fr) and fr[-1] >= r["n_frames"] - 2
        se = r.get("speech_end") or r["dur_raw"]
        d["late"] += r["final_t0"] > se + LATE_S
        d["pmax_in"].append(r.get("pmax_in_speech", 0.0))
        d["pmax_after"].append(r.get("pmax_after", 0.0))
    for d in out.values():
        d["last_frame_frac"] = d["last_frame"] / d["n"]
        d["late_frac"] = d["late"] / d["n"]
        d["pmax_in_gt05"] = float(np.mean(np.asarray(d.pop("pmax_in")) > 0.5))
        d["pmax_after_gt05"] = float(np.mean(np.asarray(d.pop("pmax_after")) > 0.5))
    return {"|".join(k): v for k, v in out.items()}


def zeroth_stats(z):
    out = {}
    for r in z:
        if r.get("err") or "R" not in r:
            continue
        for v in ("R", "T"):
            k = (r["split"], v)
            d = out.setdefault(k, {"n": 0, "tail": [], "last_frame": 0, "late": 0, "last_char": {}})
            d["n"] += 1
            se = r["speech_end"] or r["dur"]
            if v == "R":
                d["tail"].append(r["dur"] - se)
            fr = r[v]["last_frames"]
            d["last_frame"] += bool(fr) and fr[-1] >= r[v]["n_frames"] - 2
            d["late"] += r[v]["final_t0"] > se + LATE_S
            d["last_char"][r["last_char"]] = d["last_char"].get(r["last_char"], 0) + 1
    for d in out.values():
        t = d.pop("tail")
        if t:
            d["tail_median"], d["tail_p10"], d["tail_p90"] = (float(np.median(t)), float(np.percentile(t, 10)),
                                                              float(np.percentile(t, 90)))
        d["last_frame_frac"] = d["last_frame"] / d["n"]
        d["late_frac"] = d["late"] / d["n"]
        d["last_char"] = dict(sorted(d["last_char"].items(), key=lambda x: -x[1])[:6])
    return {"|".join(k): v for k, v in out.items()}


cal = load_cal()
R = {"half": a.half, "main": {"|".join(k): v for k, v in main_stats(rows("main"), cal).items()},
     "tts": tts_stats(rows("tts")), "hyp": hyp_stats(rows("hyp")), "zeroth": zeroth_stats(rows("zeroth"))}
if a.json:
    json.dump(R, open(a.json, "w"), ensure_ascii=False, indent=1)
for k, v in sorted(R["main"].items()):
    print(k, {kk: (round(vv, 4) if isinstance(vv, float) else vv) for kk, vv in v.items()})
for sec in ("tts", "hyp", "zeroth"):
    for k, v in sorted(R[sec].items()):
        print(sec, k, {kk: (round(vv, 4) if isinstance(vv, float) else vv) for kk, vv in v.items()})
