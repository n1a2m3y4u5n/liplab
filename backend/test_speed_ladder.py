"""빠른 말 속도 단계(speed_ladder)."""
import speed_ladder as sl


def test_not_mastered_has_no_fast():
    assert sl.unlocked(False, [(2.0, True)] * 40) == 0


def test_mastered_opens_first_level_then_climbs_by_recent_accuracy():
    assert sl.unlocked(True, []) == 1
    assert sl.unlocked(True, [(1.25, True)] * 11) == 1                     # 12문항 미만
    assert sl.unlocked(True, [(1.25, True)] * 10 + [(1.25, False)] * 2) == 2  # 10/12
    assert sl.unlocked(True, [(1.25, True)] * 9 + [(1.25, False)] * 3) == 1   # 9/12
    assert sl.unlocked(True, [(1.6, True)] * 12) == 3                        # 1.6배 기록은 1.25배 조건도 채운다
    assert sl.unlocked(True, [(1.6, True)] * 12 + [(2.0, False)] * 0) == 3


def test_only_recent_window_counts_and_rounding_tolerance():
    recent = [(1.25, False)] * 3 + [(1.25, True)] * 20        # 최신 12개 중 9개 정답
    assert sl.unlocked(True, recent) == 1
    assert sl.unlocked(True, [(1.23, True)] * 12) == 2        # 반올림 여유
    assert sl.unlocked(True, [(1.0, True)] * 30) == 1          # 1.0배 기록은 다음 단계에 안 센다
