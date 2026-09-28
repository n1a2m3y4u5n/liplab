"""3단계 문장 답의 재생 속도(/api/progress speed)는 기록만 하고 숙달에는 넣지 않는다(docs/mastery-ewma.md 9절).

감속 합격을 0.5로 세는 후보가 시뮬레이션 사전 기준을 넘지 못해, 속도는 progress.speed에 남기기만 한다.
같은 답을 0.5배로 낸 학습자와 속도를 보내지 않은 학습자의 3단계 숙달 추정값이 같아야 한다. 범위(0.1~4) 밖은 거절한다.
test_sentence_review.py와 같은 방식: 임시 DB를 지정한 별도 프로세스에서 시나리오를 돌리고 결과(JSON)만 검사한다.
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
    db.commit(); db.close()
    return rows

def user(c, n):
    r = c.post("/api/auth/register", json={"email": f"sp{n}@example.com", "username": f"속도{n}", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    return {"Authorization": "Bearer " + r.json()["access_token"]}

lesson = ["따뜻한 아메리카노 한 잔 주세요", "영수증은 버려 주세요", "포장해 주세요", "카드로 계산할게요",
          "얼음은 조금만 넣어 주세요", "진동벨 받아 가세요"]
out = {}
with TestClient(main.app) as c:
    slow, plain = user(c, 1), user(c, 2)
    for h, extra in ((slow, {"speed": 0.5}), (plain, {})):
        for i, s in enumerate(lesson):
            ans = s if i != 2 else "ㅋ"
            c.post("/api/progress", headers=h, json={"scenario_id": "lesson_1", "sentence": s, "user_answer": ans,
                                                     "time_spent_seconds": 5, "situation": "카페", "difficulty_level": 2, **extra})
    out["mastery"] = [r[0] for r in sql("select mastery_score from stage_progress where stage = 3 order by user_id")]
    out["speeds"] = sorted({r[0] for r in sql("select speed from progress")}, key=lambda x: (x is None, x))
    bad = c.post("/api/progress", headers=plain, json={"scenario_id": "lesson_1", "sentence": lesson[0], "user_answer": lesson[0],
                                                       "time_spent_seconds": 5, "situation": "카페", "difficulty_level": 2,
                                                       "speed": 5.0})
    out["bad_status"] = bad.status_code
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


def test_stage3_speed_is_recorded_but_not_credited():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1", T_DB=f"{d}/t.db")
        for k in ("ANTHROPIC_API_KEY", "LIPLAB_UNLOCK_ALL", "LIPLAB_REVIEW"):
            env.pop(k, None)
        p = subprocess.run([sys.executable, "-c", _SCENARIO], cwd=here, env=env, capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])
    assert len(r["mastery"]) == 2 and r["mastery"][0] == r["mastery"][1] > 0, r["mastery"]
    assert r["speeds"] == [0.5, None], r["speeds"]
    assert r["bad_status"] == 422
