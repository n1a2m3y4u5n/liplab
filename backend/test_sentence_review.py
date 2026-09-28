"""문장 간격 반복 복습(ReviewItem kind 'sentence', 오늘의 복습).

- 3단계 레슨에서 합격선(60) 아래인 문장은 내일 복습에 들어간다. 합격한 문장, 정답을 본 뒤의 제출(practice_only),
  틀린 문장 복습(mistake_review_*)·북마크 연습(bookmark_*)의 답, 큐 칸보다 긴 문장은 넣지 않는다.
- 예정일이 되면 /api/review/due의 items 끝에 상황·난이도와 함께 나온다. 하루 5개까지이고, 오늘 이미 다시 읽은 문장 수를 뺀다.
- 복습 답(srs_review_*)은 점수 등급으로 간격을 조정한다(맞히면 1 → 6일 …, 졸업하면 큐에서 빠짐, 틀리면 내일).
  3단계 숙달(시도 수)과 추천 난이도에는 들어가지 않는다.
- 오늘의 복습에 나온 문장은 틀린 문장 목록(/api/review-sentences)에서 빠지고, 과제 탭의 남은 복습 수는 예정 목록과 같다.

test_review_king_badge.py와 같은 방식: 임시 DB를 지정한 별도 프로세스에서 시나리오를 돌리고 결과(JSON)만 검사한다.
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

def sql(q, *a):
    db = sqlite3.connect(os.environ["T_DB"])
    rows = db.execute(q, a).fetchall()
    db.commit(); db.close()
    return rows

TODAY = main._kst_today().isoformat()

def submit(c, h, sid, sentence, answer, level=3, **extra):
    body = {"scenario_id": sid, "sentence": sentence, "user_answer": answer, "time_spent_seconds": 5,
            "situation": "카페", "difficulty_level": level, **extra}
    return c.post("/api/progress", headers=h, json=body).json()

def items():
    return {r[0]: {"due": r[1], "interval": r[2], "reps": r[3], "lapses": r[4], "ease": r[5]}
            for r in sql("select ref, due_date, interval_days, repetitions, lapses, ease_factor "
                         "from review_items where kind = 'sentence'")}

def stage3():
    row = sql("select attempts from stage_progress where stage = 3")
    return row[0][0] if row else 0

def due(c, h):
    d = c.get("/api/review/due", headers=h).json()
    return d, [x for x in d["items"] if x["kind"] == "sentence"]

out = {}
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "sr@example.com", "username": "문장복습", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    uid = sql("select id from users")[0][0]
    wrong = "창가 자리에 앉을게요"
    submit(c, h, "lesson_1", wrong, "ㅋ", level=4)                         # 레슨에서 틀림 → 큐에 들어감
    submit(c, h, "lesson_1", "포장해 주세요", "포장해 주세요")               # 합격 → 넣지 않음
    submit(c, h, "lesson_1", "영수증은 버려 주세요", "ㅋ", practice_only=True)   # 정답을 본 뒤 → 넣지 않음
    submit(c, h, "mistake_review_1", "진동벨 받아 가세요", "ㅋ")              # 틀린 문장 복습 → 넣지 않음
    submit(c, h, "bookmark_3", "빨대는 저기 있어요", "ㅋ")                   # 북마크 연습 → 넣지 않음
    submit(c, h, "lesson_1", "가" * 120, "ㅋ")                              # 큐 칸(100자)보다 김 → 넣지 않음
    it = items()
    out["enqueued"] = sorted(it)
    out["first"] = it.get(wrong)
    out["due_before"] = [x["ref"] for x in due(c, h)[1]]
    # 예정일 전에 레슨에서 다시 맞혀도 간격은 그대로(말하기·단어와 같은 규칙)
    submit(c, h, "lesson_2", wrong, wrong, level=4)
    out["early_pass"] = items()[wrong]
    out["stage3_before_review"] = stage3()

    # 예정일이 됨 → 오늘의 복습에 상황·난이도와 함께 나오고, 틀린 문장 목록에서는 빠진다
    submit(c, h, "lesson_3", wrong, "ㅋ", level=4)   # 가장 최근 시도를 다시 오답으로(틀린 문장 목록 대상)
    out["mistakes_not_due"] = [x["sentence"] for x in c.get("/api/review-sentences", headers=h).json()]
    sql("update review_items set due_date = ? where kind = 'sentence'", TODAY)
    out["before_review"] = items()[wrong]
    d, sents = due(c, h)
    out["due_entry"] = {k: sents[0].get(k) for k in ("ref", "situation", "difficulty_level")} if sents else None
    out["due_counts"] = [d["count"], d["sentence_count"], d["sentence_daily_cap"], d["total"]]
    out["mistakes_due"] = [x["sentence"] for x in c.get("/api/review-sentences", headers=h).json()]
    out["tasks_review_done"] = next(t["done"] for t in c.get("/api/tasks", headers=h).json()["daily"] if t["key"] == "review_clear")

    # 복습에서 맞힘(100점): 간격이 늘고 3단계 숙달·추천 난이도에는 들어가지 않는다
    rv = submit(c, h, "srs_review_1", wrong, wrong, level=4)
    out["review_resp"] = [rv["status"], rv["passed"], rv["xp_gained"] > 0]
    out["after_pass"] = items()[wrong]
    out["stage3_after_review"] = stage3()
    out["due_after_pass"] = [x["ref"] for x in due(c, h)[1]]
    # 예정일마다 맞혀 졸업할 때까지
    answers = 1
    for _ in range(12):
        if wrong not in items():
            break
        sql("update review_items set due_date = ? where kind = 'sentence'", TODAY)
        submit(c, h, "srs_review_1", wrong, wrong, level=4)
        answers += 1
    out["answers_to_graduate"] = answers
    out["stage3_after_graduate"] = stage3()

    # 복습에서 틀림: 내일 다시(누수 +1)
    s2 = "얼음은 조금만 넣어 주세요"
    submit(c, h, "lesson_4", s2, "ㅋ")
    sql("update review_items set due_date = ? where kind = 'sentence'", TODAY)
    submit(c, h, "srs_review_2", s2, "ㅋ")
    out["after_fail"] = items()[s2]

    # 하루 5개 상한: 오늘 이미 두 문장(wrong, s2)을 다시 읽었으니 3개까지만 나온다. 새 날에는 5개
    lesson = ["따뜻한 아메리카노 한 잔 주세요", "카드로 계산할게요", "샷 추가해 주세요", "시럽은 빼 주세요",
              "머그잔에 담아 주세요", "케이크도 하나 주세요", "와이파이 비밀번호가 뭐예요"]
    for s in lesson:
        submit(c, h, "lesson_5", s, "ㅋ")
    sql("update review_items set due_date = ? where kind = 'sentence'", TODAY)
    d, sents = due(c, h)
    out["cap_today"] = [len(sents), d["sentence_count"], len(items())]
    out["mistakes_capped"] = len(c.get("/api/review-sentences", headers=h).json())
    sql("update progress set created_at = '2000-01-01 00:00:00' where scenario_id like 'srs\_review\_%' escape '\\'")
    d, sents = due(c, h)
    out["cap_new_day"] = len(sents)
    out["stage3_final"] = stage3()
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


@lru_cache(maxsize=1)
def _run():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1",
                   T_DB=f"{d}/t.db")
        for k in ("ANTHROPIC_API_KEY", "LIPLAB_UNLOCK_ALL", "LIPLAB_REVIEW"):
            env.pop(k, None)
        p = subprocess.run([sys.executable, "-c", _SCENARIO], cwd=here, env=env,
                           capture_output=True, text=True, timeout=240)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    return json.loads(line[len("RESULT "):])


def test_enqueue_only_failed_lesson_sentences():
    r = _run()
    assert r["enqueued"] == ["창가 자리에 앉을게요"], r["enqueued"]
    first = r["first"]
    assert first["interval"] == 1 and first["lapses"] == 1 and first["reps"] == 0, first
    assert r["due_before"] == [], "예정일(내일) 전에 오늘의 복습에 나왔다"
    assert r["early_pass"] == first, "예정일 전 레슨 합격이 간격을 바꿨다"


def test_due_listing_with_meta_and_mistake_dedupe():
    r = _run()
    assert "창가 자리에 앉을게요" in r["mistakes_not_due"], "예정일 전에는 틀린 문장 목록에 그대로 있어야 한다"
    assert r["due_entry"] == {"ref": "창가 자리에 앉을게요", "situation": "카페", "difficulty_level": 4}, r["due_entry"]
    assert r["due_counts"] == [1, 1, 5, 1], r["due_counts"]
    assert "창가 자리에 앉을게요" not in r["mistakes_due"], "오늘의 복습에 나온 문장이 오답 목록에도 남았다"
    assert r["tasks_review_done"] is False


def test_review_answer_schedules_by_score():
    r = _run()
    assert r["review_resp"] == ["success", True, True], r["review_resp"]
    before, after = r["before_review"], r["after_pass"]
    assert before["reps"] == 0 and before["lapses"] == 2, before   # 예정일 전이라도 레슨에서 다시 틀리면 다시 잡는다
    assert after["reps"] == 1 and after["interval"] == 1 and after["lapses"] == 2, after
    assert after["ease"] == round(before["ease"] + 0.1, 3), "100점 복습이 ease를 올리지 않았다(점수 등급 5 반영)"
    assert r["due_after_pass"] == [], "복습을 마친 문장이 오늘 목록에 남았다"
    # 1 → 6 → 6×ease … 60일 넘으면 졸업(말하기·단어 복습과 같은 SM-2)
    assert r["answers_to_graduate"] == 5, r["answers_to_graduate"]
    fail = r["after_fail"]
    assert fail["lapses"] == 2 and fail["reps"] == 0 and fail["interval"] == 1, fail


def test_review_answers_do_not_count_toward_stage3_mastery():
    r = _run()
    # 레슨 네 건(틀림·합격·큐 칸 초과·예정일 전 합격). practice_only·틀린 문장 복습·북마크는 넣지 않는다
    base = r["stage3_before_review"]
    assert base == 4, base
    assert r["stage3_after_review"] == base + 1, "문장 복습 답이 3단계 숙달에 들어갔다"   # lesson_3 한 건만
    assert r["stage3_after_graduate"] == base + 1
    assert r["stage3_final"] == base + 1 + 1 + 7   # lesson_4 한 건 + lesson_5 일곱 건, 복습 답은 없음


def test_daily_cap():
    r = _run()
    today, total_sentence_items = r["cap_today"][0], r["cap_today"][2]
    assert total_sentence_items == 8, r["cap_today"]           # s2 + 새 문장 7개(졸업한 문장은 없음)
    assert today == 3 and r["cap_today"][1] == 3, "오늘 이미 두 문장을 다시 읽어 3개만 나와야 한다"
    assert r["cap_new_day"] == 5, "하루 상한은 5개"
    # 오늘 낸 3개만 틀린 문장 목록에서 빠진다(오답 11개 중 8개, 상한에 밀린 문장은 목록에 남는다)
    assert r["mistakes_capped"] == 8, r["mistakes_capped"]
