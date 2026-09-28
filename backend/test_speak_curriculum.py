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
    # 프롬프트에 적는 구간도 채점 기준(12~45)과 같아야 한다(예전 15~45)
    soft = next(it for st in S.SPEAK_STAGES for it in st["items"] if it.get("drill") == "soft")
    _ok("12~45" in soft["prompt"], "작게 프롬프트 구간 = 채점 구간")
    _ok(S._score_prosody("soft", {"loudness": 12})[1] is True and S._score_prosody("soft", {"loudness": 45})[1] is True, "작게: 경계 12·45 통과")


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


def test_prosody_uses_semitones_so_voice_pitch_does_not_matter():
    # 같은 15Hz 올림도 남성(120Hz)은 2.0반음, 여성(220Hz)은 1.1반음이다. 반음으로 재면 목소리 높이와 상관없이 같은 기준
    _ok(S._score_prosody("rise", {"pitch_start": 120, "pitch_end": 135})[1] is True, "남성 +15Hz(2.0반음) 통과")
    _ok(S._score_prosody("rise", {"pitch_start": 220, "pitch_end": 235})[1] is False, "여성 +15Hz(1.1반음)는 부족")
    _ok(S._score_prosody("rise", {"pitch_start": 220, "pitch_end": 245})[1] is True, "여성 +25Hz(1.9반음) 통과")
    _ok(S._score_prosody("rise", {"pitch_start": 0, "pitch_end": 200})[1] is False, "음높이를 못 쟀으면 판정하지 않음")
    _ok(abs(S.semitones(150, 165) - S.RISE_FALL_ST) < 0.01, "문턱은 150Hz 목소리의 15Hz")


def test_long_and_voicing_use_sustained_voice_not_recording_length():
    # '아'를 0.4초 내고 2.5초 기다렸다 멈춤: 예전에는 녹음 길이(2.5초)로 '길게' 통과
    m = {"loudness": 70, "duration": 2.5, "voiced_duration": 0.4}
    _ok(S._score_prosody("long", m)[1] is False, "이어 낸 소리가 짧으면 '길게' 실패")
    _ok(S._score_prosody("long", {**m, "voiced_duration": 2.2})[1] is True, "2초 넘게 이어 내면 통과")
    _ok(S._score_prosody("long", {"loudness": 70, "duration": 2.5})[1] is True, "예전 클라이언트(값 없음)는 녹음 길이")
    stg0 = S.SPEAK_STAGES[0]
    _ok(S.score_attempt(0, stg0["items"][0]["target"], None, m)[1] is False, "발성 단계도 이어 낸 길이로")


def test_transcript_path_checks_focus_jamo():
    # 전사 경로 모음·자음 단계: 음운 유사도가 합격선(50)을 넘어도 초점 자모가 다르면 불합격이다.
    # 예전에는 아→이 69.0, 아→우 50.15, 풀→불 91.0, 카→가 91.0, 바→아 70.0이 모두 합격했다(틀린 모음 160/160, 첫소리 162/162).
    m = {"loudness": 50, "voiced_duration": 0.6}
    for st, t, u, sim in [(2, "아", "이", 69.0), (2, "아", "우", 50.15), (3, "풀", "불", 91.0),
                          (3, "카", "가", 91.0), (3, "바", "아", 70.0), (3, "달", "단", 92.0)]:
        score, passed, note = S.score_attempt(st, t, u, m, sim_score=sim)
        _ok(passed is False and note and score == round(sim, 1), f"{t}→{u}: 초점 자모가 달라 불합격, 점수는 그대로")
    _ok("'ㅍ'" in S.score_attempt(3, "풀", "불", m, sim_score=91.0)[2], "안내에 목표 첫소리를 적는다")
    for st, t, u in [(2, "아", "아."), (2, "으", "으"), (3, "탈", "탈"), (3, "마", "마!")]:
        _ok(S.score_attempt(st, t, u, m, sim_score=100.0)[1:] == (True, ""), f"{t}→{u}: 맞게 말하면 그대로 합격")
    # ㅐ와 ㅔ는 같은 소리로 본다(합류 정책 결정 대기)
    _ok(S.score_attempt(2, "애", "에", m, sim_score=90.0)[1] is True, "애→에 합격")
    _ok(S.score_attempt(2, "에", "애", m, sim_score=90.0)[1] is True, "에→애 합격")
    # D-GOP 경로(transcript None)는 판정을 바꾸지 않는다
    _ok(S.score_attempt(3, "풀", None, m, sim_score=91.0)[1:] == (True, ""), "D-GOP 경로는 점수만으로")
    # 단어 단계는 초점 자모를 보지 않는다(점수 판정 그대로)
    _ok(S.score_attempt(4, "밥", "압", m, sim_score=70.0)[1] is True, "4단계는 그대로")


def test_no_voice_recording_fails_on_transcript_path():
    # 프론트가 마이크 문제(micIssue)로 본 녹음도 채점에 온다. Whisper가 무음에서 만든 문장('시청해 주셔서 감사합니다.')이
    # 2단계 8/8, 3단계 9/9, 4단계 223/441 합격했다. 크기 0이거나 이어 낸 소리가 0초면 전사 점수와 상관없이 불합격이다.
    for st in (2, 3, 4, 5):
        t = S.SPEAK_STAGES[st]["items"][0]["target"]
        for m in ({"loudness": 0, "voiced_duration": 0.0}, {"loudness": 0}, {"loudness": 30, "voiced_duration": 0}):
            score, passed, note = S.score_attempt(st, t, "시청해 주셔서 감사합니다.", m, sim_score=100.0)
            _ok((score, passed, note) == (0.0, False, S.NO_VOICE_NOTE), f"{st}단계 {m}: 소리 없음은 불합격")
    _ok(not S.no_voice({}) and not S.no_voice({"loudness": 40, "voiced_duration": None}), "값이 없으면 판정하지 않음")
    _ok(S.score_attempt(4, "밥", None, {"loudness": 0, "voiced_duration": 0}, sim_score=80.0)[1] is True,
        "D-GOP 경로(transcript None)는 그대로")


def test_stage4_order_mixes_syllable_lengths():
    # 예전 고정 순서는 앞 14개가 1음절이라 합격률 0.95 학습자의 93%가 1음절만 말하고 숙달했다(최소 8회, 이동 평균 90).
    items = S.SPEAK_STAGES[4]["items"]
    a = S.mixed_order(items, "1:2026-09-27")
    _ok(sorted(x["target"] for x in a) == sorted(x["target"] for x in items), "풀 전체를 빠짐없이 한 번씩")
    _ok(a == S.mixed_order(items, "1:2026-09-27"), "같은 사용자·같은 날은 같은 순서")
    firsts = {S.mixed_order(items, f"{u}:2026-09-27")[0]["target"] for u in range(20)}
    _ok(len(firsts) > 5, "사용자·날짜가 바뀌면 첫 문항이 바뀐다")
    for u in range(200):
        o = S.mixed_order(items, f"{u}:2026-09-28")
        _ok(all(len(x["target"]) == 1 for x in o[:3]), "처음 3개는 1음절(짧은 것부터)")
        _ok(sum(len(x["target"]) > 1 for x in o[:8]) >= 4, "최소 시도 수(8) 안에 다음절 단어가 4개 이상")
        _ok(any(len(x["target"]) == 3 for x in o[:8]), "3음절도 8개 안에 나온다")
