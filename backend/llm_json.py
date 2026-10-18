"""
LLM 응답에서 JSON을 안전하게 추출하는 공용 유틸.

여러 서비스(llm_service·content_gen·conversation_scenario)가 같은 '코드펜스 제거 +
json.loads' 패턴을 5곳에 복붙해 썼다. 빈 응답이나 비어 있는 content 리스트에서 IndexError가
나거나 방어가 제각각이라, 한 곳에 모아 견고성을 공유한다. 순수 함수 — 부수효과 없음.
"""
import json
from typing import Any


def strip_code_fence(text: str) -> str:
    """```json ... ``` 또는 ``` ... ``` 코드펜스를 벗겨 순수 JSON 문자열만 남긴다."""
    t = (text or "").strip()
    if "```json" in t:
        t = t.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in t:
        t = t.split("```", 1)[1].split("```", 1)[0].strip()
    return t


def response_text(resp) -> str:
    """Anthropic 응답 객체의 텍스트 블록을 모두 이어 꺼낸다(빈 content·속성 없음 방어).

    Haiku 5.5·Sonnet 5.5는 생각이 기본으로 켜져 응답이 thinking 블록으로 시작할 수 있다. 예전처럼 첫 블록만 읽으면
    본문을 놓치므로 type이 text인 블록(type 속성이 없는 테스트용 블록 포함)만 모은다."""
    try:
        blocks = getattr(resp, "content", None) or []
        parts = [getattr(b, "text", "") or "" for b in blocks if getattr(b, "type", "text") == "text"]
        return "".join(parts).strip()
    except Exception:
        return ""


def parse_json(text: str) -> Any:
    """코드펜스를 제거하고 JSON을 파싱. 실패 시 json.JSONDecodeError를 그대로 전달한다.

    JSON 앞뒤에 설명 문장이 붙으면 처음 '{'부터 마지막 '}'까지를 한 번 더 시도한다."""
    t = strip_code_fence(text)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        i, j = t.find("{"), t.rfind("}")
        if 0 <= i < j:
            return json.loads(t[i:j + 1])
        raise


def extract_json(resp) -> Any:
    """응답 객체 → 첫 텍스트 블록 → 코드펜스 제거 → JSON 파싱을 한 번에."""
    return parse_json(response_text(resp))
