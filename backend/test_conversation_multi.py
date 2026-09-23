"""다자 대화(축 H) 테스트 — 화자 순서 섞기, 닮은꼴 오답, 빈칸 턴, 서버 재채점."""
import random

import conversation_scenario as cs
import content_rules as R


def test_speaker_sequence_not_alternating_and_complete():
    rng = random.Random(3)
    for spk in (2, 3):
        for _ in range(20):
            seq = cs.speaker_sequence(spk, 6, rng)
            assert len(set(seq)) == spk, "모든 화자가 나온다"
            assert seq != [i % spk for i in range(6)], "규칙적으로 번갈지 않는다"


def test_lookalike_variants_are_visually_confusable():
    lmap = cs.lookalike_map()
    word = next(w for w in lmap if len(w) >= 2)
    vs = cs.lookalike_variants(f"오늘 {word}를 봤어", lmap, k=3)
    assert vs, "닮은꼴 문장이 만들어져야 한다"
    for v in vs:
        changed = [t for t in v.split() if t not in f"오늘 {word}를 봤어".split()]
        assert changed and R._visually_confusable(word, changed[0][:-1] if changed[0].endswith("를") else changed[0])


def test_closure_turn_uses_context_and_three_options():
    lmap = cs.lookalike_map()
    word = next(w for w, ps in lmap.items() if len(ps) >= 2)
    turns = [{"speaker": 0, "text": "뭐 먹을까?"}, {"speaker": 1, "text": f"{word}를 먹자"}]
    c = cs.closure_turn(turns, lmap, random.Random(1))
    assert c and c["index"] == 1 and "___" in c["display"] and c["answer"] == word
    assert len(c["options"]) == 3 and word in c["options"]


def test_fallback_is_enriched():
    conv = cs.enrich(cs._fallback_conversation(2, 6, "가족 저녁 식사", random.Random(2)), random.Random(2))
    assert len(conv["turns"]) == 6 and all("lookalikes" in t for t in conv["turns"])


def test_score_multi_combines_lipreading_and_context():
    key = {"sp": [0, 1, 1], "tx": ["가", "나", "다"], "cl": "밥"}
    r = cs.score_multi(key, [0, 0, 1], ["가", "x", "다"], "밥")
    assert abs(r["speaker_accuracy"] - 2 / 3) < 1e-3 and abs(r["read_accuracy"] - 2 / 3) < 1e-3
    assert r["closure_correct"] is True and r["combined"] == round(100 * (0.5 * 2 / 3 + 0.5), 1)
    assert r["read_misses"] == ["나"]
    # 빈칸을 안 풀었으면 문맥 점수는 독해 점수로 대신한다
    assert cs.score_multi(key, [], ["가", "나", "x"], None)["combined"] == round(100 * 2 / 3, 1)
