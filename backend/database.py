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
    answer_mode = Column(String(10), nullable=True)  # 'choice'(4지선다 보기를 고름)·'typed'(주관식·서술형). 9/29 전 기록과 옛 화면은 비어 있다
    # 파일럿 로그(P0): 문장 표시부터 답까지 ms, 레슨 가상 화자, 이 문장에서 연 힌트 단계(0~3), 4지선다 보기(보인 순서)
    rt_from_onset_ms = Column(Integer, nullable=True)
    talker = Column(String(16), nullable=True)
    hint_level = Column(Integer, nullable=True)
    options = Column(JSON(none_as_null=True), nullable=True)

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
    # 마지막으로 학습 초기화한 때. 초기화하면 시행 기록이 지워져 내보내기의 학습량이 줄어드는 것을 분석에서 알 수 있게 한다
    learning_reset_at = Column(DateTime, nullable=True)
    # P3 검사 참여 순번(처음 검사 상태를 볼 때 매김)과 그 순번으로 정한 폼 순서(ABC·BCA·CAB). 학습 초기화로 바뀌지 않는다
    pilot_seq = Column(Integer, nullable=True)
    pilot_order = Column(String(3), nullable=True)
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


class ListenStageProgress(Base):
    """소리 듣기(청능훈련) 커리큘럼 단계별 진행·숙달(listen_curriculum, docs/auditory-training-design.md). 독화·발화와 별도 표.
    stage: 0 소리 확인 ~ 5 대화 듣기. 건너뛰기로 연 단계는 status 'unlocked' 행으로 남는다(프로필 포인터 열을 늘리지 않으려고)."""
    __tablename__ = "listen_stage_progress"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    stage = Column(Integer, nullable=False)        # 0..5
    status = Column(String(20), default="unlocked")  # unlocked | in_progress | mastered
    mastery_score = Column(Float, default=0.0)     # 0-100 (편향 보정 이동 평균, 수준 단계는 맨 위 수준 최근 정답률)
    attempts = Column(Integer, default=0)
    correct = Column(Integer, default=0)
    level = Column(Integer, nullable=True)         # 1·2단계의 지금 수준
    mastered_attempts = Column(Integer, nullable=True)
    mastered_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ListenAttempt(Base):
    """소리 듣기 시행 하나. 숙달·수준·소음 계단·검사 역치·혼동은 모두 이 기록에서 다시 계산한다."""
    __tablename__ = "listen_attempts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    stage = Column(Integer, nullable=False)        # 0..5
    mode = Column(String(20), nullable=False)      # ling|ax|word_id|sentence|noise|test|convo
    item_key = Column(String(200), nullable=False)
    target = Column(String(200), nullable=True)    # 정답 글(소리 구별은 '첫|둘째')
    answer = Column(String(300), nullable=True)
    correct = Column(Boolean, nullable=True)
    score = Column(Float, nullable=True)           # 문장: 낱말 정답 비율 0~1
    level = Column(Integer, nullable=True)
    snr_db = Column(Float, nullable=True)
    condition = Column(String(20), nullable=True)  # ao|av(4단계·검사), quiet|noise|phone(5단계)
    voice = Column(String(40), nullable=True)
    plays = Column(Integer, nullable=True)         # 들은 횟수
    repairs = Column(JSON, nullable=True)          # 5단계 되묻기 ['again','slow','rephrase']
    rt_ms = Column(Integer, nullable=True)
    session = Column(String(40), nullable=True)    # 검사 회차 id(test:...)·점검 회차
    route = Column(String(20), nullable=True)      # 듣는 길: stream|speaker|earphone (데이터 품질용)
    output_latency_ms = Column(Integer, nullable=True)   # 브라우저가 알린 출력 지연(블루투스 포함일 수 있음, 분석 공변량)
    av_offset_ms = Column(Integer, nullable=True)        # 소리+입모양 시행에서 입모양을 늦춘 시간
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


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
    # 복습 세션 시도인가(9/28). 진행도를 건드리지 않는 시도라 개인 향상 경로(4·5단계) 기준선에서 뺀다. 예전 행은 None
    review = Column(Boolean, nullable=True)
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
    # 채점 때까지 한 독화 연습 시행 수(선다형 + 문장, 9/29). 사전 검사를 연습 뒤에 봤는지 표시한다(assessment.PRETEST_TRIALS_FLAG).
    # 학습 초기화로 시행 기록이 지워져도 검사 당시 값이 남는다. 그 전 검사는 NULL
    trials_before = Column(Integer, nullable=True)
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
    # 파일럿 로그(P0): 문항 표시(자극 재생 시작)부터 답 확정까지 ms, 레슨 가상 화자 id(t1~t4·default), 힌트를 봤는지,
    # 탐침 종류('contrast' 짝 탐색. 실제 얼굴·지연 탐침은 따로 저장한다). 예전 기록과 옛 화면은 NULL
    rt_from_onset_ms = Column(Integer, nullable=True)
    talker = Column(String(16), nullable=True)
    hint_used = Column(Boolean, nullable=True)
    probe_kind = Column(String(16), nullable=True)
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
    # FSRS 그림자 모드(C11, fsrs_shadow.py) — 간격은 SM-2가 정하고, 이 값들은 회상 확률 예측에만 쓴다. 예전 항목은 NULL
    fsrs_stability = Column(Float, nullable=True)    # 안정도(일)
    fsrs_difficulty = Column(Float, nullable=True)   # 난이도(1~10)
    last_review_on = Column(String(10), nullable=True)   # 마지막으로 반영한 날(KST 'YYYY-MM-DD'). NULL이면 updated_at으로 어림
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



class ReviewLog(Base):
    """복습 한 번의 결과와 그때의 회상 확률 예측(C11 FSRS 그림자 모드, fsrs_shadow.py). 예정일이 된 항목에 답한 복습만 남긴다.
    예측은 기록만 하고 간격은 SM-2(srs.py)가 정한다. p_*는 관측 척도(4지선다는 0.25 + 0.75·R)이고 r_fsrs는 회상 확률 그대로다.
    신규 테이블이라 create_all이 만든다."""
    __tablename__ = "review_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String(20), nullable=False)
    ref = Column(String(100), nullable=False)
    source = Column(String(16), nullable=True)       # 'review'(복습 화면) | 'sentence'(문장 레슨·복습) | 'speak'(말하기)
    reviewed_on = Column(String(10), nullable=False) # KST 'YYYY-MM-DD'
    elapsed_days = Column(Integer, nullable=True)    # 마지막 반영 뒤 지난 날수
    quality = Column(Integer, nullable=False)        # SM-2 품질(0~5, 3 이상 합격)
    grade = Column(Integer, nullable=False)          # FSRS 등급(1 Again ~ 4 Easy)
    passed = Column(Boolean, nullable=False)
    answer_mode = Column(String(10), nullable=True)
    speed = Column(Float, nullable=True)
    guess = Column(Float, default=0.0)               # 찍기 확률(4지선다 0.25)
    r_fsrs = Column(Float, nullable=True)            # FSRS 회상 확률(상태가 없던 예전 항목은 NULL)
    p_fsrs = Column(Float, nullable=True)            # FSRS 관측 정답 확률
    p_sm2 = Column(Float, nullable=True)             # SM-2 대리 예측(0.9^(t/간격))의 관측 정답 확률
    sm2_interval = Column(Integer, nullable=True)    # 이 복습 전 SM-2 간격
    fsrs_stability = Column(Float, nullable=True)    # 이 복습 전 FSRS 상태
    fsrs_difficulty = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class MasteryProbe(Base):
    """숙달 지연 탐침(C16, mastery_probe.py) — 읽기 1~3단계를 처음 숙달하고 1일·7일 뒤에 낸 처음 보는 문항과 답.
    숙달·복습·시행 기록(TrialAttempt)·XP에는 넣지 않는다. 회차를 처음 낼 때 문항을 만들어 두고(chosen NULL), 답하면 채운다.
    신규 테이블이라 create_all이 만든다."""
    __tablename__ = "mastery_probes"
    __table_args__ = (UniqueConstraint("user_id", "stage", "wave", "seq", name="ux_mastery_probes_user_stage_wave_seq"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    stage = Column(Integer, nullable=False)          # 1..3
    wave = Column(Integer, nullable=False)           # 1 | 7 (숙달 뒤 일수)
    seq = Column(Integer, nullable=False)            # 회차 안 순번
    item_kind = Column(String(12), nullable=False)   # 'viseme' | 'word' | 'sentence'
    stimulus = Column(String(200), nullable=False)   # 아바타가 말하는 글
    target = Column(String(200), nullable=False)     # 정답(1단계는 입모양 무리 번호)
    options = Column(JSON, default=list)             # [{value, label}] 보인 순서
    mastered_on = Column(String(10), nullable=True)  # 숙달한 날(KST)
    due_on = Column(String(10), nullable=False)      # 회차 첫날(KST)
    chosen = Column(String(200), nullable=True)
    correct = Column(Boolean, nullable=True)         # 아직 안 풀었으면 NULL
    delay_days = Column(Integer, nullable=True)      # 숙달 뒤 실제로 푼 날까지의 날수
    speed = Column(Float, nullable=True)             # 재생 속도(늘 1.0, 보조 없음)
    answered_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class RetentionResult(Base):
    """지연 유지 검사(C7, retention.py) 결과 — 사후 검사와 같은 동형 폼을 정해진 날수 뒤에 다시 본 기록.
    사전·사후 비교(placement_results)에 섞이지 않게 따로 둔다. 신규 테이블이라 create_all이 만든다."""
    __tablename__ = "retention_results"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    form = Column(String(16), nullable=False)        # 다시 본 동형 폼(사후 검사의 폼)
    form_version = Column(String(16), nullable=True)
    post_result_id = Column(Integer, nullable=True)  # 짝이 되는 사후 검사(placement_results.id)
    days_after_post = Column(Integer, nullable=True)
    total = Column(Integer, default=0)
    correct = Column(Integer, default=0)
    accuracy = Column(Float, default=0.0)
    ability = Column(Float, default=0.0)
    level = Column(Integer, default=1)
    item_log = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)


class LessonEffort(Base):
    """레슨별 정신적 노력 한 문항(C14, mental_effort.py, Paas 9점). 레슨 세션(화면이 만든 id)마다 한 행.
    response: 'answered' | 'skipped' | 'left'. 적응 규칙 없이 기록만 한다. 신규 테이블이라 create_all이 만든다."""
    __tablename__ = "lesson_efforts"
    __table_args__ = (UniqueConstraint("user_id", "session_id", name="ux_lesson_efforts_user_session"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(String(40), nullable=False)
    lesson_kind = Column(String(16), nullable=True)  # 'viseme' | 'word' | 'sentence' | 'closure' | 'review'
    stage = Column(Integer, nullable=True)           # 읽기 단계(복습은 NULL)
    rating = Column(Integer, nullable=True)          # 1~9, 답하지 않았으면 NULL
    response = Column(String(10), nullable=False)
    n_items = Column(Integer, nullable=True)         # 그 레슨에서 푼 문항 수
    accuracy = Column(Float, nullable=True)          # 그 레슨 정답률(0~1)
    render_log = Column(JSON(none_as_null=True), nullable=True)   # 그 레슨의 기기·렌더링 요약(V20, pilot_battery.clean_render_log)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SentencePracticeLog(Base):
    """3단계 문장의 연습 답(practice_only) 기록. 숙달·XP·복습·오답 목록과 무관하고 분석용으로만 남긴다.
    reason: 'consonant_retry'(자음 피드백 뒤 두 번째 답, C9) | 'hint3'(발음 자막을 본 뒤) | 'answer_shown'(정답을 본 뒤 다시 풀기).
    C9의 효과(두 번째 답이 첫 답보다 나아지는지)와 힌트 3 사용을 보려는 것이다. 신규 테이블이라 create_all이 만든다."""
    __tablename__ = "sentence_practice_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    scenario_id = Column(String(200), nullable=True)
    sentence = Column(String(200), nullable=True)
    user_answer = Column(String(200), nullable=True)
    reason = Column(String(16), nullable=True)
    score = Column(Float, nullable=True)
    hint_level = Column(Integer, nullable=True)
    rt_from_onset_ms = Column(Integer, nullable=True)
    words_correct = Column(Integer, nullable=True)   # 자음 피드백 낱말 판정(sentence_feedback)의 맞힌 낱말 수
    words_total = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class P3TestSession(Base):
    """청인 예비 파일럿(P3) 검사 회차의 층 하나(pilot_battery.py, docs/pilot/battery.md). 사람 × 회차(A1·A2·B·R) × 층마다 한 행.
    층을 시작할 때 만들고 끝내면 completed를 채운다. 끝내지 못한 층도 행이 남아 ITT 분석에서 결측을 셀 수 있다.
    form_version은 검사 목록 파일의 version, manifest_sha는 그 내용 해시다. 신규 테이블이라 create_all이 만든다."""
    __tablename__ = "p3_test_sessions"
    __table_args__ = (UniqueConstraint("user_id", "session_label", "layer", name="ux_p3_test_sessions_user_label_layer"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_label = Column(String(4), nullable=False)    # 'A1' | 'A2' | 'B' | 'R'
    layer = Column(String(12), nullable=False)           # 'word' | 'sentence' | 'nonsense' | 'snr' | 'av'
    form = Column(String(2), nullable=False)             # 'A' | 'B' | 'C'
    form_version = Column(String(32), nullable=True)
    manifest_sha = Column(String(16), nullable=True)
    planned_order = Column(String(3), nullable=True)     # 'ABC' | 'BCA' | 'CAB'
    join_seq = Column(Integer, nullable=True)            # 검사 참여 순번(배정 근거)
    modality = Column(String(8), nullable=True)          # 'real' | 'avatar' | 'audio'(snr) | 'mixed'(av의 A·AV)
    talker = Column(String(16), nullable=True)           # 문장·소음 층의 배정 화자(낱말 층은 문항마다 다름)
    n_items = Column(Integer, default=0)                 # 폼의 문항 수
    n_ready = Column(Integer, default=0)                 # 낼 수 있었던 문항 수(영상·문장이 준비된 것)
    missing = Column(JSON, default=dict)                 # 못 낸 까닭별 문항 수 {media, text, noise, snr}
    snr_calibrated_db = Column(Float, nullable=True)     # snr 층: 계단 추정값. av 층: 쓴 값(A1 snr 층에서 가져옴)
    headphone_check = Column(Boolean, nullable=True)     # 소음 층: 헤드폰 착용 확인
    volume_fixed = Column(Boolean, nullable=True)        # 소음 층: 볼륨 고정 확인
    render_log = Column(JSON(none_as_null=True), nullable=True)   # 기기·렌더링 요약(pilot_battery.clean_render_log)
    completed = Column(Boolean, default=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


class P3ClosedResponse(Base):
    """P3 닫힌 응답(실제 얼굴 낱말 4지선다, 무의미 낱말 자음 식별) 한 문항. 영상이 준비되지 않아 내지 않은 문항은 행이 없다.
    rt_ms는 첫 재생이 끝난 때부터, rt_from_onset_ms는 첫 재생이 시작한 때부터 답을 확정할 때까지(ms)."""
    __tablename__ = "p3_closed_responses"
    __table_args__ = (UniqueConstraint("session_id", "item_id", name="ux_p3_closed_session_item"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(Integer, ForeignKey("p3_test_sessions.id", ondelete="CASCADE"), nullable=False)
    layer = Column(String(12), nullable=False)
    item_id = Column(String(40), nullable=False)
    seq = Column(Integer, nullable=True)                 # 제시 순번(1부터)
    talker = Column(String(16), nullable=True)
    modality = Column(String(8), nullable=True)
    target = Column(String(100), nullable=False)
    options = Column(JSON(none_as_null=True), nullable=True)      # 낱말: 보인 순서 4개. 무의미 낱말: 자리별 자음 목록
    chosen = Column(String(100), nullable=True)
    correct = Column(Boolean, default=False)
    target_consonants = Column(JSON(none_as_null=True), nullable=True)   # 무의미 낱말: [C1, C2, C3]
    chosen_consonants = Column(JSON(none_as_null=True), nullable=True)
    consonant_hits = Column(Integer, nullable=True)      # 맞힌 자리 수 0~3
    rt_ms = Column(Integer, nullable=True)
    rt_from_onset_ms = Column(Integer, nullable=True)
    plays = Column(Integer, nullable=True)
    speed = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class P3OpenResponse(Base):
    """P3 열린 응답(개방형 문장, 소음 속 문장, SNR 계단 시행) 한 문항. 타이핑 원문(answer_text, NFC)과 그때의 앱 점수(app_score,
    scoring.calculate_score visual)를 남기고, 엄격 음소 정답률(auto_phoneme_acc)은 phoneme_accuracy 모듈이 있을 때만 채운다
    (0~1, 맞힌·목표 음소 수와 함께. 채점하지 못했으면 NULL로 두고 scripts/pilot_battery_rescore.py로 나중에 계산한다)."""
    __tablename__ = "p3_open_responses"
    __table_args__ = (UniqueConstraint("session_id", "item_id", name="ux_p3_open_session_item"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(Integer, ForeignKey("p3_test_sessions.id", ondelete="CASCADE"), nullable=False)
    layer = Column(String(12), nullable=False)
    item_id = Column(String(40), nullable=False)
    seq = Column(Integer, nullable=True)
    talker = Column(String(16), nullable=True)
    modality = Column(String(8), nullable=True)          # 'real' | 'avatar' | 'A' | 'AV'
    target = Column(String(300), nullable=False)
    answer_text = Column(String(300), nullable=False, default="")
    app_score = Column(Float, nullable=True)
    app_phoneme_accuracy = Column(JSON(none_as_null=True), nullable=True)
    auto_phoneme_acc = Column(Float, nullable=True)
    auto_word_acc = Column(Float, nullable=True)
    n_matched_phonemes = Column(Integer, nullable=True)  # 엄격 채점의 맞힌 음소 수(회차 점수 = 합 / 합)
    n_target_phonemes = Column(Integer, nullable=True)   # 엄격 채점의 목표 음소 수
    strict_result = Column(JSON(none_as_null=True), nullable=True)
    scorer_version = Column(String(40), nullable=True)   # 엄격 채점 판본(예: 'strict-v1'). 채점하지 못했으면 NULL
    rt_ms = Column(Integer, nullable=True)
    rt_from_onset_ms = Column(Integer, nullable=True)
    plays = Column(Integer, nullable=True)
    speed = Column(Float, nullable=True)
    snr_db = Column(Float, nullable=True)
    noise_type = Column(String(16), nullable=True)
    criterion_met = Column(Boolean, nullable=True)       # snr 층: 계단 판정(낱말 일치 비율 >= 기준)
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
    ("listen_attempts", "output_latency_ms", "INTEGER"),
    ("listen_attempts", "av_offset_ms", "INTEGER"),
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
    # 검사 전 독화 연습 시행 수(연습 뒤 사전 검사 표시, docs/eval-metrics.md 9절)
    ("placement_results", "trials_before", "INTEGER"),
    # 파일럿 참여 코드·집단(§4.7)
    ("learning_profiles", "pilot_code", "VARCHAR(32)"),
    ("learning_profiles", "cohort", "VARCHAR(16)"),
    ("learning_profiles", "pilot_joined_at", "TIMESTAMP"),
    ("learning_profiles", "learning_reset_at", "TIMESTAMP"),
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
    # 복습 세션 시도 표시(개인 향상 경로에서 뺀다)
    ("speak_attempts", "review", "BOOLEAN"),
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
    # 3단계 문장 답 방식(보기 고름·직접 입력, docs/mastery-ewma.md 10절)
    ("progress", "answer_mode", "VARCHAR(10)"),
    # FSRS 그림자 모드 상태(C11, 간격은 바꾸지 않음)
    ("review_items", "fsrs_stability", "FLOAT"),
    ("review_items", "fsrs_difficulty", "FLOAT"),
    ("review_items", "last_review_on", "VARCHAR(10)"),
    # 파일럿 로그 사양 점검(P0, docs/pilot/log-spec-audit.md): 학습 시행의 반응 시간·화자·힌트·탐침 종류
    ("trial_attempts", "rt_from_onset_ms", "INTEGER"),
    ("trial_attempts", "talker", "VARCHAR(16)"),
    ("trial_attempts", "hint_used", "BOOLEAN"),
    ("trial_attempts", "probe_kind", "VARCHAR(16)"),
    ("progress", "rt_from_onset_ms", "INTEGER"),
    ("progress", "talker", "VARCHAR(16)"),
    ("progress", "hint_level", "INTEGER"),
    ("progress", "options", "JSON"),
    # 레슨별 기기·렌더링 요약(V20)
    ("lesson_efforts", "render_log", "JSON"),
    # P3 검사 참여 순번과 폼 순서(pilot_battery.assign_order)
    ("learning_profiles", "pilot_seq", "INTEGER"),
    ("learning_profiles", "pilot_order", "VARCHAR(3)"),
)


async def init_db():
    """Initialize database tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _add_missing_columns(conn)
        await _dedupe_and_index(conn)
        await _pilot_seq_index(conn)
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
    ("listen_stage_progress", "user_id, stage",
     "CASE status WHEN 'mastered' THEN 0 ELSE 1 END, attempts DESC, id DESC"),
    ("weak_visemes", "user_id, viseme_id", "total_attempts DESC, id DESC"),
    ("review_items", "user_id, kind, ref", "updated_at DESC, id DESC"),
)


async def _pilot_seq_index(conn) -> None:
    """P3 검사 참여 순번(learning_profiles.pilot_seq)의 고유 인덱스. 순번은 폼 순서·화자·제시 순서를 정하므로 둘이 같으면 역균형이 깨진다.
    NULL은 여럿이어도 된다(SQLite·PostgreSQL 모두). 이미 겹친 순번이 있으면 만들지 못하고 경고만 남긴다(지우지 않는다)."""
    try:
        async with _Isolated(conn):
            await conn.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_learning_profiles_pilot_seq ON learning_profiles (pilot_seq)")
    except Exception as e:
        print(f"[WARN] learning_profiles.pilot_seq 고유 인덱스 실패(겹친 순번 확인 필요): {e}")
    try:   # 유지 검사(C7)는 사후 검사 하나에 한 행(두 번 눌러 두 행이 생기던 것)
        async with _Isolated(conn):
            await conn.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_retention_results_user_post ON retention_results (user_id, post_result_id)")
    except Exception as e:
        print(f"[WARN] retention_results 고유 인덱스 실패(겹친 행 확인 필요): {e}")


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
    ("listen_attempts", "user_id, created_at"),
    ("placement_results", "user_id, created_at"),
    ("tactile_attempts", "user_id, created_at"),
    ("articulation_sessions", "user_id, created_at"),
    ("assessment_results", "user_id, created_at"),
    ("bookmarks", "user_id"),
    ("consent_records", "user_id"),
    ("review_logs", "user_id, created_at"),
    ("mastery_probes", "user_id, created_at"),
    ("retention_results", "user_id, created_at"),
    ("p3_test_sessions", "user_id"),
    ("p3_closed_responses", "user_id, session_id"),
    ("p3_open_responses", "user_id, session_id"),
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
