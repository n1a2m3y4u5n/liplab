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


def test_phoneme_accuracy_alignment():
    # 첫 음절 누락(삽입/삭제) 시 이후 음절이 밀려도 정렬로 올바르게 채점돼야 함.
    # (버그: 위치기반 zip이면 전 음절이 어긋나 phoneme_accuracy가 전부 0%가 됨)
    r = S.calculate_jamo_score(S.to_pronounced_jamos("안녕하세요"),
                               S.to_pronounced_jamos("녕하세요"))
    _ok(r["score"] == 80.0, "5음절 중 1음절 누락 = 80점")
    pa = r["phoneme_accuracy"]
    _ok(pa["initial"] > 50, "나머지 4음절 초성은 맞았으므로 초성 정확도가 0이 아님")
    _ok(pa["medial"] > 50, "중성 정확도도 0이 아님")


def test_pronounced_scoring():
    # 아바타가 '구지'로 보여주는 '굳이' — 읽은 대로 '구지'라 적어도 100점(발음형 정규화).
    both = S.calculate_jamo_score(S.to_pronounced_jamos("굳이"),
                                  S.to_pronounced_jamos("구지"))["score"]
    _ok(both == 100.0, "굳이(정답)와 구지(입력)는 발음이 같으므로 100점")
    same = S.calculate_jamo_score(S.to_pronounced_jamos("같이"),
                                  S.to_pronounced_jamos("가치"))["score"]
    _ok(same == 100.0, "같이/가치도 동일 발음 → 100점")


def test_error_visemes_alignment():
    # 정답을 발음대로 맞히면 오류 비심이 없어야 하고, 무음 초성 ㅇ이 가짜 오류를 만들지 않아야 함.
    r = S.calculate_jamo_score(S.to_pronounced_jamos("굳이"), S.to_pronounced_jamos("구지"))
    ev = S.error_visemes_from_alignment(r["alignment"])
    _ok(ev == [], "발음이 일치하면 오류 비심 없음(허위 오류 0)")
    # 결정론적 순서
    r2 = S.calculate_jamo_score(_syl("밥"), _syl("국"))
    a = S.error_visemes_from_alignment(r2["alignment"])
    b = S.error_visemes_from_alignment(r2["alignment"])
    _ok(a == b, "오류 비심 순서는 호출마다 동일(결정론)")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n{len(tests)}개 테스트 통과")
