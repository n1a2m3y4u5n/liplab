"""객관식(보기를 고른 답)은 채점식 대신 정확 일치로 채점한다(POST /api/progress, answer_mode='choice').

비슷한 오답 보기가 통과 점수를 받아 3단계 숙달에 들어가던 문제의 회귀 테스트. 임시 DB를 쓰는 별도 프로세스에서 돈다.
"""
import json
import os
import subprocess
import sys
import tempfile

_FLOW = r'''
import json
from fastapi.testclient import TestClient
import main
out = {}
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "mc@example.com", "username": "mc1", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    body = {"scenario_id": "t", "sentence": "여기 커피가 너무 뜨거워요.", "time_spent_seconds": 5,
            "situation": "카페", "difficulty_level": 1}
    w = c.post("/api/progress", json={**body, "user_answer": "여기 커피가 너무 차가워요.", "answer_mode": "choice"},
               headers=h).json()
    r = c.post("/api/progress", json={**body, "user_answer": "여기 커피가 너무 뜨거워요", "answer_mode": "choice"},
               headers=h).json()
    out["choice_wrong"], out["wrong_passed"] = w["score"], w.get("passed")
    out["choice_right"], out["right_passed"] = r["score"], r.get("passed")
    out["typed_similar"] = c.post("/api/progress", json={**body, "user_answer": "여기 커피가 너무 차가워요."},
                                  headers=h).json()["score"]
print("RESULT " + json.dumps(out))
'''


def test_choice_answers_use_exact_match():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1")
        env.pop("ANTHROPIC_API_KEY", None)
        p = subprocess.run([sys.executable, "-c", _FLOW], cwd=here, env=env, capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])
    assert r["choice_wrong"] == 0, "비슷한 오답 보기가 점수를 받았다"
    assert r["choice_right"] == 100, "공백·문장부호만 다른 정답 보기는 만점"
    assert r["wrong_passed"] is False and r["right_passed"] is True, "응답의 합격 여부가 점수와 맞아야 한다"
    assert 0 < r["typed_similar"] < 100   # 직접 적은 답은 v2 채점(부분 점수)
