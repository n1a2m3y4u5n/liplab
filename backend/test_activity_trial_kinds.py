"""회차 히스토리(/api/calendar/activities)와 회차 상세(/api/analysis/activity-detail)가 2단계 주관식(word_typed)과
단어 레슨 속 문맥 문항(context)도 보여 준다. 예전에는 두 유형이 목록(ORDER)에 없어 그날 기록에서 빠졌다.
임시 DB를 쓰는 별도 프로세스에서 돈다.
"""
import json
import os
import subprocess
import sys
import tempfile

_FLOW = r'''
import json, datetime as dt
from fastapi.testclient import TestClient
import main
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "tk@example.com", "username": "tku", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    post = lambda url, body: c.post(url, json=body, headers=h)
    post("/api/curriculum/word-answer", {"word": "밥", "correct": True, "chosen": "밥"})
    post("/api/curriculum/word-answer", {"word": "밥", "correct": False, "chosen": "맘", "mode": "typed"})    # 입모양은 맞음
    post("/api/curriculum/word-answer", {"word": "밥", "correct": False, "chosen": "하늘", "mode": "typed"})  # 오답
    item = main._training_closures()[0]
    post("/api/curriculum/context-answer", {"item_id": item["id"], "chosen": item["answer"]})
    today = (dt.datetime.utcnow() + dt.timedelta(hours=9)).date().isoformat()
    acts = c.get("/api/calendar/activities", params={"tz_offset_min": -540}, headers=h).json()
    det = lambda kind: c.get("/api/analysis/activity-detail", params={"day": today, "kind": kind, "tz_offset_min": -540},
                             headers=h).json()
    print("RESULT " + json.dumps({"rows": acts.get(today), "typed": det("word_typed"), "ctx": det("context"),
                                  "word": det("word")}, ensure_ascii=False))
'''


def test_typed_and_context_trials_show_in_history():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1",
                   LIPLAB_UNLOCK_ALL="1")
        env.pop("ANTHROPIC_API_KEY", None)
        p = subprocess.run([sys.executable, "-c", _FLOW], cwd=here, env=env, capture_output=True, text=True, timeout=240)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])
    rows = {x["kind"]: x for x in r["rows"]}
    assert set(rows) >= {"word", "word_typed", "context"}, list(rows)
    assert rows["word"]["n"] == 1 and rows["word_typed"]["n"] == 2 and rows["context"]["n"] == 1
    assert rows["word_typed"]["label"] == "독화 · 단어 주관식" and rows["word_typed"]["route"] == "/learn/word"
    assert rows["context"]["label"] == "독화 · 단어 레슨 문맥" and rows["context"]["route"] == "/learn/word"
    # 회차 상세: 유형마다 자기 행만, 주관식은 쓴 답과 판정(입모양은 맞음)을 준다
    assert r["word"]["summary"]["n"] == 1
    t = r["typed"]
    assert t["summary"]["n"] == 2 and [i["verdict"] for i in t["items"]] == ["homophene", "wrong"]
    assert [i["chosen"] for i in t["items"]] == ["맘", "하늘"]
    assert r["ctx"]["summary"]["n"] == 1 and r["ctx"]["items"][0]["correct"] is True
