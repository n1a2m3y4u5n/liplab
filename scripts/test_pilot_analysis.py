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
