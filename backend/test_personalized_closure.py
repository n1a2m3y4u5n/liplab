"""문맥 추론 개인화(축 G-6) API 테스트 — 표적 입모양 항목이 앞에 오고, 표준검사 문항 단어는 빠진다.

test_account_security.py와 같은 방식: 임시 DB를 지정한 별도 프로세스에서 시나리오를 돌리고 결과(JSON)만 검사한다.
"""
import json
import os
import subprocess
import sys
import tempfile

_SCENARIO = r'''
import json
from fastapi.testclient import TestClient
import main, assessment, content_rules as cr

out = {}
tw = assessment.test_only_words()
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "g6@example.com", "username": "g6user", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    first = c.get("/api/curriculum/closure", headers=h).json()["items"]
    out["n_items"] = len(first)
    out["n_training"] = len(main._training_closures())
    out["test_word_leak"] = sum(1 for it in first if it["answer"] in tw or set(it["options"]) & tw)
    out["same_twice"] = [it["id"] for it in first] == [it["id"] for it in c.get("/api/curriculum/closure", headers=h).json()["items"]]
    # 양순음(viseme 1) 입모양을 계속 틀리게 기록 → 표적이 1이 된다
    for _ in range(6):
        c.post("/api/curriculum/mouth-attempt", json={"viseme_id": 1, "score": 20}, headers=h)
    d = c.get("/api/curriculum/closure", headers=h).json()
    out["targets"] = d["target_visemes"]
    hits = [len(set(cr.word_visemes(it["answer"])) & set(d["target_visemes"])) for it in d["items"]]
    out["hits_sorted"] = hits == sorted(hits, reverse=True)
    out["first_hit"] = hits[0] if hits else 0
    nxt = c.get("/api/curriculum/next", headers=h).json()
    out["next_closure_leak"] = sum(1 for it in nxt["closures"] if it["answer"] in tw or set(it["options"]) & tw)
print("RESULT " + json.dumps(out))
'''


def _run():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1")
        p = subprocess.run([sys.executable, "-c", _SCENARIO], cwd=here, env=env,
                           capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    return json.loads(line[len("RESULT "):])


def test_closure_personalized_and_excludes_test_words():
    r = _run()
    assert r["n_items"] == r["n_training"] > 100, "훈련용 문맥 문항 전체를 돌려줘야 한다"
    assert r["test_word_leak"] == 0 and r["next_closure_leak"] == 0, "표준검사 문항 단어가 훈련에 나오면 안 된다"
    assert r["same_twice"], "같은 날 같은 사용자에게는 순서가 같아야 한다(이어 풀기)"
    assert 1 in r["targets"], "틀린 입모양이 표적이 되어야 한다"
    assert r["hits_sorted"] and r["first_hit"] > 0, "표적 입모양을 담은 문항이 앞에 와야 한다"
