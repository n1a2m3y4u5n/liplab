"""
음운론적 채점 검증 — get_phoneme_similarity + calculate_jamo_score.
자모 단위 부분 점수와 시각 유사도 폴백이 의도대로 동작하는지 확인한다. 외부 의존성 없음.
실행: python3 test_scoring.py
"""
import scoring as S
from engine import decompose_hangul


def _ok(cond, msg):
    assert cond, "FAIL: " + msg


def _syl(w):
    return [decompose_hangul(c) for c in w]


def test_similarity():
    _ok(S.get_phoneme_similarity("ㅂ", "ㅂ") == 1.0, "동일 음소 1.0")
    _ok(S.get_phoneme_similarity("ㅂ", "ㅍ") == 0.7, "표에 있는 양순음 쌍")
    _ok(S.get_phoneme_similarity("ㄹ", "ㅅ") == 0.5, "표에 없어도 같은 입모양이면 폴백 0.5")
    _ok(S.get_phoneme_similarity("ㅂ", "ㄱ") == 0.0, "다른 입모양은 0")


def test_jamo_identical():
    _ok(S.calculate_jamo_score(_syl("밥"), _syl("밥"))["score"] == 100.0, "정답과 같으면 100")


def test_jamo_partial_credit():
    near = S.calculate_jamo_score(_syl("밥"), _syl("팝"))["score"]   # 양순음만 다름
    far = S.calculate_jamo_score(_syl("밥"), _syl("국"))["score"]    # 전부 다름
    _ok(near > far, "시각적으로 비슷한 오답이 더 높은 점수")
    _ok(50 < near < 100, "밥→팝은 부분 점수(입모양은 맞고 소리만 다름)")
    _ok(far < 20, "밥→국은 거의 0")


def test_jamo_length_diff():
    r = S.calculate_jamo_score(_syl("사과"), _syl("사"))
    _ok(0.0 <= r["score"] <= 100.0, "음절 수가 달라도 DP 정렬로 채점(범위 내)")


def test_viseme_confusions_same_viseme():
    # 밥 vs 맘: 초성 ㅂ→ㅁ, 종성 ㅂ→ㅁ 모두 양순(같은 입모양) → same_viseme=True
    cf = S.viseme_confusions("밥", "맘")
    _ok(len(cf) >= 1, "밥→맘은 자모 혼동이 잡힌다")
    _ok(all(c["same_viseme"] for c in cf), "ㅂ/ㅁ은 같은 입모양이라 same_viseme=True")
    _ok({c["position"] for c in cf} <= {"초성", "중성", "종성"}, "위치 라벨은 초/중/종성")


def test_viseme_confusions_diff_viseme():
    # 밥 vs 각: 초성 ㅂ(양순)→ㄱ(연구개)은 다른 입모양 → same_viseme=False
    cf = S.viseme_confusions("밥", "각")
    init = [c for c in cf if c["position"] == "초성"]
    _ok(init and init[0]["same_viseme"] is False, "ㅂ→ㄱ은 입모양이 달라 same_viseme=False")


def test_viseme_confusions_identical():
    _ok(S.viseme_confusions("사과", "사과") == [], "정답과 같으면 혼동 없음")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n{len(tests)}개 테스트 통과")
