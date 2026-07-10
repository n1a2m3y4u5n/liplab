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

    # 연음 — 받침 + (무음 초성 ㅇ) → 받침이 다음 음절 초성으로 이동
    "밥을": [["ㅂ", "ㅏ", ""], ["ㅂ", "ㅡ", "ㄹ"]],   # 바블
    "옷이": [["", "ㅗ", ""], ["ㅅ", "ㅣ", ""]],        # 오시
    "꽃이": [["ㄲ", "ㅗ", ""], ["ㅊ", "ㅣ", ""]],      # 꼬치
    "한국어": [["ㅎ", "ㅏ", "ㄴ"], ["ㄱ", "ㅜ", ""], ["ㄱ", "ㅓ", ""]],  # 한구거

    # 겹받침 + 모음 → 뒤 자음만 이동, 앞 자음은 종성으로 남음
    "닭이": [["ㄷ", "ㅏ", "ㄹ"], ["ㄱ", "ㅣ", ""]],    # 달기

    # ㅎ 탈락 — 받침 ㅎ + 모음
    "좋아": [["ㅈ", "ㅗ", ""], ["", "ㅏ", ""]],        # 조아

    # 종성 ㅇ[ŋ]은 연음되지 않고 그대로 (초성 ㅇ만 무음)
    "강아지": [["ㄱ", "ㅏ", "ㅇ"], ["", "ㅏ", ""], ["ㅈ", "ㅣ", ""]],
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


if __name__ == "__main__":
    import sys
    sys.exit(0 if run() else 1)
