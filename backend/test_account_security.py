"""계정 보안(§4.9 표11 ②④③) API 테스트 — 가입 동의 서버 검증·기록, 비밀번호 변경 시 토큰 무효화,
계정 삭제·이메일 변경 재인증, 콘텐츠 검수 운영자 제한.

database 모듈이 import 시점에 DATABASE_URL을 읽으므로, 개발 DB(./liplab.db)를 건드리지 않도록
임시 DB를 지정한 별도 프로세스에서 시나리오를 돌리고 결과(JSON)만 검사한다.
"""
import json
import os
import subprocess
import sys
import tempfile

_SCENARIO = r'''
import json, os
from fastapi.testclient import TestClient
import main

out = {}
with TestClient(main.app) as c:
    base = {"email": "u1@example.com", "username": "tester1", "password": "pw-123456"}
    out["reg_no_consent"] = c.post("/api/auth/register", json=base).status_code
    r = c.post("/api/auth/register", json={**base, "agree_terms": True, "age_confirmed": True})
    out["reg_ok"] = r.status_code
    tok = r.json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    data = c.get("/api/account/data", headers=h).json()["data"]
    cr = data.get("consent_records", [])
    out["consent_rows"] = len(cr)
    out["consent_age"] = bool(cr and cr[0].get("age_confirmed"))

    # 이메일 변경 — 비밀번호 없으면 거부, 있으면 허용
    out["email_no_pw"] = c.patch("/api/account/profile", json={"email": "new@example.com"}, headers=h).status_code
    out["email_pw"] = c.patch("/api/account/profile",
                              json={"email": "new@example.com", "current_password": "pw-123456"}, headers=h).status_code
    # 이름만 바꿀 때는 비밀번호가 필요 없다
    out["name_only"] = c.patch("/api/account/profile", json={"username": "tester2"}, headers=h).status_code

    # 비밀번호 변경 → 옛 토큰 거부, 새 토큰 허용
    r = c.post("/api/account/password", json={"current_password": "pw-123456", "new_password": "pw-abcdefgh"}, headers=h)
    out["pw_change"] = r.status_code
    new_h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    out["old_token_me"] = c.get("/api/auth/me", headers=h).status_code
    out["new_token_me"] = c.get("/api/auth/me", headers=new_h).status_code

    # 검수 API — LIPLAB_REVIEW=1이어도 운영자 목록에 없으면 거부, 있으면 허용
    os.environ["LIPLAB_REVIEW"] = "1"
    os.environ["LIPLAB_ADMIN_EMAILS"] = ""
    out["review_no_admin"] = c.get("/api/admin/content/candidates", headers=new_h).status_code
    os.environ["LIPLAB_ADMIN_EMAILS"] = "new@example.com"
    out["review_admin"] = c.get("/api/admin/content/candidates", headers=new_h).status_code
    demo = c.post("/api/auth/demo").json()["access_token"]
    os.environ["LIPLAB_ADMIN_EMAILS"] = "demo@liplab.app"
    out["review_demo"] = c.get("/api/admin/content/candidates",
                               headers={"Authorization": f"Bearer {demo}"}).status_code

    # 계정 삭제 — 비밀번호가 틀리면 거부, 맞으면 삭제 후 토큰 무효
    out["del_bad_pw"] = c.request("DELETE", "/api/account", params={"confirm": True},
                                  json={"password": "wrong"}, headers=new_h).status_code
    out["del_ok"] = c.request("DELETE", "/api/account", params={"confirm": True},
                              json={"password": "pw-abcdefgh"}, headers=new_h).status_code
    out["after_delete_me"] = c.get("/api/auth/me", headers=new_h).status_code
print("RESULT " + json.dumps(out))
'''


def _run():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1")
        env.pop("LIPLAB_REVIEW", None)
        p = subprocess.run([sys.executable, "-c", _SCENARIO], cwd=here, env=env,
                           capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    return json.loads(line[len("RESULT "):])


def test_account_security_flow():
    r = _run()
    assert r["reg_no_consent"] == 400, "동의 없이 가입되면 안 된다"
    assert r["reg_ok"] == 201 and r["consent_rows"] == 1 and r["consent_age"], "동의 기록이 남아야 한다"
    assert r["email_no_pw"] == 403 and r["email_pw"] == 200 and r["name_only"] == 200
    assert r["pw_change"] == 200
    assert r["old_token_me"] == 401 and r["new_token_me"] == 200, "비밀번호 변경 뒤 옛 토큰은 거부"
    assert r["review_no_admin"] == 403 and r["review_admin"] == 200 and r["review_demo"] == 403
    assert r["del_bad_pw"] == 403 and r["del_ok"] == 200 and r["after_delete_me"] == 401
