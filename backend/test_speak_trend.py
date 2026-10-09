"""분석 탭 말하기 문장 점수 주 평균(analytics.speak_sentence_weekly, overview의 speak_trend).

- 창은 주별 추이(weekly)와 같다(오늘로 끝나는 7일 창 7개, 오래된 순, 사용자 시간대).
- 문장이 5개보다 적은 주는 평균을 내지 않는다(mean None, n은 그대로). 근거가 화자당 6~80문장 평균이라서다
  (docs/speak-intelligibility-index-2026-10.md 10.4절).
- 서버 경로: 말하기 문장 단계(mode 'sentence')만 세고, 낱말·확인(probe) 시도와 소리가 잡히지 않은 시도는 뺀다.
  점수는 입모양을 섞기 전 음향 점수(audio_score)를 쓴다.
"""
import json
import os
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta
from functools import lru_cache

import analytics as an

KST = -540


def test_weekly_mean_needs_five_sentences():
    today = date(2026, 10, 9)
    now = datetime(2026, 10, 9, 3, 0)            # UTC = 한국 12:00
    pts = [(now - timedelta(hours=i), 60 + i) for i in range(6)]            # 이번 주 6문장: 60..65
    pts += [(now - timedelta(days=8, hours=i), 90) for i in range(4)]       # 지난주 4문장
    w = an.speak_sentence_weekly(pts, today, KST)
    assert len(w) == an.WEEKS
    assert w[-1]["n"] == 6 and w[-1]["mean"] == 62.5
    assert w[-2]["n"] == 4 and w[-2]["mean"] is None, "5문장 미만인 주는 평균을 내지 않는다"
    assert all(x["n"] == 0 and x["mean"] is None for x in w[:-2])
    assert w[-1]["start"] == (today - timedelta(days=6)).isoformat()


def test_weekly_mean_window_follows_local_date_and_clamps():
    today = date(2026, 10, 9)
    # UTC 10/2 15:30 = 한국 10/3 00:30 → 이번 주 창(10/3~10/9)의 첫날
    edge = datetime(2026, 10, 2, 15, 30)
    pts = [(edge, 120.0)] + [(datetime(2026, 10, 8, 1, 0), 50.0)] * 4 + [(None, 70.0), (datetime(2026, 10, 8), None)]
    w = an.speak_sentence_weekly(pts, today, KST)
    assert w[-1]["n"] == 5, "시각·점수가 없는 점은 빼고, 현지 날짜로 창을 고른다"
    assert w[-1]["mean"] == 60.0, "점수는 0~100으로 자른다(120 → 100)"
    # 창 밖(7주보다 오래됨)은 세지 않는다
    old = an.speak_sentence_weekly([(datetime(2026, 8, 1), 80.0)] * 9, today, KST)
    assert sum(x["n"] for x in old) == 0


def test_overview_carries_speak_trend_only_when_given():
    now = datetime(2026, 10, 9, 3, 0)
    info = dict(read_mastered=set(), read_total=5, speak_mastered=set(), speak_total=6,
                conversation_attempts=0, reviews_done=0, reviews_overdue=0, level=1)
    assert an.overview([], now, KST, **info)["speak_trend"] is None
    ov = an.overview([], now, KST, speak_sentences=[(now, 70.0)] * 5, **info)
    t = ov["speak_trend"]
    assert t["min_n"] == 5 and t["n"] == 5 and t["weeks"][-1]["mean"] == 70.0
    assert ov["weekly"][-1]["accuracy"] is None, "문장 점수 주 평균은 기존 정확도 추이에 섞지 않는다"


_SCENARIO = r'''
import json, os, sqlite3, datetime as dt
from fastapi.testclient import TestClient
import main

def sql(q, *a):
    db = sqlite3.connect(os.environ["T_DB"])
    rows = db.execute(q, a).fetchall()
    db.commit(); db.close()
    return rows

out = {}
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "st@example.com", "username": "추세", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    uid = sql("select id from users")[0][0]
    out["empty"] = c.get("/api/analysis/overview", headers=h).json()["speak_trend"]
    now = dt.datetime.utcnow()
    def add(mode, score, audio, loud, ago_h, tr=None):
        t = (now - dt.timedelta(hours=ago_h)).strftime("%Y-%m-%d %H:%M:%S.%f")
        sql("insert into speak_attempts (user_id, stage, mode, target, transcript, score, audio_score, loudness, created_at) "
            "values (?, 5, ?, '오늘 날씨가 좋아요', ?, ?, ?, ?, ?)", uid, mode, tr, score, audio, loud, t)
    for i, s in enumerate([60, 70, 80, 90]):
        add("sentence", s, s, 40, i + 1)
    add("sentence", 95, 50, 40, 5)          # 입모양 융합으로 score가 바뀐 행: 음향 점수 50을 쓴다
    add("sentence", 0, 0, 0, 6)             # 소리가 잡히지 않은 시도: 뺀다
    add("word", 10, 10, 40, 2)              # 낱말 단계: 뺀다
    add("probe", 10, 10, 40, 3)             # 확인 시도: 뺀다
    for i in range(3):
        add("sentence", 40, 40, 40, 24 * 8 + i)   # 지난주 3문장: 평균 없음
    out["after"] = c.get("/api/analysis/overview", headers=h).json()["speak_trend"]
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


def test_overview_endpoint_speak_trend():
    r = _run()
    assert r["empty"]["n"] == 0 and all(w["mean"] is None for w in r["empty"]["weeks"])
    a = r["after"]
    assert a["min_n"] == 5
    assert a["weeks"][-1]["n"] == 5, "문장 단계의 소리 있는 시도만 센다(낱말·확인·무음 제외)"
    assert a["weeks"][-1]["mean"] == 70.0, "융합 전 음향 점수 평균 (60+70+80+90+50)/5"
    assert a["weeks"][-2]["n"] == 3 and a["weeks"][-2]["mean"] is None
    assert a["n"] == 8
