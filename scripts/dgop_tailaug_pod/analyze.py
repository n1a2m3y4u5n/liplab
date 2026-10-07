"""끝 무음 증강 재학습 판정(맥, docs/dgop-aligner-tailaug-2026-10.md 5~6절의 계산을 그대로). 결과를 보기 전에 커밋한다.

    python analyze.py RUN_OUT [--half 0|1|all] [--json OUT.json]

RUN_OUT: 파드 결과 폴더(main.*.jsonl, tts.*.jsonl, hyp.*.jsonl, zeroth.0.jsonl, mfa.jsonl, latency_*.json).
--half는 538·608의 화자 절반(서버 음성은 절반이 없어 늘 전체). 기준선 K0_t는 지금 앱(지금 정렬기·채점기 + 끝 자르기)이다.
"""
import argparse
import glob
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(APP, "backend"))
sys.path.insert(0, os.path.join(APP, "scripts", "sound_pod"))
os.environ.setdefault("LIPLAB_BACKEND", os.path.join(APP, "backend"))

ap = argparse.ArgumentParser()
ap.add_argument("run")
ap.add_argument("--half", default="all")
ap.add_argument("--json", default="")
a = ap.parse_args()

PASS = 65.0
RATE_P10 = 4.08            # speak_cues.RATE_P10
TTS_TAIL = 0.150           # 서버 음성은 말소리 끝 뒤 150 ms를 남겼다(docs/sound-qa-2026-10.md 5절)
LATE_S = 0.100             # 무음에 놓임: 끝 모음 시작 − 말소리 끝 > 100 ms
BASE = ("K0", "t")         # 지금 앱
CANDS = [("A", "n"), ("A", "t"), ("B", "n"), ("B", "t")]


def rows(pat):
    out = []
    for f in sorted(glob.glob(os.path.join(a.run, pat))):
        out += [json.loads(l) for l in open(f, encoding="utf-8") if l.strip()]
    return out


def final_idx(ph):
    for i in range(len(ph) - 1, -1, -1):
        if ph[i][0].startswith("n:"):
            return i
    return None


def weak(ph, k=3):
    """main._weak_phones와 같은 규칙(음소 [토큰, t0, t1, naive, silent_h])."""
    cand = [(i, p) for i, p in enumerate(ph) if p[0] != "|" and not p[4]]
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


def split_variant(v):
    pair, tr, cond = v.split("_")
    return pair, tr, cond


def in_half(r):
    return a.half == "all" or str(r.get("half")) == a.half


# ───────── MFA 참조 ─────────
MFA = {}
for r in rows("mfa.jsonl"):
    if r.get("ok"):
        MFA[r["key"]] = r


def onset_err(key, ph):
    """우리 끝 모음 시작 − MFA 끝 모음 시작(초). MFA가 없으면 None."""
    m = MFA.get(key)
    fi = final_idx(ph)
    if m is None or fi is None:
        return None
    return ph[fi][1] - m["final_vowel_t0"]


def nonfinal_errs(key, ph):
    """끝이 아닌 모음 시작 차(모음 수가 MFA와 같을 때만, 보고용)."""
    m = MFA.get(key)
    if m is None:
        return []
    ours = [p[1] for p in ph if p[0].startswith("n:")]
    ref = [v[1] for v in m["vowels"]]
    if len(ours) != len(ref) or len(ours) < 2:
        return []
    return [o - r for o, r in zip(ours[:-1], ref[:-1])]


# ───────── 538·608 ─────────
def main_stats(main):
    by = {}
    for r in main:
        if r.get("err") or not in_half(r):
            continue
        by.setdefault((r["set"], r["variant"]), []).append(r)
    res = {}
    for (st, v), L in by.items():
        pair, tr, cond = split_variant(v)
        same, diff, late, fin_w, nuc_w, nuc_n, rates, slow, fin_nv, oerr, nferr, n_mfa = [], [], [], 0, 0, 0, {}, 0, [], [], [], 0
        for r in L:
            own = r["targets"][0]
            ph = own["phones"]
            fi = final_idx(ph)
            same.append(own["score"])
            diff += [t["score"] for t in r["targets"][1:]]
            se = r.get("speech_end_raw")
            if se is not None and fi is not None:
                late.append(ph[fi][1] - se)
            w = weak(ph)
            fin_w += fi in w
            nuc = [i for i, p in enumerate(ph) if p[0].startswith("n:") and i != fi]
            nuc_n += len(nuc)
            nuc_w += sum(1 for i in nuc if i in w)
            if fi is not None:
                fin_nv.append(ph[fi][3])
            rp = own.get("rate") or {}
            if rp.get("rate") is not None:
                rates[r["clip"]] = rp["rate"]
                slow += rp["rate"] < RATE_P10
            if st == "538":
                e = onset_err(f"538:{r['clip']}", ph)
                if e is not None:
                    oerr.append(e)
                    n_mfa += 1
                nferr += nonfinal_errs(f"538:{r['clip']}", ph)
        late = np.asarray(late)
        oerr = np.asarray(oerr)
        res[(pair, tr, cond, st)] = {
            "n": len(L), "auc": auc(same, diff),
            "fail65": float(np.mean([x < PASS for x in same])), "pass65_diff": float(np.mean([x >= PASS for x in diff])),
            "same_median": float(np.median(same)),
            "late_frac": float(np.mean(late > LATE_S)) if len(late) else None,
            "late_median": float(np.median(late)) if len(late) else None,
            "late_p95": float(np.percentile(late, 95)) if len(late) else None,
            "final_weak_rate": fin_w / len(L), "nuc_weak_rate": nuc_w / max(1, nuc_n),
            "final_naive_median": float(np.median(fin_nv)) if fin_nv else None,
            "slow_rate": slow / max(1, len(rates)), "rates": rates,
            "mfa_cover": (n_mfa / len(L)) if st == "538" else None,
            "onset_abs_median": float(np.median(np.abs(oerr))) if len(oerr) else None,
            "onset_signed_median": float(np.median(oerr)) if len(oerr) else None,
            "onset_within40": float(np.mean(np.abs(oerr) <= 0.040)) if len(oerr) else None,
            "nonfinal_abs_median": float(np.median(np.abs(nferr))) if nferr else None}
    for k, v in res.items():
        pair, tr, cond, st = k
        if cond == "T" and (pair, tr, "R", st) in res:
            rr, rt = res[(pair, tr, "R", st)]["rates"], v["rates"]
            ks = sorted(set(rr) & set(rt))
            v["rate_ratio_T_over_R"] = float(np.median([rt[c] / rr[c] for c in ks])) if ks else None
    for v in res.values():
        v.pop("rates", None)
    return res


# ───────── 서버 음성 ─────────
def tts_stats(tts):
    import sound_clips as SCL
    import jamo_vocab as JV
    try:
        import qa_rules as QR
    except Exception as e:                       # qa_rules가 못 올라오면 보정 비율만 빠진다
        print("qa_rules 불러오기 실패:", e)
        QR = None
    man = json.load(open(os.path.join(APP, "backend", "data", "sound", "manifest.json"), encoding="utf-8"))
    by = {}
    for r in tts:
        if not r.get("err"):
            by.setdefault(r["variant"], []).append(r)
    out = {}
    for v, L in by.items():
        pair, tr, cond = split_variant(v)
        late, sc, oerr, fixed, yo_new, yo_man, n_syl = [], [], [], 0, [], [], 0
        for r in L:
            ph = r["phones"]
            fi = final_idx(ph)
            ref = r["dur_raw"] - TTS_TAIL
            late.append(ph[fi][1] - ref)
            sc.append(r["score"])
            key = f"tts:{r['clip']}"
            e = onset_err(key, ph)
            if e is not None:
                oerr.append(e)
            toks = JV.text_to_tokens(r["target"])
            syl = SCL.syllable_times([{"token": p[0], "t0": p[1], "t1": p[2]} for p in ph], toks, duration_ms=r["dur_raw"] * 1000.0)
            if syl and QR is not None:
                n_syl += 1
                fixed += QR.fix_tail_syllables(syl, r["dur_raw"] * 1000.0 - TTS_TAIL * 1000.0) != syl
            m = MFA.get(key)
            if m is not None and ph[-1][0] == "n:ㅛ" and syl:
                yo_new.append(syl[-1][0] / 1000.0 - m["final_vowel_t0"])
                voice, k = r["clip"].split(":", 1)
                ms = (man["clips"].get(voice, {}).get(k) or {}).get("syl")
                if ms:
                    yo_man.append(ms[-1][0] / 1000.0 - m["final_vowel_t0"])
        late, oerr = np.asarray(late), np.asarray(oerr)
        out[(pair, tr, cond)] = {
            "n": len(L), "late_frac": float(np.mean(late > LATE_S)), "late_median": float(np.median(late)),
            "score_mean": float(np.mean(sc)), "mfa_cover": len(oerr) / len(L),
            "onset_abs_median": float(np.median(np.abs(oerr))) if len(oerr) else None,
            "onset_signed_median": float(np.median(oerr)) if len(oerr) else None,
            "onset_within40": float(np.mean(np.abs(oerr) <= 0.040)) if len(oerr) else None,
            "fix_tail_changed": fixed / max(1, n_syl),
            "yo_syl_abs_median_new": float(np.median(np.abs(yo_new))) if yo_new else None,
            "yo_syl_abs_median_manifest": float(np.median(np.abs(yo_man))) if yo_man else None, "yo_n": len(yo_new)}
    return out


def hyp_stats(hyp):
    out = {}
    for r in hyp:
        if r.get("err") or not in_half(r):
            continue
        k = (r["model"], r["variant"], "yo" if r["last_tok"] == "n:ㅛ" else "other")
        d = out.setdefault(k, {"n": 0, "last_frame": 0, "late": 0, "pin": []})
        d["n"] += 1
        fr = r.get("last_frames") or []
        d["last_frame"] += bool(fr) and fr[-1] >= r["n_frames"] - 2
        se = r.get("speech_end") or r["dur_raw"]
        d["late"] += r["final_t0"] > se + LATE_S
        d["pin"].append(r.get("pmax_in_speech", 0.0))
    for d in out.values():
        d["last_frame_frac"] = d["last_frame"] / d["n"]
        d["late_frac"] = d["late"] / d["n"]
        d["pmax_in_gt05"] = float(np.mean(np.asarray(d.pop("pin")) > 0.5))
    return {"|".join(k): v for k, v in out.items()}


def zeroth_stats(z):
    out = {}
    for r in z:
        if r.get("err"):
            continue
        for key, v in r.items():
            if not isinstance(v, dict) or "n_frames" not in v:
                continue
            k = (key, r["split"])
            d = out.setdefault(k, {"n": 0, "last_frame": 0, "late": 0})
            d["n"] += 1
            fr = v["last_frames"]
            d["last_frame"] += bool(fr) and fr[-1] >= v["n_frames"] - 2
            se = r["speech_end"] or r["dur"]
            d["late"] += v["final_t0"] > se + LATE_S
    for d in out.values():
        d["last_frame_frac"] = d["last_frame"] / d["n"]
        d["late_frac"] = d["late"] / d["n"]
    return {"|".join(k): v for k, v in out.items()}


def latency():
    out = {}
    for f in glob.glob(os.path.join(a.run, "latency_*.json")):
        d = json.load(open(f))
        out[d["pair"]] = d
    return out


# ───────── 판정 ─────────
def judge(M, T, LAT):
    J = {}

    def g(pair, tr, cond, st, key):
        return (M.get((pair, tr, cond, st)) or {}).get(key)

    def gt(pair, tr, cond, key):
        return (T.get((pair, tr, cond)) or {}).get(key)

    for pair, tr in CANDS:
        if (pair, tr, "R", "538") not in M:
            continue
        c = {}
        # C1: 끝 자르기 없이(그 짝의 n) 끝 모음 무음에 놓임 ≤ 5%(538 R·T, 서버 음성 R·T). t 후보는 자기 설정의 서버 음성도 ≤ 5%
        v = [g(pair, "n", cd, "538", "late_frac") for cd in "RT"] + [gt(pair, "n", cd, "late_frac") for cd in "RT"]
        if tr == "t":
            v += [gt(pair, "t", cd, "late_frac") for cd in "RT"]
        c["C1"] = all(x is not None and x <= 0.05 for x in v), v
        # C2: 끝 모음 시작과 MFA 끝 모음 시작의 절대 차 중앙 ≤ 40 ms(538 R·T, 서버 음성 R·T), MFA 덮개 ≥ 80%
        v = [g(pair, tr, cd, "538", "onset_abs_median") for cd in "RT"] + [gt(pair, tr, cd, "onset_abs_median") for cd in "RT"]
        cov = [g(pair, tr, "R", "538", "mfa_cover"), gt(pair, tr, "R", "mfa_cover")]
        c["C2"] = all(x is not None and x <= 0.040 for x in v) and all(x is not None and x >= 0.8 for x in cov), v + cov
        # C3: 608 AUC ≥ 지금 앱(같은 소리 조건) − 0.005
        v = [(g(pair, tr, cd, "608", "auc"), g(*BASE, cd, "608", "auc")) for cd in "RT"]
        c["C3"] = all(x is not None and b is not None and x >= b - 0.005 for x, b in v), v
        # C4: 다른 문장 65점 합격 538 ≤ 5%, 608 ≤ 5%
        v = [g(pair, tr, cd, st, "pass65_diff") for cd in "RT" for st in ("538", "608")]
        c["C4"] = all(x is not None and x <= 0.05 for x in v), v
        # C5: 같은 끝 자르기(t)로 측정한 짝의 지연 중앙 ≤ 지금 앱 × 1.10, 파일 크기 ±1%, 특징 추출부 공유
        L0, L1 = LAT.get("K0"), LAT.get(pair)
        if L0 and L1:
            ok = (L1["t"]["median_s"] <= 1.10 * L0["t"]["median_s"] and L1.get("shared_feature_encoder")
                  and all(abs(L1["bytes"][m] - L0["bytes"][m]) <= 0.01 * L0["bytes"][m] for m in ("aligner", "scorer")))
            c["C5"] = bool(ok), [L1["t"]["median_s"], L0["t"]["median_s"], L1["n"]["median_s"], L1.get("shared_feature_encoder")]
        else:
            c["C5"] = False, "지연 측정 없음"
        # C6: 맞게 말함 불합격 608 ≤ 앱 + 2%p, 538 ≤ 앱 + 1%p, 끝 모음 코칭 지목 538·608 ≤ 앱 + 2%p
        v, ok = [], True
        for cd in "RT":
            for st, tol in (("608", 0.02), ("538", 0.01)):
                x, b = g(pair, tr, cd, st, "fail65"), g(*BASE, cd, st, "fail65")
                v.append(("fail", st, cd, x, b))
                ok &= x is not None and b is not None and x <= b + tol
            for st in ("538", "608"):
                x, b = g(pair, tr, cd, st, "final_weak_rate"), g(*BASE, cd, st, "final_weak_rate")
                v.append(("weak", st, cd, x, b))
                ok &= x is not None and b is not None and x <= b + 0.02
        c["C6"] = bool(ok), v
        # C7: 538 R 자기 문장 표시 점수 중앙이 앱 ± 2.0 안, 서버 음성 R 점수 평균 ≥ 앱 − 1.0
        x, b = g(pair, tr, "R", "538", "same_median"), g(*BASE, "R", "538", "same_median")
        y, yb = gt(pair, tr, "R", "score_mean"), gt(*BASE, "R", "score_mean")
        c["C7"] = (x is not None and b is not None and abs(x - b) <= 2.0 and y is not None and yb is not None and y >= yb - 1.0), [x, b, y, yb]
        # C8: 538 rate(T)/rate(R) 중앙 0.97~1.03, 538 T '느림' ≤ 앱 R + 2%p
        rr = g(pair, tr, "T", "538", "rate_ratio_T_over_R")
        s, sb = g(pair, tr, "T", "538", "slow_rate"), g(*BASE, "R", "538", "slow_rate")
        c["C8"] = (rr is not None and 0.97 <= rr <= 1.03 and s is not None and sb is not None and s <= sb + 0.02), [rr, s, sb]
        c["ALL"] = all(c[k][0] for k in ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"))
        J[f"{pair}_{tr}"] = c
    # 채택 규칙(5.5절): A 우선, 같은 짝에서 n·t 둘 다 통과하면 t, 단 n의 608 T AUC가 t보다 0.005 이상 높고 n 지연 ≤ 앱 × 1.25면 n
    pick = None
    for pair in ("A", "B"):
        ok = [tr for tr in ("n", "t") if J.get(f"{pair}_{tr}", {}).get("ALL")]
        if not ok:
            continue
        if ok == ["n", "t"]:
            an, at = g(pair, "n", "T", "608", "auc"), g(pair, "t", "T", "608", "auc")
            L0, L1 = LAT.get("K0"), LAT.get(pair)
            fast = L0 and L1 and L1["n"]["median_s"] <= 1.25 * L0["t"]["median_s"]
            pick = f"{pair}_n" if (an - at >= 0.005 and fast) else f"{pair}_t"
        else:
            pick = f"{pair}_{ok[0]}"
        break
    J["pick"] = pick
    return J


def fmt(x):
    if isinstance(x, float):
        return round(x, 4)
    if isinstance(x, (list, tuple)):
        return [fmt(y) for y in x]
    return x


M = main_stats(rows("main.*.jsonl"))
T = tts_stats(rows("tts.*.jsonl"))
LAT = latency()
R = {"half": a.half, "main": {"|".join(k): v for k, v in M.items()}, "tts": {"|".join(k): v for k, v in T.items()},
     "hyp": hyp_stats(rows("hyp.*.jsonl")), "zeroth": zeroth_stats(rows("zeroth.*.jsonl")), "latency": LAT,
     "mfa_n": len(MFA), "judge": judge(M, T, LAT)}
if a.json:
    json.dump(R, open(a.json, "w"), ensure_ascii=False, indent=1, default=str)
for k, v in sorted(R["main"].items()):
    print("main", k, {kk: fmt(vv) for kk, vv in v.items()})
for sec in ("tts", "hyp", "zeroth"):
    for k, v in sorted(R[sec].items()):
        print(sec, k, {kk: fmt(vv) for kk, vv in v.items()})
for k, v in LAT.items():
    print("latency", k, v)
print("mfa", R["mfa_n"])
for k, v in R["judge"].items():
    if k == "pick":
        print("PICK", v)
    else:
        print("JUDGE", k, "ALL" if v["ALL"] else "-", {c: (("PASS" if r[0] else "FAIL"), fmt(r[1])) for c, r in v.items() if c != "ALL"})
