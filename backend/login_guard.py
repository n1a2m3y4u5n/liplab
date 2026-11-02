"""DB 원자 갱신으로 로그인 시도를 예약해 같은 DB의 여러 워커도 잠금을 공유한다."""
import hashlib
import hmac
from datetime import datetime, timedelta
from fastapi import HTTPException
from sqlalchemy import delete, update
from database import LoginAttempt
from auth import SECRET_KEY

LIMIT = 5
WINDOW_SECONDS = 900


def account_key(email):
    return hmac.new(SECRET_KEY.encode(), email.strip().lower().encode(), hashlib.sha256).hexdigest()


async def reserve_attempt(email, db):
    now = datetime.utcnow()
    key = account_key(email)
    # 만료 행을 정리해 알 수 없는 이메일의 해시가 영구히 쌓이지 않게 한다.
    await db.execute(delete(LoginAttempt).where(LoginAttempt.expires_at <= now))
    dialect = db.bind.dialect.name
    if dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    elif dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        raise RuntimeError("unsupported login lock database")
    await db.execute(insert(LoginAttempt).values(key=key, attempts=0,
        expires_at=now + timedelta(seconds=WINDOW_SECONDS)).on_conflict_do_nothing(index_elements=["key"]))
    result = await db.execute(update(LoginAttempt).where(LoginAttempt.key == key,
        LoginAttempt.attempts < LIMIT).values(attempts=LoginAttempt.attempts + 1))
    await db.commit()
    if result.rowcount != 1:
        raise HTTPException(429, "로그인 시도가 너무 많아요. 15분 뒤 다시 시도해 주세요.",
                            headers={"Retry-After": str(WINDOW_SECONDS)})


async def clear_attempts(email, db):
    await db.execute(delete(LoginAttempt).where(LoginAttempt.key == account_key(email)))
    await db.commit()
