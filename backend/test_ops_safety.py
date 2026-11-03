"""11/03 검토 묶음 C: 파괴적 마이그레이션 전 사본, 사본 보존 개수, /health/ready."""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile

import ops_safety

KEYS = (("stage_progress", "user_id, stage", "id DESC"),)


def _make_db(path, dup=False, usage_notnull=False):
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE stage_progress (id INTEGER PRIMARY KEY, user_id INTEGER, stage INTEGER)")
    c.executemany("INSERT INTO stage_progress (user_id, stage) VALUES (?, ?)", [(1, 1), (1, 2)] + ([(1, 1)] if dup else []))
    if usage_notnull:
        c.execute("CREATE TABLE usage_events (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL)")
    c.commit()
    c.close()


def test_no_backup_when_nothing_destructive(tmp_path):
    db = str(tmp_path / "t.db")
    _make_db(db)
    assert ops_safety.backup_before_migration(db, KEYS) is None
    assert not (tmp_path / "backup").exists()


def test_no_backup_when_db_missing(tmp_path):
    assert ops_safety.backup_before_migration(str(tmp_path / "none.db"), KEYS) is None


def test_backup_made_before_dedupe_and_is_a_readable_copy(tmp_path):
    db = str(tmp_path / "t.db")
    _make_db(db, dup=True)
    dest = ops_safety.backup_before_migration(db, KEYS)
    assert dest and os.path.dirname(dest) == str(tmp_path / "backup")
    c = sqlite3.connect(dest)
    assert c.execute("SELECT COUNT(*) FROM stage_progress").fetchone()[0] == 3   # 지우기 전 상태
    c.close()


def test_backup_made_before_usage_rebuild(tmp_path):
    db = str(tmp_path / "t.db")
    _make_db(db, usage_notnull=True)
    assert ops_safety.backup_before_migration(db, KEYS)


def test_only_latest_three_backups_kept(tmp_path):
    db = str(tmp_path / "t.db")
    _make_db(db, dup=True)
    d = tmp_path / "backup"
    d.mkdir()
    for i in range(5):
        (d / f"pre-2026010{i + 1}T000000Z.db").write_bytes(b"x")
    ops_safety.backup_before_migration(db, KEYS, keep=3)
    names = sorted(os.listdir(d))
    assert len(names) == 3 and names[0] == "pre-20260104T000000Z.db"   # 가장 오래된 것부터 지워졌다(옛 5개 + 새 1개 중 최근 3개)


def test_sqlite_path_parsing():
    assert ops_safety.sqlite_path("sqlite+aiosqlite:////data/liplab.db") == "/data/liplab.db"
    assert ops_safety.sqlite_path("sqlite+aiosqlite:///./liplab.db") == "./liplab.db"
    assert ops_safety.sqlite_path("sqlite+aiosqlite:///:memory:") is None
    assert ops_safety.sqlite_path("postgresql+asyncpg://u@h/db") is None


_FLOW = r'''
import json, os
from fastapi.testclient import TestClient
import main, ops_safety
out = {}
with TestClient(main.app) as c:
    r = c.get("/health/ready"); out["ready"] = [r.status_code, r.json()["status"], r.json()["checks"]["db"], r.json()["checks"]["data"]["writable"]]
    out["text_has_path"] = os.environ["DATABASE_URL"].split("///")[-1] in r.text
    ops_safety.MIGRATION_WARNINGS.append("w")
    r = c.get("/health/ready"); out["degraded"] = [r.status_code, r.json()["status"], r.json()["schema_warnings"]]
    ops_safety.MIN_FREE_BYTES = 1 << 62
    r = c.get("/health/ready"); out["nospace"] = [r.status_code, r.json()["status"]]
    out["health"] = c.get("/health").json()["status"]
print("RESULT " + json.dumps(out))
'''


def test_health_ready_states():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
        p = subprocess.run([sys.executable, "-c", _FLOW], cwd=here, env=env, capture_output=True, text=True, timeout=300)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, p.stdout[-1500:] + p.stderr[-2500:]
    o = json.loads(line[7:])
    assert o["ready"] == [200, "ready", True, True]
    assert o["text_has_path"] is False
    assert o["degraded"] == [200, "degraded", 1]
    assert o["nospace"] == [503, "not_ready"]
    assert o["health"] == "healthy"
