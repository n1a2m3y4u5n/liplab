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


def test_week_accuracy_is_not_moved_by_item_type_mix():
    # 실력은 그대로(입모양 90%, 문맥 60%)인데 지난주는 입모양 위주, 이번 주는 문맥 위주 → 합쳐 평균하면 −18%p로 보였다
    now = datetime(2026, 9, 23, 3, 0)
    def block(y, m, d, kind, n, n_correct):
        return [an.Event(datetime(y, m, d, 1, i), "read", 1.0 if i < n_correct else 0.0, kind) for i in range(n)]
    ev = (block(2026, 9, 14, "viseme", 20, 18) + block(2026, 9, 14, "closure", 5, 3)
          + block(2026, 9, 22, "viseme", 10, 9) + block(2026, 9, 22, "closure", 40, 24))
    ov = an.overview(ev, now, KST, **_info())
    raw = ov["weekly"][-1]["accuracy_raw"] - ov["weekly"][-2]["accuracy_raw"]
    assert raw < -0.15, raw
    assert abs(ov["week_accuracy_delta"]) < 0.05, ov["week_accuracy_delta"]
    assert abs(ov["weekly"][-1]["accuracy"] - ov["weekly"][-2]["accuracy"]) < 0.05
    # 겹치는 유형이 없으면 지난주 대비를 내지 않는다(유형이 바뀐 것과 실력 변화를 가를 수 없다)
    ov2 = an.overview(block(2026, 9, 14, "viseme", 10, 9) + block(2026, 9, 22, "closure", 10, 6), now, KST, **_info())
    assert ov2["week_accuracy_delta"] is None


def test_read_track_counts_all_graded_read_questions():
    # 1단계 48문항 + 2단계 36문항만 푼 학습자(문장 연습 0): 분석 상세 '점수'가 /api/statistics(문장 연습만)로 '독화 0점 · 0회'를
    # 보이던 것. 독화 트랙은 선다형 시행까지 세고, 채점하지 않는 활동(검사 이벤트)은 문항 수에 넣지 않는다
    now = datetime(2026, 9, 23, 3, 0)
    ev = [an.Event(datetime(2026, 9, 22, 1, 0) + timedelta(seconds=20 * i), "read", 0.0 if i % 4 == 0 else 1.0,
                   "viseme" if i < 48 else "word") for i in range(84)]
    ev += [an.Event(datetime(2026, 9, 22, 2, 0), "test", None), an.Event(datetime(2026, 9, 22, 2, 1), "speak", None, "speak:")]
    tr = an.overview(ev, now, KST, **_info())["tracks"]
    assert tr["read"]["questions"] == 84 and abs(tr["read"]["accuracy"] - 0.75) < 1e-9
    assert tr["speak"]["questions"] == 0 and tr["speak"]["accuracy"] is None


def _weekly_linear(events, today, tz, weeks=an.WEEKS):
    """고치기 전 weekly의 주 찾기(7주를 차례로 비교)를 그대로 옮긴 기준 구현. 새 weekly와 결과를 비교한다."""
    starts = [today - timedelta(days=7 * k + 6) for k in range(weeks)][::-1]
    mins = [0.0] * weeks
    graded = [[] for _ in starts]

    def idx(d):
        for i, s in enumerate(starts):
            if s <= d <= s + timedelta(days=6):
                return i
        return None
    for s in an.sessions(events):
        i = idx(an.to_local(s[0].ts, tz).date())
        if i is not None:
            mins[i] += an.session_minutes(s)
    for e in events:
        i = idx(an.to_local(e.ts, tz).date())
        if e.graded is not None and i is not None:
            graded[i].append(e.graded)
    return [(s.isoformat(), round(m), len(g)) for s, m, g in zip(starts, mins, graded)]


def test_weekly_constant_time_index_matches_linear_search():
    # PERF-2: 주 번호를 (날짜 − 첫 주 시작일).days // 7로 바꿨다. 창 경계(첫날·마지막 날·하루 전·오늘 뒤)와
    # 시간대를 섞어도 예전 선형 탐색과 같은 칸에 들어가야 한다
    import random
    rnd = random.Random(7)
    now = datetime(2026, 9, 23, 3, 0)
    for tz in (KST, 0, 300, -840, 720):
        today = an.to_local(now, tz).date()
        ev = [an.Event(now - timedelta(minutes=rnd.randint(0, 60 * 24 * 60)), "read",
                       rnd.choice([None, 0.0, 1.0, 0.5]), rnd.choice(["viseme", "word"])) for _ in range(400)]
        for dd in (-1, 0, 6, 7, 48, 49, 50):   # 오늘 뒤·오늘·주 경계·첫날(48)·창 밖(49, 50)
            ev.append(an.Event(datetime.combine(today - timedelta(days=dd), datetime.min.time()).replace(hour=12)
                               + timedelta(minutes=tz), "read", 1.0, "word"))
        got = [(w["start"], w["minutes"], w["n_graded"]) for w in an.weekly(ev, today, tz)]
        assert got == _weekly_linear(ev, today, tz)
        # overview가 넘기는 회차·현지 날짜로 계산해도 같다
        loc = [an.to_local(e.ts, tz).date() for e in ev]
        assert an.weekly(ev, today, tz, sess=an.sessions(ev), local_dates=loc) == an.weekly(ev, today, tz)


def test_badges_same_with_precomputed_sessions_and_local_times():
    ev = [an.Event(datetime(2026, 9, 22, 18, 0) + timedelta(minutes=i), "read", 1.0, "word") for i in range(12)]
    kw = _info(reviews_done=1)
    plain = an.badges(ev, KST, 3, **kw)
    pre = an.badges(ev, KST, 3, sess=an.sessions(ev), local_times=[an.to_local(e.ts, KST) for e in ev], **kw)
    assert plain == pre
    got = {b["key"]: b["earned"] for b in pre}
    assert got["acc90"] and got["dawn"]   # 한국 03:00 회차 12문항 전부 정답
