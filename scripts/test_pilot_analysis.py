"""scripts/pilot_analysis.py 검사 — 분석 규칙(protocol.md 6.1)과 통계 값(KR-20, 신뢰구간, 효과크기)을 손으로 계산한 값과 맞춘다.
실행: python -m pytest scripts/test_pilot_analysis.py
"""
import importlib.util
import json
import os
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("pilot_analysis", os.path.join(_HERE, "pilot_analysis.py"))
PA = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(PA)


def _form(form, n_correct, version="v1", date="2026-10-01"):
    items = [{"id": f"{form}{i:02d}", "correct": i < n_correct, "chosen": None if i < n_correct else "오답"}
             for i in range(24)]
    return {"form": form, "form_version": version, "accuracy": n_correct / 24, "level": None, "date": date,
            "after_join": True, "items": items}


def _p(pid, cohort, *tests, days=5):
    return {"pid": pid, "cohort": cohort, "track": "perception", "joined_on": "2026-10-01", "tests": list(tests),
            "trials_by_stage": {}, "speak": {"n": 0, "mean_score": None}, "active_days": days,
            "since_join": {"trials_by_stage": {"1": {"n": 10, "correct": 7}}, "speak": {"n": 2, "mean_score": 60.0},
                           "active_days": days}}


EXPORT = {"version": 2, "exported_at": "2026-11-01T00:00:00Z", "tz_offset_min": -540, "participants": [
    _p("p1", "L", _form("A", 10), _form("B", 16)),
    _p("p2", "L", _form("A", 12), _form("B", 15)),
    _p("p3", "L", _form("A", 8), _form("B", 14), days=2),
    _p("p4", "C", _form("A", 14), _form("B", 15)),
    _p("p5", "C", _form("A", 16), _form("B", 16)),
    _p("p6", "C", _form("A", 13)),                                         # 사후 없음
    _p("p7", "L", _form("B", 12), _form("A", 14)),                         # 순서가 계획과 다름
    _p("p8", "L", _form("A", 12), _form("B", 13, version="v2")),           # 판본 다름
    _p("p9", "L", _form("A", 11), _form("A", 12), _form("B", 13)),         # A를 다시 풂 → 첫 A만
    _p("p10", "L", _form("A", 5), _form("B", 20)),                         # 철회
    _p("p11", "L", {"form": "placement", "accuracy": 0.5, "date": "2026-10-01", "items": None}),
]}


def test_stat_helpers_match_hand_values():
    assert abs(PA.t_crit(3) - 3.182) < 1e-3 and abs(PA.t_crit(10) - 2.228) < 1e-3 and abs(PA.t_crit(30) - 2.042) < 1e-3
    assert abs(PA.kr20([[1, 1, 0], [1, 0, 0], [1, 1, 1], [0, 0, 0]]) - 0.75) < 1e-12
    es = PA.effect_sizes([10, 12, 8, 11], [16, 15, 14, 13])
    assert abs(es["d_av"] - 2.834) < 1e-3 and abs(es["g_av"] - 2.061) < 1e-3


def test_selection_rules_and_group_numbers():
    res = PA.analyze(EXPORT, learning=["L"], control=["C"], withdrawn=["p10"], min_active_days=3)
    assert res["n_withdrawn_excluded"] == 1 and res["n_analyzed"] == 6
    assert res["excluded"]["C"] == {"no_post": 1}
    assert res["excluded"]["L"] == {"order": 1, "version": 1, "repeat_records": 1, "no_form_test": 1}
    L = res["groups"]["L"]
    assert L["n"] == 4 and abs(L["change"]["mean"] - 4.25) < 1e-12
    lo, hi = L["change_ci95"]
    assert abs(lo - 0.970) < 1e-2 and abs(hi - 7.530) < 1e-2
    cmp = res["comparisons"]["learning_minus_control_change"]
    assert abs(cmp["diff"] - 3.75) < 1e-12 and cmp["ci95"][0] < 3.75 < cmp["ci95"][1]
    assert res["completers"]["n"] == 5            # 학습한 날 2일인 p3만 빠진다
    assert res["items"]["A"]["k"] == 24 and res["items"]["A"]["n_complete"] == 6


def test_counterbalanced_keeps_b_first_and_writes_outputs():
    res = PA.analyze(EXPORT, learning=["L"], counterbalanced=True, withdrawn=["p10"])
    assert "order" not in res["excluded"].get("L", {})
    p7 = next(r for r in res["rows"] if r["pid"] == "p7")
    assert p7["order"] == "B→A" and p7["change"] == 2
    assert "form_A_minus_B_mean_correct" in res["comparisons"]
    with tempfile.TemporaryDirectory() as d:
        PA.write_outputs(res, d)
        md = open(os.path.join(d, "report.md"), encoding="utf-8").read()
        assert "파일럿 분석 결과" in md and "역균형" in md
        assert len(open(os.path.join(d, "participants.csv"), encoding="utf-8").read().splitlines()) == len(res["rows"]) + 1
        json.load(open(os.path.join(d, "results.json"), encoding="utf-8"))


def _post_with_talkers(form, face_right, new_right, version="v1"):
    """사후 검사: 앞 12문항은 기본 얼굴, 뒤 12문항은 새 가상 화자(h1·h2 번갈아)."""
    items = [{"id": f"{form}{i:02d}", "correct": i < face_right, "chosen": None, "talker": "default"} for i in range(12)]
    items += [{"id": f"{form}{i:02d}", "correct": i - 12 < new_right, "chosen": None, "talker": ("h1", "h2")[i % 2]}
              for i in range(12, 24)]
    c = sum(i["correct"] for i in items)
    return {"form": form, "form_version": version, "accuracy": c / 24, "level": None, "date": "2026-10-20",
            "after_join": True, "items": items}


def test_default_face_primary_score_and_talker_reported_separately():
    exp = {"version": 4, "exported_at": "x", "participants": [
        _p("t1", "L", {**_form("A", 12), "trials_before": 0}, _post_with_talkers("B", 9, 3)),
        _p("t2", "L", {**_form("A", 10), "trials_before": 35}, _post_with_talkers("B", 6, 6)),
    ]}
    res = PA.analyze(exp, learning=["L"])
    r1 = next(r for r in res["rows"] if r["pid"] == "t1")
    # 기본 얼굴 9/12 → 24문항 환산 18. 예전처럼 24문항을 모두 세면 12(새 화자 3개만 맞힘)라 변화가 0으로 보였다
    assert r1["post"] == 18 and r1["change"] == 6 and r1["post_n_default"] == 12
    assert abs(r1["talker_gap"] - (3 / 12 - 9 / 12)) < 1e-12
    tc = res["talker_condition"]["all"]
    assert tc["n"] == 2 and abs(tc["gap"]["mean"] - (-0.25)) < 1e-12
    pt = res["pretest_training"]
    assert pt["n_flagged"] == 1 and pt["flagged_pids"] == ["t2"] and pt["without_flagged"]["L"]["n"] == 1
    assert r1["pre_after_training"] is False
    md = PA.report_md(res)
    assert "새 가상 화자 조건" in md and "민감도 분석" in md and "24문항으로 환산" in md
    # 판 4 이전(trials_before 없음)은 표시할 수 없어 '기록 없음'으로 센다
    assert PA.analyze(EXPORT, learning=["L"], withdrawn=["p10"])["pretest_training"]["n_unknown"] == 6


def test_null_simulation_default_face_score_is_unbiased():
    """학습 효과 없음에서 새 가상 화자 문항 정답률이 10%p 낮을 때: 기본 얼굴 점수의 평균 변화 |편향| ≤ 2%p, 예전(24문항 전부)은 음수."""
    import math
    import random
    import sys
    sys.path.insert(0, os.path.join(_HERE, "..", "backend"))
    sys.dont_write_bytecode = True
    import assessment as A
    F = A.frozen_forms(build_if_missing=False)
    rng = random.Random(7)

    def p_ok(t, d):
        return 0.25 + 0.75 / (1 + math.exp(-A._EAP_SLOPE * (t - d)))
    parts = []
    for u in range(1200):
        theta = rng.uniform(0.3, 0.9)
        pre = [{"id": it["id"], "correct": rng.random() < p_ok(theta, it["difficulty"])} for it in F["A"]]
        post = [{"id": it["id"], "talker": it["talker"],
                 "correct": rng.random() < p_ok(theta, it["difficulty"]) - (0.10 if it["talker"] != "default" else 0)}
                for it in A.assign_talker_conditions(F["B"], u)]
        parts.append(_p(f"s{u}", "N", {"form": "A", "form_version": "v2", "items": pre},
                        {"form": "B", "form_version": "v2", "items": post}))
    res = PA.analyze({"version": 4, "participants": parts})
    ch = [r["change"] / PA.FORM_LENGTH * 100 for r in res["rows"]]
    assert abs(sum(ch) / len(ch)) <= 2.0
    old = [(sum(i["correct"] for i in p["tests"][1]["items"]) - sum(i["correct"] for i in p["tests"][0]["items"]))
           / 24 * 100 for p in parts]
    assert sum(old) / len(old) < -4.0
