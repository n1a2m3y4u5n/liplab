"""측정 기록 네 가지의 서버 경로(10/6): FSRS 그림자 기록(C11), 숙달 지연 탐침(C16), 지연 유지 검사(C7), 레슨별 정신적 노력(C14).

- FSRS: 예정일이 된 복습 답만 review_logs에 남고(예정일 전 답·레슨 오답은 남지 않음), 4지선다 관측 확률은 0.25 + 0.75·R이다.
  간격은 SM-2(srs.schedule) 그대로다. 상태가 없던 예전 항목은 예측을 NULL로 남긴다.
- 탐침: 숙달 1·7일 뒤 회차가 생기고, 한 레슨에 비율 상한(12문항이면 3개)만큼 나온다. 답은 mastery_probes에만 남고 숙달·시행 기록·
  복습 큐는 그대로다.
- 유지 검사: 사후 검사 28일 뒤 due, 채점 결과는 retention_results에만 남고 사전·사후 비교(history·progression)는 그대로다.
- 노력: 세션마다 한 행, answered > skipped > left.

test_review_king_badge.py와 같은 방식(임시 DB를 지정한 별도 프로세스에서 시나리오를 돌리고 결과 JSON만 검사)."""
import json
import os
import subprocess
import sys
import tempfile
from functools import lru_cache

_SCENARIO = r'''
import json, math, os, sqlite3
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
import main, srs, fsrs_shadow as fs, assessment

def sql(q, *a):
    db = sqlite3.connect(os.environ["T_DB"])
    rows = db.execute(q, a).fetchall()
    db.commit(); db.close()
    return rows

def ago(days):
    return str(datetime.utcnow() - timedelta(days=days))

def register(c, email):
    r = c.post("/api/auth/register", json={"email": email, "username": email.split("@")[0], "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    return {"Authorization": "Bearer " + r.json()["access_token"]}

out = {}
today = main._kst_today()
with TestClient(main.app) as c:
    h = register(c, "m1@example.com")
    uid = sql("select id from users where email = 'm1@example.com'")[0][0]

    # ── C11 FSRS 그림자 ──
    c.post("/api/curriculum/recognition", headers=h, json={"viseme_id": 1, "chosen_id": 2})   # 레슨 오답 → 등록
    out["new_item"] = sql("select fsrs_stability, fsrs_difficulty, last_review_on, interval_days, ease_factor, repetitions, lapses "
                          "from review_items where kind='viseme'")[0]
    out["logs_after_lesson"] = sql("select count(*) from review_logs")[0][0]
    c.post("/api/review/answer", headers=h, json={"kind": "viseme", "ref": "1", "correct": True, "answer_mode": "choice", "speed": 1.0})
    out["logs_after_early"] = sql("select count(*) from review_logs")[0][0]     # 예정일 전: 남기지 않는다
    yday = (today - timedelta(days=1)).isoformat()
    sql("update review_items set due_date = ?, last_review_on = ? where kind='viseme'", today.isoformat(), yday)
    ef, iv, rp, lp = sql("select ease_factor, interval_days, repetitions, lapses from review_items where kind='viseme'")[0]
    st0 = sql("select fsrs_stability from review_items where kind='viseme'")[0][0]
    r = c.post("/api/review/answer", headers=h, json={"kind": "viseme", "ref": "1", "correct": True, "answer_mode": "choice", "speed": 1.0}).json()
    exp = srs.schedule(3, ease_factor=ef, interval_days=iv, repetitions=rp, lapses=lp)
    out["interval_same_as_sm2"] = r["interval_days"] == exp["interval_days"]
    row = sql("select source, elapsed_days, quality, grade, passed, guess, r_fsrs, p_fsrs, p_sm2, sm2_interval from review_logs")[0]
    out["log"] = row
    out["expect_r"] = fs.retrievability(1, st0)
    # 예정일이 된 항목을 레슨에서 다시 틀림(_srs_schedule_wrong): 맞힌 답이 오지 않는 경로라 남기지 않는다
    sql("update review_items set due_date = ? where kind='viseme'", today.isoformat())
    c.post("/api/curriculum/recognition", headers=h, json={"viseme_id": 1, "chosen_id": 2})
    out["logs_after_due_lesson_wrong"] = sql("select count(*) from review_logs")[0][0]
    # 상태가 없던 예전 항목
    sql("insert into review_items (user_id, kind, ref, due_date, interval_days, ease_factor, repetitions, lapses, created_at, updated_at) "
        "values (?, 'word', '나무', ?, 6, 2.3, 2, 1, ?, ?)", uid, today.isoformat(), ago(6), ago(6))
    c.post("/api/review/answer", headers=h, json={"kind": "word", "ref": "나무", "correct": False, "answer_mode": "choice", "speed": 1.0})
    out["legacy_log"] = sql("select elapsed_days, r_fsrs, p_fsrs, p_sm2, passed, grade from review_logs where kind='word'")[0]
    out["legacy_state"] = sql("select fsrs_stability is not null, last_review_on from review_items where kind='word'")[0]

    # ── C16 숙달 지연 탐침 ──
    sql("delete from stage_progress where user_id = ?", uid)
    for stage, d in ((1, 1), (2, 7), (3, 1)):
        sql("insert into stage_progress (user_id, stage, status, mastery_score, attempts, correct, mastered_attempts, mastered_at, updated_at) "
            "values (?, ?, 'mastered', 90, 20, 18, 10, ?, ?)", uid, stage, ago(d), ago(d))
    before = {t: sql(f"select count(*) from {t}")[0][0] for t in ("trial_attempts", "review_items", "progress")}
    sp_before = sql("select stage, status, mastery_score, attempts, correct from stage_progress order by stage")
    p1 = c.get("/api/curriculum/mastery-probes", headers=h, params={"lesson_len": 12}).json()
    out["probe_first"] = {"n": len(p1["items"]), "quota": p1["quota"], "pending": p1["pending"],
                          "stages": sorted(s for (s,) in sql("select distinct stage from mastery_probes")),
                          "waves": sorted(s for (s,) in sql("select distinct wave from mastery_probes")),
                          "speeds": sorted({it["speed"] for it in p1["items"]}),
                          "has_target": any("target" in it for it in p1["items"])}
    out["probe_rows"] = sql("select stage, wave, count(*) from mastery_probes group by stage, wave order by stage, wave")
    it = p1["items"][0]
    out["probe_answer"] = c.post("/api/curriculum/mastery-probe-answer", headers=h, json={"id": it["id"], "chosen": it["options"][0]["value"]}).json()
    out["probe_again"] = c.post("/api/curriculum/mastery-probe-answer", headers=h, json={"id": it["id"], "chosen": it["options"][0]["value"]}).json()
    out["probe_bad"] = c.post("/api/curriculum/mastery-probe-answer", headers=h, json={"id": p1["items"][1]["id"], "chosen": "없는 보기"}).status_code
    out["probe_row"] = sql("select chosen is not null, correct is not null, delay_days, speed from mastery_probes where id = ?", it["id"])[0]
    out["probe_untouched"] = (before == {t: sql(f"select count(*) from {t}")[0][0] for t in ("trial_attempts", "review_items", "progress")}
                              and sp_before == sql("select stage, status, mastery_score, attempts, correct from stage_progress order by stage"))
    p2 = c.get("/api/curriculum/mastery-probes", headers=h, params={"lesson_len": 12}).json()
    out["probe_second"] = {"n": len(p2["items"]), "pending": p2["pending"], "rebuilt": sql("select count(*) from mastery_probes")[0][0],
                           "skips_answered": it["id"] not in [x["id"] for x in p2["items"]]}
    out["probe_used_full"] = len(c.get("/api/curriculum/mastery-probes", headers=h, params={"lesson_len": 12, "used": 3}).json()["items"])
    h_other = register(c, "m2@example.com")
    out["probe_other_user"] = c.post("/api/curriculum/mastery-probe-answer", headers=h_other, json={"id": it["id"], "chosen": "x"}).status_code

    # ── C7 지연 유지 검사 ──
    ver = assessment.frozen_forms()["version"]
    out["ret_none"] = c.get("/api/assessment/retention", headers=h).json()["state"]
    log = json.dumps([{"id": "x", "word": "나무", "chosen": "나무", "correct": True, "difficulty": 0.5}])
    sql("insert into placement_results (user_id, form, total, correct, accuracy, ability, level, error_visemes, error_phonemes, form_version, item_log, created_at) "
        "values (?, 'A', 24, 12, 0.5, 0.4, 2, '[]', '[]', ?, ?, ?)", uid, ver, log, ago(40))
    sql("insert into placement_results (user_id, form, total, correct, accuracy, ability, level, error_visemes, error_phonemes, form_version, item_log, created_at) "
        "values (?, 'B', 24, 18, 0.75, 0.6, 3, '[]', '[]', ?, ?, ?)", uid, ver, log, ago(28))
    hist0 = c.get("/api/assessment/history", headers=h).json()
    prog0 = c.get("/api/assessment/progression", headers=h).json()
    st = c.get("/api/assessment/retention", headers=h).json()
    out["ret_due"] = {k: st.get(k) for k in ("state", "form", "days", "post_accuracy")}
    items = c.get("/api/assessment/retention/items", headers=h).json()["items"]
    out["ret_items"] = len(items)
    resp = {i["id"]: i["word"] for i in items[:20]}
    sc = c.post("/api/assessment/retention/score", headers=h, json={"responses": resp}).json()
    out["ret_score"] = {k: sc.get(k) for k in ("total", "correct", "form", "post_accuracy", "days_after_post")}
    out["ret_done"] = c.get("/api/assessment/retention", headers=h).json()["state"]
    out["ret_rows"] = sql("select form, total, correct, days_after_post from retention_results")
    out["ret_flows_unchanged"] = (hist0 == c.get("/api/assessment/history", headers=h).json()
                                  and prog0 == c.get("/api/assessment/progression", headers=h).json())
    out["ret_placement_rows"] = sql("select count(*) from placement_results")[0][0]
    out["ret_score_again"] = c.post("/api/assessment/retention/score", headers=h, json={"responses": resp}).status_code
    uid2 = sql("select id from users where email = 'm2@example.com'")[0][0]
    for form, d in (("A", 20), ("B", 10)):
        sql("insert into placement_results (user_id, form, total, correct, accuracy, ability, level, error_visemes, error_phonemes, form_version, item_log, created_at) "
            "values (?, ?, 24, 12, 0.5, 0.4, 2, '[]', '[]', ?, '[]', ?)", uid2, form, ver, ago(d))
    st2 = c.get("/api/assessment/retention", headers=h_other).json()
    out["ret_waiting"] = {"state": st2["state"], "days_left": st2["days_left"]}
    out["ret_waiting_items"] = c.get("/api/assessment/retention/items", headers=h_other).status_code

    # ── C14 정신적 노력 ──
    def eff(**kw):
        return c.post("/api/lesson/effort", headers=h, json={"session_id": "sess-abc123", "lesson_kind": "word", "stage": 2, **kw})
    out["eff_left"] = eff(response="left").json()["response"]
    out["eff_answer"] = eff(rating=6, n_items=12, accuracy=0.75).json()["response"]
    out["eff_skip_after"] = eff(response="skipped").json()["response"]
    out["eff_row"] = sql("select rating, response, stage, lesson_kind, n_items from lesson_efforts")
    out["eff_bad_rating"] = c.post("/api/lesson/effort", headers=h, json={"session_id": "sess-xyz789", "rating": 12}).json()["response"]
    out["eff_bad_session"] = c.post("/api/lesson/effort", headers=h, json={"session_id": "a b", "rating": 3}).status_code
print("RESULT " + json.dumps(out, ensure_ascii=False, default=str))
'''


@lru_cache(maxsize=1)
def _run():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1",
                   T_DB=f"{d}/t.db")
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("LIPLAB_RETENTION_DAYS", None)
        p = subprocess.run([sys.executable, "-c", _SCENARIO], cwd=here, env=env,
                           capture_output=True, text=True, timeout=240)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    return json.loads(line[len("RESULT "):])


def test_fsrs_state_on_new_item_and_no_log_outside_due_reviews():
    r = _run()
    stab, diff, last, *_ = r["new_item"]
    assert abs(stab - 0.40255) < 1e-9 and 1 <= diff <= 10 and last
    assert r["logs_after_lesson"] == 0 and r["logs_after_early"] == 0
    assert r["logs_after_due_lesson_wrong"] == 1          # 앞의 예정 복습 한 건뿐


def test_due_review_logs_prediction_without_changing_interval():
    r = _run()
    assert r["interval_same_as_sm2"] is True
    source, elapsed, quality, grade, passed, guess, r_fsrs, p_fsrs, p_sm2, sm2_iv = r["log"]
    assert source == "review" and elapsed == 1 and quality == 3 and grade == 3 and passed == 1 and guess == 0.25
    assert abs(r_fsrs - r["expect_r"]) < 1e-9
    assert abs(p_fsrs - (0.25 + 0.75 * r_fsrs)) < 1e-9
    assert abs(p_sm2 - (0.25 + 0.75 * 0.9 ** (1 / sm2_iv))) < 1e-9


def test_legacy_item_logs_sm2_proxy_only_then_gets_state():
    r = _run()
    elapsed, r_fsrs, p_fsrs, p_sm2, passed, grade = r["legacy_log"]
    assert elapsed == 6 and r_fsrs is None and p_fsrs is None
    assert abs(p_sm2 - (0.25 + 0.75 * 0.9)) < 1e-9 and passed == 0 and grade == 1
    assert r["legacy_state"][0] == 1 and r["legacy_state"][1]


def test_mastery_probes_are_scheduled_capped_and_kept_apart():
    r = _run()
    f = r["probe_first"]
    assert f["quota"] == 3 and f["n"] == 3 and f["pending"] == 18
    assert f["stages"] == [1, 2, 3] and f["waves"] == [1, 7] and f["speeds"] == [1.0] and f["has_target"] is False
    assert r["probe_rows"] == [[1, 1, 6], [2, 7, 6], [3, 1, 6]]
    assert r["probe_answer"] == {"recorded": True}
    assert r["probe_again"]["already"] is True and r["probe_bad"] == 400 and r["probe_other_user"] == 404
    assert r["probe_row"][:2] == [1, 1] and r["probe_row"][2] == 1 and r["probe_row"][3] == 1.0
    assert r["probe_untouched"] is True                   # 숙달·시행 기록·복습 큐·문장 기록 그대로
    s = r["probe_second"]
    assert s["n"] == 3 and s["pending"] == 17 and s["rebuilt"] == 18 and s["skips_answered"] is True
    assert r["probe_used_full"] == 0                      # 다른 탐침과 상한을 함께 쓴다


def test_retention_test_is_scheduled_after_post_and_kept_apart():
    r = _run()
    assert r["ret_none"] == "none"
    assert r["ret_due"] == {"state": "due", "form": "B", "days": 28, "post_accuracy": 0.75}
    assert r["ret_items"] == 24
    assert r["ret_score"]["total"] == 24 and r["ret_score"]["correct"] == 20 and r["ret_score"]["form"] == "B"
    assert r["ret_score"]["days_after_post"] == 28
    assert r["ret_done"] == "done" and r["ret_rows"] == [["B", 24, 20, 28]]
    assert r["ret_flows_unchanged"] is True and r["ret_placement_rows"] == 2
    assert r["ret_score_again"] == 409
    assert r["ret_waiting"] == {"state": "waiting", "days_left": 18} and r["ret_waiting_items"] == 409


def test_effort_one_row_per_session_and_answer_wins():
    r = _run()
    assert r["eff_left"] == "left" and r["eff_answer"] == "answered" and r["eff_skip_after"] == "answered"
    assert r["eff_row"] == [[6, "answered", 2, "word", 12]]
    assert r["eff_bad_rating"] == "skipped" and r["eff_bad_session"] == 422
