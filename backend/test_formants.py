"""축 E 모음 포먼트 교정(formants.py) 테스트 — 알려진 포먼트로 합성한 모음으로 추정·방향을 검증."""
import numpy as np

import formants as F


def _vowel(f1, f2, f3, f0=120.0, dur=0.5, sr=F.SR):
    """성문 펄스열 → 2차 공명기 3개 직렬(소스-필터)로 만든 합성 모음."""
    n = int(dur * sr)
    x = np.zeros(n)
    x[::int(sr / f0)] = 1.0
    for fc, bw in ((f1, 80), (f2, 100), (f3, 150)):
        r = np.exp(-np.pi * bw / sr)
        c1, c2 = 2 * r * np.cos(2 * np.pi * fc / sr), -r * r
        y = np.zeros(n)
        for i in range(n):
            y[i] = x[i] + c1 * (y[i - 1] if i >= 1 else 0.0) + c2 * (y[i - 2] if i >= 2 else 0.0)
        x = y
    return (x / np.max(np.abs(x))).astype(np.float32)


def test_target_vowel():
    assert F.target_vowel("아") == "ㅏ" and F.target_vowel("이") == "ㅣ"
    assert F.target_vowel("가") is None and F.target_vowel("안") is None and F.target_vowel("아이") is None


def test_estimates_known_formants():
    est = F.estimate_formants(_vowel(700, 1200, 2500))
    assert est is not None
    assert abs(est["f1"] - 700) / 700 < 0.12 and abs(est["f2"] - 1200) / 1200 < 0.12


def test_direction_messages():
    # 목표 ㅣ(300, 2300)인데 ㅏ처럼 말함 → 혀가 낮고(F1 높음) 뒤에 있음(F2 낮음)
    fb = F.vowel_feedback(_vowel(780, 1300, 2500), "ㅣ")
    assert fb["height"] == "raise" and fb["front"] == "forward"
    # 목표에 맞게 말하면 ok
    ok = F.vowel_feedback(_vowel(300, 2300, 2500), "ㅣ")
    assert ok["height"] == "ok" and ok["front"] == "ok"


def test_speaker_scale_for_higher_voice():
    # 성도가 짧아 전 포먼트가 1.2배 높은 화자가 ㅏ를 정확히 말한 경우 → 정규화 후 ok
    fb = F.vowel_feedback(_vowel(780 * 1.2, 1300 * 1.2, 2500 * 1.2, f0=220), "ㅏ")
    assert fb["speaker_scale"] > 1.1 and fb["height"] == "ok" and fb["front"] == "ok"
