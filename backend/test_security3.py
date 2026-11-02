"""독립 DB에서 두 사용자 토큰과 사유 객체의 소유권을 점검한다."""
import os
import subprocess
import sys
import tempfile

SCENARIO = r'''
import asyncio, io, os, time, sys
from types import SimpleNamespace
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile, Headers
from fastapi import HTTPException
import main, database, auth, login_guard
from sqlalchemy import select, update
from datetime import datetime, timedelta

with TestClient(main.app) as c:
    def reg(n):
        r=c.post("/api/auth/register",json={"email":f"{n}@example.com","username":n,"password":"pw-123456","agree_terms":True,"age_confirmed":True})
        assert r.status_code==201, r.text
        return r.json()["user"]["id"], {"Authorization":"Bearer "+r.json()["access_token"]}
    uid,a=reg("alice"); vid,b=reg("bob")
    # 인증 의존성이 있는 모든 라우트는 미인증 요청을 거부한다.
    from fastapi.routing import APIRoute
    def flatten(routes):
        for route in routes:
            if hasattr(route,"original_router"):
                yield from flatten(route.original_router.routes)
            else:
                yield route
    routes=list(flatten(main.app.routes))
    import runpy
    generated=runpy.run_path("../scripts/api_security_inventory.py")["inventory"]()
    assert {(r["method"],r["path"]) for r in generated} == {
        (method,route.path) for route in routes if isinstance(route,APIRoute)
        and (route.path.startswith("/api/") or route.path=="/health") for method in route.methods}
    def protected(dep):
        return dep.call is auth.get_current_user or any(protected(x) for x in dep.dependencies)
    count=0
    for route in routes:
        if not isinstance(route,APIRoute) or not route.path.startswith("/api/") or not protected(route.dependant): continue
        import re
        path=re.sub(r"\{[^}]+\}","1",route.path)
        for method in route.methods:
            r=c.request(method,path,json={})
            assert r.status_code in (401,403), (method,path,r.status_code,r.text[:200])
            count+=1
    # 타인 북마크 삭제가 실패한 뒤 소유자는 여전히 삭제할 수 있다.
    r=c.post("/api/bookmarks",json={"sentence":"private sentinel","situation":"test","level":1},headers=a)
    assert r.status_code==201, r.text
    bid=c.get("/api/bookmarks",headers=a).json()[0]["id"]
    assert c.delete(f"/api/bookmarks/{bid}",headers=b).status_code==404
    assert "private sentinel" not in c.get("/api/bookmarks",headers=b).text
    assert c.delete(f"/api/bookmarks/{bid}",headers=a).status_code==200
    # 파일럿 참여 조건을 충족하는 두 사용자와 실제 DB 회차를 준비한다.
    os.environ["LIPLAB_PILOT"]="1"; os.environ["LIPLAB_PILOT_CODES"]="ALPHA:train"
    for h in (a,b):
        assert c.post("/api/pilot/join",json={"code":"ALPHA"},headers=h).status_code==200
    async def seed():
        async with database.AsyncSessionLocal() as db:
            row=database.P3TestSession(user_id=uid,session_label="A1",layer="word",form="A",planned_order="ABC",join_seq=1)
            db.add(row); await db.commit(); return row.id
    sid=c.portal.call(seed)
    for method,path,body in [
        ("GET",f"/api/pilot/battery/media/{sid}/private",None),
        ("GET",f"/api/pilot/battery/noise/{sid}",None),
        ("POST","/api/pilot/battery/answer",{"session_id":sid,"item_id":"private","chosen":"x"}),
        ("POST","/api/pilot/battery/finish",{"session_id":sid})]:
        r=c.request(method,path,json=body,headers=b)
        assert r.status_code==404, (path,r.status_code,r.text)
        assert "검사 회차가 없습니다" in r.json()["detail"], r.text
    # 녹음·코칭 메모리 객체도 타인 토큰에 공개하지 않는다. 모델 추론은 하지 않는다.
    os.environ["DGOP_STREAM"]="1"
    import dgop_stream
    stream=SimpleNamespace(id="private-stream",user_id=uid,touched=time.monotonic())
    dgop_stream.SESSIONS._s[stream.id]=stream
    assert c.post("/api/speak/stream/private-stream/chunk",content=b"\0\0",headers=b).status_code==404
    assert dgop_stream.SESSIONS.get(stream.id,uid) is stream
    assert main._pop_speak_stream(stream.id,vid) is None
    assert dgop_stream.SESSIONS.get(stream.id,uid) is stream
    async def task(): return "private coaching"
    async def coaching():
        main._COACH_JOBS._jobs["private-coach"]={"user":uid,"t":time.monotonic(),"task":asyncio.create_task(task())}
    c.portal.call(coaching)
    assert c.get("/api/speak/coaching/private-coach",headers=b).status_code==404
    assert c.get("/api/speak/coaching/private-coach",headers=a).status_code==200
    # 서명된 대화 답안 키에도 소유자가 묶여 있어야 한다.
    key=auth.create_access_token({"uid":uid,"sp":[0],"tx":["private"],"cl":None})
    assert c.post("/api/conversation/multi/result",json={"answer_key":key},headers=b).status_code==403
    # 내보내기는 쿼리로 받은 user_id를 신뢰하지 않는다.
    own=c.get("/api/account/data",headers=b,params={"user_id":uid}).json()
    assert own["user"]["id"]==vid
    # 관리자 라우트는 일반 사용자를 거부한다.
    os.environ["LIPLAB_REVIEW"]="1"; os.environ["LIPLAB_ADMIN_EMAILS"]="alice@example.com"
    assert c.get("/api/pilot/export",headers=b).status_code==403
    assert c.post("/api/pilot/lookup",json={"email":"alice@example.com"},headers=b).status_code==403
    for route in routes:
        if isinstance(route,APIRoute) and route.path.startswith("/api/admin/"):
            for method in route.methods:
                r=c.request(method,route.path,json={"kind":"words","item":{},"decision":"approve"},headers=b)
                assert r.status_code==403, (route.path,r.status_code)
    # CORS는 필요한 헤더만 허용한다.
    origin={"Origin":"http://localhost:5173","Access-Control-Request-Method":"POST","Access-Control-Request-Headers":"authorization,content-type,x-usage-device-id"}
    assert c.options("/api/auth/login",headers=origin).status_code==200
    assert c.options("/api/auth/login",headers={**origin,"Access-Control-Request-Method":"TRACE"}).status_code==400
    assert c.options("/api/auth/login",headers={**origin,"Access-Control-Request-Headers":"x-evil"}).status_code==400
    # IP를 바꿔도 계정 잠금이 적용되고 만료 후 정상 로그인할 수 있다.
    for n in range(5):
        r=c.post("/api/auth/login",json={"email":"ALICE@example.com","password":"wrong"},headers={"Fly-Client-IP":f"192.0.2.{n}"})
        assert r.status_code==401, r.text
    assert c.post("/api/auth/login",json={"email":"alice@example.com","password":"pw-123456"},headers={"Fly-Client-IP":"192.0.2.99"}).status_code==429
    async def expire():
        async with database.AsyncSessionLocal() as db:
            await db.execute(update(database.LoginAttempt).values(expires_at=datetime.utcnow()-timedelta(seconds=1))); await db.commit()
    c.portal.call(expire)
    assert c.post("/api/auth/login",json={"email":"alice@example.com","password":"pw-123456"},headers={"Fly-Client-IP":"192.0.2.98"}).status_code==200
    # Content-Length 없는 청크 본문도 크기를 제한한다.
    r=c.post("/api/public/score",content=iter([b"x"*(1024*1024)]*3))
    assert r.status_code==413, r.status_code
    async def uploads():
        for content,ctype,expected in [(b"<script>","audio/wav",415),(b"", "audio/wav",400),(b"x"*20,"audio/wav",413),(b"RIFF"+b"\0"*4+b"WAVE"+b"\0"*4,"audio/wav",None)]:
            f=UploadFile(io.BytesIO(content),headers=Headers({"content-type":ctype}))
            try:
                await main._read_audio_limited(f,max_bytes=16)
                assert expected is None
            except HTTPException as e: assert e.status_code==expected
    c.portal.call(uploads)
    # 오류 메시지·DB 바인드 매개변수는 로그로 보내지 않는다.
    import logging
    class Capture(logging.Handler):
        def emit(self,record):
            assert "private-pii@example.com" not in self.format(record)
            assert not record.exc_info
    log=logging.getLogger("liplab"); handler=Capture(); log.addHandler(handler)
    try: main._server_error(ValueError("private-pii@example.com"),"security-test")
    finally: log.removeHandler(handler)
    from security_logging import AccessPrivacyFilter
    record=logging.LogRecord("uvicorn.access",logging.INFO,"",0,'%s - "%s %s HTTP/%s" %s',
        ("192.0.2.1","GET","/api/sound?text=private-pii@example.com","1.1",200),None)
    AccessPrivacyFilter().filter(record)
    assert "192.0.2.1" not in record.getMessage()
    assert "private-pii@example.com" not in record.getMessage()
    from security_logging import ExceptionPrivacyFilter
    try: raise ValueError("private-pii@example.com")
    except ValueError:
        record.exc_info=sys.exc_info()
        ExceptionPrivacyFilter().filter(record)
    assert not record.exc_info and "private-pii@example.com" not in record.getMessage()
    print("SECURITY3_OK protected_routes="+str(count))
'''


def test_security3_isolation_and_controls():
    with tempfile.TemporaryDirectory() as d:
        env=dict(os.environ,DATABASE_URL=f"sqlite+aiosqlite:///{d}/test.db",LIPLAB_CONTENT_WARMUP="0",PYTHONDONTWRITEBYTECODE="1",PYTHONUTF8="1")
        r=subprocess.run([sys.executable,"-X","utf8","-c",SCENARIO],cwd=os.path.dirname(__file__),env=env,capture_output=True,text=True,timeout=180)
    assert r.returncode==0, r.stdout[-1000:]+r.stderr[-5000:]
    assert "SECURITY3_OK" in r.stdout
