"""
LIPLAB FastAPI Main Application
Serves API endpoints and React static files for production deployment
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import local modules
from database import init_db, close_db, get_db
from auth import (
    UserRegister, UserLogin, Token, UserResponse,
    register_user, authenticate_user, create_token_response,
    get_current_user
)

# Import engines (will be created in next steps)
# These imports will work once we create the modules
try:
    from engine import text_to_visemes
    from llm_service import generate_adaptive_scenario, generate_conversation_turn, generate_analysis_recommendation
    from scoring import calculate_score
except ImportError:
    # Placeholder functions for initial setup
    async def text_to_visemes(text: str):
        return []
    async def generate_adaptive_scenario(user_id: int, situation: str, level: int, db):
        return {"sentences": [], "situation": situation, "level": level}
    async def calculate_score(correct: str, user_answer: str):
        return {"score": 0, "details": {}}
    async def generate_conversation_turn(situation: str, level: int, history: list):
        return {"text": "안녕하세요."}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup and shutdown"""
    # Startup
    await init_db()
    print("[OK] Database initialized")
    yield
    # Shutdown
    await close_db()
    print("[OK] Database connections closed")


# Initialize FastAPI app
app = FastAPI(
    title="LIPLAB API",
    description="AI-Powered Speechreading Training Platform for the Deaf",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================
# Authentication Endpoints
# ============================================

@app.post("/api/auth/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserRegister, db: AsyncSession = Depends(get_db)):
    """Register a new user account"""
    user = await register_user(user_data, db)
    return create_token_response(user)


@app.post("/api/auth/login", response_model=Token)
async def login(credentials: UserLogin, db: AsyncSession = Depends(get_db)):
    """Authenticate user and return JWT token"""
    user = await authenticate_user(credentials.email, credentials.password, db)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return create_token_response(user)


@app.post("/api/auth/demo", response_model=Token)
async def demo_login(db: AsyncSession = Depends(get_db)):
    """로그인 없이 데모 계정으로 즉시 입장(멱등). 심사·데모 편의를 위해 계정이 없으면
    생성하고 토큰을 발급한다. 인증 체계 자체는 그대로라 진행도·북마크 등은 정상 동작한다."""
    from sqlalchemy import select
    from database import User
    from auth import get_password_hash

    email = "demo@liplab.app"
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(email=email, username="게스트", hashed_password=get_password_hash("liplab-demo-guest"))
        db.add(user)
        try:
            await db.commit()
            await db.refresh(user)
        except Exception:
            # 동시 첫 요청 경쟁 → 유니크 충돌 시 롤백 후 재조회
            await db.rollback()
            result = await db.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=500, detail="Demo login failed")
    return create_token_response(user)


@app.get("/api/auth/me", response_model=UserResponse)
async def get_me(current_user = Depends(get_current_user)):
    """Get current authenticated user information"""
    return current_user


# ============================================
# Core API Endpoints
# ============================================

from pydantic import BaseModel
from typing import List, Optional

class VisemeFrame(BaseModel):
    viseme: int
    duration_ms: int
    transition_ms: int = 50
    text_index: int


class ScenarioResponse(BaseModel):
    situation: str
    level: int
    sentences: List[str]
    scenario_id: str


class ProgressSubmission(BaseModel):
    scenario_id: str
    sentence: str
    user_answer: str
    time_spent_seconds: int
    situation: str
    difficulty_level: int


class ProgressResponse(BaseModel):
    status: str
    score: float
    new_level: int
    xp_gained: int
    streak_count: int = 0
    streak_multiplier: float = 1.0
    feedback: dict
    phoneme_accuracy: dict


@app.get("/api/viseme", response_model=List[VisemeFrame])
async def get_visemes(text: str):
    """
    Convert Korean text to viseme animation frames
    Returns array of viseme IDs with duration and transition timing
    """
    if not text or len(text.strip()) == 0:
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    try:
        visemes = await text_to_visemes(text)
        return visemes
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Viseme conversion failed: {str(e)}")


@app.get("/api/scenario", response_model=ScenarioResponse)
async def get_scenario(
    situation: str,
    level: int,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate adaptive learning scenario based on user's weak points
    Uses Claude API to create contextually relevant sentences
    """
    if level < 1 or level > 5:
        raise HTTPException(status_code=400, detail="Level must be between 1 and 5")

    try:
        scenario = await generate_adaptive_scenario(
            user_id=current_user.id,
            situation=situation,
            level=level,
            db=db
        )
        return scenario
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scenario generation failed: {str(e)}")


@app.post("/api/progress", response_model=ProgressResponse)
async def submit_progress(
    submission: ProgressSubmission,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Submit practice result and update user progress
    Returns score, XP gained, and adaptive feedback
    """
    try:
        # Calculate score with phonological similarity weighting
        scoring_result = await calculate_score(
            correct=submission.sentence,
            user_answer=submission.user_answer,
            db=db
        )

        # Save progress to database
        from database import Progress, WeakViseme
        from sqlalchemy import select, update

        progress = Progress(
            user_id=current_user.id,
            scenario_id=submission.scenario_id,
            sentence=submission.sentence,
            user_answer=submission.user_answer,
            score=scoring_result["score"],
            time_spent_seconds=submission.time_spent_seconds,
            difficulty_level=submission.difficulty_level,
            situation=submission.situation,
            viseme_errors=scoring_result.get("viseme_errors", []),
            phoneme_accuracy=scoring_result.get("phoneme_accuracy", {})
        )
        db.add(progress)

        # Update weak visemes
        # Step 1: increment total_attempts for ALL visemes in the sentence
        all_viseme_frames = await text_to_visemes(submission.sentence)
        all_viseme_ids = list({
            f["viseme"] for f in all_viseme_frames
            if 1 <= f["viseme"] <= 10  # only named groups
        })
        error_ids = set(scoring_result.get("viseme_errors", []))

        for viseme_id in all_viseme_ids:
            result = await db.execute(
                select(WeakViseme).where(
                    WeakViseme.user_id == current_user.id,
                    WeakViseme.viseme_id == viseme_id
                )
            )
            weak_viseme = result.scalar_one_or_none()

            if weak_viseme:
                weak_viseme.total_attempts += 1
                if viseme_id in error_ids:
                    weak_viseme.error_count += 1
                    weak_viseme.last_error_at = progress.created_at
            else:
                weak_viseme = WeakViseme(
                    user_id=current_user.id,
                    viseme_id=viseme_id,
                    error_count=1 if viseme_id in error_ids else 0,
                    total_attempts=1,
                    phonological_feature=scoring_result.get("features", {}).get(str(viseme_id), "unknown")
                )
                db.add(weak_viseme)

        # Streak calculation
        from datetime import date, timedelta
        today_str = date.today().isoformat()
        yesterday_str = (date.today() - timedelta(days=1)).isoformat()
        last_date = current_user.last_practice_date

        if last_date is None or last_date < yesterday_str:
            current_user.streak_count = 1       # 첫 연습 or 스트릭 끊김
        elif last_date == yesterday_str:
            current_user.streak_count += 1      # 연속 학습!
        # last_date == today_str: 오늘 이미 연습 → streak_count 유지
        current_user.last_practice_date = today_str

        # Calculate XP and level up logic
        base_xp = int(scoring_result["score"] * submission.difficulty_level * 2)
        time_bonus = max(0, 50 - submission.time_spent_seconds // 2)
        streak_multiplier = min(1.0 + current_user.streak_count * 0.1, 3.0)
        xp_gained = int(base_xp * streak_multiplier) + time_bonus

        current_user.total_xp += xp_gained

        # Level up formula: level = floor(sqrt(total_xp / 100)) + 1
        new_level = int((current_user.total_xp / 100) ** 0.5) + 1
        current_user.current_level = max(current_user.current_level, new_level)

        # 3단계(문장 연습) 숙달 갱신 — 점수 PASS 이상이면 성공 1회로 누적(4단계 해금 근거)
        await _bump_stage_progress(
            current_user.id, 3, scoring_result["score"] >= _STAGE3_PASS,
            _STAGE3_MIN_ATTEMPTS, _STAGE3_MASTERY, db)

        await db.commit()

        return ProgressResponse(
            status="success",
            score=scoring_result["score"],
            new_level=current_user.current_level,
            xp_gained=xp_gained,
            streak_count=current_user.streak_count,
            streak_multiplier=round(streak_multiplier, 2),
            feedback=scoring_result.get("feedback", {}),
            phoneme_accuracy=scoring_result.get("phoneme_accuracy", {})
        )

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Progress submission failed: {str(e)}")


@app.get("/api/statistics")
async def get_statistics(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's learning statistics and weak visemes"""
    from database import Progress, WeakViseme
    from sqlalchemy import select, func

    # Get total practice sessions
    total_sessions = await db.execute(
        select(func.count(Progress.id)).where(Progress.user_id == current_user.id)
    )
    total_count = total_sessions.scalar()

    # Get average score
    avg_score = await db.execute(
        select(func.avg(Progress.score)).where(Progress.user_id == current_user.id)
    )
    average = avg_score.scalar() or 0

    # Get weak visemes
    weak_visemes_query = await db.execute(
        select(WeakViseme)
        .where(WeakViseme.user_id == current_user.id)
        .order_by(WeakViseme.error_count.desc())
        .limit(5)
    )
    weak_visemes = weak_visemes_query.scalars().all()

    return {
        "total_sessions": total_count,
        "average_score": round(average, 2),
        "current_level": current_user.current_level,
        "total_xp": current_user.total_xp,
        "weak_visemes": [
            {
                "viseme_id": wv.viseme_id,
                "error_rate": round(wv.error_count / wv.total_attempts * 100, 1) if wv.total_attempts > 0 else 0,
                "feature": VISEME_GROUP_NAMES.get(wv.viseme_id, wv.phonological_feature or f"viseme {wv.viseme_id}")
            }
            for wv in weak_visemes
        ]
    }


# ============================================
# Static File Serving (Production)
# ============================================

# Serve React app static files
# ============================================
# Bookmark Endpoints
# ============================================

class BookmarkCreate(BaseModel):
    sentence: str
    situation: str = ""
    level: int = 1


@app.get("/api/bookmarks")
async def list_bookmarks(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from database import Bookmark
    from sqlalchemy import select
    result = await db.execute(
        select(Bookmark).where(Bookmark.user_id == current_user.id).order_by(Bookmark.created_at.desc())
    )
    items = result.scalars().all()
    return [{"id": b.id, "sentence": b.sentence, "situation": b.situation, "level": b.level} for b in items]


@app.post("/api/bookmarks", status_code=201)
async def add_bookmark(data: BookmarkCreate, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from database import Bookmark
    from sqlalchemy import select
    existing = await db.execute(
        select(Bookmark).where(Bookmark.user_id == current_user.id, Bookmark.sentence == data.sentence)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already bookmarked")
    bm = Bookmark(user_id=current_user.id, sentence=data.sentence, situation=data.situation, level=data.level)
    db.add(bm)
    await db.commit()
    await db.refresh(bm)
    return {"id": bm.id, "sentence": bm.sentence, "situation": bm.situation, "level": bm.level}


@app.delete("/api/bookmarks/{bookmark_id}")
async def remove_bookmark(bookmark_id: int, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from database import Bookmark
    from sqlalchemy import select
    result = await db.execute(
        select(Bookmark).where(Bookmark.id == bookmark_id, Bookmark.user_id == current_user.id)
    )
    bm = result.scalar_one_or_none()
    if not bm:
        raise HTTPException(status_code=404, detail="Bookmark not found")
    await db.delete(bm)
    await db.commit()
    return {"deleted": True}


# ============================================
# Analysis Endpoint
# ============================================

VISEME_GROUP_NAMES = {
    1: "양순음 (ㅂ/ㅍ/ㅁ)",
    2: "개방모음 (ㅏ/ㅐ)",
    3: "전설모음 (ㅣ/ㅔ)",
    4: "원순모음 (ㅗ/ㅜ)",
    5: "중설모음 (ㅓ/ㅡ)",
    6: "치경음 (ㄷ/ㄴ/ㄹ/ㅅ)",
    7: "연구개음 (ㄱ/ㅇ)",
    8: "성문음 (ㅎ)",
    9: "이중모음",
    10: "경구개음 (ㅈ/ㅊ)",
}


@app.get("/api/analysis")
async def get_analysis(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from database import Progress
    from sqlalchemy import select, func
    import traceback

    try:
        # Total sessions & average score
        total_q = await db.execute(select(func.count(Progress.id)).where(Progress.user_id == current_user.id))
        total = total_q.scalar() or 0
        avg_q = await db.execute(select(func.avg(Progress.score)).where(Progress.user_id == current_user.id))
        avg_score = float(avg_q.scalar() or 0)

        progress_q = await db.execute(
            select(Progress)
            .where(Progress.user_id == current_user.id)
            .order_by(Progress.created_at.desc())
            .limit(100)
        )
        all_progress = progress_q.scalars().all()

        # viseme_id -> list of session scores
        viseme_score_map: dict = {}
        for prog in all_progress:
            try:
                if not prog.sentence:
                    continue
                frames = await text_to_visemes(prog.sentence)
                sentence_visemes = {f["viseme"] for f in frames if 1 <= f["viseme"] <= 10}
                for v in sentence_visemes:
                    viseme_score_map.setdefault(v, []).append(prog.score)
            except Exception as e:
                print(f"[WARN] viseme scoring failed for sentence '{prog.sentence}': {e}")
                continue

        viseme_stats = []
        for v_id, scores in viseme_score_map.items():
            if v_id not in VISEME_GROUP_NAMES:
                continue
            avg_accuracy = round(sum(scores) / len(scores), 1)
            viseme_stats.append({
                "viseme_id": v_id,
                "name": VISEME_GROUP_NAMES[v_id],
                "accuracy": avg_accuracy,
                "attempts": len(scores),
                "errors": sum(1 for s in scores if s < 60),
            })

        viseme_stats.sort(key=lambda x: x["accuracy"])
        strengths = [s for s in viseme_stats if s["accuracy"] >= 70][-3:]
        weaknesses = [s for s in viseme_stats if s["accuracy"] < 70][:3]

        # Phoneme confusion analysis
        from scoring import extract_jamo_sequence
        confusion_map: dict = {}
        for prog in all_progress:
            try:
                if prog.score >= 80 or not prog.sentence:
                    continue
                c_jamos = extract_jamo_sequence(prog.sentence.replace(" ", ""))
                u_jamos = extract_jamo_sequence((prog.user_answer or "").replace(" ", ""))
                for i in range(min(len(c_jamos), len(u_jamos))):
                    c_i, c_m, _ = c_jamos[i]
                    u_i, u_m, _ = u_jamos[i]
                    if c_i and u_i and c_i != u_i:
                        key = (c_i, u_i)
                        confusion_map[key] = confusion_map.get(key, 0) + 1
                    if c_m and u_m and c_m != u_m:
                        key = (c_m, u_m)
                        confusion_map[key] = confusion_map.get(key, 0) + 1
            except Exception as e:
                print(f"[WARN] confusion analysis failed: {e}")
                continue

        top_confusions = sorted(confusion_map.items(), key=lambda x: -x[1])[:8]
        confusions = [{"correct": k[0], "confused_as": k[1], "count": v} for k, v in top_confusions]

        analysis_data = {
            "total_sessions": total,
            "average_score": round(avg_score, 1),
            "strengths": strengths,
            "weaknesses": weaknesses,
            "viseme_stats": viseme_stats,
            "confusions": confusions,
        }

        # Generate AI recommendation only if enough data
        recommendation = ""
        if total >= 3:
            recommendation = await generate_analysis_recommendation(analysis_data)
        else:
            recommendation = "아직 데이터가 부족합니다. 테스트를 3회 이상 완료하면 맞춤형 분석을 받을 수 있어요!"

        return {**analysis_data, "recommendation": recommendation}

    except Exception as e:
        print(f"[ERROR] get_analysis failed: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"분석 데이터 로드 실패: {str(e)}")


@app.delete("/api/analysis/reset")
async def reset_analysis(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Clear all practice history for the current user to start fresh."""
    from database import Progress, WeakViseme
    from sqlalchemy import delete as sql_delete
    await db.execute(sql_delete(WeakViseme).where(WeakViseme.user_id == current_user.id))
    await db.execute(sql_delete(Progress).where(Progress.user_id == current_user.id))
    await db.commit()
    return {"reset": True}


@app.get("/api/calendar")
async def get_calendar(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Return daily session counts for the past 90 days as { 'YYYY-MM-DD': count }"""
    from database import Progress
    from sqlalchemy import select, func
    import datetime as dt

    cutoff = (dt.date.today() - dt.timedelta(days=90)).isoformat()
    result = await db.execute(
        select(
            func.date(Progress.created_at).label("day"),
            func.count(Progress.id).label("cnt"),
        )
        .where(Progress.user_id == current_user.id)
        .where(Progress.created_at >= cutoff)
        .group_by(func.date(Progress.created_at))
    )
    return {row.day: row.cnt for row in result.all()}


@app.get("/api/review-sentences")
async def get_review_sentences(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Return up to 10 distinct sentences the user got wrong (score < 60)."""
    from database import Progress
    from sqlalchemy import select

    result = await db.execute(
        select(Progress)
        .where(Progress.user_id == current_user.id)
        .where(Progress.score < 60)
        .order_by(Progress.score.asc(), Progress.created_at.desc())
        .limit(30)
    )
    records = result.scalars().all()
    seen: set = set()
    unique = []
    for p in records:
        if p.sentence not in seen:
            seen.add(p.sentence)
            unique.append({
                "sentence": p.sentence,
                "situation": p.situation,
                "difficulty_level": p.difficulty_level,
                "score": round(p.score, 1),
            })
        if len(unique) >= 10:
            break
    return unique


# ============================================
# Curriculum (단계형 커리큘럼) — 재설계 Phase 1
# ============================================
import curriculum as _curriculum

_STAGE1_MIN_ATTEMPTS = 8       # 숙달 판정 최소 시도
_STAGE1_MASTERY = 70.0         # 숙달 판정 정확도(%)
_STAGE2_MIN_ATTEMPTS = 6
_STAGE2_MASTERY = 70.0
# 3·4단계는 점수(0~100)를 내는 활동이라 'PASS 이상이면 성공 1회'로 환산해 누적한다.
_STAGE3_MIN_ATTEMPTS = 5       # 문장 연습
_STAGE3_MASTERY = 65.0
_STAGE3_PASS = 60.0            # 문장 1건을 '성공'으로 볼 최소 점수
_STAGE4_MIN_ATTEMPTS = 4       # 대화 실전
_STAGE4_MASTERY = 60.0
_STAGE4_PASS = 55.0            # 대화 1턴을 '성공'으로 볼 최소 이해도


async def _bump_stage_progress(user_id: int, stage: int, passed: bool,
                               min_attempts: int, mastery_pct: float, db):
    """단계별 진행률 rolling 갱신(1건 채점 → 시도·정답 누적, 숙달 판정). sp 반환.
    커밋은 호출부에서 다른 갱신과 함께 처리한다."""
    from database import StageProgress
    from sqlalchemy import select
    r = await db.execute(select(StageProgress).where(
        StageProgress.user_id == user_id, StageProgress.stage == stage))
    sp = r.scalar_one_or_none()
    if sp is None:
        # default=0은 flush 시점 적용 → 즉시 증감하려면 초기값 명시
        sp = StageProgress(user_id=user_id, stage=stage, status="in_progress",
                           attempts=0, correct=0, mastery_score=0.0)
        db.add(sp)
    sp.attempts += 1
    if passed:
        sp.correct += 1
    sp.mastery_score = (sp.correct / sp.attempts * 100) if sp.attempts else 0.0
    sp.status = "mastered" if (sp.attempts >= min_attempts and sp.mastery_score >= mastery_pct) else "in_progress"
    return sp

from datetime import date as _sr_date, timedelta as _sr_delta


async def _srs_schedule_wrong(user_id: int, kind: str, ref, db: AsyncSession):
    """오답 → 내일 복습 예약(SRS). 기존 항목이면 간격 리셋. commit은 호출부에서."""
    from database import ReviewItem
    from sqlalchemy import select
    tomorrow = (_sr_date.today() + _sr_delta(days=1)).isoformat()
    r = await db.execute(select(ReviewItem).where(
        ReviewItem.user_id == user_id, ReviewItem.kind == kind, ReviewItem.ref == str(ref)))
    item = r.scalar_one_or_none()
    if item is None:
        db.add(ReviewItem(user_id=user_id, kind=kind, ref=str(ref), due_date=tomorrow, interval_days=1))
    else:
        item.interval_days = 1
        item.due_date = tomorrow


async def _get_or_create_profile(user_id: int, db: AsyncSession):
    from database import LearningProfile
    from sqlalchemy import select
    r = await db.execute(select(LearningProfile).where(LearningProfile.user_id == user_id))
    prof = r.scalar_one_or_none()
    if prof is None:
        prof = LearningProfile(user_id=user_id)
        db.add(prof)
        await db.commit()
        await db.refresh(prof)
    return prof


@app.get("/api/curriculum/stages")
async def curriculum_stages(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """단계형 학습 경로 + 사용자별 상태(대시보드/오늘의 학습 구동)."""
    from database import StageProgress
    from sqlalchemy import select

    prof = await _get_or_create_profile(current_user.id, db)
    r = await db.execute(select(StageProgress).where(StageProgress.user_id == current_user.id))
    sp_map = {sp.stage: sp for sp in r.scalars().all()}

    stages = []
    for s in _curriculum.STAGES:
        st = dict(s)
        stage = s["stage"]
        if s.get("coming_soon"):
            st["status"] = "coming_soon"
        elif stage == 0:
            st["status"] = "mastered" if prof.placed else "unlocked"
        elif stage == 1:
            sp = sp_map.get(1)
            if not prof.placed:
                st["status"] = "locked"
            elif sp is None:
                st["status"] = "unlocked"
            else:
                st["status"] = sp.status
                st["mastery_score"] = round(sp.mastery_score, 1)
                st["attempts"] = sp.attempts
        else:  # 2·3·4단계 — 직전 단계를 숙달해야 순차 해금
            prev = sp_map.get(stage - 1)
            sp = sp_map.get(stage)
            if not (prev is not None and prev.status == "mastered"):
                st["status"] = "locked"        # 전 단계 숙달 후 열림
            elif sp is None:
                st["status"] = "unlocked"
            else:
                st["status"] = sp.status
                st["mastery_score"] = round(sp.mastery_score, 1)
                st["attempts"] = sp.attempts
        stages.append(st)

    return {"track": prof.track, "placed": prof.placed,
            "current_stage": prof.current_stage, "stages": stages}


class TrackSelect(BaseModel):
    track: str  # 'perception' | 'language'


@app.post("/api/curriculum/track")
async def curriculum_set_track(data: TrackSelect, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """배치: 트랙 선택 → 1단계(입모양 인지) 잠금 해제."""
    if data.track not in ("perception", "language"):
        raise HTTPException(status_code=400, detail="track must be 'perception' or 'language'")
    prof = await _get_or_create_profile(current_user.id, db)
    prof.track = data.track
    prof.placed = True
    prof.current_stage = max(prof.current_stage or 0, 1)
    await db.commit()
    return {"track": prof.track, "placed": prof.placed, "current_stage": prof.current_stage}


@app.post("/api/curriculum/track/reset")
async def curriculum_reset_track(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """배치 취소: 트랙 선택 화면으로 되돌아가기(진행 데이터는 보존)."""
    prof = await _get_or_create_profile(current_user.id, db)
    prof.placed = False
    await db.commit()
    return {"track": prof.track, "placed": prof.placed, "current_stage": prof.current_stage}


@app.get("/api/curriculum/viseme-lessons")
async def curriculum_viseme_lessons(current_user=Depends(get_current_user)):
    """1단계 콘텐츠: 입모양 10그룹 레슨 + 동구형이음 무리 + 최소대립쌍."""
    lessons = []
    for l in _curriculum.VISEME_LESSONS:
        lessons.append({
            **l,
            "demo_syllable": _curriculum.DEMO_SYLLABLE.get(l["viseme_id"]),
            "quizzable": l["visibility"] != "low",
            "homophene_cluster": (_curriculum.homophene_cluster_of(l["viseme_id"]) or {}).get("id"),
        })
    return {
        "lessons": lessons,
        "homophene_clusters": _curriculum.HOMOPHENE_CLUSTERS,
        "minimal_pairs": _curriculum.MINIMAL_PAIRS,
        "anchors": _curriculum.VISIBLE_ANCHORS,
    }


class RecognitionSubmit(BaseModel):
    viseme_id: int   # 제시된(정답) 그룹
    chosen_id: int   # 사용자가 고른 그룹


@app.post("/api/curriculum/recognition")
async def curriculum_recognition(data: RecognitionSubmit, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """입모양 인지퀴즈 채점 + 1단계 숙달 갱신 + 취약 입모양(WeakViseme) 통합 반영."""
    from database import StageProgress, WeakViseme
    from sqlalchemy import select
    from datetime import datetime as _dt

    target = _curriculum.lesson_by_id(data.viseme_id)
    if target is None:
        raise HTTPException(status_code=400, detail="invalid viseme_id")
    correct = (data.viseme_id == data.chosen_id)
    # '같아 보이는 무리'로 틀렸는지 — 동구형이음 학습 취지의 피드백용
    same_cluster = _curriculum.same_homophene_cluster(data.viseme_id, data.chosen_id)

    try:
        # 1단계 진행/숙달 갱신
        r = await db.execute(select(StageProgress).where(
            StageProgress.user_id == current_user.id, StageProgress.stage == 1))
        sp = r.scalar_one_or_none()
        if sp is None:
            # default=0은 flush 시점에 적용되므로 즉시 증감하려면 초기값을 명시한다
            sp = StageProgress(user_id=current_user.id, stage=1, status="in_progress",
                               attempts=0, correct=0, mastery_score=0.0)
            db.add(sp)
        sp.attempts += 1
        if correct:
            sp.correct += 1
        sp.mastery_score = (sp.correct / sp.attempts * 100) if sp.attempts else 0.0
        sp.status = "mastered" if (sp.attempts >= _STAGE1_MIN_ATTEMPTS and sp.mastery_score >= _STAGE1_MASTERY) else "in_progress"

        # 취약 입모양 반영 — 기존 분석·적응 로직과 통합
        r2 = await db.execute(select(WeakViseme).where(
            WeakViseme.user_id == current_user.id, WeakViseme.viseme_id == data.viseme_id))
        wv = r2.scalar_one_or_none()
        if wv is None:
            wv = WeakViseme(user_id=current_user.id, viseme_id=data.viseme_id,
                            error_count=0, total_attempts=0, phonological_feature=target["name"])
            db.add(wv)
        wv.total_attempts += 1
        if not correct:
            wv.error_count += 1
            wv.last_error_at = _dt.utcnow()
            await _srs_schedule_wrong(current_user.id, "viseme", str(data.viseme_id), db)

        await db.commit()
        await db.refresh(sp)
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"recognition submit failed: {str(e)}")

    return {
        "correct": correct,
        "same_cluster": same_cluster,
        "target": {"viseme_id": data.viseme_id, "name": target["name"], "teach": target["teach"]},
        "mastery_score": round(sp.mastery_score, 1),
        "attempts": sp.attempts,
        "mastered": sp.status == "mastered",
    }


class WordAnswer(BaseModel):
    word: str
    correct: bool


@app.get("/api/curriculum/words")
async def curriculum_words(current_user=Depends(get_current_user)):
    """2단계 콘텐츠: 큐레이션 단어 은행 + 최소대립쌍(프론트가 단어 퀴즈를 구성)."""
    return {"words": _curriculum.WORD_BANK, "minimal_pairs": _curriculum.MINIMAL_PAIRS}


@app.post("/api/curriculum/word-answer")
async def curriculum_word_answer(data: WordAnswer, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """단어 인식 채점 → 2단계 숙달 갱신 + 오답 시 SRS 예약."""
    if not _curriculum.is_word(data.word):
        raise HTTPException(status_code=400, detail="unknown word")
    from database import StageProgress
    from sqlalchemy import select
    try:
        r = await db.execute(select(StageProgress).where(
            StageProgress.user_id == current_user.id, StageProgress.stage == 2))
        sp = r.scalar_one_or_none()
        if sp is None:
            sp = StageProgress(user_id=current_user.id, stage=2, status="in_progress",
                               attempts=0, correct=0, mastery_score=0.0)
            db.add(sp)
        sp.attempts += 1
        if data.correct:
            sp.correct += 1
        sp.mastery_score = (sp.correct / sp.attempts * 100) if sp.attempts else 0.0
        sp.status = "mastered" if (sp.attempts >= _STAGE2_MIN_ATTEMPTS and sp.mastery_score >= _STAGE2_MASTERY) else "in_progress"
        if not data.correct:
            await _srs_schedule_wrong(current_user.id, "word", data.word, db)
        await db.commit()
        await db.refresh(sp)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"word answer failed: {str(e)}")
    return {"mastery_score": round(sp.mastery_score, 1), "attempts": sp.attempts, "mastered": sp.status == "mastered"}


# ── 간격 반복 복습 (SRS) ──────────────────────────────────────────────────
@app.get("/api/review/due")
async def review_due(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """오늘까지 복습 예정인 항목(입모양/단어)."""
    from database import ReviewItem
    from sqlalchemy import select
    today = _sr_date.today().isoformat()
    r = await db.execute(select(ReviewItem).where(
        ReviewItem.user_id == current_user.id, ReviewItem.due_date <= today).order_by(ReviewItem.due_date))
    items = r.scalars().all()
    out = []
    for it in items:
        entry = {"kind": it.kind, "ref": it.ref}
        if it.kind == "viseme" and it.ref.isdigit():
            les = _curriculum.lesson_by_id(int(it.ref))
            if les:
                entry["name"] = les["name"]
        out.append(entry)
    return {"count": len(out), "items": out}


class ReviewAnswer(BaseModel):
    kind: str
    ref: str
    correct: bool


@app.post("/api/review/answer")
async def review_answer(data: ReviewAnswer, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """복습 결과로 다음 등장일 재조정(정답=간격 2배, 오답=내일). 간격이 충분히 커지면 졸업(제거)."""
    from database import ReviewItem
    from sqlalchemy import select
    r = await db.execute(select(ReviewItem).where(
        ReviewItem.user_id == current_user.id, ReviewItem.kind == data.kind, ReviewItem.ref == data.ref))
    item = r.scalar_one_or_none()
    if item is None:
        return {"ok": True, "removed": False}
    if data.correct:
        new_interval = min((item.interval_days or 1) * 2, 32)
        if new_interval >= 32:
            await db.delete(item)          # 졸업 — 큐에서 제거
            await db.commit()
            return {"ok": True, "removed": True}
        item.interval_days = new_interval
        item.due_date = (_sr_date.today() + _sr_delta(days=new_interval)).isoformat()
    else:
        item.interval_days = 1
        item.due_date = (_sr_date.today() + _sr_delta(days=1)).isoformat()
    await db.commit()
    return {"ok": True, "removed": False, "next_due": item.due_date, "interval_days": item.interval_days}


# ── 3단계 문맥 추론(closure) + 대화 채점 + 적응형 난이도(Phase 3·4) ──────────
@app.get("/api/curriculum/closure")
async def curriculum_closure(current_user=Depends(get_current_user)):
    """문맥 추론 항목(빈칸+비슷하게 보이는 보기). 눈으로 구별 안 되니 문맥으로 답을 고른다."""
    return {"items": _curriculum.CLOSURE_ITEMS}


class ScoreRequest(BaseModel):
    correct: str
    user_answer: str


@app.post("/api/score")
async def score_answer(data: ScoreRequest, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """임의 문장 채점(대화 이해도 등) — 기존 음운 유사도 엔진 재사용.
    대화 실전에서 호출되므로 4단계 숙달도 함께 갱신한다."""
    try:
        r = await calculate_score(correct=data.correct, user_answer=data.user_answer, db=db)
        score = round(r.get("score", 0), 1)
        # 4단계(대화 실전) 숙달 갱신 — 이해도 PASS 이상이면 성공 1회로 누적
        await _bump_stage_progress(
            current_user.id, 4, score >= _STAGE4_PASS,
            _STAGE4_MIN_ATTEMPTS, _STAGE4_MASTERY, db)
        await db.commit()
        return {"score": score, "feedback": r.get("feedback", {}), "phoneme_accuracy": r.get("phoneme_accuracy", {})}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"score failed: {str(e)}")


@app.get("/api/curriculum/recommended-level")
async def recommended_level(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """최근 문장 연습 정확도로 다음 난이도를 추천(적응형)."""
    from database import Progress
    from sqlalchemy import select
    r = await db.execute(
        select(Progress.score, Progress.difficulty_level)
        .where(Progress.user_id == current_user.id)
        .order_by(Progress.created_at.desc()).limit(10))
    rows = r.all()
    if not rows:
        base = min(max(current_user.current_level or 1, 1), 5)
        return {"recommended_level": base, "recent_avg": None, "sample": 0, "reason": "아직 기록이 없어 기본값을 추천해요"}
    avg = sum(x[0] for x in rows) / len(rows)
    practiced = rows[0][1] or (current_user.current_level or 1)
    if avg >= 82:
        lvl, reason = min(practiced + 1, 5), "최근 정확도가 높아 한 단계 올렸어요"
    elif avg <= 55:
        lvl, reason = max(practiced - 1, 1), "최근 정확도가 낮아 한 단계 내렸어요"
    else:
        lvl, reason = min(max(practiced, 1), 5), "지금 난이도가 적당해요"
    return {"recommended_level": lvl, "recent_avg": round(avg, 1), "sample": len(rows), "reason": reason}


# ── 발화 커리큘럼(6단계) — 상태·게이팅·콘텐츠 ────────────────────────────────
import speak_curriculum as _speakcur


async def _bump_speak_progress(user_id: int, stage: int, passed: bool,
                               min_attempts: int, mastery_pct: float, db):
    """발화 단계 진행률 rolling 갱신(읽기 _bump_stage_progress의 발화판). sp 반환."""
    from database import SpeakStageProgress
    from sqlalchemy import select
    r = await db.execute(select(SpeakStageProgress).where(
        SpeakStageProgress.user_id == user_id, SpeakStageProgress.stage == stage))
    sp = r.scalar_one_or_none()
    if sp is None:
        sp = SpeakStageProgress(user_id=user_id, stage=stage, status="in_progress",
                                attempts=0, correct=0, mastery_score=0.0)
        db.add(sp)
    sp.attempts += 1
    if passed:
        sp.correct += 1
    sp.mastery_score = (sp.correct / sp.attempts * 100) if sp.attempts else 0.0
    sp.status = "mastered" if (sp.attempts >= min_attempts and sp.mastery_score >= mastery_pct) else "in_progress"
    return sp


@app.get("/api/speak/curriculum")
async def speak_curriculum_stages(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """발화 6단계 + 사용자 상태. 게이팅: 0단계 항상 열림, N단계는 N-1 숙달 시 해금."""
    from database import SpeakStageProgress
    from sqlalchemy import select
    r = await db.execute(select(SpeakStageProgress).where(SpeakStageProgress.user_id == current_user.id))
    sp_map = {sp.stage: sp for sp in r.scalars().all()}
    stages = []
    for meta in _speakcur.stages_overview():
        st = dict(meta)
        n = meta["stage"]
        sp = sp_map.get(n)
        if n == 0:
            base_open = True
        else:
            prev = sp_map.get(n - 1)
            base_open = prev is not None and prev.status == "mastered"
        if not base_open:
            st["status"] = "locked"
        elif sp is None:
            st["status"] = "unlocked"
        else:
            st["status"] = sp.status
            st["mastery_score"] = round(sp.mastery_score, 1)
            st["attempts"] = sp.attempts
        stages.append(st)
    return {"stages": stages}


@app.get("/api/speak/stage/{n}")
async def speak_stage_content(n: int, current_user=Depends(get_current_user)):
    """단계 콘텐츠(항목·모드·가이드)."""
    stg = _speakcur.get_stage(n)
    if not stg:
        raise HTTPException(status_code=404, detail="unknown stage")
    return {
        "stage": stg["stage"], "title": stg["title"], "mode": stg["mode"],
        "desc": stg["desc"], "guide": stg["guide"], "icon": stg.get("icon", ""),
        "items": stg["items"],
    }


# ── 발화(말하기) 채점 — 단계 모드별 채점 + 진행률 + 코칭 ──────────────────────
@app.post("/api/speak/assess")
async def speak_assess(
    target: str = Form(...),
    audio: UploadFile = File(...),
    loudness: float = Form(0.0),
    pitch_range: float = Form(0.0),
    duration: float = Form(0.0),
    pitch_start: float = Form(0.0),
    pitch_end: float = Form(0.0),
    stage: int = Form(None),
    drill: str = Form(None),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """녹음 → (단계 모드에 따라) 지표/전사 채점 → 진행률 갱신 → 코칭.
    발성·운율(0·1)은 지표만으로, 모음·자음·단어·문장(2~5)은 Whisper 전사+음운 유사도."""
    data = await audio.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty audio")

    metrics = {"loudness": loudness, "pitch_range": pitch_range, "duration": duration,
               "pitch_start": pitch_start, "pitch_end": pitch_end}
    stg = _speakcur.get_stage(stage) if stage is not None else None
    mode = stg["mode"] if stg else "word"

    transcript = None
    confusions = []
    sim = None
    need_asr = (mode in ("phoneme", "word", "sentence")) or (stage is None)
    if need_asr:
        from speak_service import transcribe, is_available
        if not is_available():
            raise HTTPException(status_code=503, detail="서버에 음성인식 모델(faster-whisper)이 없습니다.")
        try:
            transcript = await transcribe(data)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"전사 실패: {str(e)}")
        try:
            sc = await calculate_score(correct=target, user_answer=transcript, db=db)
            sim = sc.get("score", 0)
        except Exception:
            sim = 0.0
        try:
            from scoring import extract_jamo_sequence
            cj = extract_jamo_sequence(target.replace(" ", ""))
            uj = extract_jamo_sequence((transcript or "").replace(" ", ""))
            for i in range(min(len(cj), len(uj))):
                ci, cm, _ = cj[i]
                ui, um, _ = uj[i]
                if ci and ui and ci != ui:
                    confusions.append({"correct": ci, "confused_as": ui})
                if cm and um and cm != um:
                    confusions.append({"correct": cm, "confused_as": um})
        except Exception:
            pass

    note = ""
    passed = None
    progress = None
    if stage is not None and stg is not None:
        score, passed, note = _speakcur.score_attempt(stage, target, transcript, metrics, drill, sim)
        sp = await _bump_speak_progress(current_user.id, stage, bool(passed),
                                        stg["min_attempts"], stg["mastery"], db)
    else:
        score = round(sim or 0.0, 1)
        sp = None

    # 개별 시도 영속화(말하기 분석용 — 독화가 Progress에 쌓는 것과 대칭)
    from database import SpeakAttempt
    db.add(SpeakAttempt(
        user_id=current_user.id, stage=stage, mode=mode, target=target,
        transcript=transcript, score=score, passed=passed,
        loudness=loudness, pitch_range=pitch_range, duration=duration,
        pitch_start=pitch_start, pitch_end=pitch_end, confusions=confusions[:6],
    ))
    await db.commit()
    if sp is not None:
        progress = {"stage": stage, "attempts": sp.attempts,
                    "mastery_score": round(sp.mastery_score, 1),
                    "mastered": sp.status == "mastered"}

    # 발성·운율은 규칙 기반 note가 곧 구체 코칭, 모음~문장은 Claude 코칭(+억양 note)
    if mode in ("voicing", "prosody"):
        coaching = note
    else:
        from llm_service import generate_speaking_coaching
        coaching = await generate_speaking_coaching(target, transcript, score, confusions, metrics)
        if note:
            coaching = f"{coaching} {note}"

    return {
        "transcript": transcript,
        "score": score,
        "passed": passed,
        "note": note,
        "confusions": confusions[:6],
        "coaching": coaching,
        "metrics": metrics,
        "progress": progress,
        "mode": mode,
    }


@app.get("/api/speak/analysis")
async def speak_analysis(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """말하기(발화) 분석 — 독화 분석과 분리. 자주 틀리는 소리·억양/크기 추세·단계 숙달."""
    from database import SpeakAttempt, SpeakStageProgress
    from sqlalchemy import select
    from collections import Counter

    rows = (await db.execute(
        select(SpeakAttempt).where(SpeakAttempt.user_id == current_user.id)
        .order_by(SpeakAttempt.created_at.desc()).limit(200))).scalars().all()
    total = len(rows)
    avg = round(sum(r.score for r in rows) / total, 1) if total else 0.0

    # 자주 틀리는 소리 — 음소 혼동 집계
    conf = Counter()
    for r in rows:
        for c in (r.confusions or []):
            key = (c.get("correct"), c.get("confused_as"))
            if key[0] and key[1]:
                conf[key] += 1
    weak_sounds = [{"correct": k[0], "confused_as": k[1], "count": v} for k, v in conf.most_common(6)]

    # 억양·크기 — 발성이 있었던 시도 평균 + 최근 추세
    voiced = [r for r in rows if r.loudness]
    avg_loud = round(sum(r.loudness for r in voiced) / len(voiced), 1) if voiced else 0.0
    avg_range = round(sum(r.pitch_range for r in voiced) / len(voiced), 1) if voiced else 0.0
    recent = list(reversed(rows[:12]))
    trend = [{"loudness": round(r.loudness, 1), "pitch_range": round(r.pitch_range, 1),
              "score": round(r.score, 1)} for r in recent]

    # 단계별 숙달
    sp_rows = (await db.execute(select(SpeakStageProgress)
               .where(SpeakStageProgress.user_id == current_user.id))).scalars().all()
    sp_map = {sp.stage: sp for sp in sp_rows}
    stages = []
    for meta in _speakcur.stages_overview():
        sp = sp_map.get(meta["stage"])
        stages.append({"stage": meta["stage"], "title": meta["title"], "icon": meta.get("icon", ""),
                       "mastery_score": round(sp.mastery_score, 1) if sp else 0.0,
                       "attempts": sp.attempts if sp else 0,
                       "status": sp.status if sp else ("unlocked" if meta["stage"] == 0 else "locked")})

    tips = []
    if weak_sounds:
        w = weak_sounds[0]
        tips.append(f"'{w['correct']}' 소리를 '{w['confused_as']}'로 내는 경우가 많아요. 그 입모양·조음을 다시 연습해보세요.")
    if voiced and avg_loud < 40:
        tips.append("전반적으로 목소리가 작은 편이에요(크기 %d/100). 배에 힘을 주고 크게 내보세요." % round(avg_loud))
    if voiced and avg_range < 25:
        tips.append("억양이 평평한 편이에요(폭 %dHz). 문장 끝을 올리고 내리며 억양을 넣어보세요." % round(avg_range))
    if not tips:
        tips.append("좋아요! 지금처럼 단계 연습을 꾸준히 이어가세요.")

    return {"total": total, "avg_score": avg, "weak_sounds": weak_sounds,
            "avg_loudness": avg_loud, "avg_pitch_range": avg_range, "trend": trend,
            "stages": stages, "tips": tips}


@app.get("/api/speak/review")
async def speak_review(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """발음 복습 — 최근 발화에서 틀렸거나 저조했던 단어/문장을 다시 연습 큐로.
    동적 계산: 각 target의 가장 최근 시도가 실패/저조(<70)면 복습 대상, 이후 잘하면 자동 제외.
    (발음은 운동 기억이라 '틀린 항목 반복'이 핵심 — 독화 SRS의 발화판)"""
    from database import SpeakAttempt
    from sqlalchemy import select
    rows = (await db.execute(
        select(SpeakAttempt).where(SpeakAttempt.user_id == current_user.id)
        .order_by(SpeakAttempt.created_at.desc()).limit(300))).scalars().all()
    seen = {}
    for r in rows:
        if r.mode not in ("phoneme", "word", "sentence") or not r.target:
            continue
        if r.target in seen:
            continue  # desc 정렬 → 각 target의 첫 등장이 최신 시도
        seen[r.target] = r
    items = []
    for t, r in seen.items():
        if (r.passed is False) or (r.score is not None and r.score < 70):
            items.append({"target": t, "stage": r.stage, "mode": r.mode,
                          "last_score": round(r.score or 0, 1)})
    items.sort(key=lambda x: x["last_score"])
    return {"items": items[:15], "count": len(items)}


class ConversationRequest(BaseModel):
    situation: str
    level: int = 1
    history: List[dict] = []


class ConversationResponse(BaseModel):
    text: str


@app.post("/api/conversation", response_model=ConversationResponse)
async def conversation_turn(
    request: ConversationRequest,
    current_user = Depends(get_current_user)
):
    """
    Generate one turn of dialogue for conversation practice mode.
    """
    if request.level < 1 or request.level > 5:
        raise HTTPException(status_code=400, detail="Level must be 1-5")
    try:
        result = await generate_conversation_turn(
            situation=request.situation,
            level=request.level,
            history=request.history
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conversation generation failed: {str(e)}")


class SignRequest(BaseModel):
    text: str


@app.post("/api/sign/translate")
async def sign_translate(
    request: SignRequest,
    current_user = Depends(get_current_user)
):
    """
    한국어 문장을 한국수어(KSL) 학습 보조 시퀀스로 변환.
    Stage A(Claude gloss 번역) → Stage B(국립국어원 사전 조회 + 지문자 폴백) + 입모양.
    학습·이해 보조용이며 통역 서비스가 아니다.
    """
    text = (request.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    if len(text) > 200:
        raise HTTPException(status_code=400, detail="text too long (max 200)")
    try:
        from sign_service import translate_to_ksl
        return await translate_to_ksl(text)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sign translation failed: {str(e)}")


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    return {
        "status": "healthy",
        "service": "LIPLAB API",
        "version": "1.0.0"
    }


# ============================================
# Static file serving (must be LAST — catch-all would shadow API routes above)
# ============================================
frontend_dist = os.path.join(os.path.dirname(__file__), "frontend", "dist")

if os.path.exists(frontend_dist):
    # Mount static assets
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")

    # Serve index.html for all non-API routes (SPA routing)
    @app.get("/{full_path:path}")
    async def serve_react_app(full_path: str):
        """Serve React app for all non-API routes"""
        # Don't serve for API routes
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API endpoint not found")

        # Check if requesting a specific file
        file_path = os.path.join(frontend_dist, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)

        # Default to index.html for SPA routing
        index_path = os.path.join(frontend_dist, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)

        raise HTTPException(status_code=404, detail="File not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        reload=False
    )
