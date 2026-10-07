"""문장 끝 모음 정렬 결함 수정(docs/dgop-final-vowel-2026-10.md): 정렬 전 끝 무음 자르기.

정렬기는 마지막 토큰을 입력의 마지막 프레임에 내므로, 끝 무음을 잘라야 끝 모음이 말소리 끝 근처에 놓인다.
모델 없이 합성 파형과 가짜 ctc_log_probs로 확인한다. 실행: python -m pytest -q test_dgop_tail_trim.py
"""
import numpy as np

import dgop_acoustic as DA

SR = 16000


def _speech_then_noise(speech_s=0.5, tail_s=1.0, lead_s=0.2, seed=0):
    rng = np.random.default_rng(seed)
    lead = rng.standard_normal(int(SR * lead_s)) * 1e-4
    t = np.arange(int(SR * speech_s)) / SR
    tone = 0.3 * np.sin(2 * np.pi * 220 * t)
    tail = rng.standard_normal(int(SR * tail_s)) * 1e-4
    return np.concatenate([lead, tone, tail]).astype(np.float32)


def test_speech_end_finds_end_of_voiced_part():
    y = _speech_then_noise()
    end = DA.speech_end_seconds(y, SR)
    assert end is not None and abs(end - 0.7) <= 0.011


def test_speech_end_none_for_tiny_or_missing_input():
    assert DA.speech_end_seconds(None, SR) is None
    assert DA.speech_end_seconds(np.zeros(200, np.float32), SR) is None


def test_trim_cuts_tail_only_with_margin():
    y = _speech_then_noise()
    out = DA.trim_trailing_silence(y, SR)
    assert np.array_equal(out, y[:len(out)])                       # 앞은 그대로, 끝만 자른다
    end = DA.speech_end_seconds(y, SR)
    assert len(out) == int(round((end + DA.TAIL_TRIM_MARGIN_S) * SR))
    assert len(DA.trim_trailing_silence(y, SR, margin_s=5.0)) == len(y)   # 여유가 녹음보다 길면 그대로


def test_trim_never_below_minimum_and_can_be_disabled(monkeypatch):
    y = np.concatenate([np.full(320, 0.5, np.float32), np.zeros(SR, np.float32)])
    assert len(DA.trim_trailing_silence(y, SR, margin_s=0.0)) == int(0.1 * SR)
    monkeypatch.setenv("DGOP_TAIL_TRIM", "0")
    assert DA.trim_trailing_silence(y, SR) is y
    assert DA.trim_trailing_silence(None, SR) is None


def test_phone_confidences_aligns_trimmed_audio_and_keeps_time_base(monkeypatch):
    """정렬기·채점기에는 자른 소리가 들어가고, 시각은 자른 길이로 프레임을 초로 바꾼다(앞을 자르지 않아 원래 녹음 기준과 같다)."""
    if not DA.HAS_ACOUSTIC:
        return
    import torch
    vocab = {"<pad>": 0, "A": 1, "B": 2}
    seen = []

    def fake(waveform, sample_rate, model_id=DA.DEFAULT_MODEL_ID):
        seen.append(len(waveform))
        n = len(waveform) // 320
        lg = torch.full((n, 3), -10.0)
        lg[:, 0] = 10.0
        lg[n // 3, 0], lg[n // 3, 1] = -10.0, 10.0
        lg[n - 1, 0], lg[n - 1, 2] = -10.0, 10.0        # 마지막 토큰은 입력 끝 프레임에(정렬기의 버릇)
        return torch.log_softmax(lg, -1), vocab

    monkeypatch.setattr(DA, "ctc_log_probs", fake)
    y = _speech_then_noise()
    res = DA.phone_confidences(y, SR, ["A", "B"], aligner_id="x")
    cut = len(DA.trim_trailing_silence(y, SR))
    assert seen == [cut]
    assert res[-1]["t1"] <= cut / SR + 1e-6 and res[-1]["t1"] < 0.8   # 끝 토큰이 1초 끝 무음이 아니라 말소리 끝 근처
