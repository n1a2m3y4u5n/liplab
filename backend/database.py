"""
Database configuration and models for LIPLAB
Supports both SQLite (development) and PostgreSQL (production)
"""
import os
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, ForeignKey, Boolean
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
    # 토큰 버전(§4.9 인증·세션) — 비밀번호를 바꾸면 1 올려, 그 전에 발급된 토큰(tv 불일치)을 모두 무효화한다.
    token_version = Column(Integer, default=0)

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
    # 어느 기둥의 북마크인지 — 독화(read)·말하기(speak). 두 기둥 복습을 동일 구조로 다룬다.
    # 'tactile'은 2026-09-14 기준 쓰이지 않지만, 과거 행이 남아 있을 수 있어 값은 허용한다.
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
    # ⚠️ 2026-09-14 — 촉각(타도마) 파트는 b730c0d에서 제거됐고(세 기둥 → 두 기둥),
    # 이 테이블을 읽고 쓰는 코드는 남아 있지 않다. 기존 행을 잃지 않기 위해 **일부러 남긴**
    # 스키마다. 지우려면 별도 마이그레이션이 필요하다(STATUS.md의 결정 항목 참고).
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
    # ⚠️ 2026-09-14 — 촉각(타도마) 파트는 b730c0d에서 제거됐고(세 기둥 → 두 기둥),
    # 이 테이블을 읽고 쓰는 코드는 남아 있지 않다. 기존 행을 잃지 않기 위해 **일부러 남긴**
    # 스키마다. 지우려면 별도 마이그레이션이 필요하다(STATUS.md의 결정 항목 참고).
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


class PlacementResult(Base):
    """디지털 독화 표준검사 결과(축 I) — 배치검사·향상도검사의 회차 기록.
    동형 폼(A=사전, B=사후)으로 사전·사후를 비교해 통제된 향상도를 산출한다.
    form: 'placement'(수준 진단) | 'A'(사전) | 'B'(사후)."""
    __tablename__ = "placement_results"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    form = Column(String(16), default="placement")   # placement | A | B
    total = Column(Integer, default=0)
    correct = Column(Integer, default=0)
    accuracy = Column(Float, default=0.0)
    ability = Column(Float, default=0.0)             # 통과 최고 난이도(0~1)
    level = Column(Integer, default=1)               # 추정 수준 1~5
    error_visemes = Column(JSON, default=list)       # [viseme_id...]
    error_phonemes = Column(JSON, default=list)      # [{phoneme, count}...] 음소 단위
    # 동형 폼 판본(assessment.FORMS_VERSION)과 문항 단위 기록 — 사전·사후가 같은 판본인지 확인하고
    # 신뢰도(KR-20)·문항 분석을 하려면 필요하다(docs/assessment-design.md).
    form_version = Column(String(16), nullable=True)
    item_log = Column(JSON, default=list)            # [{id, word, chosen, correct, difficulty}]
    created_at = Column(DateTime, default=datetime.utcnow)


class ArticulationSession(Base):
    """웹캠 조음 교정 세션 요약(축 E-9) — 관찰 차원(개구·원순·폐쇄)의 목표 대비 평균 |차이|를
    세션 처음과 끝에서 재어 남긴다. 교정 전후 오차 비교의 원천 데이터.
    영상·계수 원본은 저장하지 않는다(요약 수치만)."""
    __tablename__ = "articulation_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    viseme_id = Column(Integer, nullable=False)
    score = Column(Float, nullable=True)        # 입모양 채점 최고점(0~100)
    gap_start = Column(Float, nullable=True)    # 처음 표본들의 평균 |목표-관찰| (0~1)
    gap_end = Column(Float, nullable=True)      # 마지막 표본들의 평균 |목표-관찰|
    n_samples = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class TrialAttempt(Base):
    """독화 개별 시행 기록 — 선다형 시행(1단계 입모양 인지·2단계 단어·문맥추론 MWIS)을
    '시행 단위'로 저장한다. 비심 혼동행렬·시행별 학습곡선·사전/사후 평가의 원천 데이터.
    (문장 채점은 Progress에 쌓이므로 여기엔 선다형만.)"""
    __tablename__ = "trial_attempts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    stage = Column(Integer, nullable=True)          # 1..3
    item_type = Column(String(12), nullable=False)  # 'viseme' | 'word' | 'closure'
    target = Column(String(200), nullable=False)
    chosen = Column(String(200), nullable=True)
    correct = Column(Boolean, default=False)
    phase = Column(String(10), default="practice")  # 'pre' | 'post' | 'practice'
    confusions = Column(JSON, default=list)         # [{position,target,read,viseme,same_viseme}]
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
    # SM-2 경량 스케줄링 — 항목별 난이도(ease)와 반복/누수를 기록해 복습 간격을 개인화한다.
    ease_factor = Column(Float, default=2.5)         # 클수록 간격이 빨리 늘어남(잘 맞히는 항목)
    repetitions = Column(Integer, default=0)         # 연속 성공 횟수(실패 시 0으로 리셋)
    lapses = Column(Integer, default=0)              # 누적 실패 횟수(누수·leech 판별용)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AssessmentResult(Base):
    """배치·향상도 검사 결과 이력(축 I). 매 검사 결과를 남겨, 첫 검사(baseline)와 최근 검사를
    비교해 실제로 나아졌는지(향상도)를 객관 수치로 보여준다. 훈련 전/후 효과 서사의 근거."""
    __tablename__ = "assessment_results"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    accuracy = Column(Float, default=0.0)            # 0~1 정답률
    ability = Column(Float, default=0.0)             # 통과한 최고 난이도(0~1)
    level = Column(Integer, default=1)               # 추정 수준 1~5
    error_visemes = Column(JSON, default=list)       # 자주 틀린 입모양 id 목록
    created_at = Column(DateTime, default=datetime.utcnow)


# Dependency for getting DB session
async def get_db():
    """Dependency for FastAPI routes to get database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


class ConsentRecord(Base):
    """회원가입 동의 기록(§4.9 표11 ② 미성년 보호) — 어느 판본의 약관·처리방침에 언제 동의했는지,
    만 14세 이상이거나 법정대리인 동의를 받았다고 확인했는지를 서버에 남긴다.
    화면 체크박스만으로는 API 직접 호출로 우회되고 동의 시각도 남지 않았다."""
    __tablename__ = "consent_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    terms_version = Column(String(20), nullable=False)
    privacy_version = Column(String(20), nullable=False)
    age_confirmed = Column(Boolean, default=False)   # 만 14세 이상 또는 법정대리인 동의 확인
    created_at = Column(DateTime, default=datetime.utcnow)


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
        # SM-2 경량 스케줄링 컬럼 — 기존 review_items에 없으면 추가
        for ddl in (
            "ALTER TABLE review_items ADD COLUMN ease_factor FLOAT DEFAULT 2.5",
            "ALTER TABLE review_items ADD COLUMN repetitions INTEGER DEFAULT 0",
            "ALTER TABLE review_items ADD COLUMN lapses INTEGER DEFAULT 0",
            # 토큰 무효화(비밀번호 변경 시) — 기존 users에 없으면 추가
            "ALTER TABLE users ADD COLUMN token_version INTEGER DEFAULT 0",
            # 표준검사 판본·문항 기록(축 I)
            "ALTER TABLE placement_results ADD COLUMN form_version VARCHAR(16)",
            "ALTER TABLE placement_results ADD COLUMN item_log JSON",
        ):
            try:
                await conn.exec_driver_sql(ddl)
            except Exception:
                pass  # 이미 존재


async def close_db():
    """Close database connections"""
    await engine.dispose()
