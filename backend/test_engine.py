"""
발음 변환(g2p) 엔진 검증 테스트.
독화 앱은 '실제 발화 입모양'이 생명이므로, 철자가 아니라 '소리 나는 대로'의
음절 구조를 만들어야 한다. 아래는 한국어 표준 발음법의 핵심 규칙 중
**입모양(viseme)을 실제로 바꾸는** 것들에 대한 기대값이다.

실행: python3 test_engine.py   (외부 의존성 없음)
"""
from engine import to_pronounced_syllables


def _kor(syllables):
    """한글 음절만 [초, 중, 종] 리스트로 추출 (초성 '' = 무음)"""
    return [s for s in syllables if isinstance(s, (list, tuple))]


CASES = {
    # 겹받침 단순화 (음절 말 자음군 단순화) — 대표음 하나로
    "값":   [["ㄱ", "ㅏ", "ㅂ"]],            # ㅄ → ㅂ
    "닭":   [["ㄷ", "ㅏ", "ㄱ"]],            # ㄺ → ㄱ
    "앉":   [["", "ㅏ", "ㄴ"]],              # 초성 ㅇ 무음, ㄵ → ㄴ

    # 초성 ㅇ 무음화 (소리 없는 초성 ㅇ은 입모양 프레임 없음)
    "아이": [["", "ㅏ", ""], ["", "ㅣ", ""]],

    # 구개음화 (ㄷ·ㅌ + ㅣ/반모음 → ㅈ·ㅊ) — 입모양이 치경→경구개로 바뀜
    "굳이": [["ㄱ", "ㅜ", ""], ["ㅈ", "ㅣ", ""]],   # ㄷ → ㅈ
    "같이": [["ㄱ", "ㅏ", ""], ["ㅊ", "ㅣ", ""]],   # ㅌ → ㅊ

    # 연음 — 받침 + (무음 초성 ㅇ) → 받침이 다음 음절 초성으로 이동
    "밥을": [["ㅂ", "ㅏ", ""], ["ㅂ", "ㅡ", "ㄹ"]],   # 바블
    "옷이": [["", "ㅗ", ""], ["ㅅ", "ㅣ", ""]],        # 오시
    "꽃이": [["ㄲ", "ㅗ", ""], ["ㅊ", "ㅣ", ""]],      # 꼬치
    "한국어": [["ㅎ", "ㅏ", "ㄴ"], ["ㄱ", "ㅜ", ""], ["ㄱ", "ㅓ", ""]],  # 한구거

    # 겹받침 + 모음 → 뒤 자음만 이동, 앞 자음은 종성으로 남음
    "닭이": [["ㄷ", "ㅏ", "ㄹ"], ["ㄱ", "ㅣ", ""]],    # 달기

    # ㅎ 탈락 — 받침 ㅎ + 모음
    "좋아": [["ㅈ", "ㅗ", ""], ["", "ㅏ", ""]],        # 조아

    # 격음화(축약) — 코다 ㅎ + 평음 → 거센소리, 성문음 ㅎ 프레임 제거
    "좋다": [["ㅈ", "ㅗ", ""], ["ㅌ", "ㅏ", ""]],       # 조타
    "많다": [["ㅁ", "ㅏ", "ㄴ"], ["ㅌ", "ㅏ", ""]],     # 만타 (ㄶ → ㄴ 코다 남음)
    "놓고": [["ㄴ", "ㅗ", ""], ["ㅋ", "ㅗ", ""]],       # 노코

    # 격음화 — 코다 평음 + 초성 ㅎ → 다음 초성이 거세짐, ㅎ(성문음 8) 프레임이 양순/연구개로 바뀜
    "입학": [["", "ㅣ", ""], ["ㅍ", "ㅏ", "ㄱ"]],       # 이팍
    "국화": [["ㄱ", "ㅜ", ""], ["ㅋ", "ㅘ", ""]],       # 구콰
    "축하": [["ㅊ", "ㅜ", ""], ["ㅋ", "ㅏ", ""]],       # 추카

    # ㅎ 매개 구개음화 — ㄷ + 히 → 치 (입모양 치경→경구개)
    "닫히다": [["ㄷ", "ㅏ", ""], ["ㅊ", "ㅣ", ""], ["ㄷ", "ㅏ", ""]],  # 다치다

    # 종성 ㅇ[ŋ]은 연음되지 않고 그대로 (초성 ㅇ만 무음)
    "강아지": [["ㄱ", "ㅏ", "ㅇ"], ["", "ㅏ", ""], ["ㅈ", "ㅣ", ""]],

    # ㄶ·ㅀ + 모음 — ㅎ은 발음하지 않고 앞 자음이 넘어감(표준발음법 12항 4). 예전에는 만히·실허였다
    "많이": [["ㅁ", "ㅏ", ""], ["ㄴ", "ㅣ", ""]],                        # 마니
    "싫어": [["ㅅ", "ㅣ", ""], ["ㄹ", "ㅓ", ""]],                        # 시러
    "괜찮아요": [["ㄱ", "ㅙ", "ㄴ"], ["ㅊ", "ㅏ", ""], ["ㄴ", "ㅏ", ""], ["", "ㅛ", ""]],   # 괜차나요

    # 남은 받침 ㅈ·ㅊ → ㄷ (입모양이 경구개에서 치경으로). 예전에는 끝에 ㅈ 입모양이 나왔다
    "꽃": [["ㄲ", "ㅗ", "ㄷ"]],                                          # 꼳
    "몇 시": [["ㅁ", "ㅕ", "ㄷ"], ["ㅅ", "ㅣ", ""]],                     # 멷 시
}


def run():
    passed = 0
    failed = 0
    for word, expected in CASES.items():
        got = _kor(to_pronounced_syllables(word))
        got = [list(s) for s in got]
        if got == expected:
            passed += 1
            print(f"  ✓ {word}: {got}")
        else:
            failed += 1
            print(f"  ✗ {word}: got {got}, expected {expected}")
    print(f"\n{passed} passed, {failed} failed")
    return failed == 0


def test_cases():
    # 예전에는 test_ 함수가 없어 pytest가 이 파일의 기대값을 한 번도 검사하지 않았다
    assert run()


def test_h_deletion_is_viseme_path_only():
    # 채점 라벨 경로(phonetic)는 자체 채점 모델을 학습한 라벨과 맞추려 예전 그대로다(바꾸려면 D-GOP 재평가 뒤)
    assert _kor(to_pronounced_syllables("많이", phonetic=True)) == [["ㅁ", "ㅏ", "ㄴ"], ["ㅎ", "ㅣ", ""]]


if __name__ == "__main__":
    import sys
    sys.exit(0 if run() else 1)


def test_diphthong_frames_glide():
    # 이중모음은 활음 → 모음 두 프레임(와: 원순 4 → 개방 2, 의: ㅡ 5 → ㅣ 3). 서명(word_visemes)은 그대로 9
    import asyncio
    from engine import text_to_visemes
    import content_rules as cr
    assert [f["viseme"] for f in asyncio.run(text_to_visemes("와"))] == [4, 2]
    assert [f["viseme"] for f in asyncio.run(text_to_visemes("의"))] == [5, 3]
    assert [f["viseme"] for f in asyncio.run(text_to_visemes("뭐"))] == [1, 4, 5]
    assert sum(f["duration_ms"] for f in asyncio.run(text_to_visemes("와"))) == 200
    assert cr.word_visemes("와") == [9]


def _spoken(text, **kw):
    """to_pronounced_syllables 결과를 다시 한글 음절 문자열로(비교용)."""
    cho = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
    jung = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
    jong = [""] + list("ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ")
    return "".join(chr(0xAC00 + (cho.index(t[0] or "ㅇ") * 21 + jung.index(t[1])) * 28 + jong.index(t[2]))
                   if isinstance(t, list) else t for t in to_pronounced_syllables(text, **kw))


def test_n_insertion_dictionary():
    # ㄴ 첨가(29항)는 사전에 든 합성어·파생어에만. 시각 기호 경로(phonetic + n_insert)는 표준 발음 그대로 나온다
    full = dict(phonetic=True, h_delete=True, n_insert=True)
    assert _spoken("꽃잎", **full) == "꼰닙" and _spoken("담요", **full) == "담뇨"
    assert _spoken("색연필", **full) == "생년필" and _spoken("나뭇잎", **full) == "나문닙"
    assert _spoken("서울역", **full) == "서울력" and _spoken("유럽여행을", **full) == "유럼녀행을"
    assert _spoken("집안일", **full) == "지반닐" and _spoken("식용유", **full) == "시굥뉴"
    assert _spoken("해야 할 일이", **full) == "해야 할 리리"
    # 입모양 경로(기본값)도 켜진다. 비음화는 같은 입모양이라 하지 않는다(꼳닢의 ㄷ·ㄴ은 모두 치경 6)
    assert _spoken("꽃잎") == "꼳닢" and _spoken("담요") == "담뇨" and _spoken("빨간 꽃잎이") == "빨간 꼳니피"
    import content_rules as cr
    assert cr.word_visemes("꽃잎") == [7, 4, 6, 6, 3, 1] and cr.word_visemes("담요") == [6, 2, 1, 6, 4]
    # 사전에 없는 말은 그대로 연음(뒷요소·받침 조건으로 걸면 틀리던 말들)
    for w, want in (("필요", "피료"), ("금요일", "그묘일"), ("만약", "마냑"), ("생일", "생일"), ("3일", "사밀"),
                    ("월요일", "워료일"), ("목욕", "모굑"), ("상담요청", "상다묘청"), ("할 일정", "할 일정")):
        assert _spoken(w, **full) == want and _spoken(w) == want, w
    # 채점 라벨 경로(phonetic 기본값, D-GOP·jamo_vocab)는 모델을 학습한 라벨과 맞추려 예전 그대로
    assert _spoken("꽃잎", phonetic=True) == "꼬칩" and _spoken("담요", phonetic=True) == "다묘"


def test_n_insertion_dictionary_is_well_formed():
    # 사전의 '|' 뒤 음절은 무음 ㅇ + 이·야·여·요·유, 앞 음절은 받침이 있어야 한다
    from engine import N_INSERT_WORDS, N_INSERT_PHRASES, decompose_hangul
    for w in N_INSERT_WORDS + N_INSERT_PHRASES:
        head, tail = w.split("|")
        ini, med, _ = decompose_hangul(tail[0])
        assert ini == "ㅇ" and med in ("ㅣ", "ㅑ", "ㅕ", "ㅛ", "ㅠ"), w
        assert decompose_hangul(head.strip()[-1])[2], w
