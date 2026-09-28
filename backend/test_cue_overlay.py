"""
시각 증강 오버레이 검증 테스트 — 고도화 축 J.

동구형이음을 가르는 자질(격음·경음·비음)에만 기호가 붙고, 평음은 기준이라 붙지 않으며,
숙달도(페이딩)·표적 음소로 소거가 되는지 확인한다. 외부 의존성 없음.

실행: python3 test_cue_overlay.py
"""
import cue_overlay as CU


def _ok(cond, msg):
    assert cond, "FAIL: " + msg


def test_phoneme_cue():
    _ok(CU.phoneme_cue("ㅍ") == "aspirated", "격음 → 기식")
    _ok(CU.phoneme_cue("ㅋ") == "aspirated", "ㅋ 격음")
    _ok(CU.phoneme_cue("ㅃ") == "tense", "경음 → 긴장")
    _ok(CU.phoneme_cue("ㅁ") == "nasal", "비음 → 울림")
    _ok(CU.phoneme_cue("ㅂ") is None, "평음은 기준(기호 없음)")
    _ok(CU.phoneme_cue("ㅏ") is None, "모음은 기호 없음")


def test_generate_basic():
    cues = CU.generate_cues("팔")
    _ok(len(cues) == 1 and cues[0]["cue"] == "aspirated", "팔 → ㅍ 기식 1개")
    _ok(CU.generate_cues("밥") == [], "밥은 전부 평음이라 기호 없음")
    # 빵 → ㅃ(경음, 초성) + ㅇ(비음, 종성)
    cues = CU.generate_cues("빵")
    kinds = {(c["position"], c["cue"]) for c in cues}
    _ok(("initial", "tense") in kinds and ("final", "nasal") in kinds, "빵 → 경음+비음")


def test_fade_by_mastery():
    full = CU.generate_cues("빵")
    faded = CU.generate_cues("빵", mastery={1: 0.9})  # 양순음 숙달 → ㅃ 소거
    _ok(len(faded) < len(full), "숙달된 음소 기호는 페이딩으로 소거")
    _ok(all(c["viseme"] != 1 for c in faded), "viseme1 기호가 사라짐")


def test_target_focus():
    cues = CU.generate_cues("나무", target_visemes=[6])  # 치경음만
    _ok(len(cues) == 1 and cues[0]["phoneme"] == "ㄴ", "표적 음소만 남김")


def test_priority_and_cap():
    cues = CU.generate_cues("코끼리를 타고 학교에 갔다")
    _ok(all("priority" in c for c in cues), "각 기호에 우선순위(난이도지수) 부여")
    idxs = [c["syllable_index"] for c in cues]
    _ok(idxs == sorted(idxs), "기호는 타임라인 순 정렬")
    capped = CU.generate_cues("코끼리를 타고 학교에 갔다", max_cues=2)
    _ok(len(capped) <= 2, "max_cues 상한 적용")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n{len(tests)}개 테스트 통과")


def test_cues_follow_actual_pronunciation():
    # 국물[궁물]: 첫 음절 받침이 비음 → 울림 기호. 먹고[먹꼬]: 둘째 음절 초성이 된소리 → 긴장 기호.
    gm = CU.generate_cues("국물")
    assert any(c["syllable_index"] == 0 and c["position"] == "final" and c["cue"] == "nasal" for c in gm)
    mg = CU.generate_cues("먹고")
    assert any(c["syllable_index"] == 1 and c["position"] == "initial" and c["cue"] == "tense" for c in mg)
    # 음절 수는 표기와 같아야 화면 위치와 맞는다
    assert max(c["syllable_index"] for c in gm + mg) <= 1


def test_no_aspiration_cue_for_silent_linking_h():
    # 많이[마니]·싫어요[시러요]: ㄶ·ㅀ + 모음의 ㅎ은 내지 않는다 → 기식 기호가 없어야 한다(예전에는 붙었다)
    import cue_overlay as C
    assert not any(c["cue"] == "aspirated" for c in C.generate_cues("많이"))
    assert not any(c["cue"] == "aspirated" for c in C.generate_cues("싫어요"))
    assert [(c["syllable_index"], c["cue"]) for c in C.generate_cues("많이")] == [(0, "nasal"), (1, "nasal")]
    assert any(c["cue"] == "aspirated" for c in C.generate_cues("좋다"))   # 좋다[조타]의 거센소리는 그대로


def test_n_insertion_cues():
    # 꽃잎[꼰닙]: 예전에는 꼬칲으로 연음해 '기식(ㅊ)' 기호가 붙었다. 이제 받침·초성 ㄴ에 '울림'
    got = [(c["syllable_index"], c["position"], c["phoneme"], c["cue"]) for c in CU.generate_cues("꽃잎")]
    assert got == [(0, "initial", "ㄲ", "tense"), (0, "final", "ㄴ", "nasal"), (1, "initial", "ㄴ", "nasal")]
    assert [(c["syllable_index"], c["phoneme"]) for c in CU.generate_cues("담요")] == [(0, "ㅁ"), (1, "ㄴ")]
    # 사전에 없는 말(만약[마냑])은 그대로
    assert [(c["syllable_index"], c["phoneme"]) for c in CU.generate_cues("만약")] == [(0, "ㅁ"), (1, "ㄴ")]


def test_l_tensification_cues():
    # 할게요[할께요]·할 수[할쑤]: 예전에는 게·수에 '긴장' 기호가 없었다(27항)
    assert (4, "ㄲ", "tense") in [(c["syllable_index"], c["phoneme"], c["cue"]) for c in CU.generate_cues("제가 할게요.")]
    assert (2, "ㅆ", "tense") in [(c["syllable_index"], c["phoneme"], c["cue"]) for c in CU.generate_cues("할 수 있어요.")]
    # 부사형 -게(길게 말해요)에는 붙이지 않는다
    assert not any(c["cue"] == "tense" for c in CU.generate_cues("길게 말해요"))
