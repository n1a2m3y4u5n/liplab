"""파일럿 보관·파기 스크립트(§4.7) 테스트 — 기한 전 거부, 집단별 파일럿 해제, 동의 철회 즉시 파기, 파기 대장.

test_pilot.py와 같은 방식: 임시 DB를 지정한 별도 프로세스에서 시나리오를 돌리고 결과(JSON)만 검사한다.
두 프로세스가 같은 가명을 쓰도록 JWT_SECRET을 고정한다.
"""
import json
import os
import subprocess
import sys
import tempfile

_SETUP = r'''
import json, os
from fastapi.testclient import TestClient
import main
out = {}
with TestClient(main.app) as c:
    def reg(email, name):
        r = c.post("/api/auth/register", json={"email": email, "username": name, "password": "pw-123456",
                                               "agree_terms": True, "age_confirmed": True})
        return {"Authorization": "Bearer " + r.json()["access_token"]}
    p1, p2, p3, op = (reg(f"{n}@example.com", f"user{n}") for n in ("p1", "p2", "p3", "op"))
    os.environ["LIPLAB_PILOT"] = "1"
    os.environ["LIPLAB_PILOT_CODES"] = "ALPHA:train,BETA:control"
    os.environ["LIPLAB_ADMIN_EMAILS"] = "op@example.com"
    c.post("/api/pilot/join", json={"code": "ALPHA"}, headers=p1)
    c.post("/api/pilot/join", json={"code": "BETA"}, headers=p2)
    for h in (p1, p3):
        item = main._training_closures()[0]
        c.post("/api/curriculum/closure-answer", json={"item_id": item["id"], "chosen": item["answer"]}, headers=h)
    ex = c.get("/api/pilot/export", headers=op).json()
    out["pids"] = {r["cohort"]: r["pid"] for r in ex["participants"]}
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''

_RETAIN = r'''
import asyncio, importlib.util, json, os, sys
spec = importlib.util.spec_from_file_location("pr", os.path.join("..", "scripts", "pilot_retention.py"))
pr = importlib.util.module_from_spec(spec); spec.loader.exec_module(pr)
pids = json.loads(os.environ["T_PIDS"])
led = os.environ["T_LEDGER"]
base = ["--study-end", "2026-01-01", "--retain-days", "30", "--ledger", led]
async def go():
    out = {}
    out["report"] = await pr.run(base + ["--today", "2026-01-15"])
    out["early"] = await pr.run(base + ["--today", "2026-01-15", "--apply", "--mode", "delete"])
    out["unlink"] = await pr.run(base + ["--today", "2026-02-01", "--apply", "--mode", "unlink", "--cohort", "control"])
    out["withdraw"] = await pr.run(["--withdraw", pids["train"], "--withdraw", "000000000000",
                                    "--apply", "--mode", "delete", "--ledger", led])
    out["after"] = await pr.run(base + ["--today", "2026-02-01"])
    from sqlalchemy import select
    from database import AsyncSessionLocal, User
    async with AsyncSessionLocal() as db:
        out["emails"] = sorted(e for (e,) in (await db.execute(select(User.email))).all())
    return out
out = asyncio.run(go())
out["ledger"] = [json.loads(l) for l in open(led, encoding="utf-8")]
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


def _sub(code, env, cwd):
    p = subprocess.run([sys.executable, "-c", code], cwd=cwd, env=env, capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    return json.loads(line[len("RESULT "):])


def test_retention_refuses_early_then_unlinks_and_purges():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1",
                   JWT_SECRET="test-secret-for-pilot-retention-0123456789")
        for k in ("LIPLAB_PILOT", "LIPLAB_PILOT_CODES", "LIPLAB_ADMIN_EMAILS"):
            env.pop(k, None)
        pids = _sub(_SETUP, env, here)["pids"]
        r = _sub(_RETAIN, dict(env, T_PIDS=json.dumps(pids), T_LEDGER=os.path.join(d, "ledger.jsonl")), here)
    assert set(pids) == {"train", "control"}
    rep = r["report"]
    assert rep["due"] == "2026-01-31" and not rep["applied"] and len(rep["participants"]) == 2
    train_rows = next(p["rows"] for p in rep["participants"] if p["cohort"] == "train")
    assert train_rows.get("trial_attempts") == 1
    assert r["early"].get("refused") and not r["early"]["applied"]
    assert r["unlink"]["applied"] and [p["pid"] for p in r["unlink"]["participants"]] == [pids["control"]]
    w = r["withdraw"]
    assert w["applied"] and w["reason"] == "withdrawal" and w["missing_pids"] == ["000000000000"]
    assert w["removed"].get("trial_attempts") == 1
    assert r["after"]["participants"] == []
    # 파일럿에서 빠진 p2와 참여하지 않은 p3·운영자 계정은 남고, 철회한 p1만 계정째 지워진다
    assert r["emails"] == ["op@example.com", "p2@example.com", "p3@example.com"]
    assert [e["reason"] for e in r["ledger"]] == ["retention", "withdrawal"]
    assert r["ledger"][1]["pids"] == [pids["train"]] and "p1@example.com" not in json.dumps(r["ledger"])
