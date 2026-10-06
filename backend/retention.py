"""
지연 유지 검사 예약(종합 계획 C7).

사후 검사를 본 날부터 정해진 날수(기본 28일, 14~28일 사이로 설정)가 지나면 유지 검사를 권한다. 유지 검사는 **사후 검사와 같은 동형 폼·
판본**을 다시 본다(같은 문항, 같은 화자 조건 배정). 문항이 같아 기억 효과가 섞일 수 있다는 점은 결과와 함께 적는다.
사전·사후 흐름(PlacementResult, /api/assessment/score·history·progression)은 바꾸지 않는다. 예약은 저장하지 않고 검사 기록에서 계산하며,
유지 검사 결과는 따로(`retention_results` 표) 남겨 사전·사후 비교에 섞이지 않게 한다.

사후 검사 = 처음 본 동형 폼(A·B, 사전) 뒤에 처음으로 본 **다른** 동형 폼 가운데 사전과 같은 판본인 것(/api/assessment/progression이
사전과 같은 판본을 먼저 찾는 것과 같은 기준, 같은 판본이 없으면 다른 판본이라도 처음 본 다른 폼). 파일럿 역균형(B 먼저)도 같다.

**순수 함수**만 둔다. 날짜는 호출부가 KST로 바꿔 준다.
"""
from datetime import date, timedelta
from typing import Dict, Optional, Sequence

RETENTION_DAYS_DEFAULT = 28
RETENTION_DAYS_MIN = 14
RETENTION_DAYS_MAX = 28
FIXED_FORMS = ("A", "B")


def retention_days(raw=None) -> int:
    """설정값(환경 변수 LIPLAB_RETENTION_DAYS 문자열 등) → 14~28일. 비었거나 숫자가 아니면 28."""
    try:
        d = int(str(raw).strip()) if raw not in (None, "") else RETENTION_DAYS_DEFAULT
    except (TypeError, ValueError):
        d = RETENTION_DAYS_DEFAULT
    return max(RETENTION_DAYS_MIN, min(RETENTION_DAYS_MAX, d))


def post_test(rows: Sequence) -> Optional[Dict]:
    """rows(시간순, .form·.form_version을 가진 검사 기록)에서 {pre, post}. 사후 검사가 없으면 None."""
    ab = [r for r in rows if getattr(r, "form", None) in FIXED_FORMS]
    if not ab:
        return None
    pre = ab[0]
    later = [r for r in ab[1:] if r.form != pre.form]
    post = next((r for r in later if getattr(r, "form_version", None) == getattr(pre, "form_version", None)), None)
    if post is None and later:
        post = later[0]
    return {"pre": pre, "post": post} if post is not None else None


def status(post_on: Optional[date], done_on: Optional[date], today: date, days: int = RETENTION_DAYS_DEFAULT) -> Dict:
    """유지 검사 상태. post_on = 사후 검사 날(KST), done_on = 그 뒤에 본 유지 검사 날(없으면 None).
    state: 'none'(사후 검사 없음) | 'waiting'(아직 이름) | 'due'(볼 때) | 'done'(봤음)."""
    if post_on is None:
        return {"state": "none", "due_on": None, "days_left": None, "days": days}
    due_on = post_on + timedelta(days=days)
    out = {"due_on": due_on.isoformat(), "post_on": post_on.isoformat(), "days": days,
           "days_left": max(0, (due_on - today).days), "days_since_post": (today - post_on).days}
    if done_on is not None and done_on >= post_on:
        out.update(state="done", done_on=done_on.isoformat(), days_left=0)
    elif today >= due_on:
        out["state"] = "due"
    else:
        out["state"] = "waiting"
    return out


def summary(pairs: Sequence[Dict]) -> Dict:
    """유지 검사를 본 학습자들의 사후 → 유지 정답률 변화. pairs: {post_accuracy, retention_accuracy, days_after_post}.
    같은 문항을 다시 본 값이라 기억 효과가 섞일 수 있다(보고만 한다)."""
    ps = [p for p in pairs if p.get("post_accuracy") is not None and p.get("retention_accuracy") is not None]
    if not ps:
        return {"learners": 0, "mean_post": None, "mean_retention": None, "mean_change": None, "days": []}
    n = len(ps)
    m_post = sum(p["post_accuracy"] for p in ps) / n
    m_ret = sum(p["retention_accuracy"] for p in ps) / n
    return {"learners": n, "mean_post": round(m_post, 4), "mean_retention": round(m_ret, 4),
            "mean_change": round(m_ret - m_post, 4),
            "days": sorted(p.get("days_after_post") for p in ps if p.get("days_after_post") is not None)}
