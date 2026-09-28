"""학습 콘텐츠 품질(9/28 감사, docs/content-audit-2026-09-28.md): 감사 스크립트의 불변 조건과 사람이 고친 항목의 회귀 테스트."""
import importlib.util
import os
import re

import content_rules as R
import curriculum as C

_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "content_audit.py")


def _audit():
    spec = importlib.util.spec_from_file_location("content_audit", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_audit_script_finds_no_invariant_violations():
    # 짝 관계·같아 보임 표시, 서빙 문항의 거의 같은 문장·문장 부호, 대화 대체 대사의 길이·되풀이, 억양 표시를 한 번에 본다
    mod = _audit()
    assert mod.errors(mod.run()) == {}


def test_every_pair_is_one_jamo_minimal_pair_or_homophene():
    # 최소대립쌍은 자모 한 자리만 다르고, 두 자리 이상 다른 짝은 보이는 입모양 열이 완전히 같은 동구형이음(밥/맘)이어야 한다
    for p in C.MINIMAL_PAIRS:
        a, b, rel = p["a"], p["b"], p.get("relation")
        sa, sb = R._jamo_seq(a), R._jamo_seq(b)
        dist = sum(x != y for x, y in zip(sa, sb)) if len(sa) == len(sb) else None
        if rel == "minimal_pair":
            assert dist == 1, (a, b, dist)
        else:
            assert rel == "homophene" and R.looks_identical(a, b), (a, b, rel)


def _served():
    import main
    return main._training_closures()


def test_distractors_that_also_fit_the_sentence_are_gone():
    # 사람이 읽고 찾은 '오답도 문장에 맞는' 틀(오답, 문장 틀). 문항을 고치거나 빼서 서빙 문항에 다시 나오면 안 된다.
    #   맘을 먹었어요(마음먹다), 다쳐서 판을 못 들었어, 콩을 던져요, 박물관에서 토끼를 만져 봤어, 도끼로 만든 컵,
    #   밤새 공모했어
    fits = [("맘", r"^___을 먹었"), ("판", r"___을 못 들었"), ("콩", r"___을 던져"), ("토끼", r"___를 직접 만져"),
            ("도끼", r"___로 만든"), ("공모", r"밤새 ___했")]
    for c in _served():
        for o in c["options"]:
            if o == c["answer"]:
                continue
            for word, frame in fits:
                assert not (o == word and re.search(frame, c["display"])), (c["id"], c["display"], o)
    # 정답 자체가 두 뜻으로 읽히던 문항: '오늘 날 잡아줄 수 있어?'의 날은 '나를'로도 읽혔다
    assert not [c["id"] for c in _served() if c["answer"] == "날" and re.search(r"___ 잡아", c["display"])]


def test_grammar_only_and_unnatural_items_stay_out():
    # 정답만 조사·부사·관형사라 문법으로 오답이 지워지는 문항, 어색한 문장, 드문 정답은 서빙하지 않는다
    served = {c["id"] for c in _served()}
    for cid in ("g648d50e8", "g9ddb8924", "g1ef83cef", "g23bea801", "gd33b667f", "g27346a63", "g160a2043", "g93c85579", "g32", "g55"):
        assert cid in C.CLOSURE_EXCLUDED and cid not in served, cid
    # 비단어·품사가 다른 오답(콕·탄·만)을 실단어로 바꾼 문항
    by_id = {c["id"]: c for c in C.CLOSURE_ITEMS}
    assert "콕" not in by_id["g38"]["options"] and "탄" not in by_id["g42"]["options"] and "만" not in by_id["g3"]["options"]
    assert len(served) >= 80


def test_fallback_turns_fit_level_and_do_not_repeat_early():
    import llm_service as L
    for sit in list(L.FALLBACK_TURNS) + ["목록에 없는 상황"]:
        lines = L.FALLBACK_TURNS.get(sit) or L.FALLBACK_TURNS_GENERIC
        for lv in (1, 2, 3, 4, 5):
            n_fit = sum(1 for t in lines if L.conv_turn_ok(t, lv))
            assert n_fit >= 4, (sit, lv, n_fit)
            hist, said = [], []
            for _ in range(n_fit):
                t = L.fallback_turn(sit, lv, hist)
                assert L.conv_turn_ok(t, lv), (sit, lv, t)
                said.append(t)
                hist += [{"role": "assistant", "content": t}, {"role": "user", "content": "(학습자가 읽은 글)"}]
            assert len(set(said)) == n_fit, (sit, lv, said)
            # 다 쓴 뒤에는 가장 오래전 대사부터 다시
            assert L.fallback_turn(sit, lv, hist) == said[0]


def test_lookalike_map_skips_rare_and_test_words():
    import assessment as A
    import conversation_scenario as cs
    skip = set(A.test_only_words()) | set(C.STAGE2_EXCLUDED)
    lmap = cs.lookalike_map()
    assert lmap
    assert not skip & set(lmap), sorted(skip & set(lmap))[:5]
    assert not skip & {w for ps in lmap.values() for w in ps}


def test_tier_one_means_everyday_word():
    # 빈도 사전이 한 음절 동형이의어나 문어를 등급 1로 올린 말은 내렸고, 아이들도 아는 구체 명사는 올렸다
    tier = {w["word"]: w["tier"] for w in C.WORD_BANK}
    for w in ("공학", "보스", "선발", "사상", "톤", "기사", "곡", "도", "만"):
        assert tier[w] >= 2, w
    for w in ("달", "발", "불", "강아지", "우산", "의자", "연필"):
        assert tier[w] == 1, w
    for w in ("공책", "지우개", "젓가락"):
        assert tier[w] <= 2, w


def test_new_rare_words_leave_stage2_and_speaking_pools():
    import speak_curriculum as S
    pool = {it["target"] for it in S._BY_STAGE[4]["items"]}
    for w in ("공무", "사당", "축", "룸", "팝", "탄"):
        assert w in C.STAGE2_EXCLUDED and w not in pool, w
