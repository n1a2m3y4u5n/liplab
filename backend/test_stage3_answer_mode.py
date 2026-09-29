"""3단계 문장 답 방식(/api/progress answer_mode)의 기록과 4지선다 우연 보정(docs/mastery-ewma.md 10절).

- progress.answer_mode에 'choice'·'typed'만 남기고, 보내지 않거나 다른 값이면 비워 둔다.
- 3단계 숙달 이동 평균에 4지선다 정답은 1, 오답은 −1/3으로 들어간다. 주관식·서술형은 합격 1, 불합격 0 그대로다.
- 정답 수(stage_progress.correct)는 답 방식과 상관없이 합격 수다.
test_stage3_speed_record.py와 같은 방식: 임시 DB를 지정한 별도 프로세스에서 시나리오를 돌리고 결과(JSON)만 검사한다.
"""
import json
import os
import subprocess
import sys
import tempfile

os.environ.setdefault("JWT_SECRET", "test-only-answer-mode-secret")

_SCENARIO = r'''
import json, os, sqlite3
from fastapi.testclient import TestClient
import main

def sql(q, *a):
    db = sqlite3.connect(os.environ["T_DB"])
    rows = db.execute(q, a).fetchall()
    db.commit(); db.close()
    return rows

def user(c, n):
    r = c.post("/api/auth/register", json={"email": f"am{n}@example.com", "username": f"답방식{n}", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    return {"Authorization": "Bearer " + r.json()["access_token"]}

lesson = ["따뜻한 아메리카노 한 잔 주세요", "영수증은 버려 주세요", "포장해 주세요", "카드로 계산할게요",
          "얼음은 조금만 넣어 주세요", "진동벨 받아 가세요"]
wrong = {1, 4}
out = {}
with TestClient(main.app) as c:
    choice, typed, legacy = user(c, 1), user(c, 2), user(c, 3)
    for h, extra in ((choice, {"answer_mode": "choice"}), (typed, {"answer_mode": "typed"}), (legacy, {"answer_mode": "bogus"})):
        for i, s in enumerate(lesson):
            ans = lesson[(i + 1) % len(lesson)] if (i in wrong and extra["answer_mode"] == "choice") else ("ㅋ" if i in wrong else s)
            r = c.post("/api/progress", headers=h, json={"scenario_id": "lesson_1", "sentence": s, "user_answer": ans,
                                                         "time_spent_seconds": 5, "situation": "카페", "difficulty_level": 2, **extra})
            assert r.status_code == 200, r.text
    out["mastery"] = [list(r) for r in sql("select mastery_score, correct, attempts from stage_progress where stage = 3 order by user_id")]
    out["modes"] = [r[0] for r in sql("select answer_mode from progress order by user_id, id")]
    ev = c.get("/api/eval/summary", headers=choice).json()
    out["by_mode"] = ev.get("sentence_by_mode")
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


def test_answer_mode_recorded_and_choice_chance_corrected():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1", T_DB=f"{d}/t.db")
        for k in ("ANTHROPIC_API_KEY", "LIPLAB_UNLOCK_ALL", "LIPLAB_REVIEW"):
            env.pop(k, None)
        p = subprocess.run([sys.executable, "-c", _SCENARIO], cwd=here, env=env, capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])

    import main
    passes = [i not in (1, 4) for i in range(6)]

    def run(credits):
        est = 0.0
        for n, v in enumerate(credits):
            est = main._ewma_mastery(est, n, v)
        return est

    want_choice = run([1.0 if ok else -1.0 / 3 for ok in passes])
    want_typed = run([1.0 if ok else 0.0 for ok in passes])
    (m_choice, c_choice, a_choice), (m_typed, c_typed, a_typed), (m_legacy, _, _) = r["mastery"]
    assert abs(m_choice - want_choice) < 1e-6 and abs(m_typed - want_typed) < 1e-6
    assert m_choice < m_typed                     # 4지선다 오답은 추정값을 더 내린다
    assert abs(m_legacy - want_typed) < 1e-6      # 알 수 없는 값은 지금처럼 0·1
    assert c_choice == c_typed == 4 and a_choice == a_typed == 6
    assert r["modes"] == ["choice"] * 6 + ["typed"] * 6 + [None] * 6
    by = {row["mode"]: row for row in r["by_mode"]}
    assert by["choice"]["n"] == 6 and by["choice"]["pass_rate"] == round(4 / 6 * 100, 1)
    assert set(by) == {"choice"}


def test_stage3_credit_and_negative_success():
    import main
    assert main._stage3_credit(True, "choice") == 1.0
    assert main._stage3_credit(False, "choice") == main._CHOICE_WRONG_CREDIT == -1.0 / 3
    assert main._stage3_credit(False, "typed") == 0.0 and main._stage3_credit(False, None) == 0.0
    assert main._answer_mode("choice") == "choice" and main._answer_mode("typed") == "typed"
    assert main._answer_mode("essay") is None and main._answer_mode(None) is None
    # 음수 성공 정도도 받되 저장값은 0~100이다
    assert main._ewma_mastery(0.0, 0, -1.0 / 3) == 0.0
    assert main._ewma_mastery(50.0, 10, -1.0 / 3) < main._ewma_mastery(50.0, 10, 0.0) < 50.0
