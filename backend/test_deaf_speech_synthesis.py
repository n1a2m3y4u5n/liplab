"""
농인 발화 근사 합성 검증 테스트 — 고도화 축 A.

실제 음성 없이 합성 신호(사인파·백색잡음)로 각 교란 함수의 '측정 가능한 효과'만
결정론적으로 검증한다(소리가 실제로 자연스러운지는 사람이 들어야 하는 영역이라
범위 밖 — scripts/check_ml_env.py처럼 모델이 필요한 것도 아니라 여기서는 전부 유닛테스트).

librosa/scipy 미설치 환경(HAS_SYNTHESIS=False)에서는 스킵한다.

실행: python3 test_deaf_speech_synthesis.py
"""
import numpy as np

import deaf_speech_synthesis as S


def _ok(cond, msg):
    assert cond, "FAIL: " + msg


SR = 16000


def _tone(freq_hz: float, duration_s: float = 1.0, sr: int = SR) -> np.ndarray:
    t = np.linspace(0, duration_s, int(sr * duration_s), endpoint=False)
    return np.sin(2 * np.pi * freq_hz * t).astype(np.float32)


def _band_energy(y: np.ndarray, sr: int, lo_hz: float, hi_hz: float) -> float:
    spec = np.abs(np.fft.rfft(y))
    freqs = np.fft.rfftfreq(len(y), d=1.0 / sr)
    band = (freqs >= lo_hz) & (freqs <= hi_hz)
    return float(np.sum(spec[band] ** 2))


def test_time_stretch_changes_duration():
    if not S.HAS_SYNTHESIS:
        print("  (librosa 미설치 → 스킵)")
        return
    y = _tone(220, duration_s=1.0)
    faster = S.time_stretch(y, rate=2.0)
    slower = S.time_stretch(y, rate=0.5)
    _ok(abs(len(faster) - len(y) / 2) < SR * 0.05, "rate=2.0이면 길이가 절반 근처")
    _ok(abs(len(slower) - len(y) * 2) < SR * 0.1, "rate=0.5이면 길이가 두 배 근처")


def test_lowpass_removes_high_frequency_energy():
    if not S.HAS_SYNTHESIS:
        print("  (scipy 미설치 → 스킵)")
        return
    # 저역(300Hz)과 고역(6000Hz) 성분을 섞은 신호에 2000Hz 저역통과를 걸면
    # 고역 에너지만 크게 줄고 저역은 거의 보존돼야 한다.
    y = _tone(300) + _tone(6000)
    filtered = S.lowpass(y, SR, cutoff_hz=2000)
    low_before = _band_energy(y, SR, 100, 500)
    low_after = _band_energy(filtered, SR, 100, 500)
    high_before = _band_energy(y, SR, 5000, 7000)
    high_after = _band_energy(filtered, SR, 5000, 7000)
    _ok(low_after > low_before * 0.8, "저역 에너지는 대부분 보존")
    _ok(high_after < high_before * 0.01, "고역 에너지는 거의 제거")


def test_add_noise_hits_target_snr():
    if not S.HAS_SYNTHESIS:
        print("  (numpy만 필요 → 계속 진행)")
    y = _tone(440, duration_s=1.0)
    rng = np.random.default_rng(42)
    noisy = S.add_noise(y, snr_db=10.0, rng=rng)
    noise_component = noisy - y
    signal_power = float(np.mean(y.astype(np.float64) ** 2))
    noise_power = float(np.mean(noise_component.astype(np.float64) ** 2))
    achieved_snr_db = 10.0 * np.log10(signal_power / noise_power)
    _ok(abs(achieved_snr_db - 10.0) < 0.5, f"목표 SNR 10dB 근접해야 함 (실측 {achieved_snr_db:.2f}dB)")


def test_add_noise_deterministic_with_seed():
    y = _tone(440)
    a = S.add_noise(y, snr_db=15.0, rng=np.random.default_rng(7))
    b = S.add_noise(y, snr_db=15.0, rng=np.random.default_rng(7))
    _ok(np.allclose(a, b), "같은 시드면 같은 잡음(결정론적)")


def test_severity_levels_monotonically_degrade_config():
    levels = [S.SEVERITY_LEVELS[i] for i in range(5)]
    cutoffs = [lv["cutoff_hz"] for lv in levels]
    snrs = [lv["snr_db"] for lv in levels]
    _ok(all(cutoffs[i] > cutoffs[i + 1] for i in range(4)), "강도가 오를수록 저역통과 컷오프는 낮아짐(고주파 손실↑)")
    _ok(all(snrs[i] > snrs[i + 1] for i in range(4)), "강도가 오를수록 SNR은 낮아짐(잡음↑)")


def test_simulate_deaf_speech_higher_severity_loses_more_high_freq():
    if not S.HAS_SYNTHESIS:
        print("  (librosa/scipy 미설치 → 스킵)")
        return
    y = _tone(300) + _tone(5500)
    mild = S.simulate_deaf_speech(y, SR, severity=1, rng=np.random.default_rng(1))
    severe = S.simulate_deaf_speech(y, SR, severity=4, rng=np.random.default_rng(1))
    high_mild = _band_energy(mild, SR, 5000, 6000)
    high_severe = _band_energy(severe, SR, 5000, 6000)
    _ok(high_severe < high_mild, "강도 4가 강도 1보다 고주파 성분을 더 많이 잃어야 함")
    _ok(len(mild) == len(y) and len(severe) == len(y), "포먼트 이동 후에도 원본 길이로 복원되어야 함")


def test_simulate_deaf_speech_rejects_invalid_severity():
    try:
        S.simulate_deaf_speech(_tone(200), SR, severity=9)
        _ok(False, "범위 밖 severity는 ValueError여야 함")
    except ValueError:
        pass


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n{len(tests)}개 테스트 통과")
