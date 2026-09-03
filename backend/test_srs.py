"""
SM-2 경량 간격반복 스케줄러 검증. 순수 함수라 외부 의존성 없음.
실행: python3 test_srs.py
"""
import srs


def _ok(cond, msg):
    assert cond, "FAIL: " + msg


def test_quality_mapping():
    _ok(srs.quality_from_score(100) == 5, "만점=5")
    _ok(srs.quality_from_score(60) == 3, "60=경계 성공 3")
    _ok(srs.quality_from_score(59) == 2, "59=실패(<3)")
    _ok(srs.quality_from_correct(True) == 4 and srs.quality_from_correct(False) == 1, "이진 4/1")


def test_success_growth():
    # 첫 성공 → 1일, 둘째 → 6일, 셋째부터 ×ease로 늘어남
    a = srs.schedule(quality=4)                      # 신규 첫 성공
    _ok(a["interval_days"] == 1 and a["repetitions"] == 1, "첫 성공은 1일")
    b = srs.schedule(quality=4, ease_factor=a["ease_factor"],
                     interval_days=a["interval_days"], repetitions=a["repetitions"])
    _ok(b["interval_days"] == 6, "둘째 성공은 6일")
    c = srs.schedule(quality=4, ease_factor=b["ease_factor"],
                     interval_days=b["interval_days"], repetitions=b["repetitions"])
    _ok(c["interval_days"] > 6, "셋째부터 6일보다 길어짐")


def test_lapse_resets_and_lowers_ease():
    good = srs.schedule(quality=5, ease_factor=2.5, interval_days=20, repetitions=4)
    bad = srs.schedule(quality=1, ease_factor=good["ease_factor"],
                       interval_days=good["interval_days"], repetitions=good["repetitions"])
    _ok(bad["interval_days"] == 1, "실패하면 내일로 리셋")
    _ok(bad["repetitions"] == 0, "실패하면 반복 카운트 0")
    _ok(bad["lapses"] == 1, "누수(lapse) 누적")
    _ok(bad["ease_factor"] < good["ease_factor"], "실패하면 ease 감소")


def test_ease_floor():
    ef = 1.35
    for _ in range(5):
        ef = srs.schedule(quality=0, ease_factor=ef)["ease_factor"]
    _ok(ef >= srs.EF_MIN, "ease는 하한 밑으로 내려가지 않음")


def test_harder_item_shorter_interval():
    # 낮은 ease(어려운 항목)는 같은 반복이어도 다음 간격이 더 짧다
    easy = srs.schedule(quality=4, ease_factor=2.6, interval_days=10, repetitions=3)
    hard = srs.schedule(quality=4, ease_factor=1.4, interval_days=10, repetitions=3)
    _ok(hard["interval_days"] < easy["interval_days"], "어려운 항목이 더 촘촘히 복습됨")


def test_graduation_flag():
    g = srs.schedule(quality=5, ease_factor=2.5, interval_days=40, repetitions=6)
    _ok(g["interval_days"] >= srs.GRADUATE_INTERVAL and g["graduated"], "충분히 길어지면 졸업 플래그")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n{len(tests)}개 테스트 통과")
