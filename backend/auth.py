"""
JWT-based authentication system for LIPLAB
Handles user registration, login, token generation and validation
"""
import os
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import bcrypt as bcrypt_lib
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import User, get_db

# Security configuration
# JWT 서명키. 공개 기본값으로 서명되면 임의 user_id 토큰을 위조해 전 계정을 사칭할 수 있다.
# 따라서 미설정/기본값이면: 프로덕션은 기동 실패(fail-fast), 개발은 임시 무작위 키(재시작 시 토큰 무효)로 경고.
_DEFAULT_INSECURE = "liplab-super-secret-key-change-in-production-2024"
SECRET_KEY = os.getenv("JWT_SECRET")
if not SECRET_KEY or SECRET_KEY == _DEFAULT_INSECURE:
    # 배포 환경 감지: Fly.io는 FLY_APP_NAME을 자동 주입한다. ENVIRONMENT=production도 인정.
    # 배포에서 JWT_SECRET 누락 시 임시키로 조용히 기동하면 재시작마다 전 사용자 토큰이 무효화되므로 기동 실패시킨다.
    _deployed = bool(os.getenv("FLY_APP_NAME")) or os.getenv("ENVIRONMENT", "").lower() == "production"
    if _deployed:
        raise RuntimeError(
            "JWT_SECRET 환경변수를 설정하세요. 기본값·미설정은 배포 환경에서 금지됩니다 "
            "(예: `openssl rand -hex 32`로 생성해 `fly secrets set JWT_SECRET=...`로 등록)."
        )
    import secrets as _secrets
    import logging as _logging
    SECRET_KEY = _secrets.token_hex(32)
    _logging.getLogger("uvicorn.error").warning(
        "JWT_SECRET 미설정 → 개발용 임시 시크릿 생성(서버 재시작 시 발급 토큰 무효). 배포에선 반드시 설정."
    )
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

security = HTTPBearer()


# Pydantic models for request/response
class UserRegister(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    # 가입 동의(§4.9 ②) — 서버에서도 확인하고 ConsentRecord로 남긴다(화면 체크박스만으로는 우회 가능).
    agree_terms: bool = False       # 이용약관·개인정보 처리방침 동의
    age_confirmed: bool = False     # 만 14세 이상이거나 법정대리인 동의를 받음


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str
    user: dict


class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    current_level: int
    total_xp: int
    streak_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


# Password utilities
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return bcrypt_lib.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def get_password_hash(password: str) -> str:
    """Generate password hash"""
    return bcrypt_lib.hashpw(password.encode("utf-8"), bcrypt_lib.gensalt()).decode("utf-8")


# Token utilities
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt if isinstance(encoded_jwt, str) else encoded_jwt.decode("utf-8")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Dependency to get current authenticated user from JWT token
    Raises HTTPException if token is invalid or user not found
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        user_id = int(user_id)
        token_version = int(payload.get("tv", 0))   # tv가 없는 옛 토큰은 0으로 본다
    except (JWTError, ValueError, TypeError):
        raise credentials_exception

    # Fetch user from database
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise credentials_exception
    # 비밀번호를 바꾸면 token_version이 올라가 그 전에 발급된 토큰은 모두 거부된다(§4.9 인증·세션).
    if token_version != (user.token_version or 0):
        raise credentials_exception

    return user


# Authentication functions
async def authenticate_user(email: str, password: str, db: AsyncSession) -> Optional[User]:
    """Authenticate user by email and password"""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None

    return user


async def register_user(user_data: UserRegister, db: AsyncSession) -> User:
    """Register a new user"""
    # Check if email already exists
    result = await db.execute(select(User).where(User.email == user_data.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Check if username already exists
    result = await db.execute(select(User).where(User.username == user_data.username))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )

    # Create new user
    hashed_password = get_password_hash(user_data.password)
    new_user = User(
        email=user_data.email,
        username=user_data.username,
        hashed_password=hashed_password
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return new_user


def create_token_response(user: User) -> Token:
    """Create token response with user data"""
    # tv(토큰 버전)를 넣어 두면 비밀번호 변경 뒤 옛 토큰을 get_current_user가 거부한다.
    access_token = create_access_token(data={"sub": str(user.id), "tv": user.token_version or 0})

    return Token(
        access_token=access_token,
        token_type="bearer",
        user={
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "current_level": user.current_level,
            "total_xp": user.total_xp,
            "streak_count": user.streak_count or 0,
        }
    )
