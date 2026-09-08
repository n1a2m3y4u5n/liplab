"""
hf_audio 변환 검증 — datasets 버전 간 오디오 형식 차이를 흡수하는지.

datasets 5.x는 AudioDecoder 객체를, 그 이전은 {"array", "sampling_rate"} 딕셔너리를
돌려준다. 실제 datasets 없이도 두 형식을 흉내내 결정론적으로 검증한다.

실행: PYTHONPATH=. python3 test_hf_audio.py
"""
import numpy as np

import hf_audio as A


def _ok(cond, msg):
    assert cond, "FAIL: " + msg


class _FakeSamples:
    def __init__(self, data, sr):
        self.data, self.sample_rate = data, sr


class _FakeDecoder:
    """torchcodec AudioDecoder 흉내 — (채널, 샘플) 텐서를 돌려준다."""
    def __init__(self, arr, sr=16000):
        self._arr, self._sr = arr, sr

    def get_all_samples(self):
        class _T:
            def __init__(self, a): self._a = a
            def numpy(self): return self._a
        return _FakeSamples(_T(self._arr), self._sr)


def test_audiodecoder_form():
    wave = np.random.default_rng(0).standard_normal((1, 800)).astype("float32")
    out = A.to_waveform(_FakeDecoder(wave))
    _ok(out.ndim == 1 and out.shape == (800,), f"1D로 펴져야 함 (얻은 값 {out.shape})")
    _ok(out.dtype == np.float32, "float32여야 함")
    _ok(A.sampling_rate_of(_FakeDecoder(wave)) == 16000, "샘플레이트 추출")


def test_dict_form():
    wave = np.random.default_rng(1).standard_normal(500)
    out = A.to_waveform({"array": wave, "sampling_rate": 22050})
    _ok(out.shape == (500,) and out.dtype == np.float32, "딕셔너리 형식 처리")
    _ok(A.sampling_rate_of({"array": wave, "sampling_rate": 22050}) == 22050, "딕셔너리 샘플레이트")


def test_stereo_downmix():
    """다채널이면 모노로 평균한다 — 음향 모델은 모노 입력을 받는다."""
    stereo = np.stack([np.ones(100), np.full(100, 3.0)]).astype("float32")
    out = A.to_waveform(_FakeDecoder(stereo))
    _ok(out.shape == (100,), f"모노로 합쳐져야 함 (얻은 값 {out.shape})")
    _ok(np.allclose(out, 2.0), "채널 평균이어야 함")


def test_plain_array():
    out = A.to_waveform(np.arange(10, dtype="float64"))
    _ok(out.shape == (10,) and out.dtype == np.float32, "생배열도 통과")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n{len(tests)}개 테스트 통과")
