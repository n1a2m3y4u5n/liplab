"""엄격 음소 정답률(phoneme_accuracy.py, P20 선행): 문서 예시 표, 공백·문장 부호 불변, 낱말 경계 연음, 낱자, 정렬 동등성.
기준 문서는 docs/pilot/typed-scoring-check.md 3절과 9절이다."""
import os
import random

import pytest

import phoneme_accuracy as pa
import scoring
from phoneme_accuracy import strict_phoneme_accuracy as spa


def _acc(t, a, **kw):
    r = spa(t, a, **kw)
    return r["n_matched_phonemes"], r["n_target_phonemes"], r["n_words_correct"], r["n_words"]


# ── 문서 2.2 예시 표(같은 정답·답으로 엄격 정의가 내는 값) ───────────────────────

DOC_TABLE = [
    # (정답, 답, 맞은 음소, 정답 음소, 맞은 어절, 어절)
    ("옷 입어", "옷입어", 5, 5, 2, 2),             # 띄어쓰기 무시
    ("옷 입어", "오시버", 5, 5, 2, 2),             # 철자대로 연음한 소리도 받음
    ("옷 입어", "오디버", 5, 5, 2, 2),             # 표준 발음(대표음 연음). 앱 채점은 96.1점이던 것, 문서 (나)
    ("옷 입어", "옷　입어", 5, 5, 2, 2),       # 전각 공백. 앱 채점은 69.4점이던 것, 문서 (가)
    ("같이 가요", "가치 가요", 7, 7, 2, 2),         # 구개음화
    ("닭이 울어", "달기 울어", 8, 8, 2, 2),         # 겹받침 연음
    ("밥 먹었어", "밥 먹었ㅇ", 7, 9, 1, 2),         # 낱자 ㅇ은 버림(기본값), 셋째 음절 ㅆ·ㅓ를 놓침
    ("사과 주세요", "ㅅㅏ과 주세요", 7, 9, 1, 2),   # 낱자 두 개를 버려 첫 음절이 빠짐
    ("학교에 가요", "가요 학교에", 6, 9, 1, 2),     # 순서를 지키는 정렬이라 한쪽만(R7)
    ("학교에 가요", "학교에 가요 학교에 가요", 9, 9, 2, 2),   # 덧붙인 말은 감점하지 않음(R6)
]


@pytest.mark.parametrize("t,a,m,n,wc,nw", DOC_TABLE)
def test_doc_example_table(t, a, m, n, wc, nw):
    assert _acc(t, a) == (m, n, wc, nw)


def test_return_shape_and_ratios():
    r = spa("학교에 가요", "가요 학교에")
    assert set(r) >= {"phoneme_accuracy", "word_accuracy", "n_target_phonemes", "alignment"}
    assert r["phoneme_accuracy"] == round(6 / 9, 4) and r["word_accuracy"] == 0.5
    assert r["n_extra_syllables"] == 2 and r["scorer_version"] == pa.SCORER_VERSION
    assert r["alignment"] == [
        {"word": "학교에", "key": "학교에", "answer": "학교에", "n": 6, "matched": 6, "correct": True},
        {"word": "가요", "key": "가요", "answer": "--", "n": 3, "matched": 0, "correct": False},
    ]


def test_extra_words_are_counted_but_not_penalized():
    r = spa("학교에 가요", "학교에 가요 학교에 가요")
    assert r["phoneme_accuracy"] == 1.0 and r["n_extra_syllables"] == 5


# ── 분모 정의 ─────────────────────────────────────────────────────

def test_denominator_counts_onset_vowel_coda_without_silent_onset():
    # 아이: 무음 초성 둘 → 모음 2개만. 밥: ㅂ ㅏ ㅂ. 의자: ㅢ(이중모음 한 단위) + ㅈ ㅏ
    assert spa("아이", "아이")["n_target_phonemes"] == 2
    assert spa("밥", "밥")["n_target_phonemes"] == 3
    assert spa("의자", "의자")["n_target_phonemes"] == 3
    # 연음으로 받침이 다음 첫소리가 되면 음소 수는 그대로, 자리만 옮긴다(먹어 = ㅁ ㅓ ㄱ ㅓ)
    assert spa("먹어", "먹어")["n_target_phonemes"] == 4


def test_same_viseme_substitution_is_wrong_in_strict_right_in_visual():
    r = spa("밥", "맙")   # R8
    assert (r["n_matched_phonemes"], r["n_visual_matched"], r["n_target_phonemes"]) == (2, 3, 3)
    assert r["word_accuracy"] == 0.0 and r["visual_phoneme_accuracy"] == 1.0


def test_partial_word_counts_phonemes():
    # R10: 낱말 일부만 맞아도 맞은 음소는 인정
    m, n, wc, _ = _acc("사과 주세요", "사고 주세요")
    assert (m, n, wc) == (8, 9, 1)


def test_empty_answer_and_unknown_answer():
    r = spa("사과 주세요", "")
    assert r["phoneme_accuracy"] == 0.0 and r["word_accuracy"] == 0.0 and r["n_target_phonemes"] == 9
    assert spa("사과 주세요", "  ,. ")["phoneme_accuracy"] == 0.0
    assert spa("사과 주세요", "apple")["phoneme_accuracy"] == 0.0   # R5 영문 0점


def test_empty_target_gives_none():
    r = spa("", "아무 말")
    assert r["phoneme_accuracy"] is None and r["word_accuracy"] is None and r["n_target_phonemes"] == 0


def test_extra_coda_breaks_word_but_not_phoneme_count():
    # 답에만 받침이 더 있으면 정답 음소는 다 맞지만 그 어절은 '정확히 맞음'이 아니다
    r = spa("가요", "각요")
    assert r["phoneme_accuracy"] == 1.0 and r["word_accuracy"] == 0.0


# ── (가) 공백·문장 부호는 결과를 바꾸지 않는다 ──────────────────────────────

SENTENCES = ["옷 입어", "닭 앞에 서 있어", "꽃 위에 앉았어", "같이 가요", "밥 먹었어?", "3시에 만나요", "사과 두 개 주세요."]
SEPARATORS = [" ", "　", " ", "\t", "\n", ",", ".", "!", "?", "~", " , ", "…", "  "]


@pytest.mark.parametrize("sentence", SENTENCES)
def test_answer_whitespace_and_punctuation_do_not_change_result(sentence):
    base = spa(sentence, sentence)
    assert base["phoneme_accuracy"] == 1.0 and base["word_accuracy"] == 1.0
    words = sentence.replace("?", "").replace(".", "").split()
    rng = random.Random(sentence)
    variants = ["".join(words)]
    for sep in SEPARATORS:
        variants.append(sep.join(words))
        variants.append(sep + sep.join(words) + sep)
    # 낱말 안 아무 자리에 공백·부호를 넣어도 같다(답의 띄어쓰기는 무시, R1)
    for _ in range(10):
        chars = list("".join(words))
        k = rng.randrange(1, len(chars))
        chars.insert(k, rng.choice(SEPARATORS))
        variants.append("".join(chars))
    for v in variants:
        r = spa(sentence, v)
        assert (r["n_matched_phonemes"], r["n_target_phonemes"], r["n_words_correct"]) == \
            (base["n_matched_phonemes"], base["n_target_phonemes"], base["n_words_correct"]), repr(v)


@pytest.mark.parametrize("sep", [" ", "　", " ", "\t", ", ", " / "])
def test_target_separator_kind_does_not_change_result(sep):
    for answer in ("오디버", "옷입어", "오비버", "입어"):
        assert spa(sep.join(["옷", "입어"]), answer) == spa("옷 입어", answer)


def test_wrong_answer_also_invariant_to_spacing():
    a = spa("닭 앞에 서 있어", "다가페 서 이써")
    b = spa("닭 앞에 서 있어", "다가 페서이써")
    c = spa("닭 앞에 서 있어", "다가페,서　이써")
    assert a["n_matched_phonemes"] == b["n_matched_phonemes"] == c["n_matched_phonemes"]


def test_nfd_input_is_same_as_nfc():
    import unicodedata
    t, a = "같이 가요", "가치 가요"
    assert spa(unicodedata.normalize("NFD", t), unicodedata.normalize("NFD", a)) == spa(t, a)


# ── (나) 낱말 경계 연음: 표준 발음(대표음)과 철자대로 연음한 소리를 함께 받는다 ─────────────────

@pytest.mark.parametrize("t,answers,key", [
    ("옷 입어", ["오디버", "오시버", "옷 입어", "옷입어"], ["오", "디버"]),
    ("꽃 위에", ["꼬뒤에", "꼬취에", "꽃 위에", "꽃위에"], ["꼬", "뒤에"]),
    ("닭 앞에", ["다가페", "달가페", "닭 앞에", "닭앞에"], ["다", "가페"]),   # 겹받침은 대표음 하나만 옮김(15항 닭 앞에[다가페])
    ("값 없어", ["가법서", "갑섭서", "값 없어", "값없어"], ["가", "법서"]),
])
def test_cross_word_liaison_accepts_standard_and_spelling(t, answers, key):
    for a in answers:
        r = spa(t, a)
        assert r["phoneme_accuracy"] == 1.0 and r["word_accuracy"] == 1.0, (t, a, r["alignment"])
    assert [w["key"] for w in spa(t, answers[0])["alignment"]] == key


def test_cross_word_liaison_denominator_follows_standard():
    # 닭 앞에 → [다가페]: 표준 발음에서는 ㄹ이 빠져 6음소(철자대로 연음한 [달가페]는 7)
    assert spa("닭 앞에", "다가페")["n_target_phonemes"] == 6
    assert spa("닭앞에", "닭앞에")["n_target_phonemes"] == 7   # 한 어절이면 어절 안 연음(엔진 규칙 그대로)


def test_cross_word_liaison_still_rejects_other_consonants():
    r = spa("옷 입어", "오비버")
    assert (r["n_matched_phonemes"], r["n_target_phonemes"]) == (4, 5)
    r = spa("옷 입어", "오이버")   # 연음 자음을 빠뜨림
    assert (r["n_matched_phonemes"], r["n_target_phonemes"]) == (4, 5)


def test_no_liaison_variant_without_vowel_onset_or_with_ieung_coda():
    # 뒤 어절이 자음으로 시작하면 경계 규칙이 없다
    assert [w["key"] for w in spa("밥 먹어", "밥먹어")["alignment"]] == ["밥", "머거"]
    # 받침 ㅇ은 옮기지 않는다
    assert [w["key"] for w in spa("방 안", "방안")["alignment"]] == ["방", "안"]


def test_liaison_moves_phoneme_to_next_word():
    # 발음열 기준이라 '옷'의 ㅅ은 뒤 낱말 첫소리로 센다: 앞 어절은 모음 하나
    r = spa("옷 입어", "오 이버")
    assert [(w["n"], w["matched"], w["correct"]) for w in r["alignment"]] == [(1, 1, True), (4, 3, False)]


# ── (다) 낱자 ────────────────────────────────────────────────────────

def test_loose_jamo_drop_is_default_and_counted():
    r = spa("사과 주세요", "ㅅㅏ과 주세요")
    assert r["loose_jamo"] == "drop" and r["n_loose_jamo"] == 2 and r["phoneme_accuracy"] == round(7 / 9, 4)


def test_loose_jamo_compose_follows_r4():
    assert spa("사과 주세요", "ㅅㅏ과 주세요", loose_jamo="compose")["phoneme_accuracy"] == 1.0
    assert spa("사과 주세요", "ㅅㅏㄱㅘ ㅈㅜㅅㅔㅇㅛ", loose_jamo="compose")["phoneme_accuracy"] == 1.0
    assert spa("사과 주세요", "ㅅㅏㄱㅗㅏ", loose_jamo="compose")["alignment"][0]["correct"] is True   # ㅗ+ㅏ = ㅘ
    # 홀로 친 자음은 모음을 모르는 음절의 첫소리. 앞 받침이 연음돼 ㅆ을 친 것으로 인정(8/9)
    r = spa("밥 먹었어", "밥 먹었ㅇ", loose_jamo="compose")
    assert (r["n_matched_phonemes"], r["n_target_phonemes"]) == (8, 9)
    assert r["alignment"][1]["answer"] == "머거ㅆ"
    # 홀로 친 첫소리 자음
    r = spa("밥", "ㅂ", loose_jamo="compose")
    assert (r["n_matched_phonemes"], r["n_target_phonemes"]) == (1, 3)
    assert spa("밥", "ㅂ")["n_matched_phonemes"] == 0


def test_loose_jamo_bad_mode():
    with pytest.raises(ValueError):
        spa("밥", "밥", loose_jamo="keep")


# ── 숫자, 소리 규칙 선택 ─────────────────────────────────────────────

def test_numbers_read_as_korean():
    assert spa("3시에 만나", "세 시에 만나")["phoneme_accuracy"] == 1.0
    assert spa("사과 2개", "사과 두 개")["phoneme_accuracy"] == 1.0


def test_sound_rules_option_accepts_phonetic_spelling_with_same_denominator():
    plain = spa("국물 줘", "궁물 줘")
    sound = spa("국물 줘", "궁물 줘", sound_rules=True)
    assert plain["n_target_phonemes"] == sound["n_target_phonemes"] == 8
    assert plain["n_matched_phonemes"] == 7 and sound["n_matched_phonemes"] == 8
    assert spa("국물 줘", "국물 줘", sound_rules=True)["phoneme_accuracy"] == 1.0


# ── 정렬은 문서 2.3의 align_visual과 같다(허용 변이가 없을 때) ───────────────────

def test_alignment_matches_align_visual_without_variants():
    rng = random.Random(20261006)
    pool = list("밥맙팝반방가카나다타라마바사자차하오우이에아요워의") + ["닭", "값", "앉", "많", "옷", "꽃", "밭", "삶"]
    for _ in range(400):
        t = "".join(rng.choice(pool) for _ in range(rng.randint(1, 6)))
        a = "".join(rng.choice(pool) for _ in range(rng.randint(0, 7)))
        _, tsyl = pa.target_syllables(t)   # 한 어절이라 경계 변이가 없다
        usyl, _ = pa.answer_syllables(a)
        mine = [(tsyl[i].key if i is not None else None, usyl[j] if j is not None else None)
                for i, j in pa._align(tsyl, usyl)]
        ref = scoring.align_visual(scoring.to_pronounced_jamos(t), scoring.to_pronounced_jamos(a))
        assert mine == ref, (t, a)


def test_app_scoring_is_untouched():
    # 분석 전용 모듈: 앱 서버가 가져오지 않는다
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "main.py"), encoding="utf-8") as f:
        src = f.read()
    assert "phoneme_accuracy import" not in src and "import phoneme_accuracy" not in src
