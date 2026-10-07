"""3단계 자음 피드백(sentence_feedback) 테스트."""
from sentence_feedback import consonant_feedback, skeleton


def test_skeleton_shows_onsets_only():
    assert skeleton("바로곡") == ["ㅂ", "ㄹ", "ㄱ"]
    assert skeleton("아이") == ["ㅇ", "ㅇ"]
    assert skeleton("주세요?") == ["ㅈ", "ㅅ", "ㅇ"]   # 문장 부호는 뺀다
    assert skeleton("3시") == ["3", "ㅅ"]


def test_all_correct_and_spacing_free_punctuation():
    r = consonant_feedback("물 좀 주세요.", "물 좀 주세요")
    assert r["correct_words"] == r["total_words"] == 3
    assert all(w["correct"] and w["text"] for w in r["words"])


def test_wrong_words_hide_text_and_show_skeleton():
    r = consonant_feedback("물 좀 주세요", "불 좀 주세요")
    first = r["words"][0]
    assert first == {"text": None, "correct": False, "skeleton": ["ㅁ"]}
    assert r["correct_words"] == 2 and r["total_words"] == 3


def test_same_pronunciation_counts_as_correct():
    # 표기는 달라도 소리 나는 대로 같으면 맞힌 것(같이 → [가치])
    r = consonant_feedback("같이 가요", "가치 가요")
    assert r["correct_words"] == 2


def test_order_kept_and_empty_answer():
    r = consonant_feedback("오늘 날씨 좋네요", "좋네요 오늘")
    assert r["correct_words"] == 1   # 순서가 바뀐 낱말은 한쪽만 맞힌 것으로
    e = consonant_feedback("오늘 날씨 좋네요", "")
    assert e["correct_words"] == 0 and all(w["skeleton"] for w in e["words"])


# API: 주관식 응답에 word_feedback이 붙고, 4지선다에는 없다(임시 DB, 별도 프로세스)
_FLOW = r'''
import json
from fastapi.testclient import TestClient
import main
out = {}
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "wf@example.com", "username": "wf1", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    body = {"scenario_id": "t", "sentence": "물 좀 주세요.", "time_spent_seconds": 5, "situation": "식당", "difficulty_level": 1}
    out["typed"] = c.post("/api/progress", json={**body, "user_answer": "불 좀 주세요", "answer_mode": "typed"}, headers=h).json()
    out["retry"] = c.post("/api/progress", json={**body, "user_answer": "물 좀 주세요", "answer_mode": "typed",
                                                 "practice_only": True}, headers=h).json()
    out["choice"] = c.post("/api/progress", json={**body, "user_answer": "물 좀 주세요.", "answer_mode": "choice"}, headers=h).json()
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


def test_progress_returns_word_feedback_for_typed_only():
    import json, os, subprocess, sys, tempfile
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1")
        env.pop("ANTHROPIC_API_KEY", None)
        p = subprocess.run([sys.executable, "-c", _FLOW], cwd=here, env=env, capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])
    wf = r["typed"]["word_feedback"]
    assert wf["total_words"] == 3 and wf["correct_words"] == 2
    assert wf["words"][0] == {"text": None, "correct": False, "skeleton": ["ㅁ"]}
    assert r["retry"]["status"] == "practice_only" and r["retry"]["word_feedback"]["correct_words"] == 3
    assert r["choice"].get("word_feedback") is None


def test_scoring_ignores_any_whitespace_and_punctuation():
    # 전각 공백·줄 바꿈 없는 공백·탭·쉼표가 낱말 사이에 있어도 연음이 막히지 않는다(docs/pilot/typed-scoring-check.md)
    import asyncio
    from scoring import calculate_score
    for a in ["옷 입어", "옷입어", "옷　입어", "옷 입어", "옷\t입어", "옷,입어", "옷 입어!"]:
        assert asyncio.run(calculate_score("옷 입어", a, mode="visual"))["score"] == 100.0, repr(a)


_FLOW_LOG = r'''
import asyncio, json
from fastapi.testclient import TestClient
import main, database
from sqlalchemy import select
out = {}
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "pl@example.com", "username": "pl1", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    uid = r.json()["user"]["id"]
    body = {"scenario_id": "t", "sentence": "물 좀 주세요.", "time_spent_seconds": 5, "situation": "식당", "difficulty_level": 1,
            "answer_mode": "typed"}
    c.post("/api/progress", json={**body, "user_answer": "불 좀 주세요"}, headers=h)
    c.post("/api/progress", json={**body, "user_answer": "물 좀 주세요", "practice_only": True,
                                  "practice_reason": "consonant_retry", "hint_level": 2, "rt_from_onset_ms": 4200}, headers=h)
    c.post("/api/progress", json={**body, "user_answer": "물 좀", "practice_only": True, "practice_reason": "weird"}, headers=h)
    async def rows():
        async with database.AsyncSessionLocal() as db:
            rs = (await db.execute(select(database.SentencePracticeLog).where(
                database.SentencePracticeLog.user_id == uid).order_by(database.SentencePracticeLog.id))).scalars().all()
            prog = (await db.execute(select(database.Progress).where(database.Progress.user_id == uid))).scalars().all()
            return [(x.reason, x.score, x.hint_level, x.rt_from_onset_ms, x.words_correct, x.words_total) for x in rs], len(prog)
    out["logs"], out["n_progress"] = asyncio.run(rows())
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


def test_practice_only_answers_are_logged_separately():
    import json, os, subprocess, sys, tempfile
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1")
        env.pop("ANTHROPIC_API_KEY", None)
        p = subprocess.run([sys.executable, "-c", _FLOW_LOG], cwd=here, env=env, capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])
    assert r["n_progress"] == 1   # 연습 답은 진행 기록(숙달·오답 목록)에 들어가지 않는다
    assert len(r["logs"]) == 2
    assert r["logs"][0][0] == "consonant_retry" and r["logs"][0][1] == 100.0 and r["logs"][0][2:] == [2, 4200, 3, 3]
    assert r["logs"][1][0] is None   # 알 수 없는 사유는 비운다


def test_merged_vowel_spellings_count_as_correct():
    # 소리로 가르지 못하는 모음 표기(ㅐ·ㅔ, 이에요·이예요, ㅙ·ㅚ·ㅞ, 자음 뒤 ㅖ, 첫머리 아닌 의)는 맞힌 것
    for target, answer in [("물 좀 주세요", "물 좀 주새요"), ("저는 학생이에요", "저는 학생이예요"),
                           ("이건 의자예요", "이건 의자에요"), ("아니에요", "아니예요"), ("안 돼요", "안 되요"),
                           ("계속 가요", "게속 가요"), ("우리의 집", "우리이 집")]:
        r = consonant_feedback(target, answer)
        assert r["correct_words"] == r["total_words"], (target, answer)


def test_word_initial_vowels_still_differ():
    # 낱말 첫머리의 예/에, 의/이는 소리로 갈리므로 그대로 틀린 것
    assert consonant_feedback("예", "에")["correct_words"] == 0
    assert consonant_feedback("의사", "이사")["correct_words"] == 0
    assert consonant_feedback("물 좀 주세요", "물 좀 주시요")["correct_words"] == 2   # 다른 모음은 여전히 틀림


def test_spacing_is_ignored():
    # 띄어쓰기를 틀려도 낱말을 소리대로 다 적었으면 맞힌 것(예전에는 붙여 쓴 낱말이 모두 틀림)
    for target, answer in [("가을 산에서 밤을 주웠어", "가을산에서 밤을 주웠어"), ("물 좀 주세요", "물좀 주세요"),
                           ("내일 다시 올게요", "내일다시 올께요"), ("같이 갈 수 있어요", "같이 갈수 있어요"),
                           ("책을 읽고 있어요", "책을 읽고있어요"), ("국물이 짜요", "궁물이 짜요")]:
        r = consonant_feedback(target, answer)
        assert r["correct_words"] == r["total_words"], (target, answer)


def test_order_and_missing_words_still_count():
    r = consonant_feedback("물 좀 주세요", "좀 물 주세요")
    assert r["correct_words"] == 2          # 순서가 바뀐 낱말 하나는 세지 않는다
    assert consonant_feedback("물 좀 주세요", "")["correct_words"] == 0
    r = consonant_feedback("오늘 날씨가 좋아요", "날씨가")
    assert [w["correct"] for w in r["words"]] == [False, True, False]


def test_digits_in_answer_are_read_as_words():
    # 정답은 한글 수, 답은 숫자: 문맥 읽기·한자어·고유어 가운데 맞는 쪽으로 본다
    for target, answer in [("여섯 시 오십 분까지 극장 앞으로 와", "6시 50분까지 극장 앞으로 와"),
                           ("회의는 삼 층 큰 방에서 해요", "회의는 3층 큰 방에서 해요"),
                           ("부산행 기차는 칠 번 타는 곳에서 출발합니다", "부산행 기차는 7번 타는 곳에서 출발합니다"),
                           ("하루 세 번 드세요", "하루 3번 드세요"), ("물 한 잔 주세요", "물 1잔 주세요")]:
        r = consonant_feedback(target, answer)
        assert r["correct_words"] == r["total_words"], (target, answer)
    r = consonant_feedback("오 분 빨라요", "6분 빨라요")
    assert [w["correct"] for w in r["words"]] == [False, True, True]   # 다른 수는 틀림
