"""오답 복습 목록(/api/review-sentences) — 가장 최근에도 틀린 문장만 싣고, 틀린 횟수(wrong_count)와 시각을 준다.

test_unlock_mode.py와 같은 방식: 임시 DB를 지정한 별도 프로세스에서 시나리오를 돌리고 결과(JSON)만 검사한다.
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

def submit(c, h, sentence, answer):
    r = c.post("/api/progress", headers=h, json={"scenario_id": "t", "sentence": sentence, "user_answer": answer,
                                                 "time_spent_seconds": 5, "situation": "카페", "difficulty_level": 1})
    return r.json()["score"]

with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "rv@example.com", "username": "복습시험", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    a, b = "따뜻한 아메리카노 한 잔 주세요", "영수증은 버려 주세요"
    scores = [submit(c, h, a, "ㅋ"), submit(c, h, a, "ㅎ"), submit(c, h, b, "ㅋ"), submit(c, h, b, b)]
    rows = c.get("/api/review-sentences", headers=h).json()
print("RESULT " + json.dumps({"scores": scores, "rows": rows}, ensure_ascii=False))
'''


def _run():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1",
                   ANTHROPIC_API_KEY="")
        p = subprocess.run([sys.executable, "-c", _SCENARIO], cwd=here, env=env,
                           capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    return json.loads(line[len("RESULT "):])


def test_wrong_count_and_graduation():
    r = _run()
    s = r["scores"]
    assert s[0] < 60 and s[1] < 60 and s[2] < 60 and s[3] >= 60, s
    rows = {x["sentence"]: x for x in r["rows"]}
    assert list(rows) == ["따뜻한 아메리카노 한 잔 주세요"], "마지막에 맞힌 문장은 목록에서 빠진다"
    row = rows["따뜻한 아메리카노 한 잔 주세요"]
    assert row["wrong_count"] == 2
    assert row["created_at"] and row["created_at"].endswith(("Z", "+00:00")), "UTC 시각이어야 현지 날짜로 바꿀 수 있다"
