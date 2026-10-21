"""S4 스트리밍 채점(dgop_stream) 시험. 학생 ONNX는 아직 없으므로 가짜 순전파 두 가지로 이어 붙이기만 본다.

- 국소 모델(합성곱처럼 프레임 g가 표본 [320g, 320g+400)만 보는 모델): 창을 어떻게 나눠도 전체 순전파와 값이 같아야 한다.
  프레임 계산(창 시작·끝, 마지막 덩어리, 끝 자르기)이 하나라도 어긋나면 값이 달라진다.
- 전역 모델(창 전체 평균을 더하는 모델, 트랜스포머 대리): 창이 소리 전체를 덮으면 전체 순전파와 같고, 아니면 등록 측정
  (scripts/phone_tail/pod/stream_lat.py의 windows·stitch)과 같은 창에서 나온 값이어야 한다.
- 녹음 세션 끝(assess)은 국소 모델에서 예전 경로(assess_text)와 같은 점수·음소를 내야 한다.
"""
import json
import os
import subprocess
import sys
import tempfile
import types

import numpy as np
import pytest

import dgop_stream as S

C = 49
_RNG = np.random.default_rng(0)
_W = _RNG.standard_normal((4, C)).astype(np.float32)
_W2 = _RNG.standard_normal((4, C)).astype(np.float32)


def _feat(y, n_frames):
    f = np.empty((n_frames, 4), dtype=np.float32)
    for g in range(n_frames):
        seg = y[g * S.HOP:g * S.HOP + S.RECEPTIVE]
        f[g] = (seg.mean(), seg.std(), seg[:80].mean(), seg[-80:].mean())
    return f


def local_forward(y):
    """국소 모델: 출력 둘(정렬·채점 몫)."""
    f = _feat(np.asarray(y, dtype=np.float32), S.conv_frames(len(y)))
    return [f @ _W * 50, f @ _W2 * 50]


def global_forward(y):
    """전역 모델: 국소 특징 + 창 전체 평균(창 경계에 민감)."""
    y = np.asarray(y, dtype=np.float32)
    f = _feat(y, S.conv_frames(len(y)))
    f = f + y.mean() * 10 + y.std()
    return [f @ _W, f @ _W2]


def _wave(seconds, seed=1):
    r = np.random.default_rng(seed)
    n = int(round(seconds * S.SR))
    t = np.arange(n) / S.SR
    return (0.3 * np.sin(2 * np.pi * 180 * t) * (1 + np.sin(2 * np.pi * 0.7 * t)) + 0.05 * r.standard_normal(n)).astype(np.float32)


def _registered_windows(n, cf, lf, rf):
    """10/15 등록 측정의 창 나누기(stream_lat.windows를 그대로 옮김)."""
    G = S.conv_frames(n)
    out, b = [], 0
    while b < G:
        e = min(b + cf, G)
        f0 = max(0, b - lf)
        s1 = n if e >= G else min(n, (e + rf - 1) * S.HOP + 400)
        out.append((b, e, f0, f0 * S.HOP, s1))
        b = e
    return G, out


def test_conv_frames_matches_conv_stack():
    assert S.conv_frames(399) == 0 and S.conv_frames(400) == 1 and S.conv_frames(719) == 1 and S.conv_frames(720) == 2
    assert all(S.conv_frames(n) == max(0, (n - 400) // 320 + 1) for n in range(0, 20000, 7))
    assert S.conv_frames(30 * S.SR) == 1499


@pytest.mark.parametrize("cfg", [S.StreamConfig(), S.StreamConfig(1.0, 0.0, 0.0), S.StreamConfig(0.5, 0.3, 0.02),
                                 S.StreamConfig(4.0, 4.0, 2.0), S.StreamConfig(0.02, 0.0, 0.0)])
@pytest.mark.parametrize("sec", [0.05, 1.0, 3.99, 4.0, 5.0 + 1 / S.SR, 7.0, 12.345, 30.0])
def test_local_model_stream_equals_full(cfg, sec):
    y = _wave(sec)
    full = local_forward(y)
    got = S.stream_outputs(y, local_forward, cfg, feed_samples=1234)
    assert [g.shape for g in got] == [f.shape for f in full]
    for g, f in zip(got, full):
        np.testing.assert_allclose(g, f, rtol=0, atol=1e-4)


def test_window_covering_clip_equals_full_for_global_model():
    y = _wave(7.3)
    full = global_forward(y)
    got = S.stream_outputs(y, global_forward, S.StreamConfig(chunk_s=10.0))
    for g, f in zip(got, full):
        np.testing.assert_array_equal(g, f)


@pytest.mark.parametrize("sec", [3.0, 4.0, 15.0, 29.99])
def test_global_model_matches_registered_windows(sec):
    y = _wave(sec, seed=3)
    cfg = S.StreamConfig()
    G, ws = _registered_windows(len(y), cfg.chunk_frames, cfg.left_frames, cfg.right_frames)
    exp = [[], []]
    for b, e, f0, s0, s1 in ws:
        o = global_forward(y[s0:s1])
        for k in range(2):
            exp[k].append(o[k][b - f0:e - f0])
    exp = [np.concatenate(x) for x in exp]
    got = S.stream_outputs(y, global_forward, cfg, feed_samples=777)
    assert got[0].shape == (G, C)
    for g, f in zip(got, exp):
        np.testing.assert_allclose(g, f, rtol=0, atol=1e-5)
    if sec > 6:   # 창이 여럿이면 전체 순전파와는 달라야 한다(전역 모델)
        assert not np.allclose(got[0], global_forward(y)[0], atol=1e-3)


def test_chunk_without_full_right_context_waits_for_the_end():
    """8.7초: 둘째 덩어리 [200, 400)의 창 끝(9초 + 80표본)이 녹음보다 길다. 등록 측정 시뮬레이션은 오른쪽 문맥을 녹음 끝에서 잘라
    녹음 중에 돌린 것으로 쳤지만, 실제 녹음에서는 그 소리가 오기 전에 돌릴 수 없으므로 마지막 창 [100, 435)에 합친다."""
    y = _wave(8.7, seed=3)
    got = S.stream_outputs(y, global_forward, S.StreamConfig())
    first = global_forward(y[:S.StreamConfig().window_end(200)])
    last = global_forward(y[100 * S.HOP:])
    G = S.conv_frames(len(y))
    for k in range(2):
        np.testing.assert_allclose(got[k][:200], first[k][:200], atol=1e-5)
        np.testing.assert_allclose(got[k][200:], last[k][100:G - 100], atol=1e-5)


def test_windows_run_during_recording_and_frame_accounting():
    """덩어리 k는 창 끝 (e + 오른쪽 문맥 − 1)·320 + 400 표본이 왔을 때 한 번만 돈다. 마지막 덩어리는 finish에서."""
    cfg = S.StreamConfig()
    st = S.StreamStitcher(local_forward, cfg)
    calls = []
    st.forward = lambda w: (calls.append(len(w)), local_forward(w))[1]
    need = cfg.window_end(200)              # 첫 덩어리 [0, 200) 프레임: 창 [0, 250·320 + 80)
    assert need == 250 * 320 + 80
    st.feed(np.zeros(need - 1, np.float32))
    assert calls == [] and st.committed_frames == 0
    st.feed(np.zeros(1, np.float32))
    assert calls == [need] and st.committed_frames == 200
    # 둘째 덩어리 [200, 400): 왼쪽 문맥 100프레임 → 창 [100·320, 450·320 + 80)
    st.feed(np.zeros(cfg.window_end(400) - need, np.float32))
    assert calls[-1] == cfg.window_end(400) - 100 * 320 and st.committed_frames == 400
    n = st.n + 5000                          # 마지막 부분 덩어리(4초 미만)
    st.feed(np.zeros(5000, np.float32))
    out = st.finish()
    assert out[0].shape[0] == S.conv_frames(n)
    assert calls[-1] == n - 300 * 320         # 마지막 창은 왼쪽 문맥 2초(100프레임)부터 끝까지
    assert st.summary()["windows_during"] == 2


def test_trim_discards_chunks_whose_window_passes_the_cut():
    y = _wave(14.0, seed=5)
    cfg = S.StreamConfig()
    st = S.StreamStitcher(local_forward, cfg)
    st.feed(y)
    assert st.committed_frames == 600       # 덩어리 3개(12초 창 끝 = 650프레임 + 80표본 ≤ 14초)
    n_valid = int(9.5 * S.SR)                # 끝 무음을 자른 길이: 셋째 덩어리 창 끝(13초 + 80표본)이 넘으므로 둘째까지만 남는다
    out = st.finish(n_valid)
    assert out[0].shape[0] == S.conv_frames(n_valid)
    np.testing.assert_allclose(out[0], local_forward(y[:n_valid])[0], atol=1e-4)


def test_cap_30_seconds_and_pcm16_feed():
    st = S.StreamStitcher(local_forward, S.StreamConfig())
    st.feed(np.zeros(31 * S.SR, np.float32))
    assert st.n == 30 * S.SR and st.dropped == S.SR
    sess = S.StreamSession(1, local_forward, {}, None, S.StreamConfig())
    pcm = (np.array([0, 16384, -32768, 32767], dtype="<i2")).tobytes() + b"\x01"   # 홀수 바이트 끝은 버린다
    sess.feed_pcm16(pcm)
    np.testing.assert_allclose(sess.stitcher.waveform, [0, 0.5, -1.0, 32767 / 32768])


def test_session_store_owner_ttl_and_cap(monkeypatch):
    monkeypatch.setattr(S, "load_backend", lambda: (local_forward, {}, None))
    store = S.SessionStore(ttl_s=60, per_user=2)
    a, b, c = store.create(1), store.create(1), store.create(1)
    assert store.get(a.id, 1) is None and store.get(b.id, 1) is b and store.get(c.id, 1) is c   # 사람마다 최근 2개
    assert store.get(b.id, 2) is None and store.pop(b.id, 2) is None                           # 남의 세션은 못 씀
    assert store.pop(b.id, 1) is b and store.get(b.id, 1) is None
    c.touched -= 120
    assert store.get(c.id, 1) is None                                                           # 오래된 세션은 지움


def test_flag_and_model_defaults(monkeypatch):
    monkeypatch.delenv("DGOP_STREAM", raising=False)
    monkeypatch.delenv("DGOP_STREAM_MODEL", raising=False)
    assert S.enabled() is False
    with pytest.raises(RuntimeError):
        S.load_backend()
    monkeypatch.setenv("DGOP_STREAM_MODEL", "/없는/student.onnx")
    with pytest.raises(RuntimeError):
        S.load_backend()
    monkeypatch.setenv("DGOP_STREAM_CHUNK_S", "6")
    monkeypatch.setenv("DGOP_STREAM_LEFT_S", "8")
    monkeypatch.setenv("DGOP_STREAM_RIGHT_S", "4")
    cfg = S.StreamConfig.from_env()
    assert (cfg.chunk_frames, cfg.left_frames, cfg.right_frames) == (300, 400, 200)


def test_session_assess_equals_assess_text_for_local_model(monkeypatch):
    """국소 모델이면 스트리밍 채점(창 4/2/1초)과 예전 assess_text가 같은 점수·음소를 낸다(뒷부분 공용 코드 확인)."""
    import dgop_acoustic as DA
    if not DA.HAS_ACOUSTIC:
        pytest.skip("torch 미설치")
    import torch
    import jamo_vocab
    monkeypatch.delenv("DGOP_CALIBRATION", raising=False)
    y16 = (_wave(9.0, seed=7) * 32767).astype("<i2")
    y16[int(7.5 * S.SR):] //= 200           # 끝 1.5초는 거의 무음(끝 자르기가 일어나게)
    y = y16.astype(np.float32) / 32768.0
    text = "오늘 날씨가 좋아요"

    fake_fw = types.ModuleType("faster_whisper.audio")
    fake_fw.decode_audio = lambda f, sampling_rate=16000: y.copy()
    monkeypatch.setitem(sys.modules, "faster_whisper", types.ModuleType("faster_whisper"))
    monkeypatch.setitem(sys.modules, "faster_whisper.audio", fake_fw)

    def ctc_outputs(w, sr, model_id=DA.DEFAULT_MODEL_ID):
        lg = torch.from_numpy(local_forward(np.asarray(w, np.float32))[0 if model_id == "al" else 1])
        return torch.log_softmax(lg, -1), lg, dict(jamo_vocab.VOCAB)
    monkeypatch.setattr(DA, "ctc_outputs", ctc_outputs)
    monkeypatch.setattr(DA, "tokens_for_text", lambda t, model_id=None: jamo_vocab.text_to_tokens(t))
    monkeypatch.setattr(DA, "_share_once", lambda a, b: None)
    ref = DA.assess_text(b"", text, aligner_id="al", scorer_id="sc")

    sess = S.StreamSession(1, local_forward, dict(jamo_vocab.VOCAB), DA.DEFAULT_CALIBRATION_PATH, S.StreamConfig())
    for i in range(0, len(y16), 4000):
        sess.feed_pcm16(y16[i:i + 4000].tobytes())
    got = sess.assess(text)
    assert got["stream"]["windows_during"] == 1
    assert len(DA.trim_trailing_silence(y, S.SR)) < len(y)
    assert got["score"] == pytest.approx(ref["score"], abs=1e-4)
    assert got["raw_score"] == pytest.approx(ref["raw_score"], abs=1e-4)
    assert [p["token"] for p in got["phones"]] == [p["token"] for p in ref["phones"]]
    for a, b in zip(got["phones"], ref["phones"]):
        assert (a.get("t0"), a.get("t1"), a.get("aligned")) == (b.get("t0"), b.get("t1"), b.get("aligned"))
        if b.get("dgop") is not None:
            assert a["dgop"] == pytest.approx(b["dgop"], abs=1e-4)


_SCENARIO = r'''
import json, numpy as np
from fastapi.testclient import TestClient
import dgop_acoustic, dgop_stream, jamo_vocab, main
import test_dgop_stream as T

if dgop_stream.enabled():
    dgop_stream.load_backend = lambda: (T.local_forward, dict(jamo_vocab.VOCAB), dgop_acoustic.DEFAULT_CALIBRATION_PATH)
out = {}
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "s4@example.com", "username": "스트림시험", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    st = c.post("/api/speak/stream/start", headers=h)
    out["start"] = [st.status_code, st.json()]
    if st.status_code == 200:
        sid = st.json()["stream_id"]
        y16 = (T._wave(6.0) * 20000).astype("<i2")
        for i in range(0, len(y16), 16000):
            rr = c.post(f"/api/speak/stream/{sid}/chunk", content=y16[i:i + 16000].tobytes(), headers=h)
            out.setdefault("chunks", []).append(rr.json())
        out["other_user_chunk"] = c.post(f"/api/speak/stream/nope/chunk", content=b"\x00\x00", headers=h).status_code
        res = c.post("/api/speak/assess", data={"target": "오늘 날씨", "stream_id": sid},
                     files={"audio": ("a.webm", b"\x00" * 2048, "audio/webm")}, headers=h)
        j = res.json()
        out["assess"] = [res.status_code, j.get("assessment_method"), (j.get("dgop") or {}).get("stream")]
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


def _run(**env_extra):
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1", ANTHROPIC_API_KEY="")
        for k in ("DGOP_STREAM", "DGOP_STREAM_MODEL", "DGOP_ALIGNER_ID", "DGOP_MODEL_ID", "DGOP_SCORER_ID", "DGOP_CALIBRATION"):
            env.pop(k, None)
        env.update(env_extra)
        p = subprocess.run([sys.executable, "-c", _SCENARIO], cwd=here, env=env, capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    return json.loads(line[len("RESULT "):])


def test_endpoints_off_by_default():
    r = _run()
    assert r["start"][0] == 404


def test_endpoints_on_streams_and_scores():
    import dgop_acoustic as DA
    if not DA.HAS_ACOUSTIC:
        pytest.skip("torch 미설치")
    r = _run(DGOP_STREAM="1")
    assert r["start"][0] == 200 and r["start"][1]["sample_rate"] == 16000 and r["start"][1]["chunk_s"] == 4.0
    assert [x["frames"] for x in r["chunks"]] == [0, 0, 0, 0, 0, 200]   # 6초째에 첫 덩어리(창 끝 5초 + 80표본)
    assert r["other_user_chunk"] == 404
    code, method, stream = r["assess"]
    assert code == 200 and method == "dgop" and stream["windows_during"] == 1 and stream["samples"] == 6 * 16000


# ── 녹음 뒤 지연 줄이기(docs/scorer-stream-latency-2026-10.md 10절): 꼬리 조각을 채점 요청에 붙이기·코칭 뒤에서 받기
_SCENARIO_LATENCY = r'''
import json, numpy as np
from fastapi.testclient import TestClient
import dgop_acoustic, dgop_stream, jamo_vocab, main
import test_dgop_stream as T

dgop_stream.load_backend = lambda: (T.local_forward, dict(jamo_vocab.VOCAB), dgop_acoustic.DEFAULT_CALIBRATION_PATH)
out = {}
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "lat@example.com", "username": "지연시험", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    r2 = c.post("/api/auth/register", json={"email": "lat2@example.com", "username": "다른사람", "password": "pw-123456",
                                            "agree_terms": True, "age_confirmed": True})
    h2 = {"Authorization": "Bearer " + r2.json()["access_token"]}
    y16 = (T._wave(6.5) * 20000).astype("<i2").tobytes()
    step, last = 32000, 6 * 32000
    for kind in ("chunk", "tail"):
        sid = c.post("/api/speak/stream/start", headers=h).json()["stream_id"]
        for i in range(0, last, step):
            c.post(f"/api/speak/stream/{sid}/chunk", content=y16[i:i + step], headers=h)
        d = {"target": "오늘 날씨", "stage": "5", "stream_id": sid, "loudness": "60", "duration": "6.5"}
        files = {"audio": ("a.webm", b"\x00" * 2048, "audio/webm")}
        if kind == "chunk":
            c.post(f"/api/speak/stream/{sid}/chunk", content=y16[last:], headers=h)
        else:
            files["stream_tail"] = ("t.pcm", y16[last:], "application/octet-stream")
            d["coaching_async"] = "1"
        res = c.post("/api/speak/assess", data=d, files=files, headers=h)
        j = res.json()
        o = {"code": res.status_code, "score": j.get("score"), "method": j.get("assessment_method"),
             "phones": (j.get("acoustic_dgop") or {}).get("phones"), "samples": ((j.get("dgop") or {}).get("stream") or {}).get("samples"),
             "coaching": j.get("coaching"), "pending": j.get("coaching_pending"), "timing": res.headers.get("server-timing")}
        if kind == "tail":
            cid = j.get("coaching_id")
            o["other_user"] = c.get(f"/api/speak/coaching/{cid}", headers=h2).status_code
            o["missing"] = c.get("/api/speak/coaching/nope", headers=h).status_code
            o["coaching_later"] = c.get(f"/api/speak/coaching/{cid}", headers=h).json().get("coaching")
            hist = c.get("/api/speak/analysis", headers=h)
            o["analysis_code"] = hist.status_code
        out[kind] = o
    import asyncio
    from sqlalchemy import select
    from database import AsyncSessionLocal, SpeakAttempt
    async def saved():
        async with AsyncSessionLocal() as s:
            return [a.coaching for a in (await s.execute(select(SpeakAttempt).order_by(SpeakAttempt.id))).scalars()]
    out["saved"] = asyncio.run(saved())
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


def test_tail_in_assess_and_async_coaching_keep_outputs():
    """꼬리 조각을 채점 요청에 붙여도(stream_tail) 따로 보낸 것과 점수·음소가 같고, coaching_async=1이면 점수를 먼저 주고
    같은 코칭을 /api/speak/coaching/{id}로 준다(시도 기록에도 저장). 다른 사람·없는 id는 404."""
    import dgop_acoustic as DA
    if not DA.HAS_ACOUSTIC:
        pytest.skip("torch 미설치")
    global _SCENARIO
    keep = _SCENARIO
    try:
        _SCENARIO = _SCENARIO_LATENCY
        r = _run(DGOP_STREAM="1")
    finally:
        _SCENARIO = keep
    a, b = r["chunk"], r["tail"]
    assert a["code"] == b["code"] == 200 and a["method"] == b["method"] == "dgop"
    assert a["samples"] == b["samples"] == int(6.5 * 16000)
    assert a["score"] == b["score"] and a["phones"] == b["phones"]
    assert a["pending"] is False and a["coaching"]
    assert b["pending"] is True and b["coaching"] is None
    assert b["coaching_later"] == a["coaching"]          # 같은 입력이면 같은 코칭(키 없음 → 규칙 코칭)
    assert b["other_user"] == 404 and b["missing"] == 404
    assert r["saved"] == [a["coaching"], a["coaching"]]
    assert "stream_assess;dur=" in a["timing"] and "stream_tail;dur=" in b["timing"]
