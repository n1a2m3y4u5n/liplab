"""
Database configuration and models for LIPLAB
Supports both SQLite (development) and PostgreSQL (production)
"""
import os
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, ForeignKey, Boolean, UniqueConstraint
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
    speed = Column(Float, nullable=True)  # 답하기 전에 본 유효 재생 속도(기록만, 숙달에는 넣지 않음. docs/mastery-ewma.md 9절)

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
    speak_current_stage = Column(Integer, default=0)   # 발화 트랙 건너뛰기로 연 단계(0 발성 ~ 5 문장)
    placed = Column(Boolean, default=False)        # 배치(트랙 선택) 완료 여부
    # 파일럿(§4.7) — 참여 코드와 집단. 코드는 운영자가 나눠 준 값이고, 내보내기는 가명으로만 한다.
    pilot_code = Column(String(32), nullable=True)
    cohort = Column(String(16), nullable=True)
    pilot_joined_at = Column(DateTime, nullable=True)   # 참여 코드를 처음 넣은 때(내보내기의 '참여 뒤' 집계 기준)
    # 예정된 복습에 답한 누적 횟수('복습왕' 배지). 복습 항목은 졸업하면 지워져 항목 수로는 셀 수 없다
    reviews_completed = Column(Integer, default=0)
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
    mastered_attempts = Column(Integer, nullable=True)   # 처음 숙달한 순간의 시도 수(학습 효과 리포트의 숙달 도달 시행수)
    mastered_at = Column(DateTime, nullable=True)
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
    # 회차 상세(Figma 212:24)용 — 소리(융합 전 음향 점수)·입모양(웹캠)·융합·불확실성, 음소 칩, 코칭 문장
    audio_score = Column(Float, nullable=True)
    mouth_score = Column(Float, nullable=True)
    fused_score = Column(Float, nullable=True)
    uncertainty = Column(Float, nullable=True)
    phones = Column(JSON, nullable=True)            # [{label, dgop}] 정렬·채점 대상 음소만(최대 40)
    coaching = Column(String(600), nullable=True)
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
    item_type = Column(String(12), nullable=False)  # 'viseme' | 'word' | 'word_typed' | 'closure' | 'context'
    target = Column(String(200), nullable=False)
    chosen = Column(String(200), nullable=True)
    correct = Column(Boolean, default=False)
    phase = Column(String(10), default="practice")  # 'pre' | 'post' | 'practice'
    confusions = Column(JSON, default=list)         # [{position,target,read,viseme,same_viseme}]
    item_id = Column(String(40), nullable=True)     # 문맥 추론 문항 id(정답 단어가 여러 문항에 겹쳐 target으로는 못 가린다)
    speed = Column(Float, nullable=True)            # 답하기 전에 본 실제 재생 속도(1.0 미만은 감속, docs/mastery-ewma.md 7절)
    # 화면에 보여 준 보기(정답 포함, 보인 순서). 1단계는 입모양 번호 문자열. 주관식이나 예전 기록은 NULL.
    # 보기에 무엇이 있었는지 알아야 '그 보기가 있었을 때 고른 비율'로 혼동을 잴 수 있다(docs/confusion-pair-serving.md 5.4)
    options = Column(JSON(none_as_null=True), nullable=True)   # None은 SQL NULL(IS NOT NULL로 거른다)
    # 짝 탐색 문항이면 {position, target, read, contrast, source}(보기에 대비 단어를 넣은 2단계 단어 문항, 5.4-2). 보통 문항은 NULL.
    # item_type은 'word' 그대로라 숙달·학습 곡선에 똑같이 들어가고, 분석은 이 열로 탐색 문항을 가를 수 있다
    probe = Column(JSON(none_as_null=True), nullable=True)   # None은 SQL NULL(IS NOT NULL로 거른다)
    created_at = Column(DateTime, default=datetime.utcnow)


class ReviewItem(Base):
    """간격 반복(SRS) 복습 큐 — 틀린 항목이 due_date에 다시 등장한다.
    kind: 'viseme'(입모양 그룹, ref=id 문자열) | 'word'(단어, ref=단어) | 'speak'(말하기, ref=목표 문장·단어)
    | 'sentence'(3단계 문장, ref=문장. 상황·난이도는 그 문장의 최근 Progress 기록에서 가져온다)."""
    __tablename__ = "review_items"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String(20), nullable=False)       # 'viseme' | 'word' | 'speak' | 'sentence'
    ref = Column(String(100), nullable=False)       # viseme_id(str) 또는 단어
    due_date = Column(String(10), nullable=False)   # 'YYYY-MM-DD'
    interval_days = Column(Integer, default=1)
    # SM-2 경량 스케줄링 — 항목별 난이도(ease)와 반복/누수를 기록해 복습 간격을 개인화한다.
    ease_factor = Column(Float, default=2.5)         # 클수록 간격이 빨리 늘어남(잘 맞히는 항목)
    repetitions = Column(Integer, default=0)         # 연속 성공 횟수(실패 시 0으로 리셋)
    lapses = Column(Integer, default=0)              # 누적 실패 횟수(누수·leech 판별용)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TaskClaim(Base):
    """과제 보상 수령 기록(과제 탭, daily_tasks.py). 과제마다 기간에 한 번만 XP를 준다.
    period: 하루 과제는 'YYYY-MM-DD'(KST), 주 과제는 'W' + 그 주 월요일. 신규 테이블이라 create_all이 만든다."""
    __tablename__ = "task_claims"
    __table_args__ = (UniqueConstraint("user_id", "task_key", "period", name="ux_task_claims_user_task_period"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    task_key = Column(String(32), nullable=False)
    period = Column(String(16), nullable=False)
    xp = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


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


# 경량 마이그레이션: create_all은 기존 표에 컬럼을 더하지 않으므로, 나중에 생긴 컬럼을 (표, 컬럼, 형) 목록으로 두고 켜질 때 없는 것만 더한다.
# 예전에는 ALTER를 모두 한 트랜잭션에서 돌리고 실패를 try/except pass로 넘겼다. SQLite에서는 '이미 있음' 실패가 트랜잭션을 깨지 않아
# 괜찮았지만 PostgreSQL은 한 문장이 실패하면 그 트랜잭션의 뒤 문장이 모두 실패해(current transaction is aborted), 첫 ALTER가 '이미 있음'으로
# 실패하면 뒤에 새로 더한 컬럼이 조용히 빠졌다. 지금은 있는 컬럼을 먼저 읽어 없는 것만 ALTER하고, 문장마다 SAVEPOINT로 실패를 가둔다.
_ADD_COLUMNS = (
    ("bookmarks", "domain", "VARCHAR(12) DEFAULT 'read'"),
    # SM-2 경량 스케줄링 컬럼
    ("review_items", "ease_factor", "FLOAT DEFAULT 2.5"),
    ("review_items", "repetitions", "INTEGER DEFAULT 0"),
    ("review_items", "lapses", "INTEGER DEFAULT 0"),
    # 토큰 무효화(비밀번호 변경 시)
    ("users", "token_version", "INTEGER DEFAULT 0"),
    # 표준검사 판본·문항 기록(축 I)
    ("placement_results", "form_version", "VARCHAR(16)"),
    ("placement_results", "item_log", "JSON"),
    # 파일럿 참여 코드·집단(§4.7)
    ("learning_profiles", "pilot_code", "VARCHAR(32)"),
    ("learning_profiles", "cohort", "VARCHAR(16)"),
    ("learning_profiles", "pilot_joined_at", "TIMESTAMP"),
    # 발화 트랙 건너뛰기(Figma 78:8·79:5·80:6)
    ("learning_profiles", "speak_current_stage", "INTEGER DEFAULT 0"),
    # 누적 복습 횟수('복습왕' 배지)
    ("learning_profiles", "reviews_completed", "INTEGER DEFAULT 0"),
    # 말하기 회차 상세(Figma 212:24)
    ("speak_attempts", "audio_score", "FLOAT"),
    ("speak_attempts", "mouth_score", "FLOAT"),
    ("speak_attempts", "fused_score", "FLOAT"),
    ("speak_attempts", "uncertainty", "FLOAT"),
    ("speak_attempts", "phones", "JSON"),
    ("speak_attempts", "coaching", "VARCHAR(600)"),
    # 숙달 도달 시행수(docs/eval-metrics.md)
    ("stage_progress", "mastered_attempts", "INTEGER"),
    ("stage_progress", "mastered_at", "TIMESTAMP"),
    # 문맥 추론 문항 id(최근에 푼 문항을 뒤로 보내기)
    ("trial_attempts", "item_id", "VARCHAR(40)"),
    # 답할 때 본 재생 속도(감속 정답은 숙달에 0.5)
    ("trial_attempts", "speed", "FLOAT"),
    # 보여 준 보기(기회로 나눈 혼동률)
    ("trial_attempts", "options", "JSON"),
    ("trial_attempts", "probe", "JSON"),
    # 3단계 문장 답의 유효 재생 속도(기록만)
    ("progress", "speed", "FLOAT"),
)


async def init_db():
    """Initialize database tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _add_missing_columns(conn)
        await _dedupe_and_index(conn)
        await _user_indexes(conn)


def _existing_columns(sync_conn) -> dict:
    """{표: 컬럼 이름 집합}. run_sync로 부른다."""
    from sqlalchemy import inspect
    insp = inspect(sync_conn)
    return {t: {c["name"] for c in insp.get_columns(t)} for t in insp.get_table_names()}


class _Isolated:
    """문장 하나의 실패를 그 문장에 가둔다. PostgreSQL 등은 SAVEPOINT(begin_nested)로 되돌리고, SQLite는 실패한 문장이 트랜잭션을
    깨지 않으므로 그대로 둔다(pysqlite는 SAVEPOINT 처리가 불안정해 예전 동작을 유지한다)."""

    def __init__(self, conn):
        self._tx = None if conn.dialect.name == "sqlite" else conn.begin_nested()

    async def __aenter__(self):
        if self._tx is not None:
            await self._tx.__aenter__()
        return self

    async def __aexit__(self, *exc):
        if self._tx is not None:
            return await self._tx.__aexit__(*exc)
        return False


async def _add_missing_columns(conn, columns=_ADD_COLUMNS) -> list:
    """없는 컬럼만 ALTER TABLE로 더한다. 표가 아직 없으면(create_all이 새로 만든 표에는 이미 있다) 건너뛴다. 더한 (표, 컬럼) 목록."""
    have = await conn.run_sync(_existing_columns)
    added = []
    for table, col, ddl_type in columns:
        if table not in have or col in have[table]:
            continue
        try:
            async with _Isolated(conn):
                await conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {col} {ddl_type}")
            added.append((table, col))
        except Exception as e:   # 켜지는 것을 막지 않는다. 다만 조용히 넘기지 않는다
            print(f"[WARN] {table}.{col} 컬럼 추가 실패: {e}")
    return added


# 사용자별로 한 행이어야 하는 표. 예전에는 고유 제약이 없어(조회 뒤 없으면 넣기) 동시 첫 제출이나 데모 재시드로
# 같은 키의 행이 두 벌 생겼고, 그 뒤 scalar_one_or_none()이 예외를 내 그 단계의 답 제출이 계속 500이었다
# (9/26 liplab-dev 데모 계정 2단계). 켜질 때 한 행만 남기고(숙달 > 시도 많은 행 > 최근 행) 고유 인덱스를 건다.
_UNIQUE_KEYS = (
    ("stage_progress", "user_id, stage",
     "CASE status WHEN 'mastered' THEN 0 ELSE 1 END, attempts DESC, id DESC"),
    ("speak_stage_progress", "user_id, stage",
     "CASE status WHEN 'mastered' THEN 0 ELSE 1 END, attempts DESC, id DESC"),
    ("tactile_stage_progress", "user_id, stage",
     "CASE status WHEN 'mastered' THEN 0 ELSE 1 END, attempts DESC, id DESC"),
    ("weak_visemes", "user_id, viseme_id", "total_attempts DESC, id DESC"),
    ("review_items", "user_id, kind, ref", "updated_at DESC, id DESC"),
)


async def _dedupe_and_index(conn) -> None:
    for table, key, order in _UNIQUE_KEYS:
        name = "ux_" + table + "_" + key.replace(", ", "_")
        try:
            async with _Isolated(conn):
                await _dedupe_one(conn, table, key, order, name)
        except Exception as e:   # 켜지는 것을 막지 않는다(조회 쪽도 여러 행에서 첫 행을 쓴다)
            print(f"[WARN] {table} 중복 정리·고유 인덱스 실패: {e}")


async def _dedupe_one(conn, table: str, key: str, order: str, name: str) -> None:
    await conn.exec_driver_sql(
        f"DELETE FROM {table} WHERE id IN (SELECT id FROM ("
        f"SELECT id, ROW_NUMBER() OVER (PARTITION BY {key} ORDER BY {order}) AS rn FROM {table}"
        f") AS ranked WHERE rn > 1)")
    await conn.exec_driver_sql(f"CREATE UNIQUE INDEX IF NOT EXISTS {name} ON {table} ({key})")


# 사용자별 기록 표는 늘 user_id로(대개 시간순까지) 읽는다(분석 탭·학습 효과 리포트·말하기 분석·문맥 추론 순서·배치검사 비교).
# 예전에는 인덱스가 id뿐이라 요청마다 표 전체를 훑었다. 켜질 때 없으면 만든다(create_all은 기존 표에 인덱스를 더하지 않는다).
_USER_INDEXES = (
    ("progress", "user_id, created_at"),
    ("trial_attempts", "user_id, created_at"),
    ("speak_attempts", "user_id, created_at"),
    ("placement_results", "user_id, created_at"),
    ("tactile_attempts", "user_id, created_at"),
    ("articulation_sessions", "user_id, created_at"),
    ("assessment_results", "user_id, created_at"),
    ("bookmarks", "user_id"),
    ("consent_records", "user_id"),
)


async def _user_indexes(conn) -> None:
    for table, cols in _USER_INDEXES:
        name = "ix_" + table + "_" + cols.replace(", ", "_")
        try:
            async with _Isolated(conn):
                await conn.exec_driver_sql(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({cols})")
        except Exception as e:   # 켜지는 것을 막지 않는다
            print(f"[WARN] {table} 인덱스 실패: {e}")


async def close_db():
    """Close database connections"""
    await engine.dispose()
