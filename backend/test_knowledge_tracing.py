"""
지식추적(Knowledge Tracing) 검증 테스트 — 고도화 축 G 개인화.

학습 로그에서 음소별 숙달도 추정과 표적 음소 선정이 의도대로 동작하는지 확인한다.
now를 주입하므로 결정론적이다. 외부 의존성 없음.

실행: python3 test_knowledge_tracing.py
"""
from datetime import datetime, timedelta

import knowledge_tracing as KT

NOW = datetime(2026, 9, 3, 12, 0, 0)


def _ok(cond, msg):
    assert cond, "FAIL: " + msg


def test_mastery_ordering():
    recs = [
        {"viseme_id": 1, "error_count": 8, "total_attempts": 10, "last_error_at": NOW - timedelta(days=1)},
        {"viseme_id": 2, "error_count": 0, "total_attempts": 12, "last_error_at": None},
    ]
    m = KT.estimate_mastery(recs, now=NOW)
    _ok(m[1] < 0.4, "자주 틀린 음소는 숙달도 낮음")
    _ok(m[2] > 0.8, "안 틀린 음소는 숙달도 높음")
    _ok(m[1] < m[2], "정답률 순서가 유지돼야")


def test_empty_and_unseen():
    _ok(KT.estimate_mastery([], now=NOW) == {}, "기록 없으면 빈 dict")
    # 학습 대상 아닌 viseme(11~15)은 제외
    m = KT.estimate_mastery([{"viseme_id": 14, "error_count": 1, "total_attempts": 2, "last_error_at": None}], now=NOW)
    _ok(m == {}, "전환·휴지 viseme은 추적 대상 아님")


def test_recency_penalty():
    recent = [{"viseme_id": 6, "error_count": 3, "total_attempts": 10, "last_error_at": NOW - timedelta(days=1)}]
    old = [{"viseme_id": 6, "error_count": 3, "total_attempts": 10, "last_error_at": NOW - timedelta(days=60)}]
    m_recent = KT.estimate_mastery(recent, now=NOW)[6]
    m_old = KT.estimate_mastery(old, now=NOW)[6]
    _ok(m_recent < m_old, "최근에 틀린 음소가 더 낮게 추정돼야(감쇠)")


def test_targets_and_level():
    recs = [
        {"viseme_id": 1, "error_count": 9, "total_attempts": 10, "last_error_at": NOW - timedelta(days=1)},
        {"viseme_id": 2, "error_count": 0, "total_attempts": 10, "last_error_at": None},
    ]
    rec = KT.recommend(recs, k=2, now=NOW)
    _ok(1 in rec["target_visemes"], "가장 약한 음소가 표적")
    _ok(1 <= rec["level"] <= 5, "난이도는 1~5")
    # 기록 없는 유저는 아직 안 배운 음소를 표적으로
    rec0 = KT.recommend([], now=NOW)
    _ok(len(rec0["target_visemes"]) > 0 and rec0["level"] == 1, "미학습 유저 기본 표적·난이도 1")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n{len(tests)}개 테스트 통과")


def test_rank_weak_prefers_high_error_rate_over_high_error_count():
    # 자주 나오는 모음(2): 200번 중 30번 틀림(15%). 드문 ㅎ(8): 10번 중 6번 틀림(60%).
    # 예전(오류 횟수 순)은 모음이 위였고, 상위 5개를 자르면 ㅎ이 빠지기도 했다
    recs = [{"viseme_id": 2, "error_count": 30, "total_attempts": 200, "last_error_at": None},
            {"viseme_id": 8, "error_count": 6, "total_attempts": 10, "last_error_at": None},
            {"viseme_id": 6, "error_count": 25, "total_attempts": 190, "last_error_at": None}]
    r = KT.rank_weak(recs, k=5, now=NOW)
    _ok([x["viseme_id"] for x in r][0] == 8, f"오답률 높은 ㅎ이 먼저: {r}")
    _ok(r[0]["attempts"] == 10 and abs(r[0]["error_rate"] - 0.6) < 1e-9, "시도 수·오답률을 함께 준다")
    # 표본이 작으면 0.5 쪽으로 당긴다: 3번 중 2번(67%)보다 20번 중 13번(65%)이 더 약하다고 본다
    r2 = KT.rank_weak([{"viseme_id": 10, "error_count": 2, "total_attempts": 3, "last_error_at": None},
                       {"viseme_id": 8, "error_count": 13, "total_attempts": 20, "last_error_at": None}], k=5, now=NOW)
    _ok([x["viseme_id"] for x in r2] == [8, 10], f"표본이 작은 입모양은 덜 믿는다: {r2}")
    _ok(KT.rank_weak([], now=NOW) == [], "기록이 없으면 빈 목록")
