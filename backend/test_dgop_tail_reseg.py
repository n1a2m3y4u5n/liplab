"""끝 구간 다시 나누기(docs/dgop-final-vowel-fix2-2026-10.md): 정렬기가 끝 토큰을 입력 끝에 낼 때 시각만 다시 정한다.

모델 없이 합성 log_probs로 확인한다. 실행: python -m pytest -q test_dgop_tail_reseg.py
"""
import numpy as np
import pytest

import dgop_acoustic as DA

VOCAB = {"<pad>": 0, "|": 1, "o:ㅎ": 2, "n:ㅐ": 3, "n:ㅛ": 4, "c:ㄴ": 5}


def _lp(n, frames):
    """frames: {프레임: (토큰 id, 확률)} 밖은 빈칸 0.98. 빈칸이 아닌 나머지 질량은 ref 토큰들에 나눈다."""
    lp = np.full((n, len(VOCAB)), 1e-4)
    lp[:, 0] = 0.98
    for t, row in frames.items():
        for tok, p in row.items():
            lp[t, tok] = p
    lp = lp / lp.sum(axis=1, keepdims=True)
    return np.log(lp)


def test_monotone_segments_simple_split():
    sc = np.array([[0, -5], [0, -5], [-5, 0], [-5, 0], [-5, 0]], float)
    assert DA._monotone_segments(sc) == [0, 2]
    with pytest.raises(ValueError):
        DA._monotone_segments(np.zeros((1, 2)))


def test_retime_moves_final_vowel_start_to_where_it_dominates_non_blank():
    """'해요': ㅛ는 빈칸에 눌려 입력 끝(프레임 39)에서만 이기지만, 빈칸을 빼면 프레임 20부터 ㅛ가 ㅐ보다 높다."""
    n = 40
    fr = {5: {2: 0.9}, 10: {3: 0.9}, 39: {4: 0.95}}
    for t in range(11, 20):
        fr[t] = {3: 0.01, 4: 0.001}      # ㅐ 구간(빈칸 우세)
    for t in range(20, 30):
        fr[t] = {3: 0.001, 4: 0.01}      # ㅛ 구간(빈칸 우세, 그래도 ㅛ > ㅐ)
    lp = _lp(n, fr)
    toks = ["o:ㅎ", "n:ㅐ", "n:ㅛ"]
    spans = [{"token": t, "start": s, "end": s} for t, s in zip(toks, (5, 10, 39))]
    out = DA.retime_tail(lp, VOCAB, toks, spans, end_frame=30, gate="late")
    assert out[0] == spans[0] and out[1] == spans[1]          # 앞 토큰들은 그대로
    assert out[2]["start"] == 20 and out[2]["end"] == 30 and out[2]["retimed"]
    assert spans[2]["start"] == 39                            # 원래 spans는 바꾸지 않는다


def test_retime_handles_vowel_plus_coda_and_word_boundary():
    n = 40
    fr = {5: {3: 0.9}, 8: {1: 0.9}, 39: {5: 0.95}, 30: {4: 0.9}}
    for t in range(9, 22):
        fr[t] = {3: 0.01, 4: 0.001, 5: 0.0001}
    for t in range(22, 28):
        fr[t] = {3: 0.0001, 4: 0.01, 5: 0.001}
    for t in range(28, 33):
        fr[t] = {4: 0.001, 5: 0.01}
    lp = _lp(n, fr)
    toks = ["n:ㅐ", "|", "n:ㅛ", "c:ㄴ"]
    spans = [{"token": t, "start": s, "end": s} for t, s in zip(toks, (5, 8, 30, 39))]
    out = DA.retime_tail(lp, VOCAB, toks, spans, end_frame=32, gate="late")
    assert out[0] == spans[0]                                 # 앞 토큰은 어절 경계를 건너뛴 n:ㅐ
    assert out[1]["start"] < out[2]["start"] < out[3]["start"] <= out[3]["end"] == 32   # 사이의 어절 경계도 상태 하나로 나눈다
    assert 20 <= out[2]["start"] <= 23


def test_retime_gate_late_keeps_tokens_emitted_inside_speech():
    n = 40
    lp = _lp(n, {5: {2: 0.9}, 10: {3: 0.9}, 20: {4: 0.9}})
    toks = ["o:ㅎ", "n:ㅐ", "n:ㅛ"]
    spans = [{"token": t, "start": s, "end": s} for t, s in zip(toks, (5, 10, 20))]
    assert DA.retime_tail(lp, VOCAB, toks, spans, end_frame=30, gate="late") == spans
    moved = DA.retime_tail(lp, VOCAB, toks, spans, end_frame=30, gate="all")
    assert moved[2]["retimed"] and moved[2]["end"] == 30


def test_retime_leaves_spans_when_inputs_do_not_fit():
    lp = _lp(10, {2: {2: 0.9}, 9: {4: 0.9}})
    toks = ["o:ㅎ", "n:ㅛ"]
    spans = [{"token": t, "start": s, "end": s} for t, s in zip(toks, (2, 9))]
    assert DA.retime_tail(lp, VOCAB, toks, spans, end_frame=None) == spans
    assert DA.retime_tail(lp, VOCAB, toks, spans, end_frame=2, gate="all") == spans     # 프레임 부족
    assert DA.retime_tail(lp, VOCAB, ["o:ㅎ", "c:ㄴ"], spans, end_frame=9) == spans     # 중성 없음


def test_phone_confidences_retimes_only_when_flag_is_on(monkeypatch):
    """켜면 끝 토큰의 시각만 바뀌고 naive(채점)는 CTC 구간 그대로다."""
    if not DA.HAS_ACOUSTIC:
        return
    import torch
    sr = 16000
    rng = np.random.default_rng(0)
    t = np.arange(int(sr * 0.6)) / sr
    y = np.concatenate([rng.standard_normal(int(sr * 0.1)) * 1e-4, 0.3 * np.sin(2 * np.pi * 220 * t),
                        rng.standard_normal(int(sr * 0.6)) * 1e-4]).astype(np.float32)
    vocab = {"<pad>": 0, "n:A": 1, "n:B": 2}

    def fake(waveform, sample_rate, model_id=DA.DEFAULT_MODEL_ID):
        n = len(waveform) // 320
        lg = torch.full((n, 3), -10.0)
        lg[:, 0] = 10.0
        lg[n // 5, 0], lg[n // 5, 1] = -10.0, 10.0
        lg[n // 5 + 1:n // 2, 1], lg[n // 5 + 1:n // 2, 2] = 1.0, 0.0     # 앞 토큰 A 구간(빈칸 우세)
        lg[n // 2:, 1], lg[n // 2:, 2] = 0.0, 1.0                          # B 구간과 끝 무음(빈칸 우세)
        lg[n - 1, 0], lg[n - 1, 2] = -10.0, 10.0                           # 끝 토큰은 입력 끝 프레임에(정렬기의 버릇)
        return torch.log_softmax(lg, -1), vocab

    monkeypatch.setattr(DA, "ctc_log_probs", fake)
    monkeypatch.setattr(DA, "_is_scorable", lambda tok: True)
    monkeypatch.setattr(DA, "speech_end_seconds", lambda w, s: 0.7)
    monkeypatch.setattr(DA, "TAIL_RESEG_GATE", "all")
    monkeypatch.setenv("DGOP_TAIL_TRIM", "0")
    monkeypatch.delenv("DGOP_TAIL_RESEG", raising=False)
    old = DA.phone_confidences(y, sr, ["n:A", "n:B"], aligner_id="x")
    assert old[-1]["t0"] > 1.2 and "retimed" not in old[-1]
    monkeypatch.setenv("DGOP_TAIL_RESEG", "1")
    new = DA.phone_confidences(y, sr, ["n:A", "n:B"], aligner_id="x")
    assert new[-1]["retimed"] and abs(new[-1]["t1"] - 0.77) < 0.03 and new[-1]["t0"] < 0.75
    assert [p["naive"] for p in new] == [p["naive"] for p in old]          # 채점은 그대로
    assert new[0]["t0"] == old[0]["t0"]


def test_retime_groups_tokens_that_all_landed_at_input_end():
    """'해요'에서 ㅐ와 ㅛ가 모두 입력 끝에 몰려 나와도(앞 토큰 ㅎ만 말소리 안), 묶음 [ㅐ, ㅛ]를 ㅎ 뒤에서 다시 나눈다."""
    n = 40
    fr = {5: {2: 0.9}, 38: {3: 0.9}, 39: {4: 0.95}}
    for t in range(6, 18):
        fr[t] = {3: 0.01, 4: 0.001}
    for t in range(18, 30):
        fr[t] = {3: 0.001, 4: 0.01}
    lp = _lp(n, fr)
    toks = ["o:ㅎ", "n:ㅐ", "n:ㅛ"]
    spans = [{"token": t, "start": s, "end": s} for t, s in zip(toks, (5, 38, 39))]
    out = DA.retime_tail(lp, VOCAB, toks, spans, end_frame=30, gate="late")
    assert out[0] == spans[0]
    assert out[1]["retimed"] and out[1]["start"] == 6
    assert out[2]["start"] == 18 and out[2]["end"] == 30
