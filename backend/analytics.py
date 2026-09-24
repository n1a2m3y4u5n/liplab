"""학습 분석 집계(분석 탭·과제 탭 배지) — 순수 함수.

활동 기록 테이블(Progress·TrialAttempt·SpeakAttempt·PlacementResult)의 시각과 정오답을
Event 목록으로 받아 학습 시간·정확도 추이·연속 학습·배지를 계산한다. DB·네트워크 의존이 없어
결정론적으로 테스트할 수 있다(test_analytics.py).

학습 시간은 따로 기록하지 않으므로 추정한다. 활동 사이 간격이 30분을 넘으면 새 회차로 보고,
회차 길이 = 마지막 활동 − 첫 활동 + 1분(마지막 문항을 푸는 시간)으로 잡는다.
날짜는 사용자 시간대 기준이다. DB 시각은 UTC이고, tz_offset_min은 브라우저
Date.getTimezoneOffset() 값(UTC − 현지, 한국 = −540)이다.
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


def weekly(events: Sequence[Event], today: date, tz_offset_min: int, weeks: int = WEEKS) -> List[Dict]:
    """최근 weeks주(오늘로 끝나는 7일 창, 오래된 순)의 학습 분·정확도.
    회차 시간은 회차 시작일이 속한 주에 넣는다."""
    starts = [today - timedelta(days=7 * k + 6) for k in range(weeks)][::-1]
    buckets = [{"minutes": 0.0, "graded": []} for _ in starts]

    def idx(d: date) -> Optional[int]:
        for i, s in enumerate(starts):
            if s <= d <= s + timedelta(days=6):
                return i
        return None

    for sess in sessions(events):
        i = idx(to_local(sess[0].ts, tz_offset_min).date())
        if i is not None:
            buckets[i]["minutes"] += session_minutes(sess)
    for e in events:
        if e.graded is None:
            continue
        i = idx(to_local(e.ts, tz_offset_min).date())
        if i is not None:
            buckets[i]["graded"].append(e.graded)
    out = []
    for s, b in zip(starts, buckets):
        g = b["graded"]
        out.append({"start": s.isoformat(), "minutes": round(b["minutes"]),
                    "accuracy": round(sum(g) / len(g), 4) if g else None, "n_graded": len(g)})
    return out


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
           level: int) -> List[Dict]:
    """배지별 획득 여부. 판정 근거가 없는 배지는 earned=None(브라우저 판정 또는 미표시)."""
    graded = [e for e in events if e.graded is not None]
    lesson90 = any(
        len([e for e in s if e.graded is not None]) >= 10 and (accuracy(s) or 0) >= 0.9
        for s in sessions(events))
    dawn = any(0 <= to_local(e.ts, tz_offset_min).hour < 6 for e in events)
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


def overview(events: Sequence[Event], now_utc: datetime, tz_offset_min: int, **track_info) -> Dict:
    """분석 탭 요약. track_info: read_mastered·read_total·speak_mastered·speak_total·
    conversation_attempts·reviews_done·reviews_overdue·level."""
    today = to_local(now_utc, tz_offset_min).date()
    days = {to_local(e.ts, tz_offset_min).date() for e in events}
    cur, best = streaks(days, today)
    week = weekly(events, today, tz_offset_min)
    sess = sessions(events)
    read_ev = [e for e in events if e.track == "read"]
    speak_ev = [e for e in events if e.track == "speak"]
    this_w, prev_w = week[-1], week[-2]
    acc_delta = (None if this_w["accuracy"] is None or prev_w["accuracy"] is None
                 else round(this_w["accuracy"] - prev_w["accuracy"], 4))
    b = badges(events, tz_offset_min, best,
               read_mastered=track_info["read_mastered"], read_total=track_info["read_total"],
               speak_mastered=track_info["speak_mastered"], speak_total=track_info["speak_total"],
               conversation_attempts=track_info["conversation_attempts"],
               reviews_done=track_info["reviews_done"], reviews_overdue=track_info["reviews_overdue"],
               level=track_info["level"])
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
        "today_read": len([e for e in read_ev if to_local(e.ts, tz_offset_min).date() == today]),
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
        "tracks": {
            "read": {"accuracy": accuracy(read_ev), "done": len(track_info["read_mastered"]),
                     "total": track_info["read_total"]},
            "speak": {"accuracy": accuracy(speak_ev), "done": len(track_info["speak_mastered"]),
                      "total": track_info["speak_total"]},
        },
    }
