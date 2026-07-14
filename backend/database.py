"""
Database configuration and models for LIPLAB
Supports both SQLite (development) and PostgreSQL (production)
"""
import os
from datetime import datetime
from typing import Optional
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, JSON, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base as async_declarative_base

# Database URL from environment or default to SQLite
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./liplab.db")

# Convert postgres:// to postgresql:// for SQLAlchemy compatibility
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("sqlite"):
    # Ensure async SQLite
    if "aiosqlite" not in DATABASE_URL:
        DATABASE_URL = DATABASE_URL.replace("sqlite://", "sqlite+aiosqlite://")

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,
)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = async_declarative_base()


class User(Base):
    """User account model with authentication and progress tracking"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    # Gamification fields
    current_level = Column(Integer, default=1)
    total_xp = Column(Integer, default=0)
    streak_count = Column(Integer, default=0)
    last_practice_date = Column(String(10), nullable=True)  # 'YYYY-MM-DD'

    # Relationships
    progress_records = relationship("Progress", back_populates="user", cascade="all, delete-orphan")
    weak_visemes = relationship("WeakViseme", back_populates="user", cascade="all, delete-orphan")
    bookmarks = relationship("Bookmark", back_populates="user", cascade="all, delete-orphan")


class Progress(Base):
    """Individual practice session record"""
    __tablename__ = "progress"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    scenario_id = Column(String(100), nullable=False)
    sentence = Column(String(500), nullable=False)
    user_answer = Column(String(500), nullable=False)
    score = Column(Float, nullable=False)  # 0-100
    time_spent_seconds = Column(Integer, default=0)
    difficulty_level = Column(Integer, nullable=False)
    situation = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Detailed analytics
    viseme_errors = Column(JSON, default=list)  # List of viseme IDs that were incorrect
    phoneme_accuracy = Column(JSON, default=dict)  # {initial: 0.9, medial: 0.85, final: 0.95}

    user = relationship("User", back_populates="progress_records")


class WeakViseme(Base):
    """Tracks user's weak visemes for adaptive learning"""
    __tablename__ = "weak_visemes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    viseme_id = Column(Integer, nullable=False)  # 1-15
    error_count = Column(Integer, default=0)
    total_attempts = Column(Integer, default=0)
    last_error_at = Column(DateTime, default=datetime.utcnow)

    # Phonological feature for grouping
    phonological_feature = Column(String(50))  # e.g., "bilabial", "dental", "velar"

    user = relationship("User", back_populates="weak_visemes")


class Bookmark(Base):
    """User bookmarked sentences for review"""
    __tablename__ = "bookmarks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    sentence = Column(String(500), nullable=False)
    situation = Column(String(100), default="")
    level = Column(Integer, default=1)
    # 어느 기둥의 북마크인지 — 독화(read)·말하기(speak)·촉각(tactile). 세 기둥 복습을 동일 구조로.
    domain = Column(String(12), default="read", index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="bookmarks")


class ScenarioCache(Base):
    """Cache for LLM-generated scenarios to reduce API calls"""
    __tablename__ = "scenario_cache"

    id = Column(Integer, primary_key=True, index=True)
    situation = Column(String(100), nullable=False)
    difficulty_level = Column(Integer, nullable=False)
    target_visemes = Column(JSON, default=list)  # List of viseme IDs to focus on
    sentences = Column(JSON, nullable=False)  # List of generated sentences
    created_at = Column(DateTime, default=datetime.utcnow)
    use_count = Column(Integer, default=0)

    # Composite index for fast lookup
    __table_args__ = (
        # Index is created automatically by SQLAlchemy for performance
    )


class LearningProfile(Base):
    """단계형 커리큘럼의 사용자별 상태(트랙·현재 단계).
    기존 테이블 무변경 원칙에 따라 User에 컬럼을 더하지 않고 별도 테이블로 둔다
    (신규 테이블 → create_all이 자동 생성, 마이그레이션 불필요)."""
    __tablename__ = "learning_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    track = Column(String(20), nullable=True)      # 'perception'(중도·난청) | 'language'(선천성) | None(미배치)
    current_stage = Column(Integer, default=0)     # 0 입문 ~ 4 대화
    placed = Column(Boolean, default=False)        # 배치(트랙 선택) 완료 여부
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class StageProgress(Base):
    """단계별 진행·숙달 상태. 인지퀴즈 등 활동 결과가 rolling으로 반영된다."""
    __tablename__ = "stage_progress"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    stage = Column(Integer, nullable=False)        # 0..4
    status = Column(String(20), default="locked")  # locked | unlocked | in_progress | mastered
    mastery_score = Column(Float, default=0.0)     # 0-100 (correct/attempts*100)
    attempts = Column(Integer, default=0)
    correct = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SpeakStageProgress(Base):
    """발화(말하기) 커리큘럼 단계별 진행·숙달. 읽기 StageProgress와 분리(별도 테이블).
    stage: 0 발성 ~ 5 문장·억양."""
    __tablename__ = "speak_stage_progress"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    stage = Column(Integer, nullable=False)        # 0..5
    status = Column(String(20), default="locked")  # locked | unlocked | in_progress | mastered
    mastery_score = Column(Float, default=0.0)     # 0-100 (correct/attempts*100)
    attempts = Column(Integer, default=0)
    correct = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TactileStageProgress(Base):
    """촉각(타도마) 커리큘럼 단계별 진행·숙달. 독화·발화 진행도와 동급으로 별도 테이블.
    stage: 0 감각 ~ 4 문장. 퀴즈 정답 여부가 rolling으로 반영된다."""
    __tablename__ = "tactile_stage_progress"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    stage = Column(Integer, nullable=False)        # 0..4
    status = Column(String(20), default="locked")  # locked | unlocked | in_progress | mastered
    mastery_score = Column(Float, default=0.0)     # 0-100 (correct/attempts*100)
    attempts = Column(Integer, default=0)
    correct = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TactileAttempt(Base):
    """촉각(타도마) 개별 문제 시도 기록 — 복습(틀린 항목 다시)·분석용.
    말하기 SpeakAttempt의 촉각판. target=문제 정답 텍스트."""
    __tablename__ = "tactile_attempts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    stage = Column(Integer, nullable=True)          # 0..4
    target = Column(String(200), nullable=False)
    correct = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class SpeakAttempt(Base):
    """발화 개별 시도 기록 — 말하기 '분석'용(자주 틀리는 소리·억양/크기 추세).
    독화가 Progress에 시도마다 쌓듯, 말하기도 여기에 쌓아 분석을 분리한다."""
    __tablename__ = "speak_attempts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    stage = Column(Integer, nullable=True)          # 0..5 (자유 연습이면 None)
    mode = Column(String(20), nullable=True)        # voicing|prosody|phoneme|word|sentence
    target = Column(String(200), nullable=False)
    transcript = Column(String(200), nullable=True)
    score = Column(Float, default=0.0)
    passed = Column(Boolean, nullable=True)
    loudness = Column(Float, default=0.0)
    pitch_range = Column(Float, default=0.0)
    duration = Column(Float, default=0.0)
    pitch_start = Column(Float, default=0.0)
    pitch_end = Column(Float, default=0.0)
    confusions = Column(JSON, default=list)         # [{correct, confused_as}]
    created_at = Column(DateTime, default=datetime.utcnow)


class ReviewItem(Base):
    """간격 반복(SRS) 복습 큐 — 틀린 항목이 due_date에 다시 등장한다.
    kind: 'viseme'(입모양 그룹, ref=id 문자열) | 'word'(단어, ref=단어)."""
    __tablename__ = "review_items"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String(20), nullable=False)       # 'viseme' | 'word'
    ref = Column(String(100), nullable=False)       # viseme_id(str) 또는 단어
    due_date = Column(String(10), nullable=False)   # 'YYYY-MM-DD'
    interval_days = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Dependency for getting DB session
async def get_db():
    """Dependency for FastAPI routes to get database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Initialize database tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 경량 마이그레이션 — create_all은 기존 테이블에 컬럼을 추가하지 않으므로
        # 나중에 생긴 bookmarks.domain 컬럼을 있으면 무시, 없으면 추가한다(SQLite).
        try:
            await conn.exec_driver_sql(
                "ALTER TABLE bookmarks ADD COLUMN domain VARCHAR(12) DEFAULT 'read'")
        except Exception:
            pass  # 이미 존재


async def close_db():
    """Close database connections"""
    await engine.dispose()
