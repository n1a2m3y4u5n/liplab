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


_SKIP_SCENARIO = r'''
import json
from fastapi.testclient import TestClient
import main

def st(c, h, path):
    return {str(s["stage"]): s["status"] for s in c.get(path, headers=h).json()["stages"]}

out = {}
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "skip@example.com", "username": "건너뛰기", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    out["read_before"] = st(c, h, "/api/curriculum/stages")
    c.post("/api/curriculum/track", json={"track": "perception", "start_stage": 2}, headers=h)   # 독화 건너뛰기 = 포인터 이동
    out["read_after"] = st(c, h, "/api/curriculum/stages")
    out["speak_before"] = st(c, h, "/api/speak/curriculum")
    out["skip_far"] = c.post("/api/speak/skip", json={"stage": 3}, headers=h).status_code
    out["skip_1"] = c.post("/api/speak/skip", json={"stage": 1}, headers=h).status_code
    out["speak_after"] = st(c, h, "/api/speak/curriculum")
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


def test_skip_opens_only_the_next_stage_when_gated():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1",
                   ANTHROPIC_API_KEY="")
        env["LIPLAB_UNLOCK_ALL"] = "0"
        p = subprocess.run([sys.executable, "-c", _SKIP_SCENARIO], cwd=here, env=env,
                           capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])
    assert r["read_before"]["2"] == "locked"
    assert r["read_after"]["2"] == "unlocked" and r["read_after"]["3"] == "locked"   # 배치·건너뛰기로 2단계까지
    assert r["speak_before"]["1"] == "locked"
    assert r["skip_far"] == 400 and r["skip_1"] == 200                                 # 한 번에 한 단계만
    assert r["speak_after"]["1"] == "unlocked" and r["speak_after"]["2"] == "locked"
