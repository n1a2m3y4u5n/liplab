"""
LIPLAB FastAPI Main Application
Serves API endpoints and React static files for production deployment
"""
import os
import asyncio
import logging
import ratelimit
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
# 와일드카드(*)+credentials 조합은 임의 사이트가 자격증명 요청을 보낼 수 있어 금지한다.
# ALLOWED_ORIGINS(쉼표구분)로 화이트리스트를 주면 그 출처만 허용, 미설정 시 개발용 localhost만.
_origins_env = os.getenv("ALLOWED_ORIGINS", "").strip()
if _origins_env:
    _allow_origins = [o.strip() for o in _origins_env.split(",") if o.strip()]
    _allow_credentials = True
else:
    _allow_origins = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8080"]
    _allow_credentials = False  # 앱은 Bearer 토큰(헤더) 인증이라 쿠키 credentials 불필요
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


from fastapi.responses import JSONResponse as _JSONResponse

@app.exception_handler(Exception)
async def _unhandled_exception(request, exc):
    logging.getLogger("liplab").exception("unhandled: %s %s", request.method, request.url.path)
    return _JSONResponse(status_code=500, content={"detail": "서버 오류가 발생했습니다."})


# 보안 응답 헤더(§4.9) — 다운그레이드·MIME 스니핑·클릭재킹·레퍼러 유출 방어.
# 자원 로딩을 제한하는 script/style/connect-src 류 CSP는 이 앱이 SPA(/assets·MediaPipe CDN·모델)를
# 함께 서빙해 잘못 좁히면 깨진다 → 정책 수립·검증 전까지 보류. 다만 자원 로딩에 영향 없는
# 안전한 지시어(object/frame-ancestors/base-uri)는 지금 적용해 클릭재킹·플러그인·base 하이재킹을 막는다.
@app.middleware("http")
async def _security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("Content-Security-Policy", "object-src 'none'; frame-ancestors 'self'; base-uri 'self'")
    # HSTS는 HTTPS에서만 의미(브라우저가 http에선 무시). fly는 force_https라 실서비스에서 적용됨.
    resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return resp


# 업로드 상한(§4.9) — audio.read()로 전체를 메모리에 적재하므로 상한이 없으면 DoS 소지.
_MAX_AUDIO_BYTES = 10 * 1024 * 1024  # 10MB


async def _read_audio_limited(audio: UploadFile, max_bytes: int = _MAX_AUDIO_BYTES) -> bytes:
    """오디오 업로드를 상한까지만 읽고, 초과·빈 파일·비오디오 타입을 거부한다."""
    ctype = (audio.content_type or "").lower()
    if ctype and not (ctype.startswith("audio/") or ctype in ("application/octet-stream", "video/webm")):
        raise HTTPException(status_code=415, detail="오디오 파일만 업로드할 수 있습니다.")
    data = await audio.read(max_bytes + 1)
    if not data:
        raise HTTPException(status_code=400, detail="empty audio")
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail=f"오디오가 너무 큽니다(최대 {max_bytes // (1024 * 1024)}MB).")
    return data


def _server_error(exc: Exception, where: str) -> HTTPException:
    """500 오류를 서버 로그로만 남기고 클라이언트엔 고정 문구를 준다(§4.9 내부정보 노출 차단)."""
    logging.getLogger("liplab").exception("server error @ %s", where)
    return HTTPException(status_code=500, detail="처리 중 오류가 발생했습니다.")


def _sanitize_text(s, maxlen: int) -> str:
    """LLM 프롬프트에 들어가는 자유 입력을 정규화 — 제어문자 제거 + 길이 상한(프롬프트 조작·남용 방지)."""
    s = (s or "").strip()
    s = "".join(ch for ch in s if ch in ("\n", "\t") or ord(ch) >= 32)
    return s[:maxlen]


def _sanitize_history(history, max_items: int = 20, max_len: int = 400) -> list:
    """대화 이력을 최근 max_items개로 제한하고 각 항목의 텍스트를 정규화한다."""
    out = []
    for h in (history or [])[-max_items:]:
        if not isinstance(h, dict):
            continue
        item = dict(h)
        for k in ("text", "content", "message"):
            if k in item and isinstance(item[k], str):
                item[k] = _sanitize_text(item[k], max_len)
        out.append(item)
    return out


_DEMO_EMAIL = "demo@liplab.app"
# 약관·처리방침 판본(frontend/src/pages/Legal.jsx의 시행일과 같게 유지). 가입 동의 기록에 남는다.
_TERMS_VERSION = "2026-09-23"
_PRIVACY_VERSION = "2026-09-23"


def _user_data_models():
    """user_id를 가진 모든 사용자 데이터 모델(개인정보 열람·삭제 대상)."""
    import inspect as _inspect
    import database as _db
    out = []
    for name in dir(_db):
        o = getattr(_db, name)
        if _inspect.isclass(o) and hasattr(o, "__tablename__"):
            if "user_id" in [c.name for c in o.__table__.columns]:
                out.append(o)
    return out


def _iso_utc(ts):
    """DB의 naive UTC 시각 → 'YYYY-MM-DDTHH:MM:SSZ'(브라우저가 현지 시각으로 바꿔 상대 날짜를 만든다)."""
    return ts.replace(microsecond=0).isoformat() + "Z" if ts else None


def _row_to_dict(row) -> dict:
    d = {}
    for c in row.__table__.columns:
        v = getattr(row, c.name)
        d[c.name] = v.isoformat() if hasattr(v, "isoformat") else v
    return d


# ============================================
# Authentication Endpoints
# ============================================

@app.post("/api/auth/register", response_model=Token, status_code=status.HTTP_201_CREATED,
          dependencies=[Depends(ratelimit.rate_limit(10, 60, "auth"))])
async def register(user_data: UserRegister, db: AsyncSession = Depends(get_db)):
    """회원가입. 약관·처리방침 동의와 연령(만 14세 이상 또는 법정대리인 동의) 확인을 서버에서도
    검사하고, 동의한 판본·시각을 ConsentRecord로 남긴다(§4.9 표11 ②)."""
    if not (user_data.agree_terms and user_data.age_confirmed):
        raise HTTPException(status_code=400,
                            detail="이용약관·개인정보 처리방침 동의와 연령 확인이 필요합니다.")
    user = await register_user(user_data, db)
    from database import ConsentRecord
    db.add(ConsentRecord(user_id=user.id, terms_version=_TERMS_VERSION,
                         privacy_version=_PRIVACY_VERSION, age_confirmed=True))
    await db.commit()
    return create_token_response(user)


@app.post("/api/auth/login", response_model=Token,
          dependencies=[Depends(ratelimit.rate_limit(10, 60, "auth"))])
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


@app.post("/api/auth/demo", response_model=Token,
          dependencies=[Depends(ratelimit.rate_limit(30, 60, "auth"))])
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


@app.get("/api/account/data", dependencies=[Depends(ratelimit.rate_limit(10, 60, "account-export"))])
async def account_export(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """개인정보 열람권(§4.9) — 내 계정·학습 데이터 전체를 JSON으로 내보낸다(데이터 이동성).
    민감 정보(비밀번호 해시)는 제외한다."""
    from sqlalchemy import select as _select
    from datetime import datetime as _dt
    user = {c.name: (getattr(current_user, c.name).isoformat()
                     if hasattr(getattr(current_user, c.name), "isoformat") else getattr(current_user, c.name))
            for c in current_user.__table__.columns if c.name != "hashed_password"}
    data = {}
    for M in _user_data_models():
        r = await db.execute(_select(M).where(M.user_id == current_user.id))
        data[M.__tablename__] = [_row_to_dict(x) for x in r.scalars().all()]
    return {"exported_at": _dt.utcnow().isoformat(), "user": user, "data": data,
            "note": ("웹캠 영상은 기기 안에서만 처리되고, 원음성은 채점하는 동안 서버 메모리에서만 처리한 뒤 "
                     "저장하지 않으므로 이 내보내기에 포함되지 않습니다. 전사문·음성 지표·입모양 계수 기반 점수는 "
                     "학습 기록으로 저장되어 아래 data에 들어 있습니다.")}


from pydantic import BaseModel as _PydBaseModel


class AccountDeleteReq(_PydBaseModel):
    password: str = ""


@app.delete("/api/account", dependencies=[Depends(ratelimit.rate_limit(5, 60, "account-delete"))])
async def account_delete(req: AccountDeleteReq, confirm: bool = False,
                         current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """개인정보 삭제권(§4.9) — 내 계정과 모든 학습 데이터를 영구 삭제한다.
    실수 방지를 위해 confirm=true, 탈취된 토큰으로 지우지 못하게 현재 비밀번호 재확인이 필요하다.
    공용 데모 계정은 삭제할 수 없다."""
    from auth import verify_password
    if not confirm:
        raise HTTPException(status_code=400, detail="삭제를 확인하려면 confirm=true가 필요합니다.")
    if (current_user.email or "").lower() == _DEMO_EMAIL:
        raise HTTPException(status_code=403, detail="공용 데모 계정은 삭제할 수 없습니다.")
    if not verify_password(req.password or "", current_user.hashed_password):
        raise HTTPException(status_code=403, detail="비밀번호가 일치하지 않습니다.")
    from sqlalchemy import delete as _delete
    from database import User as _User
    counts = {}
    for M in _user_data_models():
        res = await db.execute(_delete(M).where(M.user_id == current_user.id))
        counts[M.__tablename__] = res.rowcount if res.rowcount is not None else 0
    await db.execute(_delete(_User).where(_User.id == current_user.id))
    await db.commit()
    return {"deleted": True, "removed": counts}


# ============================================
# Core API Endpoints
# ============================================

from pydantic import BaseModel
from typing import List, Optional


class ProfileUpdateReq(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    current_password: Optional[str] = None   # 이메일을 바꿀 때만 필요(재인증)


class PasswordChangeReq(BaseModel):
    current_password: str
    new_password: str


@app.patch("/api/account/profile", dependencies=[Depends(ratelimit.rate_limit(10, 60, "account-profile"))])
async def account_update_profile(req: ProfileUpdateReq,
                                 current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """개인정보 정정권(§4.9) — 표시 이름(username)·이메일을 수정한다. 공용 데모 계정은 수정 불가."""
    if (current_user.email or "").lower() == _DEMO_EMAIL:
        raise HTTPException(status_code=403, detail="공용 데모 계정은 수정할 수 없습니다.")
    from sqlalchemy import select as _select
    from database import User as _User
    if req.username is not None:
        name = _sanitize_text(req.username, 100).strip()
        if not (1 <= len(name) <= 100):
            raise HTTPException(status_code=400, detail="이름은 1~100자여야 합니다.")
        dup = (await db.execute(_select(_User).where(_User.username == name,
                                                     _User.id != current_user.id))).scalar_one_or_none()
        if dup:
            raise HTTPException(status_code=409, detail="이미 사용 중인 이름입니다.")
        current_user.username = name
    if req.email is not None:
        import re as _re
        from sqlalchemy import func as _func
        email = _sanitize_text(req.email, 200).strip().lower()
        # 간단한 형식 검증(정정권 대응) — 대소문자 무시, 유일성 보장.
        if not _re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            raise HTTPException(status_code=400, detail="이메일 형식이 올바르지 않습니다.")
        if email != (current_user.email or "").lower():
            # 이메일은 로그인 식별자라, 바꿀 때는 현재 비밀번호로 본인임을 다시 확인한다(§4.9 재인증).
            from auth import verify_password
            if not verify_password(req.current_password or "", current_user.hashed_password):
                raise HTTPException(status_code=403, detail="이메일을 바꾸려면 현재 비밀번호가 필요합니다.")
        dupe = (await db.execute(_select(_User).where(_func.lower(_User.email) == email,
                                                      _User.id != current_user.id))).scalar_one_or_none()
        if dupe:
            raise HTTPException(status_code=409, detail="이미 사용 중인 이메일입니다.")
        current_user.email = email
    await db.commit()
    await db.refresh(current_user)
    return {"ok": True, "username": current_user.username, "email": current_user.email}


@app.post("/api/account/password", dependencies=[Depends(ratelimit.rate_limit(5, 60, "account-password"))])
async def account_change_password(req: PasswordChangeReq,
                                  current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """비밀번호 변경(§4.9 정정권 + 민감동작 재인증) — 현재 비밀번호를 확인한 뒤에만 변경한다."""
    from auth import verify_password, get_password_hash
    if (current_user.email or "").lower() == _DEMO_EMAIL:
        raise HTTPException(status_code=403, detail="공용 데모 계정은 비밀번호를 변경할 수 없습니다.")
    if not verify_password(req.current_password or "", current_user.hashed_password):
        raise HTTPException(status_code=403, detail="현재 비밀번호가 일치하지 않습니다.")
    if len(req.new_password or "") < 8:
        raise HTTPException(status_code=400, detail="새 비밀번호는 8자 이상이어야 합니다.")
    current_user.hashed_password = get_password_hash(req.new_password)
    # 토큰 버전을 올려 다른 기기·탈취된 토큰을 모두 무효화하고, 이 기기에는 새 토큰을 준다.
    current_user.token_version = (current_user.token_version or 0) + 1
    await db.commit()
    await db.refresh(current_user)
    return {"ok": True, "access_token": create_token_response(current_user).access_token}


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
    old_level: int = 1
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
        raise _server_error(e, "Viseme conversion failed")


@app.get("/api/avatar/audio2face/status")
async def audio2face_status():
    """음성구동 아바타(A4) 사용 가능 여부 — 프론트가 UI 노출 판단에 사용."""
    try:
        import audio2face
        return {"available": audio2face.is_available()}
    except Exception:
        return {"available": False}


@app.post("/api/avatar/audio2face", dependencies=[Depends(ratelimit.rate_limit(20, 60, "audio"))])
async def avatar_audio2face(audio: UploadFile = File(...), current_user=Depends(get_current_user)):
    """
    음성 → 얼굴 블렌드셰이프 시퀀스(축 A4). 실제 음성으로 아바타가 립싱크한다.
    화자 불변 WavLM 특징 → BiGRU → 52 ARKit 블렌드셰이프(미학습화자 jawOpen r≈0.66, 20화자 교차검증).
    모델/라이브러리가 없으면 503(프론트는 텍스트→비심 경로로 폴백).
    """
    try:
        import audio2face
    except Exception:
        raise HTTPException(status_code=503, detail="audio2face 모듈 로드 실패")
    if not audio2face.is_available():
        raise HTTPException(status_code=503, detail="서버에 음성구동 아바타 모델(A4)이 없습니다.")
    data = await _read_audio_limited(audio)
    try:
        result = await asyncio.to_thread(audio2face.blendshapes_from_audio, data)
    except Exception as e:
        logging.getLogger("liplab").exception("audio2face 추론 실패")
        raise HTTPException(status_code=500, detail="음성구동 처리에 실패했습니다.")
    return result


@app.get("/api/scenario", response_model=ScenarioResponse,
         dependencies=[Depends(ratelimit.rate_limit(40, 60, "llm"))])
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
    situation = _sanitize_text(situation, 80)

    try:
        scenario = await generate_adaptive_scenario(
            user_id=current_user.id,
            situation=situation,
            level=level,
            db=db
        )
        return scenario
    except Exception as e:
        raise _server_error(e, "Scenario generation failed")


# ── 공용 학습 보상 — 모든 활동(문장·인지·단어·문맥·복습·대화)이 XP·스트릭·취약 입모양을
#    동일하게 갱신하도록 한 곳에 모은다. 예전엔 문장 연습만 XP/스트릭을 줘서, 인지·단어·복습만
#    한 날은 스트릭이 끊기고 다른 활동이 개인화(WeakViseme) 데이터에 전혀 기여하지 못했다.
def _award_xp_and_streak(user, base_xp: int, bonus: int = 0) -> dict:
    """스트릭(하루 1회 갱신·idempotent) + XP + 레벨업을 계산해 user에 반영. 커밋은 호출부.
    base_xp는 활동별 기본 XP(스트릭 배수 적용 전), bonus는 배수 미적용 가산점(예: 시간 보너스)."""
    from datetime import date, timedelta
    today_str = date.today().isoformat()
    yesterday_str = (date.today() - timedelta(days=1)).isoformat()
    last_date = user.last_practice_date
    if last_date is None or last_date < yesterday_str:
        user.streak_count = 1            # 첫 학습 또는 스트릭 끊김
    elif last_date == yesterday_str:
        user.streak_count += 1           # 연속 학습
    # last_date == today_str: 오늘 이미 학습함 → streak 유지
    user.last_practice_date = today_str

    streak_multiplier = min(1.0 + user.streak_count * 0.1, 3.0)
    xp_gained = int(base_xp * streak_multiplier) + bonus
    old_level = user.current_level
    user.total_xp += xp_gained
    new_level = int((user.total_xp / 100) ** 0.5) + 1        # level = floor(sqrt(xp/100))+1
    user.current_level = max(user.current_level, new_level)
    return {
        "xp_gained": xp_gained,
        "streak_count": user.streak_count,
        "streak_multiplier": round(streak_multiplier, 2),
        "old_level": old_level,
        "new_level": user.current_level,
    }


async def _bump_weak_visemes(user_id: int, viseme_ids, error_ids, features: dict, db, when=None):
    """주어진 viseme들의 시도/오류를 WeakViseme에 누적(1~10 유명 그룹만). 커밋은 호출부.
    문장·단어·문맥 어떤 활동이든 취약 입모양 통계에 기여하게 하는 공용 경로."""
    from database import WeakViseme
    from sqlalchemy import select
    from datetime import datetime as _dt2
    when = when or _dt2.utcnow()
    error_ids = set(error_ids or [])
    for vid in viseme_ids:
        if not (1 <= vid <= 10):
            continue
        r = await db.execute(select(WeakViseme).where(
            WeakViseme.user_id == user_id, WeakViseme.viseme_id == vid))
        wv = r.scalar_one_or_none()
        if wv is None:
            wv = WeakViseme(user_id=user_id, viseme_id=vid, error_count=0,
                            total_attempts=0,
                            phonological_feature=(features or {}).get(str(vid), "unknown"))
            db.add(wv)
        wv.total_attempts += 1
        if vid in error_ids:
            wv.error_count += 1
            wv.last_error_at = when


async def _weak_visemes_for_text(text: str):
    """텍스트의 유명 viseme id 목록과 특징맵 — 단어/문맥 활동의 취약 입모양 반영용."""
    from engine import get_viseme_feature
    frames = await text_to_visemes(text)
    vids = sorted({f["viseme"] for f in frames if 1 <= f["viseme"] <= 10})
    features = {str(v): get_viseme_feature(v) for v in vids}
    return vids, features


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
        from database import Progress

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

        # 취약 입모양 갱신 — 문장의 모든 유명 viseme에 시도 1회, 오류난 것만 오류 1회 (공용 경로)
        all_viseme_frames = await text_to_visemes(submission.sentence)
        all_viseme_ids = sorted({
            f["viseme"] for f in all_viseme_frames
            if 1 <= f["viseme"] <= 10  # only named groups
        })
        error_ids = set(scoring_result.get("viseme_errors", []))
        await _bump_weak_visemes(
            current_user.id, all_viseme_ids, error_ids,
            scoring_result.get("features", {}), db, when=progress.created_at)

        # XP·스트릭·레벨 — 공용 보상 (문장 연습은 시간 보너스를 가산)
        base_xp = int(scoring_result["score"] * submission.difficulty_level * 2)
        time_bonus = max(0, 50 - submission.time_spent_seconds // 2)
        award = _award_xp_and_streak(current_user, base_xp, bonus=time_bonus)

        # 3단계(문장 연습) 숙달 갱신 — 점수 PASS 이상이면 성공 1회로 누적(4단계 해금 근거)
        await _bump_stage_progress(
            current_user.id, 3, scoring_result["score"] >= _STAGE3_PASS,
            _STAGE3_MIN_ATTEMPTS, _STAGE3_MASTERY, db)

        await db.commit()

        return ProgressResponse(
            status="success",
            score=scoring_result["score"],
            new_level=award["new_level"],
            old_level=award["old_level"],
            xp_gained=award["xp_gained"],
            streak_count=award["streak_count"],
            streak_multiplier=award["streak_multiplier"],
            feedback=scoring_result.get("feedback", {}),
            phoneme_accuracy=scoring_result.get("phoneme_accuracy", {})
        )

    except Exception as e:
        await db.rollback()
        raise _server_error(e, "Progress submission failed")


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
    domain: str = "read"   # read | speak — 두 기둥 공통 북마크


@app.get("/api/bookmarks")
async def list_bookmarks(domain: str = None, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from database import Bookmark
    from sqlalchemy import select
    q = select(Bookmark).where(Bookmark.user_id == current_user.id)
    if domain:
        q = q.where(Bookmark.domain == domain)
    result = await db.execute(q.order_by(Bookmark.created_at.desc()))
    items = result.scalars().all()
    return [{"id": b.id, "sentence": b.sentence, "situation": b.situation,
             "level": b.level, "domain": getattr(b, "domain", "read") or "read",
             "created_at": _iso_utc(b.created_at)} for b in items]


@app.post("/api/bookmarks", status_code=201)
async def add_bookmark(data: BookmarkCreate, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from database import Bookmark
    from sqlalchemy import select
    existing = await db.execute(
        select(Bookmark).where(Bookmark.user_id == current_user.id, Bookmark.sentence == data.sentence,
                               Bookmark.domain == data.domain)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already bookmarked")
    bm = Bookmark(user_id=current_user.id, sentence=data.sentence, situation=data.situation,
                  level=data.level, domain=data.domain)
    db.add(bm)
    await db.commit()
    await db.refresh(bm)
    return {"id": bm.id, "sentence": bm.sentence, "situation": bm.situation, "level": bm.level, "domain": bm.domain}


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


@app.get("/api/analysis", dependencies=[Depends(ratelimit.rate_limit(30, 60, "llm-analysis"))])
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
        # 같은 문장이 여러 번 반복되므로 문장→비심 변환을 요청 내에서 캐시(최대 100건 재계산 방지)
        viseme_score_map: dict = {}
        _vis_cache: dict = {}
        for prog in all_progress:
            try:
                if not prog.sentence:
                    continue
                sentence_visemes = _vis_cache.get(prog.sentence)
                if sentence_visemes is None:
                    frames = await text_to_visemes(prog.sentence)
                    sentence_visemes = {f["viseme"] for f in frames if 1 <= f["viseme"] <= 10}
                    _vis_cache[prog.sentence] = sentence_visemes
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

        # Phoneme confusion analysis — 발음형으로 정규화 + 채점과 같은 DP 정렬 사용
        # (철자 기준이면 굳이/구지처럼 '정답 발음을 맞힌' 경우가 혼동으로 잘못 집계됨)
        from scoring import to_pronounced_jamos, align_jamos
        confusion_map: dict = {}
        for prog in all_progress:
            try:
                if prog.score >= 80 or not prog.sentence:
                    continue
                c_jamos = to_pronounced_jamos(prog.sentence.replace(" ", ""))
                u_jamos = to_pronounced_jamos((prog.user_answer or "").replace(" ", ""))
                for cs, us in align_jamos(c_jamos, u_jamos):
                    if cs is None or us is None:
                        continue
                    if cs[0] and us[0] and cs[0] != us[0]:
                        key = (cs[0], us[0])
                        confusion_map[key] = confusion_map.get(key, 0) + 1
                    if cs[1] and us[1] and cs[1] != us[1]:
                        key = (cs[1], us[1])
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
        raise _server_error(e, "분석 데이터 로드 실패")


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


@app.get("/api/calendar/activities")
async def get_calendar_activities(days_back: int = 140, tz_offset_min: int = -540,
                                  current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """날짜별로 '무엇을 학습했는지' 요약 — 활동 캘린더·회차 히스토리용.
    /api/calendar는 문장 연습(Progress) 건수만 세므로, 여기서는 활동 종류별 테이블을 모두 모아
    { 'YYYY-MM-DD': [ {kind, label, n, accuracy}, ... ] }로 돌려준다. label은 화면에 그대로 붙이는 한국어 문구.
    날짜는 tz_offset_min(브라우저 Date.getTimezoneOffset(), 한국 −540)으로 정한 사용자 현지 날짜다(분석 개요와 같은 기준).
    accuracy(0~1)는 채점된 시도의 평균이다 — 문장·말하기 점수는 /100, 선다형은 정오, 검사는 정답률.
    채점 기록이 없는 행은 null.
    """
    from database import Progress, TrialAttempt, SpeakAttempt, PlacementResult
    from sqlalchemy import select
    import datetime as dt
    from collections import defaultdict
    from urllib.parse import quote
    import analytics as _an

    tz = max(-840, min(720, int(tz_offset_min)))
    days_back = max(7, min(400, int(days_back)))
    cutoff = dt.datetime.utcnow() - dt.timedelta(days=days_back + 1)
    uid = current_user.id
    # day → kind → detail → [시도 수, 채점 합, 채점 수]
    days: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: [0, 0.0, 0])))

    def add(ts, kind, detail, grade):
        if ts is None:
            return
        cell = days[_an.to_local(ts, tz).date().isoformat()][kind][detail]
        cell[0] += 1
        if grade is not None:
            cell[1] += max(0.0, min(1.0, float(grade)))
            cell[2] += 1

    # 문장 연습(3단계·복습) — 상황별로 묶는다
    for ts, situation, score in (await db.execute(
            select(Progress.created_at, Progress.situation, Progress.score)
            .where(Progress.user_id == uid, Progress.created_at >= cutoff))).all():
        add(ts, "sentence", situation or "", None if score is None else score / 100.0)
    # 1·2단계·문맥 추론 시행
    for ts, item_type, correct in (await db.execute(
            select(TrialAttempt.created_at, TrialAttempt.item_type, TrialAttempt.correct)
            .where(TrialAttempt.user_id == uid, TrialAttempt.created_at >= cutoff))).all():
        add(ts, item_type or "trial", "", 1.0 if correct else 0.0)
    # 말하기 연습 — 모드별(통과 여부가 있으면 그것, 없으면 점수)
    for ts, mode, passed, score in (await db.execute(
            select(SpeakAttempt.created_at, SpeakAttempt.mode, SpeakAttempt.passed, SpeakAttempt.score)
            .where(SpeakAttempt.user_id == uid, SpeakAttempt.created_at >= cutoff))).all():
        g = (1.0 if passed else 0.0) if passed is not None else (None if score is None else score / 100.0)
        add(ts, "speak", mode or "", g)
    # 배치·향상도 검사
    for ts, form, acc in (await db.execute(
            select(PlacementResult.created_at, PlacementResult.form, PlacementResult.accuracy)
            .where(PlacementResult.user_id == uid, PlacementResult.created_at >= cutoff))).all():
        add(ts, "assessment", form or "placement", acc)

    KIND_LABEL = {"viseme": "입모양 인지", "word": "단어", "closure": "문맥 추론", "trial": "인지 훈련"}
    SPEAK_LABEL = {"voicing": "발성", "prosody": "억양", "phoneme": "음소", "word": "단어", "sentence": "문장"}
    FORM_LABEL = {"placement": "배치검사", "A": "사전검사", "B": "사후검사"}
    TYPE_LABEL = {"assessment": "검사", "viseme": "독화", "word": "독화", "closure": "독화", "trial": "독화",
                  "sentence": "문장 연습", "speak": "말하기"}
    # 블록 클릭 시 이동할 학습 화면. 말하기 모드는 speak_curriculum의 단계 번호로 연결한다.
    SPEAK_STAGE = {"voicing": 0, "prosody": 1, "phoneme": 2, "word": 4, "sentence": 5}
    KIND_ROUTE = {"assessment": "/learn/placement", "viseme": "/learn/viseme", "word": "/learn/word",
                  "closure": "/learn/closure", "trial": "/learn/viseme"}
    ORDER = ["assessment", "viseme", "word", "closure", "trial", "sentence", "speak"]

    # 주제가 다르면 같은 날이라도 각자 한 행 — 문장 연습은 상황별, 말하기는 모드별, 검사는 폼별로 나눈다.
    out = {}
    for day, kinds in sorted(days.items()):
        rows = []
        for kind in ORDER:
            if kind not in kinds:
                continue
            for detail, (n, g_sum, g_n) in sorted(kinds[kind].items(), key=lambda kv: -kv[1][0]):
                # topic_label = 블록 제목(상황·모드·검사 종류), type_label = 유형 배지
                if kind == "sentence":
                    topic_label = detail or "문장 연습"
                elif kind == "speak":
                    topic_label = SPEAK_LABEL.get(detail, detail) if detail else "말하기"
                elif kind == "assessment":
                    topic_label = FORM_LABEL.get(detail, detail)
                else:
                    topic_label = KIND_LABEL[kind]
                type_label = TYPE_LABEL[kind]
                if kind == "sentence":
                    route = "/review/mistakes" if detail == "복습" else (
                        f"/learn/scenario?situation={quote(detail)}" if detail else "/learn/scenario")
                elif kind == "speak":
                    route = f"/learn/speaking?stage={SPEAK_STAGE[detail]}" if detail in SPEAK_STAGE else "/learn/speaking"
                else:
                    route = KIND_ROUTE[kind]
                label = topic_label if topic_label == type_label or kind == "assessment" else f"{type_label} · {topic_label}"
                rows.append({"kind": kind, "topic": detail, "topic_label": topic_label,
                             "type_label": type_label, "label": label, "n": n, "route": route,
                             "accuracy": round(g_sum / g_n, 3) if g_n else None})
        out[day] = rows
    return out


@app.get("/api/analysis/overview")
async def get_analysis_overview(tz_offset_min: int = -540, current_user=Depends(get_current_user),
                                db: AsyncSession = Depends(get_db)):
    """분석 탭 요약 + 배지 — 활동 기록 전체에서 계산한다(집계 로직은 analytics.py).

    학습 시간은 따로 저장하지 않으므로 활동 시각으로 회차를 나눠 추정하고(30분 공백 = 새 회차),
    정확도는 독화 시행(정오답)·문장 점수·말하기 통과 여부를 0~1로 모아 평균한다.
    tz_offset_min은 브라우저 Date.getTimezoneOffset()(한국 −540) — 날짜·연속 학습·새벽 판정에 쓴다.
    """
    import datetime as dt
    import analytics as _an
    from database import (Progress, TrialAttempt, SpeakAttempt, PlacementResult,
                          StageProgress, SpeakStageProgress, ReviewItem)
    from sqlalchemy import select

    tz = max(-840, min(720, int(tz_offset_min)))
    uid = current_user.id
    events = []
    for ts, score in (await db.execute(select(Progress.created_at, Progress.score)
                                       .where(Progress.user_id == uid))).all():
        events.append(_an.Event(ts, "read", None if score is None else max(0.0, min(1.0, score / 100.0))))
    for ts, correct in (await db.execute(select(TrialAttempt.created_at, TrialAttempt.correct)
                                         .where(TrialAttempt.user_id == uid))).all():
        events.append(_an.Event(ts, "read", 1.0 if correct else 0.0))
    for ts, passed, score in (await db.execute(select(SpeakAttempt.created_at, SpeakAttempt.passed, SpeakAttempt.score)
                                               .where(SpeakAttempt.user_id == uid))).all():
        g = (1.0 if passed else 0.0) if passed is not None else (None if score is None else max(0.0, min(1.0, score / 100.0)))
        events.append(_an.Event(ts, "speak", g))
    for (ts,) in (await db.execute(select(PlacementResult.created_at)
                                   .where(PlacementResult.user_id == uid))).all():
        events.append(_an.Event(ts, "test", None))
    events = [e for e in events if e.ts is not None]

    prof = await _get_or_create_profile(uid, db)
    read_rows = (await db.execute(select(StageProgress).where(StageProgress.user_id == uid))).scalars().all()
    read_mastered = {sp.stage for sp in read_rows if sp.status == "mastered"}
    if prof.placed:
        read_mastered.add(0)                     # 0단계는 배치(트랙 선택) 완료가 곧 숙달
    conv = next((sp.attempts for sp in read_rows if sp.stage == 4), 0) or 0
    speak_rows = (await db.execute(select(SpeakStageProgress).where(SpeakStageProgress.user_id == uid))).scalars().all()
    speak_mastered = {sp.stage for sp in speak_rows if sp.status == "mastered"}

    now = dt.datetime.utcnow()
    today_local = _an.to_local(now, tz).date().isoformat()
    reviews = (await db.execute(select(ReviewItem).where(ReviewItem.user_id == uid))).scalars().all()
    reviews_done = sum(1 for r in reviews if (r.repetitions or 0) > 0 or (r.lapses or 0) > 0)
    reviews_overdue = sum(1 for r in reviews if r.due_date and r.due_date < today_local)

    return _an.overview(
        events, now, tz,
        read_mastered=read_mastered,
        read_total=len([s for s in _curriculum.STAGES if not s.get("coming_soon")]),
        speak_mastered=speak_mastered, speak_total=len(_speakcur.stages_overview()),
        conversation_attempts=conv, reviews_done=reviews_done, reviews_overdue=reviews_overdue,
        level=current_user.current_level or 1,
    )


@app.get("/api/review-sentences")
async def get_review_sentences(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """최근에도 틀린(가장 최근 시도 점수 < 60) 서로 다른 문장을 최대 10개 반환.

    예전엔 '이력 어디선가 score<60'이면 넣어, 나중에 그 문장을 마스터해도 과거 오답 때문에
    영원히 복습 목록에 남았다. 각 문장의 '가장 최근' 시도만 보고, 최근에도 60 미만일 때만
    복습 대상에 넣어 마스터하면 자연히 졸업하게 한다.
    """
    from database import Progress
    from sqlalchemy import select

    result = await db.execute(
        select(Progress)
        .where(Progress.user_id == current_user.id)
        .order_by(Progress.created_at.desc())   # 최신순 — 각 문장의 첫 등장이 가장 최근 시도
        .limit(200)
    )
    records = result.scalars().all()
    seen: set = set()
    unique = []
    for p in records:
        if p.sentence in seen:
            continue
        seen.add(p.sentence)                     # 이 문장의 '가장 최근' 시도만 판단
        if p.score < 60:                         # 최근에도 틀렸을 때만 복습 대상
            unique.append({
                "sentence": p.sentence,
                "situation": p.situation,
                "difficulty_level": p.difficulty_level,
                "score": round(p.score, 1),
                "created_at": _iso_utc(p.created_at),   # 가장 최근에 틀린 시각
            })
        if len(unique) >= 10:
            break
    return unique


# ============================================
# Curriculum (단계형 커리큘럼) — 재설계 Phase 1
# ============================================
import curriculum as _curriculum

# 심사·데모 편의: 모든 단계 잠금 해제(순차 잠금 로직은 유지하되 표시만 unlocked로).
# 실제 순차 학습을 강제하려면 환경변수 LIPLAB_UNLOCK_ALL=0.
_UNLOCK_ALL = os.getenv("LIPLAB_UNLOCK_ALL", "1") == "1"

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


async def _srs_apply(user_id: int, kind: str, ref, quality: int, db, create: bool = True) -> dict:
    """SM-2 경량 스케줄러(srs.schedule)를 한 복습 항목에 적용. 항목의 ease/간격/반복/누수를
    갱신하고 due_date를 다시 잡는다. 간격이 충분히 커지면(졸업) 큐에서 제거한다.
    항목이 없을 때 quality<3(실패)이고 create면 새로 등록한다. commit은 호출부.
    반환: {removed, due_date, interval_days}."""
    import srs
    from database import ReviewItem
    from sqlalchemy import select
    ref = str(ref)
    if not ref:
        return {"removed": False, "due_date": None, "interval_days": None}
    r = await db.execute(select(ReviewItem).where(
        ReviewItem.user_id == user_id, ReviewItem.kind == kind, ReviewItem.ref == ref))
    item = r.scalar_one_or_none()

    if item is None:
        if not create or quality >= 3:
            return {"removed": False, "due_date": None, "interval_days": None}
        s = srs.schedule(quality)  # 첫 실패 → 내일 재등장
        due = (_sr_date.today() + _sr_delta(days=s["interval_days"])).isoformat()
        db.add(ReviewItem(user_id=user_id, kind=kind, ref=ref, due_date=due,
                          interval_days=s["interval_days"], ease_factor=s["ease_factor"],
                          repetitions=s["repetitions"], lapses=s["lapses"]))
        return {"removed": False, "due_date": due, "interval_days": s["interval_days"]}

    s = srs.schedule(quality, ease_factor=item.ease_factor, interval_days=item.interval_days,
                     repetitions=item.repetitions, lapses=item.lapses)
    if s["graduated"] and quality >= 3:
        await db.delete(item)   # 졸업 — 큐에서 제거
        return {"removed": True, "due_date": None, "interval_days": s["interval_days"]}
    item.interval_days = s["interval_days"]
    item.ease_factor = s["ease_factor"]
    item.repetitions = s["repetitions"]
    item.lapses = s["lapses"]
    item.due_date = (_sr_date.today() + _sr_delta(days=s["interval_days"])).isoformat()
    return {"removed": False, "due_date": item.due_date, "interval_days": item.interval_days}


async def _srs_schedule_wrong(user_id: int, kind: str, ref, db: AsyncSession):
    """오답 → SM-2로 복습 재예약(신규면 등록). commit은 호출부에서."""
    import srs
    await _srs_apply(user_id, kind, ref, srs.quality_from_correct(False), db, create=True)


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

    if _UNLOCK_ALL:
        for st in stages:
            if st.get("status") == "locked":
                st["status"] = "unlocked"

    return {"track": prof.track, "placed": prof.placed,
            "current_stage": prof.current_stage, "stages": stages}


class TrackSelect(BaseModel):
    track: str  # 'perception' | 'language'
    start_stage: Optional[int] = None  # 표준검사(축 I) 진단 결과의 추천 시작 단계(자동 배치)


@app.post("/api/curriculum/track")
async def curriculum_set_track(data: TrackSelect, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """배치: 트랙 선택 → 잠금 해제. start_stage가 오면(표준검사 진단) 그 단계로 자동 배치한다."""
    if data.track not in ("perception", "language"):
        raise HTTPException(status_code=400, detail="track must be 'perception' or 'language'")
    prof = await _get_or_create_profile(current_user.id, db)
    prof.track = data.track
    prof.placed = True
    start = data.start_stage if (data.start_stage and 1 <= data.start_stage <= 4) else 1
    prof.current_stage = max(prof.current_stage or 0, start)
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
    import articulation as _art
    lessons = []
    for l in _curriculum.VISEME_LESSONS:
        tgt = _art.articulation_target(l["viseme_id"])
        lessons.append({
            **l,
            "demo_syllable": _curriculum.DEMO_SYLLABLE.get(l["viseme_id"]),
            "quizzable": l["visibility"] != "low",
            "homophene_cluster": (_curriculum.homophene_cluster_of(l["viseme_id"]) or {}).get("id"),
            # 축 E: 밖에서 안 보이는 내부 조음(혀·조음 위치·방식). look(보이는 입모양)의 짝.
            "articulation": {"place": tgt["place"], "manner": tgt["manner"],
                             "guide": tgt["hidden_guide"], "nasal": tgt["nasal"]},
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

        # 공용 보상 — 인지퀴즈도 XP·스트릭에 기여(예전엔 문장 연습만 XP를 줬음)
        award = _award_xp_and_streak(current_user, 15 if correct else 3)
        # 시행 기록 — 학습곡선·유형별 정확도(eval/summary)가 1단계 입모양 인지도 포함하도록.
        # (그룹 선다라 자모 혼동은 없음 → confusions=[])
        from database import TrialAttempt
        db.add(TrialAttempt(user_id=current_user.id, stage=1, item_type="viseme",
                            target=str(data.viseme_id), chosen=str(data.chosen_id), correct=correct, confusions=[]))

        await db.commit()
        await db.refresh(sp)
    except Exception as e:
        await db.rollback()
        raise _server_error(e, "recognition submit failed")

    return {
        "correct": correct,
        "same_cluster": same_cluster,
        "target": {"viseme_id": data.viseme_id, "name": target["name"], "teach": target["teach"]},
        "mastery_score": round(sp.mastery_score, 1),
        "attempts": sp.attempts,
        "mastered": sp.status == "mastered",
        "xp_gained": award["xp_gained"],
        "streak_count": award["streak_count"],
    }


class WordAnswer(BaseModel):
    word: str
    correct: bool
    chosen: Optional[str] = None   # 사용자가 실제로 고른 단어(오답 시 자모 혼동 분석용)


@app.get("/api/curriculum/words")
async def curriculum_words(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """2단계 콘텐츠: 큐레이션 단어 은행 + 최소대립쌍(프론트가 단어 퀴즈를 구성).
    각 단어에 개인화 priority를 실어 준다(tier가 낮을수록·약점 비심을 포함할수록 높음).
    프론트가 이 값으로 가중 표집하면 쉬운 것부터·약점 위주로 자연스레 출제된다."""
    import knowledge_tracing as _kt
    from content_rules import word_visemes as _wv
    from database import WeakViseme as _WV
    from sqlalchemy import select as _select
    try:
        r = await db.execute(_select(_WV).where(_WV.user_id == current_user.id))
        records = [{"viseme_id": w.viseme_id, "error_count": w.error_count,
                    "total_attempts": w.total_attempts, "last_error_at": w.last_error_at}
                   for w in r.scalars().all()]
        mastery = _kt.estimate_mastery(records)
    except Exception:
        mastery = {}
    weak = {vid for vid, m in mastery.items() if m < 0.7}
    # 표준검사 사전·사후 문항 단어는 훈련에서 뺀다 — 향상도가 문항 암기를 재지 않게(축 I, 폼 판본 동결).
    import assessment as _asmt
    test_words = _asmt.test_only_words()
    words = []
    for w in _curriculum.WORD_BANK:
        if w["word"] in test_words:
            continue
        pri = max(1, 4 - int(w.get("tier", 1)))       # tier1→3, tier2→2, tier3→1
        if weak:
            try:
                if any(v in weak for v in _wv(w["word"])):
                    pri += 2                            # 약점 비심 포함 단어를 더 자주
            except Exception:
                pass
        words.append({**w, "priority": pri})
    pairs = [p for p in _curriculum.MINIMAL_PAIRS if p.get("a") not in test_words and p.get("b") not in test_words]
    return {"words": words, "minimal_pairs": pairs}


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
        # 정답 여부는 서버가 재계산(클라이언트 data.correct를 신뢰하지 않음 — 숙달·해금·평가 조작 방지).
        # chosen이 없는 구버전 호출만 data.correct로 폴백.
        correct = (data.chosen == data.word) if data.chosen is not None else bool(data.correct)
        sp.attempts += 1
        if correct:
            sp.correct += 1
        sp.mastery_score = (sp.correct / sp.attempts * 100) if sp.attempts else 0.0
        sp.status = "mastered" if (sp.attempts >= _STAGE2_MIN_ATTEMPTS and sp.mastery_score >= _STAGE2_MASTERY) else "in_progress"
        # 취약 입모양 반영 — 오답이면 단어의 모든 유명 viseme을 오류로 누적(단어 인식 실패 신호).
        # 예전엔 단어 학습이 개인화(WeakViseme)에 전혀 기여하지 못했다.
        vids, features = await _weak_visemes_for_text(data.word)
        await _bump_weak_visemes(current_user.id, vids,
                                 vids if not correct else [], features, db)
        # 오답이면 '무엇을 무엇으로 읽었는지'를 자모·입모양 단위로 분석(근거 기반 피드백 + 혼동행렬 데이터)
        confusions = []
        if not correct and data.chosen and data.chosen != data.word:
            from scoring import viseme_confusions
            confusions = viseme_confusions(data.word, data.chosen)
        from database import TrialAttempt
        db.add(TrialAttempt(user_id=current_user.id, stage=2, item_type="word",
                            target=data.word, chosen=data.chosen, correct=correct, confusions=confusions))
        if not correct:
            await _srs_schedule_wrong(current_user.id, "word", data.word, db)
        award = _award_xp_and_streak(current_user, 15 if correct else 3)
        await db.commit()
        await db.refresh(sp)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise _server_error(e, "word answer failed")
    return {"mastery_score": round(sp.mastery_score, 1), "attempts": sp.attempts,
            "mastered": sp.status == "mastered",
            "xp_gained": award["xp_gained"], "streak_count": award["streak_count"],
            "confusions": confusions}


# ── 간격 반복 복습 (SRS) ──────────────────────────────────────────────────
@app.get("/api/review/due")
async def review_due(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """오늘까지 복습 예정인 독화 항목(입모양/단어)만. 말하기 예정은 /api/speak/review가 별도 반환."""
    from database import ReviewItem
    from sqlalchemy import select
    today = _sr_date.today().isoformat()
    r = await db.execute(select(ReviewItem).where(
        ReviewItem.user_id == current_user.id, ReviewItem.due_date <= today,
        ReviewItem.kind.in_(["viseme", "word"])).order_by(ReviewItem.due_date))
    items = r.scalars().all()
    out = []
    for it in items:
        # created_at = 처음 복습 큐에 들어온 시각, updated_at = 마지막으로 다시 푼 시각(목록의 상대 날짜용)
        entry = {"kind": it.kind, "ref": it.ref, "due_date": it.due_date,
                 "created_at": _iso_utc(it.created_at), "updated_at": _iso_utc(it.updated_at)}
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
    """복습 결과로 다음 등장일 재조정(SM-2). ease·반복에 따라 간격이 늘고, 충분히 커지면 졸업(제거)."""
    import srs
    # 공용 보상 — 복습도 XP·스트릭에 기여(복습만 한 날 스트릭이 끊기던 문제 해결)
    award = _award_xp_and_streak(current_user, 10 if data.correct else 3)
    reward = {"xp_gained": award["xp_gained"], "streak_count": award["streak_count"]}
    res = await _srs_apply(current_user.id, data.kind, data.ref,
                           srs.quality_from_correct(data.correct), db, create=False)
    await db.commit()
    return {"ok": True, "removed": res["removed"], "next_due": res["due_date"],
            "interval_days": res["interval_days"], **reward}


# ── 공용 복습 유틸 — 두 기둥(독화·말하기)이 동일 구조(예정/틀림/북마크)를 쓰도록 ──
async def _sr_touch(user_id: int, kind: str, ref: str, correct: bool, db, score: float = None):
    """SRS 큐 유지(SM-2) — 틀리면 내일 재등장(신규면 등록), 맞으면 ease·반복에 따라 간격을 늘려
    충분히 커지면 졸업. 점수(score 0~100)가 오면 이진 대신 등급(quality)으로 반영한다.
    커밋은 호출부에서. review/answer와 동일한 규칙."""
    import srs
    quality = srs.quality_from_score(score) if score is not None else srs.quality_from_correct(correct)
    await _srs_apply(user_id, kind, ref, quality, db, create=True)


async def _due_refs(user_id: int, kinds, db):
    """오늘까지 예정인 ReviewItem ref 목록(kinds 중 하나)."""
    from database import ReviewItem
    from sqlalchemy import select
    today = _sr_date.today().isoformat()
    r = await db.execute(select(ReviewItem).where(
        ReviewItem.user_id == user_id, ReviewItem.kind.in_(list(kinds)),
        ReviewItem.due_date <= today).order_by(ReviewItem.due_date))
    return [it.ref for it in r.scalars().all()]


async def _bookmark_refs(user_id: int, domain: str, db):
    """해당 기둥(domain) 북마크의 (id, text) 목록."""
    from database import Bookmark
    from sqlalchemy import select
    r = await db.execute(select(Bookmark).where(
        Bookmark.user_id == user_id, Bookmark.domain == domain).order_by(Bookmark.created_at.desc()))
    return [{"id": b.id, "text": b.sentence} for b in r.scalars().all()]


# ── 3단계 문맥 추론(closure) + 대화 채점 + 적응형 난이도(Phase 3·4) ──────────
async def _kt_recommend(user_id: int, db: AsyncSession) -> dict:
    """WeakViseme 기록 → 지식추적 추천({mastery, target_visemes, level, coverage})."""
    import knowledge_tracing as _kt
    from database import WeakViseme
    from sqlalchemy import select
    r = await db.execute(select(WeakViseme).where(WeakViseme.user_id == user_id))
    records = [{"viseme_id": w.viseme_id, "error_count": w.error_count,
                "total_attempts": w.total_attempts, "last_error_at": w.last_error_at}
               for w in r.scalars().all()]
    return _kt.recommend(records, k=2)


def _training_closures() -> list:
    """훈련용 문맥 문항 — 정답이나 보기에 표준검사 문항 단어가 든 항목은 뺀다(축 I, 문항 노출 방지)."""
    import assessment as _asmt
    tw = _asmt.test_only_words()
    return [c for c in _curriculum.CLOSURE_ITEMS
            if c["answer"] not in tw and not (set(c.get("options") or []) & tw)]


@app.get("/api/curriculum/closure")
async def curriculum_closure(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """문맥 추론 항목(빈칸+비슷하게 보이는 보기). 눈으로 구별 안 되니 문맥으로 답을 고른다.

    지식추적 표적 입모양을 정답에 많이 담은 항목부터 준다(축 G). 적중 수가 같은 항목끼리는
    사용자·날짜로 정한 순서로 섞어, 날마다 같은 문항부터 시작하지 않게 한다.
    """
    import random
    import content_rules as _crules
    from datetime import date
    rec = await _kt_recommend(current_user.id, db)
    tv = set(rec["target_visemes"])
    items = _training_closures()
    random.Random(f"{current_user.id}:{date.today().isoformat()}").shuffle(items)
    # 안정 정렬 — 같은 적중 수 안에서는 섞인 순서가 유지된다
    items.sort(key=lambda c: -len(set(_crules.word_visemes(c["answer"])) & tv))
    return {"items": items, "target_visemes": rec["target_visemes"]}


class ClosureAnswer(BaseModel):
    item_id: str       # 문맥 추론 항목 id(정답은 서버가 CLOSURE_ITEMS에서 찾는다)
    chosen: str        # 사용자가 고른 보기


@app.post("/api/curriculum/closure-answer")
async def curriculum_closure_answer(data: ClosureAnswer, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """문맥 추론(MWIS) 시행 채점 — 정답은 서버가 재계산한다(클라이언트 정오답을 신뢰하지 않음).
    시행 기록(TrialAttempt)·자모 혼동 피드백에 더해 3단계 숙달·취약 입모양·SRS·XP까지 잇는다."""
    item = next((it for it in _curriculum.CLOSURE_ITEMS if it["id"] == data.item_id), None)
    if item is None:
        raise HTTPException(status_code=400, detail="unknown closure item")
    answer = item["answer"]
    correct = data.chosen == answer
    from scoring import viseme_confusions
    from database import TrialAttempt
    confusions = [] if correct else viseme_confusions(answer, data.chosen)
    try:
        db.add(TrialAttempt(user_id=current_user.id, stage=3, item_type="closure",
                            target=answer, chosen=data.chosen, correct=correct, confusions=confusions))
        # 3단계(문맥 추론) 숙달 — 문장 연습과 같은 트랙에 성공/시도 누적
        await _bump_stage_progress(
            current_user.id, 3, correct, _STAGE3_MIN_ATTEMPTS, _STAGE3_MASTERY, db)
        # 취약 입모양 — 오답이면 정답 단어의 유명 viseme들을 오류로 누적(문맥으로도 못 가른 입모양)
        vids, features = await _weak_visemes_for_text(answer)
        await _bump_weak_visemes(current_user.id, vids,
                                 vids if not correct else [], features, db)
        if not correct:
            await _srs_schedule_wrong(current_user.id, "word", answer, db)
        award = _award_xp_and_streak(current_user, 15 if correct else 3)
        await db.commit()
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise _server_error(e, "closure answer failed")
    return {"correct": correct, "answer": answer, "confusions": confusions,
            "xp_gained": award["xp_gained"], "streak_count": award["streak_count"]}


@app.get("/api/curriculum/confusion-matrix")
async def curriculum_confusion_matrix(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """시행 기록(TrialAttempt)에서 자모 혼동행렬을 집계 — 개인별 헷갈림 리포트·평가자료용.
    '무엇을 무엇으로 읽었나(target→read)'를 빈도순으로, 입모양이 같아 헷갈린 비율도 함께 낸다."""
    from database import TrialAttempt
    from sqlalchemy import select
    r = await db.execute(select(TrialAttempt).where(TrialAttempt.user_id == current_user.id))
    rows = r.scalars().all()
    jamo = {}          # (target, read) -> {count, same}
    same_cnt = tot_cf = 0
    n_wrong = sum(1 for a in rows if not a.correct)
    for a in rows:
        for cf in (a.confusions or []):
            key = (cf.get("target"), cf.get("read"))
            e = jamo.setdefault(key, {"count": 0, "same_viseme": 0})
            e["count"] += 1
            tot_cf += 1
            if cf.get("same_viseme"):
                e["same_viseme"] += 1; same_cnt += 1
    jamo_list = sorted(
        [{"target": t, "read": rd, "count": v["count"], "same_viseme": v["same_viseme"]}
         for (t, rd), v in jamo.items()], key=lambda x: -x["count"])[:30]
    return {"trials": len(rows), "wrong": n_wrong, "confusion_count": tot_cf,
            "same_viseme_ratio": round(same_cnt / tot_cf, 3) if tot_cf else 0.0,
            "jamo_confusions": jamo_list}


@app.get("/api/eval/summary")
async def eval_summary(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """학습 효과 리포트 — 개인별 시행 기록으로 학습곡선·단계별 도달 시행수·초기 대비 최근
    향상도를 집계한다. 공모전 평가/효과성 근거용. 데이터가 적으면 각 지표를 null·빈 배열로
    돌려 프론트가 '데이터가 쌓이면 표시' 상태를 그릴 수 있게 한다.

    지표
    - learning_curve: 선다형 시행(TrialAttempt)을 시간순 8구간으로 나눈 정확도 추이.
    - baseline_vs_recent: 첫 1/3 vs 마지막 1/3 정확도(통제된 사전/사후는 아니며 '관찰된 향상').
    - by_item_type: 입모양·단어·문맥추론별 정확도.
    - trials_to_criterion: 단계별 숙달까지 걸린(또는 현재까지의) 시도수.
    - same_viseme_ratio: 오답 중 '입모양이 같아' 헷갈린 비율(시각 혼동성 근거).
    - sentence_trend: 문장 채점(Progress) 점수의 시간순 추이.
    """
    from database import TrialAttempt, Progress, StageProgress
    from sqlalchemy import select

    def bucketize(items, key, n_bins=8):
        """시간순 items를 최대 n_bins개 연속 구간으로 나눠 각 구간의 평균(key)·개수를 낸다."""
        if not items:
            return []
        n = len(items)
        bins = min(n_bins, n)
        out = []
        for b in range(bins):
            lo = (n * b) // bins
            hi = (n * (b + 1)) // bins
            seg = items[lo:hi]
            if not seg:
                continue
            out.append({"bin": b + 1, "n": len(seg),
                        "value": round(sum(key(x) for x in seg) / len(seg), 3)})
        return out

    # ── 선다형 시행 ──────────────────────────────────────────────
    tr = (await db.execute(
        select(TrialAttempt).where(TrialAttempt.user_id == current_user.id)
        .order_by(TrialAttempt.created_at.asc()))).scalars().all()
    n_tr = len(tr)
    n_correct = sum(1 for a in tr if a.correct)

    learning_curve = bucketize(tr, lambda a: 1.0 if a.correct else 0.0)

    baseline_vs_recent = None
    if n_tr >= 9:                       # 1/3씩 나누려면 최소 9시행
        k = n_tr // 3
        early = tr[:k]; late = tr[-k:]
        eb = sum(1 for a in early if a.correct) / len(early)
        lb = sum(1 for a in late if a.correct) / len(late)
        baseline_vs_recent = {
            "baseline_acc": round(eb * 100, 1), "recent_acc": round(lb * 100, 1),
            "delta_pp": round((lb - eb) * 100, 1), "n_each": k,
            "note": "통제된 사전/사후가 아니라 시행 순서 기준 초기 1/3 vs 최근 1/3 정확도"}

    by_item_type = []
    for it, label in (("viseme", "입모양 인지"), ("word", "단어"), ("closure", "문맥 추론")):
        seg = [a for a in tr if a.item_type == it]
        if seg:
            by_item_type.append({"item_type": it, "label": label, "n": len(seg),
                                 "accuracy": round(sum(1 for a in seg if a.correct) / len(seg) * 100, 1)})

    # 오답 중 같은 입모양 혼동 비율
    same_cnt = tot_cf = 0
    for a in tr:
        for cf in (a.confusions or []):
            tot_cf += 1
            if cf.get("same_viseme"):
                same_cnt += 1
    same_viseme_ratio = round(same_cnt / tot_cf, 3) if tot_cf else None

    # ── 단계별 도달 시행수 ───────────────────────────────────────
    sps = (await db.execute(
        select(StageProgress).where(StageProgress.user_id == current_user.id)
        .order_by(StageProgress.stage.asc()))).scalars().all()
    _STAGE_MIN = {1: _STAGE1_MIN_ATTEMPTS, 2: _STAGE2_MIN_ATTEMPTS, 3: _STAGE3_MIN_ATTEMPTS, 4: _STAGE4_MIN_ATTEMPTS}
    _STAGE_NAME = {1: "입모양 인지", 2: "단어", 3: "문장", 4: "대화"}
    # 한 단계에 StageProgress 행이 여러 개일 수 있어(과거 데이터·경쟁 삽입) 단계별로 합산한다.
    agg = {}  # stage -> {attempts, correct, mastery, mastered}
    for sp in sps:
        if sp.stage not in _STAGE_NAME:
            continue
        a = agg.setdefault(sp.stage, {"attempts": 0, "correct": 0, "mastery": 0.0, "mastered": False})
        a["attempts"] += sp.attempts or 0
        a["correct"] += sp.correct or 0
        a["mastery"] = max(a["mastery"], sp.mastery_score or 0.0)
        a["mastered"] = a["mastered"] or (sp.status == "mastered")
    trials_to_criterion = []
    for stage in sorted(agg):
        a = agg[stage]
        trials_to_criterion.append({
            "stage": stage, "name": _STAGE_NAME[stage],
            "status": "mastered" if a["mastered"] else ("in_progress" if a["attempts"] else "locked"),
            "attempts": a["attempts"], "correct": a["correct"],
            "mastery_score": round(a["mastery"], 1),
            "criterion_attempts": _STAGE_MIN.get(stage),
            "mastered": a["mastered"]})

    # ── 문장 채점 추이 ───────────────────────────────────────────
    prog = (await db.execute(
        select(Progress).where(Progress.user_id == current_user.id)
        .order_by(Progress.created_at.asc()))).scalars().all()
    sentence_trend = bucketize(prog, lambda p: p.score or 0.0)
    sentence_avg = round(sum(p.score or 0 for p in prog) / len(prog), 1) if prog else None

    return {
        "overview": {
            "total_trials": n_tr,
            "trial_accuracy": round(n_correct / n_tr * 100, 1) if n_tr else None,
            "total_sentences": len(prog),
            "sentence_avg_score": sentence_avg,
        },
        "learning_curve": learning_curve,
        "baseline_vs_recent": baseline_vs_recent,
        "by_item_type": by_item_type,
        "same_viseme_ratio": same_viseme_ratio,
        "trials_to_criterion": trials_to_criterion,
        "sentence_trend": sentence_trend,
    }


class ScoreRequest(BaseModel):
    correct: str
    user_answer: str


@app.post("/api/score", dependencies=[Depends(ratelimit.rate_limit(60, 60, "llm"))])
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
        # 취약 입모양 — 정답 문장의 오류 비심 반영(대화도 개인화에 기여)
        vids, features = await _weak_visemes_for_text(data.correct)
        await _bump_weak_visemes(current_user.id, vids, r.get("viseme_errors", []), features, db)
        award = _award_xp_and_streak(current_user, int(score * 1.5))
        await db.commit()
        return {"score": score, "feedback": r.get("feedback", {}),
                "phoneme_accuracy": r.get("phoneme_accuracy", {}),
                "xp_gained": award["xp_gained"], "streak_count": award["streak_count"]}
    except Exception as e:
        await db.rollback()
        raise _server_error(e, "score failed")


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


@app.get("/api/curriculum/next")
async def curriculum_next(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """지식추적 개인화 — 취약 음소를 표적으로 다음에 연습할 콘텐츠를 추천한다.

    WeakViseme 기록에서 viseme별 숙달도를 추정(BKT 경량판)해 가장 약한 음소를 표적으로
    삼고, 대량화된 단어·최소대립쌍·문맥 문항 중 그 음소를 포함하고 난이도가 맞는 것을 앞세운다.
    """
    import content_rules as _crules

    rec = await _kt_recommend(current_user.id, db)
    # 표준검사 사전·사후 문항 단어는 훈련 추천에서도 뺀다(축 I, 문항 노출 방지).
    import assessment as _asmt
    tw = _asmt.test_only_words()
    bank = [w for w in _curriculum.WORD_BANK if w["word"] not in tw]
    pairs = [p for p in _curriculum.MINIMAL_PAIRS if p.get("a") not in tw and p.get("b") not in tw]
    # strict=True: 표적 음소 적중 콘텐츠가 충분하면 무적중을 걸러 개인화를 강화(부족하면 자동 정렬 폴백)
    sel = _crules.select_personalized(
        bank, pairs, _training_closures(),
        rec["target_visemes"], rec["level"], strict=True)

    targets = []
    for v in rec["target_visemes"]:
        les = _curriculum.lesson_by_id(v)
        if les:
            targets.append({"viseme_id": v, "name": les["name"], "teach": les["teach"],
                            "demo_syllable": _curriculum.DEMO_SYLLABLE.get(v),
                            "mastery": rec["mastery"].get(v)})
    return {
        "mastery": rec["mastery"], "level": rec["level"], "coverage": rec["coverage"],
        "target_visemes": rec["target_visemes"], "targets": targets,
        "words": sel["words"], "minimal_pairs": sel["pairs"], "closures": sel["closures"],
    }


class MouthAttempt(BaseModel):
    viseme_id: int
    score: float  # 0~100 (웹캠 입모양 코사인 채점)
    # 조음 교정 세션 요약(축 E-9, 선택) — 관찰 차원 평균 |목표-관찰|의 처음·끝 값(0~1)과 표본 수
    gap_start: Optional[float] = None
    gap_end: Optional[float] = None
    n_samples: int = 0


@app.post("/api/curriculum/mouth-attempt")
async def curriculum_mouth_attempt(data: MouthAttempt, current_user=Depends(get_current_user),
                                  db: AsyncSession = Depends(get_db)):
    """웹캠 입모양 채점 결과를 학습 기록에 반영(축 D → 지식추적 연결).

    점수가 임계 미만이면 해당 viseme의 오답으로 누적한다. 이 기록이 WeakViseme에 쌓여
    지식추적(개인화)과 시각 증강 페이딩의 근거가 된다.
    """
    from database import WeakViseme
    from sqlalchemy import select
    from engine import get_viseme_feature
    from datetime import datetime

    passed = data.score >= 60
    r = await db.execute(select(WeakViseme).where(
        WeakViseme.user_id == current_user.id, WeakViseme.viseme_id == data.viseme_id))
    wv = r.scalar_one_or_none()
    if wv:
        wv.total_attempts += 1
        if not passed:
            wv.error_count += 1
            wv.last_error_at = datetime.utcnow()
    else:
        wv = WeakViseme(user_id=current_user.id, viseme_id=data.viseme_id,
                        total_attempts=1, error_count=0 if passed else 1,
                        last_error_at=datetime.utcnow(),
                        phonological_feature=get_viseme_feature(data.viseme_id))
        db.add(wv)
    # 조음 교정 세션 요약(E-9) — 처음·끝 오차가 둘 다 0~1 범위일 때만 남긴다(원본 계수는 받지 않는다)
    session_saved = False
    gs, ge = data.gap_start, data.gap_end
    if gs is not None and ge is not None and 0 <= gs <= 1 and 0 <= ge <= 1 and data.n_samples >= 2:
        from database import ArticulationSession
        db.add(ArticulationSession(user_id=current_user.id, viseme_id=data.viseme_id,
                                   score=round(data.score, 1), gap_start=round(gs, 3), gap_end=round(ge, 3),
                                   n_samples=min(int(data.n_samples), 10000)))
        session_saved = True
    await db.commit()
    return {"ok": True, "passed": passed, "viseme_id": data.viseme_id, "score": round(data.score, 1),
            "session_saved": session_saved}


@app.get("/api/analysis/articulation")
async def analysis_articulation(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """웹캠 조음 교정 전후 오차(축 E-9) — 세션 처음과 끝의 관찰 차원 평균 |목표−관찰|.
    change가 음수면 세션 안에서 목표에 가까워졌다는 뜻이다. 첫 세션들과 최근 세션들도 따로 준다."""
    import articulation as _art
    from database import ArticulationSession
    from sqlalchemy import select
    r = await db.execute(select(ArticulationSession).where(ArticulationSession.user_id == current_user.id)
                         .order_by(ArticulationSession.created_at))
    rows = [{"viseme_id": x.viseme_id, "gap_start": x.gap_start, "gap_end": x.gap_end,
             "created_at": x.created_at} for x in r.scalars().all()]
    out = _art.summarize_sessions(rows)
    k = min(5, len(rows) // 2)   # 세션이 쌓이면 처음 k개 대 최근 k개로 세션 사이 변화도 본다
    out["early"] = _art.summarize_sessions(rows[:k])["gap_start"] if k else None
    out["recent"] = _art.summarize_sessions(rows[-k:])["gap_start"] if k else None
    return out


@app.get("/api/cues")
async def get_cues(text: str, personalize: bool = True, max_cues: int | None = None,
                  focus: bool = False,
                  current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """시각 증강(축 J) — 문장에서 '안 드러나는 자질'(격음·경음·비음)에 기호를 얹을 지점을 반환.

    동구형이음은 입모양이 같아 눈으로 못 가르므로, 그 순간의 조음 자질에 대응하는 최소
    기호를 프론트가 SVG로 겹쳐 준다. 로그인 유저는 숙달도(지식추적)로 이미 익숙한 음소의
    기호를 소거(페이딩)한다. focus=true면 아직 약한 표적 음소에만 기호를 남긴다(집중 학습).
    """
    import cue_overlay as _cue
    mastery = None
    target_visemes = None
    if personalize:
        import knowledge_tracing as _kt
        from database import WeakViseme
        from sqlalchemy import select
        r = await db.execute(select(WeakViseme).where(WeakViseme.user_id == current_user.id))
        records = [{"viseme_id": w.viseme_id, "error_count": w.error_count,
                    "total_attempts": w.total_attempts, "last_error_at": w.last_error_at}
                   for w in r.scalars().all()]
        mastery = _kt.estimate_mastery(records)
        if focus and mastery:
            # 표적 = 아직 덜 익힌(숙달 0.85 미만) 비심만 → 그 음소 기호만 남겨 집중
            target_visemes = [v for v, m in mastery.items() if m < 0.85]
    cues = _cue.generate_cues(text or "", target_visemes=target_visemes, mastery=mastery,
                              max_cues=max_cues if (max_cues and max_cues > 0) else None)
    return {"text": text, "cues": cues, "legend": _cue.CUE_FEATURES}


# ── 콘텐츠 사람검수(축 G '이중 게이트'의 사람 단계) — 인앱 운영자용 ──────────────
# 운영자 전용이라 기본 비활성(LIPLAB_REVIEW=1일 때만). 콘텐츠 승인은 커리큘럼에 영향을 주므로
# 아무나 못 하게 게이트한다(§4.9 최소권한). 활성 시 인증된 사용자가 후보를 승인/반려한다.
def _review_gate(user=None):
    """콘텐츠 검수는 운영자 전용. LIPLAB_REVIEW=1로 켜고, LIPLAB_ADMIN_EMAILS(쉼표 구분)에 든 계정만
    쓸 수 있다. 목록이 비어 있으면 누구도 못 쓴다(켜기만 하면 공용 데모 계정으로 들어온 방문자도
    승인·반려할 수 있던 문제, §4.9 표11 ③)."""
    if os.getenv("LIPLAB_REVIEW") != "1":
        raise HTTPException(status_code=403, detail="콘텐츠 검수 기능이 비활성화되어 있습니다(운영자 전용).")
    admins = {e.strip().lower() for e in os.getenv("LIPLAB_ADMIN_EMAILS", "").split(",") if e.strip()}
    email = (getattr(user, "email", "") or "").lower()
    if not email or email == _DEMO_EMAIL or email not in admins:
        raise HTTPException(status_code=403, detail="운영자 계정만 콘텐츠를 검수할 수 있습니다.")


@app.get("/api/admin/content/candidates")
async def content_candidates(current_user=Depends(get_current_user)):
    """검수 대기 후보(승인·반려 안 된 것) + 종류별 건수. 축 G 사람검수 게이트."""
    _review_gate(current_user)
    import content_review as _cr
    return _cr.pending()


class ContentReviewReq(BaseModel):
    kind: str          # words | pairs | closures
    item: dict
    decision: str      # approve | reject


@app.post("/api/admin/content/review", dependencies=[Depends(ratelimit.rate_limit(60, 60, "content-review"))])
async def content_review_action(req: ContentReviewReq, current_user=Depends(get_current_user)):
    """후보 1건 승인/반려 → approved.json / rejected.json 반영(중복 없이)."""
    _review_gate(current_user)
    import content_review as _cr
    try:
        return _cr.review(req.kind, req.item or {}, req.decision)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/articulation/guide")
async def get_articulation_guide(text: str, current_user=Depends(get_current_user)):
    """조음 가이드(축 E) — 문장을 음절·자모로 풀어 음소별 '보이지 않는 조음'을 가르친다.

    독화·웹캠은 개구·원순·양순 폐쇄 같은 겉조음만 잡는다. 소리를 가르는 결정적 조음(혀 위치,
    조음 위치·방식)은 입 안에 있어 안 보이므로, 목표 음소마다 혀·조음 위치·방식을 글로 가르친다.
    """
    import articulation as _art
    return _art.articulation_guide(text or "")


class ArticulationFeedbackReq(BaseModel):
    viseme: int
    observed: dict  # 웹캠 역추정 관찰 조음 {jaw, round, close} (0~1)


@app.post("/api/articulation/feedback")
async def post_articulation_feedback(req: ArticulationFeedbackReq,
                                     current_user=Depends(get_current_user)):
    """조음 교정(축 E) — 웹캠 역추정 관찰 조음(jaw/round/close)을 목표 비심과 비교해 교정 방향을
    낸다("입을 더 벌리세요"). 관찰로는 안 잡히는 혀·조음 위치는 목표 조음 교육문을 함께 준다."""
    import articulation as _art
    return _art.articulation_correction(req.viseme, req.observed or {})


class PlacementScoreReq(BaseModel):
    items: list
    responses: dict
    form: str = "placement"   # placement | A(사전) | B(사후)


@app.get("/api/assessment/placement")
async def assessment_placement(n: int = 8, form: str = None,
                               current_user=Depends(get_current_user)):
    """디지털 독화 배치검사 문항(축 I) — 지각 난이도로 통제한 입모양 단어 4지선다.
    오답 보기는 정답과 시각적으로 혼동되는(동구형이음·최소대립) 단어를 우선 배치한다.
    form='A'/'B'를 주면 향상도검사용 동형(난이도 매칭) 사전/사후 폼을 반환한다."""
    import assessment as _asmt
    words = [w["word"] for w in _curriculum.WORD_BANK]
    if form in ("A", "B"):
        # 사전·사후는 동결된 판본(data/assessment/forms_v1.json)을 쓴다 — 콘텐츠가 바뀌어도 같은 문항.
        forms = _asmt.frozen_forms(words)
        return {"items": forms.get(form, []), "form": form, "version": forms.get("version")}
    items = _asmt.build_placement_items(words, n=n)
    return {"items": items, "form": "placement"}


class PlacementNextReq(BaseModel):
    asked: list = []
    responses: dict = {}
    n: int = 8


@app.post("/api/assessment/placement/next")
async def assessment_placement_next(data: PlacementNextReq,
                                    current_user=Depends(get_current_user)):
    """적응형 배치검사(축 I) — 지금까지의 정오답으로 능력 θ를 추정해 다음 문항 1개를 고른다.
    난이도지수(C)에 θ를 맞추고 누적 오답 자질을 표적으로 겨냥한다. 고정 N 도달·문항 소진 시 done.
    동형폼(A/B) 향상도검사는 이 경로를 타지 않아 사전·사후 통제 비교의 불변성을 지킨다."""
    import assessment as _asmt
    words = [w["word"] for w in _curriculum.WORD_BANK]
    n = max(3, min(20, data.n or 8))
    asked = data.asked or []
    responses = data.responses or {}
    est = _asmt.estimate_ability(asked, responses)
    if len(asked) >= n:
        return {"item": None, "done": True, "ability": est["ability"],
                "target_visemes": est["error_visemes"], "index": len(asked), "n": n}
    item = _asmt.select_next_item(asked, responses, words)
    return {"item": item, "done": item is None, "ability": est["ability"],
            "target_visemes": est["error_visemes"], "index": len(asked) + 1, "n": n}


@app.post("/api/assessment/score")
async def assessment_score(data: PlacementScoreReq, current_user=Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    """배치검사/향상도검사 채점 → 추정 수준·음소별 오류 프로파일·시작 단계 추천.
    결과를 PlacementResult로 저장해 사전(A)·사후(B) 통제 비교(향상도)를 가능케 한다."""
    import assessment as _asmt
    from engine import get_viseme_feature
    result = _asmt.score_placement(data.items, data.responses)
    form = data.form or "placement"
    version = None
    if form in ("A", "B"):
        version = (_asmt.frozen_forms(build_if_missing=False) or {}).get("version") or "unfrozen"
    try:
        from database import PlacementResult
        db.add(PlacementResult(
            user_id=current_user.id, form=form,
            total=result["total"], correct=result["correct"], accuracy=result["accuracy"],
            ability=result["ability"], level=result["level"],
            error_visemes=result.get("error_visemes", []),
            error_phonemes=result.get("error_phonemes", []),
            form_version=version, item_log=result.get("item_log", []),
        ))
        # 검사 → 학습 순환(축 I-10): 문항의 입모양별 정오답을 취약 입모양 통계에 넣어, 첫 검사 결과가
        # 곧바로 개인화(지식추적·약점 출제)의 초기값이 되게 한다.
        for it in data.items or []:
            chosen = (data.responses or {}).get(it.get("id"))
            if chosen is None:
                continue
            vids = [v for v in (it.get("visemes") or []) if isinstance(v, int)]
            wrong = vids if chosen != it.get("word") else []
            await _bump_weak_visemes(current_user.id, vids, wrong,
                                     {str(v): get_viseme_feature(v) for v in vids}, db)
        await db.commit()
    except Exception as e:
        await db.rollback()  # 채점 결과 반환은 저장 실패와 무관하게 보장
        print(f"[WARN] placement result save failed: {e}")
    return result


@app.get("/api/assessment/history")
async def assessment_history(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """배치·향상도 검사 이력 — 첫 검사(baseline)와 최근 검사, 그리고 향상도(delta)를 반환.
    검사가 2회 이상이면 정답률·능력·수준의 증감과 극복한 취약 입모양을 함께 준다.
    (병합 메모: 저장 테이블이 AssessmentResult → PlacementResult로 통일됐다. 폼(A/B) 구분 없는
    단순 첫/최근 비교는 이 엔드포인트, 동형 폼 통제 비교는 /api/assessment/progression.)"""
    import assessment as _asmt
    from database import PlacementResult
    from sqlalchemy import select
    r = await db.execute(select(PlacementResult).where(
        PlacementResult.user_id == current_user.id).order_by(PlacementResult.created_at))
    rows = r.scalars().all()

    def _row(x):
        return {"accuracy": x.accuracy, "ability": x.ability, "level": x.level,
                "error_visemes": x.error_visemes or [],
                "at": x.created_at.isoformat() if x.created_at else None}
    if not rows:
        return {"count": 0, "baseline": None, "latest": None, "delta": None}
    baseline, latest = _row(rows[0]), _row(rows[-1])
    delta = _asmt.improvement_delta(baseline, latest) if len(rows) >= 2 else None
    return {"count": len(rows), "baseline": baseline, "latest": latest, "delta": delta}


@app.get("/api/assessment/benchmark")
async def assessment_benchmark(current_user=Depends(get_current_user)):
    """한국어 독화 표준 평가셋(축 C 공개 리소스). 난이도 3구간 층화·seed 고정(재현 가능).
    앱 내 표준 평가와 앱 밖 연구·교육이 동일 문항을 쓰도록 고정 벤치마크를 제공한다."""
    import perceptual as _perc
    bm = _perc.build_benchmark([w["word"] for w in _curriculum.WORD_BANK])
    return bm


@app.get("/api/assessment/resources")
async def assessment_resources(current_user=Depends(get_current_user)):
    """한국어 독화 공개 표준 리소스(축 C) — 동구형이음 사전·독화 난이도지수·최소대립쌍·
    표준 평가셋·(있으면)데이터 유래 자모 시각유사도를 한 자원으로 제공한다. 한국어 독화에는
    이런 표준 자원이 거의 없어, 앱 밖 연구·교육에서도 쓸 수 있게 노출한다."""
    import perceptual as _perc
    return _perc.build_standard_resources([w["word"] for w in _curriculum.WORD_BANK])


@app.get("/api/assessment/progression")
async def assessment_progression(current_user=Depends(get_current_user),
                                 db: AsyncSession = Depends(get_db)):
    """통제된 향상도(축 I) — 동형 폼 사전(A)·사후(B) 결과를 비교해 델타·음소별 오류 감소를 반환.
    A/B가 아직 없으면 가장 이른/최근 검사 회차로 대체 비교한다."""
    from database import PlacementResult
    from sqlalchemy import select
    rows = (await db.execute(
        select(PlacementResult).where(PlacementResult.user_id == current_user.id)
        .order_by(PlacementResult.created_at.asc())
    )).scalars().all()
    if len(rows) < 2:
        return {"available": False, "n": len(rows),
                "note": "사전·사후 검사가 2회 이상이면 향상도가 나옵니다."}
    a = next((r for r in rows if r.form == "A"), rows[0])          # 사전
    b = next((r for r in reversed(rows) if r.form == "B"), rows[-1])  # 사후
    if a.id == b.id:
        a, b = rows[0], rows[-1]
    err_a = {e["phoneme"]: e["count"] for e in (a.error_phonemes or []) if isinstance(e, dict)}
    err_b = {e["phoneme"]: e["count"] for e in (b.error_phonemes or []) if isinstance(e, dict)}
    phonemes = sorted(set(err_a) | set(err_b))
    per_phoneme = [{"phoneme": p, "before": err_a.get(p, 0), "after": err_b.get(p, 0),
                    "delta": err_b.get(p, 0) - err_a.get(p, 0)} for p in phonemes]
    return {
        "available": True,
        "pre": {"form": a.form, "accuracy": a.accuracy, "level": a.level, "ability": a.ability},
        "post": {"form": b.form, "accuracy": b.accuracy, "level": b.level, "ability": b.ability},
        "accuracy_delta": round(b.accuracy - a.accuracy, 3),
        "level_delta": b.level - a.level,
        "ability_delta": round(b.ability - a.ability, 3),
        "error_phoneme_change": per_phoneme,
        "homogeneous": (a.form == "A" and b.form == "B"),
    }


@app.get("/api/conversation/multi", dependencies=[Depends(ratelimit.rate_limit(30, 60, "llm-multi"))])
async def conversation_multi(speakers: int = 2, turns: int = 6,
                             current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """다자 대화 시나리오(축 H) — 여러 화자가 번갈아 말하는 짧은 대화(화자 식별 + 입모양 읽기).
    학습자의 약점 입모양이 든 승인 단어(G)를 대화에 넣도록 요청하고(H-3), 턴마다 닮은꼴 오답과
    빈칸 턴을 붙인다(H-4). answer_key는 서버 재채점용 서명 정답(H-9)이다."""
    import conversation_scenario as _conv
    import knowledge_tracing as _kt
    import content_rules as _crules
    from database import WeakViseme
    from sqlalchemy import select as _select
    from auth import SECRET_KEY, ALGORITHM
    from jose import jwt as _jwt
    from datetime import datetime as _dt, timedelta as _td
    try:
        rows = (await db.execute(_select(WeakViseme).where(WeakViseme.user_id == current_user.id))).scalars().all()
        rec = _kt.recommend([{"viseme_id": w.viseme_id, "error_count": w.error_count,
                              "total_attempts": w.total_attempts, "last_error_at": w.last_error_at}
                             for w in rows], k=2)
        targets = set(rec.get("target_visemes") or [])
        focus = [w["word"] for w in _curriculum.WORD_BANK
                 if targets and set(_crules.word_visemes(w["word"])) & targets][:30]
        import random as _rnd
        _rnd.shuffle(focus)
        conv = await _conv.generate_multi_conversation(speakers=speakers, turns=turns, focus_words=focus[:6])
    except Exception as e:
        raise _server_error(e, "conversation gen failed")
    key = {"uid": current_user.id, "sp": [t["speaker"] for t in conv["turns"]],
           "tx": [t["text"] for t in conv["turns"]],
           "cl": (conv.get("closure") or {}).get("answer"),
           "exp": _dt.utcnow() + _td(hours=3)}
    conv["answer_key"] = _jwt.encode(key, SECRET_KEY, algorithm=ALGORITHM)
    return conv


class MultiConvResultReq(BaseModel):
    speaker_correct: int = 0
    speaker_total: int = 0
    read_correct: int = 0
    read_total: int = 0
    read_hits: List[str] = []    # 립리딩(문맥추론) 정답 발화 텍스트
    read_misses: List[str] = []  # 오독 발화 텍스트
    # 서버 재채점(H-9) — answer_key가 있으면 아래 선택으로 서버가 다시 채점하고 위 집계값은 무시한다.
    answer_key: Optional[str] = None
    speaker_choices: List[Optional[int]] = []   # 턴별로 고른 화자 번호
    read_choices: List[Optional[str]] = []      # 턴별로 고른 문장(원문 또는 닮은꼴)
    closure_choice: Optional[str] = None        # 빈칸 턴에서 고른 단어


@app.post("/api/conversation/multi/result", dependencies=[Depends(ratelimit.rate_limit(30, 60, "llm"))])
async def conversation_multi_result(req: MultiConvResultReq,
                                    current_user=Depends(get_current_user),
                                    db: AsyncSession = Depends(get_db)):
    """다자대화(축 H) 세션 결과 기록·채점. 화자 식별 정확도와 립리딩(문맥추론) 정확도를 결합해
    종합 점수를 내고, 오독한 발화의 비심을 지식추적(WeakViseme)에 반영해 개인화(축 G)로 잇는다.
    (커리큘럼 단계 잠금·숙달 판정은 건드리지 않는다 — H는 실전 변형이라 보조 기록.)"""
    from database import WeakViseme
    from sqlalchemy import select as _select
    from engine import get_viseme_feature
    from content_rules import word_visemes
    from datetime import datetime as _dt

    scored = None
    if req.answer_key:
        import conversation_scenario as _conv
        from auth import SECRET_KEY, ALGORITHM
        from jose import jwt as _jwt, JWTError as _JWTError
        try:
            key = _jwt.decode(req.answer_key, SECRET_KEY, algorithms=[ALGORITHM])
        except _JWTError:
            raise HTTPException(status_code=400, detail="대화 정답 키가 유효하지 않습니다(만료 또는 변조).")
        if key.get("uid") != current_user.id:
            raise HTTPException(status_code=403, detail="다른 사용자의 대화입니다.")
        scored = _conv.score_multi(key, req.speaker_choices, req.read_choices, req.closure_choice)
        req.read_hits, req.read_misses = scored["read_hits"], scored["read_misses"]
        spk_acc, read_acc, combined = scored["speaker_accuracy"], scored["read_accuracy"], scored["combined"]
    else:
        # 구버전 화면(집계값만 보냄) 호환 — 화자식별·독해 평균
        spk_acc = (req.speaker_correct / req.speaker_total) if req.speaker_total else 0.0
        read_acc = (req.read_correct / req.read_total) if req.read_total else 0.0
        combined = round(100 * (0.5 * spk_acc + 0.5 * read_acc), 1)

    def _vis(texts):
        s = set()
        for t in texts or []:
            for v in word_visemes(t or ""):
                if 1 <= v <= 10:
                    s.add(v)
        return s
    missed = _vis(req.read_misses)
    hit = _vis(req.read_hits) - missed   # 같은 비심이 오독에도 있으면 오독을 우선한다
    for vid in (missed | hit):
        is_err = vid in missed
        r = await db.execute(_select(WeakViseme).where(
            WeakViseme.user_id == current_user.id, WeakViseme.viseme_id == vid))
        wv = r.scalar_one_or_none()
        if wv:
            wv.total_attempts += 1
            if is_err:
                wv.error_count += 1
                wv.last_error_at = _dt.utcnow()
        else:
            wv = WeakViseme(user_id=current_user.id, viseme_id=vid,
                            total_attempts=1, error_count=1 if is_err else 0,
                            last_error_at=_dt.utcnow() if is_err else None,
                            phonological_feature=get_viseme_feature(vid))
            db.add(wv)
    await db.commit()
    return {"combined": combined, "speaker_accuracy": round(spk_acc, 3),
            "read_accuracy": round(read_acc, 3), "recorded_visemes": sorted(missed | hit),
            "missed_visemes": sorted(missed),   # 오독한 발화의 입모양(복습·지식추적에 오답으로 반영)
            "closure_correct": (scored or {}).get("closure_correct"),
            "server_scored": scored is not None}


# ── 발화 커리큘럼(6단계) — 상태·게이팅·콘텐츠 ────────────────────────────────
import speak_curriculum as _speakcur


@app.post("/api/seed-demo")
async def seed_demo(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """데모 계정이 비어 있으면 더미 학습 기록을 채운다(멱등 — 기록 있으면 스킵)."""
    import demo_seed
    seeded = await demo_seed.run(current_user, db)
    return {"seeded": seeded}


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
    if _UNLOCK_ALL:
        for st in stages:
            if st.get("status") == "locked":
                st["status"] = "unlocked"
    return {"stages": stages}


@app.get("/api/speak/stage/{n}", dependencies=[Depends(ratelimit.rate_limit(60, 60, "llm-speakstage"))])
async def speak_stage_content(n: int, current_user=Depends(get_current_user)):
    """단계 콘텐츠(항목·모드·가이드).
    단어(4)·문장(5) 단계는 매번 AI로 새 문항을 생성해 변주를 준다(실패 시 큐레이션 풀 폴백).
    발성·모음·자음(0~3)은 정해진 음소 드릴이라 고정."""
    stg = _speakcur.get_stage(n)
    if not stg:
        raise HTTPException(status_code=404, detail="unknown stage")

    items = stg["items"]
    if os.getenv("LIPLAB_AI_ITEMS", "1") == "1" and stg["mode"] in ("word", "sentence"):
        try:
            import content_gen
            base = [it.get("target") for it in stg["items"]]
            if stg["mode"] == "word":
                gen = await content_gen.generate_words(n=10, max_syllable=3, avoid=base)
                ai_items = [{"target": w} for w in gen]
            else:
                ai_items = await content_gen.generate_sentences(n=8, avoid=base, with_intonation=True)
            if len(ai_items) >= 4:
                # AI 생성분을 앞에, 기존 풀을 뒤에 섞어 다양성 + 안정성 확보
                items = ai_items + stg["items"]
        except Exception as e:
            print(f"[WARN] speak AI items gen failed (stage {n}): {e}")

    return {
        "stage": stg["stage"], "title": stg["title"], "mode": stg["mode"],
        "desc": stg["desc"], "guide": stg["guide"], "icon": stg.get("icon", ""),
        "items": items,
    }


# ── 발화(말하기) 채점 — 단계 모드별 채점 + 진행률 + 코칭 ──────────────────────
@app.post("/api/speak/assess", dependencies=[Depends(ratelimit.rate_limit(40, 60, "audio"))])
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
    review: int = Form(0),
    mouth_confidence: float = Form(None),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """녹음 → (단계 모드에 따라) 지표/전사 채점 → 진행률 갱신 → 코칭.
    발성·운율(0·1)은 지표만으로, 모음·자음·단어·문장(2~5)은 Whisper 전사+음운 유사도."""
    data = await _read_audio_limited(audio)

    metrics = {"loudness": loudness, "pitch_range": pitch_range, "duration": duration,
               "pitch_start": pitch_start, "pitch_end": pitch_end}
    stg = _speakcur.get_stage(stage) if stage is not None else None
    mode = stg["mode"] if stg else "word"

    transcript = None
    confusions = []
    sim = None
    dgop_result = None
    assessment_method = None
    need_asr = (mode in ("phoneme", "word", "sentence")) or (stage is None)
    if need_asr:
        # 축 B — 전사 비의존 D-GOP 경로. 아래 환경변수가 설정된 경우에만 시도하고,
        # 실패(모델 미설치·정렬 실패 등)하면 조용히 전사 경로로 폴백한다.
        #
        # 모델이 둘인 이유(축 A): 정렬기는 뭉갠 발화에 강인해야 하고, 채점기는 정상 발화
        # 기준이어야 한다 — 채점기까지 강인해지면 뭉개도 점수가 높아져 변별력이 사라진다.
        # 근거는 docs/axis-a-training-plan.md §0, 구현은 dgop_acoustic.phone_confidences.
        #
        #   DGOP_ALIGNER_ID — 강제정렬용(축 A A-2 산출물)
        #   DGOP_SCORER_ID  — 채점용(축 A A-1 산출물). 생략 시 정렬기와 동일 모델.
        #   DGOP_MODEL_ID   — 구 변수명. 하위호환으로 정렬기 겸 채점기로 취급한다.
        #   DGOP_CALIBRATION — 표시용 점수 보정 앵커 JSON 경로. 생략 시
        #                      backend/data/dgop_calibration.json, 그것도 없으면 축 A 실측 내장값.
        #
        # 실제 발화 정확도 검증 전까지는 배포 기본값을 켜지 않는다(미설정 = 전사 경로).
        # (병합 메모 2026-09-21: 상대 브랜치는 torch만 있으면 D-GOP를 항상 주 경로로 썼지만,
        #  A-6 채점식 교체로 앵커 재적합 전까지 켜지 않는다는 STATUS.md 방침을 따른다.
        #  D-GOP가 켜지면 아래 융합에서 상대의 구간별(per-phone) 후기융합을 쓴다.)
        dgop_aligner_id = os.getenv("DGOP_ALIGNER_ID") or os.getenv("DGOP_MODEL_ID")
        dgop_scorer_id = os.getenv("DGOP_SCORER_ID") or dgop_aligner_id
        if dgop_aligner_id:
            try:
                import dgop_acoustic
                if not dgop_acoustic.HAS_ACOUSTIC:
                    raise RuntimeError("torch/torchaudio/transformers 미설치")
                result = await asyncio.to_thread(
                    dgop_acoustic.assess_text,
                    data, target, aligner_id=dgop_aligner_id, scorer_id=dgop_scorer_id,
                )
                if result.get("score") is not None:
                    dgop_result = result
                    # 표시용 보정 점수를 쓴다 — 원점수는 깨끗한 발화도 10점 안쪽이라
                    # 합격선(50·65)과 비교조차 되지 않는다. 보정 전 값은 응답의
                    # dgop.raw_score로 함께 나간다(축 A 한계 ② 대응).
                    sim = dgop_result["score"]
                    assessment_method = "dgop"
            except Exception as e:
                # 폴백으로 계속 진행하되 **조용히 넘어가지 않는다.** 비공개 HF 저장소
                # (duadnwls/liplab-dgop-*)는 HF_TOKEN 없이는 로드에 실패하는데, 그때
                # 전사 경로로 소리 없이 떨어지면 D-GOP가 꺼진 줄도 모르고 배포된다.
                print(f"[WARN] D-GOP 경로 실패 — 전사 경로로 폴백합니다 "
                      f"(aligner={dgop_aligner_id}): {type(e).__name__}: {e}")
                dgop_result = None

        if assessment_method != "dgop":
            from speak_service import transcribe, is_available
            if not is_available():
                raise HTTPException(status_code=503, detail="서버에 음성인식 모델(faster-whisper)이 없습니다.")
            try:
                transcript = await transcribe(data)
            except Exception as e:
                raise _server_error(e, "전사 실패")
            try:
                sc = await calculate_score(correct=target, user_answer=transcript, db=db)
                sim = sc.get("score", 0)
            except Exception:
                sim = 0.0
            try:
                from scoring import to_pronounced_jamos, align_jamos
                cj = to_pronounced_jamos(target.replace(" ", ""))
                uj = to_pronounced_jamos((transcript or "").replace(" ", ""))
                for cs, us in align_jamos(cj, uj):
                    if cs is None or us is None:
                        continue
                    if cs[0] and us[0] and cs[0] != us[0]:
                        confusions.append({"correct": cs[0], "confused_as": us[0]})
                    if cs[1] and us[1] and cs[1] != us[1]:
                        confusions.append({"correct": cs[1], "confused_as": us[1]})
            except Exception:
                pass
            assessment_method = "asr_transcript"

    note = ""
    passed = None
    progress = None
    if stage is not None and stg is not None:
        score, passed, note = _speakcur.score_attempt(stage, target, transcript, metrics, drill, sim)
        # 복습 세션은 채점·코칭만 하고 단계 진행도(숙달/해금)는 건드리지 않는다
        if review:
            sp = None
        else:
            sp = await _bump_speak_progress(current_user.id, stage, bool(passed),
                                            stg["min_attempts"], stg["mastery"], db)
    else:
        score = round(sim or 0.0, 1)
        sp = None

    # 축 B 오디오·비주얼 융합 — 웹캠 입모양(D) 신뢰도가 오면, 음향 점수가 낮을(불확실할)수록
    # 입모양에 더 가중해 최종 점수를 낸다(농인은 음성이 불안정하나 입모양은 상대적으로 안정적).
    av_fusion = None
    if mouth_confidence is not None and mouth_confidence >= 0:
        import dgop
        vis = mouth_confidence * 100 if mouth_confidence <= 1 else mouth_confidence
        # D-GOP 경로면 실측 불확실성을, 전사 경로면 기존 점수 기반 근사치를 쓴다.
        # 음소별(phones) 정보가 있으면 구간별 융합 — 음향이 뭉갠 '그 구간'일수록 영상 가중이
        # 국소적으로 커진다(계획서 B). 정렬됐고 채점 대상인 음소만 넣는다(어절 경계 제외).
        av_fusion = None
        if dgop_result:
            scored_phones = [p for p in (dgop_result.get("phones") or [])
                             if p.get("aligned") and p.get("scorable")]
            av_fusion = dgop.fuse_audio_visual_per_phone(scored_phones, vis)
        if av_fusion is None:
            audio_uncertainty = dgop_result["uncertainty"] if dgop_result else max(0.0, 1 - score / 100.0)
            av_fusion = dgop.fuse_audio_visual(score, audio_uncertainty, vis)
        score = av_fusion["score"]

    # 개별 시도 영속화(말하기 분석용 — 독화가 Progress에 쌓는 것과 대칭)
    from database import SpeakAttempt
    db.add(SpeakAttempt(
        user_id=current_user.id, stage=stage, mode=mode, target=target,
        transcript=transcript, score=score, passed=passed,
        loudness=loudness, pitch_range=pitch_range, duration=duration,
        pitch_start=pitch_start, pitch_end=pitch_end, confusions=confusions[:6],
    ))
    # SRS 복습 큐 유지 — 발음/단어/문장은 틀리면 예정 등록, 맞으면 간격 확장(세 기둥 공통).
    # 말하기는 0~100 점수가 있으므로 이진 대신 점수 등급으로 복습 간격을 조절한다(SM-2).
    if mode in ("phoneme", "word", "sentence") and passed is not None:
        await _sr_touch(current_user.id, "speak", target, bool(passed), db, score=score)
    await db.commit()
    if sp is not None:
        progress = {"stage": stage, "attempts": sp.attempts,
                    "mastery_score": round(sp.mastery_score, 1),
                    "mastered": sp.status == "mastered"}

    # 축 E — 모음 단계에서 목표가 단모음 음절('아'·'이' 등)이면 녹음의 포먼트(F1·F2)로 혀 높낮이·앞뒤
    # 교정 방향을 만든다(formants.py). 웹캠이 못 보는 혀 위치를 소리로 짚어 주는 경로다.
    vowel_fb = None
    if mode == "phoneme":
        import formants as _fm
        _v = _fm.target_vowel(target)
        if _v:
            try:
                _y = await asyncio.to_thread(_fm.decode_mono16k, data)
                vowel_fb = await asyncio.to_thread(_fm.vowel_feedback, _y, _v) if _y is not None else None
            except Exception as e:  # 교정 실패는 채점 결과와 무관
                print(f"[WARN] vowel formant feedback failed: {e}")

    # 발성·운율은 규칙 기반 note가 곧 구체 코칭, 모음~문장은 Claude 코칭(+억양 note)
    if mode in ("voicing", "prosody"):
        coaching = note
    else:
        from llm_service import generate_speaking_coaching
        coaching = await generate_speaking_coaching(target, transcript, score, confusions, metrics)
        if note:
            coaching = f"{coaching} {note}"
    if vowel_fb and vowel_fb.get("messages"):
        coaching = f"{coaching} {' '.join(vowel_fb['messages'])}".strip()

    # 프론트 음소 칩(SpeakingPractice)이 읽는 acoustic_dgop. 채점은 위 assess_text(naive)가 끝냈고,
    # 여기서는 그 결과를 화면용 모양으로만 옮긴다. 정렬됐고 채점 대상인 음소만 싣고, 자모 토큰의
    # 위치 접두(o:·n:·c:)는 떼어 label로 쓴다. D-GOP가 꺼져 있으면(기본) None.
    # (병합 메모 2026-09-23: 9/21 병합에서 구 계산부가 빠지고 반환 키만 남아 모든 요청이 NameError로 500이었다.)
    acoustic_dgop = None
    if dgop_result:
        acoustic_dgop = {
            "uncertainty": dgop_result.get("uncertainty"),
            "phones": [{**p, "label": (p.get("token") or "").split(":", 1)[-1].replace("|", " ").strip()}
                       for p in (dgop_result.get("phones") or [])
                       if p.get("aligned") and p.get("scorable")],
        }

    return {
        "transcript": transcript,
        "score": score,
        "passed": passed,
        "note": note,
        "confusions": confusions[:6],
        "coaching": coaching,
        "assessment_method": assessment_method,  # "dgop" | "asr_transcript" — 축 B 전환 투명성
        "dgop": dgop_result,
        "metrics": metrics,
        "av_fusion": av_fusion,
        "acoustic_dgop": acoustic_dgop,
        "vowel_feedback": vowel_fb,   # 축 E: {vowel, f1, f2, target_f1, target_f2, height, front, messages}
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
    wrong = []
    for t, r in seen.items():
        if (r.passed is False) or (r.score is not None and r.score < 70):
            wrong.append({"target": t, "stage": r.stage, "mode": r.mode,
                          "last_score": round(r.score or 0, 1)})
    wrong.sort(key=lambda x: x["last_score"])

    # 세 기둥 공통 구조: 예정(SRS) · 틀림 · 북마크
    due = await _due_refs(current_user.id, ["speak"], db)
    bookmarks = await _bookmark_refs(current_user.id, "speak", db)
    # 복습 세션에서 순회할 통합 목록(중복 제거) — 예정 → 틀림 → 북마크
    union, _seen = [], set()
    wrong_by_target = {item["target"]: item for item in wrong}
    for t in due + [w["target"] for w in wrong] + [b["text"] for b in bookmarks]:
        if t and t not in _seen:
            _seen.add(t)
            union.append({"target": t, **wrong_by_target.get(t, {})})
    return {
        "items": union[:30], "count": len(union),
        "buckets": {"due": len(due), "wrong": len(wrong), "bookmark": len(bookmarks)},
        "wrong": wrong[:15], "due": due[:15], "bookmarks": bookmarks[:15],
    }


class ConversationRequest(BaseModel):
    situation: str
    level: int = 1
    history: List[dict] = []


class ConversationResponse(BaseModel):
    text: str


@app.post("/api/conversation", response_model=ConversationResponse,
          dependencies=[Depends(ratelimit.rate_limit(40, 60, "llm"))])
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
            situation=_sanitize_text(request.situation, 80),
            level=request.level,
            history=_sanitize_history(request.history)
        )
        return result
    except Exception as e:
        raise _server_error(e, "Conversation generation failed")


class SignRequest(BaseModel):
    text: str


@app.post("/api/sign/translate", dependencies=[Depends(ratelimit.rate_limit(40, 60, "llm"))])
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
    text = _sanitize_text(text, 200)  # 제어문자 제거 — 타 LLM 경로와 동일한 입력 정규화(§4.9 주입 방어)
    try:
        from sign_service import translate_to_ksl
        return await translate_to_ksl(text)
    except HTTPException:
        raise
    except Exception as e:
        raise _server_error(e, "Sign translation failed")


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

        # Check if requesting a specific file — full_path는 사용자 제어이므로 dist 밖으로
        # 벗어나는 경로(../ 등)는 차단한다(dist 밖 .env·DB 노출 방지).
        _dist_real = os.path.realpath(frontend_dist)
        file_path = os.path.realpath(os.path.join(frontend_dist, full_path))
        _contained = os.path.commonpath([file_path, _dist_real]) == _dist_real
        if _contained and os.path.isfile(file_path):
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
