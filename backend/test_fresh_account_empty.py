"""새 계정(기록 없음)이 학습·복습·과제·분석·소리 듣기 탭이 부르는 조회 API를 전부 200으로 받는지,
가입·로그인 경계 입력이 500 없이 4xx로 끝나는지 본다. 임시 DB를 쓰는 별도 프로세스로 돌린다."""
import json
import os
import subprocess
import sys
import tempfile

_SCENARIO = r'''
import json
from fastapi.testclient import TestClient
import main

GETS = ["/api/auth/me", "/api/statistics", "/api/tasks", "/api/review/due", "/api/review-sentences",
        "/api/bookmarks", "/api/calendar", "/api/calendar/activities", "/api/analysis/overview",
        "/api/analysis/articulation", "/api/curriculum/stages", "/api/curriculum/next",
        "/api/curriculum/recommended-level", "/api/curriculum/viseme-lessons", "/api/curriculum/mastery-probes",
        "/api/listen/summary", "/api/listen/review", "/api/listen/today", "/api/listen/links",
        "/api/listen/curriculum", "/api/listen/contrasts", "/api/speak/analysis", "/api/speak/review",
        "/api/speak/curriculum", "/api/assessment/history", "/api/assessment/progression",
        "/api/assessment/retention", "/api/eval/summary"]
out = {"gets": {}}
with TestClient(main.app, raise_server_exceptions=False) as c:
    body = {"email": "Fresh@Example.com", "username": "fresh1", "password": "pw-123456",
            "agree_terms": True, "age_confirmed": True}
    r = c.post("/api/auth/register", json=body)
    out["reg"] = r.status_code
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    for p in GETS:
        out["gets"][p] = c.get(p, headers=h).status_code
    # 같은 이메일(대소문자만 다름)·같은 사용자명
    out["dup_email"] = c.post("/api/auth/register", json={**body, "email": "fresh@example.com", "username": "other"}).status_code
    out["dup_name"] = c.post("/api/auth/register", json={**body, "email": "b@example.com"}).status_code
    # 경계 입력은 500이 아니어야 한다
    out["long_pw"] = c.post("/api/auth/register", json={**body, "email": "c@example.com", "username": "c1", "password": "가" * 40}).status_code
    out["short_pw"] = c.post("/api/auth/register", json={**body, "email": "d@example.com", "username": "d1", "password": "123"}).status_code
    out["bad_email"] = c.post("/api/auth/register", json={**body, "email": "nope"}).status_code
    out["login_long_pw"] = c.post("/api/auth/login", json={"email": "fresh@example.com", "password": "x" * 500}).status_code
    out["login_wrong"] = c.post("/api/auth/login", json={"email": "fresh@example.com", "password": "wrong-pw"}).status_code
    out["login_nouser"] = c.post("/api/auth/login", json={"email": "none@example.com", "password": "wrong-pw"}).status_code
    out["login_upper"] = c.post("/api/auth/login", json={"email": "FRESH@EXAMPLE.COM", "password": "pw-123456"}).status_code
    out["me_garbage"] = c.get("/api/auth/me", headers={"Authorization": "Bearer abc"}).status_code
    out["me_none"] = c.get("/api/auth/me").status_code
    out["demo1"] = c.post("/api/auth/demo").status_code
    out["demo2"] = c.post("/api/auth/demo").status_code
    out["logout"] = c.post("/api/auth/logout", headers=h).status_code
print("RESULT " + json.dumps(out))
'''


def test_fresh_account_and_auth_edges():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1")
        p = subprocess.run([sys.executable, "-c", _SCENARIO], cwd=here, env=env,
                           capture_output=True, text=True, timeout=240)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])
    assert r["reg"] == 201
    bad = {k: v for k, v in r["gets"].items() if v != 200}
    assert not bad, f"새 계정에서 200이 아닌 조회: {bad}"
    assert r["dup_email"] == 400 and r["dup_name"] == 400
    assert r["long_pw"] == 422 and r["short_pw"] == 422 and r["bad_email"] == 422
    assert r["login_long_pw"] == 401 and r["login_wrong"] == 401 and r["login_nouser"] == 401
    assert r["login_upper"] == 200
    assert r["me_garbage"] == 401 and r["me_none"] in (401, 403)
    assert r["demo1"] == 200 and r["demo2"] == 200
    assert r["logout"] in (200, 204)
