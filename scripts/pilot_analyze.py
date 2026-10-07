#!/usr/bin/env python
"""
예비 파일럿 주분석(사전 등록 초안의 계산). 가명 내보내기(`GET /api/pilot/export?trials=true`, 판 7 이상)를 받아 두 파일럿의 주결과를
계산하고 보고서(Markdown)와 수치(JSON)를 만든다. 사전·사후 A·B 설계(protocol.md 6절)는 예전 스크립트 `pilot_analysis.py`가 맡는다.

1. P3 청인 독화 파일럿(`docs/pilot/claim-ledger.md` 3.3, `design-simulation.md` 2·5절)
   - 주지표: 실제 얼굴 개방형 문장(battery layer `sentence`) 엄격 음소 정답률의 사람별 D = (B − A2) − (A2 − A1) = B − 2·A2 + A1(%p).
     회차 점수는 맞힌 음소 수 합 / 목표 음소 수 합. A1·A2·B 문장 층을 모두 마친 사람(완료자)만 넣는다.
   - 순서(planned_order)를 고정효과로 둔 평균: 순서 평균들의 평균, 오차는 순서 안 잔차의 합동 분산, 자유도 n − (순서 수).
   - 3갈래 판정(MME 5%p): 지지 = 95% 구간 하한 > 0, 반증 = 하한 ≤ 0이고 상한 < MME, 판정 불가 = 나머지.
   - 함께 보고: B − A2(관대한 상한), 낱말 4지선다·무의미 낱말 자음 층의 같은 D(판정 없음), R − A2(유지), RCI ≥ 1.96 비율,
     ITT(배정·시작·완료 인원과 끝내지 못한 층), 소음 속 문장 시청각 이득(VE), SNR 계단 미수렴(estimate_kind = last_levels) 목록,
     학습량(A2 완료 날부터 B 완료 날까지의 학습 날 수와 분).
   - 순차 멈춤 규칙: B 완료 순번(b_completed_seq)으로 완료자를 줄 세워 5·10·…·40명마다 한쪽 JZS BF+0(반코시 r = 0.707)을 순서 고정효과
     t로 계산한다. 10명 전에는 멈추지 않고, BF ≥ 6(지지 쪽) 또는 ≤ 1/6(영가설 쪽)에서 멈춘다. 최대 40명. 판정 문장은 멈춘 시점의
     구간 판정으로 고른다(claim-ledger 1절 5).
2. 소리 듣기 청인 모의 파일럿(`docs/pilot/listen-vocoder-pilot-prereg.md` 3절)
   - 주결과: 인공와우 모의(sim=ci) 잡담 잡음(babble) 역치 검사의 사람별 개선 = 사전 SRT − 사후 SRT(dB, 클수록 좋음). 사전은 처음 마친
     검사, 사후는 그 뒤 마지막으로 마친 검사. 집단 차이(훈련 − 대조)와 Welch 95% 구간.
   - 판정(초안 값): 성공 = 차이 ≥ 2 dB이고 하한 > 0, 실패 = 상한 < 1 dB, 판정 불가 = 나머지.
   - 일반화: talker2 잡음 같은 계산, 낱말 일반화 검사 정답률 변화(%p). 층화 변수인 첫 검사 폼(A→B, B→A)별 인원.
   - 순차 규칙: 집단마다 12명이 차면 한 번 들여다본다. 사후 검사 날짜(같은 날이면 가명 순)로 앞 12명씩을 같은 판정에 넣는다.
   - 용량: 사전 검사 날부터 사후 검사 날까지 훈련한 날 수와 분(listen.days, 대조 집단은 reading_days).

가정값과 판정 경계는 등록 전 초안이다(두 문서의 7·6절 결정 사항). 결과를 보기 전에 이 파일의 상수와 명령줄 기본값을 고정한다.

  python scripts/pilot_analyze.py export.json --out pilot_out \\
      --p3-cohorts train,control --listen-train listen_ci --listen-control listen_ctrl [--allow-avatar] [--withdrawn pid1,pid2]

--allow-avatar: 촬영 전(문장 층 modality가 avatar)인 리허설 자료로도 계산한다. 주결과는 실제 얼굴 조건이라 본 분석에서는 쓰지 않는다.
"""
import argparse
import json
import math
import os
import statistics
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from pilot_analysis import mean_ci, t_crit, welch_ci, _pearson  # noqa: E402

MME_P3 = 5.0                    # %p, master-plan 0절 원칙 3
SEQ = {"looks_every": 5, "n_min": 10, "n_max": 40, "upper": 6.0, "lower": 1 / 6, "r": math.sqrt(2) / 2}
LISTEN = {"success_diff_db": 2.0, "fail_upper_db": 1.0, "look_n_per_group": 12, "sessions": 5, "minutes_per_session": 20}
LABELS = ("A1", "A2", "B", "R")


# ───────────────────────── 공통 ─────────────────────────
def verdict(lo, hi, mme):
    if lo is None or hi is None:
        return None
    if lo > 0:
        return "support"
    if hi < mme:
        return "refute"
    return "undecided"


VERDICT_KO = {"support": "지지", "refute": "반증", "undecided": "판정 불가", None: "계산 불가",
              "success": "성공", "fail": "실패"}


def order_adjusted(values, orders):
    """순서 고정효과 평균. values·orders는 같은 길이. 반환 {estimate, se, df, n_eff, lo, hi, n, n_by_order} 또는 계산 불가면 estimate None.
    추정값 = 순서 평균들의 평균, 오차 분산 = 순서 안 잔차의 합동 분산(자유도 n − k), se² = s² · Σ(1/n_o) / k²(설계 문서 2.1)."""
    groups = {}
    for v, o in zip(values, orders):
        groups.setdefault(o, []).append(v)
    n, k = len(values), len(groups)
    out = {"n": n, "n_by_order": {o: len(v) for o, v in sorted(groups.items())}, "estimate": None, "se": None, "df": None,
           "n_eff": None, "lo": None, "hi": None}
    if n - k < 1:
        return out
    means = {o: statistics.fmean(v) for o, v in groups.items()}
    est = statistics.fmean(means.values())
    ss = sum((x - means[o]) ** 2 for o, v in groups.items() for x in v)
    df = n - k
    inv = sum(1.0 / len(v) for v in groups.values())
    se = math.sqrt(ss / df * inv / (k * k))
    h = t_crit(df, 0.95) * se
    out.update(estimate=est, se=se, df=df, n_eff=k * k / inv, lo=est - h, hi=est + h)
    return out


_BF = {}


def bf_plus0(t, n_eff, df, r=SEQ["r"]):
    """한쪽 JZS BF+0(δ > 0 반코시 척도 r). design-simulation과 같은 수치 적분(pilot_design_sim.bf_table)을 쓴다."""
    if t is None or df is None or df < 1:
        return None
    import numpy as np
    from pilot_design_sim import bf_table
    key = (round(t, 6), round(n_eff, 6), df, r)
    if key not in _BF:
        plus, _two = bf_table(n_eff, df, r, np.array([float(t)]))
        _BF[key] = float(plus[0])
    return _BF[key]


def _d(s):
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


# ───────────────────────── P3 ─────────────────────────
def layer_score(row):
    """회차 행 하나 → 점수(%) 또는 None. 문장·소음 층은 엄격 음소 합 / 합, 낱말은 정답률, 무의미 낱말은 자리 정답률."""
    if row["layer"] in ("sentence", "av", "snr"):
        rs = [r for r in (row.get("open") or []) if r.get("n_target_phonemes")]
        tot = sum(r["n_target_phonemes"] for r in rs)
        return 100.0 * sum(r["n_matched_phonemes"] or 0 for r in rs) / tot if tot else None
    rs = row.get("closed") or []
    if not rs:
        return None
    if row["layer"] == "nonsense":
        return 100.0 * sum(r.get("consonant_hits") or 0 for r in rs) / (3 * len(rs))
    return 100.0 * sum(1 for r in rs if r.get("correct")) / len(rs)


def p3_person(p, layer, allow_avatar):
    """{label: 점수} (마친 층만), 결측 사유."""
    out, why = {}, {}
    for b in p.get("battery") or []:
        if b["layer"] != layer:
            continue
        lab = b["session_label"]
        if not b.get("completed"):
            why[lab] = "not_completed"
            continue
        if layer == "sentence" and b.get("modality") != "real" and not allow_avatar:
            why[lab] = "not_real_face"
            continue
        if layer == "sentence" and any(r.get("n_target_phonemes") is None for r in b.get("open") or []):
            why[lab] = "needs_rescore"   # 엄격 채점이 비었다: scripts/pilot_battery_rescore.py
            continue
        s = layer_score(b)
        if s is None:
            why[lab] = "no_responses"
            continue
        out[lab] = s
    return out, why


def index_rows(parts, layer, allow_avatar):
    rows = []
    for p in parts:
        sc, why = p3_person(p, layer, allow_avatar)
        if all(x in sc for x in ("A1", "A2", "B")):
            rows.append({"pid": p["pid"], "order": p.get("planned_order") or "?", "b_seq": p.get("b_completed_seq"),
                         "A1": sc["A1"], "A2": sc["A2"], "B": sc["B"], "R": sc.get("R"),
                         "D": sc["B"] - 2 * sc["A2"] + sc["A1"], "BmA2": sc["B"] - sc["A2"]})
    return rows


def sequential(rows):
    """B 완료 순번으로 줄 세운 완료자의 순차 BF. looks: [{n, estimate, t, bf, stop}]."""
    rs = sorted((r for r in rows if r.get("b_seq")), key=lambda r: r["b_seq"])
    looks, stopped = [], None
    for k in range(SEQ["looks_every"], min(len(rs), SEQ["n_max"]) + 1, SEQ["looks_every"]):
        sub = rs[:k]
        oa = order_adjusted([r["D"] for r in sub], [r["order"] for r in sub])
        t = oa["estimate"] / oa["se"] if oa["estimate"] is not None and oa["se"] else None
        bf = bf_plus0(t, oa["n_eff"], oa["df"]) if t is not None else None
        stop = None
        if stopped is None and bf is not None and k >= SEQ["n_min"]:
            stop = "support" if bf >= SEQ["upper"] else ("null" if bf <= SEQ["lower"] else None)
            if stop:
                stopped = {"n": k, "side": stop, "bf": bf, "estimate": oa["estimate"], "lo": oa["lo"], "hi": oa["hi"],
                           "verdict": verdict(oa["lo"], oa["hi"], MME_P3)}
        looks.append({"n": k, "estimate": oa["estimate"], "lo": oa["lo"], "hi": oa["hi"], "t": t, "bf_plus0": bf,
                      "n_by_order": oa["n_by_order"], "stop": stop})
    if stopped:
        state = "stopped"
    elif len(rs) >= SEQ["n_max"]:
        state = "max_reached"
    else:
        state = "continue"
    return {"rule": SEQ, "n_completers_with_seq": len(rs), "looks": looks, "stopped": stopped, "state": state}


def p3_analyze(parts, allow_avatar=False):
    res = {"warnings": []}
    rows = index_rows(parts, "sentence", allow_avatar)
    oa = order_adjusted([r["D"] for r in rows], [r["order"] for r in rows])
    if oa["estimate"] is not None and len(oa["n_by_order"]) < 3:
        res["warnings"].append("세 폼 순서가 모두 차지 않아 폼 난이도가 순서 효과와 섞인다")
    up = order_adjusted([r["BmA2"] for r in rows], [r["order"] for r in rows])
    res["primary"] = {"layer": "sentence", "metric": "strict phoneme accuracy (%p)", "mme": MME_P3, **oa,
                      "verdict": verdict(oa["lo"], oa["hi"], MME_P3),
                      "naive_ci": mean_ci([r["D"] for r in rows])}
    res["upper_b_minus_a2"] = up
    res["persons"] = rows
    sec = {}
    for layer in ("word", "nonsense"):
        rr = index_rows(parts, layer, True)
        sec[layer] = {**order_adjusted([r["D"] for r in rr], [r["order"] for r in rr]),
                      "b_minus_a2": order_adjusted([r["BmA2"] for r in rr], [r["order"] for r in rr])["estimate"]}
    res["secondary"] = sec
    # 유지(R − A2)와 B 뒤 날수
    ret = []
    for p in parts:
        sc, _ = p3_person(p, "sentence", allow_avatar)
        if "R" in sc and "A2" in sc:
            bd = max((_d(b.get("completed_on")) for b in p.get("battery") or [] if b["session_label"] == "B" and b.get("completed_on")),
                     default=None)
            rd = min((_d(b.get("completed_on")) for b in p.get("battery") or [] if b["session_label"] == "R" and b.get("completed_on")),
                     default=None)
            ret.append({"pid": p["pid"], "R_minus_A2": sc["R"] - sc["A2"], "days_after_b": (rd - bd).days if bd and rd else None})
    res["retention"] = {"n": len(ret), "mean": statistics.fmean([x["R_minus_A2"] for x in ret]) if ret else None,
                        "ci": mean_ci([x["R_minus_A2"] for x in ret]), "persons": ret}
    # RCI: A1·A2 재검사로 신뢰도를 잡고 B − A2의 신뢰할 만한 변화 비율
    rci = None
    if len(rows) >= 3:
        r12 = _pearson([r["A1"] for r in rows], [r["A2"] for r in rows])
        sd1 = statistics.stdev([r["A1"] for r in rows])
        if r12 is not None and r12 < 1 and sd1 > 0:
            sdiff = math.sqrt(2) * sd1 * math.sqrt(1 - r12)
            rci = {"r_a1_a2": r12, "s_diff": sdiff,
                   "share_rci_ge_1_96": sum(1 for r in rows if r["BmA2"] / sdiff >= 1.96) / len(rows)}
    res["rci"] = rci
    # ITT: 배정(참여 순번 있음), 회차별 문장 층 완료, 끝내지 못한 층과 준비 전 문항
    assigned = [p for p in parts if p.get("join_seq")]
    by_label = {lab: sum(1 for p in assigned if any(b["session_label"] == lab and b["layer"] == "sentence" and b.get("completed")
                                                       for b in p.get("battery") or [])) for lab in LABELS}
    unfinished = [(p["pid"], b["session_label"], b["layer"]) for p in assigned for b in p.get("battery") or [] if not b.get("completed")]
    missing = {}
    for p in assigned:
        for b in p.get("battery") or []:
            for k, n in (b.get("missing") or {}).items():
                key = f"{b['layer']}:{k}"
                missing[key] = missing.get(key, 0) + n
    why = {}
    for p in assigned:
        _, w = p3_person(p, "sentence", allow_avatar)
        for lab, reason in w.items():
            why[reason] = why.get(reason, 0) + 1
    res["itt"] = {"n_participants": len(parts), "n_assigned": len(assigned), "sentence_completed_by_label": by_label,
                  "n_completers": len(rows), "unfinished_layers": unfinished, "missing_items": missing,
                  "excluded_sentence_rows": why}
    # SNR 계단 미수렴과 소음 속 시청각 이득 VE = (AV − A) / (100 − A)
    snr = []
    for p in assigned:
        for b in p.get("battery") or []:
            if b["layer"] == "snr" and b.get("completed") and b.get("n_ready"):
                snr.append({"pid": p["pid"], "snr_db": b.get("snr_calibrated_db"), "kind": b.get("snr_estimate_kind"),
                            "reversals": b.get("snr_reversals"), "headphone": b.get("headphone_check"),
                            "volume_fixed": b.get("volume_fixed")})
    res["snr"] = {"n": len(snr), "not_converged": [s["pid"] for s in snr if s["kind"] != "reversals"],
                  "checks_missing": [s["pid"] for s in snr if not (s["headphone"] and s["volume_fixed"])], "persons": snr}
    ve = {}
    for p in assigned:
        for b in p.get("battery") or []:
            if b["layer"] != "av" or not b.get("open"):
                continue
            sc = {}
            for mod in ("A", "AV"):
                rs = [r for r in b["open"] if r.get("modality") == mod and r.get("n_target_phonemes")]
                tot = sum(r["n_target_phonemes"] for r in rs)
                sc[mod] = 100.0 * sum(r["n_matched_phonemes"] or 0 for r in rs) / tot if tot else None
            if sc["A"] is not None and sc["AV"] is not None and sc["A"] < 100:
                ve.setdefault(b["session_label"], []).append((sc["AV"] - sc["A"]) / (100.0 - sc["A"]))
    res["av_gain"] = {lab: {"n": len(v), "mean_ve": statistics.fmean(v)} for lab, v in sorted(ve.items())}
    # 학습량: A2 문장 층을 마친 날 다음 날부터 B 문장 층을 마친 날까지
    dose = []
    for p in assigned:
        a2 = [_d(b.get("completed_on")) for b in p.get("battery") or [] if b["session_label"] == "A2" and b["layer"] == "sentence"]
        bb = [_d(b.get("completed_on")) for b in p.get("battery") or [] if b["session_label"] == "B" and b["layer"] == "sentence"]
        lo, hi = (a2[0] if a2 else None), (bb[0] if bb else None)
        days = [d for d in p.get("reading_days") or [] if _d(d["day"]) and (lo is None or _d(d["day"]) >= lo)
                and (hi is None or _d(d["day"]) <= hi)]
        dose.append({"pid": p["pid"], "days": len(days), "minutes": round(sum(d.get("minutes") or 0 for d in days), 1),
                     "trials": sum(d.get("n") or 0 for d in days), "reset_on": p.get("learning_reset_on")})
    res["dose"] = dose
    res["sequential"] = sequential(rows)
    return res


# ───────────────────────── 소리 듣기 ─────────────────────────
def _pre_post(tests, key):
    """시간순 기록에서 처음 마친 것과 그 뒤 마지막으로 마친 것."""
    done = [t for t in tests if t.get(key) is not None]
    if len(done) < 2:
        return (done[0] if done else None), None
    return done[0], done[-1]


def listen_person(p, sim="ci"):
    lt = (p.get("listen") or {})
    out = {"pid": p["pid"], "cohort": p.get("cohort"), "flags": []}
    for noise in ("babble", "talker2"):
        ts = [t for t in lt.get("tests") or [] if t.get("noise") == noise and (sim is None or t.get("sim") == sim)]
        pre, post = _pre_post(ts, "srt_db")
        out[noise] = {"pre": pre and pre["srt_db"], "post": post and post["srt_db"],
                      "pre_form": pre and pre.get("form"), "post_form": post and post.get("form"),
                      "pre_on": pre and pre.get("started_on"), "post_on": post and post.get("started_on"),
                      "improvement": (pre["srt_db"] - post["srt_db"]) if pre and post else None}
        if pre and post and pre.get("form") == post.get("form"):
            out["flags"].append(f"{noise}_same_form")
        others = [t for t in lt.get("tests") or [] if t.get("noise") == noise and t.get("sim") != sim and t.get("srt_db") is not None]
        if others:
            out["flags"].append(f"{noise}_other_sim_tests_ignored")
    wt = [t for t in lt.get("word_tests") or [] if t.get("complete") and (sim is None or t.get("sim") == sim)]
    pre, post = _pre_post(wt, "accuracy")
    out["word"] = {"pre": pre and pre["accuracy"], "post": post and post["accuracy"],
                   "change_pp": 100.0 * (post["accuracy"] - pre["accuracy"]) if pre and post else None}
    first = next((t for t in lt.get("tests") or [] if t.get("noise") == "babble"), None)
    out["first_form"] = first and first.get("form")
    lo, hi = _d(out["babble"]["pre_on"]), _d(out["babble"]["post_on"])
    days = [d for d in lt.get("days") or [] if _d(d["day"]) and (lo is None or _d(d["day"]) >= lo) and (hi is None or _d(d["day"]) <= hi)]
    rdays = [d for d in p.get("reading_days") or [] if _d(d["day"]) and (lo is None or _d(d["day"]) >= lo)
             and (hi is None or _d(d["day"]) <= hi)]
    out["dose"] = {"listen_days": len(days), "listen_minutes": round(sum(d.get("minutes") or 0 for d in days), 1),
                   "listen_ci_trials": sum(d.get("n_ci") or 0 for d in days),
                   "reading_days": len(rdays), "reading_minutes": round(sum(d.get("minutes") or 0 for d in rdays), 1)}
    return out


def listen_decision(train, ctrl):
    a = [x for x in train if x is not None]
    b = [x for x in ctrl if x is not None]
    if not a or not b:
        return {"n_train": len(a), "n_control": len(b), "diff": None, "ci": None, "verdict": None}
    diff = statistics.fmean(a) - statistics.fmean(b)
    ci = welch_ci(a, b)
    v = None
    if ci:
        if diff >= LISTEN["success_diff_db"] and ci[0] > 0:
            v = "success"
        elif ci[1] < LISTEN["fail_upper_db"]:
            v = "fail"
        else:
            v = "undecided"
    return {"n_train": len(a), "n_control": len(b), "mean_train": statistics.fmean(a), "mean_control": statistics.fmean(b),
            "diff": diff, "ci": ci, "verdict": v}


def listen_analyze(parts, train_cohorts, control_cohorts, sim="ci"):
    persons = [listen_person(p, sim) for p in parts if p.get("cohort") in set(train_cohorts) | set(control_cohorts)]
    tr = [x for x in persons if x["cohort"] in train_cohorts]
    ct = [x for x in persons if x["cohort"] in control_cohorts]
    res = {"sim": sim, "train_cohorts": list(train_cohorts), "control_cohorts": list(control_cohorts), "persons": persons,
           "rule": LISTEN}
    res["primary"] = {"noise": "babble", **listen_decision([x["babble"]["improvement"] for x in tr],
                                                           [x["babble"]["improvement"] for x in ct])}
    res["talker2"] = listen_decision([x["talker2"]["improvement"] for x in tr], [x["talker2"]["improvement"] for x in ct])
    wd = listen_decision([x["word"]["change_pp"] for x in tr], [x["word"]["change_pp"] for x in ct])
    wd["verdict"] = None   # 낱말 일반화는 판정하지 않는다(방향과 구간만)
    res["word"] = wd
    strata = {}
    for x in persons:
        k = f"{x['cohort']}:{x['first_form'] or '?'}"
        strata[k] = strata.get(k, 0) + 1
    res["strata_first_form"] = strata
    # 순차 들여다보기: 집단마다 앞 12명(사후 검사 날짜, 같은 날이면 가명 순)
    k = LISTEN["look_n_per_group"]

    def first_k(xs):
        xs = [x for x in xs if x["babble"]["improvement"] is not None]
        return sorted(xs, key=lambda x: (x["babble"]["post_on"] or "9999", x["pid"]))[:k]
    tk, ck = first_k(tr), first_k(ct)
    look = None
    if len(tk) >= k and len(ck) >= k:
        look = listen_decision([x["babble"]["improvement"] for x in tk], [x["babble"]["improvement"] for x in ck])
        look["stop"] = look["verdict"] in ("success", "fail")
    res["sequential"] = {"look_at_per_group": k, "reached": look is not None, "look": look,
                         "n_train_complete": sum(1 for x in tr if x["babble"]["improvement"] is not None),
                         "n_control_complete": sum(1 for x in ct if x["babble"]["improvement"] is not None)}
    need = LISTEN["sessions"]
    res["compliance"] = {"rule": f"훈련한 날 {need}일 이상(사전·사후 검사 사이)",
                         "train_met": sum(1 for x in tr if x["dose"]["listen_days"] >= need),
                         "control_met": sum(1 for x in ct if x["dose"]["reading_days"] >= need),
                         "n_train": len(tr), "n_control": len(ct)}
    return res


# ───────────────────────── 묶기·출력 ─────────────────────────
def analyze(export, p3_cohorts=None, listen_train=(), listen_control=(), allow_avatar=False, withdrawn=(), listen_sim="ci"):
    parts = [p for p in export.get("participants") or [] if p.get("pid") not in set(withdrawn)]
    warnings = []
    if (export.get("version") or 0) < 7:
        warnings.append(f"내보내기 판 {export.get('version')}: 판 7 이상이 필요하다(학습량·SNR 추정 방식)")
    if not any(p.get("trial_log") is not None for p in parts):
        warnings.append("trials=true로 받지 않은 내보내기다(시행 기록 없음)")
    p3_parts = [p for p in parts if not p3_cohorts or p.get("cohort") in set(p3_cohorts)]
    p3 = p3_analyze(p3_parts, allow_avatar)
    if allow_avatar and any(b.get("modality") == "avatar" for p in p3_parts for b in p.get("battery") or [] if b["layer"] == "sentence"):
        warnings.append("문장 층이 아바타 조건이다(--allow-avatar). 주결과(실제 얼굴)로 쓰지 않는다")
    warnings += p3.pop("warnings")
    ex_rows = p3["itt"]["excluded_sentence_rows"]
    if ex_rows.get("not_real_face"):
        warnings.append(f"실제 얼굴 조건이 아닌 문장 층 {ex_rows['not_real_face']}개를 주분석에서 뺐다(촬영 전 리허설 자료는 --allow-avatar)")
    if ex_rows.get("needs_rescore"):
        warnings.append(f"엄격 채점이 빈 문장 층 {ex_rows['needs_rescore']}개: scripts/pilot_battery_rescore.py로 채운 뒤 다시 돌린다")
    listen = listen_analyze(parts, list(listen_train), list(listen_control), listen_sim) if (listen_train or listen_control) else \
        {"primary": {"diff": None, "verdict": None}, "note": "--listen-train·--listen-control을 주지 않았다"}
    return {"export_version": export.get("version"), "exported_at": export.get("exported_at"), "n_participants": len(parts),
            "withdrawn": list(withdrawn), "p3": p3, "listen": listen, "warnings": warnings}


def _f(x, nd=2):
    return "-" if x is None else (f"{x:.{nd}f}" if isinstance(x, float) else str(x))


def report_md(res):
    p3, ls = res["p3"], res["listen"]
    pr = p3["primary"]
    L = [f"# 예비 파일럿 주분석 결과", "",
         f"가명 내보내기 {res['exported_at']}(판 {res['export_version']}), 참여자 {res['n_participants']}명. "
         f"계산은 `scripts/pilot_analyze.py`이고 판정 경계는 등록 전 초안이다.", ""]
    if res["warnings"]:
        L += ["주의:", *[f"- {w}" for w in res["warnings"]], ""]
    L += ["## 1. P3 독화 파일럿", "",
          "| 지표 | n | 추정(%p) | 95% 구간 | 판정 |", "|---|--:|--:|---|---|",
          f"| D = (B − A2) − (A2 − A1), 개방형 문장 음소 | {pr['n']} | {_f(pr['estimate'])} | {_f(pr['lo'])} ~ {_f(pr['hi'])} | "
          f"{VERDICT_KO[pr['verdict']]} |",
          f"| B − A2(관대한 상한) | {p3['upper_b_minus_a2']['n']} | {_f(p3['upper_b_minus_a2']['estimate'])} | "
          f"{_f(p3['upper_b_minus_a2']['lo'])} ~ {_f(p3['upper_b_minus_a2']['hi'])} | 판정 없음 |"]
    for layer, name in (("word", "실제 얼굴 낱말 4지선다"), ("nonsense", "무의미 낱말 자음")):
        s = p3["secondary"][layer]
        L.append(f"| D, {name} | {s['n']} | {_f(s['estimate'])} | {_f(s['lo'])} ~ {_f(s['hi'])} | 판정 없음 |")
    rt = p3["retention"]
    L.append(f"| R − A2(유지) | {rt['n']} | {_f(rt['mean'])} | "
             f"{(_f(rt['ci'][0]) + ' ~ ' + _f(rt['ci'][1])) if rt['ci'] else '-'} | 판정 없음 |")
    L += ["", f"순서별 인원 {pr['n_by_order']}, 자유도 {pr['df']}, 유효 인원 {_f(pr['n_eff'])}.",
          f"RCI: {('A1·A2 상관 ' + _f(p3['rci']['r_a1_a2']) + ', B − A2가 RCI 1.96 이상인 비율 ' + _f(p3['rci']['share_rci_ge_1_96'])) if p3['rci'] else '계산 불가(3명 미만 또는 분산 0)'}.",
          ""]
    sq = p3["sequential"]
    L += ["### 순차 멈춤 규칙", "",
          f"B 완료 순번이 있는 완료자 {sq['n_completers_with_seq']}명. 상태: "
          f"{ {'stopped': '멈춤', 'max_reached': '최대 인원 도달(미결)', 'continue': '계속 모집'}[sq['state']] }.", "",
          "| 들여다본 인원 | 추정(%p) | 95% 구간 | t | BF+0 | 멈춤 |", "|--:|--:|---|--:|--:|---|"]
    for lk in sq["looks"]:
        L.append(f"| {lk['n']} | {_f(lk['estimate'])} | {_f(lk['lo'])} ~ {_f(lk['hi'])} | {_f(lk['t'])} | {_f(lk['bf_plus0'], 3)} | "
                 f"{ {'support': '지지 쪽', 'null': '영가설 쪽', None: ''}[lk['stop']] } |")
    if sq["stopped"]:
        s = sq["stopped"]
        L += ["", f"멈춘 시점 {s['n']}명, BF {_f(s['bf'], 3)}, 구간 판정 {VERDICT_KO[s['verdict']]}."]
    it = p3["itt"]
    L += ["", "### ITT와 준비 상태", "",
          f"배정 {it['n_assigned']}명, 회차별 문장 층 완료 {it['sentence_completed_by_label']}, 완료자 {it['n_completers']}명.",
          f"끝내지 못한 층 {len(it['unfinished_layers'])}개, 준비 전 문항(층:사유 합) {it['missing_items']}, "
          f"문장 층 제외 사유 {it['excluded_sentence_rows']}.",
          f"SNR 계단 {p3['snr']['n']}건, 미수렴 {p3['snr']['not_converged']}, 헤드폰·볼륨 확인 빠짐 {p3['snr']['checks_missing']}.",
          "소음 속 시청각 이득 VE((AV − A) / (100 − A)): "
          + (", ".join(f"{lab} {_f(v['mean_ve'])}({v['n']}명)" for lab, v in p3["av_gain"].items()) or "-") + ".", ""]
    L += ["## 2. 소리 듣기 청인 모의 파일럿", ""]
    if "persons" in ls:
        pp, t2, wd = ls["primary"], ls["talker2"], ls["word"]
        L += ["| 지표 | 훈련 n | 대조 n | 차이(훈련 − 대조) | 95% 구간 | 판정 |", "|---|--:|--:|--:|---|---|",
              f"| 잡담 잡음 역치 개선(dB) | {pp['n_train']} | {pp['n_control']} | {_f(pp['diff'])} | "
              f"{(_f(pp['ci'][0]) + ' ~ ' + _f(pp['ci'][1])) if pp.get('ci') else '-'} | {VERDICT_KO[pp['verdict']]} |",
              f"| 두 사람 말소리 역치 개선(dB) | {t2['n_train']} | {t2['n_control']} | {_f(t2['diff'])} | "
              f"{(_f(t2['ci'][0]) + ' ~ ' + _f(t2['ci'][1])) if t2.get('ci') else '-'} | 판정 없음 |",
              f"| 낱말 일반화 정답률 변화(%p) | {wd['n_train']} | {wd['n_control']} | {_f(wd['diff'])} | "
              f"{(_f(wd['ci'][0]) + ' ~ ' + _f(wd['ci'][1])) if wd.get('ci') else '-'} | 판정 없음 |", "",
              f"모의 청취 {ls['sim']}, 첫 검사 폼 층화 {ls['strata_first_form']}.",
              f"순차 들여다보기(집단마다 {ls['sequential']['look_at_per_group']}명): "
              f"{'도달, 판정 ' + VERDICT_KO[ls['sequential']['look']['verdict']] if ls['sequential']['reached'] else '아직(완료 훈련 ' + str(ls['sequential']['n_train_complete']) + '명, 대조 ' + str(ls['sequential']['n_control_complete']) + '명)'}.",
              f"용량 준수({ls['compliance']['rule']}): 훈련 {ls['compliance']['train_met']}/{ls['compliance']['n_train']}, "
              f"대조 {ls['compliance']['control_met']}/{ls['compliance']['n_control']}.", ""]
    else:
        L += [ls.get("note", ""), ""]
    return "\n".join(L)


def write_outputs(res, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "pilot_analyze.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1, default=str)
    with open(os.path.join(out_dir, "pilot_analyze.md"), "w", encoding="utf-8") as f:
        f.write(report_md(res))


def _list(s):
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def main(argv=None):
    ap = argparse.ArgumentParser(description="예비 파일럿 주분석(P3 독화, 소리 듣기 모의 청취)")
    ap.add_argument("export")
    ap.add_argument("--out", default="pilot_analyze_out")
    ap.add_argument("--p3-cohorts", default="", help="P3에 넣을 집단(비우면 모든 참여자)")
    ap.add_argument("--listen-train", default="")
    ap.add_argument("--listen-control", default="")
    ap.add_argument("--listen-sim", default="ci", help="역치 검사의 모의 청취 조건(사전 등록: ci). 'any'면 가리지 않는다")
    ap.add_argument("--allow-avatar", action="store_true")
    ap.add_argument("--withdrawn", default="")
    a = ap.parse_args(argv)
    with open(a.export, encoding="utf-8") as f:
        ex = json.load(f)
    res = analyze(ex, _list(a.p3_cohorts), _list(a.listen_train), _list(a.listen_control), a.allow_avatar, _list(a.withdrawn),
                  None if a.listen_sim == "any" else a.listen_sim)
    write_outputs(res, a.out)
    pr = res["p3"]["primary"]
    print(f"P3 D = {_f(pr['estimate'])}%p [{_f(pr['lo'])}, {_f(pr['hi'])}] n={pr['n']} → {VERDICT_KO[pr['verdict']]}; "
          f"순차 {res['p3']['sequential']['state']}")
    lp = res["listen"]["primary"]
    print(f"소리 듣기 개선 차이 = {_f(lp.get('diff'))} dB → {VERDICT_KO[lp.get('verdict')]}")
    for w in res["warnings"]:
        print("주의:", w)
    print("결과:", os.path.abspath(a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
