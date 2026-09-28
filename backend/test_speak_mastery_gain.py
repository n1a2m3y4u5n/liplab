"""말하기 4·5단계 숙달 문턱(77)과 개인 향상 경로(9/28, docs/curriculum-roadmap.md 2-1)."""
import speak_curriculum as sc


def test_stage4_5_threshold_reachable_by_hearing_impaired_readers():
    # 608 청각장애 화자가 대본을 읽은 문장의 65점 합격률 82.2% − 5점 = 77
    for n in (4, 5):
        stg = sc.get_stage(n)
        assert stg["mastery"] == 77.0 and stg["pass"] == 65.0 and stg["gain"]


def test_gain_mastered_needs_enough_attempts_and_clear_improvement():
    g = sc.get_stage(4)["gain"]
    assert not sc.gain_mastered([40] * 10 + [60] * 9, g)          # 19번: 시도 부족
    assert sc.gain_mastered([40] * 10 + [60] * 10, g)             # +20
    assert not sc.gain_mastered([40] * 10 + [52] * 10, g)         # +12: 향상 부족
    assert sc.gain_mastered([30, 40, 50] * 4 + [58] * 10, g)      # 처음 10번 중앙값 40 → 58
    assert not sc.gain_mastered([40] * 30, g)
    assert not sc.gain_mastered([40] * 30, None)
    assert not sc.gain_mastered([None] * 25, g)


def test_gain_mastered_absolute_floor():
    # 리뷰 뒤 고침: 최근 10번 중앙값이 합격선 − 15(합격 65면 50) 이상이어야 한다
    g = sc.get_stage(4)["gain"]
    assert g["floor"] == 15.0
    assert not sc.gain_mastered([20] * 10 + [40] * 10, g, 65.0)   # +20이지만 최근 40 < 50
    assert not sc.gain_mastered([0] * 10 + [30] * 10, g, 65.0)    # 리뷰어 사례: 기준선 0, 늘 30
    assert sc.gain_mastered([30] * 10 + [50] * 10, g, 65.0)       # 하한 50에 딱 닿음
    assert sc.gain_mastered([40] * 10 + [60] * 10, g, 65.0)


def test_voiced_attempt():
    assert sc.voiced_attempt(50, "사과", 80) and sc.voiced_attempt(50, None, 30)   # D-GOP 경로는 전사가 None
    assert not sc.voiced_attempt(0, "사과", 80)          # 크기 0(micIssue, 예전 클라이언트)
    assert not sc.voiced_attempt(None, None, 40)
    assert not sc.voiced_attempt(50, "", 0)              # 전사 경로 소리 없음
    assert sc.voiced_attempt(50, "", 5)


def test_bump_speak_progress_uses_gain_path():
    # 합격(65)은 한 번도 못 했지만 점수가 40 → 60으로 오른 학습자: 절대 문턱은 못 넘고 향상 경로로 숙달
    import asyncio, os, subprocess, sys, tempfile, json
    here = os.path.dirname(os.path.abspath(__file__))
    code = r'''
import asyncio, json
from fastapi.testclient import TestClient
import database, main
from database import SpeakAttempt
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "g@example.com", "username": "gainu", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    uid = c.get("/api/auth/me", headers=h).json()["id"]
    async def run():
        out = []
        async with database.AsyncSessionLocal() as db:
            for i in range(22):
                sc = 40.0 if i < 10 else 60.0
                sp = await main._bump_speak_progress(uid, 4, False, 8, 77.0, db, score=sc)
                db.add(SpeakAttempt(user_id=uid, stage=4, mode="word", target="밥", score=sc, passed=False, loudness=50.0))
                await db.commit()
                out.append(sp.status)
        return out
    res = asyncio.run(run())
print("RESULT " + json.dumps(res))
'''
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1")
        env.pop("ANTHROPIC_API_KEY", None)
        p = subprocess.run([sys.executable, "-c", code], cwd=here, env=env, capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, p.stderr[-2000:]
    st = json.loads(line[7:])
    assert st[18] == "in_progress"      # 19번째: 시도 부족
    assert st[19] == "mastered"         # 20번째: 처음 10번 40, 최근 10번 60
    assert st[-1] == "mastered"


_LEAK = r'''
import asyncio, json
from fastapi.testclient import TestClient
import database, main
from database import SpeakAttempt, SpeakStageProgress
from sqlalchemy import select, delete
out = {}
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "g@example.com", "username": "gainu", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    uid = c.get("/api/auth/me", headers=h).json()["id"]
    # 리뷰어 재현: 복습 세션(review=1)에서 4단계 문항 10번, 소리 없음(점수 0). 진행도는 안 건드린다
    for i in range(10):
        rr = c.post("/api/speak/assess", headers=h,
                    data={"target": "사과", "stage": "4", "review": "1", "loudness": "0", "voiced_duration": "0"},
                    files={"audio": ("a.webm", b"\x00" * 2000, "audio/webm")})
        assert rr.status_code == 200, rr.text

    async def reset():
        async with database.AsyncSessionLocal() as db:
            await db.execute(delete(SpeakStageProgress).where(SpeakStageProgress.user_id == uid))
            await db.commit()

    async def run(seq, pre=()):
        out = []
        async with database.AsyncSessionLocal() as db:
            for kw in pre:
                db.add(SpeakAttempt(user_id=uid, stage=4, mode="word", target="밥", passed=False, **kw))
            await db.commit()
            for sc in seq:
                sp = await main._bump_speak_progress(uid, 4, False, 8, 77.0, db, score=sc)
                db.add(SpeakAttempt(user_id=uid, stage=4, mode="word", target="밥", score=sc, passed=False, loudness=50.0))
                await db.commit()
                out.append(sp.status)
        return out

    async def flags():
        async with database.AsyncSessionLocal() as db:
            return [x for (x,) in (await db.execute(select(SpeakAttempt.review).where(SpeakAttempt.user_id == uid)
                                                    .order_by(SpeakAttempt.id))).all()]
    out["review_flags"] = asyncio.run(flags())
    # 1) 복습 무음 10번 뒤 정규 시도 20번 모두 30점: 예전에는 기준선 0 → 30으로 숙달
    out["review_then_30"] = asyncio.run(run([30.0] * 20))
    # 2) 정규 시도지만 소리 없음(크기 0, 전사 빈 문자열, 점수 0) 10번 뒤 55점: 예전에는 기준선 0 → 55로 숙달
    async def wipe():
        async with database.AsyncSessionLocal() as db:
            await db.execute(delete(SpeakAttempt).where(SpeakAttempt.user_id == uid))
            await db.execute(delete(SpeakStageProgress).where(SpeakStageProgress.user_id == uid))
            await db.commit()
    asyncio.run(wipe())
    out["novoice_then_55"] = asyncio.run(run([55.0] * 20, pre=[{"score": 0.0, "loudness": 0.0, "transcript": ""}] * 5
                                             + [{"score": 0.0, "loudness": 40.0, "transcript": ""}] * 5))
    # 3) 소리가 잡힌 복습 시도(낮은 점수)도 기준선에 넣지 않는다
    asyncio.run(wipe())
    out["voiced_review_then_55"] = asyncio.run(run([55.0] * 20, pre=[{"score": 20.0, "loudness": 40.0, "review": True}] * 10))
    # 4) 향상은 있지만 최근 중앙값이 하한(50) 아래
    asyncio.run(wipe())
    out["low_gain"] = asyncio.run(run([20.0] * 10 + [40.0] * 10))
    # 5) 정당한 향상 40 → 60, 앞에 복습·무음 기록이 섞여도 숙달한다
    asyncio.run(wipe())
    out["legit"] = asyncio.run(run([40.0] * 10 + [60.0] * 10, pre=[{"score": 0.0, "loudness": 0.0, "transcript": ""},
                                                               {"score": 90.0, "loudness": 50.0, "review": True}]))
print("RESULT " + json.dumps(out))
'''


def test_gain_path_ignores_review_and_silent_attempts():
    import json, os, subprocess, sys, tempfile
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1")
        env.pop("ANTHROPIC_API_KEY", None)
        for k in ("DGOP_ALIGNER_ID", "DGOP_SCORER_ID", "DGOP_MODEL_ID"):
            env.pop(k, None)
        p = subprocess.run([sys.executable, "-c", _LEAK], cwd=here, env=env, capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, p.stdout[-2000:] + p.stderr[-3000:]
    r = json.loads(line[7:])
    assert r["review_flags"] == [True] * 10                       # 복습 세션 시도는 review로 남는다
    assert "mastered" not in r["review_then_30"]
    assert "mastered" not in r["novoice_then_55"]
    assert "mastered" not in r["voiced_review_then_55"]
    assert "mastered" not in r["low_gain"]
    assert r["legit"][18] == "in_progress" and r["legit"][19] == "mastered"


def test_interleaved_order_after_one_pass():
    items = sc.get_stage(3)["items"]
    assert sc.interleaved_order(items, len(items) - 1, "u:3:d") == items          # 한 바퀴 전: 원래 순서
    mixed = sc.interleaved_order(items, len(items), "u:3:d")
    assert sorted(i["target"] for i in mixed) == sorted(i["target"] for i in items) and mixed != items
    assert mixed == sc.interleaved_order(items, 50, "u:3:d")                        # 같은 날 같은 순서
