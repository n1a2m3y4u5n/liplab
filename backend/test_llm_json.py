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


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n{len(tests)}개 테스트 통과")
