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
    _ok(S.get_phoneme_similarity("ㅂ", "ㅍ") == 0.7, "표에 있는 양순음 쌍(큐레이션 우선)")
    # 표에 없는 자음 쌍 — 같은 입모양(치경)이면 부분점수
    _ok(0.4 <= S.get_phoneme_similarity("ㄹ", "ㅅ") <= 0.65, "같은 입모양 자음은 부분점수")
    # 명백히 다른 입모양(양순 vs 연구개)은 0에 가깝다
    _ok(S.get_phoneme_similarity("ㅂ", "ㄱ") < 0.1, "양순 vs 연구개는 거의 0")


def test_similarity_perceptual_grading():
    # 지각공간(MDS) 폴백이 활성일 때: 시각적으로 닮은 정도가 등급화되어야 한다.
    if not S._CONS_SIM:
        return  # numpy/perceptual_space 없으면 스킵(기존 비심 폴백만 동작)
    same = S.get_phoneme_similarity("ㄹ", "ㅅ")     # 같은 입모양(치경)
    near = S.get_phoneme_similarity("ㄷ", "ㅈ")     # 치경↔경구개(어느 정도 닮음)
    far = S.get_phoneme_similarity("ㅂ", "ㄱ")      # 양순↔연구개(안 닮음)
    _ok(same > near > far, "같은 입모양 > 어느정도 닮음 > 안 닮음 (등급화)")
    _ok(near > 0, "표엔 없지만 시각적으로 닮은 쌍은 0보다 큰 부분점수")


def test_vowel_perceptual_grading():
    # 모음도 지각공간(MDS)에서 도출한 시각 유사도로 등급화된다(예전엔 같은 군이면 일괄 0.5).
    if not S._VOWEL_SIM:
        return  # numpy/perceptual_space 없으면 스킵
    same = S.get_phoneme_similarity("ㅐ", "ㅑ")   # 같은 입모양(개방), 표엔 없음
    far = S.get_phoneme_similarity("ㅏ", "ㅜ")    # 개방 vs 원순폐구, 표엔 없음
    _ok(same > far, "같은 입모양 모음이 다른 입모양 모음보다 시각적으로 가깝다")
    _ok(far < 0.2, "개방↔원순폐구는 시각적으로 거의 안 닮음")


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


def test_viseme_confusions_silent_onset_is_not_velar():
    # 아 vs 바: 초성 ㅇ은 소리가 없어 입모양이 없다. 예전에는 '정답은 연구개음 입모양'이라고 했다
    cf = S.viseme_confusions("아", "바")[0]
    _ok(cf["viseme"] is None and "연구개" not in cf["viseme_name_ko"] and "모음" in cf["viseme_name_ko"], cf)
    _ok(cf["same_viseme"] is False, "없는 자음과 양순음은 다르게 보인다")
    # 가 vs 아: 정답 ㄱ은 연구개음 그대로, 받침 ㅇ([ŋ])도 연구개음 그대로
    _ok(S.viseme_confusions("가", "아")[0]["viseme"] == 7, "정답 ㄱ은 연구개")
    fin = [c for c in S.viseme_confusions("강", "간") if c["position"] == "종성"][0]
    _ok(fin["viseme"] == 7, "받침 ㅇ은 소리가 있다")


def test_viseme_confusions_inside_cluster_is_same():
    # 달 vs 갈: ㄷ(치경)과 ㄱ(연구개)은 입 안쪽 무리라 겉모습이 같다(보기 생성·동형 폼과 같은 기준)
    cf = S.viseme_confusions("달", "갈")[0]
    _ok(cf["same_viseme"] is True and cf["viseme_name_ko"] == S._INSIDE_NAME_KO, cf)
    # 같은 viseme면 그 이름(ㄷ/ㄴ은 둘 다 치경음)
    cf2 = S.viseme_confusions("달", "날")[0]
    _ok(cf2["same_viseme"] is True and cf2["viseme_name_ko"].startswith("치경음"), cf2)
    # 입 안쪽과 입술은 여전히 다르다
    _ok(S.viseme_confusions("달", "발")[0]["same_viseme"] is False, "ㄷ/ㅂ은 다르다")


def test_viseme_confusions_double_final_uses_representative():
    # 닭([닥]) vs 달: 겹받침 ㄺ은 대표음 ㄱ(연구개)으로 본다. 예전에는 중립(15)이었다
    fin = [c for c in S.viseme_confusions("닭", "달") if c["position"] == "종성"][0]
    _ok(fin["viseme"] == 7 and fin["same_viseme"] is True, fin)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n{len(tests)}개 테스트 통과")
