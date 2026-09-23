"""파일럿 계측(§4.7) API 테스트 — 참여 코드 검증·집단 배정, 운영자 전용 가명 내보내기(개인정보 미포함).

test_account_security.py와 같은 방식: 임시 DB를 지정한 별도 프로세스에서 시나리오를 돌리고 결과(JSON)만 검사한다.
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
    def reg(email, name):
        r = c.post("/api/auth/register", json={"email": email, "username": name, "password": "pw-123456",
                                               "agree_terms": True, "age_confirmed": True})
        return {"Authorization": "Bearer " + r.json()["access_token"]}
    p1 = reg("p1@example.com", "pilot1")
    op = reg("op@example.com", "operator")
    out["off"] = c.post("/api/pilot/join", json={"code": "ALPHA"}, headers=p1).status_code
    os.environ["LIPLAB_PILOT"] = "1"
    os.environ["LIPLAB_PILOT_CODES"] = "ALPHA:train,BETA:control"
    out["bad_code"] = c.post("/api/pilot/join", json={"code": "nope"}, headers=p1).status_code
    j = c.post("/api/pilot/join", json={"code": "alpha"}, headers=p1)
    out["join"], out["cohort"] = j.status_code, j.json().get("cohort")
    item = main._training_closures()[0]
    c.post("/api/curriculum/closure-answer", json={"item_id": item["id"], "chosen": item["answer"]}, headers=p1)
    out["export_no_admin"] = c.get("/api/pilot/export", headers=op).status_code
    os.environ["LIPLAB_ADMIN_EMAILS"] = "op@example.com"
    ex = c.get("/api/pilot/export", headers=op)
    out["export"] = ex.status_code
    body = ex.json()
    out["n"] = body["n"]
    out["text"] = json.dumps(body, ensure_ascii=False)
    out["row"] = body["participants"][0] if body["participants"] else None
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


def _run():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1")
        for k in ("LIPLAB_PILOT", "LIPLAB_PILOT_CODES", "LIPLAB_ADMIN_EMAILS"):
            env.pop(k, None)
        p = subprocess.run([sys.executable, "-c", _SCENARIO], cwd=here, env=env,
                           capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    return json.loads(line[len("RESULT "):])


def test_pilot_join_and_pseudonymized_export():
    r = _run()
    assert r["off"] == 403 and r["bad_code"] == 400
    assert r["join"] == 200 and r["cohort"] == "train"
    assert r["export_no_admin"] == 403 and r["export"] == 200 and r["n"] == 1
    row = r["row"]
    assert len(row["pid"]) == 12 and row["cohort"] == "train"
    assert row["trials_by_stage"]["3"] == {"n": 1, "correct": 1}
    # 이메일·사용자명은 내보내기에 없어야 한다
    assert "p1@example.com" not in r["text"] and "pilot1" not in r["text"]
