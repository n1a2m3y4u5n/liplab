"""2단계 단어 보기(GET /api/curriculum/words)에 정답과 입모양이 같은 단어(동구형이음)가 없어야 한다.

예전 규칙은 최소대립 짝을 먼저 넣었는데 짝의 약 2/3가 동구형이음이라 문항의 57%가 입모양만으로 풀 수 없었다.
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
import main, visual_difficulty as V
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "wo@example.com", "username": "wo1", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    d = c.get("/api/curriculum/words", headers=h).json()
idx = V.VocabIndex([w["word"] for w in d["words"]])
bad = sum(1 for w in d["words"] if set(w.get("distractors", [])) & set(idx.homophenes(w["word"])))
print("RESULT " + json.dumps({"n": len(d["words"]), "with_homophene": bad, "level": d.get("option_level"),
                              "all_three": all(len(w.get("distractors", [])) == 3 for w in d["words"])}))
'''


def test_word_options_have_no_homophenes():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1")
        p = subprocess.run([sys.executable, "-c", _FLOW], cwd=here, env=env, capture_output=True, text=True, timeout=240)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])
    assert r["n"] > 400 and r["all_three"], r
    assert r["with_homophene"] == 0, "보기에 동구형이음이 들어갔다"
    assert r["level"] == 2, "숙달 전에는 보기 2단계(보이는 최소대립 1개)"


def test_stage2_pool_skips_rare_and_non_standalone_words():
    """9/27 단어 은행 감사: 드문 한자어·홀로 안 쓰이는 말은 2단계 문제로도 오답으로도 나오지 않는다."""
    import curriculum
    import main
    ex = curriculum.STAGE2_EXCLUDED
    assert {"소급", "당주", "빈", "본", "바", "폭도"} <= set(ex)
    assert "공학" not in ex                      # 흔한 말은 남긴다
    t = main._stage2_table()
    pool = set(t.words)
    assert not (pool & set(ex)) and len(pool) >= 400
    for w in list(pool)[:60]:
        assert not (set(t.classes(w).get("distinct", [])) & set(ex))
