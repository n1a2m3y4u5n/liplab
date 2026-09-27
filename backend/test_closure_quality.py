"""문맥 추론 문항 품질(9/27 감사, docs/content-routine.md 4절): 강화한 규칙 게이트와 서빙 목록의 회귀 테스트."""
import content_rules as R


def _gate(display, answer, options, hint=None, compound=False):
    return R.check_closure(display, answer, options, hint=hint, compound=compound)


def test_particle_must_agree_with_answer():
    assert not _gate("이 김치는 ___가 좀 싱겁네.", "맛", ["맛", "만", "팥"])[0]        # 맛가
    assert _gate("이 김치는 ___이 좀 싱겁네.", "맛", ["맛", "만", "팥"])[0]
    assert not _gate("국 끓일 때 ___를 조금만 넣어.", "소금", ["소금", "도금", "소급"])[0]
    assert not _gate("두부는 ___로 만들어.", "콩", ["콩", "공", "콕"])[0]             # 콩으로
    assert _gate("두부는 ___으로 만들어.", "콩", ["콩", "공", "콕"])[0]


def test_particle_must_not_reveal_the_answer():
    # ㄹ 받침(솔)만 '로'를 받고 손·놋은 '으로'라 조사만 보고 오답을 지울 수 있었다
    ok, _, why = _gate("___로 이를 닦았더니 개운해", "솔", ["솔", "놋", "손"])
    assert not ok and "조사만" in why
    assert _gate("___로 이를 닦았더니 개운해", "솔", ["솔", "돌", "톨"], hint="이를 닦을 때 쓰는 도구")[0]


def test_spacing_fragment_and_hint_rules():
    assert not _gate("오늘 ___ 이 유난히 밝네.", "달", ["달", "살", "쌀"])[0]
    assert not _gate("저 ___콤한 냄새 좀 맡아봐.", "달", ["달", "탄", "살"])[0]            # 달콤한의 조각
    assert not _gate("___뚜껑이 너무 뜨거워.", "솥", ["솥", "순", "손"])[0]
    assert _gate("___뚜껑이 너무 뜨거워.", "솥", ["솥", "순", "손"], compound=True)[0]  # 사람이 확인한 합성어
    assert not _gate("시험 ___이 틀렸어.", "답", ["답", "탑", "담"], hint="정답과 오답 사이")[0]
    assert _gate("밤새 ___한 보람이 있네!", "공부", ["공부", "동부", "공무"])[0]           # 하다 활용은 허용
    assert _gate("다 네 ___이야, 솔직히 말해.", "탓", ["탓", "탈", "낫"])[0]              # 서술격 조사


def test_served_closures_all_pass_the_gate_and_skip_exclusions():
    import main
    import curriculum
    served = main._training_closures()
    assert len(served) >= 80
    ex = curriculum.CLOSURE_EXCLUDED
    assert not [c["id"] for c in served if c["id"] in ex]
    for c in served:
        ok, _, why = _gate(c["display"], c["answer"], c["options"], hint=c.get("hint"), compound=bool(c.get("compound")))
        assert ok, (c["id"], why)
    ids = {c["id"] for c in curriculum.CLOSURE_ITEMS}
    assert set(ex) <= ids, "제외 목록에 없는 id가 있다"
    # 감사에서 찾은 비단어 오답이 서빙 문항에 남지 않았다
    nonwords = {"터리", "소마", "노바", "나부", "부루", "기라", "컴", "같", "캐", "빼", "짜"}
    assert not [c["id"] for c in served if nonwords & set(c["options"])]
