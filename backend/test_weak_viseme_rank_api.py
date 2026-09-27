"""분석 화면의 약점 입모양 순위(/api/statistics)는 지식추적 숙달도가 낮은 순이다(knowledge_tracing.rank_weak).

예전에는 오류 횟수 상위 5개였다: 자주 나오는 모음(26번 중 6번 틀림)이 드문 ㅎ(4번 중 3번 틀림)보다 위였다.
임시 DB를 쓰는 별도 프로세스에서 돈다.
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
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "wr@example.com", "username": "wr1", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    def mark(vid, n_pass, n_fail):
        for _ in range(n_pass):
            c.post("/api/curriculum/mouth-attempt", json={"viseme_id": vid, "score": 90}, headers=h)
        for _ in range(n_fail):
            c.post("/api/curriculum/mouth-attempt", json={"viseme_id": vid, "score": 20}, headers=h)
    mark(2, 20, 6)    # 모음: 오류 6번(23%)
    mark(8, 1, 3)     # ㅎ: 오류 3번(75%)
    mark(6, 15, 4)    # 치경: 오류 4번(21%)
    d = c.get("/api/statistics", headers=h).json()
print("RESULT " + json.dumps(d["weak_visemes"], ensure_ascii=False))
'''


def test_statistics_rank_weak_visemes_by_mastery():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1")
        p = subprocess.run([sys.executable, "-c", _FLOW], cwd=here, env=env, capture_output=True, text=True, timeout=240)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    wv = json.loads(line[len("RESULT "):])
    assert [w["viseme_id"] for w in wv][0] == 8, wv
    assert wv[0]["attempts"] == 4 and wv[0]["error_rate"] == 75.0 and "mastery" in wv[0], wv
