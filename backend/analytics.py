"""학습 분석 집계(분석 탭·과제 탭 배지) — 순수 함수.

활동 기록 테이블(Progress·TrialAttempt·SpeakAttempt·PlacementResult)의 시각과 정오답을
Event 목록으로 받아 학습 시간·정확도 추이·연속 학습·배지를 계산한다. DB·네트워크 의존이 없어
결정론적으로 테스트할 수 있다(test_analytics.py).

학습 시간은 따로 기록하지 않으므로 추정한다. 활동 사이 간격이 30분을 넘으면 새 회차로 보고,
회차 길이 = 마지막 활동 − 첫 활동 + 1분(마지막 문항을 푸는 시간)으로 잡는다.
날짜는 사용자 시간대 기준이다. DB 시각은 UTC이고, tz_offset_min은 브라우저
Date.getTimezoneOffset() 값(UTC − 현지, 한국 = −540)이다.

주별 정확도는 문항 유형(입모양·단어·문맥·문장·말하기 모드)마다 정답률이 달라, 학습 경로를 따라 쉬운 유형에서 어려운
유형으로 옮겨 가면 실력이 그대로여도 내려갔다(학습 효과 리포트의 eval_metrics와 같은 문제). 이제 추이는 유형 평균을 빼고
전체 평균을 더한 값(유형 고정효과 보정, accuracy_raw는 보정 전)이고, 지난주 대비는 두 주에 모두 있는 유형 안에서 잰 차이를
두 주 문항 수의 조화평균으로 가중 평균한다(겹치는 유형이 없으면 None). 유형이 하나뿐이면 예전 값과 같다.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

SESSION_GAP = timedelta(minutes=30)
ITEM_TAIL = timedelta(minutes=1)
WEEKS = 7


@dataclass(frozen=True)
class Event:
    ts: datetime                 # UTC(naive, DB 저장 형식)
    track: str                   # 'read' | 'speak' | 'test'
    graded: Optional[float]      # 0~1 정오답·점수. 채점하지 않는 활동은 None
    kind: str = ""               # 문항 유형(viseme·word·word_typed·context·closure·sentence·speak:<모드>). 주별 정확도 보정에 쓴다


def to_local(ts: datetime, tz_offset_min: int) -> datetime:
    """UTC → 사용자 현지 시각."""
    return ts - timedelta(minutes=tz_offset_min)


def sessions(events: Sequence[Event]) -> List[List[Event]]:
    """시간순으로 정렬해 30분 넘는 공백마다 회차를 나눈다."""
    out: List[List[Event]] = []
    for e in sorted(events, key=lambda x: x.ts):
        if out and e.ts - out[-1][-1].ts <= SESSION_GAP:
            out[-1].append(e)
        else:
            out.append([e])
    return out


def session_minutes(sess: Sequence[Event]) -> float:
    return ((sess[-1].ts - sess[0].ts) + ITEM_TAIL).total_seconds() / 60.0


def accuracy(events: Iterable[Event]) -> Optional[float]:
    g = [e.graded for e in events if e.graded is not None]
    return (sum(g) / len(g)) if g else None


def streaks(days: Set[date], today: date) -> Tuple[int, int]:
    """(현재 연속, 최고 연속). 오늘이나 어제 학습했으면 거기서부터 거꾸로 센다."""
    best = run = 0
    prev = None
    for d in sorted(days):
        run = run + 1 if prev is not None and d - prev == timedelta(days=1) else 1
        best = max(best, run)
        prev = d
    start = today if today in days else (today - timedelta(days=1))
    cur = 0
    while start in days:
        cur += 1
        start -= timedelta(days=1)
    return cur, best


def _kind_adjusted(events: Sequence[Event]) -> Dict[int, float]:
    """채점된 이벤트마다 (값 − 그 유형 평균 + 전체 평균). id(e) → 보정값."""
    g = [e for e in events if e.graded is not None]
    if not g:
        return {}
    by: Dict[str, List[float]] = {}
    for e in g:
        by.setdefault(e.kind, []).append(e.graded)
    mean = {k: sum(v) / len(v) for k, v in by.items()}
    overall = sum(e.graded for e in g) / len(g)
    return {id(e): e.graded - mean[e.kind] + overall for e in g}


def within_kind_delta(recent: Sequence[Event], before: Sequence[Event]) -> Optional[float]:
    """두 기간 정확도 차이를 유형 안에서 재서, 두 기간 문항 수의 조화평균으로 가중 평균한다. 겹치는 유형이 없으면 None."""
    def by_kind(evs):
        out: Dict[str, List[float]] = {}
        for e in evs:
            if e.graded is not None:
                out.setdefault(e.kind, []).append(e.graded)
        return out
    a, b = by_kind(recent), by_kind(before)
    shared = set(a) & set(b)
    if not shared:
        return None
    w = {k: 2.0 / (1.0 / len(a[k]) + 1.0 / len(b[k])) for k in shared}
    return sum(w[k] * (sum(a[k]) / len(a[k]) - sum(b[k]) / len(b[k])) for k in shared) / sum(w.values())


def weekly(events: Sequence[Event], today: date, tz_offset_min: int, weeks: int = WEEKS, *,
           sess: Optional[List[List[Event]]] = None, local_dates: Optional[Sequence[date]] = None) -> List[Dict]:
    """최근 weeks주(오늘로 끝나는 7일 창, 오래된 순)의 학습 분·정확도.
    회차 시간은 회차 시작일이 속한 주에 넣는다. accuracy는 유형 고정효과 보정값, accuracy_raw는 보정 전.
    sess(sessions(events))·local_dates(이벤트마다 현지 날짜, events와 같은 순서)는 overview가 한 번 계산해 넘긴다.
    없으면 여기서 계산한다(결과는 같다)."""
    first = today - timedelta(days=7 * (weeks - 1) + 6)
    starts = [first + timedelta(days=7 * k) for k in range(weeks)]
    buckets = [{"minutes": 0.0, "graded": [], "adjusted": []} for _ in starts]
    adj = _kind_adjusted(events)
    if sess is None:
        sess = sessions(events)
    if local_dates is None:
        local_dates = [to_local(e.ts, tz_offset_min).date() for e in events]

    # 주 번호는 첫 주 시작일과의 일수 차 // 7. 예전에는 이벤트마다 7주를 차례로 비교해 이벤트 2만 개에서 0.05초였다
    def idx(d: date) -> Optional[int]:
        k = (d - first).days
        return k // 7 if 0 <= k < 7 * weeks else None

    for s in sess:
        i = idx(to_local(s[0].ts, tz_offset_min).date())
        if i is not None:
            buckets[i]["minutes"] += session_minutes(s)
    for e, d in zip(events, local_dates):
        if e.graded is None:
            continue
        i = idx(d)
        if i is not None:
            buckets[i]["graded"].append(e.graded)
            buckets[i]["adjusted"].append(adj[id(e)])
    out = []
    for s, b in zip(starts, buckets):
        g, a = b["graded"], b["adjusted"]
        out.append({"start": s.isoformat(), "minutes": round(b["minutes"]),
                    "accuracy": round(min(1.0, max(0.0, sum(a) / len(a))), 4) if a else None,
                    "accuracy_raw": round(sum(g) / len(g), 4) if g else None, "n_graded": len(g)})
    return out


# 말하기 문장 점수 주 평균(분석 탭 '참고, 기계 채점 기준' 줄). 화자 단위로 보면 지금 문장 점수(D-GOP)의 평균이 기계 전사 오류율과
# 같은 방향으로 움직였다(S20, docs/speak-intelligibility-index-2026-10.md 10.4절, 33명 ρ 0.762). 근거가 화자당 6~80문장 평균이라
# 문장이 SPEAK_TREND_MIN_N개보다 적은 주는 평균을 내지 않는다. 합격·숙달 판정에는 쓰지 않는다(보이기만 한다).
SPEAK_TREND_MIN_N = 5


def speak_sentence_weekly(points: Sequence[Tuple[datetime, float]], today: date, tz_offset_min: int,
                          weeks: int = WEEKS, min_n: int = SPEAK_TREND_MIN_N) -> List[Dict]:
    """말하기 문장 점수(0~100)의 주 평균. points는 (UTC 시각, 점수). 창은 weekly와 같다(오늘로 끝나는 7일, 오래된 순).
    반환: [{start, n, mean}], n이 min_n보다 적으면 mean은 None(n은 그대로 낸다)."""
    first = today - timedelta(days=7 * (weeks - 1) + 6)
    starts = [first + timedelta(days=7 * k) for k in range(weeks)]
    vals: List[List[float]] = [[] for _ in starts]
    for ts, sc in points:
        if ts is None or sc is None:
            continue
        k = (to_local(ts, tz_offset_min).date() - first).days
        if 0 <= k < 7 * weeks:
            vals[k // 7].append(max(0.0, min(100.0, float(sc))))
    return [{"start": s.isoformat(), "n": len(v), "mean": round(sum(v) / len(v), 1) if len(v) >= min_n else None}
            for s, v in zip(starts, vals)]


# 배지 정의 — 과제 탭(TasksPage)의 12칸 순서와 같다. 'sign'은 서버 기록이 없어 브라우저가 판정한다.
BADGES = [
    ("first_step", "첫 걸음"), ("streak7", "7일 연속"), ("viseme_master", "입모양 마스터"),
    ("acc90", "정확도 90%"), ("q100", "100문제 돌파"), ("review_king", "복습왕"),
    ("free_talk", "자유 발화"), ("sign", "수어 탐험"), ("streak30", "30일 연속"),
    ("dawn", "새벽 학습"), ("complete", "완주"), ("level5", "레벨 5"),
]


def badges(events: Sequence[Event], tz_offset_min: int, best_streak: int, *,
           read_mastered: Set[int], read_total: int, speak_mastered: Set[int], speak_total: int,
           conversation_attempts: int, reviews_done: int, reviews_overdue: int,
           level: int, sess: Optional[List[List[Event]]] = None,
           local_times: Optional[Sequence[datetime]] = None) -> List[Dict]:
    """배지별 획득 여부. 판정 근거가 없는 배지는 earned=None(브라우저 판정 또는 미표시).
    sess·local_times(이벤트마다 현지 시각)는 overview가 한 번 계산해 넘긴다. 없으면 여기서 계산한다."""
    graded = [e for e in events if e.graded is not None]
    if sess is None:
        sess = sessions(events)
    if local_times is None:
        local_times = [to_local(e.ts, tz_offset_min) for e in events]
    lesson90 = any(
        len([e for e in s if e.graded is not None]) >= 10 and (accuracy(s) or 0) >= 0.9
        for s in sess)
    dawn = any(0 <= t.hour < 6 for t in local_times)
    earned = {
        "first_step": len(events) > 0,
        "streak7": best_streak >= 7,
        "viseme_master": 1 in read_mastered,
        "acc90": lesson90,
        "q100": len(graded) >= 100,
        "review_king": reviews_done > 0 and reviews_overdue == 0,
        "free_talk": conversation_attempts > 0,
        "sign": None,
        "streak30": best_streak >= 30,
        "dawn": dawn,
        "complete": (len(read_mastered) >= read_total and len(speak_mastered) >= speak_total
                     and read_total > 0 and speak_total > 0),
        "level5": level >= 5,
    }
    return [{"key": k, "label": label, "earned": earned[k]} for k, label in BADGES]


def overview(events: Sequence[Event], now_utc: datetime, tz_offset_min: int, listen: Optional[Dict] = None,
             speak_sentences: Optional[Sequence[Tuple[datetime, float]]] = None, **track_info) -> Dict:
    """분석 탭 요약. track_info: read_mastered·read_total·speak_mastered·speak_total·
    conversation_attempts·reviews_done·reviews_overdue·level.
    speak_sentences는 말하기 문장 시도의 (UTC 시각, 점수)이고 'speak_trend'(주 평균, 참고용)로 낸다. None이면 'speak_trend'도 None.
    listen은 소리 듣기 요약 몇 칸(main._listen_brief, 듣기 트랙을 시작하지 않았으면 None)이고 그대로 'listen'에 싣는다.
    듣기 시행은 events에 넣지 않는다(학습 시간·정확도·연속 학습 같은 기존 칸의 뜻을 바꾸지 않게)."""
    today = to_local(now_utc, tz_offset_min).date()
    # 회차 나누기(정렬)와 현지 시각 변환은 한 번만 하고 weekly·badges가 다시 쓴다. 예전에는 sessions가 세 번,
    # to_local이 이벤트마다 네다섯 번 불렸다. 합성 이벤트 2만 개에서 130 → 53ms, 5천 개 30 → 13ms(결과 JSON 같음)
    sess = sessions(events)
    local_times = [to_local(e.ts, tz_offset_min) for e in events]
    local_dates = [t.date() for t in local_times]
    days = set(local_dates)
    cur, best = streaks(days, today)
    week = weekly(events, today, tz_offset_min, sess=sess, local_dates=local_dates)
    read_ev = [e for e in events if e.track == "read"]
    speak_ev = [e for e in events if e.track == "speak"]
    this_w, prev_w = week[-1], week[-2]
    # 지난주 대비: weekly의 마지막 두 창(오늘로 끝나는 7일, 그 앞 7일)과 같은 구간에서 유형 안 차이
    loc = list(zip(local_dates, events))
    this_ev = [e for d0, e in loc if today - timedelta(days=6) <= d0 <= today]
    prev_ev = [e for d0, e in loc if today - timedelta(days=13) <= d0 <= today - timedelta(days=7)]
    d = within_kind_delta(this_ev, prev_ev)
    acc_delta = None if d is None else round(d, 4)
    b = badges(events, tz_offset_min, best,
               read_mastered=track_info["read_mastered"], read_total=track_info["read_total"],
               speak_mastered=track_info["speak_mastered"], speak_total=track_info["speak_total"],
               conversation_attempts=track_info["conversation_attempts"],
               reviews_done=track_info["reviews_done"], reviews_overdue=track_info["reviews_overdue"],
               level=track_info["level"], sess=sess, local_times=local_times)
    acc_all = accuracy(events)
    # 과제 탭: 오늘 회차·오늘 독화 활동 수, 이번 주(월요일 시작) 학습한 날 수
    today_sess = [s for s in sess if to_local(s[0].ts, tz_offset_min).date() == today]
    monday = today - timedelta(days=today.weekday())
    # 분석 탭 활동 캘린더 부제의 '총 N회 학습'(207:26) — 회차를 시작한 현지 날짜별로 센다.
    # '총 학습 회차'(sessions)와 같은 회차 정의라 기간을 좁혀 더해도 두 수가 어긋나지 않는다.
    session_days: Dict[str, int] = {}
    for s in sess:
        k = to_local(s[0].ts, tz_offset_min).date().isoformat()
        session_days[k] = session_days.get(k, 0) + 1
    return {
        "has_data": bool(events),
        "today_sessions": len(today_sess),
        "today_read": sum(1 for d0, e in loc if d0 == today and e.track == "read"),
        "week_days": len({d for d in days if monday <= d <= today}),
        "total_minutes": round(sum(session_minutes(s) for s in sess)),
        "week_minutes": this_w["minutes"],
        "week_minutes_delta": this_w["minutes"] - prev_w["minutes"],
        "accuracy": round(acc_all, 4) if acc_all is not None else None,
        "week_accuracy": this_w["accuracy"],
        "week_accuracy_delta": acc_delta,
        "streak_current": cur,
        "streak_best": best,
        "weekly": week,
        "sessions": len(sess),
        "session_days": session_days,
        "questions": len([e for e in events if e.graded is not None]),
        "badges": b,
        # questions는 트랙별 채점된 활동 수. 분석 상세 '점수'가 독화 정확도 옆에 문항 수로 쓴다(예전에는 문장 연습 수만 셌다)
        "tracks": {
            "read": {"accuracy": accuracy(read_ev), "done": len(track_info["read_mastered"]),
                     "total": track_info["read_total"],
                     "questions": len([e for e in read_ev if e.graded is not None])},
            "speak": {"accuracy": accuracy(speak_ev), "done": len(track_info["speak_mastered"]),
                      "total": track_info["speak_total"],
                      "questions": len([e for e in speak_ev if e.graded is not None])},
        },
        "listen": listen,
        "speak_trend": None if speak_sentences is None else {
            "weeks": speak_sentence_weekly(speak_sentences, today, tz_offset_min), "min_n": SPEAK_TREND_MIN_N,
            "n": sum(1 for p in speak_sentences if p[1] is not None)},
    }
