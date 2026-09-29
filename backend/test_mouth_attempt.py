"""웹캠 입모양 익힘 기록(/api/curriculum/mouth-attempt): 입모양 그룹 1~10과 0~100 점수만 받는다."""
import json
import os
import subprocess
import sys
import tempfile

_FLOW = r'''
import asyncio, json
from fastapi.testclient import TestClient
import main, database
out = {}
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "ma@example.com", "username": "mau", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    post = lambda body: c.post("/api/curriculum/mouth-attempt", json=body, headers=h)
    out["v0"] = post({"viseme_id": 0, "score": 80}).status_code
    out["v11"] = post({"viseme_id": 11, "score": 80}).status_code
    out["v15"] = post({"viseme_id": 15, "score": 80}).status_code
    out["neg"] = post({"viseme_id": 2, "score": -1}).status_code
    out["over"] = post({"viseme_id": 2, "score": 101}).status_code
    ok1 = post({"viseme_id": 1, "score": 80})
    ok10 = post({"viseme_id": 10, "score": 30})
    out["ok1"] = [ok1.status_code, ok1.json().get("passed")]
    out["ok10"] = [ok10.status_code, ok10.json().get("passed")]
    uid = c.get("/api/auth/me", headers=h).json()["id"]

    async def weak_ids():
        from sqlalchemy import select
        async with database.AsyncSessionLocal() as db:
            r = await db.execute(select(database.WeakViseme.viseme_id).where(database.WeakViseme.user_id == uid))
            return sorted(r.scalars().all())
    out["weak_ids"] = asyncio.run(weak_ids())
print("RESULT " + json.dumps(out))
'''


def test_mouth_attempt_rejects_out_of_range():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1",
                   JWT_SECRET="test-only-mouth-attempt-secret")
        env.pop("ANTHROPIC_API_KEY", None)
        p = subprocess.run([sys.executable, "-c", _FLOW], cwd=here, env=env, capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])
    # 범위 밖 입모양 번호(0·11·15)와 0~100 밖 점수는 400으로 거절해 WeakViseme에 쌓지 않는다
    assert r["v0"] == 400 and r["v11"] == 400 and r["v15"] == 400
    assert r["neg"] == 400 and r["over"] == 400
    # 경계값 1·10은 받는다(합격선 60)
    assert r["ok1"] == [200, True] and r["ok10"] == [200, False]
    assert r["weak_ids"] == [1, 10]
