"""과제 탭 보상(GET /api/tasks, POST /api/tasks/claim, daily_tasks.py)과 말하기 예정 복습(/api/review/due의 speak).

- 달성 전에는 받을 것이 없다(XP 0). 과제 조회(GET)는 XP를 주지 않는다.
- 달성한 과제는 한 번만 받는다. 표시한 XP(+10·+15·+20·+100)가 그대로 total_xp에 더해진다(연속 학습 배수 없음).
- 날짜(KST)가 바뀌면 하루 과제를 다시 받는다. 주 과제는 그 주에 한 번.
- 예정된 복습(독화·말하기)이 남아 있으면 '오늘의 복습 정리'는 달성이 아니다.
- task_claims의 고유 인덱스가 같은 과제·기간의 두 번째 기록을 막는다(동시 요청의 중복 지급 방지).

test_review_king_badge.py와 같은 방식: 임시 DB를 지정한 별도 프로세스에서 시나리오를 돌리고 결과(JSON)만 검사한다.
날짜는 main._kst_today를 고정해 흉내 내고, 활동 기록은 그 날짜의 시각으로 표에 바로 넣는다.
"""
import json
import os
import subprocess
import sys
import tempfile
from functools import lru_cache

_SCENARIO = r'''
import json, os, sqlite3
from datetime import date, datetime, timedelta
from fastapi.testclient import TestClient
import main

def sql(q, *a):
    db = sqlite3.connect(os.environ["T_DB"])
    rows = db.execute(q, a).fetchall()
    db.commit(); db.close()
    return rows

DAY = [date(2030, 1, 9)]            # 수요일
main._kst_today = lambda: DAY[0]

def trial(uid, d, hh, mm=0):
    # KST d hh:mm의 독화 시행 한 건(DB 시각은 UTC)
    ts = datetime(d.year, d.month, d.day, hh, mm) - timedelta(hours=9)
    sql("insert into trial_attempts (user_id, stage, item_type, target, chosen, correct, phase, confusions, created_at) "
        "values (?, 1, 'viseme', '1', '1', 1, 'practice', '[]', ?)", uid, ts.strftime("%Y-%m-%d %H:%M:%S.000000"))

def xp():
    return sql("select total_xp from users")[0][0]

def board(res):
    return {t["key"]: [t["cur"], t["done"], t["claimed"]] for t in res["daily"] + res["weekly"]}

out = {}
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "tk@example.com", "username": "과제", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    uid = sql("select id from users")[0][0]

    g = c.get("/api/tasks", headers=h).json()
    out["defs"] = [[t["key"], t["total"], t["xp"], t["period"]] for t in g["daily"] + g["weekly"]]
    out["empty_board"] = board(g)
    x0 = xp()
    r0 = c.post("/api/tasks/claim", headers=h).json()
    out["claim_empty"] = [r0["xp_gained"], xp() - x0]

    # 말하기에서 틀린 문항이 오늘 예정(kind speak). review/due는 독화(items)와 말하기(speak)를 나눠 준다
    sql("insert into review_items (user_id, kind, ref, due_date, interval_days, ease_factor, repetitions, lapses, "
        "created_at, updated_at) values (?, 'speak', '안녕하세요', ?, 1, 2.5, 0, 1, ?, ?)",
        uid, DAY[0].isoformat(), "2030-01-08 00:00:00.000000", "2030-01-08 00:00:00.000000")
    d = c.get("/api/review/due", headers=h).json()
    out["due"] = [d["count"], len(d["items"]), d["speak_count"], [s["ref"] for s in d["speak"]], d["total"]]

    # 독화 한 번: 독화 1회 달성, 복습은 말하기 예정이 남아 미달성
    trial(uid, DAY[0], 10)
    x1 = xp()
    g1 = c.get("/api/tasks", headers=h).json()
    out["get_no_xp"] = xp() - x1
    out["unclaimed_xp"] = g1["unclaimed_xp"]
    r1 = c.post("/api/tasks/claim", headers=h).json()
    out["claim1"] = [sorted(k["key"] for k in r1["claimed"]), r1["xp_gained"], xp() - x1, r1["total_xp"] == xp()]
    out["board1"] = board(r1)
    x2 = xp()
    r2 = c.post("/api/tasks/claim", headers=h).json()
    out["claim_again"] = [r2["xp_gained"], xp() - x2]

    # 한 시간 뒤 두 번째 회차, 말하기 복습을 마쳐 예정일이 내일로
    trial(uid, DAY[0], 11, 30)
    sql("update review_items set due_date = ?", (DAY[0] + timedelta(days=1)).isoformat())
    x3 = xp()
    r3 = c.post("/api/tasks/claim", headers=h).json()
    out["claim3"] = [sorted(k["key"] for k in r3["claimed"]), r3["xp_gained"], xp() - x3]
    out["claim3_again"] = c.post("/api/tasks/claim", headers=h).json()["xp_gained"]

    # 이틀 뒤(금요일): 월·화·목·금에도 학습해 이번 주 5일. 하루 과제는 새로 받고 주 과제도 받는다.
    # 말하기 예정(목요일)이 밀려 있어 복습 정리는 미달성
    for dd in (date(2030, 1, 7), date(2030, 1, 8), date(2030, 1, 10)):
        trial(uid, dd, 9)
    DAY[0] = date(2030, 1, 11)
    trial(uid, DAY[0], 9)
    x4 = xp()
    r4 = c.post("/api/tasks/claim", headers=h).json()
    out["claim_new_day"] = [sorted(k["key"] for k in r4["claimed"]), r4["xp_gained"], xp() - x4]
    out["week_board"] = board(r4)["week_5days"]

    # 토요일: 주 과제는 이미 받아 다시 주지 않는다
    DAY[0] = date(2030, 1, 12)
    trial(uid, DAY[0], 9)
    r5 = c.post("/api/tasks/claim", headers=h).json()
    out["claim_sat"] = sorted(k["key"] for k in r5["claimed"])

    # 같은 과제·기간을 두 번 기록할 수 없다
    try:
        sql("insert into task_claims (user_id, task_key, period, xp) values (?, 'read_once', '2030-01-12', 15)", uid)
        out["dup_blocked"] = False
    except sqlite3.IntegrityError:
        out["dup_blocked"] = True

    # 학습 초기화는 보상 기록도 지운다(개인정보 열람·삭제 대상)
    exp = c.get("/api/account/data", headers=h).json()
    out["export_has_claims"] = len(exp["data"].get("task_claims", []))
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


def test_task_definitions_come_from_server():
    r = _run()
    assert r["defs"] == [["review_clear", 1, 10, "day"], ["read_once", 1, 15, "day"],
                         ["two_sessions", 2, 20, "day"], ["week_5days", 5, 100, "week"]]


def test_nothing_to_claim_before_achieving():
    r = _run()
    assert all(v == [0, False, False] for v in r["empty_board"].values())
    assert r["claim_empty"] == [0, 0]


def test_review_due_separates_speaking_items():
    r = _run()
    assert r["due"] == [0, 0, 1, ["안녕하세요"], 1]


def test_claim_once_with_displayed_xp():
    r = _run()
    assert r["get_no_xp"] == 0                       # 조회는 XP를 주지 않는다
    assert r["unclaimed_xp"] == 15
    # 말하기 예정이 남아 복습 정리는 빠지고, 독화 1회만 표시 그대로 +15
    assert r["claim1"] == [["read_once"], 15, 15, True]
    assert r["board1"]["review_clear"] == [0, False, False]
    assert r["board1"]["read_once"] == [1, True, True]
    assert r["claim_again"] == [0, 0]
    assert r["claim3"] == [["review_clear", "two_sessions"], 30, 30]
    assert r["claim3_again"] == 0


def test_new_day_claims_again_and_week_once():
    r = _run()
    assert r["claim_new_day"] == [["read_once", "week_5days"], 115, 115]
    assert r["week_board"] == [5, True, True]
    assert r["claim_sat"] == ["read_once"]


def test_claim_rows_unique_and_exported():
    r = _run()
    assert r["dup_blocked"] is True
    assert r["export_has_claims"] == 6
