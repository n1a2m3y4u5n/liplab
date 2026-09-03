"""
발화(말하기) 커리큘럼 채점 규칙 검증 — 임계값 로직이 많아 회귀에 취약하다.
순수 함수(외부 의존성 없음). 실행: python3 test_speak_curriculum.py
"""
import speak_curriculum as S


def _ok(cond, msg):
    assert cond, "FAIL: " + msg


def test_prosody_loud():
    _ok(S._score_prosody("loud", {"loudness": 60})[1] is True, "크게: 60이면 통과")
    _ok(S._score_prosody("loud", {"loudness": 30})[1] is False, "크게: 30이면 실패")


def test_prosody_soft_band():
    _ok(S._score_prosody("soft", {"loudness": 30})[1] is True, "작게: 12~45 범위면 통과")
    _ok(S._score_prosody("soft", {"loudness": 60})[1] is False, "작게: 너무 크면 실패")
    _ok(S._score_prosody("soft", {"loudness": 5})[1] is False, "작게: 거의 무음도 실패")


def test_prosody_long():
    _ok(S._score_prosody("long", {"duration": 2.0})[1] is True, "길게: 2초면 통과")
    _ok(S._score_prosody("long", {"duration": 1.0})[1] is False, "길게: 1초면 실패")


def test_prosody_rise_fall():
    _ok(S._score_prosody("rise", {"pitch_start": 100, "pitch_end": 120})[1] is True, "올림: +20 통과")
    _ok(S._score_prosody("rise", {"pitch_start": 100, "pitch_end": 108})[1] is False, "올림: +8 실패")
    _ok(S._score_prosody("fall", {"pitch_start": 120, "pitch_end": 100})[1] is True, "내림: -20 통과")
    _ok(S._score_prosody("fall", {"pitch_start": 100, "pitch_end": 120})[1] is False, "내림인데 올라가면 실패")


def test_voicing_stage():
    # 0단계 voicing: 충분히 크고(>=22) 길게(>=1.2초)면 통과
    _ok(S.score_attempt(0, "아", None, {"loudness": 40, "duration": 1.5})[1] is True, "발성: 크고 길면 통과")
    _ok(S.score_attempt(0, "아", None, {"loudness": 10, "duration": 1.5})[1] is False, "발성: 소리 약하면 실패")


def test_phoneme_word_pass_thresholds():
    # 2단계 phoneme pass=50, 4단계 word pass=65
    _ok(S.score_attempt(2, "가", "가", {}, sim_score=70)[1] is True, "음소: 70이면 통과(임계 50)")
    _ok(S.score_attempt(2, "가", "카", {}, sim_score=40)[1] is False, "음소: 40이면 실패")
    _ok(S.score_attempt(4, "사과", "사과", {}, sim_score=70)[1] is True, "단어: 70이면 통과(임계 65)")
    _ok(S.score_attempt(4, "사과", "수박", {}, sim_score=60)[1] is False, "단어: 60이면 실패(임계 65)")


def test_unknown_stage_falls_back_to_sim():
    score, passed, _ = S.score_attempt(999, "x", "x", {}, sim_score=80)
    _ok(score == 80.0 and passed is True, "미지 단계는 sim_score로 폴백")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n{len(tests)}개 테스트 통과")
