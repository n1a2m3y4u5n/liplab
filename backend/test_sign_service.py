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
    # 아라비아 숫자 → 한국수어 숫자 수어(투명 치환). '3'→셋
    r = asyncio.run(ss.translate_to_ksl("3"))
    t = r["tokens"][0]
    assert t["type"] == "sign" and t["word"] == "3" and t.get("signed_as") == "셋"
    # 10 이상은 사전의 수 표제어로(9/28 감사 E7). 예전에는 한 자리씩 12→하나+둘, 20→둘+영, 100→하나+영+영이었다
    for num, want in (("12", ["열둘"]), ("20", ["스물"]), ("25", ["스물", "다섯"]), ("100", ["백"]),
                      ("350", ["삼", "백", "오십"]), ("2024", ["이천", "이십", "사"])):
        toks = asyncio.run(ss.translate_to_ksl(num))["tokens"]
        assert [tk.get("signed_as") for tk in toks] == want, num
        assert all(tk["type"] == "sign" and tk["word"] == num for tk in toks), num
    assert asyncio.run(ss.translate_to_ksl("12"))["tokens"][0]["origin_no"] == "10923"
    # 사전 표제어는 비관형형(열둘·스물)이다. 관형형(열두·스무)은 사전에 없다
    assert ss.lookup_number_sign("열두") is None and ss.lookup_number_sign("스무") is None
    # 0으로 시작하거나 17자리 이상(번호)은 한 자리씩
    assert [tk.get("signed_as") for tk in asyncio.run(ss.translate_to_ksl("010"))["tokens"]] == ["영", "하나", "영"]
    assert len(asyncio.run(ss.translate_to_ksl("1" * 17))["tokens"]) == 17


def _signed(text):
    return [tk.get("signed_as") for tk in asyncio.run(ss.translate_to_ksl(text))["tokens"]]


def test_large_numbers_use_unit_signs():
    # 9/29: 5자리 이상 금액은 한 자리씩(10000 → 하나·영·영·영·영) 읽혀 전체 재생에서 같은 영상이 네 번 이어졌다.
    # 만·억·조 단위 수어로 읽고, 사전에 있는 합성(십만·백만)은 한 수어로 보인다.
    for num, want in (("10000", ["만"]), ("10,000", ["만"]), ("50000", ["오", "만"]),
                      ("12345", ["만", "이천", "삼", "백", "사십", "오"]), ("100000", ["십만"]),
                      ("1000000", ["백만"]), ("10000000", ["천", "만"]), ("2500000", ["이", "백", "오십", "만"]),
                      ("100000000", ["억"]), ("300000000", ["삼", "억"]), ("10025", ["만", "이십", "오"])):
        toks = asyncio.run(ss.translate_to_ksl(num))["tokens"]
        assert [tk.get("signed_as") for tk in toks] == want, num
        assert all(tk["type"] == "sign" and tk["word"] == num for tk in toks), num
    assert asyncio.run(ss.translate_to_ksl("10000"))["tokens"][0]["origin_no"] == "10398"   # 개념 > 수 '만'


def test_number_compounds_only_from_number_category():
    # '오만'(교만)·'구조'처럼 숫자와 소리가 같은 다른 뜻 표제어를 합성 수어로 고르면 안 된다
    assert ss.number_sign_parts("50000") == ["오", "만"]
    assert ss._is_number_headword("오십") and not ss._is_number_headword("오만")


def test_decimal_point():
    # 9/29: 규칙 경로가 마침표를 지워 3.5가 35(서른다섯)였다. 소수는 정수 부분 + 소수점 수어 + 한 자리씩
    assert _signed("3.5") == ["삼", "점", "오"]
    assert _signed("0.25") == ["영", "점", "이", "오"]
    assert _signed("12.5") == ["십", "이", "점", "오"]
    toks = asyncio.run(ss.translate_to_ksl("3.5"))["tokens"]
    assert all(t["type"] == "sign" and t["word"] == "3.5" for t in toks)
    assert toks[1]["origin_no"] == "2211"          # 소수점 수어(가게 뜻의 '점' 4908이 아님)
    # 문장 끝 마침표는 예전처럼 지운다
    assert _signed("학교.") == [None]


def test_unicode_digits_do_not_crash():
    # 9/29: '3²'·'①'은 str.isdigit이 참이라 int()에서 500이 났다. 원문자는 숫자로, 위첨자는 제곱으로 읽는다
    r = asyncio.run(ss.translate_to_ksl("3²"))
    assert [(t["word"], t["type"], t.get("signed_as")) for t in r["tokens"]] == [("3", "sign", "셋"), ("²", "fingerspell", "제곱")]
    assert r["tokens"][1]["jamo"] == ss.fingerspell("제곱")
    assert _signed("①") == ["하나"]
    assert _signed("⑩") == ["열"]
    assert _signed("１２") == ["열둘"]
    # 규칙 경로에서 숫자로 시작하는 어절은 숫자와 나머지로 나눈다
    assert [(t["word"], t["type"]) for t in asyncio.run(ss.translate_to_ksl("3시에"))["tokens"]][0] == ("3", "sign")
    # 숫자 비슷한 다른 글자는 500 없이 지문자(글자 그대로)로
    for text in ("x⁴", "❶", "⑴", "٣", "²", "3.5.1", "1,2", "10,000원", "𝟑"):
        r = asyncio.run(ss.translate_to_ksl(text))
        assert r["coverage"]["total"] == len(r["tokens"]) > 0, text


def test_zero_is_number_sign():
    # 0도 숫자 수어(영, 개념>수 카테고리 origin 1214)로 나와야 한다(지문자 아님).
    r = asyncio.run(ss.translate_to_ksl("0"))
    zero = r["tokens"][0]
    assert zero["type"] == "sign" and zero["word"] == "0" and zero.get("signed_as") == "영"
    assert zero["origin_no"] == "1214"          # 천주교 동형어(17688)가 아닌 숫자 0
    # 동형어 중 '수' 카테고리를 골랐는지 직접 확인
    assert ss.lookup_number_sign("영")["origin_no"] == "1214"


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


def test_lookup_prefers_daily_life_sign():
    """9/27 감사: 동형어의 첫 항목이 전문용어 수어여도 일상생활 수어를 고른다."""
    import sign_service as S
    idx = S.load_index()
    for w in ("나무", "불", "시험", "친구", "산", "풀"):
        got = S.lookup_sign(w)
        cat = next(e["category"] for e in idx[w] if e["origin_no"] == got["origin_no"])
        assert cat.startswith("일상생활"), (w, cat)
    assert S._ALIASES["자동차"] == "승용차" and S.lookup_sign("승용차")["origin_no"] == "6956"
