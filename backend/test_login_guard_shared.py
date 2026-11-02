"""로그인 잠금은 DB를 공유하는 다른 프로세스와 동시 요청에서도 유지된다."""
import hashlib
import os
import subprocess
import sys
import tempfile

SCRIPT = r'''
import asyncio, json, os
from fastapi import HTTPException
from database import init_db, close_db, AsyncSessionLocal, LoginAttempt
from login_guard import reserve_attempt
from sqlalchemy import update
from datetime import datetime, timedelta

async def attempt():
    async with AsyncSessionLocal() as db:
        try:
            await reserve_attempt("shared@example.com", db)
            return 200
        except HTTPException as e:
            return e.status_code

async def run():
    await init_db()
    if os.environ.get("EXPIRE"):
        async with AsyncSessionLocal() as db:
            await db.execute(update(LoginAttempt).values(expires_at=datetime.utcnow()-timedelta(seconds=1)))
            await db.commit()
    statuses=await asyncio.gather(*(attempt() for _ in range(int(os.environ["ATTEMPTS"]))))
    print(json.dumps(sorted(statuses)))
    await close_db()
asyncio.run(run())
'''


def test_shared_atomic_login_budget():
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/lock.db",
                   JWT_SECRET=hashlib.sha256(b"isolated login guard fixture").hexdigest(),
                   PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
        def run(n, expire=False):
            import json
            r = subprocess.run([sys.executable, "-X", "utf8", "-c", SCRIPT],
                               cwd=os.path.dirname(__file__),
                               env=dict(env, ATTEMPTS=str(n), EXPIRE="1" if expire else ""),
                               capture_output=True, text=True, timeout=90)
            assert r.returncode == 0, r.stderr[-2000:]
            return json.loads(next(x for x in r.stdout.splitlines() if x.startswith("[")))
        assert run(3) == [200] * 3
        assert run(3) == [200, 200, 429]
        assert run(6, expire=True) == [200] * 5 + [429]
