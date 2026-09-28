"""말하기 모음·자음(2·3단계) 낱말 속 소리 확인(docs/curriculum-roadmap.md 2-5, P9).

- 확인 낱말: 서로 다른 목표 소리, 첫 음절 위치, 1·2음절, 약한 소리 먼저, (사용자, 날짜) seed로 결정적, 애·에는 한 소리.
- 숙달: 이동 평균 조건 + 최근 4번 중 3번 합격. 확인은 이동 평균·시도 수를 바꾸지 않고, 이미 숙달한 단계는 그대로다.
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
    assert cfg == {"n": 4, "need": 3}
    assert sc.probes_ok([True, False, True, True], cfg)
    assert not sc.probes_ok([True, False, False, True], cfg)
    assert not sc.probes_ok([True, True], cfg)
    assert sc.probes_ok([False, False, True, True, True], cfg)     # 최근 4번만 본다
    assert not sc.probes_ok([True, True, True, False, False], cfg)
    assert sc.probes_ok([], None)


_SCENARIO = r'''
import asyncio, json
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

    def assess(target, stage, text, probe=0, review=0):
        heard["text"] = text
        res = c.post("/api/speak/assess", headers=h, files={"audio": ("a.webm", b"\x00" * 2048, "audio/webm")},
                     data={"target": target, "stage": str(stage), "loudness": "50", "duration": "1.0",
                           "voiced_duration": "0.8", "probe": str(probe), "review": str(review)})
        b = res.json()
        return {"status": res.status_code, "score": b.get("score"), "passed": b.get("passed"), "progress": b.get("progress")}

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

    # 처음(이동 평균 전): 확인 낱말 없음
    d0 = c.get("/api/speak/stage/3", headers=h).json()
    out["before"] = {"carryover": d0["carryover"], "probes": d0["probes"]}
    # 이동 평균 조건을 채움(8번 모두 합격) → 확인 전이라 숙달이 아니다
    out["gate"] = asyncio.run(bump(3, [True] * 8))
    d1 = c.get("/api/speak/stage/3", headers=h).json()
    d1b = c.get("/api/speak/stage/3", headers=h).json()
    out["probes"] = d1["probes"]
    out["carryover"] = d1["carryover"]
    out["same_day_same"] = d1["probes"] == d1b["probes"]
    w = d1["probes"][0]["target"]
    # 확인: 합격·불합격·불합격·합격(2/4) → 숙달 아님, 이어서 합격(최근 4번 F F T T 2/4), 합격(F T T T 3/4) → 숙달
    seq = []
    for ok in (True, False, False, True):
        seq.append(assess(w, 3, w if ok else "아", probe=1))
    out["after_2_of_4"] = asyncio.run(rows(3))
    seq.append(assess(w, 3, w, probe=1))
    out["after_F_F_T_T"] = asyncio.run(rows(3))
    seq.append(assess(w, 3, w, probe=1))
    out["after_3_of_4"] = asyncio.run(rows(3))
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
    status, attempts, mastery = r["gate"]
    assert status == "in_progress" and attempts == 8 and mastery >= 85      # 이동 평균만으로는 숙달하지 않는다
    assert r["carryover"] is True and r["same_day_same"]
    assert len(r["probes"]) == 4 and len({p["sound"] for p in r["probes"]}) == 4
    for s in r["seq"]:
        assert s["status"] == 200
    # 단어 규칙(합격 65)으로 채점: 맞게 들리면 합격, '아'면 불합격
    assert [s["passed"] for s in r["seq"]] == [True, False, False, True, True, True]
    assert r["seq"][0]["score"] >= 65 and r["seq"][1]["score"] < 65
    # 2/4 → 숙달 아님. 확인은 이동 평균·시도 수를 바꾸지 않고 mode 'probe'로 남는다
    a = r["after_2_of_4"]
    assert a["status"] == "in_progress" and a["attempts"] == attempts and a["mastery"] == mastery
    assert a["modes"] == ["probe"] * 4
    assert r["after_F_F_T_T"]["status"] == "in_progress"
    assert r["seq"][3]["progress"]["probe"] == {"carryover": True, "passed": 2, "tried": 4, "n": 4, "need": 3}
    # 최근 4번 중 3번 → 숙달
    m = r["after_3_of_4"]
    assert m["status"] == "mastered" and m["attempts"] == attempts and m["mastery"] == mastery
    assert r["seq"][-1]["progress"]["mastered"] is True and r["seq"][-1]["progress"]["probe"]["carryover"] is False
    assert r["after_mastered"] == {"carryover": False, "probes": []}
    # 복습 세션: 진행도·확인 기록을 건드리지 않는다
    assert r["review_probe"]["progress"] is None
    assert r["review_rows"]["status"] == "in_progress" and "probe" not in r["review_rows"]["modes"]
    # 예전에 숙달한 단계는 확인 없이도, 오답이 이어져도 숙달 유지
    assert r["legacy"][0] == "mastered"
    assert r["legacy_stage"] == {"carryover": False, "probes": []}
