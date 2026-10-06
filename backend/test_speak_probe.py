"""말하기 모음·자음(2·3단계) 낱말 속 소리 확인(docs/curriculum-roadmap.md 2-5, P9).

- 확인 낱말: 서로 다른 목표 소리, 첫 음절 위치, 1·2음절, 약한 소리 먼저, (사용자, 날짜) seed로 결정적, 애·에는 한 소리.
- 숙달: 이동 평균 조건 + 최근 3번 중 2번 합격(사전 등록 규칙, 리뷰 뒤 되돌림). 합격은 이 단계 합격선 + 첫 음절 목표 소리.
  확인은 이동 평균·시도 수를 바꾸지 않고, 이미 숙달한 단계는 그대로다.
"""
import json
import os
import subprocess
import sys
import tempfile

import speak_curriculum as sc


def test_stage_sounds_merge_ae_e():
    assert sc.stage_sounds(2) == ["ㅏ", "ㅓ", "ㅗ", "ㅜ", "ㅡ", "ㅣ", "ㅐ"]     # 애·에는 ㅐ 하나
    assert sc.stage_sounds(3) == ["ㅁ", "ㅂ", "ㅍ", "ㄷ", "ㅌ", "ㅅ", "ㅈ", "ㅊ", "ㄱ", "ㅋ", "ㅎ"]   # 9/28 마찰·파찰·성문음 추가(1-5)
    assert sc.stage_sounds(4) == [] and sc.probe_words(4, "s") == []
    assert sc.probe_sound(2, "베개") == "ㅐ" and sc.probe_sound(2, "배추") == "ㅐ"
    assert sc.probe_sound(3, "토끼") == "ㅌ" and sc.probe_sound(3, "아기") is None


def test_probe_words_cover_distinct_sounds_in_first_syllable():
    for stage in (2, 3):
        n = sc.get_stage(stage)["probe"]["n"]
        items = {it["target"] for it in sc.get_stage(stage)["items"]}
        for day in range(30):
            ps = sc.probe_words(stage, f"7:{stage}:2026-09-{day:02d}")
            assert len(ps) == n
            sounds = [p["sound"] for p in ps]
            assert len(set(sounds)) == n and set(sounds) <= set(sc.stage_sounds(stage))
            for p in ps:
                assert p["probe"] is True and p["target"] in sc._STAGE4_WORDS and p["target"] not in items
                assert sc.probe_sound(stage, p["target"]) == p["sound"]
                assert 1 <= sc._n_syllables(p["target"]) <= 2
                assert "ㅔ" not in sounds


def test_probe_words_deterministic_and_weak_first():
    a = sc.probe_words(3, "5:3:2026-09-28", weak=["ㅋ", "ㅅ"])
    assert a == sc.probe_words(3, "5:3:2026-09-28", weak=["ㅋ", "ㅅ"])
    assert a[0]["sound"] == "ㅋ"                     # 약한 소리 먼저, 이 단계 소리가 아닌 ㅅ은 무시
    days = {tuple(p["target"] for p in sc.probe_words(3, f"5:3:2026-09-{d:02d}")) for d in range(1, 29)}
    assert len(days) > 5                              # 날마다 바뀐다
    e = sc.probe_words(2, "5:2:2026-09-28", weak=["ㅔ", "ㅡ"])
    assert [p["sound"] for p in e[:2]] == ["ㅐ", "ㅡ"]   # 약한 ㅔ는 ㅐ 소리로 먼저 낸다


def test_probe_words_prefer_short_familiar_words():
    pool = ["코끼리다", "크림", "코", "사과"]          # 4음절은 빼고, 1·2음절을 먼저
    ps = sc.probe_words(3, "x", weak=["ㅋ"], pool=pool)
    assert ps[0]["target"] in ("크림", "코") and ps[0]["sound"] == "ㅋ"
    assert [p["target"] for p in sc.probe_words(3, "x", pool=["코끼리"])] == ["코끼리"]   # 짧은 말이 없으면 3음절


def test_probes_ok_window():
    cfg = sc.get_stage(3)["probe"]
    assert cfg == {"n": 3, "need": 2}
    assert sc.probes_ok([True, False, True], cfg)
    assert not sc.probes_ok([True, False, False], cfg)
    assert sc.probes_ok([True, True], cfg)
    assert not sc.probes_ok([True], cfg)
    assert sc.probes_ok([False, False, False, True, True], cfg)     # 최근 3번만 본다
    assert not sc.probes_ok([True, True, False, False, True], cfg)
    assert sc.probes_ok([], None)


_SCENARIO = r'''
import asyncio, datetime, json
from fastapi.testclient import TestClient
import database, llm_service, main, speak_service
from database import SpeakAttempt, SpeakStageProgress
from sqlalchemy import select

heard = {"text": ""}
async def fake_transcribe(data):
    return heard["text"]
class _Boom:
    class messages:
        @staticmethod
        async def create(*a, **k):
            raise RuntimeError("no network in tests")
speak_service.transcribe = fake_transcribe
speak_service.is_available = lambda: True
llm_service.anthropic_client = _Boom

out = {}
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "probe@example.com", "username": "probeu", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    uid = c.get("/api/auth/me", headers=h).json()["id"]

    def assess(target, stage, text, probe=0, review=0, loud="50"):
        heard["text"] = text
        res = c.post("/api/speak/assess", headers=h, files={"audio": ("a.webm", b"\x00" * 2048, "audio/webm")},
                     data={"target": target, "stage": str(stage), "loudness": loud, "duration": "1.0",
                           "voiced_duration": "0.8", "probe": str(probe), "review": str(review)})
        b = res.json()
        return {"status": res.status_code, "score": b.get("score"), "passed": b.get("passed"), "progress": b.get("progress"),
                "probe": b.get("probe"), "counted": b.get("probe_counted"), "note": b.get("note")}

    def swap_onset(word):
        # 첫 음절 첫소리만 바꾼 말(물 → 불): 낱말 점수는 높지만 목표 소리가 틀렸다
        code = ord(word[0]) - 0xAC00
        onset, rest = code // 588, code % 588
        return chr(0xAC00 + (7 if onset != 7 else 6) * 588 + rest) + word[1:]

    async def bump(stage, seq):
        async with database.AsyncSessionLocal() as db:
            for ok in seq:
                sp = await main._bump_speak_progress(uid, stage, ok, 8, 85.0, db)
            await db.commit()
            return [sp.status, sp.attempts, round(sp.mastery_score, 4)]

    async def rows(stage):
        async with database.AsyncSessionLocal() as db:
            sp = (await db.execute(select(SpeakStageProgress).where(SpeakStageProgress.user_id == uid,
                                                                    SpeakStageProgress.stage == stage))).scalars().first()
            modes = [m for (m,) in (await db.execute(select(SpeakAttempt.mode).where(
                SpeakAttempt.user_id == uid, SpeakAttempt.stage == stage).order_by(SpeakAttempt.id))).all()]
            return {"status": sp.status, "attempts": sp.attempts, "mastery": round(sp.mastery_score, 4), "modes": modes}

    # 처음(이동 평균 전): 확인 낱말 없음. 확인 상태가 아닐 때 probe=1은 보통 시도로 채점한다
    d0 = c.get("/api/speak/stage/3", headers=h).json()
    out["before"] = {"carryover": d0["carryover"], "probes": d0["probes"]}
    out["early_probe"] = assess("마", 3, "마", probe=1)
    async def wipe3():
        async with database.AsyncSessionLocal() as db:
            from sqlalchemy import delete
            await db.execute(delete(SpeakAttempt).where(SpeakAttempt.user_id == uid))
            await db.execute(delete(SpeakStageProgress).where(SpeakStageProgress.user_id == uid))
            await db.commit()
    asyncio.run(wipe3())
    # 이동 평균 조건을 채움(8번 모두 합격) → 확인 전이라 숙달이 아니다
    out["gate"] = asyncio.run(bump(3, [True] * 8))
    d1 = c.get("/api/speak/stage/3", headers=h).json()
    d1b = c.get("/api/speak/stage/3", headers=h).json()
    out["probes"] = d1["probes"]
    out["carryover"] = d1["carryover"]
    out["same_day_same"] = d1["probes"] == d1b["probes"]
    w = d1["probes"][0]["target"]
    # 오늘 확인 낱말이 아닌 말을 probe=1로 보내면 확인으로 세지 않는다(보통 시도로 채점, mode 'phoneme')
    # 고른 말이 날짜에 따라 오늘·어제의 확인 낱말과 겹치지 않게, 서버와 같은 seed로 확인 낱말이 아닌 말을 고른다
    import speak_curriculum as _sc
    _t = main._kst_today()
    fw = next(x for x in ["사과", "바다", "나무", "우유", "모자", "아기", "구두", "포도"]
              if not any(_sc.is_probe_word(3, x, f"{uid}:3:{d.isoformat()}") for d in (_t, _t - datetime.timedelta(days=1))))
    out["foreign"] = assess(fw, 3, fw, probe=1)
    # 소리 없는 확인은 세지 않는다(창에서 빠짐)
    out["silent"] = assess(w, 3, "", probe=1, loud="0")
    # 첫 음절 첫소리가 틀린 확인(물 → 불): 낱말 점수는 합격선 위지만 불합격
    out["swapped"] = assess(w, 3, swap_onset(w), probe=1)
    out["after_extra"] = asyncio.run(rows(3))
    async def drop_extra():
        async with database.AsyncSessionLocal() as db:
            from sqlalchemy import delete
            ids = [i for (i,) in (await db.execute(select(SpeakAttempt.id).where(SpeakAttempt.user_id == uid)
                                                  .order_by(SpeakAttempt.id.desc()).limit(3))).all()]
            await db.execute(delete(SpeakAttempt).where(SpeakAttempt.id.in_(ids)))
            await db.commit()
    asyncio.run(drop_extra())   # 아래 창 계산을 단순하게 하려고 방금 세 시도를 지운다
    # 확인: 합격·불합격·불합격(1/3) → 숙달 아님, 이어서 합격(최근 3번 F F T 1/3), 합격(F T T 2/3) → 숙달
    seq = []
    for ok in (True, False, False):
        seq.append(assess(w, 3, w if ok else "아", probe=1))
    out["after_1_of_3"] = asyncio.run(rows(3))
    seq.append(assess(w, 3, w, probe=1))
    out["after_F_F_T"] = asyncio.run(rows(3))
    seq.append(assess(w, 3, w, probe=1))
    out["after_2_of_3"] = asyncio.run(rows(3))
    out["seq"] = seq
    d2 = c.get("/api/speak/stage/3", headers=h).json()
    out["after_mastered"] = {"carryover": d2["carryover"], "probes": d2["probes"]}
    # 모음 단계: 복습 세션의 확인 플래그는 확인으로 세지 않는다
    out["gate2"] = asyncio.run(bump(2, [True] * 8))
    out["review_probe"] = assess("배추", 2, "배추", probe=1, review=1)
    out["review_rows"] = asyncio.run(rows(2))
    # 이미 숙달한 단계(예전 자료)는 확인 없이도 숙달을 유지한다
    async def legacy():
        async with database.AsyncSessionLocal() as db:
            sp = (await db.execute(select(SpeakStageProgress).where(SpeakStageProgress.user_id == uid,
                                                                    SpeakStageProgress.stage == 2))).scalars().first()
            sp.status = "mastered"
            await db.commit()
    asyncio.run(legacy())
    out["legacy"] = asyncio.run(bump(2, [False, False]))
    d3 = c.get("/api/speak/stage/2", headers=h).json()
    out["legacy_stage"] = {"carryover": d3["carryover"], "probes": d3["probes"]}
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


def _run():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1",
                   ANTHROPIC_API_KEY="")
        for k in ("DGOP_ALIGNER_ID", "DGOP_SCORER_ID", "DGOP_MODEL_ID", "LIPLAB_AV_FUSION"):
            env.pop(k, None)
        p = subprocess.run([sys.executable, "-c", _SCENARIO], cwd=here, env=env, capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    return json.loads(line[len("RESULT "):])


def test_probe_gate_through_api():
    r = _run()
    assert r["before"] == {"carryover": False, "probes": []}
    assert r["early_probe"]["probe"] is False and r["early_probe"]["passed"] is True   # 확인 상태 전: 보통 시도
    status, attempts, mastery = r["gate"]
    assert status == "in_progress" and attempts == 8 and mastery >= 85      # 이동 평균만으로는 숙달하지 않는다
    assert r["carryover"] is True and r["same_day_same"]
    assert len(r["probes"]) == 3 and len({p["sound"] for p in r["probes"]}) == 3
    for s in r["seq"]:
        assert s["status"] == 200 and s["probe"] is True and s["counted"] is True
    # 오늘 확인 낱말이 아니면 보통 시도, 소리 없음은 세지 않음, 첫소리가 틀리면 점수가 높아도 불합격
    assert r["foreign"]["probe"] is False and r["foreign"]["progress"]["attempts"] == attempts + 1
    assert r["silent"]["probe"] is True and r["silent"]["counted"] is False and r["silent"]["passed"] is False
    sw = r["swapped"]
    assert sw["probe"] is True and sw["counted"] is True and sw["passed"] is False and sw["score"] >= 50
    assert "첫소리" in sw["note"]
    assert r["after_extra"]["modes"][-3:] == ["phoneme", "probe", "probe"]
    attempts, mastery = r["after_extra"]["attempts"], r["after_extra"]["mastery"]   # 보통 시도 한 번이 더해졌다
    # 합격 = 이 단계 합격선(50) 이상 + 첫 음절 목표 소리: 맞게 들리면 합격, '아'면 불합격
    assert [s["passed"] for s in r["seq"]] == [True, False, False, True, True]
    assert r["seq"][0]["score"] >= 50 and r["seq"][1]["score"] < 50
    # 1/3 → 숙달 아님. 확인은 이동 평균·시도 수를 바꾸지 않고 mode 'probe'로 남는다
    a = r["after_1_of_3"]
    assert a["status"] == "in_progress" and a["attempts"] == attempts and a["mastery"] == mastery
    assert a["modes"] == ["probe"] * 3
    assert r["after_F_F_T"]["status"] == "in_progress"
    assert r["seq"][2]["progress"]["probe"] == {"carryover": True, "passed": 1, "tried": 3, "n": 3, "need": 2}
    # 최근 3번 중 2번 → 숙달
    m = r["after_2_of_3"]
    assert m["status"] == "mastered" and m["attempts"] == attempts and m["mastery"] == mastery
    assert r["seq"][-1]["progress"]["mastered"] is True and r["seq"][-1]["progress"]["probe"]["carryover"] is False
    assert r["after_mastered"] == {"carryover": False, "probes": []}
    # 복습 세션: 진행도·확인 기록을 건드리지 않는다
    assert r["review_probe"]["progress"] is None
    assert r["review_rows"]["status"] == "in_progress" and "probe" not in r["review_rows"]["modes"]
    # 예전에 숙달한 단계는 확인 없이도, 오답이 이어져도 숙달 유지
    assert r["legacy"][0] == "mastered"
    assert r["legacy_stage"] == {"carryover": False, "probes": []}


# 리뷰어 재현 쌍(probe_score.py): 첫 음절 목표 소리가 바뀌면 낱말 점수가 높아도 불합격
_SWAPS = [("물", "불", 3), ("바다", "마다", 3), ("사과", "다과", 3), ("토기", "도기", 3), ("장갑", "창갑", 3), ("파도", "바도", 3),
          ("불", "발", 2), ("언니", "안니", 2), ("노래", "누래", 2), ("그림", "기림", 2), ("머리", "모리", 2), ("발", "벌", 2)]
_VOICED = {"loudness": 30, "voiced_duration": 1.0}


def test_score_probe_transcript_checks_target_sound():
    for target, said, st in _SWAPS:
        score, passed, note, counted = sc.score_probe(st, target, said, _VOICED, 88.0)
        assert counted and not passed and note, (target, said)
        score, passed, note, counted = sc.score_probe(st, target, target, _VOICED, 88.0)
        assert counted and passed and not note, target
    assert sc.score_probe(2, "배추", "베추", _VOICED, 80.0)[1]            # 애·에는 한 소리
    assert not sc.score_probe(3, "물", "물", _VOICED, 45.0)[1]           # 합격선(50) 아래
    assert sc.score_probe(3, "물", "물", _VOICED, 50.0)[1]
    assert sc.score_probe(3, "물", "", {"loudness": 0}, 0.0) == (0.0, False, sc.NO_VOICE_NOTE, False)   # 소리 없음은 세지 않음


def test_score_probe_dgop_threshold_and_alignment_failure():
    import jamo_vocab
    def phones(word, **over):
        ps = [{"token": tk, "aligned": True, "scorable": True, "dgop": 0.3} for tk in jamo_vocab.text_to_tokens(word)]
        for i, kv in over.items():
            ps[int(i[1:])].update(kv)
        return ps
    assert sc.PROBE_DGOP_MIN == 0.05
    assert sc.score_probe(3, "물", None, _VOICED, 70.0, phones("물"))[1:] == (True, "", True)
    r = sc.score_probe(3, "물", None, _VOICED, 70.0, phones("물", i0={"dgop": 0.04}))
    assert r[1] is False and r[3] is True                                  # 첫소리 D-GOP 0.05 미만
    assert sc.score_probe(2, "물", None, _VOICED, 70.0, phones("물", i0={"dgop": 0.01}))[1]   # 모음 단계는 모음만 본다
    assert not sc.score_probe(2, "물", None, _VOICED, 70.0, phones("물", i1={"dgop": 0.01}))[1]
    assert not sc.score_probe(3, "물", None, _VOICED, 45.0, phones("물"))[1]                 # 합격선(50) 아래
    # 목표 음소를 찾지 못하면 합격이 아니고 창에도 세지 않는다
    for bad in (phones("물", i0={"aligned": False}), phones("불"), [], None,
                [{"token": "물", "aligned": True, "dgop": 0.9}]):        # 음절 vocab 모델
        assert sc.score_probe(3, "물", None, _VOICED, 90.0, bad)[1:] == (False, sc.PROBE_UNCOUNTED_NOTE, False)


def test_is_probe_word_matches_issued_words_regardless_of_weak_order():
    seed = "7:3:2026-09-28"
    issued = {p["target"] for w in (None, ["ㅋ"], ["ㅅ", "ㅎ"], ["ㅁ"]) for p in sc.probe_words(3, seed, weak=w)}
    assert issued and all(sc.is_probe_word(3, w, seed) for w in issued)
    assert not sc.is_probe_word(3, "마", seed)                 # 이 단계 문항
    assert not sc.is_probe_word(3, "아기", seed)               # 목표 소리 없음(무음 첫소리)
    others = [w for w in sc._STAGE4_WORDS if sc.probe_sound(3, w) and not sc.is_probe_word(3, w, seed)]
    assert len(others) > 50                                    # 풀의 다른 낱말은 확인이 아니다
    assert all(sc.is_probe_word(2, p["target"], "7:2:d") for p in sc.probe_words(2, "7:2:d", weak=["ㅔ"]))
