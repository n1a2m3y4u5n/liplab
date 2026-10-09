"""끝 구간 다시 나누기 판정(맥, docs/dgop-final-vowel-fix2-2026-10.md 3~6절의 계산을 그대로). 결과를 보기 전에 커밋한다.

    python analyze.py explore --offline OFF_H0.jsonl --ta TA_OUT [--json OUT]
    python analyze.py confirm --offline OFF_H1.jsonl --ta TA_OUT --pod POD_OUT --gate a|l [--json OUT] [--raw]

자료와 변형 이름(짝_자르기_소리):
  538·608(옛, 화자 절반 있음): K0_n·N1a_n·N1l_n은 offline.py(저장된 로짓), K0_t는 10/7 tailaug 파드 결과(TA_OUT/main.*.jsonl).
     MFA 참조는 TA_OUT/mfa.jsonl(키 538:클립).
  538n·608n·tts(새, 전체가 확인 자료): POD_OUT/main.*.jsonl·tts.*.jsonl·deg.*.jsonl·mfa.jsonl·cpu.json. 짝 K0·N1a·N1l × 자르기 n·t.
explore는 538 옛 절반 0에서 문(N1a=늘, N1l=늦을 때만)을 고른다(3.3절). confirm은 고른 문의 N1_n·N1_t를 C1~C9로 판정하고 PICK을 낸다.
"""
import argparse
import glob
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(APP, "backend"))
sys.path.insert(0, os.path.join(APP, "scripts", "sound_pod"))   # qa_rules(보고용 보정 비율, 사후 변경 2)

ap = argparse.ArgumentParser()
ap.add_argument("mode", choices=["explore", "confirm"])
ap.add_argument("--offline", required=True)
ap.add_argument("--ta", required=True)
ap.add_argument("--pod", default="")
ap.add_argument("--gate", default="")
ap.add_argument("--json", default="")
ap.add_argument("--raw", action="store_true", help="608 정제 규칙을 끈 전체본(보고용)")
a = ap.parse_args()

CLEAN = not a.raw
MAX608_S = 20.0            # 608 정제: 20초 넘는 조각 제외(10/7 tailaug 5.2절과 같다)
PASS = 65.0
RATE_P10 = 4.08            # speak_cues.RATE_P10
TTS_TAIL = 0.150           # 서버 음성은 말소리 끝 뒤 150 ms를 남겼다
LATE_S = 0.100             # 무음에 놓임
HALF_EXPLORE, HALF_CONFIRM = "0", "1"


def jl(pat):
    out = []
    for f in sorted(glob.glob(pat)):
        out += [json.loads(l) for l in open(f, encoding="utf-8") if l.strip()]
    return out


def hangul(t):
    return re.sub(r"[^가-힣]", "", t or "")


def ends_yo(t):
    return hangul(t).endswith("요")


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


# ───────── 자료 모으기 ─────────
def load_rows(half):
    """(자료, 변형) → 줄 목록. half는 옛 자료에만 적용(None = 전체)."""
    rows = jl(a.offline)
    for r in jl(os.path.join(a.ta, "main.*.jsonl")):
        if r["variant"] in ("K0_t_R", "K0_t_T"):
            r["src"] = "tailaug"
            rows.append(r)
    if half is not None:
        rows = [r for r in rows if str(r.get("half")) == half]
    if a.pod:
        rows += jl(os.path.join(a.pod, "main.*.jsonl")) + jl(os.path.join(a.pod, "tts.*.jsonl"))
    by = {}
    for r in rows:
        if r.get("err"):
            continue
        st = r["set"]
        if CLEAN and st in ("608", "608n") and r["dur_raw"] > MAX608_S:
            continue
        by.setdefault((st, r["variant"]), []).append(r)
    return by


MFA = {}
for r in jl(os.path.join(a.ta, "mfa.jsonl")):
    if r.get("ok") and r["key"].startswith("538:"):
        MFA[r["key"]] = r
if a.pod:
    for r in jl(os.path.join(a.pod, "mfa.jsonl")):
        if r.get("ok"):
            MFA[r["key"]] = r


def stats(st, L):
    same, diff, late, fin_w, oerr, oerr_yo, rates, slow, n_mfa, moved, yo_n = [], [], [], 0, [], [], {}, 0, 0, 0, 0
    for r in L:
        own = r["targets"][0]
        assert own["kind"] == "same"
        ph = own["phones"]
        fi = final_idx(ph)
        same.append(own["score"])
        diff += [t["score"] for t in r["targets"][1:] if not (CLEAN and hangul(t["target"]) == hangul(own["target"]))]
        ref = (r["dur_raw"] - TTS_TAIL) if st == "tts" else r.get("speech_end_raw")
        if ref is not None and fi is not None:
            late.append(ph[fi][1] - ref)
        fin_w += fi in weak(ph)
        rp = own.get("rate") or {}
        if rp.get("rate") is not None:
            rates[r["clip"]] = rp["rate"]
            slow += rp["rate"] < RATE_P10
        moved += bool(own.get("retimed"))
        m = MFA.get(f"{st}:{r['clip']}")
        yo = ends_yo(own["target"])
        yo_n += yo
        if m is not None and fi is not None:
            e = ph[fi][1] - m["final_vowel_t0"]
            oerr.append(e)
            n_mfa += 1
            if yo:
                oerr_yo.append(e)
    late, oerr, oerr_yo = np.asarray(late), np.asarray(oerr), np.asarray(oerr_yo)
    med = lambda x: float(np.median(x)) if len(x) else None
    return {"n": len(L), "auc": auc(same, diff) if diff else None,
            "fail65": float(np.mean([x < PASS for x in same])),
            "pass65_diff": float(np.mean([x >= PASS for x in diff])) if diff else None,
            "same_median": med(same), "score_mean": float(np.mean(same)),
            "late_frac": float(np.mean(late > LATE_S)) if len(late) else None, "late_median": med(late),
            "final_weak_rate": fin_w / len(L), "slow_rate": slow / max(1, len(rates)), "rates": rates,
            "rate_median": med(list(rates.values())), "retimed_frac": moved / len(L),
            "mfa_cover": n_mfa / len(L), "onset_abs_median": med(np.abs(oerr)), "onset_signed_median": med(oerr),
            "onset_p90": float(np.percentile(np.abs(oerr), 90)) if len(oerr) else None,
            "yo_n": int(yo_n), "yo_mfa_n": len(oerr_yo), "onset_yo_abs_median": med(np.abs(oerr_yo))}


def all_stats(by):
    S = {}
    for (st, v), L in by.items():
        S[(st, v)] = stats(st, L)
    for (st, v), s in S.items():
        if v.endswith("_T"):
            r = S.get((st, v[:-1] + "R"))
            if r:
                ks = sorted(set(r["rates"]) & set(s["rates"]))
                s["rate_ratio_T_over_R"] = float(np.median([s["rates"][c] / r["rates"][c] for c in ks])) if ks else None
    for s in S.values():
        s.pop("rates", None)
    return S


def tts_extra(by):
    """서버 음성: fix_tail_syllables가 바꾸는 클립 비율, '요' 끝 클립 마지막 음절 시작과 MFA의 차(새 정렬 대 지금 목록)."""
    import sound_clips as SCL
    import jamo_vocab as JV
    try:
        import qa_rules as QR
    except Exception as e:
        print("qa_rules 불러오기 실패:", e)
        QR = None
    man = json.load(open(os.path.join(APP, "backend", "data", "sound", "manifest.json"), encoding="utf-8"))
    out = {}
    for (st, v), L in by.items():
        if st != "tts":
            continue
        fixed, n_syl, yo_new, yo_man = 0, 0, [], []
        for r in L:
            ph = r["targets"][0]["phones"]
            toks = JV.text_to_tokens(r["targets"][0]["target"])
            syl = SCL.syllable_times([{"token": p[0], "t0": p[1], "t1": p[2]} for p in ph], toks, duration_ms=r["dur_raw"] * 1000.0)
            if syl and QR is not None:
                n_syl += 1
                fixed += QR.fix_tail_syllables(syl, r["dur_raw"] * 1000.0 - TTS_TAIL * 1000.0) != syl
            m = MFA.get(f"tts:{r['clip']}")
            if m is not None and ph[-1][0] == "n:ㅛ" and syl:
                yo_new.append(syl[-1][0] / 1000.0 - m["final_vowel_t0"])
                voice, k = r["clip"].split(":", 1)
                ms = (man["clips"].get(voice, {}).get(k) or {}).get("syl")
                if ms:
                    yo_man.append(ms[-1][0] / 1000.0 - m["final_vowel_t0"])
        out[v] = {"fix_tail_changed": fixed / max(1, n_syl), "yo_n": len(yo_new),
                  "yo_syl_abs_median_new": float(np.median(np.abs(yo_new))) if yo_new else None,
                  "yo_syl_abs_median_manifest": float(np.median(np.abs(yo_man))) if yo_man else None}
    return out


def deg_stats():
    rows = [r for r in jl(os.path.join(a.pod, "deg.*.jsonl")) if not r.get("err")] if a.pod else []
    out = {}
    for tr in ("n", "t"):
        by = {}
        for r in rows:
            p, t, sev = r["variant"].split("_")
            if t == tr:
                by.setdefault(r["clip"], {})[sev] = r["raw"]
        full = [d for d in by.values() if all(s in d for s in ("clean", "mild", "mod", "sev"))]
        if not full:
            continue
        mono = [d["clean"] >= d["mild"] >= d["mod"] >= d["sev"] for d in full]
        out[tr] = {"n": len(full), "monotone": float(np.mean(mono)),
                   "auc_clean_sev": auc([d["clean"] for d in full], [d["sev"] for d in full]),
                   "means": {s: float(np.mean([d[s] for d in full])) for s in ("clean", "mild", "mod", "sev")}}
    return out


def fmt(x):
    if isinstance(x, float):
        return round(x, 4)
    if isinstance(x, (list, tuple)):
        return [fmt(y) for y in x]
    if isinstance(x, dict):
        return {k: fmt(v) for k, v in x.items()}
    return x


def print_stats(S):
    for k, v in sorted(S.items()):
        print("STAT", "|".join(k), fmt(v))


# ───────── 탐색: 문 고르기(3.3절) ─────────
def explore():
    by = load_rows(HALF_EXPLORE)
    S = all_stats(by)
    print_stats(S)
    sc = {}
    for g in ("N1a", "N1l"):
        v = [S.get(("538", f"{g}_n_{cd}"), {}).get("onset_abs_median") for cd in "RT"]
        sc[g] = float(np.mean(v)) if all(x is not None for x in v) else None
    pick = "l" if sc["N1l"] is not None and (sc["N1a"] is None or sc["N1l"] <= sc["N1a"] + 0.002) else "a"
    res = {"half": HALF_EXPLORE, "score_mean_onset_abs_median": sc, "gate": pick,
           "stats": {"|".join(k): v for k, v in S.items()}}
    print("GATE_SCORES", fmt(sc))
    print("GATE", pick, "(a = 늘, l = 끝 토큰이 늦을 때만)")
    return res


# ───────── 확인: 판정(5~6절) ─────────
def confirm():
    assert a.gate in ("a", "l") and a.pod, "--gate a|l 과 --pod가 필요하다"
    G = "N1" + a.gate
    by = load_rows(HALF_CONFIRM)
    S = all_stats(by)
    T = tts_extra(by)
    D = deg_stats()
    CPU = json.load(open(os.path.join(a.pod, "cpu.json"))) if os.path.exists(os.path.join(a.pod, "cpu.json")) else {}
    print_stats(S)
    for k, v in T.items():
        print("TTSX", k, fmt(v))
    for k, v in D.items():
        print("DEG", k, fmt(v))
    print("CPU", fmt(CPU))

    def g(st, v, key):
        return (S.get((st, v)) or {}).get(key)

    J = {}
    for tr in ("n", "t"):
        cand = f"{G}_{tr}"
        c = {}
        # 538 옛 자료(저장된 로짓)는 끝 자르기 없는 설정만 계산할 수 있다
        s538 = ["538n"] + (["538"] if tr == "n" else [])
        s608 = ["608n"] + (["608"] if tr == "n" else [])
        base = lambda st, cd: f"K0_t_{cd}"
        # C1 시각: 끝 모음 무음에 놓임 ≤ 5%(538·서버 음성, R·T)
        v = [(st, cd, g(st, f"{cand}_{cd}", "late_frac")) for st in s538 + ["tts"] for cd in "RT"]
        c["C1"] = all(x is not None and x <= 0.05 for *_, x in v), v
        # C2 실제 시작: MFA 끝 모음 시작과의 절대 차 중앙 ≤ 40 ms, '요' 끝만 ≤ 60 ms, MFA 덮개 ≥ 80%
        v = [(st, cd, g(st, f"{cand}_{cd}", "onset_abs_median"), g(st, f"{cand}_{cd}", "onset_yo_abs_median"),
              g(st, f"{cand}_{cd}", "mfa_cover")) for st in s538 + ["tts"] for cd in "RT"]
        c["C2"] = all(x is not None and x <= 0.040 and y is not None and y <= 0.060 and cv is not None and cv >= 0.8
                      for _, _, x, y, cv in v), v
        # C3 분리도: 608 AUC ≥ K0_t − 0.005(같은 자료·소리 조건), 538 AUC ≥ 0.99
        v, ok = [], True
        for st in s608:
            for cd in "RT":
                x, b = g(st, f"{cand}_{cd}", "auc"), g(st, base(st, cd), "auc")
                v.append((st, cd, x, b))
                ok &= x is not None and b is not None and x >= b - 0.005
        for st in s538:
            for cd in "RT":
                x = g(st, f"{cand}_{cd}", "auc")
                v.append((st, cd, x))
                ok &= x is not None and x >= 0.99
        c["C3"] = bool(ok), v
        # C4 다른 문장: 65점 합격 ≤ 5%(538·608)
        v = [(st, cd, g(st, f"{cand}_{cd}", "pass65_diff")) for st in s538 + s608 for cd in "RT"]
        c["C4"] = all(x is not None and x <= 0.05 for *_, x in v), v
        # C5 지연·경로: CPU 2스레드 지연 중앙 ≤ K0_t × 1.10(t), × 1.25(n), CPU·GPU 점수 차 ≤ 0.5, 시각 차 ≤ 1프레임(0.02초) 99% 이상
        cc, cb = (CPU.get("configs") or {}).get(f"{G}_{tr}"), (CPU.get("configs") or {}).get("K0_t")
        if cc and cb:
            lim = 1.10 if tr == "t" else 1.25
            ok = (cc["median_s"] <= lim * cb["median_s"] and cc["score_diff_max"] is not None and cc["score_diff_max"] <= 0.5
                  and cc["time_diff_gt_frame"] is not None and cc["time_diff_gt_frame"] <= 0.01 and CPU.get("shared_feature_encoder"))
            c["C5"] = bool(ok), [cc["median_s"], cb["median_s"], lim, cc["score_diff_max"], cc["time_diff_gt_frame"]]
        else:
            c["C5"] = False, "CPU 측정 없음"
        # C6 맞는 문장·코칭: 맞게 말함 불합격 608 ≤ K0_t + 2%p, 538 ≤ K0_t + 1%p, 끝 모음 지목 ≤ K0_t + 2%p
        v, ok = [], True
        for cd in "RT":
            for st in s608 + s538:
                tol = 0.02 if st.startswith("608") else 0.01
                x, b = g(st, f"{cand}_{cd}", "fail65"), g(st, base(st, cd), "fail65")
                v.append(("fail", st, cd, x, b))
                ok &= x is not None and b is not None and x <= b + tol
                x, b = g(st, f"{cand}_{cd}", "final_weak_rate"), g(st, base(st, cd), "final_weak_rate")
                v.append(("weak", st, cd, x, b))
                ok &= x is not None and b is not None and x <= b + 0.02
        c["C6"] = bool(ok), v
        # C7 눈금: 538n R 자기 문장 표시 점수 중앙 K0_t ± 2.0, 서버 음성 R 평균 ≥ K0_t − 1.0
        x, b = g("538n", f"{cand}_R", "same_median"), g("538n", "K0_t_R", "same_median")
        y, yb = g("tts", f"{cand}_R", "score_mean"), g("tts", "K0_t_R", "score_mean")
        c["C7"] = (None not in (x, b, y, yb) and abs(x - b) <= 2.0 and y >= yb - 1.0), [x, b, y, yb]
        # C8 말 빠르기: 538 rate(T)/rate(R) 중앙 0.97~1.03, 538 T '느림' ≤ K0_t R + 2%p
        v, ok = [], True
        for st in s538:
            rr, s, sb = g(st, f"{cand}_T", "rate_ratio_T_over_R"), g(st, f"{cand}_T", "slow_rate"), g(st, "K0_t_R", "slow_rate")
            v.append((st, rr, s, sb))
            ok &= None not in (rr, s, sb) and 0.97 <= rr <= 1.03 and s <= sb + 0.02
        c["C8"] = bool(ok), v
        # C9 저하 강도 순서: 538n 단조 비율 ≥ K0_t − 2%p, AUC(원본 > 심) ≥ K0_t − 0.01(점수는 같은 자르기의 K0와 같다)
        dc, db = D.get(tr), D.get("t")
        c["C9"] = (bool(dc and db and dc["monotone"] >= db["monotone"] - 0.02 and dc["auc_clean_sev"] >= db["auc_clean_sev"] - 0.01),
                   [dc and dc["monotone"], db and db["monotone"], dc and dc["auc_clean_sev"], db and db["auc_clean_sev"]])
        c["ALL"] = all(c[k][0] for k in ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9"))
        J[cand] = c
    # 채택 규칙(6절): 둘 다 통과하면 t, 단 n의 608n T AUC가 t보다 0.005 이상 높고 n 지연 ≤ K0_t × 1.25면 n
    ok = [tr for tr in ("n", "t") if J[f"{G}_{tr}"]["ALL"]]
    pick = None
    if ok == ["n", "t"]:
        an, at = g("608n", f"{G}_n_T", "auc"), g("608n", f"{G}_t_T", "auc")
        cn, cb = (CPU.get("configs") or {}).get(f"{G}_n"), (CPU.get("configs") or {}).get("K0_t")
        fast = bool(cn and cb and cn["median_s"] <= 1.25 * cb["median_s"])
        pick = f"{G}_n" if (an is not None and at is not None and an - at >= 0.005 and fast) else f"{G}_t"
    elif ok:
        pick = f"{G}_{ok[0]}"
    J["pick"] = pick
    for k, v in J.items():
        if k == "pick":
            print("PICK", v)
        else:
            print("JUDGE", k, "ALL" if v["ALL"] else "-", {cc: (("PASS" if r[0] else "FAIL"), fmt(r[1])) for cc, r in v.items() if cc != "ALL"})
    return {"gate": a.gate, "clean": CLEAN, "stats": {"|".join(k): v for k, v in S.items()}, "tts_extra": T, "deg": D, "cpu": CPU,
            "judge": J}


R = explore() if a.mode == "explore" else confirm()
if a.json:
    json.dump(R, open(a.json, "w"), ensure_ascii=False, indent=1, default=str)
