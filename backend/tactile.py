"""
한글 → 촉각(타도마) 액추에이터 시퀀스.

웹이 문장을 음소 단위로 분석해, 얼굴 모형(아두이노)이 그대로 재현할 값을 만든다.
각 음소는 다음 값을 가진다(하드웨어는 판단 없이 이 값을 그대로 재현):
  - jaw          : 턱 벌림 각도 0~20 (클수록 크게 벌어짐)
  - lip          : 입술 0=평순(ㅣ,ㅔ) / 1=원순(ㅗ,ㅜ)
  - voicing      : 진동(성대 떨림) 0/1  — 유성음이면 1
  - airflow      : 기류 'none' | 'plosive'(파열·순간) | 'fricative'(마찰·지속)
  - duration_ms  : 지속 시간(ms)

유·무성 및 파열/마찰 분류는 하드웨어 설계 사양을 그대로 따른다.
"""
from typing import List, Dict

CHO = list("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ")
JUNG = list("ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ")
JONG = ['', 'ㄱ', 'ㄲ', 'ㄳ', 'ㄴ', 'ㄵ', 'ㄶ', 'ㄷ', 'ㄹ', 'ㄺ', 'ㄻ', 'ㄼ', 'ㄽ', 'ㄾ',
        'ㄿ', 'ㅀ', 'ㅁ', 'ㅂ', 'ㅄ', 'ㅅ', 'ㅆ', 'ㅇ', 'ㅈ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ']

# 모음: (jaw, lip)
VOWEL = {
    'ㅏ': (20, 0), 'ㅐ': (14, 0), 'ㅑ': (20, 0), 'ㅒ': (14, 0), 'ㅓ': (16, 0), 'ㅔ': (12, 0),
    'ㅕ': (16, 0), 'ㅖ': (12, 0), 'ㅗ': (10, 1), 'ㅘ': (16, 1), 'ㅙ': (14, 1), 'ㅚ': (10, 1),
    'ㅛ': (10, 1), 'ㅜ': (6, 1), 'ㅝ': (14, 1), 'ㅞ': (12, 1), 'ㅟ': (6, 1), 'ㅠ': (6, 1),
    'ㅡ': (5, 0), 'ㅢ': (5, 0), 'ㅣ': (4, 0),
}

# 초성 자음: (voicing, airflow)
CONS = {
    'ㄱ': (1, 'plosive'), 'ㄲ': (0, 'plosive'), 'ㄴ': (1, 'none'), 'ㄷ': (1, 'plosive'),
    'ㄸ': (0, 'plosive'), 'ㄹ': (1, 'none'), 'ㅁ': (1, 'none'), 'ㅂ': (1, 'plosive'),
    'ㅃ': (0, 'plosive'), 'ㅅ': (0, 'fricative'), 'ㅆ': (0, 'fricative'), 'ㅈ': (1, 'fricative'),
    'ㅉ': (0, 'fricative'), 'ㅊ': (0, 'fricative'), 'ㅋ': (0, 'plosive'), 'ㅌ': (0, 'plosive'),
    'ㅍ': (0, 'plosive'), 'ㅎ': (0, 'fricative'),
}

# 종성 → 7 대표음(발음 규칙)
FINAL_REP = {
    'ㄱ': 'ㄱ', 'ㄲ': 'ㄱ', 'ㅋ': 'ㄱ', 'ㄳ': 'ㄱ', 'ㄺ': 'ㄱ',
    'ㄴ': 'ㄴ', 'ㄵ': 'ㄴ', 'ㄶ': 'ㄴ',
    'ㄷ': 'ㄷ', 'ㅅ': 'ㄷ', 'ㅆ': 'ㄷ', 'ㅈ': 'ㄷ', 'ㅊ': 'ㄷ', 'ㅌ': 'ㄷ', 'ㅎ': 'ㄷ',
    'ㄹ': 'ㄹ', 'ㄼ': 'ㄹ', 'ㄽ': 'ㄹ', 'ㄾ': 'ㄹ', 'ㅀ': 'ㄹ',
    'ㅁ': 'ㅁ', 'ㄻ': 'ㅁ',
    'ㅂ': 'ㅂ', 'ㅍ': 'ㅂ', 'ㅄ': 'ㅂ', 'ㄿ': 'ㅂ',
    'ㅇ': 'ㅇ',
}
# 대표음별 (voicing, airflow). 받침 폐쇄음(ㄱㄷㅂ)은 불파(airflow none).
FINAL_ARTIC = {
    'ㄱ': (0, 'none'), 'ㄷ': (0, 'none'), 'ㅂ': (0, 'none'),
    'ㄴ': (1, 'none'), 'ㅁ': (1, 'none'), 'ㅇ': (1, 'none'), 'ㄹ': (1, 'none'),
}

CONS_JAW = 4  # 자음 기본 턱 각도


def _emit(label, jaw, lip, voicing, airflow, dur) -> Dict:
    return {"label": label, "jaw": int(jaw), "lip": int(lip),
            "voicing": int(voicing), "airflow": airflow, "duration_ms": int(dur)}


def text_to_tactile(text: str, cons_ms: int = 120, vowel_ms: int = 200,
                    final_ms: int = 120, pause_ms: int = 150) -> List[Dict]:
    """한글 텍스트를 음소별 액추에이터 시퀀스로 변환한다."""
    seq: List[Dict] = []
    for ch in (text or ""):
        if ch.isspace():
            seq.append(_emit('(쉼)', 0, 0, 0, 'none', pause_ms))
            continue
        code = ord(ch)
        if not (0xAC00 <= code <= 0xD7A3):   # 완성형 한글만
            continue
        b = code - 0xAC00
        cho = CHO[b // 588]
        jung = JUNG[(b % 588) // 28]
        jong = JONG[b % 28]

        # 초성 (ㅇ 초성은 무음 → 생략)
        if cho != 'ㅇ':
            v, a = CONS[cho]
            seq.append(_emit(cho, CONS_JAW, 0, v, a, cons_ms))
        # 중성 (모음)
        jw, lp = VOWEL.get(jung, (10, 0))
        seq.append(_emit(jung, jw, lp, 1, 'none', vowel_ms))
        # 종성 (받침)
        if jong:
            rep = FINAL_REP.get(jong, jong)
            v, a = FINAL_ARTIC.get(rep, (1, 'none'))
            seq.append(_emit(jong, CONS_JAW, 0, v, a, final_ms))
    return seq
