"""말하기 판정 보류(S9): 낱말·문장 단계에서 합격선 ± 1 SEM(7.5) 안이면 보류."""
from main import speak_hold


def test_hold_band_around_pass_line():
    assert speak_hold(65, 65, "sentence", True) is True
    assert speak_hold(57.6, 65, "word", False) is True
    assert speak_hold(72.4, 65, "sentence", True) is True
    assert speak_hold(57.5, 65, "sentence", False) is False   # 경계 밖(엄격 부등호)
    assert speak_hold(80, 65, "sentence", True) is False


def test_hold_not_for_phoneme_metric_or_probe():
    assert speak_hold(50, 50, "phoneme", True) is False   # SEM은 문장 점수로 잰 값이라 음절 단계에는 쓰지 않는다
    assert speak_hold(65, 65, "voicing", True) is False
    assert speak_hold(65, 65, "sentence", True, is_probe=True) is False
    assert speak_hold(65, None, "sentence", True) is False
