"""
LIPLAB FastAPI Main Application
Serves API endpoints and React static files for production deployment
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status
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
