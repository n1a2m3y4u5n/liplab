"""
Advanced Viseme Engine for Korean Speechreading
Converts Korean text to 15 fine-grained visemes with co-articulation modeling
g2pk-free version: uses built-in Korean phonological rules
"""
from typing import List, Dict

# 한국어 발음 변환 (g2p) — g2pk 없이 자체 구현
#
# 독화 앱은 '철자'가 아니라 '소리 나는 대로'의 입모양을 보여줘야 한다.
# 이 viseme 시스템은 음소를 10개 그룹으로 뭉치므로, 모든 표준 발음 규칙을
# 구현할 필요는 없고 **입모양(viseme 그룹)을 실제로 바꾸는 규칙만** 구현한다:
#   ① 겹받침 단순화(음절 말 자음군)  ② 연음(받침 이동)
#   ③ ㅎ 탈락  ④ 초성 ㅇ 무음화
# (비음화·경음화·격음화 등은 대개 같은 viseme 그룹 안에서 바뀌어 입모양이
#  변하지 않으므로, 과설계를 피하기 위해 생략한다.)

# 겹받침 → 음절 말 대표 발음(단독/자음 앞에서 하나로 줄어듦)
DOUBLE_FINAL = {
    'ㄳ': 'ㄱ', 'ㄵ': 'ㄴ', 'ㄶ': 'ㄴ', 'ㄺ': 'ㄱ', 'ㄻ': 'ㅁ', 'ㄼ': 'ㄹ',
    'ㄽ': 'ㄹ', 'ㄾ': 'ㄹ', 'ㄿ': 'ㅂ', 'ㅀ': 'ㄹ', 'ㅄ': 'ㅂ',
}

# 겹받침 + 모음(연음) 시 → (앞 자음은 종성으로 남고, 뒤 자음이 다음 초성으로)
DOUBLE_FINAL_LINK = {
    'ㄳ': ('ㄱ', 'ㅅ'), 'ㄵ': ('ㄴ', 'ㅈ'), 'ㄶ': ('ㄴ', 'ㅎ'), 'ㄺ': ('ㄹ', 'ㄱ'),
    'ㄻ': ('ㄹ', 'ㅁ'), 'ㄼ': ('ㄹ', 'ㅂ'), 'ㄽ': ('ㄹ', 'ㅅ'), 'ㄾ': ('ㄹ', 'ㅌ'),
    'ㄿ': ('ㄹ', 'ㅍ'), 'ㅀ': ('ㄹ', 'ㅎ'), 'ㅄ': ('ㅂ', 'ㅅ'),
}

# 격음화(축약) — 평음이 ㅎ과 만나 거센소리로. 입모양(viseme 그룹)이 실제로 바뀌는 방향만 반영:
#   · 코다 ㅎ + 평음 초성 → 초성이 거센소리 (좋다→조타). 성문음 ㅎ(viseme 8) 프레임이 사라진다.
#   · 코다 평음 + 초성 ㅎ → 코다가 다음 초성으로 거세게 (입학→이팍, 국화→구콰). ㅎ(8)→ㅂ계(1)·ㄱ계(7)로 바뀜.
ASPIRATE = {'ㄱ': 'ㅋ', 'ㄷ': 'ㅌ', 'ㅂ': 'ㅍ', 'ㅈ': 'ㅊ'}
# 코다 ㅎ을 품은 겹받침(격음화 후 앞 자음이 코다로 남음)
H_CODA = {'ㅎ': '', 'ㄶ': 'ㄴ', 'ㅀ': 'ㄹ'}


def to_pronounced_syllables(text: str):
    """
    한국어 텍스트를 '소리 나는 대로'의 음절 리스트로 변환.
    한글 음절은 [초성, 중성, 종성] 리스트로(초성 ''는 무음 ㅇ),
    그 외 문자는 원래 문자열 그대로 담아 반환한다.
    """
    tokens = []  # 한글: ['초','중','종'], 그 외: 원문자
    for ch in text:
        if '가' <= ch <= '힣':
            ini, med, fin = decompose_hangul(ch)
            tokens.append([ini, med, fin])
        else:
            tokens.append(ch)

    # 인접 음절 간 규칙 적용 (격음화 / 연음 / ㅎ탈락)
    for i in range(len(tokens) - 1):
        cur, nxt = tokens[i], tokens[i + 1]
        if not isinstance(cur, list) or not isinstance(nxt, list):
            continue
        fin = cur[2]
        if not fin:
            continue
        nini = nxt[0]

        # ── 격음화(축약): 다음 초성이 '실제 자음'일 때(무음 ㅇ 이전) 먼저 처리 ──
        # (a) 코다 ㅎ(계열) + 평음 초성 → 초성 거센소리, ㅎ 코다 탈락 (좋다→조타, 많다→만타)
        if fin in H_CODA and nini in ASPIRATE:
            nxt[0] = ASPIRATE[nini]
            cur[2] = H_CODA[fin]
            continue
        # (b) 코다 평음 + 초성 ㅎ → 코다가 다음 초성으로 거세게, 코다 탈락 (입학→이팍, 국화→구콰)
        if nini == 'ㅎ' and fin in ASPIRATE:
            asp = ASPIRATE[fin]
            # ㅎ 매개 구개음화 — ㄷ+히 → 치 (닫히다→다치다, 굳히다→구치다). ㅣ에 한정해 과적용 방지.
            if asp == 'ㅌ' and nxt[1] == 'ㅣ':
                asp = 'ㅊ'
            nxt[0] = asp
            cur[2] = ''
            continue

        if nini != 'ㅇ':
            continue  # (격음화 외에는) 다음 초성이 무음 ㅇ이 아니면 연음 대상 아님
        if fin == 'ㅇ':
            continue  # 종성 ㅇ[ŋ]은 넘어가지 않음 (강아지→강아지)
        elif fin == 'ㅎ':
            cur[2] = ''  # ㅎ 탈락 (좋아→조아), 다음 초성은 무음 ㅇ 유지
        elif fin in DOUBLE_FINAL_LINK:
            keep, move = DOUBLE_FINAL_LINK[fin]
            cur[2] = keep
            nxt[0] = move  # 뒤 자음만 다음 초성으로 (닭이→달기)
        elif fin in ('ㄷ', 'ㅌ') and nxt[1] in ('ㅣ', 'ㅑ', 'ㅕ', 'ㅛ', 'ㅠ', 'ㅒ', 'ㅖ'):
            # 구개음화 — 종성 ㄷ·ㅌ이 뒤 ㅣ/반모음을 만나 ㅈ·ㅊ으로(굳이→구지, 같이→가치, 붙여→부쳐).
            # 입모양이 치경(viseme 6)에서 경구개(viseme 10)로 실제로 바뀌므로 비심 엔진이 반영한다.
            nxt[0] = 'ㅈ' if fin == 'ㄷ' else 'ㅊ'
            cur[2] = ''
        else:
            nxt[0] = fin   # 받침이 통째로 다음 초성으로 (밥을→바블)
            cur[2] = ''

    for tok in tokens:
        if not isinstance(tok, list):
            continue
        # 연음되지 않고 남은 겹받침 단순화 (값→갑, 닭→닥)
        if tok[2] in DOUBLE_FINAL:
            tok[2] = DOUBLE_FINAL[tok[2]]
        # 무음 초성 ㅇ → '' (입모양 프레임 없음). 종성 ㅇ[ŋ]은 그대로 둔다.
        if tok[0] == 'ㅇ':
            tok[0] = ''

    return tokens


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
    """동시조음 전환 프레임 계산.

    코다에서 '다음 음절 초성의 조음위치'로 입이 옮겨가는 사이 프레임을 낸다.
    다음 초성의 조음위치별로 11(양순)·12(치경)·13(연구개) 세 전환을 대칭으로 부여한다.
    (기존에는 11 분기가 다음 '모음'을 검사해 초성 슬롯과 맞지 않아 한 번도 방출되지 않았다.)
    """
    if not current_final:
        return (None, 0)

    # 다음 초성이 양순음 → 입술이 닫히는 전환 (국물→[…ㄱ]→(양순전환)→[ㅁ…])
    if next_initial in ['ㅂ', 'ㅃ', 'ㅍ', 'ㅁ']:
        return (11, 35)

    if next_initial in ['ㄷ', 'ㄸ', 'ㅌ', 'ㄴ', 'ㄹ', 'ㅅ', 'ㅆ']:
        return (12, 35)

    if next_initial in ['ㄱ', 'ㄲ', 'ㅋ', 'ㅇ']:
        return (13, 35)

    return (None, 0)


async def text_to_visemes(text: str) -> List[Dict]:
    """
    한국어 텍스트를 Viseme 애니메이션 프레임 배열로 변환.
    먼저 '소리 나는 대로'(연음·겹받침·ㅎ탈락·무음 초성 ㅇ)로 변환한 뒤
    음절별 초성/중성/종성 입모양 프레임을 생성한다.
    """
    text = text.strip()
    if not text:
        return []

    try:
        tokens = to_pronounced_syllables(text)
    except Exception:
        # 변환 실패 시 원문자 그대로라도 처리
        tokens = [list(decompose_hangul(c)) if '가' <= c <= '힣' else c for c in text]

    viseme_frames = []

    for i, tok in enumerate(tokens):
        # 한글이 아닌 문자 (공백/구두점/기타)
        if not isinstance(tok, list):
            if tok in [' ', '.', ',', '?', '!', '\n']:
                viseme_frames.append({
                    "viseme": 14,
                    "duration_ms": DURATION_MAP['silence'],
                    "transition_ms": 0,
                    "text_index": i,
                })
            else:
                viseme_frames.append({
                    "viseme": VISEME_MAP.get(tok, 15),
                    "duration_ms": 100,
                    "transition_ms": 30,
                    "text_index": i,
                })
            continue

        initial, medial, final = tok
        if not medial:
            continue

        # 다음 음절의 초성 (동시조음 전환용)
        next_initial = None
        if i + 1 < len(tokens) and isinstance(tokens[i + 1], list):
            next_initial = tokens[i + 1][0]

        # 초성 프레임 — 무음 초성 ㅇ('')은 건너뜀 (소리 없이 바로 모음으로)
        if initial:
            initial_type = get_phoneme_type(initial, 'initial')
            viseme_frames.append({
                "viseme": VISEME_MAP.get(initial, 15),
                "duration_ms": DURATION_MAP.get(initial_type, 80),
                "transition_ms": 40 if medial in ['ㅗ', 'ㅜ', 'ㅚ', 'ㅟ'] else 30,
                "text_index": i,
            })

        # 중성 프레임
        medial_type = get_phoneme_type(medial, 'medial')
        viseme_frames.append({
            "viseme": VISEME_MAP.get(medial, 15),
            "duration_ms": DURATION_MAP.get(medial_type, 150),
            "transition_ms": 40 if final else 30,
            "text_index": i,
        })

        # 종성 프레임
        if final:
            trans_viseme, trans_duration = get_transition_viseme(final, next_initial)
            viseme_frames.append({
                "viseme": VISEME_MAP.get(final, 15),
                "duration_ms": DURATION_MAP['final_consonant'],
                "transition_ms": trans_duration if trans_viseme else 30,
                "text_index": i,
            })
            if trans_viseme:
                viseme_frames.append({
                    "viseme": trans_viseme,
                    "duration_ms": trans_duration,
                    "transition_ms": 20,
                    "text_index": i,
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
