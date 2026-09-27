"""켜질 때 사용자별 기록 표에 (user_id, created_at) 인덱스가 생긴다(database._user_indexes).

예전에는 id 인덱스뿐이라 분석 탭·리포트가 요청마다 표 전체를 훑었다(20만 행에서 사용자 하나 조회 6.5ms → 0.14ms).
임시 DB를 쓰는 별도 프로세스에서 돈다.
"""
import json
import os
import subprocess
import sys
import tempfile

_FLOW = r'''
import asyncio, json, sqlite3, os
import database as D
asyncio.run(D.init_db())
asyncio.run(D.init_db())   # 두 번 켜도 문제없다(IF NOT EXISTS)
con = sqlite3.connect(os.environ["DB_FILE"])
names = [r[0] for r in con.execute("select name from sqlite_master where type='index'")]
plan = con.execute("explain query plan select correct from trial_attempts where user_id = 1 order by created_at").fetchall()
print("RESULT " + json.dumps({"names": names, "plan": [p[-1] for p in plan]}))
'''


def test_user_indexes_created_on_startup():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "t.db")
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{f}", DB_FILE=f, PYTHONDONTWRITEBYTECODE="1")
        p = subprocess.run([sys.executable, "-c", _FLOW], cwd=here, env=env, capture_output=True, text=True, timeout=120)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])
    for name in ("ix_progress_user_id_created_at", "ix_trial_attempts_user_id_created_at",
                 "ix_speak_attempts_user_id_created_at", "ix_placement_results_user_id_created_at"):
        assert name in r["names"], name
    assert any("USING INDEX ix_trial_attempts_user_id_created_at" in s for s in r["plan"]), r["plan"]
