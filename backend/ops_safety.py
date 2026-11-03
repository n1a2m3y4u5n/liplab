"""운영 안전장치(11/03 검토 묶음 C): 파괴적 마이그레이션 전 SQLite 사본, 마이그레이션 경고 기록, /health/ready 점검.

값(이메일·답)은 읽거나 기록하지 않는다. 행 수와 파일 크기만 다룬다.
"""
import os
import re
import shutil
import sqlite3
import time
from datetime import datetime, timezone
from typing import List, Optional

BACKUP_KEEP_DEFAULT = 3            # 보존할 사본 개수(보수적)
MIN_FREE_BYTES = 50 * 1024 * 1024  # /health/ready: 이보다 여유 공간이 적으면 준비 안 됨
MIGRATION_WARNINGS: List[str] = [] # 켜질 때 마이그레이션이 남긴 경고(첫 줄 요약만, 값 없음)


def record_warning(message: str) -> None:
    """마이그레이션 경고를 출력하고 /health/ready가 볼 수 있게 남긴다."""
    print(message)
    if len(MIGRATION_WARNINGS) < 50:
        MIGRATION_WARNINGS.append(message[:200])


def sqlite_path(url: str) -> Optional[str]:
    """sqlite(+aiosqlite):///경로 에서 파일 경로. 메모리 DB나 sqlite가 아니면 None."""
    m = re.match(r"^sqlite(?:\+\w+)?:///(.*)$", url or "")
    if not m:
        return None
    path = m.group(1).split("?", 1)[0]
    if not path or path == ":memory:":
        return None
    return path


def backup_dir_for(db_path: str) -> str:
    return os.getenv("LIPLAB_BACKUP_DIR") or os.path.join(os.path.dirname(os.path.abspath(db_path)), "backup")


def _table_exists(c: sqlite3.Connection, name: str) -> bool:
    return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def destructive_pending(db_path: str, unique_keys) -> dict:
    """켜질 때 행을 지우거나 표를 다시 만들 일이 있는지 센다. 있으면 {이유: 행 수} (없으면 빈 dict)."""
    out = {}
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as c:
        if _table_exists(c, "usage_events"):
            cols = c.execute("PRAGMA table_info(usage_events)").fetchall()
            uid = [col for col in cols if col[1] == "user_id"]
            if uid and uid[0][3] == 1:   # notnull
                out["usage_events 표 재구성"] = c.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0]
        for table, key, _order in unique_keys:
            if not _table_exists(c, table):
                continue
            n = c.execute(f"SELECT COALESCE(SUM(cnt - 1), 0) FROM (SELECT COUNT(*) AS cnt FROM {table} GROUP BY {key} HAVING COUNT(*) > 1)").fetchone()[0]
            if n:
                out[f"{table} 중복 행 삭제"] = n
    return out


def prune_backups(directory: str, keep: int) -> List[str]:
    """pre-*.db 중 최근 keep개만 남기고 지운다. 지운 파일 이름 목록."""
    files = sorted(f for f in os.listdir(directory) if re.fullmatch(r"pre-\d{8}T\d{6}Z\.db", f))
    removed = files[:-keep] if keep > 0 else files
    for f in removed:
        try:
            os.remove(os.path.join(directory, f))
        except OSError:
            pass
    return removed


def backup_before_migration(db_path: str, unique_keys, keep: Optional[int] = None) -> Optional[str]:
    """파괴적 마이그레이션이 필요할 때만 VACUUM INTO로 사본을 남긴다. 만든 사본 경로(없으면 None).
    DB가 아직 없거나 할 일이 없으면 만들지 않는다. 사본을 못 만들면 경고만 남기고 켜지는 것은 막지 않는다."""
    if keep is None:
        keep = int(os.getenv("LIPLAB_BACKUP_KEEP", str(BACKUP_KEEP_DEFAULT)) or BACKUP_KEEP_DEFAULT)
    try:
        if not os.path.isfile(db_path) or os.path.getsize(db_path) == 0:
            return None
        pending = destructive_pending(db_path, unique_keys)
        if not pending:
            return None
        print("[MIGRATE] 파괴적 마이그레이션 예정: " + ", ".join(f"{k} {v}행" for k, v in pending.items()))
        directory = backup_dir_for(db_path)
        os.makedirs(directory, exist_ok=True)
        need = 2 * os.path.getsize(db_path)
        if shutil.disk_usage(directory).free < need:
            record_warning(f"[WARN] 사본을 만들 여유 공간이 부족해 건너뜀(필요 {need} B)")
            return None
        dest = os.path.join(directory, "pre-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".db")
        c = sqlite3.connect(db_path)
        try:
            c.execute("VACUUM INTO ?", (dest,))
        finally:
            c.close()
        removed = prune_backups(directory, keep)
        print(f"[MIGRATE] 사본 {dest} ({os.path.getsize(dest)} B), 오래된 사본 {len(removed)}개 정리")
        return dest
    except Exception as e:
        record_warning(f"[WARN] 마이그레이션 전 사본 실패: {type(e).__name__}")
        return None


def data_dir_status(db_path: Optional[str]) -> dict:
    """/data(또는 DB 폴더)의 쓰기 가능 여부와 여유 공간. 경로는 응답에 넣지 않는다."""
    directory = os.path.dirname(os.path.abspath(db_path)) if db_path else ("/data" if os.path.isdir("/data") else None)
    if not directory:
        return {"checked": False}
    probe = os.path.join(directory, f".ready-{os.getpid()}-{int(time.time() * 1000)}")
    writable = True
    try:
        with open(probe, "w") as f:
            f.write("1")
    except OSError:
        writable = False
    finally:
        try:
            os.remove(probe)
        except OSError:
            pass
    free = shutil.disk_usage(directory).free
    return {"checked": True, "writable": writable, "free_mb": int(free // (1024 * 1024)), "enough_space": free >= MIN_FREE_BYTES}
