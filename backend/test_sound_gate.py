"""실행 중 품질 게이트(sound_gate)가 10/7 품질 점검 규칙(scripts/sound_pod/qa_rules.py)과 같은 값을 내는지 본다.
qa_rules는 scipy를 쓰므로 scipy가 없으면 비교 시험은 건너뛴다(게이트 자체는 numpy만 쓴다)."""
import importlib.util
import json
import os

import numpy as np
import pytest

import sound_gate as G

HERE = os.path.dirname(os.path.abspath(__file__))
QA = os.path.join(HERE, "..", "scripts", "sound_pod", "qa_rules.py")


def _qa():
    pytest.importorskip("scipy")
    spec = importlib.util.spec_from_file_location("qa_rules_ref", QA)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _speechy(sr=16000, seed=0):
    """말소리 비슷한 신호: 무음 · 음절 같은 톤 묶음 · 짧은 쉼 · 끝 무음."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(0.18 * sr)) / sr
    parts = [np.zeros(int(0.3 * sr))]
    for k in range(6):
        f0 = 120 + 20 * k
        env = np.hanning(t.size)
        parts.append(0.2 * env * (np.sin(2 * np.pi * f0 * t) + 0.3 * np.sin(2 * np.pi * 3 * f0 * t)))
        parts.append(np.zeros(int((0.04 if k != 2 else 0.25) * sr)))
    parts.append(np.zeros(int(0.4 * sr)))
    return np.concatenate(parts) + 1e-4 * rng.standard_normal(sum(p.size for p in parts))


def test_onepole_matches_lfilter():
    sig = pytest.importorskip("scipy.signal")
    x = np.abs(np.random.default_rng(1).standard_normal(50_001))
    for sr in (16000, 44100, 48000):
        g = np.exp(-1.0 / (sr * 0.03))
        ref = sig.lfilter([1 - g], [1, -g], x)
        assert np.max(np.abs(G._onepole(x, g) - ref)) < 1e-9


def test_level_span_postprocess_match_qa_rules():
    Q = _qa()
    for sr in (16000, 44100):
        x = _speechy(sr)
        assert abs(G.active_level(x, sr) - Q.active_level(x, sr)) < 1e-9
        assert G.speech_span(x, sr) == Q.speech_span(x, sr)
        y1, i1 = G.postprocess(x, sr)
        y2, i2 = Q.postprocess(x, sr)
        assert np.allclose(y1, y2, atol=1e-7) and i1["raw_level_db"] == i2["raw_level_db"] and i1["gain_db"] == i2["gain_db"]
        m = G.signal_metrics(y1, sr)
        assert abs(m["level_db"] - G.TARGET_DBFS) < 0.3 and abs(m["lead_ms"] - G.PAD_MS) <= 10


def _phones_for(tokens, x, sr):
    """토큰마다 고른 시각(말소리 구간을 음절 수로 나눔)."""
    import sound_clips as S
    span = G.speech_span(x, sr)
    groups = S.group_jamo_by_syllable(list(tokens))
    n = len(groups)
    a, b = span[0] / 1000, span[1] / 1000
    phones = [{} for _ in tokens]
    for k, g in enumerate(groups):
        s0, s1 = a + (b - a) * k / n, a + (b - a) * (k + 1) / n
        for j, i in enumerate(g):
            phones[i] = {"token": tokens[i], "t0": s0 + (s1 - s0) * j / len(g), "t1": s0 + (s1 - s0) * (j + 1) / len(g),
                         "aligned": True, "scorable": True}
    for i, t in enumerate(tokens):
        if not phones[i]:
            phones[i] = {"token": t, "t0": None, "t1": None, "aligned": False, "scorable": False}
    return phones


def test_signal_and_judge_match_qa_rules():
    Q = _qa()
    import jamo_vocab
    sr = 16000
    text = "내일 다시 오세요"
    toks = jamo_vocab.text_to_tokens(text)
    y, info = G.postprocess(_speechy(sr), sr)
    phones = [p for p in _phones_for(toks, y, sr)]
    if any(p.get("t0") is None for p in phones):
        # 어절 경계 토큰은 시각이 없다. qa_eval과 같게, 경계는 앞 토큰 끝으로 채운다
        for i, p in enumerate(phones):
            if p.get("t0") is None:
                p["t0"] = p["t1"] = phones[i - 1]["t1"]
    m1 = G.signal_metrics(y, sr, phones, toks)
    m2 = Q.signal_metrics(y, sr, phones, toks)
    assert m1 == m2
    for grp in ("sent", "word", "one"):
        for rz, lv in ((None, None), (4.0, 7.0), (-0.5, 1.0)):
            assert G.judge_signal(m1, grp, rz, lv, False) == Q.judge_signal(m2, grp, rz, lv, False)
    assert G.fix_tail_syllables([[100, 200], [200, 300], [950, 970]], 700) == Q.fix_tail_syllables([[100, 200], [200, 300], [950, 970]], 700)
    assert G.syl_valid([[1, 2], [2, 3]], 2, 5) == Q.syl_valid([[1, 2], [2, 3]], 2, 5)
    # 게이트 판정: D-GOP 문턱
    q = G.judge(text, "m1", y, sr, info["raw_level_db"], phones, toks, 85.0)
    assert q["group"] == "sent" and q["syl"] is not None and len(q["syl"]) == 7
    assert G.judge(text, "m1", y, sr, info["raw_level_db"], phones, toks, 79.9)["tier"] == "fail"
    assert G.judge(text, "m1", y, sr, info["raw_level_db"], None, toks, None)["tier"] == "fail"


def test_ref_matches_qa_ref():
    a = json.load(open(os.path.join(HERE, "data", "sound_gate_ref.json"), encoding="utf-8"))
    b = json.load(open(os.path.join(HERE, "..", "scripts", "sound_pod", "qa_ref.json"), encoding="utf-8"))
    assert a == b and G.ref()["level"]["m1"] == b["level"]["m1"]


def test_pron_thresholds():
    assert G.judge_pron_dgop("sent", 80.0)[0] == "pass" and G.judge_pron_dgop("sent", 79.0)[0] == "fail"
    assert G.judge_pron_dgop("word", 70.0)[0] == "pass" and G.judge_pron_dgop("one", 59.9)[0] == "fail"
    assert G.judge_pron_dgop("one", None) == ("fail", "dgop_none")
    assert G.CANDIDATES == ((8, 1.05, 0), (16, 1.05, 1))


def test_make_clip_candidates(monkeypatch):
    """첫 후보가 게이트에서 떨어지면 둘째 후보(16 steps, 시드 1)를 만들고, 둘 다 떨어지면 ok=False(파일 없음)."""
    import jamo_vocab
    import sound_tts as T
    text = "내일 다시 오세요"
    toks = jamo_vocab.text_to_tokens(text)
    sr = 16000
    calls = []

    def raw(t, v, steps=8, speed=1.05, seed=0):
        calls.append((steps, speed, seed))
        tt = np.arange(int(1.2 * sr)) / sr      # 끊김 없는 1.2초 소리(음절 고르게 나눈 시각이 모두 소리 위에 놓이게)
        x = 0.08 * np.sin(2 * np.pi * 150 * tt) * (1 + 0.3 * np.sin(2 * np.pi * 4 * tt))
        return np.concatenate([np.zeros(sr // 4), x, np.zeros(sr // 4)]).astype(np.float32), sr

    scores = {}

    def phones(w16, t):
        ph = _phones_for(toks, w16, 16000)
        for i, p in enumerate(ph):
            if p.get("t0") is None:
                p["t0"] = p["t1"] = ph[i - 1]["t1"]
        return ph, toks, scores[len(calls)]

    monkeypatch.setattr(T, "synthesize_raw", raw)
    monkeypatch.setattr(T, "phones_for", phones)
    monkeypatch.setattr(T, "to16k", lambda x, s: x)
    monkeypatch.setattr(T, "encode", lambda x, s: {"ogg": b"o", "m4a": b"m"})
    scores.update({1: 70.0, 2: 88.0})
    r = T.make_clip(text, text, "M1", "m1")
    assert r["ok"] and r["q"]["cand"] == "c1" and calls == [(8, 1.05, 0), (16, 1.05, 1)] and len(r["syl"]) == 7
    assert [t["tier"] for t in r["tries"]] == ["fail", "pass"] and r["files"]["ogg"] == b"o"
    calls.clear()
    scores.update({1: 90.0})
    r = T.make_clip(text, text, "M1", "m1")
    assert r["ok"] and r["q"]["cand"] == "c0" and len(calls) == 1
    calls.clear()
    scores.update({1: 50.0, 2: 60.0})
    r = T.make_clip(text, text, "M1", "m1", keep_rejected=True)
    assert not r["ok"] and "files" not in r and r["rejected_files"] and len(r["tries"]) == 2
