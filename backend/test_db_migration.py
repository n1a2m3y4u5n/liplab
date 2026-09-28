"""경량 마이그레이션(database._add_missing_columns): 없는 컬럼만 더하고, 한 문장의 실패가 뒤 문장을 막지 않는다.

예전에는 ALTER를 한 트랜잭션에서 모두 돌리고 실패를 try/except pass로 넘겨, PostgreSQL에서는 첫 '이미 있음' 실패 뒤의 ALTER가 모두
'current transaction is aborted'로 조용히 실패했다. PostgreSQL이 없어 그 동작을 흉내 낸 가짜 연결로 확인하고, SQLite는 실제로 돌린다.
"""
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from types import SimpleNamespace

import database as D


class _FakePG:
    """PostgreSQL 트랜잭션 흉내: 한 문장이 실패하면 SAVEPOINT로 되돌리기 전까지 뒤 문장이 모두 실패한다."""
    dialect = SimpleNamespace(name="postgresql")

    def __init__(self, have, fail_on):
        self.have, self.fail_on, self.aborted, self.done = have, fail_on, False, []

    async def run_sync(self, fn):
        return self.have

    async def exec_driver_sql(self, sql):
        if self.aborted:
            raise RuntimeError("current transaction is aborted")
        if self.fail_on in sql:
            self.aborted = True
            raise RuntimeError("boom")
        self.done.append(sql)

    def begin_nested(self):
        conn = self

        class _SP:
            async def __aenter__(self):
                return self

            async def __aexit__(self, et, ev, tb):
                if et is not None:
                    conn.aborted = False   # ROLLBACK TO SAVEPOINT
                return False
        return _SP()


def test_failing_first_alter_does_not_abort_later_ones():
    cols = (("t", "a", "INTEGER"), ("t", "b", "INTEGER"), ("u", "c", "FLOAT"))
    conn = _FakePG({"t": {"id"}, "u": {"id"}}, fail_on=" a ")
    added = asyncio.run(D._add_missing_columns(conn, cols))
    assert added == [("t", "b"), ("u", "c")]
    assert not conn.aborted
    assert conn.done == ["ALTER TABLE t ADD COLUMN b INTEGER", "ALTER TABLE u ADD COLUMN c FLOAT"]


def test_existing_columns_and_missing_tables_are_skipped():
    cols = (("t", "a", "INTEGER"), ("t", "b", "INTEGER"), ("gone", "c", "FLOAT"))
    conn = _FakePG({"t": {"id", "a"}}, fail_on="never")
    assert asyncio.run(D._add_missing_columns(conn, cols)) == [("t", "b")]
    assert conn.done == ["ALTER TABLE t ADD COLUMN b INTEGER"]


_FLOW = r'''
import asyncio, json, os, sqlite3
f = os.environ["DB_FILE"]
con = sqlite3.connect(f)
# 예전 스키마: speak_attempts에 나중에 생긴 컬럼이 없다
con.execute("CREATE TABLE speak_attempts (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, stage INTEGER, mode VARCHAR(20), "
            "target VARCHAR(200) NOT NULL, transcript VARCHAR(200), score FLOAT, passed BOOLEAN, loudness FLOAT, "
            "pitch_range FLOAT, duration FLOAT, pitch_start FLOAT, pitch_end FLOAT, confusions JSON, created_at DATETIME)")
con.commit(); con.close()
import database as D
asyncio.run(D.init_db())
asyncio.run(D.init_db())   # 두 번 켜도 문제없다
cols = [r[1] for r in sqlite3.connect(f).execute("PRAGMA table_info(speak_attempts)")]
print("RESULT " + json.dumps({"cols": cols}))
'''


def test_sqlite_old_schema_gets_new_columns():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "t.db")
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{f}", DB_FILE=f, PYTHONDONTWRITEBYTECODE="1")
        p = subprocess.run([sys.executable, "-c", _FLOW], cwd=here, env=env, capture_output=True, text=True, timeout=120)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    cols = json.loads(line[len("RESULT "):])["cols"]
    want = [c for t, c, _ in D._ADD_COLUMNS if t == "speak_attempts"]
    assert want and all(c in cols for c in want), cols
    assert "컬럼 추가 실패" not in p.stdout
