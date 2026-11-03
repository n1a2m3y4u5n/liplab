"""11/03 검토 묶음 B: CSP 수어 출처, 입력 상한, 413 헤더, 스트리밍 대기열, 약점 입모양 조회 수, WAL, 수어 캐시.
임시 DB를 쓰는 별도 프로세스에서 확인한다."""
import json
import os
import subprocess
import sys
import tempfile

_FLOW = r'''
import json, asyncio
from fastapi.testclient import TestClient
import main, database, sign_service
from sqlalchemy import event
out = {}
with TestClient(main.app) as c:
    r = c.get("/health")
    csp = r.headers["Content-Security-Policy"]
    out["csp_media"] = [p for p in csp.split("; ") if p.startswith("media-src")][0]
    # 413: 보안 헤더와 CORS 헤더가 함께 간다
    big = c.post("/api/auth/login", content=b"x" * (3 * 1024 * 1024),
                 headers={"Content-Type": "application/json", "Origin": "http://localhost:5173"})
    out["big"] = [big.status_code, big.headers.get("x-content-type-options"), big.headers.get("access-control-allow-origin")]
    reg = c.post("/api/auth/register", json={"email": "b@example.com", "username": "bb1", "password": "pw-123456",
                                             "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": "Bearer " + reg.json()["access_token"]}
    uid = reg.json()["user"]["id"]
    out["viseme_long"] = c.get("/api/viseme", params={"text": "가" * (main._TEXT_MAX + 1)}).status_code
    out["viseme_ok"] = c.get("/api/viseme", params={"text": "안녕"}).status_code
    out["place_over"] = c.post("/api/assessment/score", json={"items": [{}] * 201, "responses": {}}, headers=h).status_code
    out["conv_over"] = c.post("/api/conversation", json={"situation": "cafe", "level": 1, "history": [{}] * 101}, headers=h).status_code
    # 문자열이 아닌 content도 500이 아니다
    import llm_service
    out["fallback_nonstr"] = isinstance(llm_service.fallback_turn("cafe", 1, [{"role": "assistant", "content": 5}]), str)
    # 스트리밍 조각: 대기열이 차면 503
    import dgop_stream
    class S: pass
    dgop_stream.enabled = lambda: True
    dgop_stream.SESSIONS.get = lambda sid, uid: S()
    main._ML_INFLIGHT = main._ML_CONCURRENCY + main._ML_QUEUE_MAX
    out["stream_full"] = c.post("/api/speak/stream/x/chunk", content=b"\x00\x00", headers=h).status_code
    main._ML_INFLIGHT = 0
    # 약점 입모양 조회는 한 번
    n = {"sel": 0}
    def cnt(conn, cur, stmt, *a):
        if "weak_visemes" in stmt and stmt.lstrip().upper().startswith("SELECT"):
            n["sel"] += 1
    event.listen(database.engine.sync_engine, "before_cursor_execute", cnt)
    async def go():
        async with database.AsyncSessionLocal() as db:
            await main._bump_weak_visemes(uid, [1, 2, 3, 3, 4, 11], [2], {}, db)
            await db.commit()
            await main._bump_weak_visemes(uid, [1, 3], [], {}, db)
            await db.commit()
            from sqlalchemy import select
            rows = (await db.execute(select(database.WeakViseme).where(database.WeakViseme.user_id == uid))).scalars().all()
            return {r.viseme_id: [r.total_attempts, r.error_count] for r in rows}
    out["weak"] = asyncio.get_event_loop().run_until_complete(go()) if False else None
    out["weak_rows"] = c.portal.call(go)
    out["weak_selects"] = n["sel"]
    # 대화 정답 키(typ)는 로그인 토큰으로 못 쓴다
    import jwt, datetime
    from auth import SECRET_KEY, ALGORITHM
    k = jwt.encode({"uid": uid, "sub": str(uid), "typ": "conv_key", "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)}, SECRET_KEY, algorithm=ALGORITHM)
    out["convkey_as_login"] = c.get("/api/auth/me", headers={"Authorization": "Bearer " + k}).status_code
    # WAL
    async def jm():
        async with database.engine.connect() as conn:
            from sqlalchemy import text
            return [(await conn.execute(text("PRAGMA journal_mode"))).scalar(), (await conn.execute(text("PRAGMA busy_timeout"))).scalar()]
    out["pragma"] = c.portal.call(jm)
    # 수어 캐시: 실패는 캐시하지 않고, 크기 상한이 있다
    sign_service._VIDEO_CACHE.clear()
    sign_service.urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(OSError("x"))
    sign_service._resolve_video_url_sync("1")
    out["sign_fail_cached"] = "1" in sign_service._VIDEO_CACHE
    sign_service._VIDEO_CACHE.update({str(i): "u" for i in range(sign_service._VIDEO_CACHE_MAX)})
    class R:
        def __enter__(s): return s
        def __exit__(s, *a): pass
        def read(s): return b"multimedia/multimedia_files/convert/20200101/1/MOV99_105X105.jpg"
    sign_service.urllib.request.urlopen = lambda *a, **k: R()
    sign_service._resolve_video_url_sync("new")
    out["sign_cache_len"] = len(sign_service._VIDEO_CACHE)
    out["sign_client_same"] = None
    import engine
    out["placeholders_gone"] = main.text_to_visemes is engine.text_to_visemes
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


def _run():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
        p = subprocess.run([sys.executable, "-c", _FLOW], cwd=here, env=env, capture_output=True, text=True, timeout=300)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    return json.loads(line[len("RESULT "):])


def test_batch_b_behaviors():
    o = _run()
    assert "https://sldict.korean.go.kr" in o["csp_media"] and "'self'" in o["csp_media"]
    assert o["csp_media"].count("https://") == 1                       # 그 출처 하나만
    assert o["big"] == [413, "nosniff", "http://localhost:5173"]
    assert o["viseme_long"] == 422 and o["viseme_ok"] == 200
    assert o["place_over"] == 422 and o["conv_over"] == 422
    assert o["fallback_nonstr"] is True
    assert o["stream_full"] == 503
    assert o["weak_selects"] == 3                                      # 호출 2번 + 검증 조회 1번(입모양 수와 무관)
    assert o["weak_rows"] == {"1": [2, 0], "2": [1, 1], "3": [3, 0], "4": [1, 0]}
    assert o["convkey_as_login"] == 401
    assert o["pragma"][0] == "wal" and o["pragma"][1] == 5000
    assert o["sign_fail_cached"] is False and o["sign_cache_len"] <= 2000
    assert o["placeholders_gone"] is True
