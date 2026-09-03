"""
독화 지각 자원 검증 테스트 — 고도화 축 C(규칙 기반).

동구형이음 사전과 난이도 지수가 비심 규칙대로 나오는지 확인한다. 외부 의존성 없음.
실행: python3 test_perceptual.py
"""
import perceptual as P


def _ok(cond, msg):
    assert cond, "FAIL: " + msg


def test_invisibility():
    _ok(P.invisibility("이") == 0.0, "모음은 잘 보임(안 보이는 정도 0)")
    _ok(P.invisibility("가") > 0.4, "연구개음 ㄱ은 안 보임(안 보이는 정도 높음)")
    _ok(P.invisibility("apple") is None, "한글 아니면 None")


def test_word_difficulty():
    easy = P.word_difficulty("이")
    hard = P.word_difficulty("달")
    _ok(easy["difficulty"] < hard["difficulty"], "잘 보이는 모음 단어가 안 보이는 자음 단어보다 쉬움")
    _ok(0.0 <= easy["difficulty"] <= 1.0, "난이도 범위 0~1")


def test_dictionary():
    d = P.homophene_dictionary()
    _ok("ㅂ" in d["viseme_groups"][1]["phonemes"] and "ㅁ" in d["viseme_groups"][1]["phonemes"],
        "양순음 그룹에 ㅂ·ㅁ")
    _ok(d["viseme_groups"][6]["visibility"] == "low", "치경음은 저가시성")


def test_build_and_neighbors():
    res = P.build_standard_resources(["밥", "맘", "달", "탈", "이", "우유"])
    di = res["difficulty_index"]
    _ok(di[0]["difficulty"] <= di[-1]["difficulty"], "난이도 오름차순 정렬")
    _ok(len(res["lookalike_pairs"]) > 0, "동구형이음/최소대립 쌍 발굴")
    # 밥/맘은 같은 입모양 → 이웃 밀도가 0보다 커야
    bap = next(e for e in di if e["word"] == "밥")
    _ok(bap["neighbor_density"] > 0, "밥은 같은 입모양(맘) 이웃이 있어 밀도 > 0")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n{len(tests)}개 테스트 통과")
