"""입모양 후보 발굴의 반복 계산·결과 보존·캐시 상한 회귀."""
import content_rules as R
import curriculum as C


def test_signatures_match_uncached_engine_for_entire_word_bank():
    R.viseme_signature.cache_clear()
    for item in C.WORD_BANK:
        word = item["word"]
        assert R.viseme_signature(word) == tuple(R.word_visemes(word))
    # 외부가 변경할 수 있는 리스트는 캐시에 넣지 않는다.
    result = R.word_visemes("밥")
    result.clear()
    assert R.viseme_signature("밥") == (1, 2, 1)
    R.viseme_signature.cache_clear()


def test_pair_discovery_reuses_each_word_signature():
    R.viseme_signature.cache_clear()
    words = ["밥", "맘", "밤", "발", "달", "탈"]
    first = R.discover_pairs(words)
    # 동구형이음의 visemes 목록 생성은 별개라 시그니처 miss 수로 비교한다.
    assert R.viseme_signature.cache_info().misses == len(words)
    R.discover_pairs(words)
    assert R.viseme_signature.cache_info().misses == len(words)
    assert first == R.discover_pairs(words)
    R.viseme_signature.cache_clear()


def test_signature_cache_evicts_old_entries():
    R.viseme_signature.cache_clear()
    for i in range(2100):
        R.viseme_signature(chr(0xAC00 + i))
    assert R.viseme_signature.cache_info().currsize == 2048
    assert R.viseme_signature("밥") == tuple(R.word_visemes("밥"))
    R.viseme_signature.cache_clear()
