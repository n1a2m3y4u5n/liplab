"""사전·사후 향상도는 같은 폼 판본끼리만 동형 비교로 친다(9/27 v2, docs/assessment-design.md 7절)."""
import json
import os
import subprocess
import sys
import tempfile

_FLOW = r'''
import asyncio, json
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
import main, database
from database import PlacementResult

out = {}
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "fv@example.com", "username": "fv1", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    uid = c.get("/api/auth/me", headers=h).json()["id"]
    t0 = datetime.utcnow() - timedelta(days=10)

    async def add(rows):
        async with database.AsyncSessionLocal() as db:
            for i, (form, ver, acc) in enumerate(rows):
                db.add(PlacementResult(user_id=uid, form=form, form_version=ver, total=24, correct=int(acc * 24),
                                       accuracy=acc, ability=0.5, level=2, error_visemes=[], error_phonemes=[],
                                       item_log=[], created_at=t0 + timedelta(days=i)))
            await db.commit()

    asyncio.run(add([("A", "v1", 0.5), ("B", "v2", 0.7)]))
    out["mixed"] = c.get("/api/assessment/progression", headers=h).json()
    asyncio.run(add([("B", "v1", 0.6)]))   # 같은 판본(v1)의 사후가 생기면 그것과 비교한다
    out["same"] = c.get("/api/assessment/progression", headers=h).json()
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


def test_progression_pairs_same_form_version():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1")
        env.pop("ANTHROPIC_API_KEY", None)
        p = subprocess.run([sys.executable, "-c", _FLOW], cwd=here, env=env, capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])
    m = r["mixed"]
    assert m["available"] and m["homogeneous"] is False and m["form_versions"] == ["v1", "v2"], m
    s = r["same"]
    assert s["homogeneous"] is True and s["form_versions"] == ["v1", "v1"] and abs(s["accuracy_delta"] - 0.1) < 1e-9, s
