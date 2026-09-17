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
    """Anthropic 응답 객체에서 첫 텍스트 블록을 안전하게 꺼낸다(빈 content·속성 없음 방어)."""
    try:
        blocks = getattr(resp, "content", None) or []
        if not blocks:
            return ""
        return (getattr(blocks[0], "text", "") or "").strip()
    except Exception:
        return ""


def parse_json(text: str) -> Any:
    """코드펜스를 제거하고 JSON을 파싱. 실패 시 json.JSONDecodeError를 그대로 전달한다."""
    return json.loads(strip_code_fence(text))


def extract_json(resp) -> Any:
    """응답 객체 → 첫 텍스트 블록 → 코드펜스 제거 → JSON 파싱을 한 번에."""
    return parse_json(response_text(resp))
