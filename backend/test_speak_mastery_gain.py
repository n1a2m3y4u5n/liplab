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
                db.add(SpeakAttempt(user_id=uid, stage=4, mode="word", target="밥", score=sc, passed=False))
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
