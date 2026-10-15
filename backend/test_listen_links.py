"""트랙 잇기 API(/api/listen/links, docs/listen-cross-track-2026-10.md) 시나리오."""
import json
import os

_FLOW = r'''
import json
from fastapi.testclient import TestClient
import main
import curriculum as C
out = {}
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "lk@example.com", "username": "lk1", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    out["before"] = c.get("/api/listen/links", headers=h).json()
    # 독화 낱말 문항에서 ㅂ을 ㅁ으로 네 번 읽음(입모양이 같은 짝)과 ㅂ을 ㄷ으로 네 번 읽음(다른 짝)
    bw = [w["word"] for w in C.WORD_BANK if w["word"][0] in "바박반발밤밥방배버벌베벽변별병보복본볼봄부북분불비빗빛빵"][:4]
    for w in bw:
        ch = chr(ord(w[0]) - (ord("바") - ord("마"))) + w[1:]
        c.post("/api/curriculum/word-answer", json={"word": w, "correct": False, "chosen": ch}, headers=h)
        ch2 = chr(ord(w[0]) - (ord("바") - ord("다"))) + w[1:]
        c.post("/api/curriculum/word-answer", json={"word": w, "correct": False, "chosen": ch2}, headers=h)
    out["no_ling"] = c.get("/api/listen/links", headers=h).json()
    res = {k: True for k in ["m", "u", "a", "i", "sh", "s"]}
    c.post("/api/listen/ling", json={"results": res, "false_alarms": 0}, headers=h)
    out["after"] = c.get("/api/listen/links", headers=h).json()
    out["summary_recs"] = c.get("/api/listen/summary", headers=h).json()["recommendations"]
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


def test_listen_links_flow():
    import subprocess
    import sys
    import tempfile
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1", LIPLAB_UNLOCK_ALL="0")
        env.pop("ANTHROPIC_API_KEY", None)
        p = subprocess.run([sys.executable, "-c", _FLOW], cwd=here, env=env, capture_output=True, text=True, timeout=300)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])
    # 소리 듣기를 시작하지 않았으면(소리 확인 없음) 독화 기록이 있어도 권하지 않는다
    assert r["before"] == {"listen_started": False, "from_listen": [], "from_lipread": []}
    assert r["no_ling"]["listen_started"] is False and r["no_ling"]["from_lipread"] == []
    after = r["after"]
    assert after["listen_started"] is True and after["from_listen"] == []
    # 같아 보이는 ㅂ·ㅁ만 권하고(4번), 입모양이 다른 ㅂ·ㄷ은 독화 안의 연습이라 권하지 않는다
    assert [(x["slot"], x["pair"], x["n"]) for x in after["from_lipread"]] == [("onset", ["ㅂ", "ㅁ"], 4)]
    assert after["from_lipread"][0]["routes"][0]["to"].startswith("/listen/practice/contrast?contrast=onset:")
    assert r["summary_recs"] == []
