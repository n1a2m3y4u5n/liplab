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


async def close_db():
    """Close database connections"""
    await engine.dispose()
