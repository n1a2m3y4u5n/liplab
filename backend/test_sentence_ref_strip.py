"""문장 복습 큐(kind 'sentence')와 연습 기록에 같은, 앞뒤 공백을 뗀 문장이 들어간다(리뷰 뒤 고침).

예전에는 큐에 넣을지 길이 검사만 strip한 값으로 하고 큐에는 원문을 넣었다. 공백이 붙은 100자 문장은 검사를 통과한 뒤
String(100) 칸을 넘었고, 큐의 ref와 Progress.sentence가 어긋날 수 있었다.
"""
import json
import os
import subprocess
import sys
import tempfile

_SCENARIO = r'''
import json, os, sqlite3
from fastapi.testclient import TestClient
import main

def sql(q, *a):
    db = sqlite3.connect(os.environ["T_DB"])
    rows = db.execute(q, a).fetchall()
    db.close()
    return rows

with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "st@example.com", "username": "strip", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    for s in ("  창가 자리에 앉을게요 ", "가" * 100 + "  "):
        c.post("/api/progress", headers=h, json={"scenario_id": "lesson_1", "sentence": s, "user_answer": "ㅋ",
                                                 "time_spent_seconds": 5, "situation": "카페", "difficulty_level": 3})
    sql_db = os.environ["T_DB"]
    db = sqlite3.connect(sql_db); db.execute("update review_items set due_date = ?", (main._kst_today().isoformat(),)); db.commit(); db.close()
    due = [x for x in c.get("/api/review/due", headers=h).json()["items"] if x["kind"] == "sentence"]
    out = {"refs": sorted(r[0] for r in sql("select ref from review_items where kind = 'sentence'")),
           "progress": sorted(r[0] for r in sql("select sentence from progress")),
           "due": {x["ref"]: x.get("situation") for x in due}}
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


def test_sentence_review_ref_is_stripped():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "t.db")
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{f}", T_DB=f, PYTHONDONTWRITEBYTECODE="1")
        env.pop("ANTHROPIC_API_KEY", None)
        p = subprocess.run([sys.executable, "-c", _SCENARIO], cwd=here, env=env, capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, p.stdout[-2000:] + p.stderr[-3000:]
    r = json.loads(line[len("RESULT "):])
    want = sorted(["창가 자리에 앉을게요", "가" * 100])
    assert r["refs"] == want and r["progress"] == want
    assert r["due"] == {w: "카페" for w in want}      # 큐의 ref로 연습 기록의 상황을 찾는다
