"""과제 탭의 오늘의 과제·특별 과제 정의와 달성 판정(순수 함수).

과제 목록·목표·보상 XP는 여기 한 곳에만 둔다. 프론트(과제 탭·오른쪽 패널)는 GET /api/tasks 응답을 그리기만 한다.
진행도는 기존 기록에서 계산한다(analytics.overview의 과제 탭 값과 같은 정의).
  - 독화 학습 1회: 오늘 독화 활동(문장·입모양·단어·문맥 시행) 수
  - 학습 2회 채우기: 오늘 시작한 학습 회차 수(30분 공백 = 새 회차, analytics.sessions)
  - 오늘의 복습 정리: 오늘까지 예정된 복습(독화·말하기)이 남지 않았고 오늘 학습 기록이 있으면 달성.
    학습 기록 조건이 없으면 예정 복습이 없는 사용자가 아무것도 하지 않고 보상을 받는다
  - 이번 주 5일 학습하기(특별 과제): 이번 주(월요일 시작) 학습한 날 수
  - 소리 듣기 15분(10/7): 오늘 소리 듣기 연습 분(listen_curriculum.practice_minutes, 듣기 요약 days의 minutes와 같은 추정)이
    15분 이상이면 달성. 듣기 트랙을 시작한 사용자(듣기 시행이나 단계 행이 있음)에게만 낸다(board의 listen)
날짜는 한국 시간(KST)으로 고정한다. 보상은 과제마다 기간(하루·한 주)에 한 번만 준다(task_claims 표).
"""
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Sequence, Set, Tuple

import analytics as _an

KST_OFFSET_MIN = -540   # analytics와 같은 부호(UTC - 현지)

TASKS: Tuple[Dict, ...] = (
    {"key": "review_clear", "label": "오늘의 복습 정리", "total": 1, "xp": 10, "period": "day"},
    {"key": "read_once", "label": "독화 학습 1회", "total": 1, "xp": 15, "period": "day"},
    {"key": "two_sessions", "label": "학습 2회 채우기", "total": 2, "xp": 20, "period": "day"},
    {"key": "week_5days", "label": "이번 주 5일 학습하기", "total": 5, "xp": 100, "period": "week"},
)
# 듣기 트랙을 시작한 사용자에게만 더하는 과제. 권장 용량(하루 15~20분, docs/auditory-training-design.md)의 아래 끝
LISTEN_TASK: Dict = {"key": "listen_15", "label": "소리 듣기 15분", "total": 15, "xp": 15, "period": "day"}


def tasks_for(listen: bool = False) -> Tuple[Dict, ...]:
    """보일 과제 목록. 하루 과제 뒤, 주 과제 앞에 소리 듣기 과제를 넣는다."""
    if not listen:
        return TASKS
    daily = tuple(t for t in TASKS if t["period"] == "day")
    return daily + (LISTEN_TASK,) + tuple(t for t in TASKS if t["period"] != "day")


def week_start(today: date) -> date:
    return today - timedelta(days=today.weekday())


def period_of(task: Dict, today: date) -> str:
    """보상 중복 방지 키. 하루 과제는 그날, 주 과제는 그 주 월요일(앞에 W)."""
    if task["period"] == "week":
        return "W" + week_start(today).isoformat()
    return today.isoformat()


def events_since(today: date) -> datetime:
    """계산에 필요한 기록의 시작 시각(UTC). 이번 주 월요일 0시(KST)보다 하루 앞에서 자른다."""
    start_local = datetime.combine(week_start(today) - timedelta(days=1), datetime.min.time())
    return start_local + timedelta(minutes=KST_OFFSET_MIN)


def stats(events: Sequence[_an.Event], today: date, due_left: int, listen_minutes: float = 0.0) -> Dict[str, int]:
    """기록 → 과제 진행 값. events는 events_since 뒤의 활동(analytics.Event). listen_minutes는 오늘 소리 듣기 연습 분."""
    tz = KST_OFFSET_MIN
    local_dates = [_an.to_local(e.ts, tz).date() for e in events]
    monday = week_start(today)
    today_sess = [s for s in _an.sessions(events) if _an.to_local(s[0].ts, tz).date() == today]
    return {
        "today_events": sum(1 for d in local_dates if d == today),
        "today_read": sum(1 for d, e in zip(local_dates, events) if d == today and e.track == "read"),
        "today_sessions": len(today_sess),
        "week_days": len({d for d in local_dates if monday <= d <= today}),
        "due_left": max(0, int(due_left)),
        "listen_minutes": max(0.0, float(listen_minutes or 0.0)),
    }


def progress(key: str, st: Dict[str, int]) -> int:
    if key == "review_clear":
        return 1 if st["due_left"] == 0 and st["today_events"] > 0 else 0
    if key == "read_once":
        return st["today_read"]
    if key == "two_sessions":
        return st["today_sessions"]
    if key == "week_5days":
        return st["week_days"]
    if key == "listen_15":
        return int(st.get("listen_minutes", 0.0))     # 분은 내림(14.9분은 14)
    raise KeyError(key)


def board(st: Dict[str, int], today: date, claimed: Iterable[Tuple[str, str]], listen: bool = False) -> List[Dict]:
    """과제 목록(표시용). claimed = 이미 받은 (task_key, period) 쌍. listen이면 소리 듣기 과제를 더한다."""
    got: Set[Tuple[str, str]] = set(claimed)
    out = []
    for t in tasks_for(listen):
        cur = min(t["total"], progress(t["key"], st))
        period = period_of(t, today)
        out.append({**t, "cur": cur, "done": cur >= t["total"], "claimed": (t["key"], period) in got,
                    "period_key": period})
    return out


def claimable(rows: Sequence[Dict]) -> List[Dict]:
    return [r for r in rows if r["done"] and not r["claimed"]]
