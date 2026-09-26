"""9/26 전체 검토에서 고친 결함의 회귀 테스트.

- 데모 기록 채우기는 공용 데모 계정에만 한다(로그인·회원가입 계정에 가짜 기록이 들어가던 결함).
- 공용 데모 계정은 학습 초기화(분석 초기화)를 할 수 없다.
- 같은 사용자·단계 행이 두 벌이면 켜질 때 하나만 남기고 고유 인덱스를 건다(두 벌이면 답 제출이 500이었다).
- 숙달한 단계는 오답 몇 개로 풀리지 않고, 직전 단계가 잠겨 있으면 뒤 단계가 열리지 않으며, 잠긴 단계의 답은 숙달에 넣지 않는다.
- 정답을 본 뒤의 제출(practice_only)은 숙달·XP에 넣지 않는다.
- 긴 입력·긴 비밀번호·대소문자만 다른 이메일·자유 입력 상황의 대화 대체 문구.

database 모듈이 import 시점에 DATABASE_URL을 읽으므로 임시 DB를 지정한 별도 프로세스에서 시나리오를 돌리고
결과(JSON)만 검사한다(test_account_security.py와 같은 방식).
"""
import json
import os
import subprocess
import sys
import tempfile

_FLOW = r'''
import json, os
from fastapi.testclient import TestClient
import main, curriculum

out = {}
with TestClient(main.app) as c:
    reg = {"username": "tester1", "password": "pw-123456", "agree_terms": True, "age_confirmed": True}
    r = c.post("/api/auth/register", json={**reg, "email": "u1@example.com"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}

    # 1. 실제 계정에 데모 기록을 채우지 않는다
    out["seed_user"] = c.post("/api/seed-demo", headers=h).json()
    out["user_xp_after_seed"] = c.get("/api/auth/me", headers=h).json().get("total_xp")
    demo = {"Authorization": f"Bearer {c.post('/api/auth/demo').json()['access_token']}"}
    out["seed_demo_1"] = c.post("/api/seed-demo", headers=demo).json()
    out["seed_demo_2"] = c.post("/api/seed-demo", headers=demo).json()

    # 2. 공용 데모 계정은 분석 초기화 불가, 본인 계정은 가능
    out["reset_demo"] = c.delete("/api/analysis/reset", headers=demo).status_code
    out["reset_user"] = c.delete("/api/analysis/reset", headers=h).status_code

    # 3. 단계 잠금: 배치(1단계) 뒤 문맥 추론을 맞혀도 잠긴 3단계에 쌓이지 않고 4단계가 열리지 않는다
    c.post("/api/curriculum/track", json={"track": "perception"}, headers=h)
    it = curriculum.CLOSURE_ITEMS[0]
    for _ in range(6):
        c.post("/api/curriculum/closure-answer", json={"item_id": it["id"], "chosen": it["answer"]}, headers=h)
    st = {s["stage"]: s for s in c.get("/api/curriculum/stages", headers=h).json()["stages"]}
    out["closure_stage3"] = [st[3]["status"], st[3].get("attempts")]
    out["closure_stage4"] = st[4]["status"]

    # 4. 1단계를 숙달한 뒤 오답이 이어져도 숙달이 유지되고 2단계가 열린 채로 있다
    for _ in range(8):
        c.post("/api/curriculum/recognition", json={"viseme_id": 1, "chosen_id": 1}, headers=h)
    for _ in range(6):
        c.post("/api/curriculum/recognition", json={"viseme_id": 1, "chosen_id": 2}, headers=h)
    st = {s["stage"]: s for s in c.get("/api/curriculum/stages", headers=h).json()["stages"]}
    out["sticky"] = [st[1]["status"], st[2]["status"]]

    # 5. 정답을 본 뒤 제출은 점수만 주고 XP·숙달에 넣지 않는다
    body = {"scenario_id": "t1", "sentence": "사과 주세요", "user_answer": "사과 주세요",
            "time_spent_seconds": 5, "situation": "카페", "difficulty_level": 1, "practice_only": True}
    r = c.post("/api/progress", json=body, headers=h).json()
    out["practice_only"] = [r.get("status"), r.get("score"), r.get("xp_gained")]
    # 음수 시간·범위 밖 난이도는 서버가 맞춘다(예전에는 시간 보너스로 XP가 수만씩 붙었다)
    xp0 = c.get("/api/auth/me", headers=h).json()["total_xp"]
    c.post("/api/progress", json={**body, "practice_only": False, "time_spent_seconds": -100000,
                                  "difficulty_level": 9}, headers=h)
    out["xp_gain_bounded"] = c.get("/api/auth/me", headers=h).json()["total_xp"] - xp0

    # 6. 긴 입력은 채점 전에 거절한다
    out["score_long"] = c.post("/api/score", json={"correct": "가" * 5000, "user_answer": "가" * 5000},
                               headers=h).status_code
    out["placement_n0"] = c.get("/api/assessment/placement", params={"n": 0}, headers=h).status_code

    # 7. 비밀번호 72바이트 초과는 500이 아니라 거절
    out["reg_long_pw"] = c.post("/api/auth/register", json={**reg, "username": "tester9",
                                "email": "u9@example.com", "password": "가" * 30}).status_code
    out["login_long_pw"] = c.post("/api/auth/login", json={"email": "u1@example.com",
                                  "password": "가" * 30}).status_code

    # 8. 이메일은 소문자로 저장하고, 대소문자만 다른 주소로는 다시 가입할 수 없다
    r = c.post("/api/auth/register", json={**reg, "username": "tester2", "email": "Case@Example.com"})
    out["case_stored"] = r.json().get("user", {}).get("email")
    out["case_dup"] = c.post("/api/auth/register", json={**reg, "username": "tester3",
                             "email": "case@example.com"}).status_code
    out["case_login"] = c.post("/api/auth/login", json={"email": "CASE@example.com",
                               "password": "pw-123456"}).status_code

    # 9. 목록에 없는 상황(자유 입력)에서 LLM이 실패해도 대화가 이어진다(예전에는 0으로 나눠 500)
    r = c.post("/api/conversation", json={"situation": "카페에서 음료 주문하기", "level": 1, "history": []},
               headers=h)
    out["conv_free"] = [r.status_code, bool((r.json() or {}).get("text"))]
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''

_DEDUPE_SETUP = r'''
import json
from fastapi.testclient import TestClient
import main
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "d1@example.com", "username": "dup1", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    print("RESULT " + json.dumps({"token": r.json()["access_token"], "uid": r.json()["user"]["id"]}))
'''

_DEDUPE_CHECK = r'''
import json, os, sqlite3
from fastapi.testclient import TestClient
import main
tok = os.environ["T_TOKEN"]
with TestClient(main.app) as c:   # 켜질 때 init_db가 중복을 정리한다
    r = c.post("/api/curriculum/word-answer", json={"word": "바다", "correct": True, "chosen": "바다"},
               headers={"Authorization": f"Bearer {tok}"})
db = sqlite3.connect(os.environ["T_DB"])
rows = db.execute("select status, attempts from stage_progress where user_id=? and stage=2",
                  (int(os.environ["T_UID"]),)).fetchall()
idx = [x[1] for x in db.execute("pragma index_list('stage_progress')")]
print("RESULT " + json.dumps({"word_answer": r.status_code, "rows": rows,
                              "unique_index": "ux_stage_progress_user_id_stage" in idx}))
'''


def _run(code, d, extra=None):
    here = os.path.dirname(os.path.abspath(__file__))
    env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1",
               LIPLAB_UNLOCK_ALL="0", **(extra or {}))
    for k in ("LIPLAB_REVIEW", "ANTHROPIC_API_KEY", "LIPLAB_ADMIN_EMAILS"):
        env.pop(k, None)
    p = subprocess.run([sys.executable, "-c", code], cwd=here, env=env, capture_output=True, text=True, timeout=240)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    return json.loads(line[len("RESULT "):])


def test_review_fixes_flow():
    with tempfile.TemporaryDirectory() as d:
        r = _run(_FLOW, d)
    assert r["seed_user"] == {"seeded": False} and r["user_xp_after_seed"] == 0, "실제 계정에 데모 기록이 들어갔다"
    assert r["seed_demo_1"] == {"seeded": True} and r["seed_demo_2"] == {"seeded": False}
    assert r["reset_demo"] == 403 and r["reset_user"] == 200
    assert r["closure_stage3"][0] == "locked" and not r["closure_stage3"][1], "잠긴 3단계에 문맥 추론이 쌓였다"
    assert r["closure_stage4"] == "locked", "2·3단계가 잠긴 채 4단계가 열렸다"
    assert r["sticky"] == ["mastered", "unlocked"], "숙달이 오답으로 풀려 2단계가 다시 잠겼다"
    assert r["practice_only"][0] == "practice_only" and r["practice_only"][1] > 90 and r["practice_only"][2] == 0
    assert 0 <= r["xp_gain_bounded"] < 2000, "음수 시간·범위 밖 난이도로 XP가 부풀었다"
    assert r["score_long"] == 422 and r["placement_n0"] == 200
    assert r["reg_long_pw"] == 422 and r["login_long_pw"] == 401
    assert r["case_stored"] == "case@example.com" and r["case_dup"] == 400 and r["case_login"] == 200
    assert r["conv_free"] == [200, True]


def test_duplicate_stage_rows_are_merged_on_startup():
    import sqlite3
    with tempfile.TemporaryDirectory() as d:
        key = {"JWT_SECRET": "test-only-dedupe-secret-0926"}   # 두 프로세스가 같은 키로 토큰을 읽게(로컬 기본은 무작위 키)
        s = _run(_DEDUPE_SETUP, d, key)
        db = sqlite3.connect(f"{d}/t.db")
        db.execute("drop index if exists ux_stage_progress_user_id_stage")   # 예전 DB처럼 고유 인덱스 없이
        for status, attempts, correct in (("in_progress", 12, 8), ("mastered", 36, 29)):
            db.execute("insert into stage_progress (user_id, stage, status, mastery_score, attempts, correct) "
                       "values (?, 2, ?, ?, ?, ?)", (s["uid"], status, correct / attempts * 100, attempts, correct))
        db.commit()
        db.close()
        r = _run(_DEDUPE_CHECK, d, {**key, "T_TOKEN": s["token"], "T_UID": str(s["uid"]), "T_DB": f"{d}/t.db"})
    assert r["word_answer"] == 200, "중복 행이 남아 단어 답 제출이 실패했다"
    assert r["unique_index"], "고유 인덱스가 없다"
    assert len(r["rows"]) == 1 and r["rows"][0][0] == "mastered", r["rows"]
