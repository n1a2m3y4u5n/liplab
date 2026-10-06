"""지연 유지 검사 예약(retention.py, C7)과 레슨별 정신적 노력(mental_effort.py, C14)의 순수 함수."""
from datetime import date
from types import SimpleNamespace as NS

import mental_effort as me
import retention as ret


def test_retention_days_default_and_clamp():
    assert ret.retention_days(None) == 28 and ret.retention_days("") == 28
    assert ret.retention_days("21") == 21
    assert ret.retention_days("3") == 14 and ret.retention_days("60") == 28
    assert ret.retention_days("abc") == 28


def _r(i, form, ver="v2"):
    return NS(id=i, form=form, form_version=ver)


def test_post_test_is_first_other_form_of_same_version():
    rows = [_r(1, "placement"), _r(2, "A"), _r(3, "A"), _r(4, "B"), _r(5, "B")]
    pp = ret.post_test(rows)
    assert pp["pre"].id == 2 and pp["post"].id == 4      # 다시 본 B(5)가 아니라 처음 본 B
    assert ret.post_test([_r(1, "B"), _r(2, "A")])["post"].id == 2   # 역균형(B 먼저)
    assert ret.post_test([_r(1, "A"), _r(2, "B", "v1"), _r(3, "B")])["post"].id == 3   # 같은 판본 먼저
    assert ret.post_test([_r(1, "A"), _r(2, "B", "v1")])["post"].id == 2
    assert ret.post_test([_r(1, "A"), _r(2, "placement")]) is None


def test_retention_status_states():
    post = date(2026, 9, 1)
    assert ret.status(None, None, date(2026, 10, 6))["state"] == "none"
    w = ret.status(post, None, date(2026, 9, 20), 28)
    assert w["state"] == "waiting" and w["days_left"] == 9 and w["due_on"] == "2026-09-29"
    assert ret.status(post, None, date(2026, 9, 29), 28)["state"] == "due"
    assert ret.status(post, None, date(2026, 10, 6), 14)["state"] == "due"
    d = ret.status(post, date(2026, 10, 1), date(2026, 10, 6), 28)
    assert d["state"] == "done" and d["done_on"] == "2026-10-01"


def test_retention_summary():
    s = ret.summary([{"post_accuracy": 0.8, "retention_accuracy": 0.7, "days_after_post": 28},
                     {"post_accuracy": 0.6, "retention_accuracy": 0.6, "days_after_post": 30},
                     {"post_accuracy": None, "retention_accuracy": 0.5}])
    assert s["learners"] == 2 and s["mean_change"] == -0.05 and s["days"] == [28, 30]
    assert ret.summary([])["learners"] == 0


def test_clean_rating_only_accepts_1_to_9_integers():
    assert me.clean_rating(1) == 1 and me.clean_rating(9) == 9 and me.clean_rating("5") == 5
    for bad in (0, 10, -1, 3.5, "x", None, True):
        assert me.clean_rating(bad) is None


def test_response_merge_order():
    assert me.clean_response(None, 5) == "answered"
    assert me.clean_response("left", None) == "left"
    assert me.clean_response("whatever", None) == "skipped"
    assert me.merge(None, "left")
    assert me.merge("left", "answered") and me.merge("skipped", "answered") and me.merge("answered", "answered")
    assert not me.merge("answered", "left") and not me.merge("answered", "skipped") and not me.merge("skipped", "left")


def test_report_response_rate_and_by_stage():
    rows = ([{"stage": 1, "response": "answered", "rating": r} for r in (3, 5, 7, 8)]
            + [{"stage": 1, "response": "skipped", "rating": None}]
            + [{"stage": 2, "response": "answered", "rating": 4}, {"stage": 2, "response": "left", "rating": None}]
            + [{"stage": None, "lesson_kind": "review", "response": "answered", "rating": 2}])
    rep = me.report(rows)
    assert rep["sessions"] == 8 and rep["answered"] == 6
    assert rep["response_rate"] == 0.75 and rep["meets_target"] is False
    s1 = rep["by_stage"]["1"]
    assert s1["answered"] == 4 and s1["mean"] == 5.75 and s1["high_share"] == 0.5 and s1["response_rate"] == 0.8
    assert rep["by_stage"]["2"]["answered"] == 1 and rep["by_stage"]["2"]["sessions"] == 2
    assert rep["by_stage"]["review"]["mean"] == 2
    assert me.report([])["response_rate"] is None
