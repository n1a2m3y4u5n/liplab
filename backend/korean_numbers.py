"""아라비아 숫자를 한국어 읽기로 바꾼다(입모양 엔진·채점 정규화용).

예전에는 숫자가 입모양 프레임도 채점 음절도 없이 빠져, "3시에 만나요"를 아바타가 "시에 만나요"로 보여 주고
학습자가 "세 시에 만나요"라고 적으면 정답에 없는 음절로 감점됐다. 뒤따르는 단위 명사로 고유어(세 시, 두 명)와
한자어(삼 층, 오천 원)를 고른다. 순수 함수라 결정론적으로 테스트된다.

범위: 정수(쉼표 허용)와 소수. 날짜·전화번호 같은 특수 형식은 한 자리씩 읽지 않고 수로 읽는다(콘텐츠에서 드묾).
"""
import re
from typing import List

_SINO_DIGIT = ["", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"]
_SINO_SMALL = [("천", 1000), ("백", 100), ("십", 10)]
_SINO_BIG = [("조", 10 ** 12), ("억", 10 ** 8), ("만", 10 ** 4)]

_NATIVE_ONES = ["", "하나", "둘", "셋", "넷", "다섯", "여섯", "일곱", "여덟", "아홉"]
_NATIVE_ONES_ATTR = ["", "한", "두", "세", "네", "다섯", "여섯", "일곱", "여덟", "아홉"]   # 단위 명사 앞
_NATIVE_TENS = ["", "열", "스물", "서른", "마흔", "쉰", "예순", "일흔", "여든", "아흔"]

# 고유어로 세는 단위(1~99). 그 밖의 단위와 단위가 없을 때는 한자어로 읽는다.
_NATIVE_COUNTERS = ("시간", "번째", "사람", "켤레", "그루", "송이", "마리", "시", "개", "명", "살", "잔", "병",
                    "권", "장", "벌", "대", "달", "채", "척", "통", "곡", "판", "줄", "군데", "가지", "배", "살짜리",
                    "정거장", "정류장", "그릇", "봉지", "상자", "접시", "조각", "방울", "모금", "자루", "쌍", "개비")
# 고유어 단위와 앞글자가 겹치는 한자어 단위(3개월 → 삼 개월, 5달러 → 오 달러). 고유어 단위보다 먼저 본다(9/27 감사).
_SINO_BEFORE_NATIVE = ("개월", "달러")
# '번'은 횟수면 고유어(두 번), 번호면 한자어(3번 출구). 뒤 명사로 번호를 가른다.
_NUMBERING_AFTER_BEON = ("출구", "버스", "방", "문제", "선", "게이트", "창구", "트랙", "좌석", "홀", "칸", "줄")


def sino(n: int) -> str:
    """한자어 수 읽기(일, 십, 백이십삼, 만 오천 -> 만오천)."""
    if n == 0:
        return "영"
    out = ""
    for word, unit in _SINO_BIG:
        if n >= unit:
            head = n // unit
            out += ("" if (head == 1 and word == "만") else _sino_under_10000(head)) + word
            n %= unit
    return out + _sino_under_10000(n)


def _sino_under_10000(n: int) -> str:
    out = ""
    for word, unit in _SINO_SMALL:
        if n >= unit:
            d = n // unit
            out += ("" if d == 1 else _SINO_DIGIT[d]) + word
            n %= unit
    return out + _SINO_DIGIT[n]


def native(n: int, attributive: bool = True) -> str:
    """고유어 수 읽기(1~99). 단위 명사 앞이면 한·두·세·네·스무."""
    if not 1 <= n <= 99:
        return sino(n)
    tens, ones = divmod(n, 10)
    if ones == 0:
        return "스무" if (tens == 2 and attributive) else _NATIVE_TENS[tens]
    ones_word = (_NATIVE_ONES_ATTR if attributive else _NATIVE_ONES)[ones]
    return _NATIVE_TENS[tens] + ones_word


def _reading(num: str, after: str) -> str:
    if "." in num:
        whole, frac = num.split(".", 1)
        return sino(int(whole or "0")) + "점" + "".join(_SINO_DIGIT[int(d)] or "영" for d in frac)
    n = int(num)
    if after.startswith(_SINO_BEFORE_NATIVE):
        return sino(n)
    if after.startswith("번째"):
        return "첫" if n == 1 else native(n)     # 1번째 → 첫 번째
    if after.startswith("번") and not after.startswith("번째"):
        rest = after[1:].lstrip()
        return sino(n) if rest.startswith(_NUMBERING_AFTER_BEON) else native(n)
    if after.startswith("월"):          # 유월·시월
        return {6: "유", 10: "시"}.get(n, sino(n))
    if 1 <= n <= 99 and after.startswith(_NATIVE_COUNTERS):
        return native(n)
    return sino(n)


_NUM = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")


def normalize_numbers(text: str) -> str:
    """문장 안의 숫자를 한국어 읽기로 바꾼다. 숫자가 없으면 그대로 돌려준다."""
    if not text or not any(ch.isdigit() for ch in text):
        return text
    out: List[str] = []
    pos = 0
    for m in _NUM.finditer(text):
        out.append(text[pos:m.start()])
        out.append(_reading(m.group().replace(",", ""), text[m.end():].lstrip()))
        pos = m.end()
    out.append(text[pos:])
    return "".join(out)
