"""분석 집계(analytics.py) 테스트 — 회차 분할·주별 창·연속 학습·시간대·배지."""
from datetime import date, datetime, timedelta

import analytics as an

KST = -540   # Date.getTimezoneOffset() 한국


def _ev(y, m, d, hh, mm, track="read", g=1.0):
    return an.Event(datetime(y, m, d, hh, mm), track, g)


def _info(**kw):
    base = dict(read_mastered=set(), read_total=5, speak_mastered=set(), speak_total=6,
                conversation_attempts=0, reviews_done=0, reviews_overdue=0, level=1)
    base.update(kw)
    return base


def test_sessions_split_on_30min_gap():
    ev = [_ev(2026, 9, 1, 1, 0), _ev(2026, 9, 1, 1, 20), _ev(2026, 9, 1, 1, 51)]
    s = an.sessions(ev)
    assert [len(x) for x in s] == [2, 1], "20분 간격은 같은 회차, 31분은 새 회차"
    assert an.session_minutes(s[0]) == 21.0, "마지막 − 첫 활동 + 1분"


def test_streaks_today_or_yesterday():
    today = date(2026, 9, 23)
    days = {today - timedelta(days=i) for i in (1, 2, 3)} | {date(2026, 9, 1), date(2026, 9, 2)}
    cur, best = an.streaks(days, today)
    assert cur == 3, "어제까지 이어졌으면 현재 연속으로 센다"
    assert best == 3
    assert an.streaks({date(2026, 9, 20)}, today) == (0, 1), "그제 이전에 끊겼으면 0"


def test_local_date_uses_timezone():
    # UTC 9/22 16:30 = 한국 9/23 01:30 — 한국 날짜로는 9/23, 새벽 학습
    e = an.Event(datetime(2026, 9, 22, 16, 30), "read", 1.0)
    assert an.to_local(e.ts, KST).date() == date(2026, 9, 23)
    b = {x["key"]: x["earned"] for x in an.badges([e], KST, 1, **_info())}
    assert b["dawn"] is True and b["first_step"] is True


def test_weekly_windows_and_overview():
    now = datetime(2026, 9, 23, 3, 0)            # 한국 9/23 12:00
    ev = [_ev(2026, 9, 22, 1, 0, g=1.0), _ev(2026, 9, 22, 1, 10, g=0.0),   # 이번 주 11분, 50%
          _ev(2026, 9, 14, 1, 0, g=1.0)]                                    # 지난 주 1분, 100%
    ov = an.overview(ev, now, KST, **_info())
    assert len(ov["weekly"]) == 7 and ov["weekly"][-1]["minutes"] == 11
    assert ov["weekly"][-2]["minutes"] == 1
    assert ov["week_minutes_delta"] == 10
    assert ov["week_accuracy_delta"] == -0.5
    assert ov["questions"] == 3 and ov["sessions"] == 2
    assert abs(ov["accuracy"] - 2 / 3) < 1e-3
    # 2026-09-23은 수요일 — 이번 주(9/21 월~)에 학습한 날은 9/22 하루, 오늘(9/23)은 0회
    assert ov["week_days"] == 1 and ov["today_sessions"] == 0 and ov["today_read"] == 0
    # 날짜별 회차 — 합이 총 회차와 같고, 날짜는 현지 날짜(UTC 9/22 01:00 = 한국 9/22 10:00)
    assert ov["session_days"] == {"2026-09-22": 1, "2026-09-14": 1}
    assert sum(ov["session_days"].values()) == ov["sessions"]


def test_session_days_keyed_by_local_start_date():
    # UTC 9/22 14:50 = 한국 9/22 23:50에 시작해 자정을 넘긴 회차는 시작한 날(9/22) 한 번만 센다
    ev = [_ev(2026, 9, 22, 14, 50), _ev(2026, 9, 22, 15, 10), _ev(2026, 9, 22, 16, 0)]
    ov = an.overview(ev, datetime(2026, 9, 23, 3, 0), KST, **_info())
    assert ov["sessions"] == 2 and ov["session_days"] == {"2026-09-22": 1, "2026-09-23": 1}


def test_empty_history_has_no_fake_values():
    ov = an.overview([], datetime(2026, 9, 23), KST, **_info())
    assert ov["has_data"] is False and ov["total_minutes"] == 0 and ov["accuracy"] is None
    assert ov["streak_current"] == 0 and ov["week_accuracy_delta"] is None
    assert not any(b["earned"] for b in ov["badges"]), "기록이 없으면 배지도 없다"


def test_badges_rules():
    ev = [_ev(2026, 9, 1, 3, i) for i in range(10)]          # 한 회차 10문항 전부 정답
    b = {x["key"]: x["earned"] for x in an.badges(
        ev, KST, 7, **_info(read_mastered={0, 1, 2, 3, 4}, speak_mastered=set(range(6)),
                            conversation_attempts=1, reviews_done=2, reviews_overdue=0, level=5))}
    assert b["acc90"] and b["streak7"] and b["viseme_master"] and b["free_talk"]
    assert b["review_king"] and b["complete"] and b["level5"]
    assert b["q100"] is False and b["streak30"] is False and b["sign"] is None
