"""1·2단계 숙달 점수: 편향 보정 지수 이동 평균(docs/mastery-ewma.md)의 성질."""
import os

os.environ.setdefault("JWT_SECRET", "test-only-mastery-secret")
import main   # noqa: E402


def run(seq):
    e = 0.0
    for i, c in enumerate(seq):
        e = main._ewma_mastery(e, i, c)
    return e


def test_perfect_start_reaches_threshold_at_minimum():
    # 처음부터 잘하는 학습자는 예전(누적)처럼 최소 시도에서 숙달 문턱에 닿는다
    assert run([True] * main._STAGE1_MIN_ATTEMPTS) >= main._STAGE1_MASTERY
    assert run([True] * main._STAGE2_MIN_ATTEMPTS) >= main._STAGE2_MASTERY


def test_recent_answers_weigh_more_than_early_failures():
    seq = [False] * 10 + [True] * 12
    assert run(seq) > 100 * 12 / 22 + 15   # 누적(54.5)보다 최근 성적(정답 연속)을 더 반영


def test_direction_of_updates():
    base = run([True, False, True, True])
    assert main._ewma_mastery(base, 4, True) > base > main._ewma_mastery(base, 4, False)


def test_bounded():
    assert 0.0 <= run([False] * 30) <= 100.0 and 0.0 <= run([True] * 30) <= 100.0
