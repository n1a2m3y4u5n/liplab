"""'복습왕' 배지(review_king)의 복습 횟수 = 예정된 복습에 답한 누적 횟수(learning_profiles.reviews_completed).

- 레슨에서 같은 입모양을 두 번 틀려도(lapses 2) 복습을 한 번도 안 했으면 배지가 없다. 예전에는 남은 복습 항목의
  lapses > 1로 세어 배지가 나왔다.
- 예정일 전에 맞힌 답(간격을 늘리지 않는 답)은 세지 않는다.
- 복습을 끝까지 해 항목이 졸업(행 삭제)해도 누적값이 남아 배지가 유지된다. 예전에는 행이 없어져 배지가 꺼졌다.
- 말하기 복습(_sr_touch)도 같은 경로(_srs_apply)로 센다.

test_review_sentences.py와 같은 방식: 임시 DB를 지정한 별도 프로세스에서 시나리오를 돌리고 결과(JSON)만 검사한다.
예정일이 지나는 것은 표의 due_date를 오늘로 바꿔 흉내 낸다.
"""
import json
import os
import subprocess
import sys
import tempfile
from functools import lru_cache

_SCENARIO = r'''
import json, os, sqlite3
from fastapi.testclient import TestClient
import main
import database

def sql(q, *a):
    db = sqlite3.connect(os.environ["T_DB"])
    rows = db.execute(q, a).fetchall()
    db.commit(); db.close()
    return rows

def make_due():
    sql("update review_items set due_date = ?", main._kst_today().isoformat())

def badge(c, h):
    ov = c.get("/api/analysis/overview", headers=h).json()
    return next(b["earned"] for b in ov["badges"] if b["key"] == "review_king")

def done():
    return (sql("select reviews_completed from learning_profiles") or [[None]])[0][0]

out = {}
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "rk@example.com", "username": "복습왕", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    uid = sql("select id from users")[0][0]
    # 한 레슨에서 같은 입모양을 두 번 틀림(복습 화면은 거치지 않음)
    for _ in range(2):
        c.post("/api/curriculum/recognition", headers=h, json={"viseme_id": 1, "chosen_id": 2})
    out["lapses"] = sql("select lapses from review_items")[0][0]
    out["badge_after_lesson"] = badge(c, h)
    out["done_after_lesson"] = done()
    # 예정일(내일) 전에 복습 화면에서 맞힘: 간격을 늘리지 않으므로 복습으로 세지 않는다
    c.post("/api/review/answer", headers=h, json={"kind": "viseme", "ref": "1", "correct": True})
    out["done_after_early"] = done()
    # 예정일마다 맞혀 졸업할 때까지
    answers = 0
    for _ in range(12):
        if not sql("select id from review_items where kind = 'viseme'"):
            break
        make_due()
        c.post("/api/review/answer", headers=h, json={"kind": "viseme", "ref": "1", "correct": True})
        answers += 1
    out["answers_to_graduate"] = answers
    out["rows_after_graduate"] = len(sql("select id from review_items where kind = 'viseme'"))
    out["done_after_graduate"] = done()
    out["badge_after_graduate"] = badge(c, h)

    # 말하기 복습(_sr_touch): 등록(오답) → 예정일에 다시 말함. 서버와 같은 이벤트 루프(c.portal)에서 부른다
    async def speak(correct):
        async with database.AsyncSessionLocal() as db:
            await main._sr_touch(uid, "speak", "안녕하세요", correct, db, score=80 if correct else 20)
            await db.commit()
    c.portal.call(speak, False)
    before = done()
    make_due()
    c.portal.call(speak, True)
    out["speak_counted"] = done() - before
    # 밀린 복습이 있으면 배지는 꺼진다(기존 규칙 유지)
    c.portal.call(speak, False)
    sql("update review_items set due_date = '2000-01-01'")
    out["badge_overdue"] = badge(c, h)
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


@lru_cache(maxsize=1)
def _run():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1",
                   T_DB=f"{d}/t.db")
        env.pop("ANTHROPIC_API_KEY", None)
        p = subprocess.run([sys.executable, "-c", _SCENARIO], cwd=here, env=env,
                           capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    return json.loads(line[len("RESULT "):])


def test_lesson_errors_alone_do_not_earn_review_king():
    r = _run()
    assert r["lapses"] == 2                     # 예전 조건(lapses > 1)이면 배지가 나오던 상태
    assert r["badge_after_lesson"] is False
    assert not r["done_after_lesson"]
    assert not r["done_after_early"]            # 예정일 전 답은 세지 않는다


def test_graduated_reviews_keep_the_badge():
    r = _run()
    assert r["rows_after_graduate"] == 0        # 졸업해 항목이 지워졌다
    assert r["done_after_graduate"] == r["answers_to_graduate"] >= 2
    assert r["badge_after_graduate"] is True


def test_speaking_review_counts_and_overdue_turns_badge_off():
    r = _run()
    assert r["speak_counted"] == 1
    assert r["badge_overdue"] is False
