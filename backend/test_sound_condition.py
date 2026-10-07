"""소리 조건(C17): 찾기 키 정규화, 목록 찾기, 음절 시각 계산, 비열등 점검(순수 함수)과 /api/sound 엔드포인트.

엔드포인트는 임시 소리 폴더(LIPLAB_SOUND_DIR)와 임시 DB를 지정한 별도 프로세스에서 돌린다. 동적 합성은 끈 상태(기본값)다.
"""
import json
import os
import subprocess
import sys
import tempfile

import sound_clips as S


# ── 정규화와 키 ─────────────────────────────────────────────────────────────

def test_normalize_drops_punctuation_but_keeps_question():
    assert S.normalize_text("밥 먹었어요.") == "밥 먹었어요"
    assert S.normalize_text("  밥   먹었어요 ") == "밥 먹었어요"
    assert S.normalize_text("밥 먹었어요?") == "밥 먹었어요?"
    assert S.normalize_text("괜찮아, 같이 가자!") == "괜찮아 같이 가자"
    assert S.normalize_text("...") == ""
    assert S.normalize_text("") == ""


def test_normalize_nfd_is_same_key():
    import unicodedata
    assert S.normalize_text(unicodedata.normalize("NFD", "사과")) == "사과"


def test_clip_id_depends_on_voice_and_key():
    a = S.clip_id("사과", "f1")
    assert len(a) == 16 and all(c in "0123456789abcdef" for c in a)
    assert a == S.clip_id("사과", "f1")
    assert a != S.clip_id("사과", "m1")
    assert a != S.clip_id("사과?", "f1")


def test_clip_id_rev_gives_new_name_for_resynthesized_audio():
    # 다시 합성한 소리는 rev(새 Ogg sha1 앞 12자)로 새 이름을 받는다(immutable 캐시가 옛 소리를 쓰지 않게, docs/sound-qa-2026-10.md 6절)
    old = S.clip_id("사과", "f1")
    assert S.clip_id("사과", "f1", "") == old
    r1, r2 = S.audio_rev(b"OggS one"), S.audio_rev(b"OggS two")
    assert len(r1) == 12 and r1 != r2
    n1 = S.clip_id("사과", "f1", r1)
    assert n1 != old and n1 != S.clip_id("사과", "f1", r2) and S.safe_audio_name(f"{n1}.m4a") == (n1, "m4a")


def test_shipped_manifest_ids_follow_clip_id_rule():
    # 저장소 목록: 파일 이름이 clip_id(키, 목소리, rev) 규칙을 따르고 두 형식 파일이 모두 있다
    import json
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sound")
    p = os.path.join(base, "manifest.json")
    if not os.path.exists(p):
        return
    m = json.load(open(p, encoding="utf-8"))
    for v, clips in m["clips"].items():
        for k, c in clips.items():
            assert c["id"] == S.clip_id(k, v, c.get("rev", "")), (v, k)
            for ext in ("ogg", "m4a"):
                assert os.path.exists(os.path.join(base, "clips", f"{c['id']}.{ext}")), (v, k, ext)


def test_safe_audio_name_rejects_paths():
    i = S.clip_id("사과", "f1")
    assert S.safe_audio_name(f"{i}.ogg") == (i, "ogg")
    assert S.safe_audio_name(f"{i}.m4a") == (i, "m4a")
    for bad in ("../manifest.json", f"{i}.wav", f"../{i}.ogg", "abc.ogg", f"{i}"):
        assert S.safe_audio_name(bad) is None


# ── 목록 찾기 ───────────────────────────────────────────────────────────────

def _manifest():
    return {"clips": {"밥 먹었어요": {"id": "0123456789abcdef", "ms": 900, "syl": [[100, 300], [300, 500], [500, 650], [650, 800], [800, 880]]}}}


def test_lookup_ignores_punctuation_variants():
    m = _manifest()
    assert S.lookup(m, "밥 먹었어요.")["id"] == "0123456789abcdef"
    assert S.lookup(m, "밥 먹었어요")["key"] == "밥 먹었어요"
    assert S.lookup(m, "밥 먹었어요?") is None     # 물음표는 억양이 달라 다른 키
    assert S.lookup(m, "") is None


def test_load_manifest_missing_or_broken_is_empty(tmp_path):
    assert S.load_manifest(str(tmp_path / "none.json"))["clips"] == {}
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    assert S.load_manifest(str(p))["clips"] == {}


# ── 음절 시각 ───────────────────────────────────────────────────────────────

def test_group_jamo_onset_goes_forward_coda_goes_back():
    toks = ["o:ㅂ", "n:ㅏ", "c:ㅂ", "|", "o:ㅁ", "n:ㅓ", "o:ㄱ", "n:ㅓ", "n:ㅛ"]
    assert S.group_jamo_by_syllable(toks) == [[0, 1, 2], [4, 5], [6, 7], [8]]


def _phones(spans):
    return [{"token": t, "t0": a, "t1": b} for t, a, b in spans]


def test_syllable_times_fill_to_next_start_and_keep_long_pause():
    toks = ["o:ㅂ", "n:ㅏ", "c:ㅂ", "|", "o:ㅁ", "n:ㅓ"]
    ph = _phones([("o:ㅂ", 0.10, 0.12), ("n:ㅏ", 0.12, 0.14), ("c:ㅂ", 0.20, 0.22), ("|", 0.22, 0.24),
                  ("o:ㅁ", 0.30, 0.32), ("n:ㅓ", 0.32, 0.34)])
    # 첫 음절 끝(220ms)과 다음 시작(300ms) 틈 80ms ≤ 180ms → 앞 음절이 다음 시작까지 채운다. 마지막은 끝 + 꼬리 60ms
    assert S.syllable_times(ph, toks, duration_ms=1000) == [[100, 300], [300, 400]]
    # 긴 쉼(600ms)이면 쉼을 남긴다(앞 음절 끝 = 220 + 60)
    ph2 = _phones([("o:ㅂ", 0.10, 0.12), ("n:ㅏ", 0.12, 0.14), ("c:ㅂ", 0.20, 0.22), ("|", 0.22, 0.24),
                   ("o:ㅁ", 0.82, 0.84), ("n:ㅓ", 0.84, 0.86)])
    assert S.syllable_times(ph2, toks, duration_ms=1000) == [[100, 280], [820, 920]]
    # 소리 길이를 넘지 않는다
    assert S.syllable_times(ph, toks, duration_ms=360)[-1] == [300, 360]


def test_syllable_times_unaligned_or_mismatch_is_none():
    toks = ["o:ㅂ", "n:ㅏ"]
    assert S.syllable_times([{"token": "o:ㅂ", "t0": 0.1, "t1": 0.12}, {"token": "n:ㅏ"}], toks) is None
    assert S.syllable_times([{"token": "o:ㅂ", "t0": 0.1, "t1": 0.12}], toks) is None


def test_times_for_text_maps_to_frame_text_index():
    syl = [[100, 300], [300, 500], [500, 650], [650, 800], [800, 880]]
    out = S.times_for_text("밥 먹었어요.", syl)
    # 공백(1)과 마침표(6)는 음절이 아니다
    assert [x["i"] for x in out] == [0, 2, 3, 4, 5]
    assert out[1] == {"i": 2, "t0": 300, "t1": 500}
    assert S.times_for_text("밥 먹었어", syl) is None        # 음절 수가 다르면 시각 없이
    assert S.times_for_text("밥", None) is None


def test_frame_text_index_matches_engine():
    """화면의 입모양 프레임 text_index와 같은 번호 공간인지(엔진 프레임에서 음절 자리만)."""
    import asyncio
    import engine
    text = "닭이 3마리 있어요."
    frames = asyncio.run(engine.text_to_visemes(text))
    syl_idx = sorted({f["text_index"] for f in frames if f["viseme"] != 14})
    assert syl_idx == S.syllable_positions(text)


def test_evict_plan_removes_oldest_until_under_cap():
    entries = [("a", 100, 3.0), ("b", 100, 1.0), ("c", 100, 2.0)]
    assert S.evict_plan(entries, 300) == []
    assert S.evict_plan(entries, 250) == ["b"]
    assert S.evict_plan(entries, 100) == ["b", "c"]


def test_trim_silence_keeps_100ms_margin():
    import numpy as np
    import sound_tts
    sr = 16000
    x = np.zeros(sr * 2, np.float32)
    x[8000:16000] = 0.5 * np.sin(np.arange(8000) * 2 * np.pi * 200 / sr)   # 0.5초~1.0초 소리
    y = sound_tts.trim_silence(x, sr)
    assert abs(len(y) - (8000 + 2 * 1600)) <= 160                            # 소리 0.5초 + 앞뒤 0.1초
    assert sound_tts.trim_silence(np.zeros(sr, np.float32), sr).size == sr   # 전부 무음이면 그대로


# ── 비열등 점검 ─────────────────────────────────────────────────────────────

def _user(sound, first, last, n=40):
    h = n // 2
    return {"sound": sound, "correct": [i < round(first * h) for i in range(h)] + [i < round(last * h) for i in range(h)]}


def test_user_gain():
    assert S.user_gain([False] * 10 + [True] * 10) == 1.0
    assert S.user_gain([True] * 5) is None


def test_noninferiority_verdicts():
    import random
    rnd = random.Random(1)
    same = [_user(s, 0.4, 0.4 + 0.2 + rnd.uniform(-0.05, 0.05)) for s in (True, False) for _ in range(30)]
    assert S.noninferiority(same)["verdict"] == "noninferior"
    worse = ([_user(True, 0.4, 0.45 + rnd.uniform(-0.02, 0.02)) for _ in range(30)]
             + [_user(False, 0.4, 0.65 + rnd.uniform(-0.02, 0.02)) for _ in range(30)])
    assert S.noninferiority(worse)["verdict"] == "inferior"
    few = [_user(True, 0.4, 0.6), _user(False, 0.4, 0.6)]
    assert S.noninferiority(few)["verdict"] == "inconclusive"


# ── 엔드포인트 ──────────────────────────────────────────────────────────────

_SCENARIO = r'''
import json, os
from fastapi.testclient import TestClient
import main, database
from database import TrialAttempt, Progress
from sqlalchemy import select

out = {}
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "snd@example.com", "username": "소리", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    out["noauth"] = c.get("/api/sound", params={"text": "밥 먹었어요"}).status_code
    a = c.get("/api/sound", params={"text": "밥 먹었어요."}, headers=h)
    out["hit"] = [a.status_code, a.json()]
    v = c.get("/api/sound", params={"text": "밥 먹었어요", "voice": "m1"}, headers=h)
    out["voice_m1"] = [v.status_code, v.json()]
    out["unknown_voice"] = [c.get("/api/sound", params={"text": "밥 먹었어요", "voice": "zz"}, headers=h).status_code,
                            c.get("/api/sound", params={"text": "밥 먹었어요", "voice": "zz"}, headers=h).json()]
    miss = c.get("/api/sound", params={"text": "처음 보는 문장이에요"}, headers=h)
    out["miss"] = [miss.status_code, miss.json()]
    out["voices"] = c.get("/api/sound/voices").json()
    f = c.get(a.json()["sources"][0]["url"])
    out["file"] = [f.status_code, f.headers.get("content-type"), f.headers.get("cache-control"), len(f.content)]
    out["bad_file"] = c.get("/api/sound/audio/..%2Fmanifest.json").status_code
    out["noise"] = c.get("/api/sound/noise/babble.ogg").status_code
    out["noise_bad"] = c.get("/api/sound/noise/x.ogg").status_code
    out["noise_missing"] = c.get("/api/sound/noise/talker1_f.ogg").status_code
    out["noise_path"] = c.get("/api/sound/noise/..%2Fmanifest.json").status_code
    # 시행 기록: 소리 조건 플래그가 답과 함께 들어가고, 다시 보기를 틀면 그 시행에 표시된다
    w = c.post("/api/curriculum/word-answer", json={"word": "사과", "chosen": "사과", "correct": True, "sound_condition": True}, headers=h)
    out["word"] = w.status_code
    out["replay"] = c.post("/api/sound/replay", json={"kind": "trial", "target": "사과", "item_type": "word"}, headers=h).json()
    out["replay_none"] = c.post("/api/sound/replay", json={"kind": "trial", "target": "없는말"}, headers=h).json()
    out["replay_bad"] = c.post("/api/sound/replay", json={"kind": "zzz", "target": "사과"}, headers=h).status_code
    async def rows():
        async with database.AsyncSessionLocal() as db:
            t = (await db.execute(select(TrialAttempt))).scalars().all()
            return [[x.target, x.sound_condition, x.sound_replay] for x in t]
    out["rows"] = c.portal.call(rows)
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


def _write_sound_dir(d):
    import sound_clips as S2
    f1, m1 = S2.clip_id("밥 먹었어요", "f1"), S2.clip_id("밥 먹었어요", "m1")
    man = {"version": 2, "default_voice": "f1",
           "voices": [{"id": "f1", "label": "여성 1", "sex": "f", "engine_voice": "F1"},
                      {"id": "m1", "label": "남성 1", "sex": "m", "engine_voice": "M1"}],
           "clips": {"f1": {"밥 먹었어요": {"id": f1, "ms": 900, "syl": [[100, 300], [300, 500], [500, 650], [650, 800], [800, 880]]}},
                     "m1": {"밥 먹었어요": {"id": m1, "ms": 950, "syl": None}}}}
    os.makedirs(os.path.join(d, "clips"))
    os.makedirs(os.path.join(d, "noise"))
    with open(os.path.join(d, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(man, fh, ensure_ascii=False)
    for i in (f1, m1):
        for ext in ("ogg", "m4a"):
            with open(os.path.join(d, "clips", f"{i}.{ext}"), "wb") as fh:
                fh.write(b"OggS" + b"\0" * 60)
    for name in ("babble.ogg", "babble.m4a", "ssn.ogg"):      # ssn은 m4a가 없어 목록에 넣지 않는다
        with open(os.path.join(d, "noise", name), "wb") as fh:
            fh.write(b"OggS" + b"\0" * 60)
    return f1


def test_sound_endpoints():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        snd = os.path.join(d, "sound")
        os.makedirs(snd)
        f1 = _write_sound_dir(snd)
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1",
                   LIPLAB_SOUND_DIR=snd, LIPLAB_SOUND_CACHE_DIR=os.path.join(d, "cache"))
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("LIPLAB_SOUND_DYNAMIC", None)
        p = subprocess.run([sys.executable, "-c", _SCENARIO], cwd=here, env=env, capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])
    assert r["noauth"] == 401
    code, body = r["hit"]
    assert code == 200 and body["available"] and body["voice"] == "f1" and body["source"] == "fixed"
    assert body["id"] == f1 and body["duration_ms"] == 900
    assert [s["type"] for s in body["sources"]] == ["audio/ogg; codecs=opus", "audio/mp4"]
    assert body["sources"][0]["url"] == f"/api/sound/audio/{f1}.ogg"
    assert [x["i"] for x in body["syllables"]] == [0, 2, 3, 4, 5]          # 요청한 글(마침표 포함)의 자리 번호
    code, body = r["voice_m1"]
    assert code == 200 and body["voice"] == "m1" and body["syllables"] is None
    assert r["unknown_voice"] == [404, {"available": False, "reason": "unknown_voice"}]
    assert r["miss"] == [404, {"available": False, "reason": "not_prepared"}]
    assert r["voices"]["default_voice"] == "f1"
    assert r["voices"]["voices"] == [{"id": "f1", "label": "여성 1", "sex": "f"}, {"id": "m1", "label": "남성 1", "sex": "m"}]
    st, ctype, cc, n = r["file"]
    assert st == 200 and ctype.startswith("audio/ogg") and "immutable" in cc and n == 64
    assert r["bad_file"] == 404
    assert r["noise"] == 200 and r["noise_bad"] == 404 and r["noise_missing"] == 404 and r["noise_path"] == 404
    assert r["voices"]["noises"] == ["babble"]
    assert r["word"] == 200
    assert r["replay"] == {"marked": True} and r["replay_none"] == {"marked": False} and r["replay_bad"] == 422
    assert ["사과", True, True] in r["rows"]
