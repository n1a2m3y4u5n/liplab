"""
sign_service 테스트 — 사전 조회 / 지문자 분해 / gloss 조립(규칙 폴백).
LLM 호출 없이 결정론적으로 검증하기 위해 ANTHROPIC_API_KEY를 제거하고 실행한다.
"""
import os
import asyncio

os.environ.pop("ANTHROPIC_API_KEY", None)  # 규칙기반 폴백 경로 강제

import sign_service as ss


def test_index_loaded():
    idx = ss.load_index()
    assert len(idx) > 10000, f"인덱스가 너무 작음: {len(idx)}"


def test_lookup_known_words():
    for w in ["학교", "가다", "병원", "사랑", "감사"]:
        sign = ss.lookup_sign(w)
        assert sign is not None, f"'{w}' 조회 실패"
        assert sign["origin_no"], f"'{w}' 표제어번호 없음"
        assert sign["dict_url"].startswith("https://sldict.korean.go.kr"), w


def test_lookup_miss():
    assert ss.lookup_sign("컴퓨터공학과우주정거장") is None


def test_fingerspell():
    assert ss.fingerspell("밥") == [["ㅂ", "ㅏ", "ㅂ"]]
    assert ss.fingerspell("가") == [["ㄱ", "ㅏ"]]
    assert ss.fingerspell("수어") == [["ㅅ", "ㅜ"], ["ㅇ", "ㅓ"]]
    # 비한글 문자는 그대로
    assert ss.fingerspell("AI") == [["A"], ["I"]]


def test_translate_rule_path():
    result = asyncio.run(ss.translate_to_ksl("학교에 갔어요"))
    assert result["method"] == "rule"           # 키 없음 → 규칙 폴백
    words = [t["word"] for t in result["tokens"]]
    assert "학교" in words                        # '학교에'에서 조사 제거 후 매칭
    # 매칭/지문자 카운트 합 = 전체
    cov = result["coverage"]
    assert cov["total"] == cov["matched"] + cov["fingerspelled"]


def test_translate_all_matched():
    result = asyncio.run(ss.translate_to_ksl("병원 사랑 학교"))
    assert result["coverage"]["matched"] == 3
    # 각 수어 토큰은 국립국어원 딥링크와 입모양(viseme)을 포함
    for t in result["tokens"]:
        assert t["type"] == "sign"
        assert t["dict_url"]
        assert isinstance(t["visemes"], list)


def test_fingerspell_fallback_token():
    result = asyncio.run(ss.translate_to_ksl("컴퓨터공학과우주정거장"))
    assert result["tokens"][0]["type"] == "fingerspell"
    assert len(result["tokens"][0]["jamo"]) > 0


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  ✓ {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ✗ {t.__name__}: {e}")
        except Exception as e:
            print(f"  ✗ {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed} passed, {len(tests) - passed} failed")
