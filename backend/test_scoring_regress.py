"""채점 회귀 점검(O4, scoring_regress.py). 대표 입력의 출력이 기준 파일(scoring_regress_golden.json)과 같은지, 규칙 문서에 적힌
고정 기대(PINNED)를 지키는지 본다. 실패하면 사람이 읽는 차이 보고가 메시지로 나온다.

의도한 변경이면 `scripts/scoring_regress.py --update`로 기준을 다시 쓰고, 보고(--report)를 커밋 설명에 남긴다.
"""
import pytest

import scoring_regress as R


@pytest.fixture(scope="module")
def current():
    return R.compute()


def test_pinned_rules_hold(current):
    bad = R.check_pinned(current)
    assert not bad, "고정 기대 위반:\n" + "\n".join(bad)


def test_outputs_match_golden(current):
    golden = R.load_golden()
    d = R.diff(golden["cases"], current)
    changed = any(x["changed"] or x["added"] or x["removed"] for x in d.values())
    assert not changed, "\n" + R.format_report(d, [], golden.get("meta"), max_rows=120)


def test_golden_covers_every_layer():
    golden = R.load_golden()
    assert set(golden["cases"]) == set(R.LAYERS)
    assert all(len(golden["cases"][k]) >= 20 for k in R.LAYERS)


def test_report_marks_verdict_changes():
    # 보고 형식 자체의 검사: 합격이 뒤집힌 사례는 '판정'으로, 점수 차는 부호와 함께 보인다
    old = {"speak": {"사례": {"score": 65.0, "passed": True}}}
    new = {"speak": {"사례": {"score": 64.9, "passed": False}, "새것": {"x": 1}}}
    rep = R.format_report(R.diff(old, new), [])
    assert "판정 passed: True → False" in rep
    assert "score: 65 → 64.9 (-0.1)" in rep
    assert "새 사례: 새것" in rep
