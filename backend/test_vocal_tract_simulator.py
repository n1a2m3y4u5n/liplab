"""
조음 시뮬레이터 검증 테스트 — 고도화 축 E.

VocalTractLab은 결정론적 물리 시뮬레이터라(학습된 모델이 아님) 실제 라이브러리로 직접
검증한다 — 합성음이 나오는지, 서로 다른 모음이 실측 가능한 차이(스펙트럼 무게중심)를
보이는지, 이중모음 보간이 정확한지를 확인한다.

vocaltractlab-cython 미설치 환경(HAS_VTL=False)에서는 스킵한다.

실행: python3 test_vocal_tract_simulator.py
"""
import numpy as np

import vocal_tract_simulator as VTS


def _ok(cond, msg):
    assert cond, "FAIL: " + msg


def _spectral_centroid(audio: np.ndarray, sr: int) -> float:
    mag = np.abs(np.fft.rfft(audio.astype(np.float64)))
    freqs = np.fft.rfftfreq(len(audio), d=1.0 / sr)
    return float(np.sum(freqs * mag) / (np.sum(mag) + 1e-12))


def test_synthesize_produces_real_audio():
    if not VTS.HAS_VTL:
        print("  (vocaltractlab-cython 미설치 → 스킵)")
        return
    audio, sr = VTS.synthesize_viseme_sequence([1, 2, 1], frame_duration_s=0.15)
    _ok(sr == 44100, "표준 오디오 샘플레이트")
    expected_dur = 0.15 * 3
    _ok(abs(len(audio) / sr - expected_dur) < 0.05, "프레임 길이대로 오디오 길이가 나와야 함")
    rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
    _ok(rms > 0.001, f"묵음이 아닌 실제 신호여야 함(RMS={rms:.5f})")


def test_different_vowels_have_different_spectra():
    if not VTS.HAS_VTL:
        print("  (vocaltractlab-cython 미설치 → 스킵)")
        return
    # 지속 모음(같은 viseme 반복)으로 충분한 길이를 확보해 스펙트럼 무게중심을 비교.
    audio_a, sr = VTS.synthesize_viseme_sequence([2, 2], frame_duration_s=0.3)   # 개방모음 ㅏ
    audio_i, _ = VTS.synthesize_viseme_sequence([3, 3], frame_duration_s=0.3)    # 전설모음 ㅣ
    audio_u, _ = VTS.synthesize_viseme_sequence([4, 4], frame_duration_s=0.3)    # 원순모음 ㅜ

    c_a = _spectral_centroid(audio_a, sr)
    c_i = _spectral_centroid(audio_i, sr)
    c_u = _spectral_centroid(audio_u, sr)
    _ok(c_a != c_i != c_u, "서로 다른 조음 위치는 다른 스펙트럼 무게중심을 가져야 함")
    _ok(abs(c_i - c_a) > 50, f"ㅣ(전설, 고주파 성분 큼)와 ㅏ(개방)는 뚜렷이 달라야 함 (Δ={abs(c_i-c_a):.1f}Hz)")


def test_diphthong_is_midpoint_of_open_and_rounded():
    if not VTS.HAS_VTL:
        print("  (vocaltractlab-cython 미설치 → 스킵)")
        return
    shape_open = VTS.shape_for_viseme(2)
    shape_round = VTS.shape_for_viseme(4)
    shape_diph = VTS.shape_for_viseme(9)
    expected = (shape_open + shape_round) / 2.0
    _ok(np.allclose(shape_diph, expected), "이중모음(9)은 개방(2)·원순(4)의 정확한 평균이어야 함")


def test_invalid_viseme_raises():
    if not VTS.HAS_VTL:
        print("  (vocaltractlab-cython 미설치 → 스킵)")
        return
    for bad in (11, 12, 13, 14, 15, 0, -1):
        try:
            VTS.shape_for_viseme(bad)
            _ok(False, f"viseme {bad}는 조음 시뮬레이터 대상이 아니므로 ValueError여야 함")
        except ValueError:
            pass


def test_empty_sequence_raises():
    if not VTS.HAS_VTL:
        print("  (vocaltractlab-cython 미설치 → 스킵)")
        return
    try:
        VTS.synthesize_viseme_sequence([])
        _ok(False, "빈 시퀀스는 ValueError여야 함")
    except ValueError:
        pass


def test_outline_svg_returns_valid_svg():
    if not VTS.HAS_VTL:
        print("  (vocaltractlab-cython 미설치 → 스킵)")
        return
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "shape.svg")
        svg = VTS.outline_svg(2, path)
        _ok(svg.strip().startswith("<?xml") or "<svg" in svg[:100], "SVG 문서로 시작해야 함")
        _ok(os.path.exists(path), "SVG 파일이 실제로 생성돼야 함")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n{len(tests)}개 테스트 통과")
