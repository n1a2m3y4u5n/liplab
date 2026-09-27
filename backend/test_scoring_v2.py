"""독화 이해 채점 v2(입모양 기준, docs/scoring-v2.md)의 성질.

발음 채점(전사 경로)은 기존 채점(mode 기본값)을 그대로 쓰므로, 기본값의 동작이 바뀌지 않았는지도 함께 본다.
"""
import asyncio

import scoring


def v2(correct, answer):
    return asyncio.run(scoring.calculate_score(correct, answer, mode="visual"))["score"]


def old(correct, answer):
    return asyncio.run(scoring.calculate_score(correct, answer))["score"]


def test_exact_and_spelling_variants_are_full_marks():
    assert v2("물 좀 주세요", "물 좀 주세요") == 100
    assert v2("굳이 가야 해요", "구지 가야 해요") == 100   # 소리가 같으면 표기가 달라도 만점


def test_unrelated_sentence_scores_near_zero():
    # 예전 채점은 관계없는 문장에도 평균 47점(합격선 60을 넘는 경우 10~16%)
    assert v2("케이크가 다 팔렸대요", "다음 역에서 내리세요") < 20
    assert old("케이크가 다 팔렸대요", "다음 역에서 내리세요") > v2("케이크가 다 팔렸대요", "다음 역에서 내리세요")


def test_appended_text_is_penalized():
    base = "영수증 드릴까요"
    assert v2(base, base + " 몸조리 잘하세요") < 70     # 예전에는 덧붙여도 100
    assert old(base, base + " 몸조리 잘하세요") == 100   # 기본값(발음 경로용)은 그대로


def test_same_mouth_shape_substitution_costs_less_than_visible_one():
    same = v2("바다가 넓어요", "마다가 넓어요")    # ㅂ→ㅁ: 입모양이 같다
    diff = v2("바다가 넓어요", "가다가 넓어요")    # ㅂ→ㄱ: 입모양이 다르다
    assert 100 > same > diff


def test_missing_words_lower_the_score_in_order():
    s = "오늘 저녁에 같이 밥 먹을래요"
    one = v2(s, "오늘 저녁에 밥 먹을래요")
    two = v2(s, "오늘 밥 먹을래요")
    assert 100 > one > two > 0


def test_empty_answer_is_zero():
    assert v2("물 좀 주세요", "   ") == 0
