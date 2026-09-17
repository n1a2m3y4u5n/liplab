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


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n{len(tests)}개 테스트 통과")
