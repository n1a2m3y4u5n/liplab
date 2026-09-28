"""2단계 레슨 속 문맥 문항(분석·종합 섞기, 커리큘럼 개선 계획 1-3).

문맥 문항의 답은 2단계·3단계 숙달에 넣지 않고 시행 기록(stage 2, item_type 'context')과 취약 입모양(지식추적 입력)에만 남긴다.
"""
import json
import os
import subprocess
import sys
import tempfile

os.environ.setdefault("JWT_SECRET", "test-only-context-secret")

_FLOW = r'''
import json, sqlite3, os
from fastapi.testclient import TestClient
import main
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "cx@example.com", "username": "cxu", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    served = {x["id"] for x in main._training_closures()}
    w = c.get("/api/curriculum/words", headers=h).json()
    ctx = w["context_items"]
    item = ctx[0]
    wrong = next(o for o in item["options"] if o != item["answer"])
    a1 = c.post("/api/curriculum/context-answer", json={"item_id": item["id"], "chosen": item["answer"]}, headers=h).json()
    a2 = c.post("/api/curriculum/context-answer", json={"item_id": item["id"], "chosen": wrong}, headers=h).json()
    bad = c.post("/api/curriculum/context-answer", json={"item_id": "nope", "chosen": "x"}, headers=h).status_code
    stages = {s["stage"]: s for s in c.get("/api/curriculum/stages", headers=h).json()["stages"]}
    closure = [x["id"] for x in c.get("/api/curriculum/closure", headers=h).json()["items"]]
    w2 = c.get("/api/curriculum/words", headers=h).json()
db = sqlite3.connect(os.environ["T_DB"])
sp = db.execute("select stage, attempts from stage_progress").fetchall()
trials = db.execute("select stage, item_type, item_id, correct from trial_attempts").fetchall()
weak = db.execute("select sum(total_attempts), sum(error_count) from weak_visemes").fetchone()
print("RESULT " + json.dumps({
    "n_ctx": len(ctx), "all_served": all(x["id"] in served for x in ctx),
    "shapes_ok": all(len(x["options"]) >= 3 and x["answer"] in x["options"] and "___" in x["display"] for x in ctx),
    "a1": a1["correct"], "a2": a2["correct"], "bad": bad, "sp": sp, "trials": trials, "weak": list(weak),
    "s2_attempts": stages[2].get("attempts"), "closure_last": closure[-1] == item["id"], "item": item["id"],
    "w2_ids": [x["id"] for x in w2["context_items"]]}))
'''


def test_context_items_are_recorded_but_not_counted_for_mastery():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", T_DB=f"{d}/t.db",
                   PYTHONDONTWRITEBYTECODE="1", LIPLAB_UNLOCK_ALL="1")
        env.pop("ANTHROPIC_API_KEY", None)
        p = subprocess.run([sys.executable, "-c", _FLOW], cwd=here, env=env, capture_output=True, text=True, timeout=240)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])
    # 문항은 문맥 추론과 같은 검사된 풀에서, 빈칸 문장 + 보기 3개 이상
    assert r["n_ctx"] >= 2 and r["all_served"] and r["shapes_ok"]
    assert r["a1"] is True and r["a2"] is False and r["bad"] == 400
    # 숙달(2·3단계)에는 아무것도 쌓이지 않는다
    assert all(att == 0 for _, att in r["sp"]), r["sp"]
    # 시행 기록은 2단계 'context'로, 취약 입모양(지식추적 입력)은 시도·오류가 쌓인다
    assert [(t[0], t[1], t[2]) for t in r["trials"]] == [(2, "context", r["item"])] * 2
    assert [t[3] for t in r["trials"]] == [1, 0]
    assert r["weak"][0] > 0 and r["weak"][1] > 0
    # 방금 푼 문항은 3단계 문맥 추론에서 뒤로 가고(답을 본 문항을 기억으로 맞혀 3단계 숙달에 넣지 않게), 다음 레슨에서도 먼저 나오지 않는다
    assert r["closure_last"]
    assert r["item"] not in r["w2_ids"]
