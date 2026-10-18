"""
Claude 모델 이름과 모델별 요청 인자를 한 곳에서 정한다.

예전에는 모델 문자열이 llm_service·content_gen·content_pipeline·conversation_scenario·sign_service에 따로 박혀 있어
세대를 바꿀 때마다 다섯 파일을 고쳐야 했다. 두 등급만 둔다.
  - fast: 대화 턴·되묻기·발음 코칭·듣기 문항처럼 학습자가 기다리는 짧은 호출
  - quality: 시나리오 문장·단어/문장 출제·다자 대화·수어 gloss·단어 판정
환경변수 LIPLAB_LLM_FAST, LIPLAB_LLM_QUALITY로 코드 수정 없이 바꾸거나 되돌린다(예: claude-haiku-4-5, claude-sonnet-4-6).

세대마다 받는 인자가 다르다(2026-10-18 기준).
  - Haiku 5.5·Sonnet 5.5: temperature·top_p·top_k를 기본값이 아닌 값으로 보내면 400이다. 생각(adaptive thinking)이
    기본으로 켜져 응답 앞에 thinking 블록이 올 수 있고, 생각도 max_tokens에 들어간다. 그래서 temperature는 빼고
    effort를 low로 두며, max_tokens에 생각할 여유를 더한다. 변주는 이미 프롬프트의 무작위 시드·변주 축이 맡는다.
  - 4.x 세대(되돌릴 때): 예전과 같이 temperature를 그대로 보내고 effort는 보내지 않는다(Haiku 4.5는 effort를 받지 않는다).
"""
import os
from typing import Optional

DEFAULT_FAST = "claude-haiku-5-5"
DEFAULT_QUALITY = "claude-sonnet-5-5"

# 생각이 기본으로 켜진 모델에서 max_tokens 하한. 짧은 답(120~200토큰)만 두면 생각에 다 써서 본문 없이 끝날 수 있다.
# 상한일 뿐이라 실제 쓴 토큰만 과금된다.
_THINKING_MIN_MAX_TOKENS = 1024


def fast_model() -> str:
    return (os.getenv("LIPLAB_LLM_FAST") or "").strip() or DEFAULT_FAST


def quality_model() -> str:
    return (os.getenv("LIPLAB_LLM_QUALITY") or "").strip() or DEFAULT_QUALITY


def is_legacy(model: str) -> bool:
    """temperature를 받고 생각이 기본으로 꺼진 예전 세대(Claude 3·4.x)인가."""
    m = (model or "").lower()
    return m.startswith("claude-3") or any(m.startswith(f"claude-{f}-4") for f in ("haiku", "sonnet", "opus"))


def request(tier: str, max_tokens: int, temperature: Optional[float] = None, effort: str = "low") -> dict:
    """messages.create에 펼쳐 넣을 model·max_tokens와 모델별 추가 인자.

    tier는 "fast" 또는 "quality". temperature는 예전 세대에만 보낸다."""
    model = fast_model() if tier == "fast" else quality_model()
    if is_legacy(model):
        kw = {"model": model, "max_tokens": max_tokens}
        if temperature is not None:
            kw["temperature"] = temperature
        return kw
    return {"model": model, "max_tokens": max(max_tokens, _THINKING_MIN_MAX_TOKENS),
            "output_config": {"effort": effort}}
