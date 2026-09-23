"""
파일럿 자료(§4.7)의 대상 조회·가명·보관 만료 처리.

main.py(참여·가명 내보내기, 계정 열람·삭제)와 scripts/pilot_retention.py(보관 기간 뒤 파기)가 같은 정의를 쓰도록
한곳에 둔다. 보관 기간은 연구 계획(윤리 심의)에서 정한다 — 이 모듈은 기간을 모르고, 호출하는 쪽이 연구 종료일과
보관 일수를 준다.
"""
import hashlib
import hmac
import inspect
import os
from datetime import date, timedelta
from typing import Dict, List, Optional


def user_data_models() -> List:
    """user_id를 가진 모든 사용자 데이터 모델(개인정보 열람·삭제·파기 대상)."""
    import database as _db
    out = []
    for name in dir(_db):
        o = getattr(_db, name)
        if inspect.isclass(o) and hasattr(o, "__tablename__"):
            if "user_id" in [c.name for c in o.__table__.columns]:
                out.append(o)
    return out


def pilot_secret() -> str:
    """가명 비밀키. LIPLAB_PILOT_SECRET을 쓰고, 없으면 서버 로그인 비밀키(JWT_SECRET)를 쓴다.
    로그인 비밀키는 보안 사고 때 바꿀 수 있는데, 바뀌면 가명이 모두 달라져 철회·파기 때 자료를 찾지 못한다.
    그래서 파일럿 전에 LIPLAB_PILOT_SECRET을 따로 정하고 연구가 끝날 때까지 바꾸지 않는다."""
    s = os.getenv("LIPLAB_PILOT_SECRET", "").strip()
    if s:
        return s
    from auth import SECRET_KEY
    return SECRET_KEY


def pseudonym(user_id: int) -> str:
    """가명 — 가명 비밀키로 만든 HMAC 앞 12자리. 비밀키 없이는 사용자 번호로 되돌릴 수 없다."""
    return hmac.new(pilot_secret().encode(), f"pilot:{user_id}".encode(), hashlib.sha256).hexdigest()[:12]


def due_date(study_end: date, retain_days: int) -> date:
    """파기 기한 = 연구 종료일 + 보관 일수."""
    if retain_days < 0:
        raise ValueError("보관 일수는 0 이상이어야 합니다")
    return study_end + timedelta(days=retain_days)


async def participants(db, cohort: Optional[str] = None) -> List:
    """파일럿 참여자의 학습 프로필(참여 코드가 있는 것). cohort를 주면 그 집단만."""
    from sqlalchemy import select
    from database import LearningProfile
    q = select(LearningProfile).where(LearningProfile.pilot_code.is_not(None))
    if cohort:
        q = q.where(LearningProfile.cohort == cohort)
    return list((await db.execute(q.order_by(LearningProfile.user_id))).scalars().all())


async def count_rows(db, user_id: int) -> Dict[str, int]:
    """사용자별로 표마다 남은 행 수(0인 표는 뺀다)."""
    from sqlalchemy import func, select
    out = {}
    for M in user_data_models():
        n = (await db.execute(select(func.count()).select_from(M).where(M.user_id == user_id))).scalar() or 0
        if n:
            out[M.__tablename__] = int(n)
    return out


async def purge(db, user_id: int) -> Dict[str, int]:
    """계정 삭제(DELETE /api/account)와 같은 범위 — 사용자 데이터가 든 모든 표와 계정 자체를 지운다. 커밋은 호출자가."""
    from sqlalchemy import delete
    from database import User
    counts = {}
    for M in user_data_models():
        res = await db.execute(delete(M).where(M.user_id == user_id))
        counts[M.__tablename__] = res.rowcount if res.rowcount is not None else 0
    await db.execute(delete(User).where(User.id == user_id))
    return counts


def unlink(profile) -> None:
    """파일럿에서만 뺀다(참여 코드·집단 삭제). 계정과 학습 기록은 일반 서비스 약관대로 남는다."""
    profile.pilot_code, profile.cohort = None, None
