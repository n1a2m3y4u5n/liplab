"""경량 인메모리 레이트리미터 — 고도화 §4.9 보안 대응.

무인증으로도 얻는 데모 토큰으로 Claude(시나리오·대화)·Whisper(발화 채점)를 무제한 호출하면
API 비용이 폭증하고 로그인 무차별 대입에도 노출된다. 프로세스 로컬 슬라이딩 윈도우로 IP·범위별
호출 빈도를 제한한다(외부 의존성 없음).

클라이언트 IP는 신뢰 프록시(Fly.io)가 세팅하는 Fly-Client-IP를 쓴다. X-Forwarded-For 최좌측은
클라이언트가 위조할 수 있어(엣지 프록시는 실제 IP를 XFF 오른쪽에 append) 리미터를 통째로 우회
시킬 수 있으므로 신뢰하지 않는다.

정직: 단일 인스턴스 전제다. 다중 워커/인스턴스에서는 인스턴스별로 카운트되므로 한도가 배가된다.
분산 배포에서 엄밀한 제한이 필요하면 Redis 등 공유 저장소 기반으로 교체해야 한다(데모/프로토타입 보호용).
"""
import time
from collections import defaultdict, deque
from fastapi import Request, HTTPException

_hits = defaultdict(deque)
_MAX_KEYS = 5000    # 추적 key가 이보다 많아지면 오래된(비활성) key를 청소
_MAX_TTL = 300.0    # 최근 활동이 이보다 오래된 key는 제거(모든 window가 60s 이하라 안전)


def _client_key(request: Request) -> str:
    # Fly.io 등 신뢰 프록시가 세팅하는 실제 클라이언트 IP(엣지가 덮어써 클라이언트가 위조 못 함).
    fly = request.headers.get("fly-client-ip")
    if fly:
        return fly.strip()
    # 프록시가 없으면 소켓 peer가 실제 클라이언트. XFF 최좌측은 위조 가능하므로 신뢰하지 않는다.
    return request.client.host if request.client else "unknown"


def _sweep(now: float):
    """추적 key가 상한을 넘으면 최근 활동이 오래된(만료된) key를 제거해 메모리를 회수한다."""
    if len(_hits) <= _MAX_KEYS:
        return
    stale = [k for k, dq in _hits.items() if (not dq) or (now - dq[-1]) > _MAX_TTL]
    for k in stale:
        _hits.pop(k, None)


def rate_limit(max_calls: int, window_sec: float, scope: str = "default"):
    """FastAPI 의존성 팩토리. 같은 클라이언트가 window_sec 동안 scope에서 max_calls를 넘기면 429."""
    async def _dep(request: Request):
        key = (scope, _client_key(request))
        now = time.monotonic()
        dq = _hits[key]
        cutoff = now - window_sec
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= max_calls:
            retry = max(1, int(window_sec - (now - dq[0])))
            raise HTTPException(
                status_code=429,
                detail="요청이 너무 잦습니다. 잠시 후 다시 시도해 주세요.",
                headers={"Retry-After": str(retry)},
            )
        dq.append(now)
        _sweep(now)
    return _dep
