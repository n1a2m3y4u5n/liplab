"""
한글 → 촉각(타도마) 시퀀스 변환 검증. 하드웨어(아두이노 얼굴 모형)가 그대로 재현하는
값이므로 규칙이 흔들리면 안 된다. 순수 함수, 외부 의존성 없음.
실행: python3 test_tactile.py
"""
import tactile as T


def _ok(cond, msg):
    assert cond, "FAIL: " + msg


def test_silent_initial_ieung_skipped():
    # 초성 ㅇ은 무음 → 생략, 중성만 남음
    seq = T.text_to_tactile("아")
    _ok(len(seq) == 1 and seq[0]["label"] == "ㅏ", "초성 ㅇ은 생략, 모음만")


def test_final_ieung_kept():
    # 종성 ㅇ[ŋ]은 유지 (초성 ㅇ만 생략)
    labels = [s["label"] for s in T.text_to_tactile("강")]
    _ok(labels == ["ㄱ", "ㅏ", "ㅇ"], "종성 ㅇ은 유지")


def test_vowel_always_voiced():
    for s in T.text_to_tactile("가나다라"):
        if s["label"] in T.JUNG:
            _ok(s["voicing"] == 1, "모음은 항상 유성(voicing=1)")


def test_airflow_classes():
    # 파열음/마찰음 분류가 사양대로 나오는지
    ba = [s for s in T.text_to_tactile("바") if s["label"] == "ㅂ"][0]
    sa = [s for s in T.text_to_tactile("사") if s["label"] == "ㅅ"][0]
    _ok(ba["airflow"] == "plosive", "ㅂ은 파열")
    _ok(sa["airflow"] == "fricative", "ㅅ은 마찰")


def test_rounded_vs_flat_lip():
    gu = [s for s in T.text_to_tactile("구") if s["label"] == "ㅜ"][0]
    gi = [s for s in T.text_to_tactile("기") if s["label"] == "ㅣ"][0]
    _ok(gu["lip"] == 1, "ㅜ는 원순(lip=1)")
    _ok(gi["lip"] == 0, "ㅣ는 평순(lip=0)")


def test_space_and_non_hangul():
    seq = T.text_to_tactile(" a1!")
    _ok(len(seq) == 1 and seq[0]["label"] == "(쉼)", "공백=쉼, 영문·숫자·기호는 무시")


def test_durations_honored():
    seq = T.text_to_tactile("가", cons_ms=99, vowel_ms=77)
    _ok(seq[0]["duration_ms"] == 99 and seq[1]["duration_ms"] == 77, "지속시간 인자 반영")


def test_value_ranges():
    for s in T.text_to_tactile("안녕하세요 반갑습니다"):
        _ok(0 <= s["jaw"] <= 20, "jaw 0~20")
        _ok(s["lip"] in (0, 1), "lip 0/1")
        _ok(s["voicing"] in (0, 1), "voicing 0/1")
        _ok(s["airflow"] in ("none", "plosive", "fricative"), "airflow 3분류")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n{len(tests)}개 테스트 통과")
