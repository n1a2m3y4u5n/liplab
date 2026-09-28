"""틀린 문장 복습(mistake_review_*)·북마크 연습(bookmark_*) 세션의 답 처리.

- 3단계 숙달에는 넣지 않는다(원문을 목록에서 본 뒤의 답). 예전에는 넣어서 복습만으로 3단계가 숙달됐다.
- 기록(Progress)은 남겨, 복습에서 맞힌 문장은 오답 목록(/api/review-sentences)에서 빠진다.
- 추천 난이도(/api/curriculum/recommended-level)는 복습 행을 빼고 최근 문장 연습의 난이도를 기준으로 삼는다.
  scenario_id의 밑줄은 LIKE 와일드카드라 이스케이프하지 않으면 'mistakeXreviewX...' 같은 일반 레슨도 빠진다.

test_review_sentences.py와 같은 방식: 임시 DB를 지정한 별도 프로세스에서 시나리오를 돌리고 결과(JSON)만 검사한다.
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

def submit(c, h, sid, sentence, answer, level):
    r = c.post("/api/progress", headers=h, json={"scenario_id": sid, "sentence": sentence, "user_answer": answer,
                                                 "time_spent_seconds": 5, "situation": "카페", "difficulty_level": level})
    return r.json()

def stage3(c, h):
    # 화면용 단계 목록은 잠금 해제 표시일 때 시도 수를 싣지 않아 표에서 바로 읽는다
    db = sqlite3.connect(os.environ["T_DB"])
    row = db.execute("select attempts from stage_progress where stage = 3").fetchone()
    db.close()
    return (row or [0])[0] or 0

out = {}
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "rs@example.com", "username": "복습숙달", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    lesson = ["따뜻한 아메리카노 한 잔 주세요", "영수증은 버려 주세요", "포장해 주세요", "카드로 계산할게요",
              "얼음은 조금만 넣어 주세요", "진동벨 받아 가세요", "빨대는 저기 있어요"]
    wrong = "창가 자리에 앉을게요"
    submit(c, h, "lesson_1", wrong, "ㅋ", 4)                      # 레슨에서 틀린 문장
    for s in lesson:
        submit(c, h, "lesson_1", s, s, 4)                         # 4단계 문장 7개를 맞힘
    out["after_lesson"] = stage3(c, h)
    out["rec_before_review"] = c.get("/api/curriculum/recommended-level", headers=h).json()
    out["review_list_before"] = [x["sentence"] for x in c.get("/api/review-sentences", headers=h).json()]
    # 틀린 문장 복습 3문장(옛 화면처럼 난이도 1로 보냄)과 북마크 연습 1문장
    rv = [submit(c, h, "mistake_review_1", wrong, wrong, 1)]
    rv += [submit(c, h, "mistake_review_1", s, s, 1) for s in lesson[:2]]
    rv.append(submit(c, h, "bookmark_7", lesson[2], lesson[2], 1))
    out["review_status"] = [x["status"] for x in rv]
    out["review_xp"] = [x["xp_gained"] for x in rv]
    out["after_review"] = stage3(c, h)
    out["review_list_after"] = [x["sentence"] for x in c.get("/api/review-sentences", headers=h).json()]
    out["rec_after_review"] = c.get("/api/curriculum/recommended-level", headers=h).json()
    # 밑줄 자리에 다른 글자가 든 일반 레슨은 복습이 아니다(LIKE 와일드카드 이스케이프)
    submit(c, h, "mistakeXreviewX1", lesson[3], lesson[3], 3)
    out["after_lookalike"] = stage3(c, h)
    out["rec_after_lookalike"] = c.get("/api/curriculum/recommended-level", headers=h).json()
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


@lru_cache(maxsize=1)   # 두 검사가 한 번 돌린 결과를 함께 쓴다
def _run():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1",
                   T_DB=f"{d}/t.db")
        for k in ("ANTHROPIC_API_KEY", "LIPLAB_UNLOCK_ALL", "LIPLAB_REVIEW"):
            env.pop(k, None)                        # 기본(모든 단계 열림)으로 3단계 숙달이 쌓이는지 본다
        p = subprocess.run([sys.executable, "-c", _SCENARIO], cwd=here, env=env,
                           capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    return json.loads(line[len("RESULT "):])


def test_review_sessions_skip_stage3_mastery_but_keep_records():
    r = _run()
    assert r["after_lesson"] == 8, r
    assert r["review_status"] == ["success"] * 4, "복습 답도 기록·XP는 그대로다"
    assert all(x > 0 for x in r["review_xp"]), r["review_xp"]
    assert r["after_review"] == 8, "복습·북마크 답이 3단계 숙달에 들어갔다"
    assert r["review_list_before"] == ["창가 자리에 앉을게요"]
    assert r["review_list_after"] == [], "복습에서 맞힌 문장이 오답 목록에서 빠지지 않았다"
    assert r["after_lookalike"] == 9, "이름만 비슷한 일반 레슨은 숙달에 넣는다"


def test_recommended_level_ignores_review_rows():
    r = _run()
    before, after = r["rec_before_review"], r["rec_after_review"]
    assert before["recommended_level"] == 5, before
    # 예전에는 최근 행(복습, 난이도 1)을 기준으로 삼아 2를 추천했다
    assert after["recommended_level"] == 5 and after["sample"] == before["sample"], after
    # 복습이 아닌 가장 최근 행(난이도 3)이 기준이 된다
    assert r["rec_after_lookalike"]["recommended_level"] == 4, r["rec_after_lookalike"]
