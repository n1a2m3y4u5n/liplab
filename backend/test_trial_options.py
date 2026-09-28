"""선다형 시행마다 보여 준 보기를 기록한다(TrialAttempt.options, docs/confusion-pair-serving.md 5.4-1).

보기를 알아야 '그 자리에 read 자모 보기가 있었던 시행 가운데 그것을 고른 비율'로 혼동을 잴 수 있다. 보기를 보내지 않는 예전 화면도
그대로 채점되고(options NULL), 앞뒤가 맞지 않는 목록(정답이 없거나 고른 답이 보기 밖)은 남기지 않는다.
예전 DB(options 열이 없는 trial_attempts)는 켤 때 열이 붙는다. 임시 DB를 쓰는 별도 프로세스에서 돈다.
"""
import json
import os
import subprocess
import sys
import tempfile

_FLOW = r'''
import json, sqlite3, os
from fastapi.testclient import TestClient
import main
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "op@example.com", "username": "opu", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    w = c.get("/api/curriculum/words", headers=h).json()
    e = w["words"][0]
    word, d = e["word"], e["distractors"]
    opts = [d[0], word, d[1], d[2]]
    post = lambda url, body: c.post(url, json=body, headers=h)
    out = {}
    out["w1"] = post("/api/curriculum/word-answer", {"word": word, "correct": False, "chosen": d[0], "options": opts}).status_code
    out["w2"] = post("/api/curriculum/word-answer", {"word": word, "correct": True, "chosen": word}).status_code        # 예전 화면
    out["w3"] = post("/api/curriculum/word-answer", {"word": word, "correct": False, "chosen": d[0],
                                                     "options": [d[1], d[2], "없는말", d[0]]}).status_code             # 정답 없는 목록
    out["w4"] = post("/api/curriculum/word-answer", {"word": word, "correct": False, "chosen": "바다", "mode": "typed",
                                                     "options": opts}).status_code                                   # 주관식
    out["w5"] = post("/api/curriculum/word-answer", {"word": word, "correct": False, "chosen": d[0],
                                                     "options": [{"x": 1}]}).status_code                             # 모양이 틀림
    out["r1"] = post("/api/curriculum/recognition", {"viseme_id": 1, "chosen_id": 2, "options": [3, 1, 2, 4]}).status_code
    out["r2"] = post("/api/curriculum/recognition", {"viseme_id": 1, "chosen_id": 1}).status_code
    item = w["context_items"][0]
    wrong = next(o for o in item["options"] if o != item["answer"])
    out["c1"] = post("/api/curriculum/context-answer", {"item_id": item["id"], "chosen": wrong, "options": item["options"]}).status_code
    out["k1"] = post("/api/curriculum/closure-answer", {"item_id": item["id"], "chosen": item["answer"],
                                                        "options": item["options"]}).status_code
db = sqlite3.connect(os.environ["T_DB"])
rows = db.execute("select item_type, target, chosen, options from trial_attempts order by id").fetchall()
out["rows"] = [[t, tg, ch, json.loads(o) if o else None] for t, tg, ch, o in rows]
out["opts"], out["word"], out["ctx_opts"] = opts, word, item["options"]
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''

_MIGRATE = r'''
import asyncio, json, sqlite3, os
con = sqlite3.connect(os.environ["DB_FILE"])
con.execute("create table trial_attempts (id integer primary key, user_id integer not null, stage integer, "
            "item_type varchar(12) not null, target varchar(200) not null, chosen varchar(200), correct boolean, "
            "phase varchar(10), confusions json, item_id varchar(40), speed float, created_at datetime)")
con.execute("insert into trial_attempts (user_id, stage, item_type, target, chosen, correct, confusions) "
            "values (1, 2, 'word', '바다', '바람', 0, '[]')")
con.commit(); con.close()
import database as D
asyncio.run(D.init_db())
con = sqlite3.connect(os.environ["DB_FILE"])
cols = [r[1] for r in con.execute("pragma table_info(trial_attempts)")]
old = con.execute("select target, options from trial_attempts").fetchall()
print("RESULT " + json.dumps({"cols": cols, "old": old}, ensure_ascii=False))
'''


def _run(flow, **extra):
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "t.db")
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{f}", T_DB=f, DB_FILE=f,
                   PYTHONDONTWRITEBYTECODE="1", LIPLAB_UNLOCK_ALL="1", **extra)
        env.pop("ANTHROPIC_API_KEY", None)
        p = subprocess.run([sys.executable, "-c", flow], cwd=here, env=env, capture_output=True, text=True, timeout=240)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    return json.loads(line[len("RESULT "):])


def test_shown_options_are_recorded():
    r = _run(_FLOW)
    # 보기가 있든 없든, 모양이 틀리든 채점은 된다(예전 화면과 호환)
    assert all(r[k] == 200 for k in ("w1", "w2", "w3", "w4", "w5", "r1", "r2", "c1", "k1")), r
    rows = r["rows"]
    assert [x[0] for x in rows] == ["word", "word", "word", "word_typed", "word", "viseme", "viseme", "context", "closure"]
    assert rows[0][3] == r["opts"]          # 보인 순서 그대로
    assert rows[1][3] is None               # 보기를 보내지 않은 예전 화면
    assert rows[2][3] is None               # 정답이 없는 목록은 남기지 않는다
    assert rows[3][3] is None               # 주관식은 보기가 없다
    assert rows[4][3] is None               # 문자열·숫자가 아닌 보기
    assert rows[5][3] == ["3", "1", "2", "4"] and rows[6][3] is None   # 1단계는 입모양 번호 문자열
    assert rows[7][3] == r["ctx_opts"] and rows[8][3] == r["ctx_opts"]


def test_old_db_gets_options_column():
    r = _run(_MIGRATE)
    assert "options" in r["cols"]
    assert r["old"] == [["바다", None]]     # 예전 행은 NULL
