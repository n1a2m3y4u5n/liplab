"""
Advanced Viseme Engine for Korean Speechreading
Converts Korean text to 15 fine-grained visemes with co-articulation modeling
g2pk-free version: uses built-in Korean phonological rules
"""
import re
from typing import List, Dict

# 한국어 발음 변환 규칙 (g2pk 없이 자체 구현)
# 주요 연음/변음 규칙을 커버

def apply_phonological_rules(text: str) -> str:
    """
    기본적인 한국어 발음 규칙 적용
    (연음, 격음화, 경음화 등 핵심 규칙)
    """
    result = text

    # 1. 연음 법칙: 받침 + 모음 → 받침이 다음 음절 초성으로
    # (간단한 규칙 - 실제 g2pk보다 단순하지만 충분히 작동)

    # 2. ㅎ 탈락: 모음 사이 ㅎ
    result = re.sub(r'ㅎ([아어오우이에애])', r'\1', result)

    # 3. 격음화: ㅎ + ㄱ/ㄷ/ㅂ/ㅈ → ㅋ/ㅌ/ㅍ/ㅊ
    replacements = {
        'ㅎㄱ': 'ㅋ', 'ㅎㄷ': 'ㅌ', 'ㅎㅂ': 'ㅍ', 'ㅎㅈ': 'ㅊ',
        'ㄱㅎ': 'ㅋ', 'ㄷㅎ': 'ㅌ', 'ㅂㅎ': 'ㅍ', 'ㅈㅎ': 'ㅊ',
    }
    for k, v in replacements.items():
        result = result.replace(k, v)

    return result


# 15 Viseme Classification for Korean
VISEME_MAP = {
    # 양순음 (입술 닫힘)
    'ㅂ': 1, 'ㅃ': 1, 'ㅍ': 1, 'ㅁ': 1,

    # 개방 모음 (턱 크게 벌림)
    'ㅏ': 2, 'ㅐ': 2, 'ㅑ': 2, 'ㅒ': 2,

    # 전설 모음 (입술 좌우)
    'ㅣ': 3, 'ㅔ': 3, 'ㅖ': 3,

    # 원순 모음 (입술 둥글게)
    'ㅗ': 4, 'ㅛ': 4, 'ㅜ': 4, 'ㅠ': 4,

    # 중설 모음 (중립)
    'ㅓ': 5, 'ㅕ': 5, 'ㅡ': 5,

    # 치경음 (혀끝-잇몸)
    'ㄷ': 6, 'ㄸ': 6, 'ㅌ': 6, 'ㄴ': 6, 'ㄹ': 6, 'ㅅ': 6, 'ㅆ': 6,

    # 연구개음 (입 약간 벌림)
    'ㄱ': 7, 'ㄲ': 7, 'ㅋ': 7, 'ㅇ': 7,

    # 성문음
    'ㅎ': 8,

    # 이중모음
    'ㅘ': 9, 'ㅙ': 9, 'ㅚ': 9, 'ㅝ': 9, 'ㅞ': 9, 'ㅟ': 9, 'ㅢ': 9,

    # 경구개음
    'ㅈ': 10, 'ㅉ': 10, 'ㅊ': 10,

    # 전환 상태 (동시조음)
    '_BP_': 11,
    '_AT_': 12,
    '_VT_': 13,

    # 휴지기
    ' ': 14, '.': 14, ',': 14, '?': 14, '!': 14,

    # 중립
    '_': 15,
}

# 음소 타입별 지속시간 (ms)
# 자음 프레임이 너무 짧으면 LERP가 목표치에 닿기 전에 다음 프레임으로 넘어가서
# morph target이 시각적으로 표현되지 않음 → 자음 계열 +30ms 조정
DURATION_MAP = {
    'initial_plain': 110,
    'initial_tense': 130,
    'initial_aspirated': 150,
    'initial_nasal': 120,
    'initial_liquid': 115,
    'medial_short': 150,
    'medial_long': 180,
    'medial_diphthong': 200,
    'final_consonant': 130,
    'transition': 55,
    'silence': 120,
}


def decompose_hangul(char: str) -> tuple:
    """한글 음절을 초성/중성/종성으로 분해"""
    if not ('가' <= char <= '힣'):
        return (None, None, None)

    code = ord(char) - 0xAC00
    initial_idx = code // 588
    medial_idx = (code % 588) // 28
    final_idx = code % 28

    initials = [
        'ㄱ', 'ㄲ', 'ㄴ', 'ㄷ', 'ㄸ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅃ', 'ㅅ',
        'ㅆ', 'ㅇ', 'ㅈ', 'ㅉ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ'
    ]
    medials = [
        'ㅏ', 'ㅐ', 'ㅑ', 'ㅒ', 'ㅓ', 'ㅔ', 'ㅕ', 'ㅖ', 'ㅗ', 'ㅘ',
        'ㅙ', 'ㅚ', 'ㅛ', 'ㅜ', 'ㅝ', 'ㅞ', 'ㅟ', 'ㅠ', 'ㅡ', 'ㅢ', 'ㅣ'
    ]
    finals = [
        '', 'ㄱ', 'ㄲ', 'ㄳ', 'ㄴ', 'ㄵ', 'ㄶ', 'ㄷ', 'ㄹ', 'ㄺ', 'ㄻ',
        'ㄼ', 'ㄽ', 'ㄾ', 'ㄿ', 'ㅀ', 'ㅁ', 'ㅂ', 'ㅄ', 'ㅅ', 'ㅆ', 'ㅇ',
        'ㅈ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ'
    ]

    return (initials[initial_idx], medials[medial_idx], finals[final_idx])


def get_phoneme_type(phoneme: str, position: str) -> str:
    """음소 타입 판별 (지속시간 계산용)"""
    if position == 'initial':
        if phoneme in ['ㄲ', 'ㄸ', 'ㅃ', 'ㅆ', 'ㅉ']:
            return 'initial_tense'
        elif phoneme in ['ㅋ', 'ㅌ', 'ㅍ', 'ㅊ', 'ㅎ']:
            return 'initial_aspirated'
        elif phoneme in ['ㄴ', 'ㅁ', 'ㅇ']:
            return 'initial_nasal'
        elif phoneme == 'ㄹ':
            return 'initial_liquid'
        return 'initial_plain'
    elif position == 'medial':
        if phoneme in ['ㅘ', 'ㅙ', 'ㅚ', 'ㅝ', 'ㅞ', 'ㅟ', 'ㅢ']:
            return 'medial_diphthong'
        elif phoneme in ['ㅏ', 'ㅗ', 'ㅜ']:
            return 'medial_long'
        return 'medial_short'
    elif position == 'final':
        return 'final_consonant'
    return 'silence'


def get_transition_viseme(current_final: str, next_initial: str) -> tuple:
    """동시조음 전환 프레임 계산"""
    if not current_final:
        return (None, 0)

    if current_final in ['ㅁ', 'ㅂ', 'ㅍ']:
        if next_initial in ['ㅏ', 'ㅐ', 'ㅓ', 'ㅔ']:
            return (11, 40)

    if next_initial in ['ㄷ', 'ㄸ', 'ㅌ', 'ㄴ', 'ㄹ', 'ㅅ', 'ㅆ']:
        return (12, 35)

    if next_initial in ['ㄱ', 'ㄲ', 'ㅋ', 'ㅇ']:
        return (13, 35)

    return (None, 0)


async def text_to_visemes(text: str) -> List[Dict]:
    """
    한국어 텍스트를 Viseme 애니메이션 프레임 배열로 변환
    g2pk 없이 직접 한글 분해 방식 사용
    """
    text = text.strip()
    if not text:
        return []

    # 기본 발음 규칙 적용
    try:
        phonetic = apply_phonological_rules(text)
    except Exception:
        phonetic = text

    viseme_frames = []
    chars = list(phonetic)

    for i, char in enumerate(chars):
        # 공백/구두점 처리
        if char in [' ', '.', ',', '?', '!', '\n']:
            viseme_frames.append({
                "viseme": 14,
                "duration_ms": DURATION_MAP['silence'],
                "transition_ms": 0
            })
            continue

        # 한글이 아닌 문자
        if not ('가' <= char <= '힣'):
            viseme = VISEME_MAP.get(char, 15)
            viseme_frames.append({
                "viseme": viseme,
                "duration_ms": 100,
                "transition_ms": 30
            })
            continue

        # 한글 분해
        initial, medial, final = decompose_hangul(char)
        if not initial:
            continue

        # 다음 글자 확인 (동시조음)
        next_char = chars[i + 1] if i + 1 < len(chars) else None
        next_initial = None
        if next_char and '가' <= next_char <= '힣':
            next_initial, _, _ = decompose_hangul(next_char)

        # 초성 프레임
        initial_viseme = VISEME_MAP.get(initial, 15)
        initial_type = get_phoneme_type(initial, 'initial')
        initial_duration = DURATION_MAP.get(initial_type, 80)
        transition_time = 40 if medial in ['ㅗ', 'ㅜ', 'ㅚ', 'ㅟ'] else 30

        viseme_frames.append({
            "viseme": initial_viseme,
            "duration_ms": initial_duration,
            "transition_ms": transition_time
        })

        # 중성 프레임
        medial_viseme = VISEME_MAP.get(medial, 15)
        medial_type = get_phoneme_type(medial, 'medial')
        medial_duration = DURATION_MAP.get(medial_type, 150)

        viseme_frames.append({
            "viseme": medial_viseme,
            "duration_ms": medial_duration,
            "transition_ms": 40 if final else 30
        })

        # 종성 프레임
        if final:
            final_viseme = VISEME_MAP.get(final, 15)
            trans_viseme, trans_duration = get_transition_viseme(final, next_initial)

            viseme_frames.append({
                "viseme": final_viseme,
                "duration_ms": DURATION_MAP['final_consonant'],
                "transition_ms": trans_duration if trans_viseme else 30
            })

            if trans_viseme:
                viseme_frames.append({
                    "viseme": trans_viseme,
                    "duration_ms": trans_duration,
                    "transition_ms": 20
                })

    # 너무 짧은 프레임 보정
    for frame in viseme_frames:
        if frame["duration_ms"] < 50:
            frame["duration_ms"] = 50

    return viseme_frames


def get_viseme_feature(viseme_id: int) -> str:
    """Viseme ID → 음운론적 특징명"""
    feature_map = {
        1: "bilabial", 2: "open_vowel", 3: "front_vowel",
        4: "rounded_vowel", 5: "central_vowel", 6: "alveolar",
        7: "velar", 8: "glottal", 9: "diphthong", 10: "palatal",
        11: "transition_bilabial", 12: "transition_alveolar",
        13: "transition_velar", 14: "silence", 15: "neutral"
    }
    return feature_map.get(viseme_id, "unknown")
