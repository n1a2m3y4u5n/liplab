"""활동 캘린더 정답률·현지 날짜, 복습 목록 created_at API 테스트.

test_account_security.py와 같은 방식: 임시 DB를 지정한 별도 프로세스에서 시나리오를 돌리고 결과(JSON)만 검사한다.
"""
import json
import os
import subprocess
import sys
import tempfile

_SCENARIO = r'''
import json, datetime as dt
from fastapi.testclient import TestClient
import main
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "cal@example.com", "username": "caluser", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    item = main._training_closures()[0]
    c.post("/api/curriculum/closure-answer", json={"item_id": item["id"], "chosen": "틀린보기"}, headers=h)
    c.post("/api/curriculum/closure-answer", json={"item_id": item["id"], "chosen": item["answer"]}, headers=h)
    c.post("/api/bookmarks", json={"sentence": "안녕하세요", "situation": "인사", "level": 1}, headers=h)
    kst = c.get("/api/calendar/activities", params={"tz_offset_min": -540}, headers=h).json()
    utc = c.get("/api/calendar/activities", params={"tz_offset_min": 0}, headers=h).json()
    bm = c.get("/api/bookmarks", headers=h).json()
    # 오답으로 생긴 복습 예정 항목(단어)을 지운다 — 두 번째 삭제는 0건
    del1 = c.request("DELETE", "/api/review/item", params={"kind": "word", "ref": item["answer"]}, headers=h).json()
    del2 = c.request("DELETE", "/api/review/item", params={"kind": "word", "ref": item["answer"]}, headers=h).json()
    today_kst = (dt.datetime.utcnow() + dt.timedelta(hours=9)).date().isoformat()
    today_utc = dt.datetime.utcnow().date().isoformat()
    print("RESULT " + json.dumps({"kst": kst, "utc": utc, "bm": bm, "today_kst": today_kst, "today_utc": today_utc,
                                  "del1": del1, "del2": del2},
                                 ensure_ascii=False))
'''


def _run():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1")
        p = subprocess.run([sys.executable, "-c", _SCENARIO], cwd=here, env=env,
                           capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    return json.loads(line[len("RESULT "):])


def test_calendar_rows_have_accuracy_and_local_dates():
    r = _run()
    rows = r["kst"].get(r["today_kst"])
    assert rows, "현지(한국) 날짜 키로 행이 있어야 한다"
    closure = next(x for x in rows if x["kind"] == "closure")
    assert closure["n"] == 2 and closure["accuracy"] == 0.5, "채점된 시도의 평균 정답률"
    assert r["today_utc"] in r["utc"], "tz_offset_min=0이면 UTC 날짜"


def test_bookmarks_have_created_at():
    r = _run()
    assert r["bm"] and r["bm"][0]["created_at"].endswith("Z")


def test_review_item_delete():
    r = _run()
    assert r["del1"]["deleted"] == 1 and r["del2"]["deleted"] == 0
