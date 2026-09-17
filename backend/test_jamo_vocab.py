"""
자모 CTC vocab 검증 — 축 A 학습 라벨의 무결성.

라벨이 발음과 어긋나거나 vocab을 벗어나면 $50어치 GPU 시간이 통째로 날아간다.
학습 시작 전에 이 테스트가 통과해야 한다.

실행: PYTHONPATH=. python3 test_jamo_vocab.py
"""
import jamo_vocab as V

def _ok(cond, msg):
    assert cond, "FAIL: " + msg


def test_vocab_shape():
    _ok(V.VOCAB_SIZE == 49, f"49토큰이어야 함 (실제 {V.VOCAB_SIZE})")
    _ok(V.VOCAB[V.PAD] == 0, "CTC blank(<pad>)는 id 0 — align_targets 기본값과 맞아야 함")
    _ok(len(set(V.VOCAB.values())) == V.VOCAB_SIZE, "id 중복 없음")
    _ok(len(V.CODAS) == 7, "phonetic 모드는 7종성으로 수렴")
    _ok('ㅇ' not in V.ONSETS, "무음 초성 ㅇ은 토큰이 아니다")


def test_position_distinguished():
    """초성 ㄱ과 종성 ㄱ은 서로 다른 토큰(미파열음은 다른 소리)."""
    ids = V.text_to_ids("각")
    _ok(V.VOCAB["o:ㄱ"] != V.VOCAB["c:ㄱ"], "초성 ㄱ ≠ 종성 ㄱ")
    _ok(ids[0] != ids[-1], "'각'의 첫·끝 토큰 id가 달라야 함")


def test_phonetic_rules_reach_labels():
    """발음 규칙이 라벨까지 실제로 반영되는가 — 축 A의 핵심 전제."""
    _ok(V.text_to_tokens("국물") == ["o:ㄱ", "n:ㅜ", "c:ㅇ", "o:ㅁ", "n:ㅜ", "c:ㄹ"],
        f"국물 → 궁물 (얻은 값 {V.text_to_tokens('국물')})")
    _ok("o:ㄲ" in V.text_to_tokens("학교"), "학교 → 학꾜 (경음화)")
    _ok("c:ㄷ" in V.text_to_tokens("옷"), "옷 → 옫 (평파열음화)")


def test_word_delimiter():
    toks = V.text_to_tokens("밥 먹자")
    _ok(toks.count(V.WORD_DELIM) == 1, "어절 사이에 구분자 1개")
    _ok(not toks[0] == V.WORD_DELIM and not toks[-1] == V.WORD_DELIM, "앞뒤에는 붙지 않음")
    _ok(not V.is_scorable(V.WORD_DELIM), "구분자는 D-GOP 채점 대상이 아님")
    _ok(V.is_scorable("o:ㄱ"), "자모 토큰은 채점 대상")


def test_no_oov_on_real_corpus():
    """앱이 실제로 쓰는 전체 콘텐츠에서 OOV가 0건이어야 한다."""
    import curriculum as c
    texts = [w["word"] for w in c.WORD_BANK]
    texts += [m["a"] for m in c.MINIMAL_PAIRS] + [m["b"] for m in c.MINIMAL_PAIRS]
    texts += [i.get("sentence") or i.get("answer") or "" for i in c.CLOSURE_ITEMS]
    bad = {t: V.oov_tokens(t) for t in texts if t and V.oov_tokens(t)}
    _ok(not bad, f"OOV 발생: {list(bad.items())[:5]}")


def test_ids_roundtrip():
    toks = V.text_to_tokens("안녕하세요")
    ids = V.tokens_to_ids(toks)
    _ok([V.ID_TO_TOKEN[i] for i in ids] == toks, "토큰 ↔ id 왕복 일치")
    _ok(V.VOCAB[V.UNK] not in ids, "정상 문장에 UNK가 섞이면 안 됨")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n{len(tests)}개 테스트 통과")
