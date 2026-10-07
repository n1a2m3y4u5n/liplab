"""끝 무음 증강(train_aligner.pad_silence) 단위 시험. 모델·데이터셋 없이 numpy만 쓴다.

    backend/.venv/bin/python -m pytest -q scripts/test_pad_silence.py
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import train_aligner as TA  # noqa: E402

SR = 16000


def _speech(sec=2.0, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(int(SR * sec)) / SR
    return (0.3 * np.sin(2 * np.pi * 220 * t) + 0.01 * rng.standard_normal(len(t))).astype(np.float32)


def test_speech_kept_and_lengths_in_range():
    y = _speech()
    rng = np.random.default_rng(1)
    for _ in range(200):
        out = TA.pad_silence(y, rng)
        extra = len(out) - len(y)
        assert 0 <= extra <= int(SR * (TA.PAD_TAIL_S[1] + TA.PAD_HEAD_S[1])) + 2
        # 말소리는 그대로 어딘가에 들어 있다(앞 길이만큼 밀린 자리)
        head = next(k for k in range(0, int(SR * TA.PAD_HEAD_S[1]) + 2) if np.array_equal(out[k:k + 100], y[:100]))
        assert np.array_equal(out[head:head + len(y)], y)


def test_rates_and_levels():
    y = _speech()
    rng = np.random.default_rng(2)
    n, tails, heads, quiet = 2000, 0, 0, 0
    ref = np.percentile(20 * np.log10(np.sqrt(np.mean(y[:len(y) // 160 * 160].reshape(-1, 160).astype(np.float64) ** 2, 1))), 99)
    for _ in range(n):
        out = TA.pad_silence(y, rng)
        k = next(k for k in range(0, int(SR * TA.PAD_HEAD_S[1]) + 2) if np.array_equal(out[k:k + 100], y[:100]))
        heads += k > 0
        tail = out[k + len(y):]
        tails += len(tail) > 0
        if len(tail):
            rms_db = 20 * np.log10(np.sqrt(np.mean(tail.astype(np.float64) ** 2)) + 1e-12)
            assert rms_db < ref - TA.PAD_BELOW_DB[0] + 1.0          # 붙인 소리는 말소리보다 35 dB 넘게 약하다
            quiet += rms_db < -200
    assert abs(tails / n - TA.PAD_P_TAIL) < 0.04
    assert abs(heads / n - TA.PAD_P_HEAD) < 0.04
    assert abs(quiet / max(1, tails) - TA.PAD_P_ZERO) < 0.05


def test_transform_without_pad_is_unchanged_path():
    class P:
        def __call__(self, wave, sampling_rate):
            class R:
                input_values = [np.asarray(wave, np.float32)]
            return R()
    y = _speech(1.0)
    batch = {"audio": [{"array": y, "sampling_rate": SR}] * 3, "text": ["가요"] * 3}
    out = TA.degrading_transform(P(), seed=0, severities=[0], pad_aug=False)(batch)
    assert all(len(v) == len(y) for v in out["input_values"])
    out = TA.degrading_transform(P(), seed=0, severities=[0], pad_aug=True)(batch)
    assert all(len(v) >= len(y) for v in out["input_values"])
