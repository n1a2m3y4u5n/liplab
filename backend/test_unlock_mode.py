"""단계 잠금 풀기 방식(LIPLAB_UNLOCK_ALL) — demo면 둘러보기 데모 계정만 모든 단계가 열리고, 실사용 계정은 숙달 순서대로다.

test_speak_nasal_fusion.py와 같은 방식: 임시 DB를 지정한 별도 프로세스에서 시나리오를 돌리고 결과(JSON)만 검사한다.
"""
import json
import os
import subprocess
import sys
import tempfile

_SCENARIO = r'''
import json
from fastapi.testclient import TestClient
import main

def status(c, h, path, key="stages"):
    r = c.get(path, headers=h)
    return {str(s.get("stage", s.get("n", i))): s["status"] for i, s in enumerate(r.json()[key])}

out = {}
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "gate@example.com", "username": "잠금시험", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    user = {"Authorization": "Bearer " + r.json()["access_token"]}
    demo = {"Authorization": "Bearer " + c.post("/api/auth/demo").json()["access_token"]}
    for name, h in (("user", user), ("demo", demo)):
        out[name] = {"read": status(c, h, "/api/curriculum/stages"), "speak": status(c, h, "/api/speak/curriculum")}
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


def _run(mode):
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1",
                   ANTHROPIC_API_KEY="")
        env["LIPLAB_UNLOCK_ALL"] = mode
        p = subprocess.run([sys.executable, "-c", _SCENARIO], cwd=here, env=env,
                           capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    return json.loads(line[len("RESULT "):])


def _locked(st):
    return sorted(k for k, v in st.items() if v == "locked")


def test_demo_mode_unlocks_only_demo_account():
    r = _run("demo")
    assert _locked(r["demo"]["read"]) == [] and _locked(r["demo"]["speak"]) == []
    assert _locked(r["user"]["read"]) and _locked(r["user"]["speak"])     # 실사용 계정은 잠긴 단계가 있다


def test_default_unlocks_everyone_and_zero_unlocks_no_one():
    on = _run("1")
    assert all(not _locked(on[a][k]) for a in ("user", "demo") for k in ("read", "speak"))
    off = _run("0")
    assert all(_locked(off[a][k]) for a in ("user", "demo") for k in ("read", "speak"))
