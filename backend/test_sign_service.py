"""
sign_service 테스트 — 사전 조회 / 지문자 분해 / gloss 조립(규칙 폴백).
LLM 호출 없이 결정론적으로 검증하기 위해 ANTHROPIC_API_KEY를 제거하고 실행한다.
"""
import os
import asyncio

os.environ.pop("ANTHROPIC_API_KEY", None)  # 규칙기반 폴백 경로 강제

import sign_service as ss


# 영상 URL 해석은 네트워크 I/O이므로 테스트에서는 스텁(hermetic 유지).
async def _no_video(origin_no):
    return None
ss.resolve_video_url = _no_video


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
    # 규칙 폴백: 완전일치만 수어, 나머지는 지문자. "학교"는 등재어(수어), "갔어요"는 지문자.
    result = asyncio.run(ss.translate_to_ksl("학교 갔어요"))
    assert result["method"] == "rule"           # 키 없음 → 규칙 폴백
    by_type = {t["word"]: t["type"] for t in result["tokens"]}
    assert by_type.get("학교") == "sign"
    assert by_type.get("갔어요") == "fingerspell"   # 원형화 안 함 → 정직하게 지문자
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


def test_exact_only_no_conjugation_falsematch():
    # 불규칙 활용형은 '사전에 실재하는 다른 표제어'로 절대 오매칭되면 안 됨(→ None → 지문자).
    # (지었다→지다, 물었다→물다=bite, 나았다→나다 류 오매칭 방지)
    for w in ["지었다", "물었다", "나았다", "들었다", "이었다"]:
        assert ss.lookup_sign(w) is None, f"'{w}'가 오매칭됨"


def test_exact_only_no_noun_overstrip():
    # 조사동형 음절로 끝나는 기본형 명사가 접두 표제어로 오매칭되면 안 됨.
    # '정의'는 사전 미등재 → 조사 '의' 절단해 '정'으로 매칭하면 안 됨(→ None → 지문자).
    assert ss.lookup_sign("정의") is None      # not '정'
    assert ss.lookup_sign("먹이") is None      # not '먹'


def test_exact_match_still_works():
    # 등재 표제어는 그대로 매칭(가요=歌謠도 실재)
    assert ss.lookup_sign("가요") is not None
    assert ss.lookup_sign("학교") is not None


def test_alias_values_are_real_headwords():
    # 별칭표의 동의어는 모두 실제 사전 표제어여야 한다(오매칭 방지).
    idx = ss.load_index()
    for original, syn in ss._ALIASES.items():
        assert syn in idx, f"별칭 '{original}'→'{syn}' 의 동의어가 사전에 없음"


def test_alias_substitution_transparent():
    # '밥'(OOV) → 별칭 '식사' 수어로 표시하되, 원어는 '밥'으로 남기고 signed_as='식사'.
    result = asyncio.run(ss.translate_to_ksl("밥"))
    t = result["tokens"][0]
    assert t["type"] == "sign"          # 지문자 아님 → 별칭 수어로 커버
    assert t["word"] == "밥"             # 원어 유지(사용자 입력)
    assert t.get("signed_as") == "식사"  # 실제 표시 수어는 근접 동의어(투명)


def test_number_to_sign():
    # 아라비아 숫자 → 한국수어 숫자 수어(투명 치환). '3'→셋, 자리별 처리.
    r = asyncio.run(ss.translate_to_ksl("3"))
    t = r["tokens"][0]
    assert t["type"] == "sign" and t["word"] == "3" and t.get("signed_as") == "셋"
    # 여러 자리: '25' → 둘, 다섯 (2자리 각각 수어)
    r2 = asyncio.run(ss.translate_to_ksl("25"))
    assert [tk.get("signed_as") for tk in r2["tokens"]] == ["둘", "다섯"]


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
