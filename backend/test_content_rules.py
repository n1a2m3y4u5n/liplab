"""
콘텐츠 규칙 게이트 검증 테스트 (고도화 축 G).

LLM 대량 생성물을 거르는 규칙이 음운 근거대로 동작하는지 결정론적으로 확인한다.
비심 엔진만 의존하므로 네트워크·API 키 없이 실행된다.

실행: python3 test_content_rules.py   (외부 의존성 없음)
"""
import content_rules as R


def _ok(cond, msg):
    assert cond, "FAIL: " + msg


def test_word_gate():
    ok, item, _ = R.check_word("사과")
    _ok(ok and item["word"] == "사과", "정상 단어는 통과해야 한다")
    _ok(not R.check_word("apple")[0], "영문은 탈락")
    _ok(not R.check_word("가나다라")[0], "4음절은 기본 범위 밖")
    _ok(not R.check_word("")[0], "빈 문자열 탈락")


def test_compose_and_signature():
    _ok(R.compose_syllable("ㅂ", "ㅏ", "ㅁ") == "밤", "자모→음절 합성")
    _ok(R.compose_syllable("ㅇ", "ㅏ", "") == "아", "무받침 합성")
    _ok(R.compose_syllable("ㅃ", "ㅗ", "ㄹ") is None or isinstance(R.compose_syllable("ㅃ", "ㅗ", "ㄹ"), str),
        "합성은 문자열 또는 None")
    # 밥·맘은 보이는 입모양 순열이 같다(동구형이음)
    _ok(R.viseme_signature("밥") == R.viseme_signature("맘"), "밥/맘 시그니처 동일")
    _ok(R.looks_identical("밥", "맘"), "밥/맘 동구형이음")
    _ok(not R.looks_identical("밥", "달"), "밥/달은 다르게 보임")


def test_lookalike_pair():
    # 동구형이음(시그니처 동일)
    ok, item, _ = R.check_lookalike_pair("밥", "맘")
    _ok(ok and item["relation"] == "homophene" and item["same_looking"], "밥/맘 = homophene, same_looking")
    # 최소대립 + 같은 입모양 무리 → 구별 불가
    ok, item, _ = R.check_lookalike_pair("달", "탈")
    _ok(ok and item["same_looking"], "달/탈 = 같은 입모양(구별 불가)")
    # 최소대립 + 다른 입모양 → 구별 가능
    ok, item, _ = R.check_lookalike_pair("우유", "이유")
    _ok(ok and item["relation"] == "minimal_pair" and not item["same_looking"], "우유/이유 = 구별 가능")
    # 두 자리 이상 다르면 교육쌍 아님
    _ok(not R.check_lookalike_pair("바다", "파도")[0], "바다/파도는 교육쌍 아님")
    _ok(not R.check_lookalike_pair("밥", "밥")[0], "같은 단어 탈락")


def test_candidates_and_discover():
    cands = R.lookalike_candidates("밥")
    _ok("밤" in cands and "팝" in cands, "밥 → 밤·팝 파트너 후보 생성")
    _ok("바" not in cands, "받침 제거는 최소대립 후보가 아님")
    pairs = R.discover_pairs(["밥", "맘", "물", "불", "달", "탈", "살"])
    keys = {frozenset((p["a"], p["b"])) for p in pairs}
    _ok(frozenset(("밥", "맘")) in keys, "discover가 밥/맘 발굴")
    _ok(frozenset(("달", "탈")) in keys, "discover가 달/탈 발굴")
    _ok(all(p["same_looking"] for p in pairs if p["relation"] == "homophene"), "homophene은 항상 same_looking")


def test_closure_gate():
    # 혼동되는 오답 2개(맘·밤 모두 밥과 같은 입모양 [1,2,1]) → 통과
    _ok(R.check_closure("___을 먹었어요", "밥", ["밥", "맘", "밤"])[0], "3지·혼동 오답 2개면 통과")
    # 2지선다는 추측 확률 50%라 탈락
    _ok(not R.check_closure("___을 먹었어요", "밥", ["밥", "맘"])[0], "보기 2개면 탈락")
    # 발은 밥과 최소대립이나 종성 ㅂ(양순1)↔ㄹ(치경6)이 눈에 보임 → 혼동 오답 1개뿐이라 탈락
    _ok(not R.check_closure("___을 먹었어요", "밥", ["밥", "맘", "발"])[0], "시각적으로 안 헷갈리는 오답은 미인정")
    _ok(not R.check_closure("밥을 먹어요", "밥", ["밥", "맘", "밤"])[0], "빈칸 없으면 탈락")
    _ok(not R.check_closure("___를 먹어요", "밥", ["밥", "우유", "구두"])[0], "혼동 안 되는 보기만이면 탈락")


def test_frequency_tier():
    if not R.HAS_FREQUENCY:
        print("  (wordfreq 미설치 → 빈도 테스트 스킵)")
        return
    _ok(R.is_common_word("사과", 3.0) is True, "흔한 단어는 빈도 게이트 통과")
    _ok(R.is_common_word("무름", 2.5) is False, "미등재 비단어는 컷")
    _ok(R.tier_of("사과") == 1, "매우 흔한 단어는 tier 1")
    _ok(R.tier_of("토기") >= 2, "저빈도 단어는 tier 상승")
    ok, item, _ = R.check_word("사과")
    _ok(ok and item["tier"] == 1, "check_word가 빈도 기반 tier를 매긴다")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n{len(tests)}개 테스트 통과")
