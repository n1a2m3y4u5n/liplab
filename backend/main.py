"""
LIPLAB FastAPI Main Application
Serves API endpoints and React static files for production deployment
"""
import os
import asyncio
import logging
import ratelimit
import llm_budget
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
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
    from llm_service import generate_adaptive_scenario, generate_conversation_turn
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


def _warmup_models():
    """서버 추론 모델(D-GOP 정렬·채점, 음성구동 아바타)을 뒤에서 미리 올린다(LIPLAB_WARMUP=1).
    호스팅 기계는 쉬면 멈췄다가(fly.dev.toml은 일시정지) 요청 때 켜지므로, 첫 사용자가 모델 적재를 기다리지 않게 한다.
    일시정지에서 깨어나면 올려 둔 모델이 그대로 있고, 스냅샷이 없을 때(배포 직후 등)만 이 예열이 다시 돈다.
    실패해도 앱은 뜨고, 요청 때 다시 적재를 시도한다."""
    import threading

    def run():
        try:
            aligner = os.getenv("DGOP_ALIGNER_ID") or os.getenv("DGOP_MODEL_ID")
            if aligner:
                import dgop_acoustic
                if dgop_acoustic.HAS_ACOUSTIC:
                    dgop_acoustic._load(aligner)
                    scorer = os.getenv("DGOP_SCORER_ID")
                    if scorer and scorer != aligner:
                        dgop_acoustic._load(scorer)
                        dgop_acoustic._share_once(aligner, scorer)   # 특징 추출부 공유도 미리(첫 채점이 확인하지 않게)
            import audio2face
            if audio2face.is_available():
                audio2face.warm()   # 적재에 더해 백본 가중치를 끝까지 읽어 둔다(첫 아바타 요청이 느린 디스크를 기다리지 않게)
            print("[OK] 서버 추론 모델 예열 끝")
        except Exception as e:
            print(f"[WARN] 모델 예열 실패(요청 때 다시 시도): {type(e).__name__}: {e}")

    threading.Thread(target=run, daemon=True, name="model-warmup").start()


def _warmup_content():
    """학습 콘텐츠 표를 뒤에서 미리 만든다(모델과 무관, 늘 켬, LIPLAB_CONTENT_WARMUP=0이면 끔). 2단계 출제 표(보기 부류, 약 1.5초)와
    문맥 문항 서빙 목록(규칙 게이트)을 켜진 뒤 첫 레슨 요청이 기다리지 않게 한다(9/27)."""
    import threading

    def run():
        try:
            _stage2_table()
            _training_closures()
            print("[OK] 콘텐츠 표 예열 끝")
        except Exception as e:
            print(f"[WARN] 콘텐츠 표 예열 실패(요청 때 다시 만든다): {type(e).__name__}: {e}")

    threading.Thread(target=run, daemon=True, name="content-warmup").start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup and shutdown"""
    # Startup
    await init_db()
    print("[OK] Database initialized")
    if os.getenv("LIPLAB_CONTENT_WARMUP", "1") != "0":
        _warmup_content()
    if os.getenv("LIPLAB_WARMUP") == "1":
        _warmup_models()
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


# 요청 본문 상한. FastAPI는 인증·속도 제한보다 먼저 본문을 모두 읽으므로(JSON은 메모리, 멀티파트는 임시 파일),
# 로그인 없이도 아주 큰 요청 하나로 기계가 멈출 수 있었다. Content-Length로 먼저 거른다(오디오 10MB 상한보다 조금 크게).
_MAX_BODY_MULTIPART = 12 * 1024 * 1024
_MAX_BODY_OTHER = 2 * 1024 * 1024


@app.middleware("http")
async def _limit_body(request, call_next):
    # Cloudflare 앞단을 쓰면(LIPLAB_ORIGIN_SECRET) fly 주소로 바로 오는 요청을 막는다. 공격자가 방화벽을 건너뛰지 못하게.
    # /health는 fly 상태 점검이 기계에 직접 부르므로 뺀다.
    if request.url.path != "/health" and not ratelimit.origin_ok(request):
        return _JSONResponse(status_code=403, content={"detail": "forbidden"})
    llm_budget.current_client.set(ratelimit._client_key(request))   # LLM 하루 한도의 IP별 계수(llm_budget)
    cl = request.headers.get("content-length")
    if cl and cl.isdigit():
        cap = _MAX_BODY_MULTIPART if request.headers.get("content-type", "").startswith("multipart/") else _MAX_BODY_OTHER
        if int(cl) > cap:
            return _JSONResponse(status_code=413, content={"detail": "요청이 너무 커요."})
    return await call_next(request)


# 서버 추론(발음 채점·음성구동 아바타·전사) 동시 실행 수. 추론 하나가 수백 MB를 더 쓰므로 여러 개가 겹치면 4GB 기계가
# 멈출 수 있어 차례로 돌린다(요청은 기다렸다 처리된다). LIPLAB_ML_CONCURRENCY로 늘릴 수 있다.
_ML_CONCURRENCY = max(1, int(os.getenv("LIPLAB_ML_CONCURRENCY", "1") or 1))
_ML_SEM = asyncio.Semaphore(_ML_CONCURRENCY)
# 추론 대기열 상한. 예전에는 대기가 무한이라 한 사람이 채점 요청을 계속 밀어 넣으면 다른 사용자가 끝없이 기다렸다.
# 실행 중 + 대기 중이 동시 실행 수 + LIPLAB_ML_QUEUE_MAX(기본 4)를 넘으면 받기 전에 503으로 돌려보낸다.
_ML_INFLIGHT = 0
_ML_QUEUE_MAX = max(0, int(os.getenv("LIPLAB_ML_QUEUE_MAX", "4") or 4))


def _ml_admit():
    if _ML_INFLIGHT >= _ML_CONCURRENCY + _ML_QUEUE_MAX:
        raise HTTPException(status_code=503, detail="지금 채점 요청이 많아요. 잠시 후 다시 시도해 주세요.",
                            headers={"Retry-After": "10"})


@asynccontextmanager
async def _ml_slot():
    global _ML_INFLIGHT
    _ML_INFLIGHT += 1
    try:
        async with _ML_SEM:
            yield
    finally:
        _ML_INFLIGHT -= 1


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
    """user_id를 가진 모든 사용자 데이터 모델(개인정보 열람·삭제 대상). 파일럿 파기 스크립트와 같은 정의(pilot_data)."""
    import pilot_data as _pd
    return _pd.user_data_models()


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
    민감 정보(비밀번호 해시)는 제외한다. 공용 데모 계정은 여러 방문자의 기록이 섞여 있어 내보내지 않는다."""
    if (current_user.email or "").lower() == _DEMO_EMAIL:
        raise HTTPException(status_code=403, detail="공용 데모 계정은 기록을 내려받을 수 없어요.")
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
            "note": ("웹캠 영상은 기기 안에서만 처리됩니다. 목소리 녹음은 채점하는 동안만 서버 메모리에 두고 저장하지 "
                     "않아, 이 파일에 없습니다. 녹음을 글로 옮긴 것(전사문), 소리 수치, 입모양 점수는 학습 기록으로 "
                     "저장되어 아래 data에 있습니다.")}


@app.post("/api/account/learning-reset", dependencies=[Depends(ratelimit.rate_limit(5, 60, "account-reset"))])
async def account_learning_reset(confirm: bool = False, current_user=Depends(get_current_user),
                                 db: AsyncSession = Depends(get_db)):
    """학습 초기화 — 계정은 두고 학습 기록 전부(시행·진행도·복습·북마크·검사·교정 기록)를 지우고
    XP·연속 학습·레벨·배치를 처음 상태로 되돌린다. 프로필 화면의 '사라지는 기록' 목록과 같은 범위다.
    가입 동의 기록(ConsentRecord)은 법적 기록이라 남긴다. 공용 데모 계정은 방문자 모두의 화면이라 막는다.
    파일럿 참여 중이면 표준검사 사전·사후(A·B) 결과는 남긴다 — 연구 자료이고, 지우면 사전검사를 다시 볼 수 없다.
    같은 까닭으로 유지 검사(C7)와 P3 검사 묶음(p3_test_sessions·p3_closed_responses·p3_open_responses)도 남긴다.
    참여 철회와 자료 삭제는 연구진을 통해 한다(docs/pilot-data-spec.md §5)."""
    if not confirm:
        raise HTTPException(status_code=400, detail="초기화를 확인하려면 confirm=true가 필요합니다.")
    if (current_user.email or "").lower() == _DEMO_EMAIL:
        raise HTTPException(status_code=403, detail="공용 데모 계정은 초기화할 수 없어요.")
    from sqlalchemy import delete as _delete
    from database import (ConsentRecord, LearningProfile, PlacementResult, RetentionResult, P3TestSession,
                          P3ClosedResponse, P3OpenResponse)
    prof = await _get_or_create_profile(current_user.id, db)
    in_pilot = bool(prof.pilot_code)
    removed, kept = {}, {}
    pilot_tests = (RetentionResult, P3TestSession, P3ClosedResponse, P3OpenResponse)
    for M in _user_data_models():
        if M in (ConsentRecord, LearningProfile) or (in_pilot and M in pilot_tests):
            continue   # 파일럿 참여 중이면 유지 검사 결과(C7)와 P3 검사 기록도 사전·사후처럼 연구 자료로 남긴다
        q = _delete(M).where(M.user_id == current_user.id)
        if in_pilot and M is PlacementResult:
            from sqlalchemy import or_ as _or
            q = q.where(_or(PlacementResult.form.is_(None), PlacementResult.form.not_in(("A", "B"))))
        res = await db.execute(q)
        removed[M.__tablename__] = res.rowcount if res.rowcount is not None else 0
    if in_pilot:
        from sqlalchemy import select as _select, func as _func
        kept["placement_results_ab"] = (await db.execute(
            _select(_func.count(PlacementResult.id)).where(PlacementResult.user_id == current_user.id))).scalar() or 0
        n_p3 = (await db.execute(
            _select(_func.count(P3TestSession.id)).where(P3TestSession.user_id == current_user.id))).scalar() or 0
        if n_p3:
            kept["p3_test_sessions"] = n_p3
    # 학습 프로필은 지우지 않고 배치만 처음으로 — 파일럿 참여(코드·집단)는 학습 기록이 아니라 그대로 둔다
    prof.track, prof.current_stage, prof.placed = None, 0, False
    prof.speak_current_stage = 0
    from datetime import datetime as _dt
    prof.learning_reset_at = _dt.utcnow()   # 파일럿 내보내기의 learning_reset_on(초기화로 줄어든 학습량을 분석에서 알 수 있게)
    current_user.total_xp = 0
    current_user.streak_count = 0
    current_user.last_practice_date = None   # 다시 시작한 날부터 연속 학습 1일로 센다
    current_user.current_level = 1
    db.add(current_user)
    await db.commit()
    return {"reset": True, "removed": removed, "kept": kept}


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

from pydantic import BaseModel, Field

# 채점할 글자 수 상한. 자모 정렬이 두 문장 길이의 곱만큼 표를 만들고 이벤트 루프에서 돌아, 아주 긴 입력 하나로
# 모든 요청이 멈췄다(1500자끼리 약 1.5~3.8초, 더 길면 수 GB). 앱의 문장은 수십 자라 300자면 넉넉하다.
_TEXT_MAX = 300
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
    from auth import password_fits, PASSWORD_TOO_LONG
    if not password_fits(req.new_password):
        raise HTTPException(status_code=400, detail=PASSWORD_TOO_LONG)
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
    scenario_id: str = Field(..., max_length=200)
    sentence: str = Field(..., max_length=_TEXT_MAX)
    user_answer: str = Field(..., max_length=_TEXT_MAX)
    time_spent_seconds: int      # 처리부에서 0~3600으로 맞춘다(음수면 시간 보너스로 XP가 수만씩 붙었다)
    situation: str = Field(..., max_length=200)
    difficulty_level: int        # 처리부에서 1~5로 맞춘다
    practice_only: bool = False  # 정답을 본 뒤의 다시 풀기·자막 힌트 뒤 제출: 점수만 돌려주고 기록·숙달·XP에는 넣지 않는다
    # 'choice'면 보기를 고른 답: 정확 일치(100 또는 0)로 채점하고, 3단계 숙달에는 우연 보정(정답 1, 오답 −1/3)으로 넣는다
    # (docs/mastery-ewma.md 10절). 'typed'는 주관식·서술형. progress.answer_mode에 남기고 그 밖의 값은 비워 둔다
    answer_mode: Optional[str] = Field(None, max_length=10)
    # 답하기 전에 본 유효 재생 속도(학습자가 고른 가장 느린 속도 × 적응 감속). 기록만 하고 숙달에는 넣지 않는다: 1.0배 미만 합격을
    # 0.5로 세는 규칙들이 시뮬레이션 사전 기준을 넘지 못했다(docs/mastery-ewma.md 9절). 실제 기록이 쌓이면 다시 본다
    speed: Optional[float] = Field(None, ge=0.1, le=4.0)
    # 파일럿 로그(P0): 문장 표시부터 답까지 ms, 레슨 가상 화자, 연 힌트 단계(0~3), 4지선다 보기(보인 순서). 모두 기록만 한다
    rt_from_onset_ms: Optional[int] = Field(None, ge=0, le=3_600_000)
    talker: Optional[str] = Field(None, max_length=16)
    hint_level: Optional[int] = Field(None, ge=0, le=3)
    options: Optional[List[str]] = Field(None, max_length=6)


def _sentence_options(options, sentence: str) -> Optional[list]:
    """문장 4지선다 보기(보인 순서). 정답 문장이 없거나 겹치는 보기가 있으면 남기지 않는다(_trial_options와 같은 원칙, 길이만 문장용)."""
    if not options or not all(isinstance(o, str) for o in options):
        return None
    out = [o.strip()[:_TEXT_MAX] for o in options]
    return out if len(set(out)) == len(out) and (sentence or "").strip() in out else None


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
    passed: Optional[bool] = None   # 3단계 합격선(_STAGE3_PASS) 이상인가. 화면의 레슨 집계·표시가 이 값을 쓴다
    # 주관식·서술형(typed)의 낱말별 자음 피드백(계획 C9, sentence_feedback.py). 화면은 합격선 아래인 첫 답에서 정답 문장 대신
    # 이것을 보이고 한 번 더 답하게 한다. 4지선다에는 없다
    word_feedback: Optional[dict] = None


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
    """음성구동 아바타(A4) 사용 가능 여부. 프론트가 UI 노출 판단에 쓴다.
    is_available()은 처음 부를 때 torch를 불러온다. 켜진 직후에는 예열 스레드가 torch를 불러오는 동안 기다리므로
    스레드에서 불러 이벤트 루프(다른 요청)를 막지 않는다."""
    try:
        import audio2face
        return {"available": await asyncio.to_thread(audio2face.is_available)}
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
    _ml_admit()
    try:
        async with _ml_slot():
            result = await asyncio.to_thread(audio2face.blendshapes_from_audio, data)
    except Exception as e:
        logging.getLogger("liplab").exception("audio2face 추론 실패")
        raise HTTPException(status_code=500, detail="음성구동 처리에 실패했습니다.")
    return result


@app.get("/api/scenario", response_model=ScenarioResponse,
         dependencies=[Depends(ratelimit.rate_limit(15, 60, "llm"))])
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
def _kst_today():
    """오늘 날짜(한국 시간). 서버(fly)는 UTC라 date.today()를 쓰면 오전 9시 전 학습이 전날로 잡혀, 스트릭·복습일이
    기기 시간을 쓰는 분석 탭과 어긋났다. 서비스 대상이 한국이라 KST(UTC+9)로 고정한다."""
    from datetime import datetime as _dtm, timedelta as _td
    return (_dtm.utcnow() + _td(hours=9)).date()


def _add_xp(user, xp: int) -> None:
    """XP를 더하고 레벨을 올린다(level = floor(sqrt(xp/100))+1, 내려가지 않음). 커밋은 호출부."""
    user.total_xp = (user.total_xp or 0) + int(xp)
    new_level = int((user.total_xp / 100) ** 0.5) + 1
    user.current_level = max(user.current_level or 1, new_level)


def _award_xp_and_streak(user, base_xp: int, bonus: int = 0) -> dict:
    """스트릭(하루 1회 갱신·idempotent) + XP + 레벨업을 계산해 user에 반영. 커밋은 호출부.
    base_xp는 활동별 기본 XP(스트릭 배수 적용 전), bonus는 배수 미적용 가산점(예: 시간 보너스)."""
    from datetime import date, timedelta
    today_str = _kst_today().isoformat()
    yesterday_str = (_kst_today() - timedelta(days=1)).isoformat()
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
    _add_xp(user, xp_gained)
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
        wv = r.scalars().first()
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


def _choice_result(sentence: str, chosen: str, result: dict) -> dict:
    """객관식 답: 고른 보기가 정답 문장과 같은지만 본다(공백·문장부호 무시). 채점식을 쓰면 비슷한 오답 보기가 통과
    점수를 받아 숙달에 들어갔다. 오류 입모양(취약 입모양 갱신용)은 채점식 정렬 결과를 그대로 쓴다."""
    import re as _re
    from scoring import generate_feedback
    norm = lambda t: _re.sub(r"[\s.,?!~]", "", t or "")   # noqa: E731
    score = 100.0 if norm(sentence) == norm(chosen) else 0.0
    acc = result.get("phoneme_accuracy") or {"initial": 0, "medial": 0, "final": 0}
    return {**result, "score": score, "feedback": generate_feedback(score, acc)}


class SentenceOptionsRequest(BaseModel):
    sentence: str = Field(..., max_length=_TEXT_MAX)
    exclude: List[str] = Field(default_factory=list, max_length=40)   # 이번 레슨 문장들


_SENTENCE_POOL = {"at": 0.0, "pool": []}


async def _sentence_option_pool(db: AsyncSession) -> List[str]:
    """4지선다 오답 보기 풀: 코드의 문장 + 캐시된 LLM 시나리오 문장(지금 게이트를 통과한 것). 10분 캐시."""
    import time as _time
    now = _time.time()
    if _SENTENCE_POOL["pool"] and now - _SENTENCE_POOL["at"] < 600:
        return _SENTENCE_POOL["pool"]
    import sentence_options as _so
    from content_rules import check_sentence
    from database import ScenarioCache
    from sqlalchemy import select
    import llm_service as _L
    pool = _so.static_pool()
    try:
        rows = (await db.execute(select(ScenarioCache.sentences)
                                 .order_by(ScenarioCache.created_at.desc()).limit(400))).scalars().all()
        longest = max(_L.SCENARIO_MAX_CHARS.values())
        for ss in rows:
            pool += [x for x in (ss or []) if isinstance(x, str) and check_sentence(x, max_chars=longest)[0]]
    except Exception as e:
        print(f"[WARN] sentence option pool (cache) failed: {e}")
    _SENTENCE_POOL.update(at=now, pool=list(dict.fromkeys(pool)))
    return _SENTENCE_POOL["pool"]


@app.post("/api/curriculum/sentence-options")
async def curriculum_sentence_options(data: SentenceOptionsRequest, current_user=Depends(get_current_user),
                                      db: AsyncSession = Depends(get_db)):
    """3단계 문장 4지선다의 오답 보기 3개: 이번 레슨 밖 문장 가운데 음절 수가 가까운 것(sentence_options 머리말).
    예전 보기(같은 레슨의 다른 문장)는 뒤 문항의 답을 미리 보여 주고 길이로도 고를 수 있었다."""
    import sentence_options as _so
    pool = await _sentence_option_pool(db)
    return {"options": _so.pick_options(data.sentence, pool, data.exclude)}


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
        # 앞뒤 공백은 한 번 떼고 기록·복습 큐·채점에 같은 값을 쓴다. 예전에는 복습 큐 길이 검사만 뗀 값으로 하고 큐에는 원문을 넣어,
        # 공백이 붙은 100자 문장이 String(100) 칸을 넘었고 Progress.sentence와 큐의 ref가 달라 상황·난이도를 찾지 못할 수 있었다.
        submission.sentence = (submission.sentence or "").strip()
        # 독화 이해 채점 v2(입모양 기준, docs/scoring-v2.md). 객관식은 정확 일치로 준다.
        scoring_result = await calculate_score(
            correct=submission.sentence,
            user_answer=submission.user_answer,
            db=db,
            mode="visual",
        )
        if submission.answer_mode == "choice":
            scoring_result = _choice_result(submission.sentence, submission.user_answer, scoring_result)
        time_spent = max(0, min(int(submission.time_spent_seconds), 3600))
        difficulty = max(1, min(int(submission.difficulty_level), 5))
        word_feedback = None
        if submission.answer_mode != "choice":
            from sentence_feedback import consonant_feedback
            word_feedback = consonant_feedback(submission.sentence, submission.user_answer)
        if submission.practice_only:
            # 정답을 이미 본 제출은 숙달(해금)·XP·연습 기록에 넣지 않는다(다시 풀기 네 번이면 3단계가 숙달되던 문제)
            award = _award_xp_and_streak(current_user, 0)
            await db.commit()
            return ProgressResponse(
                status="practice_only", score=scoring_result["score"], new_level=award["new_level"],
                old_level=award["old_level"], xp_gained=0, streak_count=award["streak_count"],
                streak_multiplier=award["streak_multiplier"], feedback=scoring_result.get("feedback", {}),
                phoneme_accuracy=scoring_result.get("phoneme_accuracy", {}),
                passed=scoring_result["score"] >= _STAGE3_PASS, word_feedback=word_feedback)

        # Save progress to database
        from database import Progress

        progress = Progress(
            user_id=current_user.id,
            scenario_id=submission.scenario_id,
            sentence=submission.sentence,
            user_answer=submission.user_answer,
            score=scoring_result["score"],
            time_spent_seconds=time_spent,
            difficulty_level=difficulty,
            situation=submission.situation,
            viseme_errors=scoring_result.get("viseme_errors", []),
            phoneme_accuracy=scoring_result.get("phoneme_accuracy", {}),
            speed=submission.speed,
            answer_mode=_answer_mode(submission.answer_mode),
            rt_from_onset_ms=submission.rt_from_onset_ms,
            talker=_clean_talker(submission.talker),
            hint_level=submission.hint_level,
            options=_sentence_options(submission.options, submission.sentence) if submission.answer_mode == "choice" else None,
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
        base_xp = int(scoring_result["score"] * difficulty * 2)
        time_bonus = max(0, 50 - time_spent // 2)
        award = _award_xp_and_streak(current_user, base_xp, bonus=time_bonus)

        # 3단계(문장 연습) 숙달 갱신: 점수 PASS 이상이면 성공 1회로 누적(4단계 해금 근거). 잠긴 단계면 넣지 않는다.
        # 틀린 문장 복습·북마크 연습은 원문을 본 뒤의 답이라 넣지 않는다. 기록(Progress)은 남겨 맞히면 오답 목록에서 빠지게 한다
        if not _is_review_scenario(submission.scenario_id) and await _stage_open(current_user, 3, db):
            passed3 = scoring_result["score"] >= _STAGE3_PASS
            await _bump_stage_progress(
                current_user.id, 3, passed3, _STAGE3_MIN_ATTEMPTS, _STAGE3_MASTERY, db,
                credit=_stage3_credit(passed3, submission.answer_mode))

        # 문장 간격 반복(kind 'sentence'): 레슨에서 합격선 아래면 내일 복습에 넣고, 예정일에 다시 읽으면 점수 등급으로 간격을
        # 조정한다(말하기 kind 'speak'와 같은 _sr_touch). 틀린 문장 복습·북마크 연습은 원문을 본 뒤의 답이라 일정을 건드리지 않는다
        if _schedules_sentence(submission.scenario_id, submission.sentence):
            # 4지선다 합격은 정확 일치 100점이라 점수 등급으로는 품질 5가 된다. 찍어도 25%는 맞으므로 3을 넘지 않게 한다
            await _sr_touch(current_user.id, "sentence", submission.sentence,
                            scoring_result["score"] >= _STAGE3_PASS, db, score=scoring_result["score"],
                            max_quality=3 if submission.answer_mode == "choice" else None,
                            answer_mode=submission.answer_mode)

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
            phoneme_accuracy=scoring_result.get("phoneme_accuracy", {}),
            passed=scoring_result["score"] >= _STAGE3_PASS,
            word_feedback=word_feedback,
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

    # 약점 입모양: 지식추적 숙달도가 낮은 순 5개(knowledge_tracing.rank_weak). 예전에는 오류 횟수 상위 5개를 잘라, 자주 나오는
    # 입모양이 오답률이 낮아도 올라오고 적게 나왔지만 자주 틀린 입모양은 빠졌다. 화면은 이 순서를 그대로 쓰고 시도 수를 함께 보인다.
    import knowledge_tracing as _kt
    rows = (await db.execute(select(WeakViseme).where(WeakViseme.user_id == current_user.id))).scalars().all()
    feature = {wv.viseme_id: wv.phonological_feature for wv in rows}
    ranked = _kt.rank_weak([{"viseme_id": wv.viseme_id, "error_count": wv.error_count,
                             "total_attempts": wv.total_attempts, "last_error_at": wv.last_error_at}
                            for wv in rows], k=5)

    return {
        "total_sessions": total_count,
        "average_score": round(average, 2),
        "current_level": current_user.current_level,
        "total_xp": current_user.total_xp,
        "weak_visemes": [
            {
                "viseme_id": r["viseme_id"],
                "error_rate": round(r["error_rate"] * 100, 1),
                "attempts": r["attempts"],
                "mastery": r["mastery"],
                "feature": VISEME_GROUP_NAMES.get(r["viseme_id"], feature.get(r["viseme_id"]) or f"viseme {r['viseme_id']}")
            }
            for r in ranked
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
    sentence: str = Field(..., max_length=_TEXT_MAX)
    situation: str = Field("", max_length=200)
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


@app.get("/api/analysis", dependencies=[Depends(ratelimit.rate_limit(30, 60, "analysis"))])
async def get_analysis(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """독화 문장 연습 집계(입모양별 정확도·강약점·자모 혼동). 예전엔 끝에 LLM 추천 문구(약 4초)를 붙였는데,
    그 문구를 그리던 화면이 Figma 이식 뒤 없어져 9/24에 뺐다(분석 상세는 /api/statistics를 쓴다)."""
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

        return {
            "total_sessions": total,
            "average_score": round(avg_score, 1),
            "strengths": strengths,
            "weaknesses": weaknesses,
            "viseme_stats": viseme_stats,
            "confusions": confusions,
        }

    except Exception as e:
        print(f"[ERROR] get_analysis failed: {e}")
        traceback.print_exc()
        raise _server_error(e, "분석 데이터 로드 실패")


@app.delete("/api/analysis/reset")
async def reset_analysis(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Clear all practice history for the current user to start fresh."""
    from database import Progress, WeakViseme
    from sqlalchemy import delete as sql_delete
    if (current_user.email or "").lower() == _DEMO_EMAIL:   # 공용 계정: 한 사람이 지우면 모든 방문자의 기록이 사라진다
        raise HTTPException(status_code=403, detail="공용 데모 계정은 초기화할 수 없어요.")
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

    cutoff = (_kst_today() - dt.timedelta(days=90)).isoformat()
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


# 시행 기록(TrialAttempt.item_type)의 유형. 회차 히스토리가 유형마다 한 행을 만든다
_TRIAL_KINDS = ("viseme", "viseme_ax", "word", "word_typed", "context", "closure")


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
        add(ts, item_type if item_type in _TRIAL_KINDS else "trial", "", 1.0 if correct else 0.0)
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

    # 2단계 주관식(word_typed)과 단어 레슨 속 문맥 문항(context)도 따로 한 행이다. 예전에는 ORDER에 없어 그날 기록에서 빠졌다
    KIND_LABEL = {"viseme": "입모양 인지", "viseme_ax": "입모양 같은지 다른지", "word": "단어", "word_typed": "단어 주관식", "context": "단어 레슨 문맥",
                  "closure": "문맥 추론", "trial": "인지 훈련"}
    SPEAK_LABEL = {"voicing": "발성", "prosody": "억양", "phoneme": "음소", "word": "단어", "sentence": "문장",
                   "probe": "낱말 속 소리"}
    FORM_LABEL = {"placement": "배치검사", "A": "사전검사", "B": "사후검사"}
    TYPE_LABEL = {"assessment": "검사", "viseme": "독화", "viseme_ax": "독화", "word": "독화", "word_typed": "독화", "context": "독화",
                  "closure": "독화", "trial": "독화", "sentence": "문장 연습", "speak": "말하기"}
    # 블록 클릭 시 이동할 학습 화면. 말하기 모드는 speak_curriculum의 단계 번호로 연결한다.
    SPEAK_STAGE = {"voicing": 0, "prosody": 1, "phoneme": 2, "word": 4, "sentence": 5}
    KIND_ROUTE = {"assessment": "/learn/placement", "viseme": "/learn/viseme", "viseme_ax": "/learn/viseme", "word": "/learn/word",
                  "word_typed": "/learn/word", "context": "/learn/word", "closure": "/learn/closure", "trial": "/learn/viseme"}
    ORDER = ["assessment", "viseme", "viseme_ax", "word", "word_typed", "context", "closure", "trial", "sentence", "speak"]

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


@app.get("/api/analysis/activity-detail")
async def analysis_activity_detail(day: str, kind: str, topic: str = "", tz_offset_min: int = -540,
                                   current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """회차 상세(Figma 212:24) — 회차 히스토리의 한 행(현지 날짜 × 활동 종류 × 주제)에 든 문제별 기록과 요약.
    말하기는 소리(융합 전 음향)·입모양·융합·불확실성 평균과 문제별 점수·들린 발음·음소 칩·마지막 코칭을,
    독화는 문제별 정답·고른 답을, 문장 연습은 문장·내 답·점수를, 검사는 회차별 정답률을 준다.
    """
    import datetime as dt
    import analytics as _an
    from sqlalchemy import select
    from database import Progress, TrialAttempt, SpeakAttempt, PlacementResult
    try:
        d0 = dt.date.fromisoformat(day)
    except ValueError:
        raise HTTPException(status_code=400, detail="day는 YYYY-MM-DD")
    tz = max(-840, min(720, int(tz_offset_min)))
    lo = dt.datetime.combine(d0, dt.time()) + dt.timedelta(minutes=tz)       # 현지 0시 → UTC
    hi = lo + dt.timedelta(days=1)
    uid = current_user.id

    def hm(ts):
        return _an.to_local(ts, tz).strftime("%H:%M") if ts else None

    def mean(xs):
        xs = [x for x in xs if x is not None]
        return round(sum(xs) / len(xs), 1) if xs else None

    items, summary, coaching = [], {}, None
    # 공용 데모 계정은 방문자 모두가 같은 기록을 본다 — 들린 발음·직접 쓴 답·코칭 문장처럼 다른 방문자가 한 말은 빼고 점수만 준다
    demo = (current_user.email or "").lower() == _DEMO_EMAIL
    if kind == "speak":
        q = select(SpeakAttempt).where(SpeakAttempt.user_id == uid, SpeakAttempt.created_at >= lo,
                                       SpeakAttempt.created_at < hi)
        q = q.where(SpeakAttempt.mode == topic) if topic else q.where((SpeakAttempt.mode.is_(None)) | (SpeakAttempt.mode == ""))
        rows = (await db.execute(q.order_by(SpeakAttempt.created_at))).scalars().all()
        items = [{"time": hm(r.created_at), "target": r.target, "heard": None if demo else r.transcript,
                  "score": round(r.score or 0, 1),
                  "passed": r.passed, "phones": r.phones or [], "confusions": r.confusions or []} for r in rows]
        unc = [r.uncertainty for r in rows if r.uncertainty is not None]
        summary = {"n": len(rows), "sound": mean([r.audio_score for r in rows]), "mouth": mean([r.mouth_score for r in rows]),
                   "fused": mean([r.fused_score for r in rows]),
                   "uncertainty": round(sum(unc) / len(unc), 3) if unc else None,
                   "score": mean([r.score for r in rows]),
                   "pass_rate": round(sum(1 for r in rows if r.passed) / len(rows), 3) if rows and any(r.passed is not None for r in rows) else None}
        coaching = None if demo else next((r.coaching for r in reversed(rows) if r.coaching), None)
    elif kind in _TRIAL_KINDS or kind == "trial":
        q = select(TrialAttempt).where(TrialAttempt.user_id == uid, TrialAttempt.created_at >= lo,
                                       TrialAttempt.created_at < hi)
        # 'trial'은 유형을 모르는 예전 행(목록 밖 유형 포함)
        q = q.where(TrialAttempt.item_type == kind) if kind != "trial" else q.where(
            (TrialAttempt.item_type.is_(None)) | (TrialAttempt.item_type.notin_(_TRIAL_KINDS)))
        rows = (await db.execute(q.order_by(TrialAttempt.created_at))).scalars().all()
        items = [{"time": hm(r.created_at), "target": r.target, "chosen": r.chosen, "correct": bool(r.correct),
                  "confusions": r.confusions or []} for r in rows]
        if kind == "word_typed":
            # 주관식은 직접 쓴 답이라 공용 데모 계정에서는 빼고, '입모양은 맞음'(정답 아님, 숙달 0.5)을 따로 알려 준다
            import visual_difficulty as _vd
            for it in items:
                it["verdict"] = _vd.typed_word_verdict(it["target"], it["chosen"] or "")["verdict"]
                if demo:
                    it["chosen"] = None
        summary = {"n": len(rows), "accuracy": round(sum(1 for r in rows if r.correct) / len(rows), 3) if rows else None}
    elif kind == "sentence":
        q = select(Progress).where(Progress.user_id == uid, Progress.created_at >= lo, Progress.created_at < hi,
                                   Progress.situation == topic)
        rows = (await db.execute(q.order_by(Progress.created_at))).scalars().all()
        items = [{"time": hm(r.created_at), "target": r.sentence, "chosen": None if demo else r.user_answer,
                  "score": round(r.score or 0, 1)}
                 for r in rows]
        summary = {"n": len(rows), "score": mean([r.score for r in rows])}
    elif kind == "assessment":
        q = select(PlacementResult).where(PlacementResult.user_id == uid, PlacementResult.created_at >= lo,
                                          PlacementResult.created_at < hi, PlacementResult.form == (topic or "placement"))
        rows = (await db.execute(q.order_by(PlacementResult.created_at))).scalars().all()
        items = [{"time": hm(r.created_at), "total": r.total, "correct": r.correct, "accuracy": round(r.accuracy or 0, 3),
                  "level": r.level} for r in rows]
        summary = {"n": len(rows), "accuracy": round(sum(r.accuracy or 0 for r in rows) / len(rows), 3) if rows else None}
    else:
        raise HTTPException(status_code=400, detail="알 수 없는 활동 종류")
    return {"day": day, "kind": kind, "topic": topic, "summary": summary, "items": items, "coaching": coaching}


async def _activity_events(uid: int, db, since=None) -> list:
    """활동 기록 네 표(문장·독화 시행·말하기·검사) → analytics.Event 목록. 분석 요약과 과제 탭이 같은 정의로 센다.
    since(UTC)를 주면 그 뒤 기록만 읽는다."""
    import analytics as _an
    from database import Progress, TrialAttempt, SpeakAttempt, PlacementResult
    from sqlalchemy import select

    def q(stmt, M):
        stmt = stmt.where(M.user_id == uid)
        return stmt.where(M.created_at >= since) if since is not None else stmt

    events = []
    # kind(문항 유형)는 주별 정확도를 유형 구성과 떼어 보는 데 쓴다(analytics 머리말). 문장은 난이도 단계까지 나눈다.
    for ts, score, lvl in (await db.execute(q(select(Progress.created_at, Progress.score, Progress.difficulty_level),
                                              Progress))).all():
        events.append(_an.Event(ts, "read", None if score is None else max(0.0, min(1.0, score / 100.0)),
                                f"sentence:{lvl or 0}"))
    for ts, correct, itype in (await db.execute(q(select(TrialAttempt.created_at, TrialAttempt.correct,
                                                         TrialAttempt.item_type), TrialAttempt))).all():
        events.append(_an.Event(ts, "read", 1.0 if correct else 0.0, itype or ""))
    for ts, passed, score, smode in (await db.execute(q(
            select(SpeakAttempt.created_at, SpeakAttempt.passed, SpeakAttempt.score, SpeakAttempt.mode),
            SpeakAttempt))).all():
        g = (1.0 if passed else 0.0) if passed is not None else (None if score is None else max(0.0, min(1.0, score / 100.0)))
        events.append(_an.Event(ts, "speak", g, f"speak:{smode or ''}"))
    for (ts,) in (await db.execute(q(select(PlacementResult.created_at), PlacementResult))).all():
        events.append(_an.Event(ts, "test", None))
    return [e for e in events if e.ts is not None]


@app.get("/api/analysis/overview")
async def get_analysis_overview(tz_offset_min: int = -540, current_user=Depends(get_current_user),
                                db: AsyncSession = Depends(get_db)):
    """분석 탭 요약 + 배지 — 활동 기록 전체에서 계산한다(집계 로직은 analytics.py).

    학습 시간은 따로 저장하지 않으므로 활동 시각으로 회차를 나눠 추정하고(30분 공백 = 새 회차),
    정확도는 독화 시행(정오답)·문장 점수·말하기 통과 여부를 0~1로 모아 평균한다. 주별 추이와 지난주 대비는
    문항 유형 구성과 떼어 본다(유형 고정효과 보정·유형 안 비교, analytics 머리말).
    tz_offset_min은 브라우저 Date.getTimezoneOffset()(한국 −540) — 날짜·연속 학습·새벽 판정에 쓴다.
    """
    import datetime as dt
    import analytics as _an
    from database import StageProgress, SpeakStageProgress, ReviewItem
    from sqlalchemy import select

    tz = max(-840, min(720, int(tz_offset_min)))
    uid = current_user.id
    events = await _activity_events(uid, db)

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
    # 복습을 실제로 한 횟수는 예정된 복습에 답할 때마다 프로필에 쌓은 누적값이다(_srs_apply). 예전에는 남은 항목의
    # repetitions·lapses로 셌는데, 레슨에서 같은 항목을 두 번 틀리면(lapses 2) 복습 없이 배지가 나왔고,
    # 복습을 끝까지 해 항목이 졸업(행 삭제)하면 0이 되어 배지가 꺼졌다.
    reviews_done = prof.reviews_completed or 0
    # 문장 복습은 하루 상한(_SENTENCE_REVIEW_DAILY)이 있어 오늘 낼 수 있는 것만 센다. 상한에 밀려 기다리는 문장까지 세면
    # 매일 복습을 다 해도 배지가 꺼진 채로 남는다
    shown_sentences = {it.id for it in await _due_review_items(uid, db) if it.kind == "sentence"}
    reviews_overdue = sum(1 for r in reviews if r.due_date and r.due_date < today_local
                          and (r.kind != "sentence" or r.id in shown_sentences))

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
    오늘의 복습(/api/review/due)에 문장 복습으로 나온 문장은 뺀다. 같은 문장이 오답과 예정 복습에 두 번 세어지지 않게 하고,
    예정일에 다시 읽는 쪽(원문을 먼저 보지 않는 복습)으로 풀게 한다. 예정일 전이거나 하루 상한에 밀린 문장은 그대로 여기 남는다.
    """
    from database import Progress
    from sqlalchemy import select
    scheduled = {it.ref for it in await _due_review_items(current_user.id, db) if it.kind == "sentence"}

    result = await db.execute(
        select(Progress)
        .where(Progress.user_id == current_user.id)
        .order_by(Progress.created_at.desc())   # 최신순 — 각 문장의 첫 등장이 가장 최근 시도
        .limit(200)
    )
    records = result.scalars().all()
    # 복습 탭 '2회 틀렸어요'(189:35) — 같은 창(최근 200회) 안에서 그 문장을 60점 미만으로 끝낸 횟수
    wrong_counts: dict = {}
    for p in records:
        if p.score < 60:
            wrong_counts[p.sentence] = wrong_counts.get(p.sentence, 0) + 1
    seen: set = set()
    unique = []
    for p in records:
        if p.sentence in seen:
            continue
        seen.add(p.sentence)                     # 이 문장의 '가장 최근' 시도만 판단
        if p.score < 60 and p.sentence not in scheduled:   # 최근에도 틀렸을 때만 복습 대상
            unique.append({
                "sentence": p.sentence,
                "situation": p.situation,
                "difficulty_level": p.difficulty_level,
                "score": round(p.score, 1),
                "created_at": _iso_utc(p.created_at),   # 가장 최근에 틀린 시각
                "wrong_count": wrong_counts[p.sentence],
            })
        if len(unique) >= 10:
            break
    return unique


# ============================================
# Curriculum (단계형 커리큘럼) — 재설계 Phase 1
# ============================================
import curriculum as _curriculum

# 심사·데모 편의: 단계 잠금 해제(순차 잠금 로직은 유지하되 표시만 unlocked로). LIPLAB_UNLOCK_ALL:
#   1(기본, 전시앱) 모든 계정 · demo 둘러보기 데모 계정만(실사용·파일럿 계정은 숙달 순서대로) · 0 아무도.
def _unlock_all_for(user) -> bool:
    mode = os.getenv("LIPLAB_UNLOCK_ALL", "1")
    if mode == "demo":
        return (getattr(user, "email", "") or "").lower() == _DEMO_EMAIL
    return mode == "1"

_STAGE1_MIN_ATTEMPTS = 8       # 숙달 판정 최소 시도
# 1·2단계(4지선다) 숙달 점수는 편향 보정 지수 이동 평균(최근 답에 무게, docs/mastery-ewma.md)이고 문턱은 85다.
# 가상 학습자 시뮬레이션에서 누적 정답률 70% 대비 거짓 숙달 12.4 -> 6.5%, 숙달까지 지연 39 -> 28번, 처음부터 잘하는
# 학습자는 그대로 8번이었다(시드 2 확인). 초반 실패가 끝까지 남던 누적 방식의 문제를 던다.
_STAGE1_MASTERY = 85.0
_STAGE2_MIN_ATTEMPTS = 6
_STAGE2_MASTERY = 85.0
_STAGE12_EWMA_ALPHA = 0.08


def _ewma_mastery(prev_estimate, prev_attempts, correct, alpha: float = _STAGE12_EWMA_ALPHA) -> float:
    """편향 보정 지수 이동 평균(0~100) 한 번 갱신. 저장된 추정값과 그 전 시도 수로 원래 평균을 되살린다
    (스키마 변경 없음). 초반에는 누적 평균에 가깝고 뒤로 갈수록 최근 답에 무게가 실린다.
    correct는 정오(bool) 또는 성공 정도(0~1 실수, 감속 재생 정답 0.5 등, docs/mastery-ewma.md 7절). 3단계 4지선다 오답의 우연 보정
    값 −1/3(10절)처럼 음수도 받는다. 결과는 0~100으로 잘라 저장하므로 음수는 추정값을 더 빨리 내릴 뿐이다."""
    n = max(0, int(prev_attempts or 0))
    success = min(1.0, max(-1.0, float(correct)))
    raw = float(prev_estimate or 0.0) * (1 - (1 - alpha) ** n)
    raw += alpha * (100.0 * success - raw)
    return min(100.0, max(0.0, raw / (1 - (1 - alpha) ** (n + 1))))   # 부동소수점 오차로 100을 넘지 않게


# 감속 재생(학습자 선택 속도 × 약한 입모양 적응 감속이 1.0배 미만)에서 얻은 1·2단계 정답은 숙달 추정에 성공 0.5로 넣는다.
# 2단계 화면은 숙달 추정값이 _NATURAL_SPEED_GATE 이상이면 적응 감속을 끄고 자연 속도로 낸다(자연 속도 확인 구간).
# 가상 학습자 시뮬레이션에서 거짓 숙달 10.6 → 4.9%, 감속 안 하는 학습자 지연 27번 그대로(시드 1 확인, docs/mastery-ewma.md 7절).
_SLOW_SPEED_CREDIT = 0.5
_NATURAL_SPEED_GATE = 70.0


def _speed_credit(success: float, speed) -> float:
    """정답 성공 정도에 재생 속도를 반영한다. 속도를 보내지 않은 예전 화면·1단계는 1.0배로 본다."""
    try:
        s = float(speed) if speed is not None else 1.0
    except (TypeError, ValueError):
        s = 1.0
    return success * _SLOW_SPEED_CREDIT if s < 0.999 else success
# 3·4단계는 점수(0~100)를 내는 활동이라 'PASS 이상이면 성공 1회'로 환산한다. 3단계 숙달 점수는 9/27부터 1·2단계와 같은 편향 보정
# 지수 이동 평균(a 0.08)이고 문턱은 80이다(시뮬레이션 사전 기준 통과: 거짓 숙달 17.1 → 10.9%, 지연 39 → 25번, 숙련 학습자 5번 그대로,
# docs/mastery-ewma.md 5절). 4단계는 누적 합격률 그대로다.
_STAGE3_MIN_ATTEMPTS = 5       # 문장 연습·문맥 추론
_STAGE3_MASTERY = 80.0
_STAGE3_PASS = 60.0            # 문장 1건을 '성공'으로 볼 최소 점수
# 말하기 D-GOP 문장 점수의 재검사 측정 오차(608 반복 세션 22개, ICC 0.684, docs/scoring-analyses-2026-10.md S14). 판정 보류 폭에 쓴다
_SPEAK_SEM = 7.5


def speak_hold(score, stage_pass, mode, passed, is_probe=False) -> bool:
    """판정 보류인가: 낱말·문장 단계(D-GOP 점수, SEM을 잰 조건)에서 점수가 합격선 ± 1 SEM 안. 확인 낱말·지표 단계는 해당 없음."""
    if stage_pass is None or passed is None or score is None or is_probe or mode not in ("word", "sentence"):
        return False
    return abs(float(score) - float(stage_pass)) < _SPEAK_SEM
# 틀린 문장 복습(ReviewLanding)·북마크 연습(Bookmarks) 세션의 scenario_id 접두어. 두 화면은 원문을 목록에 보여 준 뒤 풀게
# 하므로, 그 답은 3단계 숙달에 넣지 않고(입모양·단어 SRS 복습과 같은 원칙) 추천 난이도 계산에서도 뺀다. 예전에는 넣어서
# 새 문장 통과율 0.5인 학습자의 20레슨 안 3단계 숙달 확률이 0.227에서 0.676으로 올랐다(모의실험, 복습 답 통과 0.95 가정).
# 문장 간격 반복 복습(오늘의 복습, srs_review_*)도 3단계 숙달·추천 난이도에서 뺀다. 한 번 틀린 문장을 다시 읽는 답이라
# 처음 보는 문장을 읽는 3단계 숙달의 근거로 쓰지 않는다(같은 문장을 되풀이해 맞히면 숙달에 닿는 것을 막는다).
_SENTENCE_REVIEW_PREFIX = "srs_review_"
_REVIEW_SCENARIO_PREFIXES = ("mistake_review_", "bookmark_", _SENTENCE_REVIEW_PREFIX)


def _is_review_scenario(scenario_id) -> bool:
    return str(scenario_id or "").startswith(_REVIEW_SCENARIO_PREFIXES)


# 3단계 4지선다(answer_mode 'choice')는 몰라도 25%를 맞힌다. 숙달 이동 평균에는 우연 보정으로 정답 1, 오답 −1/3을 넣는다(한 답의
# 기댓값이 '알아본 확률'이 된다). 주관식·서술형은 합격 1, 불합격 0 그대로다. 가상 학습자 시뮬레이션에서 거짓 숙달 12.6 → 11.0%,
# 지연 21 → 23번, 200번 안 숙달 비율 99.99 → 99.96%(시드 1 확인, 재인 가정 L; H도 통과, docs/mastery-ewma.md 10절).
# 4지선다 정답을 0.5·0.67·0.75로 깎는 후보는 거짓 숙달을 더 줄였지만 지연이 5~17번 늘어 기준을 넘지 못했다.
_CHOICE_WRONG_CREDIT = -1.0 / 3
_ANSWER_MODES = ("choice", "typed")


def _answer_mode(value):
    """저장할 답 방식. 'choice'·'typed'만 남기고 나머지(옛 화면이 보내지 않음 등)는 None."""
    return value if value in _ANSWER_MODES else None


def _stage3_credit(passed: bool, answer_mode) -> float:
    """3단계 숙달 이동 평균에 넣을 성공 정도."""
    if answer_mode == "choice":
        return 1.0 if passed else _CHOICE_WRONG_CREDIT
    return 1.0 if passed else 0.0


_STAGE4_MIN_ATTEMPTS = 4       # 대화 실전
_STAGE4_MASTERY = 75.0        # 최근 가중 합격률(편향 보정 이동 평균, 9/27 밤 docs/mastery-ewma.md 6절, 예전 누적 60%)
_STAGE4_PASS = 55.0            # 대화 1턴을 '성공'으로 볼 최소 이해도
# 단계별 숙달 기준(최소 시도, 문턱, 합격 점수). /api/curriculum/stages에 실어 학습 경로·사용법 가이드가 같은 숫자를 보인다(9/28).
_STAGE_RULES = {
    1: (_STAGE1_MIN_ATTEMPTS, _STAGE1_MASTERY, None),
    2: (_STAGE2_MIN_ATTEMPTS, _STAGE2_MASTERY, None),
    3: (_STAGE3_MIN_ATTEMPTS, _STAGE3_MASTERY, _STAGE3_PASS),
    4: (_STAGE4_MIN_ATTEMPTS, _STAGE4_MASTERY, _STAGE4_PASS),
}


def _settle_mastery(sp, reached: bool) -> None:
    """숙달 상태 갱신. 한번 숙달하면 유지한다(정확도가 조금 떨어졌다고 다음 단계를 다시 잠그지 않게).
    처음 숙달하는 순간의 시도 수·시각을 남긴다(학습 효과 리포트의 숙달 도달 시행수, docs/eval-metrics.md)."""
    from datetime import datetime as _dt
    if sp.status == "mastered":
        return
    if reached:
        sp.status = "mastered"
        sp.mastered_attempts = sp.attempts
        sp.mastered_at = _dt.utcnow()
    else:
        sp.status = "in_progress"


async def _bump_stage_progress(user_id: int, stage: int, passed: bool,
                               min_attempts: int, mastery_pct: float, db, credit: float = None):
    """단계별 진행률 rolling 갱신(1건 채점 → 시도·정답 누적, 숙달 판정). sp 반환.
    숙달 점수는 3·4단계가 편향 보정 이동 평균(_ewma_mastery, 1·2단계는 각 채점 경로에서 같은 식). 커밋은 호출부에서 처리한다.
    credit이 오면 이동 평균에는 passed 대신 그 성공 정도를 넣는다(3단계 4지선다의 우연 보정, _stage3_credit). 정답 수는 passed로 센다."""
    from database import StageProgress
    from sqlalchemy import select
    r = await db.execute(select(StageProgress).where(
        StageProgress.user_id == user_id, StageProgress.stage == stage))
    sp = r.scalars().first()
    if sp is None:
        # default=0은 flush 시점 적용 → 즉시 증감하려면 초기값 명시
        sp = StageProgress(user_id=user_id, stage=stage, status="in_progress",
                           attempts=0, correct=0, mastery_score=0.0)
        db.add(sp)
    sp.attempts += 1
    if passed:
        sp.correct += 1
    if stage in (3, 4):
        sp.mastery_score = _ewma_mastery(sp.mastery_score, sp.attempts - 1, passed if credit is None else credit)
    else:
        sp.mastery_score = (sp.correct / sp.attempts * 100) if sp.attempts else 0.0
    _settle_mastery(sp, sp.attempts >= min_attempts and sp.mastery_score >= mastery_pct)
    return sp

from datetime import date as _sr_date, timedelta as _sr_delta


async def _srs_apply(user_id: int, kind: str, ref, quality: int, db, create: bool = True, log: dict = None) -> dict:
    """SM-2 경량 스케줄러(srs.schedule)를 한 복습 항목에 적용. 항목의 ease/간격/반복/누수를
    갱신하고 due_date를 다시 잡는다. 간격이 충분히 커지면(졸업) 큐에서 제거한다.
    항목이 없을 때 quality<3(실패)이고 create면 새로 등록한다. commit은 호출부.
    FSRS 그림자 모드(C11, fsrs_shadow.py): SM-2가 항목을 갱신할 때마다 FSRS 상태도 함께 갱신하고, log({source, answer_mode, speed})가
    오면 예정일이 된 항목의 답을 회상 확률 예측과 함께 review_logs에 남긴다. 간격·졸업은 SM-2 그대로다.
    log는 정답·오답을 모두 보내는 경로(복습 화면, 문장·말하기의 _sr_touch)만 준다. 레슨 오답만 오는 경로(_srs_schedule_wrong)까지
    남기면 맞힌 답이 빠져 통과율이 낮게 기록되기 때문이다.
    반환: {removed, due_date, interval_days}."""
    import srs
    from database import ReviewItem
    from sqlalchemy import select
    ref = str(ref)
    if not ref:
        return {"removed": False, "due_date": None, "interval_days": None}
    r = await db.execute(select(ReviewItem).where(
        ReviewItem.user_id == user_id, ReviewItem.kind == kind, ReviewItem.ref == ref))
    item = r.scalars().first()

    if item is None:
        if not create or quality >= 3:
            return {"removed": False, "due_date": None, "interval_days": None, "found": False}
        s = srs.schedule(quality)  # 첫 실패 → 내일 재등장
        due = (_kst_today() + _sr_delta(days=s["interval_days"])).isoformat()
        fs = _fsrs_first(quality, log)
        db.add(ReviewItem(user_id=user_id, kind=kind, ref=ref, due_date=due,
                          interval_days=s["interval_days"], ease_factor=s["ease_factor"],
                          repetitions=s["repetitions"], lapses=s["lapses"],
                          fsrs_stability=fs.get("stability"), fsrs_difficulty=fs.get("difficulty"),
                          last_review_on=_kst_today().isoformat() if fs else None))
        return {"removed": False, "due_date": due, "interval_days": s["interval_days"]}

    # 아직 복습일이 아닌 항목은 맞혀도 간격을 늘리지 않는다(예전에는 '다시 말하기'로 한자리에서 다섯 번 맞히면
    # 1·6·14·32·74일로 늘어 졸업했다). 틀리면 날짜와 상관없이 다시 잡는다.
    if quality >= 3 and item.due_date and item.due_date > _kst_today().isoformat():
        return {"removed": False, "due_date": item.due_date, "interval_days": item.interval_days,
                "found": True, "early": True}
    # 예정일이 된 항목에 답했으면 복습 1회로 센다('복습왕' 배지). 복습 화면(/api/review/answer)과 말하기 복습(_sr_touch)이
    # 모두 여기를 지난다. 같은 날 레슨에서 다시 틀린 항목은 예정일이 내일이라 세지 않는다
    due_now = bool(item.due_date and item.due_date <= _kst_today().isoformat())
    if due_now:
        await _count_review_done(user_id, db)
    _fsrs_shadow(user_id, item, quality, db, log if due_now else None)   # SM-2 갱신 전 상태(간격)로 예측한다
    s = srs.schedule(quality, ease_factor=item.ease_factor, interval_days=item.interval_days,
                     repetitions=item.repetitions, lapses=item.lapses)
    if s["graduated"] and quality >= 3:
        await db.delete(item)   # 졸업 — 큐에서 제거
        return {"removed": True, "due_date": None, "interval_days": s["interval_days"], "found": True}
    item.interval_days = s["interval_days"]
    item.ease_factor = s["ease_factor"]
    item.repetitions = s["repetitions"]
    item.lapses = s["lapses"]
    item.due_date = (_kst_today() + _sr_delta(days=s["interval_days"])).isoformat()
    return {"removed": False, "due_date": item.due_date, "interval_days": item.interval_days, "found": True}


def _fsrs_first(quality: int, log: dict = None) -> dict:
    """새 복습 항목의 FSRS 첫 상태(처음 본 답의 등급으로). 실패해도 SM-2 등록은 막지 않는다."""
    try:
        import fsrs_shadow as _fs
        lg = log or {}
        return _fs.step(None, _fs.grade_for(quality, lg.get("answer_mode"), lg.get("speed")), None)
    except Exception as e:   # 그림자 모드라 간격 계산을 막지 않는다
        print(f"[WARN] fsrs first state failed: {e}")
        return {}


def _fsrs_shadow(user_id: int, item, quality: int, db, log: dict = None) -> None:
    """FSRS 상태를 한 걸음 옮기고(item에 저장), log가 오면 이번 답과 예측을 review_logs에 남긴다. 간격은 건드리지 않는다.
    상태가 없던 예전 항목은 이번 답으로 첫 상태를 만들고 예측(r_fsrs·p_fsrs)은 NULL로 남긴다. 실패해도 SM-2는 그대로 진행한다."""
    try:
        import fsrs_shadow as _fs
        from datetime import date as _date, timedelta as _td
        from database import ReviewLog
        lg = log or {}
        today = _kst_today()
        last = None
        if item.last_review_on:
            try:
                last = _date.fromisoformat(item.last_review_on)
            except ValueError:
                last = None
        if last is None:
            ts = item.updated_at or item.created_at   # 예전 항목: SM-2가 마지막으로 갱신한 시각(UTC)을 KST 날짜로
            last = (ts + _td(hours=9)).date() if ts else None
        elapsed = max(0, (today - last).days) if last else None
        mode, speed = lg.get("answer_mode"), lg.get("speed")
        grade = _fs.grade_for(quality, mode, speed)
        prev = ({"stability": item.fsrs_stability, "difficulty": item.fsrs_difficulty}
                if item.fsrs_stability is not None and item.fsrs_difficulty is not None else None)
        st = _fs.step(prev, grade, elapsed)
        if log is not None:
            guess = _fs.guess_rate(mode)
            db.add(ReviewLog(
                user_id=user_id, kind=item.kind, ref=item.ref, source=lg.get("source"), reviewed_on=today.isoformat(),
                elapsed_days=elapsed, quality=int(quality), grade=grade, passed=quality >= 3, answer_mode=mode,
                speed=speed, guess=guess, r_fsrs=st["r"], p_fsrs=_fs.observed_probability(st["r"], guess),
                p_sm2=_fs.observed_probability(_fs.sm2_proxy(elapsed, item.interval_days), guess),
                sm2_interval=item.interval_days, fsrs_stability=item.fsrs_stability, fsrs_difficulty=item.fsrs_difficulty))
        item.fsrs_stability = st["stability"]
        item.fsrs_difficulty = st["difficulty"]
        item.last_review_on = today.isoformat()
    except Exception as e:   # 그림자 모드라 간격 계산을 막지 않는다
        print(f"[WARN] fsrs shadow failed: {e}")


async def _count_review_done(user_id: int, db) -> None:
    """학습자 프로필의 누적 복습 횟수를 1 올린다. commit은 호출부(_srs_apply와 같다)."""
    from database import LearningProfile
    from sqlalchemy import select
    prof = (await db.execute(select(LearningProfile).where(LearningProfile.user_id == user_id))).scalars().first()
    if prof is None:
        db.add(LearningProfile(user_id=user_id, reviews_completed=1))
    else:
        prof.reviews_completed = (prof.reviews_completed or 0) + 1


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
        # 새 계정의 첫 화면은 여러 요청(단계 목록·말하기 커리큘럼 등)이 동시에 와서 둘 다 여기서 만들려다 UNIQUE(user_id)에 걸려
        # 한쪽이 500이 났다(9/28 로컬 확인). 먼저 만든 쪽이 있으면 되돌리고 그 행을 읽는다.
        from sqlalchemy.exc import IntegrityError
        prof = LearningProfile(user_id=user_id)
        db.add(prof)
        try:
            await db.commit()
            await db.refresh(prof)
        except IntegrityError:
            await db.rollback()
            r = await db.execute(select(LearningProfile).where(LearningProfile.user_id == user_id))
            prof = r.scalar_one()
    return prof


async def _compute_stages(current_user, db):
    """사용자별 단계 상태(학습 경로·StageGate·잠긴 단계 기록 막기가 함께 쓴다). (prof, 단계 목록)."""
    from database import StageProgress
    from sqlalchemy import select

    prof = await _get_or_create_profile(current_user.id, db)
    r = await db.execute(select(StageProgress).where(StageProgress.user_id == current_user.id))
    sp_map = {sp.stage: sp for sp in r.scalars().all()}

    stages = []
    for s in _curriculum.STAGES:
        st = dict(s)
        stage = s["stage"]
        rule = _STAGE_RULES.get(stage)
        if rule:
            st["min_attempts"], st["mastery"] = rule[0], rule[1]
            if rule[2] is not None:
                st["pass"] = rule[2]
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
        else:  # 2·3·4단계 — 직전 단계를 숙달하거나, 배치검사·건너뛰기로 그 단계까지 왔으면(current_stage) 해금
            prev = sp_map.get(stage - 1)
            sp = sp_map.get(stage)
            by_pointer = bool(prof.placed) and stage <= (prof.current_stage or 0)
            # 직전 단계가 이번 계산에서 열려 있어야 한다. 예전에는 직전 단계 행만 보아, 잠긴 단계에 쌓인 기록
            # (문맥 추론은 3단계에 쌓인다)으로 2·3단계가 잠긴 채 4단계가 열렸다.
            prev_open = bool(stages) and stages[-1].get("status") not in ("locked", "coming_soon")
            if not ((prev_open and prev is not None and prev.status == "mastered") or by_pointer):
                st["status"] = "locked"        # 전 단계 숙달 후 열림
            elif sp is None:
                st["status"] = "unlocked"
            else:
                st["status"] = sp.status
                st["mastery_score"] = round(sp.mastery_score, 1)
                st["attempts"] = sp.attempts
        stages.append(st)

    if _unlock_all_for(current_user):
        for st in stages:
            if st.get("status") == "locked":
                st["status"] = "unlocked"
    return prof, stages


async def _stage_open(current_user, stage: int, db) -> bool:
    """그 단계가 지금 열려 있는가. 잠긴 단계의 답은 숙달에 넣지 않는다(API를 바로 불러 순서를 건너뛰지 못하게)."""
    _, stages = await _compute_stages(current_user, db)
    st = next((x for x in stages if x.get("stage") == stage), None)
    return st is not None and st.get("status") not in ("locked", "coming_soon")


@app.get("/api/curriculum/stages")
async def curriculum_stages(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """단계형 학습 경로 + 사용자별 상태(대시보드/오늘의 학습 구동)."""
    prof, stages = await _compute_stages(current_user, db)
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
    # 짝은 화면이 쓰는 미리보기(같아 보임 3, 달라 보임 2, VisemeLiteracy.pickPairPreview와 같은 규칙)만 보낸다. 예전에는 921쌍
    # 전부(약 100KB)를 보냈다(이 응답을 쓰는 화면은 1단계 미리보기와 복습의 레슨 이름뿐).
    pairs = _curriculum.MINIMAL_PAIRS
    preview = [p for p in pairs if p.get("same_looking")][:3] + [p for p in pairs if not p.get("same_looking")][:2]
    return {
        "lessons": lessons,
        "homophene_clusters": _curriculum.HOMOPHENE_CLUSTERS,
        "minimal_pairs": preview,
        "anchors": _curriculum.VISIBLE_ANCHORS,
    }


# 보기 목록 길이 상한(선다형은 4지, 문맥 문항은 보기 3~5개). 넘거나 모양이 틀리면 채점은 하고 보기만 남기지 않는다
_OPTIONS_MAX = 8


class TrialMeta(BaseModel):
    """학습 시행에 함께 오는 측정 필드(파일럿 로그 사양 점검 P0, docs/pilot/log-spec-audit.md). 모두 선택이라 예전 화면도 그대로 채점된다.
    rt_from_onset_ms: 문항 표시(자극 재생 시작)부터 답 확정까지 ms. talker: 레슨 가상 화자 id(lib/talkers). hint_used: 힌트를 봤는지."""
    rt_from_onset_ms: Optional[int] = Field(None, ge=0, le=3_600_000)
    talker: Optional[str] = Field(None, max_length=16)
    hint_used: Optional[bool] = None


import re as _re_talker
_TALKER_ID_RE = _re_talker.compile(r"^[A-Za-z0-9_-]{1,16}$")


def _clean_talker(t) -> Optional[str]:
    return t if isinstance(t, str) and _TALKER_ID_RE.match(t) else None


def _trial_meta(data) -> dict:
    """TrialAttempt에 넣을 측정 열. 학습 화면이 보내지 않은 값은 NULL로 둔다."""
    return {"rt_from_onset_ms": getattr(data, "rt_from_onset_ms", None), "talker": _clean_talker(getattr(data, "talker", None)),
            "hint_used": getattr(data, "hint_used", None)}


class RecognitionSubmit(TrialMeta):
    viseme_id: int   # 제시된(정답) 그룹
    chosen_id: int   # 사용자가 고른 그룹
    speed: Optional[float] = Field(None, ge=0.1, le=4.0)   # 답하기 전에 본 실제 재생 속도(1.0 미만 정답은 숙달에 0.5)
    options: Optional[list] = None   # 보여 준 보기(입모양 번호, 보인 순서). 없으면 예전 화면


def _trial_options(options, target, chosen=None) -> Optional[list]:
    """시행 기록에 남길 보기 목록(TrialAttempt.options). 문자열로 맞추고, 정답이 없거나 고른 답이 보기 밖이거나 겹치는 보기가 있으면
    남기지 않는다(None). 보기를 보내지 않는 예전 화면도 그대로 채점된다. 기회로 나눈 혼동률(docs/confusion-pair-serving.md 5.4)이
    이 목록을 '그 시행에 보인 보기'로 믿으므로, 앞뒤가 맞지 않는 목록은 버린다."""
    if not options or len(options) > _OPTIONS_MAX or not all(isinstance(o, (str, int)) for o in options):
        return None
    out = [str(o).strip()[:50] for o in options]
    if len(set(out)) != len(out) or str(target) not in out or (chosen is not None and str(chosen) not in out):
        return None
    return out


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

    try:
        # 1단계 진행/숙달 갱신
        r = await db.execute(select(StageProgress).where(
            StageProgress.user_id == current_user.id, StageProgress.stage == 1))
        sp = r.scalars().first()
        if sp is None:
            # default=0은 flush 시점에 적용되므로 즉시 증감하려면 초기값을 명시한다
            sp = StageProgress(user_id=current_user.id, stage=1, status="in_progress",
                               attempts=0, correct=0, mastery_score=0.0)
            db.add(sp)
        sp.attempts += 1
        if correct:
            sp.correct += 1
        # 최근 답에 무게(docs/mastery-ewma.md), 감속 재생 정답은 0.5(7절)
        sp.mastery_score = _ewma_mastery(sp.mastery_score, sp.attempts - 1, _speed_credit(1.0 if correct else 0.0, data.speed))
        _settle_mastery(sp, sp.attempts >= _STAGE1_MIN_ATTEMPTS and sp.mastery_score >= _STAGE1_MASTERY)

        # 취약 입모양 반영 — 기존 분석·적응 로직과 통합
        r2 = await db.execute(select(WeakViseme).where(
            WeakViseme.user_id == current_user.id, WeakViseme.viseme_id == data.viseme_id))
        wv = r2.scalars().first()
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
                            target=str(data.viseme_id), chosen=str(data.chosen_id), correct=correct, confusions=[],
                            speed=data.speed, options=_trial_options(data.options, data.viseme_id, data.chosen_id),
                            **_trial_meta(data)))

        await db.commit()
        await db.refresh(sp)
    except Exception as e:
        await db.rollback()
        raise _server_error(e, "recognition submit failed")

    return {
        "correct": correct,
        "target": {"viseme_id": data.viseme_id, "name": target["name"], "teach": target["teach"]},
        "mastery_score": round(sp.mastery_score, 1),
        "attempts": sp.attempts,
        "mastered": sp.status == "mastered",
        "xp_gained": award["xp_gained"],
        "streak_count": award["streak_count"],
    }


# 1단계 '같은지 다른지'(AX) 문항(docs/mastery-ewma.md 11절, A0(2)). 아바타가 음절 둘을 차례로 말하고 학습자가 같음·다름을 고른다.
# 사전 등록한 설계(오답 −1로 숙달에 반영)는 거짓 숙달을 늘려 탈락했고, 숙달에서 뺀 A0(2)가 사후 탐색 뒤 시드 1 확인을 통과했다.
# 그래서 이 답은 1단계 숙달(시도 수·추정값)에 넣지 않고 시행 기록(item_type 'viseme_ax')과 XP에만 남긴다.
_AX_CHOICES = ("same", "different")


class RecognitionAxSubmit(TrialMeta):
    a: str = Field(..., max_length=2)   # 먼저 보인 음절
    b: str = Field(..., max_length=2)   # 나중에 보인 음절
    chosen: str                         # 'same' | 'different'
    options: Optional[list] = None      # 보인 버튼 순서(['same', 'different']). 없으면 예전 화면


@app.post("/api/curriculum/recognition-ax")
async def curriculum_recognition_ax(data: RecognitionAxSubmit, current_user=Depends(get_current_user),
                                    db: AsyncSession = Depends(get_db)):
    """1단계 AX 문항 채점. 정답은 화면이 아니라 curriculum.ax_pair(두 음절의 입모양 무리 소속)로 정하고, 아바타에서 애매한 짝은
    400으로 거절한다. 1단계 숙달·취약 입모양·복습 큐는 건드리지 않는다."""
    from database import TrialAttempt
    pair = _curriculum.ax_pair(data.a, data.b)
    if pair is None:
        raise HTTPException(status_code=400, detail="invalid ax pair")
    if data.chosen not in _AX_CHOICES:
        raise HTTPException(status_code=400, detail="chosen must be same or different")
    key = "same" if pair["same"] else "different"
    correct = data.chosen == key
    opts = data.options if isinstance(data.options, list) and sorted(map(str, data.options)) == sorted(_AX_CHOICES) else None
    try:
        db.add(TrialAttempt(user_id=current_user.id, stage=1, item_type="viseme_ax", target=f"{data.a}/{data.b}",
                            chosen=data.chosen, correct=correct, confusions=[],
                            options=[str(o) for o in opts] if opts else None, **_trial_meta(data)))
        award = _award_xp_and_streak(current_user, 15 if correct else 3)
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise _server_error(e, "recognition ax submit failed")
    return {"correct": correct, "answer": key, "same": pair["same"], "inside": pair["inside"],
            "xp_gained": award["xp_gained"], "streak_count": award["streak_count"]}


class WordAnswer(TrialMeta):
    word: str = Field(..., max_length=50)
    correct: bool
    chosen: Optional[str] = Field(None, max_length=50)   # 사용자가 실제로 고른 단어(오답 시 자모 혼동 분석용)
    speed: Optional[float] = Field(None, ge=0.1, le=4.0)   # 답하기 전에 본 실제 재생 속도(학습자 선택 × 적응 감속)
    # 'typed'면 주관식(단어 입력, 커리큘럼 개선 계획 1-2): chosen이 입력한 글이고 서버가 visual_difficulty.typed_word_verdict로 채점한다
    mode: Optional[str] = Field(None, max_length=10)
    options: Optional[list] = None   # 보여 준 보기(정답 포함, 보인 순서). 주관식은 없음
    # 짝 탐색 문항이면 /curriculum/words의 probes[].probe를 그대로(자리·target·read·대비 단어). 서버가 보기와 맞는지 확인해 남긴다
    probe: Optional[dict] = None


def _excluded_training_words() -> set:
    """훈련·배치·말하기에서 내지 않는 단어: 사전·사후 표준검사 정답(문항 노출 방지, 축 I)과 드문 말(9/27 단어 은행 감사)."""
    import assessment as _asmt
    return set(_asmt.test_only_words()) | set(getattr(_curriculum, "STAGE2_EXCLUDED", {}))


# 2단계 서빙 풀의 정적 표(난이도·분위·보기 부류). 풀(단어 은행 - 표준검사 단어)이 같으면 재사용한다.
# 보기 부류는 처음 만들 때 약 1.5초가 들어 스레드에서 만든다(이후 요청은 약 20ms).
_STAGE2_TABLE = {"key": None, "table": None, "pairs": None}


def _stage2_table():
    import assessment as _asmt
    import visual_difficulty as _vd
    tw = _asmt.test_only_words()
    ex = getattr(_curriculum, "STAGE2_EXCLUDED", {})   # 드문 말·홀로 안 쓰이는 말(9/27 감사)은 문제로도 오답으로도 내지 않는다
    pool = tuple(w["word"] for w in _curriculum.WORD_BANK if w["word"] not in tw and w["word"] not in ex)
    if _STAGE2_TABLE["key"] != pool:
        table = _vd.Stage2Table(pool)
        for w in table.words:
            table.classes(w)
        _STAGE2_TABLE["key"], _STAGE2_TABLE["table"], _STAGE2_TABLE["pairs"] = pool, table, None
    return _STAGE2_TABLE["table"]


def _stage2_pairs():
    """서빙 풀의 짝별 대비 단어 표(confusion_pairs.PairIndex). 풀이 같으면 재사용한다."""
    import confusion_pairs as _cp
    table = _stage2_table()
    if _STAGE2_TABLE["pairs"] is None or _STAGE2_TABLE["pairs"].index is not table.index:
        _STAGE2_TABLE["pairs"] = _cp.PairIndex(table)
    return _STAGE2_TABLE["pairs"]


# 혼동 짝을 셀 선다형 시행 유형(자모 혼동이 남는 것). 1단계 입모양 퀴즈는 무리 선다라 자모가 없다.
_PAIR_TRIAL_TYPES = ("word", "context", "closure")


async def _learner_opportunities(user_id: int, db):
    """학습자의 짝별 기회·혼동 수(confusion_pairs.OpportunityCounter). 보기 기록(options)이 있는 최근 선다형 200행에서,
    정답이 아닌 보기마다 정답과 갈린 눈으로 가를 수 있는 자모 짝을 기회로, 고른 보기의 짝을 혼동으로 센다
    (docs/confusion-pair-serving.md 6.1). 탐색 문항이 이 수로 다음에 볼 짝을 고른다(상한 신뢰 순서, 7절)."""
    import confusion_pairs as _cp
    from database import TrialAttempt
    from sqlalchemy import select
    rows = (await db.execute(
        select(TrialAttempt.target, TrialAttempt.chosen, TrialAttempt.options)
        .where(TrialAttempt.user_id == user_id, TrialAttempt.item_type.in_(_PAIR_TRIAL_TYPES),
               TrialAttempt.options.isnot(None))
        .order_by(TrialAttempt.created_at.desc(), TrialAttempt.id.desc()).limit(_cp.OPP_ROWS))).all()
    cnt = _cp.OpportunityCounter()
    for target, chosen, options in rows:
        if target and isinstance(options, list) and target in options:
            cnt.add(target, chosen, [o for o in options if isinstance(o, str)])
    return cnt


@app.get("/api/curriculum/words")
async def curriculum_words(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """2단계 콘텐츠: 단어 은행 + 단어별 오답 보기 + 출제 가중(visual_difficulty.stage2_plan).
    distractors: 입모양이 완전히 같은 단어(동구형이음)와 입 안쪽 무리 차이뿐인 단어를 뺀 오답 3개. 숙달 전에는 보이는
      최소대립 1개 + 입모양이 다른 단어 2개, 숙달 뒤에는 보이는 최소대립 3개. 예전에는 최소대립 짝을 먼저 넣었는데 짝의
      약 2/3가 동구형이음이라 문항의 57%가 입모양만으로는 풀 수 없었고, 입모양을 완벽히 읽어도 평균 65%였다.
    priority: 시각 난이도 분위가 목표 위치(2단계에서 답한 수로 쉬운 쪽 0.15에서 0.9까지)에 가까울수록 크고, 약점 비심을
      담으면 1.5배. 예전 tier 가중은 짧고 입모양이 같은 단어가 많은 1음절어(가장 어려움)를 가장 자주 냈다.
    최소대립 짝 목록(127KB)은 보내지 않는다: 이 응답을 쓰는 화면(단어·복습·말하기)은 단어 필드만 읽고, 1단계 짝 미리보기는
    viseme-lessons의 것을 쓴다."""
    import asyncio as _asyncio
    import random as _random
    import knowledge_tracing as _kt
    import visual_difficulty as _vd
    from database import WeakViseme as _WV, StageProgress as _SP
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
    sp = (await db.execute(_select(_SP).where(_SP.user_id == current_user.id, _SP.stage == 2))).scalars().first()
    n_answers = int(sp.attempts or 0) if sp else 0
    mastered = bool(sp and sp.status == "mastered")
    # 표준검사 사전·사후 문항 단어는 훈련 풀에서 뺀다(축 I). 오답 보기도 이 풀 안에서만 고른다.
    table = await _asyncio.to_thread(_stage2_table)
    rng = _random.Random()
    plan = _vd.stage2_plan(table, n_answers=n_answers, mastered=mastered, weak_visemes=weak, rng=rng)
    meta = {w["word"]: w for w in _curriculum.WORD_BANK}
    words = [{**meta.get(e["word"], {}), **e} for e in plan["words"]]
    context_items = await _stage2_context_items(current_user.id, db)
    # 짝 탐색 문항(docs/confusion-pair-serving.md 5.4-2, 7절): 레슨 12문항 중 선다형 1문항을 고른 짝의 target 자모 단어 + 대비 단어
    # 보기로. 짝은 보기 기록으로 센 기회·혼동 수의 상한 신뢰 순서(기회가 적은 짝, 기회로 나눈 혼동률이 높은 짝 먼저)로 고른다.
    # 같은 짝의 단어 몇 개를 주고 화면이 레슨에서 아직 안 낸 첫 단어를 쓴다. 겨냥 출제(가중·대비 보기)는 기준 미달로 넣지 않았다.
    probes = []
    try:
        import confusion_pairs as _cp
        counter = await _learner_opportunities(current_user.id, db)
        pidx = await _asyncio.to_thread(_stage2_pairs)
        probes = _cp.probe_items(pidx, (), {e["word"]: e["priority"] for e in plan["words"]},
                                 plan["option_level"], table.classes, rng, counter=counter)
        probes = [{**meta.get(p["word"], {}), **p} for p in probes]
    except Exception as e:   # 탐색 문항이 없어도 레슨은 된다
        logging.getLogger("liplab").warning("stage2 probe failed: %s", e)
    # 빠른 말 속도 단계(speed_ladder): 숙달하면 1.25배, 한 단계에서 최근 12문항 중 10문항을 맞히면 1.6배, 2.0배(538 문장 낭독의 음절 속도 근사)
    ladder = 0
    try:
        import speed_ladder as _sl
        from database import TrialAttempt
        rows = (await db.execute(_select(TrialAttempt.speed, TrialAttempt.correct).where(
            TrialAttempt.user_id == current_user.id, TrialAttempt.stage == 2, TrialAttempt.speed >= _sl.LEVELS[0] * 0.97,
            TrialAttempt.item_type.in_(("word", "word_typed"))).order_by(TrialAttempt.id.desc()).limit(200))).all()
        ladder = _sl.unlocked(mastered, [(r[0], r[1]) for r in rows])
        ladder_levels = _sl.LEVELS[:ladder]
    except Exception as e:
        logging.getLogger("liplab").warning("speed ladder failed: %s", e)
        ladder_levels = []
    # mastery_score·natural_speed_gate: 화면이 숙달 추정값이 문턱 이상이면 적응 감속을 끈다(자연 속도 확인, docs/mastery-ewma.md 7절).
    # mastered: 숙달했으면 엔드리스에서 '빠른 말'을 연다(speed_levels = 열린 속도 단계).
    return {"words": words, "speed_levels": ladder_levels, "option_level": plan["option_level"], "target_quantile": plan["target_quantile"],
            "mastered": mastered, "mastery_score": round(float(sp.mastery_score or 0.0), 1) if sp else 0.0,
            "natural_speed_gate": _NATURAL_SPEED_GATE, "context_items": context_items, "probes": probes}


# 2단계 레슨 12문항 중 2문항은 문맥 문항이다(분석·종합 섞기, 커리큘럼 개선 계획 1-3). 한 번에 몇 개를 넉넉히 준다.
_STAGE2_CONTEXT_OFFER = 4


async def _stage2_context_items(user_id: int, db, k: int = _STAGE2_CONTEXT_OFFER) -> list:
    """2단계 레슨에 섞을 문맥 문항. 문맥 추론과 같은 문항 풀(_training_closures: 규칙 게이트 통과, 사람이 뺀 문항 제외, 보기 3개
    이상, 보기는 정답과 입모양이 비슷한 단어)에서 최근 14일 안에 문맥 추론이나 이 자리에서 푼 적 없는 것을 먼저 고른다."""
    import random
    from datetime import datetime as _dt, timedelta
    from database import TrialAttempt
    from sqlalchemy import select
    since = _dt.utcnow() - timedelta(days=14)
    seen = set((await db.execute(
        select(TrialAttempt.item_id).where(TrialAttempt.user_id == user_id,
                                           TrialAttempt.item_type.in_(("closure", "context")),
                                           TrialAttempt.item_id.isnot(None), TrialAttempt.created_at >= since))).scalars().all())
    pool = _training_closures()
    fresh = [c for c in pool if c["id"] not in seen] or list(pool)
    picked = random.sample(fresh, min(k, len(fresh)))
    return [{"id": c["id"], "display": c["display"], "answer": c["answer"], "options": list(c["options"]),
             "hint": c.get("hint")} for c in picked]


@app.post("/api/curriculum/word-answer")
async def curriculum_word_answer(data: WordAnswer, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """단어 인식 채점 → 2단계 숙달 갱신 + 오답 시 SRS 예약."""
    if not _curriculum.is_word(data.word):
        raise HTTPException(status_code=400, detail="unknown word")
    from database import StageProgress
    from sqlalchemy import select
    try:
        open2 = await _stage_open(current_user, 2, db)   # 잠긴 2단계의 답은 숙달에 넣지 않는다(직접 API 호출로 건너뛰기 방지)
        r = await db.execute(select(StageProgress).where(
            StageProgress.user_id == current_user.id, StageProgress.stage == 2))
        sp = r.scalars().first()
        if sp is None:
            sp = StageProgress(user_id=current_user.id, stage=2, status="in_progress",
                               attempts=0, correct=0, mastery_score=0.0)
            if open2:
                db.add(sp)
        # 정답 여부는 서버가 재계산(클라이언트 data.correct를 신뢰하지 않음 — 숙달·해금·평가 조작 방지).
        # chosen이 없는 구버전 호출만 data.correct로 폴백.
        typed = data.mode == "typed"
        verdict = None
        if typed:
            # 주관식: 정답 1, 입모양이 똑같은 다른 말 '입모양은 맞음' 0.5, 그 밖 0. 숙달에는 선다형 정답과 같게 센다
            import visual_difficulty as _vd
            verdict = _vd.typed_word_verdict(data.word, data.chosen or "")
            correct, success = verdict["verdict"] == "correct", verdict["credit"]
        else:
            correct = (data.chosen == data.word) if data.chosen is not None else bool(data.correct)
            success = 1.0 if correct else 0.0
        if open2:
            sp.attempts += 1
            if correct:
                sp.correct += 1
            # 최근 답에 무게, 감속 재생 정답은 0.5(docs/mastery-ewma.md 7절)
            sp.mastery_score = _ewma_mastery(sp.mastery_score, sp.attempts - 1, _speed_credit(success, data.speed))
            _settle_mastery(sp, sp.attempts >= _STAGE2_MIN_ATTEMPTS and sp.mastery_score >= _STAGE2_MASTERY)
        # 취약 입모양 반영 — 오답이면 단어의 모든 유명 viseme을 오류로 누적(단어 인식 실패 신호).
        # 예전엔 단어 학습이 개인화(WeakViseme)에 전혀 기여하지 못했다.
        vids, features = await _weak_visemes_for_text(data.word)
        read_ok = success > 0   # '입모양은 맞음'은 입모양을 바르게 읽은 것이라 약점 입모양 오류로 세지 않는다
        await _bump_weak_visemes(current_user.id, vids,
                                 vids if not read_ok else [], features, db)
        # 오답이면 '무엇을 무엇으로 읽었는지'를 자모·입모양 단위로 분석(근거 기반 피드백 + 혼동행렬 데이터)
        confusions = []
        answer = verdict["answer"] if typed else data.chosen
        if not correct and answer and answer != data.word:
            from scoring import viseme_confusions
            try:
                confusions = viseme_confusions(data.word, answer)
            except Exception:
                confusions = []   # 입력한 글은 길이가 달라 분석이 안 될 수 있다(기록만 남긴다)
        from database import TrialAttempt
        import confusion_pairs as _cp
        opts = None if typed else _trial_options(data.options, data.word, data.chosen)
        # 주관식은 유형을 따로 둔다(word_typed). 유형별 학습 곡선이 선다형 단어와 섞이지 않게(eval_metrics)
        probe = _cp.valid_probe(data.probe, data.word, opts) if opts and data.probe else None
        db.add(TrialAttempt(user_id=current_user.id, stage=2, item_type="word_typed" if typed else "word",
                            target=data.word, chosen=(data.chosen or "")[:50] if typed else data.chosen,
                            correct=correct, confusions=confusions, speed=data.speed, options=opts,
                            probe=probe, probe_kind="contrast" if probe else None, **_trial_meta(data)))
        if not correct:
            await _srs_schedule_wrong(current_user.id, "word", data.word, db)
        award = _award_xp_and_streak(current_user, 15 if correct else (8 if success > 0 else 3))   # '입모양은 맞음'은 8
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
            "confusions": confusions, "correct": correct,
            "verdict": verdict["verdict"] if typed else ("correct" if correct else "wrong")}


# ── 간격 반복 복습 (SRS) ──────────────────────────────────────────────────
_REVIEW_DUE_KINDS = ("viseme", "word", "speak", "sentence")
# 문장 복습(kind 'sentence')은 하루에 5개까지 낸다. 문장은 입모양·단어보다 한 문항이 길어(끝까지 보고 문장을 입력한다) 오늘의
# 복습이 몇 분 안에 끝나게 하려는 값이다. 한 레슨에서 여러 문장을 틀려도 다음 날 복습이 문장으로 가득 차지 않고, 넘친 문장은
# 예정일이 지난 채 다음 날로 밀린다(예정일이 이른 것부터). 오늘 이미 다시 읽은 문장 수를 빼므로 복습을 마친 뒤 목록을 다시 받아도
# 새 문장이 더 나오지 않는다.
_SENTENCE_REVIEW_DAILY = 5
_REVIEW_REF_MAX = 100   # ReviewItem.ref 길이(String(100)). 그보다 긴 문장은 큐에 넣지 않는다(시나리오 문장은 90자 이하)


def _schedules_sentence(scenario_id, sentence) -> bool:
    """이 /api/progress 답이 문장 복습 일정을 건드리는가: 일반 레슨과 문장 복습 세션만. 틀린 문장 복습·북마크 연습은 아니다."""
    sid = str(scenario_id or "")
    ok_len = 0 < len((sentence or "").strip()) <= _REVIEW_REF_MAX
    return ok_len and (sid.startswith(_SENTENCE_REVIEW_PREFIX) or not _is_review_scenario(sid))


async def _sentences_reviewed_today(user_id: int, db, today=None) -> int:
    """오늘(KST) 문장 복습 세션에서 다시 읽은 서로 다른 문장 수. 하루 상한에서 뺀다."""
    from datetime import datetime as _dtm, time as _tm, timedelta as _td
    from database import Progress
    from sqlalchemy import select, func
    start = _dtm.combine(today or _kst_today(), _tm()) - _td(hours=9)   # KST 0시의 UTC(Progress.created_at은 UTC)
    n = (await db.execute(select(func.count(func.distinct(Progress.sentence))).where(
        Progress.user_id == user_id, Progress.created_at >= start,
        Progress.scenario_id.startswith(_SENTENCE_REVIEW_PREFIX, autoescape=True)))).scalar()
    return int(n or 0)


async def _due_review_items(user_id: int, db, today=None) -> list:
    """오늘 복습에 낼 ReviewItem(예정일이 이른 순). 문장은 하루 _SENTENCE_REVIEW_DAILY개에서 오늘 이미 다시 읽은 수를 뺀 만큼만.
    예정 목록(/api/review/due)·과제 탭의 남은 복습·틀린 문장 목록의 중복 제외가 같은 목록을 쓴다."""
    from database import ReviewItem
    from sqlalchemy import select
    today = today or _kst_today()
    r = await db.execute(select(ReviewItem).where(
        ReviewItem.user_id == user_id, ReviewItem.due_date <= today.isoformat(),
        ReviewItem.kind.in_(_REVIEW_DUE_KINDS)).order_by(ReviewItem.due_date, ReviewItem.id))
    rows = r.scalars().all()
    left = None
    out = []
    for it in rows:
        if it.kind == "sentence":
            if left is None:
                left = _SENTENCE_REVIEW_DAILY - await _sentences_reviewed_today(user_id, db, today)
            if left <= 0:
                continue
            left -= 1
        out.append(it)
    return out


async def _sentence_meta(user_id: int, sentences, db) -> dict:
    """문장 → {situation, difficulty_level}: 그 문장의 가장 최근 레슨 기록(복습 세션 행은 빼되, 없으면 그것이라도)."""
    from database import Progress
    from sqlalchemy import select
    if not sentences:
        return {}
    rows = (await db.execute(select(Progress.sentence, Progress.situation, Progress.difficulty_level, Progress.scenario_id)
                             .where(Progress.user_id == user_id, Progress.sentence.in_(list(sentences)))
                             .order_by(Progress.created_at.desc()))).all()
    meta, fallback = {}, {}
    for s, situation, level, sid in rows:
        slot = fallback if _is_review_scenario(sid) else meta
        slot.setdefault(s, {"situation": situation, "difficulty_level": level})
    return {s: meta.get(s) or fallback.get(s) for s in sentences if (meta.get(s) or fallback.get(s))}


@app.get("/api/review/due")
async def review_due(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """오늘까지 복습 예정인 항목. items·count는 독화(입모양/단어/문장)만이다(간격 반복 세션 /review/scheduled가 푸는 것).
    문장(kind 'sentence', 3단계에서 합격선 아래였던 문장)은 하루 _SENTENCE_REVIEW_DAILY개까지 items 끝에 붙이고 상황·난이도를 싣는다.
    말하기 예정(kind 'speak', 말하기에서 틀린 문항)은 speak·speak_count로 따로 주고, 말하기 복습(/review/speaking)에서 푼다.
    total = 둘의 합(복습 탭·오른쪽 패널의 예정 복습 수)."""
    rows = await _due_review_items(current_user.id, db)
    meta = await _sentence_meta(current_user.id, [it.ref for it in rows if it.kind == "sentence"], db)
    read, sentences, speak = [], [], []
    for it in rows:
        # created_at = 처음 복습 큐에 들어온 시각, updated_at = 마지막으로 다시 푼 시각(목록의 상대 날짜용)
        entry = {"kind": it.kind, "ref": it.ref, "due_date": it.due_date,
                 "created_at": _iso_utc(it.created_at), "updated_at": _iso_utc(it.updated_at)}
        if it.kind == "viseme" and it.ref.isdigit():
            les = _curriculum.lesson_by_id(int(it.ref))
            if les:
                entry["name"] = les["name"]
        if it.kind == "sentence":
            m = meta.get(it.ref) or {}
            entry["situation"] = m.get("situation")
            entry["difficulty_level"] = m.get("difficulty_level")
            sentences.append(entry)
        else:
            (speak if it.kind == "speak" else read).append(entry)
    read += sentences   # 문장은 한 문항이 길어 입모양·단어 뒤에 낸다
    return {"count": len(read), "items": read, "speak_count": len(speak), "speak": speak,
            "total": len(read) + len(speak), "sentence_count": len(sentences),
            "sentence_daily_cap": _SENTENCE_REVIEW_DAILY}


@app.delete("/api/review/item")
async def review_item_delete(kind: str, ref: str, current_user=Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    """복습 예정 항목 하나를 목록에서 뺀다(복습 탭 선택 삭제). 학습 기록(시행·진행도)은 그대로 둔다."""
    from database import ReviewItem
    from sqlalchemy import delete as _delete
    res = await db.execute(_delete(ReviewItem).where(
        ReviewItem.user_id == current_user.id, ReviewItem.kind == kind, ReviewItem.ref == ref))
    await db.commit()
    return {"deleted": res.rowcount or 0}


class ReviewAnswer(BaseModel):
    kind: str = Field(..., max_length=20)
    ref: str = Field(..., max_length=100)
    correct: bool
    # 'choice'(보기를 고름)·'typed'(직접 입력)와 답하기 전에 본 재생 속도. 보기를 고른 정답과 1.0배 미만 정답은 품질 3,
    # 자연 속도에서 직접 입력한 정답만 4(srs.quality_for_answer). 보내지 않은 옛 화면은 예전처럼 정답 4다
    answer_mode: Optional[str] = Field(None, max_length=10)
    speed: Optional[float] = Field(None, ge=0.1, le=4.0)


@app.post("/api/review/answer")
async def review_answer(data: ReviewAnswer, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """복습 결과로 다음 등장일 재조정(SM-2). ease·반복에 따라 간격이 늘고, 충분히 커지면 졸업(제거)."""
    import srs
    res = await _srs_apply(current_user.id, data.kind, data.ref,
                           srs.quality_for_answer(data.correct, data.answer_mode, data.speed), db, create=False,
                           log={"source": "review", "answer_mode": _answer_mode(data.answer_mode), "speed": data.speed})
    # 공용 보상: 복습도 XP·스트릭에 기여(복습만 한 날 스트릭이 끊기던 문제 해결). 큐에 없는 항목은 XP 없음
    award = _award_xp_and_streak(current_user, (10 if data.correct else 3) if res.get("found") else 0)
    reward = {"xp_gained": award["xp_gained"], "streak_count": award["streak_count"]}
    await db.commit()
    return {"ok": True, "removed": res["removed"], "next_due": res["due_date"],
            "interval_days": res["interval_days"], **reward}


# ── 과제 탭(오늘의 과제·특별 과제) 보상: 정의·판정은 daily_tasks.py, 여기서는 기록을 모으고 XP를 준다 ──
async def _task_board(user, db) -> tuple:
    """(오늘 KST 날짜, 과제 목록). 진행도는 기존 기록(시행·회차·예정 복습)에서 서버가 계산한다."""
    import daily_tasks as _dt
    from database import TaskClaim
    from sqlalchemy import select
    today = _kst_today()
    events = await _activity_events(user.id, db, since=_dt.events_since(today))
    due_left = len(await _due_review_items(user.id, db, today))   # 예정 목록(/api/review/due)과 같은 정의(문장 하루 상한 포함)
    periods = {_dt.period_of(t, today) for t in _dt.TASKS}
    claimed = (await db.execute(select(TaskClaim.task_key, TaskClaim.period).where(
        TaskClaim.user_id == user.id, TaskClaim.period.in_(periods)))).all()
    return today, _dt.board(_dt.stats(events, today, due_left), today, [tuple(c) for c in claimed])


def _task_payload(today, rows) -> dict:
    import daily_tasks as _dt
    public = [{k: r[k] for k in ("key", "label", "total", "xp", "period", "cur", "done", "claimed")} for r in rows]
    return {"day": today.isoformat(), "week_start": _dt.week_start(today).isoformat(),
            "daily": [r for r in public if r["period"] == "day"],
            "weekly": [r for r in public if r["period"] == "week"],
            "unclaimed_xp": sum(r["xp"] for r in _dt.claimable(rows))}


@app.get("/api/tasks")
async def tasks_get(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """과제 탭·오른쪽 패널이 그리는 과제 목록(진행·보상 XP·받았는지). 읽기만 하고 XP는 주지 않는다."""
    today, rows = await _task_board(current_user, db)
    return _task_payload(today, rows)


@app.post("/api/tasks/claim", dependencies=[Depends(ratelimit.rate_limit(20, 60, "tasks-claim"))])
async def tasks_claim(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """달성했지만 아직 받지 않은 과제 보상을 모두 준다. 클라이언트는 무엇을 달성했는지 보내지 않고 서버가 기록으로 판정한다.
    과제마다 기간(하루·한 주, KST)에 한 번만 준다: task_claims의 고유 인덱스가 동시 요청의 중복 지급도 막는다.
    공용 데모 계정도 같은 규칙이다(방문자 모두 한 계정이라 그날 처음 받은 한 번만 들어간다)."""
    from database import TaskClaim
    from sqlalchemy.exc import IntegrityError
    import daily_tasks as _dt
    today, rows = await _task_board(current_user, db)
    todo = _dt.claimable(rows)
    got = []
    if todo:
        for r in todo:
            db.add(TaskClaim(user_id=current_user.id, task_key=r["key"], period=r["period_key"], xp=r["xp"]))
        _add_xp(current_user, sum(r["xp"] for r in todo))
        db.add(current_user)
        try:
            await db.commit()
            got = [{"key": r["key"], "label": r["label"], "xp": r["xp"]} for r in todo]
        except IntegrityError:
            await db.rollback()   # 다른 요청이 먼저 받았다: 이번에는 주지 않는다
        await db.refresh(current_user)
        today, rows = await _task_board(current_user, db)
    return {**_task_payload(today, rows), "claimed": got, "xp_gained": sum(g["xp"] for g in got),
            "total_xp": current_user.total_xp, "current_level": current_user.current_level}


# ── 공용 복습 유틸 — 두 기둥(독화·말하기)이 동일 구조(예정/틀림/북마크)를 쓰도록 ──
async def _sr_touch(user_id: int, kind: str, ref: str, correct: bool, db, score: float = None, max_quality: int = None,
                    answer_mode: str = None):
    """SRS 큐 유지(SM-2) — 틀리면 내일 재등장(신규면 등록), 맞으면 ease·반복에 따라 간격을 늘려
    충분히 커지면 졸업. 점수(score 0~100)가 오면 이진 대신 등급(quality)으로 반영한다.
    max_quality가 오면 성공 등급을 그 값으로 누른다(4지선다 합격은 3, srs 머리말). 커밋은 호출부에서. review/answer와 동일한 규칙.
    정답·오답이 모두 오는 경로라 예정일이 된 항목의 답은 FSRS 그림자 기록(review_logs)에 남긴다. answer_mode는 문장 답 방식이다
    (4지선다면 관측 확률에 찍기 0.25를 반영한다)."""
    quality = _review_quality(score, correct)
    if max_quality is not None and quality >= 3:
        quality = max(3, min(quality, max_quality))
    await _srs_apply(user_id, kind, ref, quality, db, create=True,
                     log={"source": kind, "answer_mode": _answer_mode(answer_mode), "speed": None})


def _review_quality(score, correct: bool) -> int:
    """복습 등급(SM-2 0~5). 점수가 있으면 점수 등급을 쓰되, 합격 여부(단계별 합격선으로 이미 판정, 말하기는 50·65점이나
    지표)와 등급의 합격(3 이상)이 어긋나지 않게 맞춘다. 예전에는 등급이 60점 고정이라 합격선 50인 단계에서 55점으로
    합격해도 복습은 실패로 잡히고, 합격선 65인 단계에서 62점으로 떨어져도 성공으로 잡혔다."""
    import srs
    if score is None:
        return srs.quality_from_correct(correct)
    quality = srs.quality_from_score(score)
    if correct and quality < 3:
        return 3
    if not correct and quality >= 3:
        return 2
    return quality


async def _due_refs(user_id: int, kinds, db):
    """오늘까지 예정인 ReviewItem ref 목록(kinds 중 하나)."""
    from database import ReviewItem
    from sqlalchemy import select
    today = _kst_today().isoformat()
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


_CLOSURE_SERVED = None


def _training_closures() -> list:
    """훈련용 문맥 문항 — 정답이나 보기에 표준검사 문항 단어가 든 항목은 뺀다(축 I, 문항 노출 방지).
    보기가 둘뿐인 항목(입모양이 같은 실단어 오답을 하나밖에 못 찾은 11개)은 반은 찍어도 맞아 문맥 훈련이 되지 않아 뺀다.
    서빙할 때도 규칙 게이트(조사 호응, 조사로 정답이 드러나는지, 힌트 속 정답, 빈칸 뒤 단어 조각)를 다시 걸고, 사람이 읽고
    뺀 문항(CLOSURE_EXCLUDED)을 거른다. 승인 파일의 문항은 예전 게이트만 거쳐 결함이 섞여 있었다(9/27 감사)."""
    global _CLOSURE_SERVED
    if _CLOSURE_SERVED is None:
        import assessment as _asmt
        import content_rules as _crules
        tw = _asmt.test_only_words()
        ex = getattr(_curriculum, "CLOSURE_EXCLUDED", {})
        _CLOSURE_SERVED = [
            c for c in _curriculum.CLOSURE_ITEMS
            if c["id"] not in ex and len(c.get("options") or []) >= 3
            and c["answer"] not in tw and not (set(c.get("options") or []) & tw)
            and _crules.check_closure(c.get("display", ""), c["answer"], c.get("options") or [],
                                      hint=c.get("hint"), compound=bool(c.get("compound")))[0]]
    return [dict(c) for c in _CLOSURE_SERVED]


@app.get("/api/curriculum/closure")
async def curriculum_closure(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """문맥 추론 항목(빈칸+비슷하게 보이는 보기). 눈으로 구별 안 되니 문맥으로 답을 고른다.

    지식추적 표적 입모양을 정답에 많이 담은 항목부터 준다(축 G). 적중 수가 같은 항목끼리는
    사용자·날짜로 정한 순서로 섞어, 날마다 같은 문항부터 시작하지 않게 한다.
    최근 14일 안에 푼 문항(2단계 레슨 속 문맥 문항 포함)은 뒤로 보낸다(오래전에 푼 것부터). 예전에는 화면이 늘 첫 문항부터 시작해 같은 날 레슨을 다시
    열면 같은 12문항이 같은 순서로 나왔고, 다시 맞힌 답이 3단계 숙달에 또 들어갔다.
    """
    import random
    import content_rules as _crules
    from datetime import datetime as _dt, timedelta
    from database import TrialAttempt
    from sqlalchemy import select, func
    rec = await _kt_recommend(current_user.id, db)
    tv = set(rec["target_visemes"])
    items = _training_closures()
    random.Random(f"{current_user.id}:{_kst_today().isoformat()}").shuffle(items)
    # 안정 정렬 — 같은 적중 수 안에서는 섞인 순서가 유지된다
    items.sort(key=lambda c: -len(set(_crules.word_visemes(c["answer"])) & tv))
    since = _dt.utcnow() - timedelta(days=14)
    rows = (await db.execute(
        select(TrialAttempt.item_id, func.max(TrialAttempt.created_at))
        .where(TrialAttempt.user_id == current_user.id, TrialAttempt.item_type.in_(("closure", "context")),
               TrialAttempt.item_id.isnot(None), TrialAttempt.created_at >= since)
        .group_by(TrialAttempt.item_id))).all()
    last_seen = {iid: ts for iid, ts in rows}
    fresh = [c for c in items if c["id"] not in last_seen]
    seen = sorted((c for c in items if c["id"] in last_seen), key=lambda c: last_seen[c["id"]])
    return {"items": fresh + seen, "target_visemes": rec["target_visemes"]}


class ClosureAnswer(TrialMeta):
    item_id: str       # 문맥 추론 항목 id(정답은 서버가 CLOSURE_ITEMS에서 찾는다)
    chosen: str        # 사용자가 고른 보기
    options: Optional[list] = None   # 보여 준 보기(보인 순서)


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
        db.add(TrialAttempt(user_id=current_user.id, stage=3, item_type="closure", item_id=item["id"],
                            target=answer, chosen=data.chosen, correct=correct, confusions=confusions,
                            options=_trial_options(data.options, answer, data.chosen), **_trial_meta(data)))
        # 3단계(문맥 추론) 숙달: 문장 연습과 같은 트랙에 성공/시도 누적. 문맥 추론 화면은 단계 잠금이 없어,
        # 3단계가 잠긴 동안의 답은 넣지 않는다(예전에는 잠긴 3단계가 미리 숙달돼 2단계를 마치자마자 4단계가 열렸다)
        if await _stage_open(current_user, 3, db):
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


class ContextAnswer(TrialMeta):
    item_id: str = Field(..., max_length=40)   # 문맥 문항 id(정답은 서버가 CLOSURE_ITEMS에서 찾는다)
    chosen: str = Field(..., max_length=50)
    options: Optional[list] = None   # 보여 준 보기(보인 순서)


@app.post("/api/curriculum/context-answer")
async def curriculum_context_answer(data: ContextAnswer, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """2단계 레슨 속 문맥 문항 채점(분석·종합 섞기, 커리큘럼 개선 계획 1-3). 이 답은 2단계 숙달에도 3단계 숙달에도 넣지 않는다.
    문맥 추론은 3단계 과제라, 2단계에서 미리 푼 답을 숙달에 넣으면 잠긴 단계의 답을 넣지 않는다는 원칙에 어긋난다.
    시행 기록(stage 2, item_type 'context')과 취약 입모양(지식추적 입력)에만 남긴다."""
    item = next((it for it in _curriculum.CLOSURE_ITEMS if it["id"] == data.item_id), None)
    if item is None:
        raise HTTPException(status_code=400, detail="unknown context item")
    answer = item["answer"]
    correct = data.chosen == answer
    from scoring import viseme_confusions
    from database import TrialAttempt
    try:
        confusions = [] if correct else viseme_confusions(answer, data.chosen)
    except Exception:
        confusions = []
    try:
        db.add(TrialAttempt(user_id=current_user.id, stage=2, item_type="context", item_id=item["id"],
                            target=answer, chosen=data.chosen, correct=correct, confusions=confusions,
                            options=_trial_options(data.options, answer, data.chosen), **_trial_meta(data)))
        vids, features = await _weak_visemes_for_text(answer)
        await _bump_weak_visemes(current_user.id, vids, vids if not correct else [], features, db)
        award = _award_xp_and_streak(current_user, 15 if correct else 3)
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise _server_error(e, "context answer failed")
    return {"correct": correct, "answer": answer, "confusions": confusions,
            "xp_gained": award["xp_gained"], "streak_count": award["streak_count"]}


def _trial_wrong(T):
    """오답 시행 조건. correct 열은 NULL을 허용하므로(default False) 예전 파이썬 'not a.correct'처럼 NULL도 오답이다."""
    from sqlalchemy import or_
    return or_(T.correct.is_(False), T.correct.is_(None))


# ── 숙달 지연 탐침(C16, mastery_probe.py) ──
# 읽기 1~3단계를 처음 숙달한 날(KST)부터 1일·7일 뒤에 처음 보는 문항 6개를 보조 없이 낸다. 일정은 숙달 날짜에서 계산하고, 회차를 처음 낼
# 때 문항을 만들어 mastery_probes에 둔다. 답은 그 표에만 남고 숙달·복습·시행 기록·XP에는 들어가지 않는다(숙달을 취소하지도 않는다).
# 한 레슨에 낼 수 있는 수는 mastery_probe.lesson_quota(레슨 문항 수, 이미 낸 다른 탐침 수)로 실제 얼굴 탐침(C8)과 상한을 함께 쓴다.

def _kst_date(ts):
    """UTC 시각 → KST 날짜(없으면 None)."""
    from datetime import timedelta as _td
    return (ts + _td(hours=9)).date() if ts else None


async def _probe_items(user_id: int, stage: int, wave: int, db) -> list:
    """한 회차의 탐침 문항(mastery_probe 머리말). 학습자가 본 낱말·문장은 뺀다. 씨앗이 고정이라 같은 회차는 같은 문항이다."""
    import random as _random
    import mastery_probe as _mp
    from sqlalchemy import select
    rng = _random.Random(_mp.seed_for(user_id, stage, wave))
    if stage == 1:
        seen = set(_curriculum.DEMO_SYLLABLE.values())
        seen |= {w[0] for l in _curriculum.VISEME_LESSONS for w in (l.get("example_words") or []) if w}
        return _mp.stage1_items(_curriculum.VISEME_LESSONS, seen, rng)
    if stage == 2:
        import assessment as _asmt
        from database import TrialAttempt
        skip = _excluded_training_words()
        pool = [w["word"] for w in _curriculum.WORD_BANK if w["word"] not in skip]
        seen = set((await db.execute(select(TrialAttempt.target).where(TrialAttempt.user_id == user_id))).scalars().all())
        seen |= set((await db.execute(select(TrialAttempt.chosen).where(TrialAttempt.user_id == user_id))).scalars().all())
        return _mp.text_items("word", pool, seen, rng,
                              lambda w, used: _asmt._confusable_options(w, [x for x in pool if x not in used], k=3,
                                                                         closeness=0.5, rng=rng))
    import sentence_options as _so
    from database import Progress
    seen = set((await db.execute(select(Progress.sentence).where(Progress.user_id == user_id))).scalars().all())
    opt_pool = await _sentence_option_pool(db)
    return _mp.text_items("sentence", _so.static_pool(), seen, rng,
                          lambda s, used: _so.pick_options(s, opt_pool, exclude=used, rng=rng))


async def _due_probe_waves(user_id: int, db, today=None) -> list:
    """오늘 낼 수 있는 (단계, 회차, 숙달일, 회차 첫날) 목록."""
    import mastery_probe as _mp
    from database import StageProgress
    from sqlalchemy import select
    today = today or _kst_today()
    rows = (await db.execute(select(StageProgress.stage, StageProgress.mastered_at).where(
        StageProgress.user_id == user_id, StageProgress.stage.in_(_mp.PROBE_STAGES),
        StageProgress.mastered_at.isnot(None)))).all()
    out = []
    for stage, at in rows:
        mon = _kst_date(at)
        for w in _mp.due_waves(mon, today):
            out.append((int(stage), w["wave"], mon, w["due_on"]))
    return sorted(out)


@app.get("/api/curriculum/mastery-probes")
async def mastery_probes_today(lesson_len: int = 12, used: int = 0, current_user=Depends(get_current_user),
                               db: AsyncSession = Depends(get_db)):
    """오늘 이 레슨에 섞을 지연 탐침(정답은 싣지 않는다). lesson_len = 레슨 문항 수, used = 이 레슨에서 이미 낸 다른 탐침 수.
    낼 회차가 처음이면 문항을 만들어 둔다. 탐침이 없으면 items가 빈 목록이다."""
    import mastery_probe as _mp
    from database import MasteryProbe
    from sqlalchemy import select, func
    from sqlalchemy.exc import IntegrityError
    waves = await _due_probe_waves(current_user.id, db)
    for stage, wave, mon, due_on in waves:
        have = (await db.execute(select(func.count(MasteryProbe.id)).where(
            MasteryProbe.user_id == current_user.id, MasteryProbe.stage == stage, MasteryProbe.wave == wave))).scalar()
        if have:
            continue
        try:
            items = await _probe_items(current_user.id, stage, wave, db)
            for seq, it in enumerate(items):
                db.add(MasteryProbe(user_id=current_user.id, stage=stage, wave=wave, seq=seq, item_kind=it["kind"],
                                    stimulus=it["stimulus"][:200], target=it["target"][:200], options=it["options"],
                                    mastered_on=mon.isoformat(), due_on=due_on, speed=1.0))
            await db.commit()
        except IntegrityError:
            await db.rollback()   # 동시에 온 다른 요청이 먼저 만들었다
        except Exception as e:   # 탐침 실패가 레슨을 막지 않게
            await db.rollback()
            print(f"[WARN] mastery probe build failed: {e}")
    quota = _mp.lesson_quota(max(1, min(int(lesson_len), 40)), max(0, int(used)))
    pending = []
    for stage, wave, _mon, _due in waves:
        pending += (await db.execute(select(MasteryProbe).where(
            MasteryProbe.user_id == current_user.id, MasteryProbe.stage == stage, MasteryProbe.wave == wave,
            MasteryProbe.correct.is_(None)).order_by(MasteryProbe.seq))).scalars().all()
    return {"items": [{"id": p.id, "stage": p.stage, "wave": p.wave, "kind": p.item_kind, "stimulus": p.stimulus,
                       "options": p.options or [], "speed": 1.0} for p in pending[:quota]],
            "quota": quota, "pending": len(pending), "cap": _mp.PROBE_SHARE_CAP}


class ProbeAnswer(BaseModel):
    id: int
    chosen: str = Field(..., max_length=200)


@app.post("/api/curriculum/mastery-probe-answer", dependencies=[Depends(ratelimit.rate_limit(60, 60, "mastery-probe"))])
async def mastery_probe_answer(data: ProbeAnswer, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """탐침 답을 기록한다. 정답 여부는 돌려주지 않는다(탐침은 정답을 공개하지 않는다). 숙달·복습·XP는 건드리지 않는다."""
    from datetime import date as _date, datetime as _dt
    from database import MasteryProbe
    from sqlalchemy import select
    p = (await db.execute(select(MasteryProbe).where(
        MasteryProbe.id == data.id, MasteryProbe.user_id == current_user.id))).scalars().first()
    if p is None:
        raise HTTPException(status_code=404, detail="probe not found")
    if p.correct is not None:
        return {"recorded": False, "already": True}
    values = [str(o.get("value")) for o in (p.options or []) if isinstance(o, dict)]
    if data.chosen not in values:
        raise HTTPException(status_code=400, detail="chosen must be one of the options")
    p.chosen = data.chosen
    p.correct = data.chosen == p.target
    p.answered_at = _dt.utcnow()
    try:
        p.delay_days = (_kst_today() - _date.fromisoformat(p.mastered_on)).days if p.mastered_on else None
    except ValueError:
        p.delay_days = None
    await db.commit()
    return {"recorded": True}


# ── 레슨별 정신적 노력 한 문항(C14, mental_effort.py) ──
_SESSION_ID_RE = r"^[A-Za-z0-9_-]{6,40}$"


class EffortReq(BaseModel):
    session_id: str = Field(..., pattern=_SESSION_ID_RE)     # 화면이 레슨마다 만든 id
    lesson_kind: Optional[str] = Field(None, max_length=16)  # viseme | word | sentence | closure | review
    stage: Optional[int] = Field(None, ge=0, le=6)
    rating: Optional[int] = None                             # 1~9, 답하지 않았으면 없음
    response: Optional[str] = Field(None, max_length=10)     # answered | skipped | left
    n_items: Optional[int] = Field(None, ge=0, le=200)
    accuracy: Optional[float] = Field(None, ge=0, le=1)
    render_log: Optional[dict] = None                        # 그 레슨의 기기·렌더링 요약(V20). 정해진 키만 남긴다


@app.post("/api/lesson/effort", dependencies=[Depends(ratelimit.rate_limit(30, 60, "lesson-effort"))])
async def lesson_effort(data: EffortReq, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """레슨 끝 정신적 노력 답(Paas 9점)을 세션마다 한 행으로 남긴다. 같은 세션이 다시 오면 answered > skipped > left 순으로 남긴다.
    적응 규칙은 없다(기록만)."""
    import mental_effort as _me
    from database import LessonEffort
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError
    rating = _me.clean_rating(data.rating) if data.rating is not None else None
    response = _me.clean_response(data.response, rating)
    kind = data.lesson_kind if data.lesson_kind in _me.LESSON_KINDS else None
    import pilot_battery as _pbat
    render = _pbat.clean_render_log(data.render_log)

    async def upsert():
        row = (await db.execute(select(LessonEffort).where(
            LessonEffort.user_id == current_user.id, LessonEffort.session_id == data.session_id))).scalars().first()
        if row is None:
            db.add(LessonEffort(user_id=current_user.id, session_id=data.session_id, lesson_kind=kind, stage=data.stage,
                                rating=rating, response=response, n_items=data.n_items, accuracy=data.accuracy,
                                render_log=render))
            return response
        if _me.merge(row.response, response):
            row.rating, row.response = rating, response
        row.lesson_kind = row.lesson_kind or kind
        row.stage = row.stage if row.stage is not None else data.stage
        if data.n_items is not None:
            row.n_items, row.accuracy = data.n_items, data.accuracy
        if render and not row.render_log:
            row.render_log = render
        return row.response

    saved = await upsert()
    try:
        await db.commit()
    except IntegrityError:   # 같은 세션의 다른 요청이 먼저 넣었다: 다시 읽어 합친다
        await db.rollback()
        saved = await upsert()
        await db.commit()
    return {"ok": True, "response": saved}

@app.get("/api/curriculum/confusion-matrix")
async def curriculum_confusion_matrix(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """시행 기록(TrialAttempt)에서 자모 혼동행렬을 집계 — 개인별 헷갈림 리포트·평가자료용.
    '무엇을 무엇으로 읽었나(target→read)'를 빈도순으로, 입모양이 같아 헷갈린 비율도 함께 낸다."""
    from database import TrialAttempt
    from sqlalchemy import select, func
    # 전체 수는 count로, confusions는 오답 행에서만 읽는다. 시행을 만드는 세 곳(입모양·단어·문맥)이 모두 정답 행에
    # confusions=[]를 넣어 결과는 같다. 예전에는 전체 행을 ORM 객체(JSON 열 포함)로 읽었다. 시행 2만 행(오답 5,849)
    # 감사 DB에서 응답 214~350 → 27~44ms(4회 실행, 각 5회 중앙값, JSON 같음). correct가 NULL인 행은 예전 'not a.correct'처럼 오답으로 센다.
    # 같은 횟수의 혼동 순서가 바뀌지 않게, 예전 쿼리가 (user_id, created_at) 인덱스로 읽던 시간순을 명시한다
    n_trials = (await db.execute(select(func.count()).select_from(TrialAttempt)
                                 .where(TrialAttempt.user_id == current_user.id))).scalar_one()
    wrong_cfs = (await db.execute(select(TrialAttempt.confusions).where(
        TrialAttempt.user_id == current_user.id, _trial_wrong(TrialAttempt))
        .order_by(TrialAttempt.created_at.asc(), TrialAttempt.id.asc()))).scalars().all()
    jamo = {}          # (target, read) -> {count, same}
    same_cnt = tot_cf = 0
    n_wrong = len(wrong_cfs)
    for confusions in wrong_cfs:
        for cf in (confusions or []):
            key = (cf.get("target"), cf.get("read"))
            e = jamo.setdefault(key, {"count": 0, "same_viseme": 0})
            e["count"] += 1
            tot_cf += 1
            if cf.get("same_viseme"):
                e["same_viseme"] += 1; same_cnt += 1
    jamo_list = sorted(
        [{"target": t, "read": rd, "count": v["count"], "same_viseme": v["same_viseme"]}
         for (t, rd), v in jamo.items()], key=lambda x: -x["count"])[:30]
    return {"trials": n_trials, "wrong": n_wrong, "confusion_count": tot_cf,
            "same_viseme_ratio": round(same_cnt / tot_cf, 3) if tot_cf else 0.0,
            "jamo_confusions": jamo_list}


@app.get("/api/eval/summary")
async def eval_summary(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """학습 효과 리포트 — 개인별 시행 기록으로 학습곡선·단계별 도달 시행수·초기 대비 최근
    향상도를 집계한다. 공모전 평가/효과성 근거용. 데이터가 적으면 각 지표를 null·빈 배열로
    돌려 프론트가 '데이터가 쌓이면 표시' 상태를 그릴 수 있게 한다.

    지표(계산은 eval_metrics, 근거는 docs/eval-metrics.md)
    - learning_curve: 선다형 시행(TrialAttempt)을 시간순 8구간으로 나눈 정확도. value는 유형(입모양·단어·문맥)
      고정효과를 뺀 값, raw는 보정 전. 단계가 바뀌며 유형이 달라지는 것만으로 곡선이 꺾이지 않게 한다.
    - baseline_vs_recent: 유형마다 처음 1/3 대 최근 1/3 정확도를 시행 수로 가중 평균(통제된 사전/사후는 아님).
      예전 전체 3등분은 학습 효과가 없어도 시뮬레이션 평균 -19%p로 나왔다. 학습곡선과 함께 1.0배로 본 보통 문항만 쓴다
      (빠른 말·감속 재생·짝 탐색 문항 제외, excluded에 건수). ci95_pp·clear는 Newcombe 95% 구간과 그 구간이 0을 벗어났는지.
    - by_item_type: 입모양·단어·문맥추론별 정확도.
    - trials_to_criterion: 단계별 숙달 도달 시행수(처음 숙달한 순간의 시도 수)와 진행 중인 단계의 진행률.
    - same_viseme_ratio: 오답 중 '입모양이 같아' 헷갈린 비율(시각 혼동성 근거).
    - sentence_trend: 문장 채점(Progress) 점수의 시간순 추이(문장 난이도 차이를 뺀 값, raw는 보정 전). 복습 행은 뺀다.
    - sentence_by_mode: 문장 점수를 답 방식(보기 고름·직접 입력·기록 없음)별로 나눈 횟수·평균·합격률(60점 이상).
    """
    from database import TrialAttempt, Progress, StageProgress
    from sqlalchemy import select
    import eval_metrics as _em

    # ── 선다형 시행 ──────────────────────────────────────────────
    # 쓰는 열(유형·정오)만 읽는다. 예전에는 시행 전체를 ORM 객체(confusions JSON 포함)로 읽었다. 시행 2만·문장 2천 행
    # 감사 DB에서 응답 268~458 → 60~111ms(각 5회 중앙값, JSON 같음). 혼동 비율은 아래에서 오답 행의 confusions만 읽는다
    rows_tr = (await db.execute(
        select(TrialAttempt.item_type, TrialAttempt.correct, TrialAttempt.speed,
               TrialAttempt.probe.is_not(None)).where(TrialAttempt.user_id == current_user.id)
        .order_by(TrialAttempt.created_at.asc(), TrialAttempt.id.asc()))).all()
    seq = [(it, bool(c)) for it, c, _, _ in rows_tr]
    n_tr = len(seq)
    n_correct = sum(1 for _, c in seq if c)

    # 학습곡선·초기 대비 최근은 1.0배로 본 보통 문항만 쓴다(docs/eval-metrics.md 7절). 빠른 말(1.25~2배)은 숙달 뒤 뒤쪽에 몰려
    # 실력이 그대로여도 최근을 깎고(모의실험: 단어 45회 중 마지막 12회가 빠른 말이면 −11.9%p, 걸러 내면 +0.1%p), 감속 정답은
    # 앞쪽에 몰려 처음을 올린다(−9.9 → +0.2%p). 짝 탐색 문항은 헷갈리는 대비 단어를 일부러 보기에 넣은 문항이다.
    natural = [(it, bool(c)) for it, c, spd, probe in rows_tr if _em.is_natural_trial(spd, probe)]
    n_probe = sum(1 for *_, probe in rows_tr if probe)
    learning_curve = _em.type_adjusted_curve(natural)
    baseline_vs_recent = _em.within_type_change(natural)   # 9시행 이상인 유형이 없으면 None
    if baseline_vs_recent is not None:
        baseline_vs_recent["excluded"] = {"speed": n_tr - len(natural) - n_probe, "probe": n_probe}

    by_item_type = []
    for it, label in (("viseme", "입모양 인지"), ("viseme_ax", "입모양 같은지 다른지"), ("word", "단어"), ("word_typed", "단어 주관식"),
                      ("context", "단어 레슨 문맥"), ("closure", "문맥 추론")):
        seg = [c for t, c in seq if t == it]
        if seg:
            by_item_type.append({"item_type": it, "label": label, "n": len(seg),
                                 "accuracy": round(sum(1 for c in seg if c) / len(seg) * 100, 1)})

    # 오답 중 같은 입모양 혼동 비율(정답 행의 confusions는 늘 비어 있어 오답 행만 읽는다)
    same_cnt = tot_cf = 0
    for confusions in (await db.execute(select(TrialAttempt.confusions).where(
            TrialAttempt.user_id == current_user.id, _trial_wrong(TrialAttempt)))).scalars().all():
        for cf in (confusions or []):
            tot_cf += 1
            if cf.get("same_viseme"):
                same_cnt += 1
    same_viseme_ratio = round(same_cnt / tot_cf, 3) if tot_cf else None

    # ── 단계별 도달 시행수 ───────────────────────────────────────
    sps = (await db.execute(
        select(StageProgress).where(StageProgress.user_id == current_user.id)
        .order_by(StageProgress.stage.asc()))).scalars().all()
    _STAGE_MIN = {1: _STAGE1_MIN_ATTEMPTS, 2: _STAGE2_MIN_ATTEMPTS, 3: _STAGE3_MIN_ATTEMPTS, 4: _STAGE4_MIN_ATTEMPTS}
    _STAGE_BAR = {1: _STAGE1_MASTERY, 2: _STAGE2_MASTERY, 3: _STAGE3_MASTERY, 4: _STAGE4_MASTERY}
    _STAGE_NAME = {1: "입모양 인지", 2: "단어", 3: "문장", 4: "대화"}
    # 한 단계에 StageProgress 행이 여러 개일 수 있어(과거 데이터·경쟁 삽입) 단계별로 합산한다.
    agg = {}  # stage -> {attempts, correct, mastery, mastered, reached}
    for sp in sps:
        if sp.stage not in _STAGE_NAME:
            continue
        a = agg.setdefault(sp.stage, {"attempts": 0, "correct": 0, "mastery": 0.0, "mastered": False, "reached": None})
        a["attempts"] += sp.attempts or 0
        a["correct"] += sp.correct or 0
        a["mastery"] = max(a["mastery"], sp.mastery_score or 0.0)
        a["mastered"] = a["mastered"] or (sp.status == "mastered")
        if sp.mastered_attempts:
            a["reached"] = min(a["reached"] or sp.mastered_attempts, sp.mastered_attempts)
    trials_to_criterion = []
    for stage in sorted(agg):
        a = agg[stage]
        trials_to_criterion.append({
            "stage": stage, "name": _STAGE_NAME[stage],
            "status": "mastered" if a["mastered"] else ("in_progress" if a["attempts"] else "locked"),
            "attempts": a["attempts"], "correct": a["correct"],
            "mastery_score": round(a["mastery"], 1),
            "mastery_threshold": _STAGE_BAR.get(stage),
            "criterion_attempts": _STAGE_MIN.get(stage),
            # 처음 숙달한 순간의 시도 수. 이 기록이 생기기 전(9/27)에 숙달한 단계는 None
            "trials_to_mastery": a["reached"] if a["mastered"] else None,
            "progress": _em.criterion_progress(a["mastered"], a["attempts"], a["mastery"],
                                               _STAGE_BAR.get(stage), _STAGE_MIN.get(stage)),
            "mastered": a["mastered"]})

    # ── 문장 채점 추이 ───────────────────────────────────────────
    # 난이도·점수 두 열만 읽는다(예전에는 문장·답·피드백 JSON까지 든 Progress 객체 전체)
    prog = [(lvl, sc, mode, sid) for lvl, sc, mode, sid in (await db.execute(
        select(Progress.difficulty_level, Progress.score, Progress.answer_mode, Progress.scenario_id)
        .where(Progress.user_id == current_user.id)
        .order_by(Progress.created_at.asc(), Progress.id.asc()))).all()]
    # 추이와 답 방식별 집계는 복습 행(틀린 문장 복습·북마크·문장 간격 반복)을 뺀다. 복습은 원문이나 정답을 본 뒤 다시 푸는 답이라
    # 점수가 높고 뒤쪽에 몰려, 실력이 그대로여도 추이가 오른다(모의실험: 뒤 2구간 − 앞 2구간 +0.1 → +8.0점). 개요의 횟수·평균은 전체
    fresh = [r for r in prog if not _is_review_scenario(r[3])]
    # 문장 난이도 차이를 뺀 점수 추이(raw는 보정 전). 경로가 쉬운 문장에서 어려운 문장으로 간다
    sentence_trend = _em.group_adjusted_curve([(lvl or 0, sc or 0.0) for lvl, sc, _, _ in fresh],
                                              lo=0.0, hi=100.0, ndigits=1)
    sentence_avg = round(sum(sc or 0 for _, sc, _, _ in prog) / len(prog), 1) if prog else None
    # 4지선다(찍어도 25%, 100 또는 0점)와 직접 입력(부분 점수)을 나눠 보인다. 추이는 두 방식이 섞인 값이다
    sentence_by_mode = _em.by_answer_mode([(mode, sc) for _, sc, mode, _ in fresh], _STAGE3_PASS)

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
        "sentence_by_mode": sentence_by_mode,
    }


class ScoreRequest(BaseModel):
    correct: str = Field(..., max_length=_TEXT_MAX)
    user_answer: str = Field(..., max_length=_TEXT_MAX)
    practice_only: bool = False   # '무슨 말인지 보기'로 문장을 본 뒤의 답: 점수만 주고 4단계 숙달·XP에는 넣지 않는다


@app.post("/api/score", dependencies=[Depends(ratelimit.rate_limit(60, 60, "llm"))])
async def score_answer(data: ScoreRequest, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """임의 문장 채점(대화 이해도 등) — 기존 음운 유사도 엔진 재사용.
    대화 실전에서 호출되므로 4단계 숙달도 함께 갱신한다."""
    try:
        r = await calculate_score(correct=data.correct, user_answer=data.user_answer, db=db, mode="visual")
        score = round(r.get("score", 0), 1)
        if data.practice_only:
            return {"score": score, "feedback": r.get("feedback", {}),
                    "phoneme_accuracy": r.get("phoneme_accuracy", {}), "xp_gained": 0,
                    "streak_count": current_user.streak_count, "practice_only": True}
        # 4단계(대화 실전) 숙달 갱신: 이해도 PASS 이상이면 성공 1회로 누적. 잠긴 단계면 넣지 않는다
        if await _stage_open(current_user, 4, db):
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
    """최근 문장 연습 정확도로 다음 난이도를 추천(적응형).
    틀린 문장 복습·북마크 연습 행은 뺀다. 예전에는 넣어서, 4단계 문장을 풀던 학습자가 복습 3문장(예전 기록 난이도 1, 100점)
    뒤에 기준 난이도가 1이 되어 2단계를 '올렸다'며 추천받았다."""
    from database import Progress
    from sqlalchemy import select
    not_review = [~Progress.scenario_id.startswith(p, autoescape=True) for p in _REVIEW_SCENARIO_PREFIXES]
    r = await db.execute(
        select(Progress.score, Progress.difficulty_level)
        .where(Progress.user_id == current_user.id, *not_review)
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
    # 2단계 풀에서 뺀 드문 말·홀로 안 쓰이는 말(9/27 감사)은 추천 단어·짝에도 내지 않는다(대시보드 '다음 학습' 카드에 보인다)
    skip = set(tw) | set(getattr(_curriculum, "STAGE2_EXCLUDED", {}))
    bank = [w for w in _curriculum.WORD_BANK if w["word"] not in skip]
    pairs = [p for p in _curriculum.MINIMAL_PAIRS if p.get("a") not in skip and p.get("b") not in skip]
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
    import math

    # 웹캠 채점 대상은 입모양 그룹 1~10뿐이다. 범위 밖 번호나 0~100 밖 점수가 WeakViseme에 쌓이면 취약 입모양 집계가 오염된다
    if not (1 <= data.viseme_id <= 10):
        raise HTTPException(status_code=400, detail="invalid viseme_id")
    if not math.isfinite(data.score) or not (0 <= data.score <= 100):
        raise HTTPException(status_code=400, detail="score는 0~100")
    passed = data.score >= 60
    r = await db.execute(select(WeakViseme).where(
        WeakViseme.user_id == current_user.id, WeakViseme.viseme_id == data.viseme_id))
    wv = r.scalars().first()
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
    파일럿에서 기호 없이 학습하는 집단(LIPLAB_PILOT_NOCUE_COHORTS)이면 빈 목록을 준다(J-12 기호 켬·끔 비교).
    """
    import cue_overlay as _cue
    if await _pilot_cues_off(current_user.id, db):
        return {"text": text, "cues": [], "legend": _cue.CUE_FEATURES, "suppressed": "pilot_cohort"}
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


# ── 파일럿 계측(§4.7) — 참여 코드·집단 등록과 운영자 가명 내보내기 ─────────────────
def _pilot_codes() -> dict:
    """LIPLAB_PILOT_CODES='코드:집단,코드:집단' → {코드: 집단}. 파일럿을 켜지 않았으면 빈 사전."""
    if os.getenv("LIPLAB_PILOT") != "1":
        return {}
    out = {}
    for part in os.getenv("LIPLAB_PILOT_CODES", "").split(","):
        code, _, cohort = part.strip().partition(":")
        if code.strip():
            out[code.strip().upper()] = (cohort.strip() or "default")[:16]
    return out


def _pseudonym(user_id: int) -> str:
    """가명 — 서버 비밀키로 만든 HMAC 앞 12자리(pilot_data.pseudonym, 파기 스크립트도 같은 값을 쓴다)."""
    import pilot_data as _pd
    return _pd.pseudonym(user_id)


def _nocue_cohorts() -> set:
    """기호(J) 없이 학습하는 파일럿 집단 — LIPLAB_PILOT_NOCUE_COHORTS='집단,집단'. 파일럿이 꺼져 있으면 없음."""
    if os.getenv("LIPLAB_PILOT") != "1":
        return set()
    return {c.strip() for c in os.getenv("LIPLAB_PILOT_NOCUE_COHORTS", "").split(",") if c.strip()}


async def _pilot_cues_off(user_id: int, db) -> bool:
    """이 사용자가 기호를 끈 파일럿 집단에 있는가(J-12 기호 켬·끔 비교). 기호 API와 파일럿 상태가 같은 판정을 쓴다."""
    off = _nocue_cohorts()
    if not off:
        return False
    from sqlalchemy import select
    from database import LearningProfile
    prof = (await db.execute(select(LearningProfile).where(LearningProfile.user_id == user_id))).scalars().first()
    return bool(prof and prof.pilot_code and prof.cohort in off)


@app.get("/api/backbone/status")
async def backbone_status(current_user=Depends(get_current_user)):
    """공용 음성 백본(A-9) 상태: 올라간 모델·장치·사용 횟수와 쓰는 축. 모델을 새로 올리지는 않는다.
    status()는 처음에 torch를 불러오므로(켜진 직후에는 예열 스레드의 불러오기를 기다린다) 스레드에서 부른다."""
    import backbone_service as _bb
    return await asyncio.to_thread(_bb.status)


def _reviewer_tag(user) -> str:
    """콘텐츠 검수 기록(approved.json의 review_log)에 남길 운영자 태그. 저장소에 들어가는 파일이라 이메일 대신
    서버 비밀키 HMAC 앞 8자리를 쓴다(같은 서버에서는 같은 운영자가 같은 태그)."""
    import hmac, hashlib
    from auth import SECRET_KEY
    email = (getattr(user, "email", "") or "").lower()
    return "op-" + hmac.new(SECRET_KEY.encode(), f"reviewer:{email}".encode(), hashlib.sha256).hexdigest()[:8]


@app.get("/api/pilot/status")
async def pilot_status(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """파일럿 진행 여부와 내 참여 상태(프로필 화면이 참여 코드 입력 줄을 보일지 정한다)."""
    enabled = bool(_pilot_codes()) and (current_user.email or "").lower() != _DEMO_EMAIL
    prof = await _get_or_create_profile(current_user.id, db)
    return {"enabled": enabled, "joined": bool(prof.pilot_code), "cohort": prof.cohort if prof.pilot_code else None,
            "cues": not await _pilot_cues_off(current_user.id, db)}


class PilotJoinReq(BaseModel):
    code: str


@app.post("/api/pilot/join", dependencies=[Depends(ratelimit.rate_limit(10, 60, "pilot"))])
async def pilot_join(req: PilotJoinReq, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """파일럿 참여 코드 입력 → 집단 배정. 파일럿이 꺼져 있거나 코드가 틀리면 거부한다. 공용 데모 계정은 참여할 수 없다."""
    codes = _pilot_codes()
    if not codes:
        raise HTTPException(status_code=403, detail="지금은 파일럿을 진행하지 않아요.")
    if (current_user.email or "").lower() == _DEMO_EMAIL:
        raise HTTPException(status_code=403, detail="공용 데모 계정은 파일럿에 참여할 수 없어요.")
    code = (req.code or "").strip().upper()
    if code not in codes:
        raise HTTPException(status_code=400, detail="참여 코드가 올바르지 않아요.")
    prof = await _get_or_create_profile(current_user.id, db)
    if prof.pilot_code != code or prof.pilot_joined_at is None:
        from datetime import datetime as _dt
        prof.pilot_joined_at = _dt.utcnow()   # 참여 뒤 활동만 따로 셀 수 있게(내보내기 since_join)
    prof.pilot_code, prof.cohort = code, codes[code]
    await db.commit()
    return {"joined": True, "cohort": prof.cohort}


def _pilot_admin_gate(user):
    if os.getenv("LIPLAB_PILOT") != "1":
        raise HTTPException(status_code=403, detail="파일럿 기능이 비활성화되어 있습니다(운영자 전용).")
    admins = {e.strip().lower() for e in os.getenv("LIPLAB_ADMIN_EMAILS", "").split(",") if e.strip()}
    email = (getattr(user, "email", "") or "").lower()
    if not email or email == _DEMO_EMAIL or email not in admins:
        raise HTTPException(status_code=403, detail="운영자 계정만 파일럿 자료를 내보낼 수 있습니다.")


PILOT_EXPORT_VERSION = 5   # 2(9/24): 참여일·참여 뒤 집계·동형 폼 문항 기록·현지 날짜 추가. 3(9/28): 사후 문항의 화자 조건(talker)
# 4(9/29): 검사 전 연습 시행 수(trials_before)·연습 뒤 사전 표시, 학습 초기화 날(learning_reset_on), 시행 단위 기록(trials=true일 때만)
# 5(10/6): P3 검사 묶음(battery: 회차·층·폼·순서·문항 응답, 개방형 답 원문 포함), 참여 순번(join_seq)·폼 순서(planned_order)·
#   B 완료 순번(b_completed_seq), 10/6 측정 표(review_logs·mastery_probes·retention_results·lesson_efforts), trial_log 확장
#   (목표·보기·고른 답·문항 id·단계 구분·화자·반응 시간·힌트·탐침 종류), progress_log(문장 원문 제외, trials=true일 때만)


@app.get("/api/pilot/export")
async def pilot_export(tz_offset_min: int = -540, trials: bool = False, current_user=Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    """파일럿 참여자 가명 자료(운영자 전용). 이메일·이름·전사문·입력 문장은 넣지 않는다.
    참여자별로 가명, 집단, 참여일, 표준검사 결과(동형 폼 A·B는 문항별 정오답 기록 포함), 단계별 시행·정답 수,
    말하기 시도·평균 점수, 학습한 날 수를 준다(최소 수집, §4.7). 계정의 모든 기록(all)과 참여 코드를 넣은 뒤의
    기록(since_join)을 따로 센다. 날짜는 tz_offset_min(한국 −540) 기준 현지 날짜다.
    trials=true면 선다형 시행 단위 기록(trial_log)과 문장 연습 기록(progress_log, 문장·답 원문 제외)을 더한다. 시각 대신 순번과 날짜만 준다.
    판 5부터 P3 검사 묶음(battery)이 들어가고, 개방형 검사 문항에 한해 타이핑 답 원문(answer_text)을 싣는다(학습 중 입력 문장은 넣지
    않는다). 동의서의 '연구진이 받는 것'(5-3)과 docs/pilot-data-spec.md 3절을 고친 뒤에만 쓴다."""
    _pilot_admin_gate(current_user)
    import analytics as _an
    from sqlalchemy import select, func, cast, Integer
    from datetime import datetime as _dt
    from database import (LearningProfile, PlacementResult, TrialAttempt, SpeakAttempt, Progress, ReviewLog, MasteryProbe,
                          RetentionResult, LessonEffort, P3TestSession, P3ClosedResponse, P3OpenResponse)
    tz = max(-840, min(720, int(tz_offset_min)))

    def day(ts):
        return _an.to_local(ts, tz).date().isoformat() if ts else None

    async def activity(uid, since):
        def w(M):
            q = M.user_id == uid
            return q if since is None else (q & (M.created_at >= since))
        by_stage = (await db.execute(select(TrialAttempt.stage, func.count(TrialAttempt.id),
                                            func.sum(cast(TrialAttempt.correct, Integer)))
                                     .where(w(TrialAttempt)).group_by(TrialAttempt.stage))).all()
        sp = (await db.execute(select(func.count(SpeakAttempt.id), func.avg(SpeakAttempt.score))
                               .where(w(SpeakAttempt)))).one()
        days = set()
        for M in (TrialAttempt, SpeakAttempt, Progress, PlacementResult):
            for (ts,) in (await db.execute(select(M.created_at).where(w(M)))).all():
                if ts:
                    days.add(day(ts))
        return {"trials_by_stage": {str(st or 0): {"n": n, "correct": int(c or 0)} for st, n, c in by_stage},
                "speak": {"n": sp[0] or 0, "mean_score": round(float(sp[1]), 2) if sp[1] is not None else None},
                "active_days": len(days)}

    async def trial_log(uid):
        # 선다형 시행 단위 기록. 시각 대신 순번과 현지 날짜만 준다(시각 단위 기록은 넣지 않는다). 주관식 답(입력 글)은 넣지 않는다:
        # word_typed의 chosen은 비운다. 목표·보기·고른 보기는 검사·학습 단어라 개인정보가 아니다(log-spec-audit.md 4.3)
        q = (await db.execute(select(TrialAttempt).where(TrialAttempt.user_id == uid)
                              .order_by(TrialAttempt.created_at.asc(), TrialAttempt.id.asc()))).scalars().all()
        return [{"seq": i + 1, "day": day(t.created_at), "stage": t.stage, "item_type": t.item_type, "correct": bool(t.correct),
                 "speed": t.speed, "probe": t.probe is not None, "target": t.target,
                 "options": t.options, "chosen": None if t.item_type == "word_typed" else t.chosen, "item_id": t.item_id,
                 "phase": t.phase, "talker": t.talker, "rt_from_onset_ms": t.rt_from_onset_ms, "hint_used": t.hint_used,
                 "probe_kind": t.probe_kind or ("contrast" if t.probe is not None else None)} for i, t in enumerate(q)]

    async def progress_log(uid):
        # 문장 연습 기록. 문장·답 원문은 넣지 않는다(학습 중 입력, 명세 3절)
        q = (await db.execute(select(Progress).where(Progress.user_id == uid)
                              .order_by(Progress.created_at.asc(), Progress.id.asc()))).scalars().all()
        return [{"seq": i + 1, "day": day(r.created_at), "difficulty_level": r.difficulty_level, "answer_mode": r.answer_mode,
                 "speed": r.speed, "score": r.score, "hint_level": r.hint_level, "talker": r.talker,
                 "rt_from_onset_ms": r.rt_from_onset_ms, "n_options": len(r.options) if r.options else None}
                for i, r in enumerate(q)]

    async def measurement(uid):
        # 10/6 측정 표(C11·C16·C7·C14). 시각 대신 날짜만 준다
        rl = (await db.execute(select(ReviewLog).where(ReviewLog.user_id == uid).order_by(ReviewLog.id))).scalars().all()
        mp = (await db.execute(select(MasteryProbe).where(MasteryProbe.user_id == uid).order_by(MasteryProbe.id))).scalars().all()
        rr = (await db.execute(select(RetentionResult).where(RetentionResult.user_id == uid)
                               .order_by(RetentionResult.id))).scalars().all()
        le = (await db.execute(select(LessonEffort).where(LessonEffort.user_id == uid).order_by(LessonEffort.id))).scalars().all()
        return {
            "review_logs": [{"kind": r.kind, "ref": r.ref, "source": r.source, "reviewed_on": r.reviewed_on,
                             "elapsed_days": r.elapsed_days, "quality": r.quality, "grade": r.grade, "passed": r.passed,
                             "answer_mode": r.answer_mode, "speed": r.speed, "guess": r.guess, "r_fsrs": r.r_fsrs,
                             "p_fsrs": r.p_fsrs, "p_sm2": r.p_sm2, "sm2_interval": r.sm2_interval,
                             "fsrs_stability": r.fsrs_stability, "fsrs_difficulty": r.fsrs_difficulty} for r in rl],
            "mastery_probes": [{"stage": r.stage, "wave": r.wave, "seq": r.seq, "item_kind": r.item_kind, "target": r.target,
                                "options": [o.get("value") if isinstance(o, dict) else o for o in (r.options or [])],
                                "chosen": r.chosen, "correct": r.correct, "mastered_on": r.mastered_on, "due_on": r.due_on,
                                "answered_on": day(r.answered_at), "delay_days": r.delay_days, "speed": r.speed} for r in mp],
            "retention_results": [{"form": r.form, "form_version": r.form_version, "days_after_post": r.days_after_post,
                                   "total": r.total, "correct": r.correct, "accuracy": r.accuracy, "level": r.level,
                                   "date": day(r.created_at),
                                   "items": [{"id": i.get("id"), "correct": bool(i.get("correct")), "chosen": i.get("chosen"),
                                              **({"talker": i["talker"]} if i.get("talker") else {})}
                                             for i in (r.item_log or []) if isinstance(i, dict)]} for r in rr],
            "lesson_efforts": [{"day": day(r.created_at), "lesson_kind": r.lesson_kind, "stage": r.stage, "rating": r.rating,
                                "response": r.response, "n_items": r.n_items, "accuracy": r.accuracy,
                                "render_log": r.render_log} for r in le],
        }

    async def battery(uid):
        # P3 검사 묶음. 회차 × 층마다 한 행, 끝내지 못한 층도 싣는다(ITT). 개방형 답 원문은 검사 문항이라 싣는다
        ss = (await db.execute(select(P3TestSession).where(P3TestSession.user_id == uid)
                               .order_by(P3TestSession.started_at, P3TestSession.id))).scalars().all()
        cl = (await db.execute(select(P3ClosedResponse).where(P3ClosedResponse.user_id == uid)
                               .order_by(P3ClosedResponse.id))).scalars().all()
        op = (await db.execute(select(P3OpenResponse).where(P3OpenResponse.user_id == uid)
                               .order_by(P3OpenResponse.id))).scalars().all()
        out = []
        for s_ in ss:
            closed = [{"seq": r.seq, "item_id": r.item_id, "talker": r.talker, "modality": r.modality, "target": r.target,
                       "options": r.options, "chosen": r.chosen, "correct": r.correct,
                       "target_consonants": r.target_consonants, "chosen_consonants": r.chosen_consonants,
                       "consonant_hits": r.consonant_hits, "rt_ms": r.rt_ms, "rt_from_onset_ms": r.rt_from_onset_ms,
                       "plays": r.plays, "speed": r.speed} for r in cl if r.session_id == s_.id]
            opened = [{"seq": r.seq, "item_id": r.item_id, "talker": r.talker, "modality": r.modality, "target": r.target,
                       "answer_text": r.answer_text, "app_score": r.app_score, "auto_phoneme_acc": r.auto_phoneme_acc,
                       "auto_word_acc": r.auto_word_acc, "scorer_version": r.scorer_version, "rt_ms": r.rt_ms,
                       "rt_from_onset_ms": r.rt_from_onset_ms, "plays": r.plays, "speed": r.speed, "snr_db": r.snr_db,
                       "noise_type": r.noise_type, "criterion_met": r.criterion_met} for r in op if r.session_id == s_.id]
            out.append({"session_label": s_.session_label, "layer": s_.layer, "form": s_.form, "form_version": s_.form_version,
                        "manifest_sha": s_.manifest_sha, "planned_order": s_.planned_order, "modality": s_.modality,
                        "talker": s_.talker, "started_on": day(s_.started_at), "completed_on": day(s_.completed_at),
                        "completed": bool(s_.completed), "n_items": s_.n_items, "n_ready": s_.n_ready, "missing": s_.missing,
                        "snr_calibrated_db": s_.snr_calibrated_db, "headphone_check": s_.headphone_check,
                        "volume_fixed": s_.volume_fixed, "render_log": s_.render_log,
                        "closed": closed if s_.layer in ("word", "nonsense") else None,
                        "open": opened if s_.layer in ("sentence", "av", "snr") else None})
        return out

    # B 완료 순번(순차 멈춤 규칙은 이 순서로 5명씩 묶는다). 문장 층(주결과)을 끝낸 시각 순, 없으면 B의 다른 층
    b_done = (await db.execute(select(P3TestSession.user_id, P3TestSession.layer, P3TestSession.completed_at)
                               .where(P3TestSession.session_label == "B", P3TestSession.completed.is_(True)))).all()
    b_first = {}
    for u, lay, ts in b_done:
        k = (0 if lay == "sentence" else 1, ts)
        if ts and (u not in b_first or k < b_first[u]):
            b_first[u] = k
    b_seq = {u: i + 1 for i, (u, _) in enumerate(sorted(b_first.items(), key=lambda kv: kv[1]))}

    import assessment as _asmt
    profs = (await db.execute(select(LearningProfile).where(LearningProfile.pilot_code.is_not(None)))).scalars().all()
    rows = []
    for pf in profs:
        uid = pf.user_id
        tests = (await db.execute(select(PlacementResult).where(PlacementResult.user_id == uid)
                                  .order_by(PlacementResult.created_at))).scalars().all()
        everything = await activity(uid, None)
        rows.append({
            "pid": _pseudonym(uid), "cohort": pf.cohort, "track": pf.track,
            "joined_on": day(pf.pilot_joined_at),
            # 마지막 학습 초기화 날. 초기화하면 시행 기록이 지워져 그 전 학습량이 집계에서 빠진다(검사의 trials_before는 남는다)
            "learning_reset_on": day(getattr(pf, "learning_reset_at", None)),
            # P3 검사 참여 순번·폼 순서(pilot_battery.assign_order)와 B 완료 순번. 검사를 시작하지 않았으면 None
            "join_seq": pf.pilot_seq, "planned_order": pf.pilot_order, "b_completed_seq": b_seq.get(uid),
            "tests": [{"form": t.form, "form_version": t.form_version, "accuracy": round(t.accuracy or 0, 4),
                       "level": t.level, "date": day(t.created_at),
                       # 채점 때까지 한 독화 연습 시행 수(선다형 + 문장). 9/29 이전 검사는 None
                       "trials_before": getattr(t, "trials_before", None),
                       "after_training": _asmt.pretest_after_training(getattr(t, "trials_before", None)),
                       "after_join": bool(pf.pilot_joined_at and t.created_at and t.created_at >= pf.pilot_joined_at),
                       # 동형 폼만 문항 기록을 싣는다(신뢰도 KR-20·문항 분석용). 고른 보기는 검사 단어라 개인정보가 아니다.
                       # 사후 검사 문항에는 화자 조건(talker: default·h1·h2, 계획 2-3)을 싣는다. 조건이 없는 검사는 예전 형식 그대로.
                       "items": ([{"id": i.get("id"), "correct": bool(i.get("correct")), "chosen": i.get("chosen"),
                                   **({"talker": i["talker"]} if i.get("talker") else {})}
                                  for i in (t.item_log or []) if isinstance(i, dict)] if t.form in ("A", "B") else None)}
                      for t in tests],
            # 예전 형식과 같은 자리(계정 전체)
            **everything,
            "since_join": (await activity(uid, pf.pilot_joined_at)) if pf.pilot_joined_at else None,
            **({"trial_log": await trial_log(uid), "progress_log": await progress_log(uid)} if trials else {}),
            "battery": await battery(uid),
            **(await measurement(uid)),
        })
    return {"exported_at": _dt.utcnow().replace(microsecond=0).isoformat() + "Z", "version": PILOT_EXPORT_VERSION,
            "tz_offset_min": tz, "n": len(rows), "participants": rows,
            "pretest_trials_flag": _asmt.PRETEST_TRIALS_FLAG,
            "note": "가명(pid)은 가명 비밀키(LIPLAB_PILOT_SECRET) HMAC이라 운영자도 자료만으로는 계정을 알 수 없다. "
                    "참여 코드를 넣기 전 기록은 all 집계에만 들어가고 since_join에는 빠진다."}


class PilotLookupReq(BaseModel):
    email: str


@app.post("/api/pilot/lookup", dependencies=[Depends(ratelimit.rate_limit(20, 60, "pilot-lookup"))])
async def pilot_lookup(req: PilotLookupReq, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """참여자 계정 이메일 → 가명(운영자 전용). 철회·파기 요청을 받았을 때 내보낸 사본에서 그 사람의 행을 찾는 데 쓴다.
    이메일은 주소줄에 남지 않도록 본문으로 받는다."""
    _pilot_admin_gate(current_user)
    from sqlalchemy import select, func
    from database import User, LearningProfile
    email = (req.email or "").strip().lower()
    user = (await db.execute(select(User).where(func.lower(User.email) == email))).scalars().first() if email else None
    if not user:
        raise HTTPException(status_code=404, detail="그 이메일의 계정이 없습니다.")
    prof = (await db.execute(select(LearningProfile).where(LearningProfile.user_id == user.id))).scalars().first()
    return {"pid": _pseudonym(user.id), "joined": bool(prof and prof.pilot_code),
            "cohort": prof.cohort if prof and prof.pilot_code else None}


# ── 청인 예비 파일럿(P3) 검사 묶음(pilot_battery.py, docs/pilot/battery.md) ─────────────────
# 파일럿 참여자(LIPLAB_PILOT=1이고 참여 코드를 넣은 계정)만 쓴다. 문항·배정은 목록 파일(data/pilot/battery_manifest.json,
# LIPLAB_PILOT_MANIFEST로 바꿀 수 있음)에서 오고, 영상·음성은 LIPLAB_PILOT_MEDIA_DIR 아래에서 읽는다. 파일이 없는 문항은 '준비 전'으로
# 내지도 세지도 않는다. 검사 중에는 정답을 알려 주지 않는다(채점은 저장만).
_BATTERY_CACHE = {"key": None, "manifest": None, "errors": None, "sha": None}


def _battery_manifest():
    """(목록, 점검 문제 목록, 해시). 파일이 바뀌면 다시 읽는다."""
    import pilot_battery as _pb
    path = os.getenv("LIPLAB_PILOT_MANIFEST") or _pb.MANIFEST_PATH
    try:
        key = (path, os.path.getmtime(path))
    except OSError:
        raise HTTPException(status_code=503, detail="검사 목록 파일이 없습니다.")
    if _BATTERY_CACHE["key"] != key:
        m = _pb.load_manifest(path)
        _BATTERY_CACHE.update(key=key, manifest=m, errors=_pb.validate_manifest(m), sha=_pb.manifest_sha(m))
    return _BATTERY_CACHE["manifest"], _BATTERY_CACHE["errors"], _BATTERY_CACHE["sha"]


async def _battery_gate(user, db):
    """P3 검사는 파일럿 참여자만 본다. 일반 학습자와 공용 데모 계정에는 기능 자체가 없다(403)."""
    if os.getenv("LIPLAB_PILOT") != "1":
        raise HTTPException(status_code=403, detail="지금은 파일럿을 진행하지 않아요.")
    if (user.email or "").lower() == _DEMO_EMAIL:
        raise HTTPException(status_code=403, detail="공용 데모 계정은 파일럿 검사를 볼 수 없어요.")
    prof = await _get_or_create_profile(user.id, db)
    if not prof.pilot_code:
        raise HTTPException(status_code=403, detail="파일럿 참여자만 볼 수 있어요.")
    return prof


async def _battery_assign(prof, db, manifest) -> tuple:
    """검사 참여 순번과 폼 순서. 처음 검사 상태를 볼 때 순번을 매기고(지금까지 가장 큰 순번 + 1) 순서를 정해 프로필에 둔다."""
    import pilot_battery as _pb
    from database import LearningProfile
    from sqlalchemy import select, func
    if prof.pilot_seq is None:
        mx = (await db.execute(select(func.max(LearningProfile.pilot_seq)))).scalar() or 0
        prof.pilot_seq = int(mx) + 1
        prof.pilot_order = _pb.assign_order(prof.pilot_seq, manifest.get("orders") or _pb.ORDERS)
        await db.commit()
    return prof.pilot_seq, prof.pilot_order


def _battery_items(manifest: dict, label: str, layer: str, seq: int, order: str, snr_db=None) -> list:
    """이 참여자·회차·층에 낼 문항(제시 순서). 각 문항: 목록 원본(item), 순번(position), 화자, 매체 상대 경로, 준비 여부와 까닭."""
    import pilot_battery as _pb
    L = (manifest.get("layers") or {}).get(layer) or {}
    talkers = (manifest.get("talkers") or {}).get(layer) or []
    modality = L.get("modality") or ("audio" if layer == "snr" else "real")
    if layer == "snr":
        base = list(L.get("items") or [])
    else:
        base = list((L.get("items") or {}).get(_pb.form_for(order, label)) or [])
    if layer == "av":
        ordered = _pb.av_blocks(base, seq)
    else:
        ordered = _pb.presentation_order(base, seq, label, layer)
    noise_ok = True
    if layer in ("av", "snr"):
        noise_ok = _pb.media_exists(_pb.noise_relpath(manifest, L.get("noise") or "babble"))
    out = []
    for pos, it in enumerate(ordered, start=1):
        if layer == "word":
            talker = _pb.word_talker(seq, label, pos - 1, talkers) if talkers else None
        elif layer == "nonsense" or (layer == "sentence" and modality == "avatar"):
            talker = "avatar"
        else:
            talker = _pb.sentence_talker(seq, talkers) if talkers else None
        rel = _pb.media_relpath(L, it, talker) if talker and talker != "avatar" else None
        media_ok = _pb.media_exists(rel) if rel else False
        ready, why = _pb.item_ready(layer, modality, it, media_ok, noise_ok, snr_db)
        out.append({"item": it, "position": pos, "talker": talker, "rel": rel, "ready": ready, "reason": why,
                    "modality": it.get("block") or modality})
    return out


def _battery_counts(items: list) -> dict:
    missing = {}
    for x in items:
        if not x["ready"]:
            missing[x["reason"]] = missing.get(x["reason"], 0) + 1
    return {"n_items": len(items), "n_ready": sum(1 for x in items if x["ready"]), "missing": missing}


async def _battery_rows(user_id: int, db) -> dict:
    from database import P3TestSession
    from sqlalchemy import select
    rows = (await db.execute(select(P3TestSession).where(P3TestSession.user_id == user_id))).scalars().all()
    return {(r.session_label, r.layer): r for r in rows}


def _battery_snr(rows: dict):
    r = rows.get(("A1", "snr"))
    return r.snr_calibrated_db if r is not None and r.completed else None


def _battery_label_done(manifest, rows, label, seq, order) -> bool:
    """회차를 마쳤는가: 그 회차의 층마다 끝냈거나, 낼 수 있는 문항이 하나도 없던 층이다."""
    snr = _battery_snr(rows)
    for layer in (manifest.get("layers_by_label") or {}).get(label, []):
        r = rows.get((label, layer))
        if r is not None and r.completed:
            continue
        if _battery_counts(_battery_items(manifest, label, layer, seq, order, snr))["n_ready"] == 0:
            continue
        return False
    return True


async def _battery_snr_state(session_id: int, manifest: dict, db) -> dict:
    """SNR 계단의 지금 상태(저장된 시행 판정을 시간순으로 다시 돌린다)."""
    import pilot_battery as _pb
    from database import P3OpenResponse
    from sqlalchemy import select
    outs = (await db.execute(select(P3OpenResponse.criterion_met).where(P3OpenResponse.session_id == session_id)
                             .order_by(P3OpenResponse.id))).scalars().all()
    return _pb.staircase_run(manifest["layers"]["snr"]["staircase"], [bool(o) for o in outs])


@app.get("/api/pilot/battery/status")
async def pilot_battery_status(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """내 P3 검사 순서·회차별 층 상태. 상태: done | in_progress | todo. available은 앞 회차를 마쳤는지."""
    import pilot_battery as _pb
    prof = await _battery_gate(current_user, db)
    m, errs, sha = _battery_manifest()
    seq, order = await _battery_assign(prof, db, m)
    rows = await _battery_rows(current_user.id, db)
    snr = _battery_snr(rows)
    labels, next_label = [], None
    for label in _pb.LABELS:
        prev = _pb.LABEL_PREV[label]
        available = prev is None or _battery_label_done(m, rows, prev, seq, order)
        layers = []
        for layer in (m.get("layers_by_label") or {}).get(label, []):
            r = rows.get((label, layer))
            cnt = _battery_counts(_battery_items(m, label, layer, seq, order, snr))
            layers.append({"layer": layer, "title": ((m.get("layers") or {}).get(layer) or {}).get("title") or layer,
                           "state": "done" if r is not None and r.completed else ("in_progress" if r is not None else "todo"),
                           **cnt})
        done = _battery_label_done(m, rows, label, seq, order)
        if next_label is None and available and not done:
            next_label = label
        labels.append({"label": label, "form": _pb.form_for(order, label), "available": available, "done": done,
                       "layers": layers})
    return {"seq": seq, "order": order, "manifest": {"version": m.get("version"), "status": m.get("status"), "sha": sha,
                                                      "errors": errs[:20], "n_errors": len(errs)},
            "snr_calibrated_db": snr, "labels": labels, "next_label": next_label,
            "playback": m.get("playback")}


class BatteryStartReq(BaseModel):
    label: str = Field(..., max_length=4)
    layer: str = Field(..., max_length=12)


@app.post("/api/pilot/battery/start", dependencies=[Depends(ratelimit.rate_limit(30, 60, "pilot-battery"))])
async def pilot_battery_start(req: BatteryStartReq, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """층 하나를 시작(또는 이어서)한다. 회차 행을 만들고 낼 문항을 준다. 정답 글은 주지 않는다: 아바타 문항은 서버가 만든 입모양
    프레임만, 영상 문항은 매체 주소만 준다."""
    import pilot_battery as _pb
    from database import P3TestSession, P3ClosedResponse, P3OpenResponse
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError
    prof = await _battery_gate(current_user, db)
    m, errs, sha = _battery_manifest()
    if errs:
        raise HTTPException(status_code=503, detail="검사 목록 파일에 문제가 있어 시작할 수 없습니다: " + "; ".join(errs[:3]))
    label, layer = req.label, req.layer
    if label not in _pb.LABELS or layer not in (m.get("layers_by_label") or {}).get(label, []):
        raise HTTPException(status_code=400, detail="이 회차에 없는 검사입니다.")
    seq, order = await _battery_assign(prof, db, m)
    rows = await _battery_rows(current_user.id, db)
    prev = _pb.LABEL_PREV[label]
    if prev and not _battery_label_done(m, rows, prev, seq, order):
        raise HTTPException(status_code=409, detail=f"{prev} 회차를 먼저 마쳐 주세요.")
    snr = _battery_snr(rows)
    L = m["layers"][layer]
    row = rows.get((label, layer))
    if row is None:
        talkers = (m.get("talkers") or {}).get(layer) or []
        row = P3TestSession(user_id=current_user.id, session_label=label, layer=layer, form=_pb.form_for(order, label),
                            form_version=str(m.get("version"))[:32], manifest_sha=sha, planned_order=order, join_seq=seq,
                            modality="mixed" if layer == "av" else (L.get("modality") or ("audio" if layer == "snr" else "real")),
                            talker=(_pb.sentence_talker(seq, talkers) if layer in ("sentence", "av", "snr") and talkers
                                    and L.get("modality") != "avatar" else None),
                            snr_calibrated_db=snr if layer == "av" else None)
        db.add(row)
        try:
            await db.commit()
        except IntegrityError:   # 같은 층을 두 번 눌러 동시에 만들었다: 먼저 만든 행을 쓴다
            await db.rollback()
            row = (await db.execute(select(P3TestSession).where(
                P3TestSession.user_id == current_user.id, P3TestSession.session_label == label,
                P3TestSession.layer == layer))).scalars().first()
    if row.completed:
        raise HTTPException(status_code=409, detail="이미 마친 검사입니다.")
    items = _battery_items(m, label, layer, seq, order, row.snr_calibrated_db if layer == "av" else snr)
    R = P3ClosedResponse if layer in _pb.CLOSED_LAYERS else P3OpenResponse
    answered = set((await db.execute(select(R.item_id).where(R.session_id == row.id))).scalars().all())
    out = []
    for x in items:
        it = x["item"]
        o = {"id": it["id"], "position": x["position"], "ready": x["ready"], "reason": x["reason"],
             "answered": it["id"] in answered, "modality": x["modality"]}
        if x["ready"]:
            if layer == "word":
                o["options"] = it.get("options")
            if layer == "nonsense":
                o["vowels"] = it.get("vowels")
            if layer in ("av", "snr"):
                o["speech_rms_dbfs"] = it.get("speech_rms_dbfs")
            if x["talker"] == "avatar":
                o["frames"] = await text_to_visemes(it["text"])
            else:
                o["media"] = f"/pilot/battery/media/{row.id}/{it['id']}"
        out.append(o)
    payload = {"session_id": row.id, "label": label, "layer": layer, "form": row.form, "modality": row.modality,
               "title": L.get("title"), "response": L.get("response"), "playback": m.get("playback"),
               "items": out, **_battery_counts(items)}
    if layer == "nonsense":
        payload["consonant_sets"] = L.get("consonant_sets")
    if layer in ("av", "snr"):
        payload["noise"] = f"/pilot/battery/noise/{row.id}"
        payload["snr_db"] = row.snr_calibrated_db
    if layer == "snr":
        payload["staircase"] = await _battery_snr_state(row.id, m, db)
    return payload


async def _battery_session(session_id: int, user_id: int, db):
    from database import P3TestSession
    from sqlalchemy import select
    row = (await db.execute(select(P3TestSession).where(P3TestSession.id == session_id,
                                                        P3TestSession.user_id == user_id))).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="검사 회차가 없습니다.")
    return row


def _battery_media_type(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return {".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime", ".wav": "audio/wav",
            ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".ogg": "audio/ogg"}.get(ext, "application/octet-stream")


@app.get("/api/pilot/battery/media/{session_id}/{item_id}")
async def pilot_battery_media(session_id: int, item_id: str, current_user=Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    """검사 문항의 영상·음성 파일(그 회차를 가진 참여자만). 파일은 저장소가 아니라 매체 폴더에 있다."""
    import pilot_battery as _pb
    from fastapi.responses import FileResponse
    prof = await _battery_gate(current_user, db)
    m, _, _ = _battery_manifest()
    row = await _battery_session(session_id, current_user.id, db)
    items = _battery_items(m, row.session_label, row.layer, prof.pilot_seq or row.join_seq or 1, row.planned_order,
                           row.snr_calibrated_db)
    x = next((x for x in items if x["item"].get("id") == item_id), None)
    path = _pb.media_path(x["rel"]) if x and x["rel"] else None
    if not path or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="영상 준비 전입니다.")
    return FileResponse(path, media_type=_battery_media_type(path), headers={"Cache-Control": "private, max-age=3600"})


@app.get("/api/pilot/battery/noise/{session_id}")
async def pilot_battery_noise(session_id: int, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """소음 층의 잡담 잡음 파일."""
    import pilot_battery as _pb
    from fastapi.responses import FileResponse
    await _battery_gate(current_user, db)
    m, _, _ = _battery_manifest()
    row = await _battery_session(session_id, current_user.id, db)
    if row.layer not in ("av", "snr"):
        raise HTTPException(status_code=404, detail="잡음이 없는 검사입니다.")
    path = _pb.media_path(_pb.noise_relpath(m, (m["layers"][row.layer].get("noise") or "babble")))
    if not path or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="잡음 파일 준비 전입니다.")
    return FileResponse(path, media_type=_battery_media_type(path), headers={"Cache-Control": "private, max-age=3600"})


class BatteryAnswerReq(BaseModel):
    session_id: int
    item_id: str = Field(..., max_length=40)
    chosen: Optional[str] = Field(None, max_length=100)                     # 낱말 4지선다에서 고른 보기
    chosen_consonants: Optional[List[Optional[str]]] = Field(None, max_length=3)   # 무의미 낱말: 자리별로 고른 자음
    answer_text: Optional[str] = Field(None, max_length=_TEXT_MAX)          # 타이핑 답 원문
    rt_ms: Optional[int] = Field(None, ge=0, le=3_600_000)                  # 첫 재생이 끝난 때부터 답 확정까지
    rt_from_onset_ms: Optional[int] = Field(None, ge=0, le=3_600_000)       # 첫 재생이 시작한 때부터 답 확정까지
    plays: Optional[int] = Field(None, ge=0, le=20)


@app.post("/api/pilot/battery/answer", dependencies=[Depends(ratelimit.rate_limit(240, 60, "pilot-battery-answer"))])
async def pilot_battery_answer(req: BatteryAnswerReq, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """문항 하나의 답을 저장한다. 정오는 알려 주지 않는다(검사). SNR 층만 다음 시행의 SNR과 끝났는지를 돌려준다.
    준비되지 않은 문항은 받지 않고(세지 않음), 같은 문항의 두 번째 답은 무시한다."""
    import pilot_battery as _pb
    from database import P3ClosedResponse, P3OpenResponse
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError
    prof = await _battery_gate(current_user, db)
    m, _, _ = _battery_manifest()
    row = await _battery_session(req.session_id, current_user.id, db)
    if row.completed:
        raise HTTPException(status_code=409, detail="이미 마친 검사입니다.")
    layer = row.layer
    items = _battery_items(m, row.session_label, layer, prof.pilot_seq or row.join_seq or 1, row.planned_order,
                           row.snr_calibrated_db)
    x = next((x for x in items if x["item"].get("id") == req.item_id), None)
    if x is None:
        raise HTTPException(status_code=400, detail="이 검사에 없는 문항입니다.")
    if not x["ready"]:
        raise HTTPException(status_code=409, detail="준비되지 않은 문항은 세지 않습니다.")
    it = x["item"]
    speed = float((m.get("playback") or {}).get("speed") or 1.0)
    common = dict(user_id=current_user.id, session_id=row.id, layer=layer, item_id=it["id"], seq=x["position"],
                  talker=x["talker"], modality=x["modality"], rt_ms=req.rt_ms, rt_from_onset_ms=req.rt_from_onset_ms,
                  plays=req.plays, speed=speed)
    R = P3ClosedResponse if layer in _pb.CLOSED_LAYERS else P3OpenResponse
    if (await db.execute(select(R.id).where(R.session_id == row.id, R.item_id == it["id"]))).first():
        return {"recorded": False, "duplicate": True}
    extra = {}
    if layer == "word":
        if req.chosen not in (it.get("options") or []):
            raise HTTPException(status_code=400, detail="보기에 없는 답입니다.")
        db.add(P3ClosedResponse(**common, target=it["word"], options=it.get("options"), chosen=req.chosen,
                                correct=_pb.score_choice(it, req.chosen)))
    elif layer == "nonsense":
        sets = m["layers"]["nonsense"].get("consonant_sets") or {}
        ch = list(req.chosen_consonants or [])[:3]
        ch += [None] * (3 - len(ch))
        if any(c is not None and c not in (sets.get(pos) or []) for c, pos in zip(ch, ("C1", "C2", "C3"))):
            raise HTTPException(status_code=400, detail="자음 목록에 없는 답입니다.")
        sc = _pb.score_nonsense(it, ch)
        db.add(P3ClosedResponse(**common, target=it["text"], options=sets, chosen=",".join(c or "" for c in ch),
                                correct=sc["correct"], target_consonants=sc["target"], chosen_consonants=sc["chosen"],
                                consonant_hits=sc["hits"]))
    else:
        answer = _pb.clean_answer(req.answer_text)
        target = it["text"]
        app_score, app_acc = 0.0, None
        if answer:
            try:
                sr = await calculate_score(correct=target, user_answer=answer, db=db, mode="visual")
                app_score, app_acc = float(sr.get("score") or 0.0), sr.get("phoneme_accuracy")
            except Exception as e:   # 앱 점수 실패는 원문 저장을 막지 않는다(원문으로 다시 채점할 수 있다)
                print(f"[WARN] battery app score failed: {e}")
                app_score = None
        strict = _pb.strict_score(target, answer)
        sf = _pb.strict_fields(strict)
        snr_db, crit = None, None
        if layer == "av":
            snr_db = row.snr_calibrated_db
        if layer == "snr":
            st = await _battery_snr_state(row.id, m, db)
            if st["done"]:
                raise HTTPException(status_code=409, detail="SNR 맞추기가 이미 끝났습니다. 마침을 눌러 주세요.")
            snr_db = st["next_db"]
            crit = _pb.word_proportion(target, answer) >= float(m["layers"]["snr"]["staircase"].get("criterion", 0.5))
        db.add(P3OpenResponse(**common, target=target, answer_text=answer, app_score=app_score, app_phoneme_accuracy=app_acc,
                              auto_phoneme_acc=sf["auto_phoneme_acc"], auto_word_acc=sf["auto_word_acc"], strict_result=strict,
                              scorer_version=("app-visual" + (f"+strict:{sf['strict_version']}" if sf["strict_version"]
                                                              else ("+strict" if strict else "")))[:40],
                              snr_db=snr_db, noise_type="babble" if layer in ("av", "snr") else None, criterion_met=crit))
    try:
        await db.commit()
    except IntegrityError:   # 같은 문항의 답이 동시에 두 번 왔다
        await db.rollback()
        return {"recorded": False, "duplicate": True}
    if layer == "snr":
        st = await _battery_snr_state(row.id, m, db)
        extra = {"staircase": {k: st[k] for k in ("next_db", "done", "reversals", "n_trials", "estimate_db", "estimate_kind")}}
    return {"recorded": True, **extra}


class BatteryFinishReq(BaseModel):
    session_id: int
    render_log: Optional[dict] = None
    headphone_check: Optional[bool] = None
    volume_fixed: Optional[bool] = None


@app.post("/api/pilot/battery/finish", dependencies=[Depends(ratelimit.rate_limit(30, 60, "pilot-battery"))])
async def pilot_battery_finish(req: BatteryFinishReq, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """층을 마친다. 문항 수·준비된 문항 수·못 낸 까닭과 기기·렌더링 요약을 남긴다. SNR 층은 계단 추정값을 정한다."""
    import pilot_battery as _pb
    from database import P3ClosedResponse, P3OpenResponse
    from sqlalchemy import select, func
    from datetime import datetime as _dt
    prof = await _battery_gate(current_user, db)
    m, _, _ = _battery_manifest()
    row = await _battery_session(req.session_id, current_user.id, db)
    if row.completed:
        return {"completed": True, "already": True}
    items = _battery_items(m, row.session_label, row.layer, prof.pilot_seq or row.join_seq or 1, row.planned_order,
                           row.snr_calibrated_db)
    cnt = _battery_counts(items)
    R = P3ClosedResponse if row.layer in _pb.CLOSED_LAYERS else P3OpenResponse
    n_answered = (await db.execute(select(func.count(R.id)).where(R.session_id == row.id))).scalar() or 0
    out = {"completed": True, "n_answered": int(n_answered), **cnt}
    if row.layer == "snr":
        st = await _battery_snr_state(row.id, m, db)
        if st["estimate_db"] is None and cnt["n_ready"] > 0:
            raise HTTPException(status_code=409, detail="SNR을 아직 정하지 못했습니다. 문장을 더 풀어 주세요.")
        row.snr_calibrated_db = st["estimate_db"]
        out["snr_calibrated_db"] = st["estimate_db"]
        out["estimate_kind"] = st["estimate_kind"]
    row.n_items, row.n_ready, row.missing = cnt["n_items"], cnt["n_ready"], cnt["missing"]
    row.render_log = _pb.clean_render_log(req.render_log)
    if row.layer in ("av", "snr"):
        row.headphone_check, row.volume_fixed = req.headphone_check, req.volume_fixed
    row.completed, row.completed_at = True, _dt.utcnow()
    await db.commit()
    return out


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
        return _cr.review(req.kind, req.item or {}, req.decision, reviewer=_reviewer_tag(current_user))
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
                               current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """디지털 독화 배치검사 문항(축 I) — 지각 난이도로 통제한 입모양 단어 4지선다.
    오답 보기는 정답과 시각적으로 혼동되는(동구형이음·최소대립) 단어를 우선 배치한다.
    form='A'/'B'를 주면 향상도검사용 동형(난이도 매칭) 사전/사후 폼을 반환한다."""
    import assessment as _asmt
    words = [w["word"] for w in _curriculum.WORD_BANK]
    if form in ("A", "B"):
        # 사전·사후는 동결된 판본(data/assessment/forms_v1.json)을 쓴다 — 콘텐츠가 바뀌어도 같은 문항.
        forms = _asmt.frozen_forms(words)
        items = forms.get(form, [])
        # 전이 조건(커리큘럼 계획 2-3): 다른 동형 폼을 이미 본 사용자에게 이 폼은 사후 검사다. 문항 절반을 검사 전용 가상 화자로
        # 낸다(문항마다 talker, 채점 때 item_log에 남는다). 보통 B지만 파일럿 역균형(B 먼저)이면 A가 사후라 A에 붙는다.
        from database import PlacementResult
        from sqlalchemy import select
        other = "B" if form == "A" else "A"
        post = (await db.execute(select(PlacementResult.id).where(
            PlacementResult.user_id == current_user.id, PlacementResult.form == other).limit(1))).first() is not None
        if post:
            items = _asmt.assign_talker_conditions(items, current_user.id)
        return {"items": items, "form": form, "version": forms.get("version"), "post": post}
    # 배치검사는 사전·사후 문항 단어를 정답·보기에서 모두 뺀다 — 사전검사 전에 문항을 미리 보지 않게(축 I).
    # 드문 말도 뺀다(9/27: 적응형 8문항의 25~44%가 드문 말을 정답·보기로 담았다, 어휘 지식이 점수에 섞인다).
    skip = _excluded_training_words()
    # n은 1~20으로 맞춘다(0이면 0으로 나눠 500, 아주 크면 단어장 전체를 돌며 몇 초씩 서버를 붙잡았다).
    items = _asmt.build_placement_items([w for w in words if w not in skip], n=max(1, min(int(n), 20)))
    return {"items": items, "form": "placement"}


class PlacementNextReq(BaseModel):
    asked: list = []
    responses: dict = {}
    n: int = 12    # 최대 문항 수. 그 전에 시작 단계가 분명해지면 끝낸다(docs/assessment-design.md 12절)


@app.post("/api/assessment/placement/next")
async def assessment_placement_next(data: PlacementNextReq,
                                    current_user=Depends(get_current_user)):
    """적응형 배치검사(축 I) — 지금까지의 정오답으로 능력 θ를 추정해 다음 문항 1개를 고른다.
    난이도지수(C)에 θ를 맞추고 누적 오답 자질을 표적으로 겨냥한다. 최대 N 도달, 문항 소진, 또는 최소 5문항 뒤 한 시작 단계의
    사후 확률이 0.85 이상이면 done(docs/assessment-design.md 12절, 예전에는 누구에게나 8문항).
    동형폼(A/B) 향상도검사는 이 경로를 타지 않아 사전·사후 통제 비교의 불변성을 지킨다."""
    import assessment as _asmt
    skip = _excluded_training_words()   # 사전·사후 문항 단어와 드문 말은 배치검사에 내지 않는다(위 GET과 같은 기준)
    words = [w["word"] for w in _curriculum.WORD_BANK if w["word"] not in skip]
    n = max(3, min(20, data.n or _asmt.ADAPTIVE_MAX_ITEMS))
    asked = data.asked or []
    responses = data.responses or {}
    est = _asmt.estimate_ability(asked, responses)
    if len(asked) >= n or est["confident"]:
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
        trials_before = await _practice_trial_count(current_user.id, db)
        if form in ("A", "B"):
            result["trials_before"] = trials_before
            # 처음 보는 동형 폼이면 사전 검사다. 연습을 기준 이상 한 뒤라면 결과 화면이 부드럽게 알린다(막지 않는다)
            from sqlalchemy import select as _sel
            seen = (await db.execute(_sel(PlacementResult.id).where(
                PlacementResult.user_id == current_user.id, PlacementResult.form.in_(("A", "B"))).limit(1))).first()
            if seen is None:
                result["pretest"] = {"trials_before": trials_before,
                                     "after_training": _asmt.pretest_after_training(trials_before),
                                     "flag_threshold": _asmt.PRETEST_TRIALS_FLAG}
        db.add(PlacementResult(
            user_id=current_user.id, form=form,
            total=result["total"], correct=result["correct"], accuracy=result["accuracy"],
            ability=result["ability"], level=result["level"],
            error_visemes=result.get("error_visemes", []),
            error_phonemes=result.get("error_phonemes", []),
            form_version=version, item_log=result.get("item_log", []), trials_before=trials_before,
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


# ── 지연 유지 검사(C7, retention.py) ──
# 사후 검사 뒤 LIPLAB_RETENTION_DAYS일(기본 28, 14~28)이 지나면 같은 동형 폼을 다시 보게 권한다. 사전·사후 흐름(위 placement·score·
# history·progression)은 그대로 두고, 예약은 검사 기록에서 계산하며 결과는 retention_results에 따로 남긴다.

async def _retention_context(user_id: int, db) -> dict:
    """{pp: {pre, post} 또는 None, done: 사후 뒤 최근 유지 검사 또는 None, status: retention.status}."""
    import os as _os
    import retention as _ret
    from database import PlacementResult, RetentionResult
    from sqlalchemy import select
    rows = (await db.execute(select(PlacementResult).where(PlacementResult.user_id == user_id)
                             .order_by(PlacementResult.created_at, PlacementResult.id))).scalars().all()
    pp = _ret.post_test(rows)
    done = None
    if pp:
        done = (await db.execute(select(RetentionResult).where(
            RetentionResult.user_id == user_id, RetentionResult.post_result_id == pp["post"].id)
            .order_by(RetentionResult.created_at.desc()))).scalars().first()
    st = _ret.status(_kst_date(pp["post"].created_at) if pp else None, _kst_date(done.created_at) if done else None,
                     _kst_today(), _ret.retention_days(_os.getenv("LIPLAB_RETENTION_DAYS")))
    return {"pp": pp, "done": done, "status": st}


def _retention_items(post, user_id: int) -> list:
    """유지 검사 문항: 사후 검사와 같은 동형 폼·같은 화자 조건 배정(assign_talker_conditions는 사용자별로 결정론적이다)."""
    import assessment as _asmt
    forms = _asmt.frozen_forms([w["word"] for w in _curriculum.WORD_BANK])
    items = list(forms.get(post.form, []))
    if _asmt.has_talker_conditions(getattr(post, "item_log", None)):
        items = _asmt.assign_talker_conditions(items, user_id)
    return items


@app.get("/api/assessment/retention")
async def assessment_retention(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """유지 검사 상태: state = none(사후 검사 없음) | waiting | due(볼 때) | done. due_on·days_left와, 봤으면 사후·유지 정답률."""
    ctx = await _retention_context(current_user.id, db)
    out = dict(ctx["status"])
    if ctx["pp"]:
        post = ctx["pp"]["post"]
        out["form"] = post.form
        out["post_accuracy"] = post.accuracy
    if ctx["done"]:
        out["retention_accuracy"] = ctx["done"].accuracy
        out["note"] = "사후 검사와 같은 문항이라 기억 효과가 조금 섞일 수 있어요."
    return out


@app.get("/api/assessment/retention/items")
async def assessment_retention_items(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """유지 검사 문항(볼 때가 된 경우만)."""
    import assessment as _asmt
    ctx = await _retention_context(current_user.id, db)
    if ctx["status"]["state"] != "due":
        raise HTTPException(status_code=409, detail="지금은 유지 검사를 볼 때가 아니에요.")
    post = ctx["pp"]["post"]
    return {"items": _retention_items(post, current_user.id), "form": post.form,
            "version": (_asmt.frozen_forms(build_if_missing=False) or {}).get("version")}


class RetentionScoreReq(BaseModel):
    responses: dict


@app.post("/api/assessment/retention/score")
async def assessment_retention_score(data: RetentionScoreReq, current_user=Depends(get_current_user),
                                     db: AsyncSession = Depends(get_db)):
    """유지 검사 채점. 문항은 서버가 다시 만든다(사후 검사와 같은 폼). 결과는 retention_results에만 남기고 사전·사후 비교·취약 입모양·
    숙달에는 넣지 않는다."""
    import assessment as _asmt
    from database import RetentionResult
    ctx = await _retention_context(current_user.id, db)
    if ctx["status"]["state"] != "due":
        raise HTTPException(status_code=409, detail="지금은 유지 검사를 볼 때가 아니에요.")
    post = ctx["pp"]["post"]
    items = _retention_items(post, current_user.id)
    responses = {str(k): v for k, v in (data.responses or {}).items() if isinstance(v, str)}
    result = _asmt.score_placement(items, responses)
    db.add(RetentionResult(
        user_id=current_user.id, form=post.form, form_version=post.form_version, post_result_id=post.id,
        days_after_post=ctx["status"].get("days_since_post"), total=result["total"], correct=result["correct"],
        accuracy=result["accuracy"], ability=result["ability"], level=result["level"], item_log=result.get("item_log", [])))
    await db.commit()
    return {**result, "form": post.form, "post_accuracy": post.accuracy,
            "days_after_post": ctx["status"].get("days_since_post")}

def _placement_scores(*rows) -> list:
    """사전·사후 비교용 능력·수준. 모든 검사에 문항 기록(item_log)이 있으면 지금 추정기로 다시 채점해 채점 방식이 섞이지 않게
    한다(9/27 능력 추정 변경, docs/assessment-design.md 10절). 하나라도 없으면 저장값을 그대로 쓴다.
    새 화자 조건이 있는 사후 검사(계획 2-3)는 기본 얼굴 문항만으로 채점한다(기본 얼굴 향상도)."""
    import assessment as _asmt
    re_ = [_asmt.rescore_log(_asmt.default_face_log(getattr(r, "item_log", None))) for r in rows]
    if all(re_):
        return re_
    return [{"ability": r.ability, "level": r.level} for r in rows]


async def _practice_trial_count(user_id, db) -> int:
    """지금까지의 독화 연습 시행 수: 선다형 시행(TrialAttempt) + 문장 채점(Progress). 자가진단·표준검사·말하기는 넣지 않는다.
    검사 결과에 trials_before로 남겨 연습 뒤에 본 사전 검사를 표시한다(assessment.PRETEST_TRIALS_FLAG)."""
    from sqlalchemy import select, func
    from database import TrialAttempt, Progress
    n = 0
    for M in (TrialAttempt, Progress):
        n += (await db.execute(select(func.count(M.id)).where(M.user_id == user_id))).scalar() or 0
    return int(n)


def _face_counts(row):
    """(정답 수, 문항 수). 새 화자 조건이 있는 검사는 기본 얼굴 절반만 센다(_face_accuracy와 같은 기준). 문항 기록이 없으면 저장값."""
    import assessment as _asmt
    log = _asmt.default_face_log(getattr(row, "item_log", None))
    rows = [it for it in (log or []) if isinstance(it, dict)]
    if rows:
        return sum(1 for it in rows if it.get("correct")), len(rows)
    return (row.correct or 0), (row.total or 0)


def _accuracy_change(a, b):
    """사전 a → 사후 b 정답률 차이의 Newcombe 95% 구간(두 검사는 서로 다른 문항이라 독립 표본으로 본다). 문항 수가 0이면 None."""
    import eval_metrics as _em
    xa, na = _face_counts(a)
    xb, nb = _face_counts(b)
    return _em.newcombe_diff(xa, na, xb, nb)


def _pretest_flag(row) -> dict:
    """사전 검사 전 연습량과 '연습 뒤 사전' 표시(기준 assessment.PRETEST_TRIALS_FLAG). 9/29 이전 검사는 값이 없다."""
    import assessment as _asmt
    tb = getattr(row, "trials_before", None)
    return {"trials_before": tb, "after_training": _asmt.pretest_after_training(tb),
            "flag_threshold": _asmt.PRETEST_TRIALS_FLAG}


def _face_accuracy(row) -> float:
    """기본 얼굴 정답률. 새 화자 조건이 있는 검사(계획 2-3)는 기본 얼굴 절반의 정답률, 그 밖은 저장값."""
    import assessment as _asmt
    log = getattr(row, "item_log", None)
    if _asmt.has_talker_conditions(log):
        acc = _asmt.log_accuracy(_asmt.default_face_log(log))
        if acc is not None:
            return acc
    return row.accuracy


@app.get("/api/assessment/history")
async def assessment_history(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """배치·향상도 검사 이력 — 최근 검사와 같은 종류의 앞선 검사(baseline), 그리고 향상도(delta)를 반환.
    같은 종류끼리만 비교한다(assessment.comparable_pair): 동형 폼(같은 판본의 A·B)끼리, 또는 자가진단(적응형)끼리. 예전에는
    종류와 상관없이 첫 검사와 비교해, 적응형 자가진단(정답률이 능력과 무관하게 절반 안팎) 뒤 동형 폼을 본 학습자에게 학습 효과가
    없어도 θ 0.3에서 −18%p가 나왔다. 짝이 없으면 delta는 None이다. comparison에 비교 종류와 문구를 준다.
    delta.accuracy_ci95·accuracy_clear는 Newcombe 95% 구간과 그 구간이 0을 벗어났는지(화면은 clear일 때만 색을 쓴다).
    pretest_taken은 동형 폼(A·B)을 한 번이라도 봤는지다(자가진단 뒤 사전 검사 권유에 쓴다).
    (동형 폼 통제 비교는 /api/assessment/progression.)"""
    import assessment as _asmt
    from database import PlacementResult
    from sqlalchemy import select
    r = await db.execute(select(PlacementResult).where(
        PlacementResult.user_id == current_user.id).order_by(PlacementResult.created_at))
    rows = r.scalars().all()

    def _row(x):
        return {"accuracy": _face_accuracy(x), "ability": x.ability, "level": x.level,
                "error_visemes": x.error_visemes or [],
                "at": x.created_at.isoformat() if x.created_at else None}
    if not rows:
        return {"count": 0, "baseline": None, "latest": None, "delta": None, "comparison": None,
                "pretest_taken": False}
    pretest_taken = any(x.form in _asmt.FIXED_FORMS for x in rows)
    pair = _asmt.comparable_pair(rows)
    latest_row = rows[-1]
    base_row = pair["base"] if pair else None
    latest = _row(latest_row)
    if base_row is None:
        latest.update(_placement_scores(latest_row)[0])
        return {"count": len(rows), "baseline": None, "latest": latest, "delta": None, "comparison": None,
                "pretest_taken": pretest_taken}
    baseline = _row(base_row)
    sb, sl = _placement_scores(base_row, latest_row)
    baseline.update(sb)
    latest.update(sl)
    # 극복·신규 입모양은 두 검사의 문항 기록을 전부 다시 세어 정한다(저장된 상위 3개끼리 비교하면 순위만 밀린 입모양도 극복으로 나왔다)
    delta = _asmt.improvement_delta(baseline, latest, getattr(base_row, "item_log", None),
                                    getattr(latest_row, "item_log", None))
    nc = _accuracy_change(base_row, latest_row)
    delta["accuracy_ci95"] = nc["ci95"] if nc else None
    delta["accuracy_clear"] = bool(nc and nc["clear"])
    return {"count": len(rows), "baseline": baseline, "latest": latest, "delta": delta,
            "comparison": {"kind": pair["kind"], "label": pair["label"],
                           "baseline_form": base_row.form, "latest_form": latest_row.form},
            "pretest_taken": pretest_taken}


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
    표준 평가셋을 한 자원으로 제공한다. 데이터 유래 자모 시각유사도는 LIPLAB_PUBLISH_DATA_DERIVED=1일 때만
    싣는다(perceptual.publish_data_derived). 한국어 독화에는 이런 표준 자원이 거의 없어, 앱 밖 연구·교육에서도
    쓸 수 있게 노출한다."""
    import perceptual as _perc
    return _perc.build_standard_resources([w["word"] for w in _curriculum.WORD_BANK])


# ── 공개 인터페이스(§6.3) — 로그인 없이 쓰는 무상태 API. IP당 요청 수만 제한하고 아무것도 저장하지 않는다 ──
_PUBLIC_RES = None


@app.get("/api/public/resources", dependencies=[Depends(ratelimit.rate_limit(20, 60, "public"))])
async def public_resources():
    """공개 표준 독화 자원(축 C) — 동구형이음 사전·난이도 지수·최소대립/동구형 쌍. 데이터 유래 자모 시각 유사도는
    LIPLAB_PUBLISH_DATA_DERIVED=1일 때만 싣는다. 판본(semver)과 라이선스(CC BY 4.0)가 meta에 있다.
    결정론적이라 한 번 만들어 둔다."""
    global _PUBLIC_RES
    if _PUBLIC_RES is None:
        import perceptual as _perc
        _PUBLIC_RES = _perc.build_standard_resources([w["word"] for w in _curriculum.WORD_BANK])
    return _PUBLIC_RES


class PublicScoreReq(BaseModel):
    target: str
    answer: str


@app.post("/api/public/score", dependencies=[Depends(ratelimit.rate_limit(30, 60, "public-score"))])
async def public_score(req: PublicScoreReq):
    """독화 답 채점(무상태) — 목표 문장과 읽은 답을 '소리 나는 대로' 자모로 바꿔 음운 유사도로 채점하고,
    어느 자리에서 어떤 입모양을 헷갈렸는지 준다. 앱 밖 수업·연구에서 같은 채점 기준을 쓰도록 연다.
    입력은 각 100자까지, 요청 내용은 저장하지 않는다."""
    target, answer = (req.target or "").strip(), (req.answer or "").strip()
    if not target or len(target) > 100 or len(answer) > 100:
        raise HTTPException(status_code=400, detail="target은 1~100자, answer는 100자까지")
    from scoring import calculate_score as _score, viseme_confusions
    r = await _score(target, answer, mode="visual")
    return {"score": r.get("score"), "phoneme_accuracy": r.get("phoneme_accuracy"),
            "viseme_errors": r.get("viseme_errors"), "confusions": viseme_confusions(target, answer) if answer else [],
            "method": "표준발음 자모 정렬 + 입모양 기준 유사도·정밀도/재현율(독화 이해 채점 v2, docs/scoring-v2.md)"}


@app.get("/api/assessment/progression")
async def assessment_progression(current_user=Depends(get_current_user),
                                 db: AsyncSession = Depends(get_db)):
    """통제된 향상도(축 I) — 동형 폼 사전·사후 결과를 비교해 델타·음소별 오류 감소를 반환.
    사전은 먼저 본 동형 폼, 사후는 그 뒤에 본 다른 동형 폼이다. 보통 A→B지만, 파일럿에서 순서를 바꿔(역균형)
    B를 먼저 보면 B→A로 비교한다. 동형 폼 두 개가 없으면 가장 이른/최근 검사 회차로 대체 비교한다."""
    import assessment as _asmt
    from database import PlacementResult
    from sqlalchemy import select
    rows = (await db.execute(
        select(PlacementResult).where(PlacementResult.user_id == current_user.id)
        .order_by(PlacementResult.created_at.asc())
    )).scalars().all()
    if len(rows) < 2:
        return {"available": False, "n": len(rows),
                "note": "사전·사후 검사가 2회 이상이면 향상도가 나옵니다."}
    ab = [r for r in rows if r.form in ("A", "B")]
    a = ab[0] if ab else None                                                    # 사전: 먼저 본 동형 폼
    # 사후: 뒤에 본 다른 폼. 사전과 같은 판본을 먼저 찾는다(9/27 v2에서 오답을 바꿔, v1 A와 v2 B는 동형이 아니다)
    b = next((r for r in reversed(ab) if a is not None and r.form != a.form and r.form_version == a.form_version), None)
    same_version = b is not None
    if b is None:
        b = next((r for r in reversed(ab) if a is not None and r.form != a.form), None)
    if a is None or b is None:
        a, b = rows[0], rows[-1]
    # 자모별 오류 변화는 두 검사의 문항 기록을 전부 다시 센 값끼리 비교한다. 예전에는 저장된 상위 6개끼리라, 6위 밖으로 밀린
    # 자모가 'n→0'으로 나왔다. 문항 기록이 없는 옛 검사가 끼면 비운다(assessment.phoneme_change)
    # 자모 변화는 사후 검사 24문항을 모두 센다(기본 얼굴 절반만 세면 문항 수가 반이라 오류 수가 저절로 준다). 새 화자 문항이
    # 섞여 있어 사후 오류는 조금 많게 나올 수 있다(보수적).
    per_phoneme = _asmt.phoneme_change(getattr(a, "item_log", None), getattr(b, "item_log", None))
    sa, sb = _placement_scores(a, b)
    # 기본 얼굴 향상도(계획 2-3): 사후 검사에 새 화자 조건이 있으면 사후 정확도·수준은 기본 얼굴 절반으로 잰다. 새 화자 조건 점수는
    # talker_transfer에 따로 준다(앱 안 근거리 전이, 실제 사람 전이 아님). 조건이 없는 옛 검사는 예전 값 그대로다.
    acc_a, acc_b = _face_accuracy(a), _face_accuracy(b)
    transfer = _asmt.talker_transfer(getattr(b, "item_log", None))
    # 개인 차이의 색은 Newcombe 95% 구간이 0을 벗어날 때만(docs/eval-metrics.md 6절). 사전 24문항·사후 기본 얼굴 12문항이라
    # 구간이 넓고, 학습 효과가 없을 때 예전(부호만 보고 색)에는 35~46%가 빨강이었다
    nc = _accuracy_change(a, b)
    return {
        "available": True,
        "pre": {"form": a.form, "accuracy": acc_a, "level": sa["level"], "ability": sa["ability"], **_pretest_flag(a)},
        "post": {"form": b.form, "accuracy": acc_b, "level": sb["level"], "ability": sb["ability"],
                 "accuracy_all": b.accuracy,
                 "n_default": transfer["default"]["n"] if transfer else None},
        "talker_transfer": transfer,
        "accuracy_delta": round(acc_b - acc_a, 3),
        "accuracy_delta_ci95": nc["ci95"] if nc else None,
        "accuracy_delta_clear": bool(nc and nc["clear"]),
        "level_delta": sb["level"] - sa["level"],
        "ability_delta": round(sb["ability"] - sa["ability"], 3),
        "error_phoneme_change": per_phoneme,
        "homogeneous": {a.form, b.form} == {"A", "B"} and same_version,
        "form_versions": [a.form_version, b.form_version],
        "order": f"{a.form}→{b.form}",
    }


@app.get("/api/assessment/report")
async def assessment_report(tz_offset_min: int = -540, current_user=Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    """교사·언어재활사용 결과지(I-9) — 검사 이력, 사전·사후 비교, 최근 검사의 오류 프로파일, 학습량, 조음 교정
    요약을 한 번에 준다. 화면(학습 효과 리포트)이 이것으로 인쇄용 결과지를 만든다. 본인 기록만 준다.
    날짜는 tz_offset_min(브라우저 Date.getTimezoneOffset(), 한국 −540)으로 정한 현지 날짜다(분석 개요와 같은 기준).
    검사는 규준(연령·청력 집단별 기준)이 없고 신뢰도는 모의실험 값이라, 해석 주의를 notes에 함께 싣는다."""
    import articulation as _art
    import analytics as _an
    from datetime import datetime as _dt
    from sqlalchemy import select, func, cast, Integer
    from database import PlacementResult, TrialAttempt, SpeakAttempt, Progress, ArticulationSession
    tz = max(-840, min(720, int(tz_offset_min)))

    def local_day(ts):
        return _an.to_local(ts, tz).date().isoformat() if ts else None

    uid = current_user.id
    tests = (await db.execute(select(PlacementResult).where(PlacementResult.user_id == uid)
                              .order_by(PlacementResult.created_at))).scalars().all()
    vis_name = {l["viseme_id"]: l["name"] for l in _curriculum.VISEME_LESSONS}
    latest = tests[-1] if tests else None
    err_vis = [{"viseme_id": v, "name": vis_name.get(v, str(v))}
               for v in ((latest.error_visemes or []) if latest else []) if isinstance(v, int)]
    err_pho = sorted([e for e in ((latest.error_phonemes or []) if latest else []) if isinstance(e, dict)],
                     key=lambda e: -int(e.get("count", 0)))[:8]
    progression = await assessment_progression(current_user=current_user, db=db)
    trials = (await db.execute(select(TrialAttempt.stage, func.count(TrialAttempt.id),
                                      func.sum(cast(TrialAttempt.correct, Integer)))
                               .where(TrialAttempt.user_id == uid).group_by(TrialAttempt.stage))).all()
    sp = (await db.execute(select(func.count(SpeakAttempt.id), func.avg(SpeakAttempt.score))
                           .where(SpeakAttempt.user_id == uid))).one()
    days = set()
    for M in (TrialAttempt, SpeakAttempt, Progress, PlacementResult):
        for (ts,) in (await db.execute(select(M.created_at).where(M.user_id == uid))).all():
            if ts:
                days.add(local_day(ts))
    arts = (await db.execute(select(ArticulationSession).where(ArticulationSession.user_id == uid)
                             .order_by(ArticulationSession.created_at))).scalars().all()
    art = _art.summarize_sessions([{"viseme_id": x.viseme_id, "gap_start": x.gap_start, "gap_end": x.gap_end,
                                    "created_at": x.created_at} for x in arts]) if arts else None
    stage_name = {1: "입모양 인지", 2: "음절·단어", 3: "문장", 4: "대화"}
    now = _dt.utcnow().replace(microsecond=0)
    return {
        "generated_at": now.isoformat() + "Z",
        "issued_on": local_day(now),
        "learner": {"name": current_user.username},
        # 능력·수준은 문항 기록이 모두 있으면 지금 추정기로 다시 채점한 값(_placement_scores, 검사끼리 채점 방식이 섞이지 않게)
        "tests": [{"date": local_day(t.created_at), "form": t.form,
                   "form_version": t.form_version, "total": t.total, "correct": t.correct,
                   "accuracy": round(t.accuracy or 0, 3), "ability": round(sc["ability"] or 0, 2), "level": sc["level"],
                   "trials_before": getattr(t, "trials_before", None)}
                  for t, sc in zip(tests, _placement_scores(*tests) if tests else [])],
        "progression": progression,
        "error_profile": {"visemes": err_vis, "phonemes": err_pho,
                          "from_test": local_day(latest.created_at) if latest else None},
        "activity": {"active_days": len(days),
                     "first_day": min(days) if days else None, "last_day": max(days) if days else None,
                     "trials_by_stage": [{"stage": st or 0, "name": stage_name.get(st or 0, "기타"), "n": n,
                                          "correct": int(c or 0)} for st, n, c in sorted(trials, key=lambda r: r[0] or 0)],
                     "speak": {"n": sp[0] or 0, "mean_score": round(float(sp[1]), 1) if sp[1] is not None else None}},
        "articulation": art,
        "notes": ["이 검사는 규준(연령·청력 집단별 기준 점수)이 아직 없어 다른 학습자와 비교하는 점수가 아닙니다.",
                  "동형 폼 A·B의 신뢰도(KR-20 약 0.76)는 모의실험 값이며, 실제 학습자 자료로 확인하고 있습니다.",
                  "사전·사후 비교는 같은 학습자의 변화를 보는 용도로 씁니다. 사전 24문항·사후 기본 얼굴 12문항이라 한 사람의 "
                  "차이는 잡음이 커서, 95% 구간이 0을 벗어난 경우만 좋아짐·나빠짐으로 읽습니다."]
                 + ([f"사전 검사를 독화 연습 {progression['pre']['trials_before']}회 뒤에 봤습니다. 연습 효과가 사전 점수에 "
                     "들어가 향상도가 작게 나올 수 있습니다."]
                    if progression.get("available") and progression["pre"].get("after_training") else []),
    }


@app.get("/api/conversation/multi", dependencies=[Depends(ratelimit.rate_limit(15, 60, "llm-multi"))])
async def conversation_multi(speakers: int = 2, turns: int = 6, scene: Optional[str] = None, level: Optional[int] = None,
                             current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """다자 대화 시나리오(축 H) — 여러 화자가 번갈아 말하는 짧은 대화(화자 식별 + 입모양 읽기).
    학습자의 약점 입모양이 든 승인 단어(G)를 대화에 넣도록 요청하고(H-3), 턴마다 닮은꼴 오답과
    빈칸 턴을 붙인다(H-4). answer_key는 서버 재채점용 서명 정답(H-9)이다.
    scene은 상황별 시나리오에서 학습자가 적은 상황(선택, 30자로 정리). speakers는 2~4명.
    level은 그 화면에서 고른 난이도(1~5, 선택)로 한 턴 길이를 정한다."""
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
        skip = _excluded_training_words()
        focus = [w["word"] for w in _curriculum.WORD_BANK
                 if targets and w["word"] not in skip and set(_crules.word_visemes(w["word"])) & targets][:30]
        import random as _rnd
        _rnd.shuffle(focus)
        conv = await _conv.generate_multi_conversation(speakers=speakers, turns=turns, scene=scene,
                                                       focus_words=focus[:6],
                                                       level=max(1, min(5, level)) if level else None)
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
        # 클라이언트 집계값이라 0~1로 맞춘다(맞힌 수가 전체보다 크면 합산 점수가 500이 나왔다)
        spk_acc = min(1.0, max(0.0, req.speaker_correct / req.speaker_total)) if req.speaker_total > 0 else 0.0
        read_acc = min(1.0, max(0.0, req.read_correct / req.read_total)) if req.read_total > 0 else 0.0
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
        wv = r.scalars().first()
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
    """데모 계정이 비어 있으면 더미 학습 기록을 채운다(멱등, 기록 있으면 건너뜀).
    공용 데모 계정에만 한다. 9/19~9/26 로그인 화면이 로그인·회원가입 뒤에도 불러, 실제 계정에 가짜 기록이 들어가고
    표시가 없던 예전 계정은 기록이 지워졌다."""
    if (current_user.email or "").lower() != _DEMO_EMAIL:
        return {"seeded": False}
    import demo_seed
    seeded = await demo_seed.run(current_user, db)
    return {"seeded": seeded}


async def _bump_speak_progress(user_id: int, stage: int, passed: bool,
                               min_attempts: int, mastery_pct: float, db, score=None, voiced: bool = True):
    """발화 단계 진행률 rolling 갱신(읽기 _bump_stage_progress의 발화판). sp 반환.
    숙달 점수는 편향 보정 이동 평균(_ewma_mastery), 문턱은 speak_curriculum의 단계별 mastery(85·90). 예전 누적 합격률(65·70)은
    초반 실패가 끝까지 남아 늦었다(가상 학습자 지연 40~51번 → 28~44번, 거짓 숙달도 모든 단계에서 낮음, docs/mastery-ewma.md 6절)."""
    from database import SpeakStageProgress
    from sqlalchemy import select
    r = await db.execute(select(SpeakStageProgress).where(
        SpeakStageProgress.user_id == user_id, SpeakStageProgress.stage == stage))
    sp = r.scalars().first()
    if sp is None:
        sp = SpeakStageProgress(user_id=user_id, stage=stage, status="in_progress",
                                attempts=0, correct=0, mastery_score=0.0)
        db.add(sp)
    sp.attempts += 1
    if passed:
        sp.correct += 1
    sp.mastery_score = _ewma_mastery(sp.mastery_score, sp.attempts - 1, passed)
    # 한번 숙달하면 유지한다(누적 정확도가 조금 떨어졌다고 다음 단계를 다시 잠그지 않게)
    reached = sp.status == "mastered" or (sp.attempts >= min_attempts and sp.mastery_score >= mastery_pct)
    # 모음·자음(2·3)은 이동 평균이 문턱에 닿아도 낱말 속 소리 확인(최근 3번 중 2번 합격, speak_curriculum._PROBE)을 넘어야 숙달이다(계획 2-5, _speak_carryover)
    probe_cfg = (_speakcur.get_stage(stage) or {}).get("probe")
    if reached and sp.status != "mastered" and probe_cfg:
        reached = _speakcur.probes_ok(await _speak_probe_passes(user_id, stage, int(probe_cfg["n"]), db), probe_cfg)
    # 4·5단계 개인 향상 경로(9/28, speak_curriculum.gain_mastered): 채점기가 청각장애 발화를 낮게 보는 몫이 있어 절대 문턱에
    # 못 닿는 학습자도 자기 처음 점수보다 뚜렷이 늘면 숙달로 본다. 지금 시도는 아직 SpeakAttempt에 없으므로 score를 덧붙인다.
    # 복습 세션 시도와 소리 없는 시도는 빼고(리뷰 뒤 고침, 기준선이 0으로 내려가 늘 30점이어도 숙달했다), 소리 없는 이번 시도로는
    # 판정하지 않는다. 최근 10번 중앙값이 합격선 − 15 이상이어야 한다(speak_curriculum._GAIN floor).
    stg = _speakcur.get_stage(stage) or {}
    gain = stg.get("gain")
    if not reached and gain and score is not None and voiced and sp.attempts >= int(gain["min_attempts"]):
        scores = await _speak_gain_scores(user_id, stage, gain, db)
        reached = scores is not None and _speakcur.gain_mastered(scores + [score], gain, stg.get("pass"))
    sp.status = "mastered" if reached else "in_progress"
    return sp


async def _speak_gain_scores(user_id: int, stage: int, gain: dict, db) -> Optional[list]:
    """개인 향상 경로에 쓸 이전 점수(시간순): 복습이 아니고 소리가 잡힌 시도(speak_curriculum.voiced_attempt와 같은 기준)의 처음
    first개와 최근 recent − 1개(이번 시도를 덧붙이면 recent개). 이번 시도까지 min_attempts에 못 미치면 None.
    예전에는 이 단계 점수를 시도마다 모두 읽었다."""
    from database import SpeakAttempt
    from sqlalchemy import select, func, or_
    cond = (SpeakAttempt.user_id == user_id, SpeakAttempt.stage == stage,
            SpeakAttempt.review.is_not(True), SpeakAttempt.score.is_not(None),
            func.coalesce(SpeakAttempt.loudness, 0) > 0,
            or_(SpeakAttempt.transcript.is_(None), SpeakAttempt.transcript != "", SpeakAttempt.score > 0))
    first_n, recent_n = int(gain["first"]), int(gain["recent"])
    n = (await db.execute(select(func.count(SpeakAttempt.id)).where(*cond))).scalar() or 0
    if n + 1 < max(int(gain["min_attempts"]), first_n + recent_n):
        return None
    first = (await db.execute(select(SpeakAttempt.score).where(*cond).order_by(SpeakAttempt.id).limit(first_n))).all()
    last = (await db.execute(select(SpeakAttempt.score).where(*cond)
                             .order_by(SpeakAttempt.id.desc()).limit(recent_n - 1))).all()
    return [x for (x,) in first] + [x for (x,) in reversed(last)]


async def _speak_probe_passes(user_id: int, stage: int, n: int, db) -> list:
    """낱말 속 소리 확인(SpeakAttempt mode 'probe')의 최근 n번 합격 여부, 시간순."""
    from database import SpeakAttempt
    from sqlalchemy import select
    rows = (await db.execute(select(SpeakAttempt.passed).where(
        SpeakAttempt.user_id == user_id, SpeakAttempt.stage == stage, SpeakAttempt.mode == "probe",
        SpeakAttempt.passed.is_not(None))   # 세지 않은 확인(정렬 실패·소리 없음)은 뺀다
        .order_by(SpeakAttempt.id.desc()).limit(n))).all()
    return [bool(p) for (p,) in reversed(rows)]


def _speak_carryover(sp, stg) -> bool:
    """낱말 속 소리 확인 중인가: 모음·자음 단계에서 이동 평균 숙달 조건은 채웠지만 아직 숙달하지 않은 상태(계획 2-5, P9).
    따로 낸 음절 점수(Ling의 음성 수준)만으로 숙달하지 않고, 배운 소리를 뜻 있는 낱말 속에서도 내는지(음운 수준) 본다."""
    return bool(sp is not None and (stg or {}).get("probe") and sp.status != "mastered"
                and sp.attempts >= stg["min_attempts"] and sp.mastery_score >= stg["mastery"])


async def _speak_probe_status(user_id: int, stage: int, sp, db) -> Optional[dict]:
    """진행 응답에 붙일 확인 상태 {carryover, passed, tried, n, need}. 확인이 없는 단계면 None."""
    stg = _speakcur.get_stage(stage) or {}
    cfg = stg.get("probe")
    if not cfg:
        return None
    window = await _speak_probe_passes(user_id, stage, int(cfg["n"]), db)
    return {"carryover": _speak_carryover(sp, stg), "passed": sum(window), "tried": len(window),
            "n": int(cfg["n"]), "need": int(cfg["need"])}


async def _settle_speak_probe(user_id: int, stage: int, stg: dict, passed: bool, db, counted: bool = True):
    """낱말 속 소리 확인 한 번을 반영한다. 이동 평균·시도 수는 그대로 두고, 이동 평균 숙달 조건을 채운 상태에서 이번 확인까지 넣어
    최근 확인 창이 조건(_PROBE)을 채우면 숙달로 올린다. 이번 시도는 아직 SpeakAttempt에 없으므로 passed를 덧붙인다. 세지 않는 확인
    (counted False)은 창에 넣지 않는다. 진행 기록이 없으면 None."""
    from database import SpeakStageProgress
    from sqlalchemy import select
    sp = (await db.execute(select(SpeakStageProgress).where(
        SpeakStageProgress.user_id == user_id, SpeakStageProgress.stage == stage))).scalars().first()
    if sp is None or sp.status == "mastered":
        return sp
    cfg = stg["probe"]
    if counted and sp.attempts >= stg["min_attempts"] and sp.mastery_score >= stg["mastery"]:
        window = await _speak_probe_passes(user_id, stage, int(cfg["n"]) - 1, db) + [passed]
        if _speakcur.probes_ok(window, cfg):
            sp.status = "mastered"
    return sp


@app.get("/api/speak/curriculum")
async def speak_curriculum_stages(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """발화 6단계 + 사용자 상태. 게이팅: 0단계 항상 열림, N단계는 N-1 숙달 시 해금(건너뛰기로 연 단계까지는 열림)."""
    from database import SpeakStageProgress
    from sqlalchemy import select
    r = await db.execute(select(SpeakStageProgress).where(SpeakStageProgress.user_id == current_user.id))
    sp_map = {sp.stage: sp for sp in r.scalars().all()}
    prof = await _get_or_create_profile(current_user.id, db)
    pointer = prof.speak_current_stage or 0
    stages = []
    for meta in _speakcur.stages_overview():
        st = dict(meta)
        n = meta["stage"]
        sp = sp_map.get(n)
        if n == 0:
            base_open = True
        else:
            prev = sp_map.get(n - 1)
            base_open = (prev is not None and prev.status == "mastered") or n <= pointer
        if not base_open:
            st["status"] = "locked"
        elif sp is None:
            st["status"] = "unlocked"
        else:
            st["status"] = sp.status
            st["mastery_score"] = round(sp.mastery_score, 1)
            st["attempts"] = sp.attempts
        stages.append(st)
    if _unlock_all_for(current_user):
        for st in stages:
            if st.get("status") == "locked":
                st["status"] = "unlocked"
    return {"stages": stages}


class SpeakSkipReq(BaseModel):
    stage: int


@app.post("/api/speak/skip")
async def speak_skip(req: SpeakSkipReq, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """발화 트랙 건너뛰기(Figma 78:8 말풍선 → 79:5 확인 → 80:6 해금). 잠긴 다음 단계 하나를 연다(바로 앞 단계가 열려
    있어야 한다). 독화 트랙은 배치 API(/api/curriculum/track의 start_stage)가 같은 포인터(current_stage)를 옮긴다."""
    from database import SpeakStageProgress
    from sqlalchemy import select
    n = int(req.stage)
    order = [m["stage"] for m in _speakcur.stages_overview()]
    if n not in order or n == 0:
        raise HTTPException(status_code=400, detail="건너뛸 수 없는 단계입니다.")
    prof = await _get_or_create_profile(current_user.id, db)
    pointer = prof.speak_current_stage or 0
    r = await db.execute(select(SpeakStageProgress).where(SpeakStageProgress.user_id == current_user.id))
    mastered = {sp.stage for sp in r.scalars().all() if sp.status == "mastered"}
    prev = n - 1
    prev_open = prev == 0 or prev <= pointer or (prev - 1) in mastered
    if not prev_open:
        raise HTTPException(status_code=400, detail="바로 앞 단계를 먼저 열어야 건너뛸 수 있습니다.")
    prof.speak_current_stage = max(pointer, n)
    await db.commit()
    return {"speak_current_stage": prof.speak_current_stage}


@app.get("/api/speak/stage/{n}", dependencies=[Depends(ratelimit.rate_limit(30, 60, "llm-speakstage"))])
async def speak_stage_content(n: int, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """단계 콘텐츠(항목·모드·가이드).
    단어(4)·문장(5) 단계는 매번 AI로 새 문항을 생성해 변주를 준다(실패 시 큐레이션 풀 폴백).
    발성·모음·자음(0~3)은 정해진 음소 드릴이라 고정."""
    stg = _speakcur.get_stage(n)
    if not stg:
        raise HTTPException(status_code=404, detail="unknown stage")

    items = stg["items"]
    sp = None
    if stg["mode"] == "word":
        # 고정 풀은 음절 수 층을 섞어 끼운다(처음 3개만 1음절). 프론트는 들어올 때마다 0번부터 시작해, 예전 고정 순서로는 앞 14개가
        # 모두 1음절이라 다음절 단어 없이 숙달했다. (사용자, 날짜) 시드라 같은 날에는 순서가 같다(speak_curriculum.mixed_order).
        items = _speakcur.mixed_order(items, f"{current_user.id}:{_kst_today().isoformat()}")
    elif stg["mode"] == "phoneme":
        # 모음·자음: 항목 수만큼 연습한 뒤로는 섞어서 낸다(speak_curriculum.interleaved_order, 계획 2-4)
        from database import SpeakStageProgress
        from sqlalchemy import select
        sp = (await db.execute(select(SpeakStageProgress).where(
            SpeakStageProgress.user_id == current_user.id, SpeakStageProgress.stage == n))).scalars().first()
        items = _speakcur.interleaved_order(items, sp.attempts if sp else 0, f"{current_user.id}:{n}:{_kst_today().isoformat()}")
    # 약한 소리 위주 출제: 최근 말하기 시도에서 D-GOP가 문장 평균보다 늘 낮게 잰 소리(없으면 전사 경로의 혼동)가 든 문항을 앞쪽에
    # 끼운다. 예전에는 약점과 상관없이 같은 순서라, 약한 소리가 든 단어가 앞 12문항에 나오는 비율이 풀 비율 그대로였다
    # (speak_curriculum.weak_sounds·focus_order, scripts/speak_focus_sim.py).
    focus = []
    if stg["mode"] in ("phoneme", "word"):
        try:
            from database import SpeakAttempt
            from sqlalchemy import select
            rows = (await db.execute(select(SpeakAttempt.phones, SpeakAttempt.confusions)
                                     .where(SpeakAttempt.user_id == current_user.id)
                                     .order_by(SpeakAttempt.created_at.desc()).limit(40))).all()
            focus = _speakcur.weak_sounds([{"phones": r[0], "confusions": r[1]} for r in rows])
            items = _speakcur.focus_order(items, focus, lead=3 if stg["mode"] == "word" else 0)
        except Exception as e:
            print(f"[WARN] speak focus failed (stage {n}): {e}")
    # 낱말 속 소리 확인(계획 2-5): 모음·자음 이동 평균이 문턱에 닿았는데 아직 숙달하지 않았으면 4단계 단어 풀에서 목표 소리가 첫 음절에
    # 든 낱말 4개를 따로 준다(약한 소리부터, (사용자, 날짜) seed). 화면은 이것을 먼저 내고, 채점은 단어 규칙(합격 65)으로 한다.
    carryover = _speak_carryover(sp, stg)
    probes = _speakcur.probe_words(n, f"{current_user.id}:{n}:{_kst_today().isoformat()}", weak=focus) if carryover else []
    if os.getenv("LIPLAB_AI_ITEMS", "1") == "1" and stg["mode"] in ("word", "sentence"):
        try:
            import content_gen
            base = [it.get("target") for it in stg["items"]]
            if stg["mode"] == "word":
                gen = await content_gen.generate_words(n=10, max_syllable=3, avoid=base)
                skip = _excluded_training_words()   # 표준검사 정답·드문 말은 AI가 만들어도 내지 않는다
                ai_items = [{"target": w} for w in gen if w not in skip]
            else:
                ai_items = await content_gen.generate_sentences(n=8, avoid=base, with_intonation=True)
            if len(ai_items) >= 4:
                # AI 생성분을 앞에, 기존 풀을 뒤에 섞어 다양성 + 안정성 확보
                items = ai_items + items
        except Exception as e:
            print(f"[WARN] speak AI items gen failed (stage {n}): {e}")

    return {
        "stage": stg["stage"], "title": stg["title"], "mode": stg["mode"],
        "desc": stg["desc"], "guide": stg["guide"], "icon": stg.get("icon", ""),
        "items": items, "focus_sounds": focus,
        "carryover": carryover, "probes": probes, "probe_rule": stg.get("probe"),
    }


# ── 발화(말하기) 채점 — 단계 모드별 채점 + 진행률 + 코칭 ──────────────────────

_JAMO_POSITION = {"o": "초성", "n": "중성", "c": "종성"}   # jamo_vocab 자모 토큰의 위치 접두


def _weak_phones(dgop_result, k: int = 3) -> list:
    """D-GOP 음소 중 가장 약한 소리 k개 [{label, dgop, position}] — 문장 평균의 60% 미만인 것만(축 B-9 코칭 근거).
    자모 토큰의 위치 접두(o:·n:·c:)와 어절 경계는 label에서 떼고, 위치는 position(초성·중성·종성, 음절 토큰이면 None)으로 넘긴다.
    예전에는 위치를 버려 받침이 약해도 코칭이 첫소리 조음(터뜨림·튕김)을 설명했다. D-GOP가 꺼져 있으면 빈 목록."""
    # silent_h: ㄶ·ㅀ + 모음에서 라벨에만 남은 ㅎ(많이[마니]) — 내지 않는 소리라 코칭하지 않는다(jamo_vocab.silent_linking_h)
    phones = [p for p in ((dgop_result or {}).get("phones") or [])
              if p.get("aligned") and p.get("scorable") and p.get("dgop") is not None and not p.get("silent_h")]
    if not phones:
        return []
    mean = sum(p["dgop"] for p in phones) / len(phones)
    out = []
    for p in sorted(phones, key=lambda x: x["dgop"]):
        tok = p.get("token") or ""
        label = tok.split(":", 1)[-1].replace("|", " ").strip()
        if label and p["dgop"] < max(0.05, 0.6 * mean):
            pos = _JAMO_POSITION.get(tok.split(":", 1)[0]) if ":" in tok else None
            out.append({"label": label, "dgop": round(float(p["dgop"]), 3), "position": pos})
        if len(out) >= k:
            break
    return out

def _av_fusion_on() -> bool:
    """입모양 점수를 채점 점수에 섞을지(연구용). 기본은 섞지 않는다(9/24 융합 검증 결과)."""
    return os.getenv("LIPLAB_AV_FUSION") == "1"


@app.post("/api/speak/assess", dependencies=[Depends(ratelimit.rate_limit(40, 60, "audio"))])
async def speak_assess(
    target: str = Form(...),
    audio: UploadFile = File(...),
    loudness: float = Form(0.0),
    pitch_range: float = Form(0.0),
    duration: float = Form(0.0),
    pitch_start: float = Form(0.0),
    pitch_end: float = Form(0.0),
    pitch_ref: float = Form(None),     # 문장 억양: 유성 프레임 전체 중앙값(Hz). 없으면 pitch_start·end로(docs/sentence-intonation.md)
    pitch_final: float = Form(None),   # 문장 억양: 마지막 3프레임 중앙값(Hz)
    pitch_frames: int = Form(None),    # 운율 올리기·내리기: 시작·끝 음높이에 쓴 유성 프레임 수. 없으면(예전 클라이언트) 보지 않는다
    voiced_duration: float = Form(None),   # 가장 길게 이어 낸 소리(초). 없으면(예전 클라이언트) 녹음 길이로 판정
    stage: int = Form(None),
    drill: str = Form(None),
    review: int = Form(0),
    probe: int = Form(0),              # 모음·자음 단계의 낱말 속 소리 확인 문항(계획 2-5)
    mouth_confidence: float = Form(None),
    mouth_track: str = Form(None),   # 녹음 중 입모양 타임라인(B-6) — {"visemes":[...], "frames":[[t, s…], …]}
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """녹음 → (단계 모드에 따라) 지표/전사 채점 → 진행률 갱신 → 코칭.
    발성·운율(0·1)은 지표만으로, 모음·자음·단어·문장(2~5)은 Whisper 전사+음운 유사도."""
    if len(target or "") > _TEXT_MAX:   # 채점 정렬 비용이 길이의 곱이라 상한을 둔다(다른 채점 요청과 같다)
        raise HTTPException(status_code=400, detail="목표 문장이 너무 길어요.")
    data = await _read_audio_limited(audio)

    metrics = {"loudness": loudness, "pitch_range": pitch_range, "duration": duration,
               "pitch_start": pitch_start, "pitch_end": pitch_end, "pitch_ref": pitch_ref, "pitch_final": pitch_final,
               "pitch_frames": pitch_frames,
               "voiced_duration": voiced_duration if voiced_duration is not None and voiced_duration >= 0 else None}
    stg = _speakcur.get_stage(stage) if stage is not None else None
    mode = stg["mode"] if stg else "word"
    # 낱말 속 소리 확인은 이 단계 합격선과 첫 음절 목표 소리로 채점하고(speak_curriculum.score_probe) mode 'probe'로 남긴다. 이동 평균에는
    # 넣지 않고 숙달 확인에만 쓴다. 복습 세션은 진행도를 건드리지 않으므로 확인으로 세지 않는다.
    is_probe = bool(probe) and not review and bool((stg or {}).get("probe"))
    if is_probe:
        # 리뷰 뒤 고침: 확인 상태(_speak_carryover)이고 target이 이 사용자·단계의 오늘(자정을 넘긴 경우 어제) 확인 낱말일 때만 확인으로 센다.
        # 아니면 400으로 막지 않고 보통 시도로 채점한다(숙달 직후 화면에 남은 확인 낱말이 와도 오류가 나지 않게, 보통 시도는 늘 보낼 수 있다).
        from database import SpeakStageProgress
        from sqlalchemy import select
        sp_now = (await db.execute(select(SpeakStageProgress).where(
            SpeakStageProgress.user_id == current_user.id, SpeakStageProgress.stage == stage))).scalars().first()
        from datetime import timedelta as _dt_timedelta
        today = _kst_today()
        is_probe = _speak_carryover(sp_now, stg) and any(
            _speakcur.is_probe_word(stage, target, f"{current_user.id}:{stage}:{d.isoformat()}")
            for d in (today, today - _dt_timedelta(days=1)))

    transcript = None
    confusions = []
    sim = None
    dgop_result = None
    assessment_method = None
    no_voice = False   # 전사 경로에서 소리 없는 녹음이라 전사를 건너뜀
    need_asr = (mode in ("phoneme", "word", "sentence")) or (stage is None)
    if need_asr:
        _ml_admit()   # 추론 대기열이 차면 받기 전에 503(지표만 쓰는 발성·운율은 추론이 없어 해당하지 않는다)
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
                async with _ml_slot():
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

        if assessment_method != "dgop" and _speakcur.no_voice(metrics):
            # 소리가 없는 녹음(프론트 micIssue)은 전사하지 않고 불합격이다. Whisper가 무음에서 만든 문장이 채점되어 합격할 수
            # 있었다(speak_curriculum.no_voice). D-GOP 경로는 그대로 둔다.
            transcript, sim, no_voice = "", 0.0, True
            assessment_method = "asr_transcript"
        elif assessment_method != "dgop":
            from speak_service import transcribe, is_available
            if not is_available():
                raise HTTPException(status_code=503, detail="서버에 음성인식 모델(faster-whisper)이 없습니다.")
            try:
                async with _ml_slot():
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
    probe_counted = False
    if stage is not None and stg is not None:
        if is_probe:
            score, passed, note, probe_counted = _speakcur.score_probe(stage, target, transcript, metrics, sim,
                                                                       (dgop_result or {}).get("phones"))
        else:
            score, passed, note = _speakcur.score_attempt(stage, target, transcript, metrics, drill, sim)
        # 복습 세션은 채점·코칭만 하고 단계 진행도(숙달/해금)는 건드리지 않는다
        if review:
            sp = None
        elif is_probe:
            sp = await _settle_speak_probe(current_user.id, stage, stg, bool(passed), db, counted=probe_counted)
        else:
            sp = await _bump_speak_progress(current_user.id, stage, bool(passed),
                                            stg["min_attempts"], stg["mastery"], db, score=score,
                                            voiced=_speakcur.voiced_attempt(loudness, transcript, score))
    else:
        score = round(sim or 0.0, 1)
        sp = None

    # 축 B 소리·입모양 — 웹캠 입모양(D) 점수는 채점 점수에 섞지 않고 따로 돌려준다(9/24 결정).
    # 538 융합 검증(docs/bfuse-validation.md)에서 웹캠 입모양 점수는 목표 문장을 가르지 못했고(AUC 0.49~0.53),
    # 섞으면 판별력이 낮아졌다(심한 교란 0.778 → 0.583). LIPLAB_AV_FUSION=1이면 연구용으로 예전 융합
    # (음소별 B-5·B-6, 비음 보조 K-5)을 그대로 재현한다.
    av_fusion = None
    audio_score = score        # 회차 상세의 '소리' — 채점 점수(입모양을 섞지 않은 음향 점수)
    vis = None
    mouth = None
    if mouth_confidence is not None and mouth_confidence >= 0:
        import dgop
        vis = min(100.0, mouth_confidence * 100 if mouth_confidence <= 1 else mouth_confidence)   # 0~100으로 맞춘다
        scored_phones = [p for p in ((dgop_result or {}).get("phones") or [])
                         if p.get("aligned") and p.get("scorable")]
        # B-6: 입모양 타임라인이 있으면 음소가 정렬된 시간 구간의 입모양 점수를 구한다
        track = (dgop.parse_mouth_track(mouth_track)
                 if dgop_result and mouth_track and len(mouth_track) <= 300_000 else None)
        vbp = dgop.visual_scores_for_phones(scored_phones, track) if track else None
        if _av_fusion_on():
            # D-GOP 경로면 음소별 소리 점수(B-5)로, 전사 경로면 점수 기반 근사치(1 − 점수/100)로 영상 가중을 정한다.
            if dgop_result:
                # K-5: 웹캠 비음 확률이 오면 ㅁ/ㅂ·ㄴ/ㄷ·ㅇ/ㄱ처럼 입모양이 같은 짝에서만 입모양 점수를 조금 조정한다
                n_nasal = 0
                if track and track.get("nasal") and vbp:
                    dgop.annotate_nasal_expectation(dgop_result.get("phones") or [], target)
                    vbp, n_nasal = dgop.apply_nasal_evidence(vbp, dgop.nasal_evidence_for_phones(scored_phones, track))
                av_fusion = dgop.fuse_audio_visual_per_phone(scored_phones, vis, visual_by_phone=vbp)
                if av_fusion is not None:
                    av_fusion["nasal_phones"] = n_nasal   # 비음 보조로 조정한 음소 수(K-5)
            if av_fusion is None:
                audio_uncertainty = dgop_result["uncertainty"] if dgop_result else max(0.0, 1 - score / 100.0)
                av_fusion = dgop.fuse_audio_visual(score, audio_uncertainty, vis)
            score = av_fusion["score"]
        else:
            by_phone = None
            if vbp:
                by_phone = [{"label": (p.get("token") or "").split(":", 1)[-1].replace("|", " ").strip(), "score": v}
                            for p, v in zip(scored_phones, vbp) if v is not None] or None
            mouth = {"score": round(float(vis), 1), "by_phone": by_phone}

    # 개별 시도 영속화(말하기 분석용 — 독화가 Progress에 쌓는 것과 대칭)
    from database import SpeakAttempt
    _phones = [{"label": (p.get("token") or "").split(":", 1)[-1].replace("|", " ").strip(),
                "dgop": round(float(p["dgop"]), 3)}
               for p in ((dgop_result or {}).get("phones") or [])
               if p.get("aligned") and p.get("scorable") and p.get("dgop") is not None and not p.get("silent_h")][:40]
    attempt = SpeakAttempt(
        user_id=current_user.id, stage=stage, mode="probe" if is_probe else mode, target=target,
        # 세지 않은 확인(소리 없음·목표 소리 자리를 못 찾음)은 passed를 비워 확인 창(_speak_probe_passes)에서 뺀다
        transcript=transcript, score=score, passed=None if is_probe and not probe_counted else passed,
        loudness=loudness, pitch_range=pitch_range, duration=duration,
        pitch_start=pitch_start, pitch_end=pitch_end, confusions=confusions[:6],
        audio_score=None if audio_score is None else round(float(audio_score), 1),
        mouth_score=None if vis is None else round(float(vis), 1),
        fused_score=None if av_fusion is None else round(float(av_fusion["score"]), 1),
        uncertainty=None if not dgop_result else round(float(dgop_result.get("uncertainty") or 0), 3),
        phones=_phones or None, review=bool(review),
    )
    db.add(attempt)
    # SRS 복습 큐 유지 — 발음/단어/문장은 틀리면 예정 등록, 맞으면 간격 확장(세 기둥 공통).
    # 말하기는 0~100 점수가 있으므로 이진 대신 점수 등급으로 복습 간격을 조절한다(SM-2).
    # 낱말 속 소리 확인은 숙달 확인용이라 복습 큐에 넣지 않는다(그 낱말은 4단계에서 따로 연습한다).
    if mode in ("phoneme", "word", "sentence") and passed is not None and not is_probe:
        await _sr_touch(current_user.id, "speak", target, bool(passed), db, score=score)
    await db.commit()
    if sp is not None:
        progress = {"stage": stage, "attempts": sp.attempts,
                    "mastery_score": round(sp.mastery_score, 1),
                    "mastered": sp.status == "mastered"}
        pst = await _speak_probe_status(current_user.id, stage, sp, db)
        if pst is not None:
            progress["probe"] = pst

    # 축 E — 모음 단계에서 목표가 단모음 음절('아'·'이' 등)이면 녹음의 포먼트(F1·F2)로 혀 높낮이·앞뒤
    # 교정 방향을 만든다(formants.py). 웹캠이 못 보는 혀 위치를 소리로 짚어 주는 경로다.
    vowel_fb = None
    if mode == "phoneme" and not no_voice and not is_probe:   # 소리 없는 녹음은 포먼트를 재지 않는다
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
    elif no_voice:
        coaching = note or _speakcur.NO_VOICE_NOTE   # 들은 것이 없으니 LLM 코칭을 부르지 않는다
    else:
        from llm_service import generate_speaking_coaching
        # 억양은 문장에서만, 그것도 기대 방향 규칙(note)이 판정하지 않았을 때만 코칭에 넣는다(음절·단어는 음높이가 고른 게 자연스럽다)
        coaching = await generate_speaking_coaching(target, transcript, score, confusions, metrics,
                                                    weak_phones=_weak_phones(dgop_result),
                                                    intonation=(mode == "sentence" and not note),
                                                    method=assessment_method)   # D-GOP면 '음성인식 결과' 줄을 뺀다
        if note:
            coaching = f"{coaching} {note}"
    if vowel_fb and vowel_fb.get("messages"):
        coaching = f"{coaching} {' '.join(vowel_fb['messages'])}".strip()
    # 회차 상세의 'DOKA의 한마디'용으로 코칭 문장도 시도 기록에 남긴다(채점 기록은 위에서 이미 저장됨)
    if coaching:
        try:
            attempt.coaching = str(coaching)[:600]
            await db.commit()
        except Exception as e:
            await db.rollback()
            print(f"[WARN] coaching save failed: {e}")

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
                       if p.get("aligned") and p.get("scorable") and not p.get("silent_h")],   # 내지 않는 ㅎ은 칩에서 뺀다
        }

    # 판정 보류(S9, docs/scoring-analyses-2026-10.md S14): 문장 하나의 D-GOP 재검사 오차(SEM)가 7.5점이라, 점수가 합격선 ± 1 SEM
    # 안이면 한 번으로는 합격·불합격을 믿기 어렵다. 화면은 '한 번 더 말해 보기'를 권한다. 숙달 계산(passed)은 바꾸지 않는다
    stage_pass = (stg or {}).get("pass") if stg else None
    hold = speak_hold(score, stage_pass, (stg or {}).get("mode"), passed, is_probe)
    return {
        "transcript": transcript,
        "score": score,
        "passed": passed,
        "pass_score": stage_pass,
        "hold": hold,
        "note": note,
        "confusions": confusions[:6],
        "coaching": coaching,
        "assessment_method": assessment_method,  # "dgop" | "asr_transcript" — 축 B 전환 투명성
        "dgop": dgop_result,
        "metrics": metrics,
        "av_fusion": av_fusion,     # 연구용 융합(LIPLAB_AV_FUSION=1)일 때만
        "mouth": mouth,             # 입모양 점수(채점에 섞지 않음) {score, by_phone}. 웹캠을 켠 시도만
        "audio_score": None if audio_score is None else round(float(audio_score), 1),   # 입모양을 섞지 않은 음향 점수
        "acoustic_dgop": acoustic_dgop,
        "vowel_feedback": vowel_fb,   # 축 E: {vowel, f1, f2, target_f1, target_f2, height, front, messages}
        "progress": progress,
        "mode": mode,
        "probe": is_probe,                 # 낱말 속 소리 확인으로 채점했는가(확인 상태·오늘 확인 낱말일 때만)
        "probe_counted": probe_counted,    # 확인 창에 셌는가(소리 없음·정렬 실패면 False)
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
    # 억양 팁은 문장 시도만 본다. 모음 늘이기·음절·단어는 음높이가 고른 게 자연스러워, 전체 평균으로 재면 거의 모두 '평평'이었다.
    sent = [r for r in voiced if r.mode == "sentence"]
    sent_range = sum(r.pitch_range for r in sent) / len(sent) if sent else None
    if len(sent) >= 3 and sent_range < 25:
        tips.append("문장 억양이 평평한 편이에요(폭 %dHz). 문장 끝을 올리고 내리며 억양을 넣어보세요." % round(sent_range))
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
          dependencies=[Depends(ratelimit.rate_limit(20, 60, "llm"))])
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


class RephraseRequest(BaseModel):
    text: str
    situation: str = ""
    level: int = 1


@app.post("/api/conversation/rephrase", dependencies=[Depends(ratelimit.rate_limit(20, 60, "llm"))])
async def conversation_rephrase(request: RephraseRequest, current_user = Depends(get_current_user)):
    """대화 되묻기 '다른 말로'(docs/curriculum-roadmap.md 1-4). 바꾼 문장이 없으면 text None(화면은 '천천히'로 대신한다)."""
    from llm_service import rephrase_turn
    level = min(5, max(1, int(request.level or 1)))
    text = await rephrase_turn(_sanitize_text(request.text, 200), _sanitize_text(request.situation, 80), level)
    return {"text": text}


class SignRequest(BaseModel):
    text: str


@app.post("/api/sign/translate", dependencies=[Depends(ratelimit.rate_limit(20, 60, "llm"))])
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
# 캐시 헤더·조건부 요청(304)·미리 압축한 GLB는 static_serving.py 머리말 참고.
# ============================================
frontend_dist = os.path.join(os.path.dirname(__file__), "frontend", "dist")

if os.path.exists(frontend_dist):
    import static_serving as _static_serving
    _static_serving.mount_frontend(app, frontend_dist)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        reload=False
    )
