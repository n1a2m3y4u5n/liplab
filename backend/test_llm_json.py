"""
LLM JSON 추출 유틸 검증. 순수 함수, 외부 의존성 없음.
실행: python3 test_llm_json.py
"""
import json
import llm_json as J


def _ok(cond, msg):
    assert cond, "FAIL: " + msg


class _Block:
    def __init__(self, text):
        self.text = text


class _Typed:
    def __init__(self, type_, text=None):
        self.type = type_
        if text is not None:
            self.text = text


class _Resp:
    def __init__(self, blocks):
        self.content = blocks


def test_strip_fence_variants():
    _ok(J.strip_code_fence('```json\n{"a":1}\n```') == '{"a":1}', "```json 펜스 제거")
    _ok(J.strip_code_fence('```\n{"a":1}\n```') == '{"a":1}', "``` 펜스 제거")
    _ok(J.strip_code_fence('{"a":1}') == '{"a":1}', "펜스 없으면 그대로")


def test_parse_json():
    _ok(J.parse_json('```json\n{"x": [1,2]}\n```') == {"x": [1, 2]}, "펜스+파싱")


def test_response_text_guards():
    _ok(J.response_text(_Resp([])) == "", "빈 content → 빈 문자열(IndexError 방지)")
    _ok(J.response_text(_Resp(None)) == "", "content None → 빈 문자열")
    _ok(J.response_text(object()) == "", "content 속성 없음 → 빈 문자열")
    _ok(J.response_text(_Resp([_Block("  hi  ")])) == "hi", "텍스트 트림")


def test_extract_json_end_to_end():
    resp = _Resp([_Block('```json\n{"sentences": ["가", "나"]}\n```')])
    _ok(J.extract_json(resp) == {"sentences": ["가", "나"]}, "응답 객체 → dict")


def test_invalid_json_raises():
    try:
        J.parse_json("not json at all")
        _ok(False, "잘못된 JSON은 예외를 던져야 함")
    except json.JSONDecodeError:
        _ok(True, "JSONDecodeError 전달")


def test_response_text_skips_thinking_blocks():
    # Haiku 5.5·Sonnet 5.5는 생각이 기본으로 켜져 응답이 thinking 블록으로 시작할 수 있다
    resp = _Resp([_Typed("thinking"), _Typed("text", '{"a": 1}')])
    _ok(J.response_text(resp) == '{"a": 1}', "thinking 블록을 건너뛰고 본문을 읽음")
    _ok(J.extract_json(resp) == {"a": 1}, "thinking 블록 뒤 JSON 파싱")


def test_parse_json_with_surrounding_prose():
    _ok(J.parse_json('다음과 같습니다.\n{"x": 1}\n이상입니다.') == {"x": 1}, "앞뒤 설명 문장이 붙은 JSON")


def test_llm_models_defaults_and_overrides(monkeypatch):
    import llm_models as M
    monkeypatch.delenv("LIPLAB_LLM_FAST", raising=False)
    monkeypatch.delenv("LIPLAB_LLM_QUALITY", raising=False)
    kw = M.request("fast", max_tokens=150, temperature=0.9)
    _ok(kw["model"] == "claude-haiku-5-5" and "temperature" not in kw, "새 세대는 temperature를 보내지 않음")
    _ok(kw["max_tokens"] >= 1024 and kw["output_config"] == {"effort": "low"}, "생각 여유와 effort")
    _ok(M.request("quality", max_tokens=600)["model"] == "claude-sonnet-5-5", "quality 기본값")
    monkeypatch.setenv("LIPLAB_LLM_FAST", "claude-haiku-4-5")
    kw = M.request("fast", max_tokens=150, temperature=0.9)
    _ok(kw == {"model": "claude-haiku-4-5", "max_tokens": 150, "temperature": 0.9}, "되돌리면 예전 인자 그대로")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    tests = [t for t in tests if not t.__code__.co_argcount]   # monkeypatch가 필요한 것은 pytest에서만
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n{len(tests)}개 테스트 통과")
