"""복습 답의 찍기·감속 보정(backend/srs.py 머리말, 9/29).

- /api/review/answer가 answer_mode·speed를 받는다. 보기를 고른 정답과 1.0배 미만 정답은 품질 3(ease −0.14), 자연 속도에서 직접
  입력한 정답과 값을 보내지 않은 옛 화면의 정답은 4(ease 그대로), 오답은 1이다. speed 범위(0.1~4) 밖은 거절한다.
- 문장 레슨(/api/progress)에서 예정된 문장을 4지선다로 맞히면 정확 일치 100점이어도 품질 3을 넘지 않는다. 직접 입력은 점수 등급 그대로.
test_sentence_review.py와 같은 방식: 임시 DB를 지정한 별도 프로세스에서 시나리오를 돌리고 결과(JSON)만 검사한다.
"""
import json
import os
import subprocess
import sys
import tempfile

import srs

_SCENARIO = r'''
import json, os, sqlite3
from fastapi.testclient import TestClient
import main

def sql(q, *a):
    db = sqlite3.connect(os.environ["T_DB"])
    rows = db.execute(q, a).fetchall()
    db.commit(); db.close()
    return rows

TODAY = main._kst_today().isoformat()
cases = {"choice": {"answer_mode": "choice", "speed": 1.0}, "typed": {"answer_mode": "typed", "speed": 1.0},
         "slow": {"answer_mode": "typed", "speed": 0.75}, "fast": {"answer_mode": "typed", "speed": 1.25},
         "legacy": {}, "wrong_choice": {"answer_mode": "choice"}}
out = {}
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "sq@example.com", "username": "복습품질", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    uid = sql("select id from users")[0][0]
    for ref in cases:
        sql("insert into review_items (user_id, kind, ref, due_date, interval_days, ease_factor, repetitions, lapses, updated_at) "
            "values (?, 'word', ?, ?, 1, 2.5, 0, 0, CURRENT_TIMESTAMP)", uid, ref, TODAY)
    for ref, extra in cases.items():
        resp = c.post("/api/review/answer", headers=h, json={"kind": "word", "ref": ref, "correct": ref != "wrong_choice", **extra})
        assert resp.status_code == 200, resp.text
    out["word"] = {r[0]: [r[1], r[2]] for r in sql("select ref, ease_factor, repetitions from review_items where kind = 'word'")}
    out["bad_speed"] = c.post("/api/review/answer", headers=h, json={"kind": "word", "ref": "typed", "correct": True,
                                                                     "speed": 9}).status_code

    # 문장 레슨에서 예정된 문장을 다시 만남: 4지선다 정답(100점)과 직접 입력 정답(100점)
    for s in ("포장해 주세요", "카드로 계산할게요"):
        sql("insert into review_items (user_id, kind, ref, due_date, interval_days, ease_factor, repetitions, lapses, updated_at) "
            "values (?, 'sentence', ?, ?, 1, 2.5, 0, 0, CURRENT_TIMESTAMP)", uid, s, TODAY)
    for s, mode in (("포장해 주세요", "choice"), ("카드로 계산할게요", "typed")):
        resp = c.post("/api/progress", headers=h, json={"scenario_id": "lesson_1", "sentence": s, "user_answer": s,
                                                        "time_spent_seconds": 5, "situation": "카페", "difficulty_level": 2,
                                                        "answer_mode": mode})
        assert resp.status_code == 200 and resp.json()["score"] == 100, resp.text
    out["sentence"] = {r[0]: r[1] for r in sql("select ref, ease_factor from review_items where kind = 'sentence'")}
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


def test_quality_for_answer():
    assert srs.quality_for_answer(True, "typed", 1.0) == 4
    assert srs.quality_for_answer(True, None, None) == 4           # 옛 화면
    assert srs.quality_for_answer(True, "typed", 1.25) == 4        # 빠른 말
    assert srs.quality_for_answer(True, "choice", 1.0) == 3
    assert srs.quality_for_answer(True, "typed", 0.75) == 3
    assert srs.quality_for_answer(True, None, "x") == 4            # 읽을 수 없는 속도는 1.0배로 본다
    assert srs.quality_for_answer(False, "typed", 1.0) == 1 and srs.quality_for_answer(False, "choice", 0.5) == 1


def test_review_answer_and_sentence_quality():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1", T_DB=f"{d}/t.db",
                   JWT_SECRET=os.environ.get("JWT_SECRET", "test-only-srs-quality-secret"))
        for k in ("ANTHROPIC_API_KEY", "LIPLAB_UNLOCK_ALL", "LIPLAB_REVIEW"):
            env.pop(k, None)
        p = subprocess.run([sys.executable, "-c", _SCENARIO], cwd=here, env=env, capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])
    q3 = srs.schedule(3, 2.5, 1, 0, 0)["ease_factor"]
    q4 = srs.schedule(4, 2.5, 1, 0, 0)["ease_factor"]
    w = r["word"]
    assert q3 < q4 == 2.5
    assert w["choice"] == [q3, 1] and w["slow"] == [q3, 1]
    assert w["typed"] == [q4, 1] and w["fast"] == [q4, 1] and w["legacy"] == [q4, 1]
    assert w["wrong_choice"][1] == 0 and w["wrong_choice"][0] < q3   # 오답은 반복을 끊고 ease를 더 내린다
    assert r["bad_speed"] == 422
    q5 = srs.schedule(5, 2.5, 1, 0, 0)["ease_factor"]
    assert r["sentence"]["포장해 주세요"] == q3                       # 4지선다 100점도 품질 3
    assert r["sentence"]["카드로 계산할게요"] == q5                   # 직접 입력 100점은 점수 등급(5) 그대로
