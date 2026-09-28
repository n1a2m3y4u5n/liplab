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
# 개국·개년·개소도 한자어다. 예전에는 '개'에 걸려 "3개국어"를 "세개국어"로 읽었다(9/28 감사).
_SINO_BEFORE_NATIVE = ("개월", "달러", "개국", "개년", "개소")
# '대'는 차·기계를 세면 고유어(차 두 대), 나이대·점수면 한자어(이십 대, 이 대 일)다. 예전에는 늘 고유어라 "20대 여성"을
# "스무대 여성"으로 보여 주고, 맞게 읽어 "이십 대 여성이에요"라고 적은 답이 65.62점, "30대예요"에 "삼십 대예요"는 54.33점
# (합격선 60 아래)이었다(9/28 감사). 셀 대상 명사 뒤면 고유어, 그 밖에 뒷말이 나이대·비교 표현이거나 10의 배수이거나
# 뒤에 숫자가 오면(2대 1) 한자어로 읽는다. 10의 배수만으로 가르면 "차 10대"가 "십 대"가 되어 앞 명사를 먼저 본다.
_DAE_SINO_NEXT = ("초반", "중반", "후반", "남성", "여성", "남자", "여자", "청소년", "직장인", "이상", "이하", "때")
_DAE_COUNTED = re.compile(r"(?:자동차|차량|차|버스|택시|자전거|오토바이|트럭|비행기|컴퓨터|노트북|기계|휴대폰)"
                          r"(?:이|가|은|는|을|를|도|만)?$")
# '번'은 횟수면 고유어(두 번), 번호면 한자어(3번 출구). 뒤 명사로 번호를 가른다.
_NUMBERING_AFTER_BEON = ("출구", "버스", "방", "문제", "선", "게이트", "창구", "트랙", "좌석", "홀", "칸", "줄")
# '분'은 시간이면 한자어(5분 뒤), 사람을 높여 세면 고유어(두 분이세요). 사람일 때만 붙는 높임 어미·조사로 가른다.
# 예전에는 전부 한자어라 식당 대화 "2분이시면"을 "이분이시면"으로 보여 줬다(9/27 밤)
_PERSON_AFTER_BUN = ("이시", "이세", "이십", "이셔", "이서", "께", "이 오셨", "이 오시", "이 계시", "이 계셨", "손님")


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


def _dae_is_sino(n: int, after: str, before: str) -> bool:
    """숫자 뒤 '대'를 한자어로 읽을지. before는 숫자 앞 어절이다."""
    if _DAE_COUNTED.search(before):
        return False
    if after[1:].lstrip().startswith(_DAE_SINO_NEXT) or (10 <= n <= 90 and n % 10 == 0):
        return True
    return bool(re.match(r"\s*\d", after[1:]))


def _reading(num: str, after: str, before: str = "") -> str:
    if "." in num:
        whole, frac = num.split(".", 1)
        return sino(int(whole or "0")) + "점" + "".join(_SINO_DIGIT[int(d)] or "영" for d in frac)
    n = int(num)
    if after.startswith(_SINO_BEFORE_NATIVE):
        return sino(n)
    if after.startswith("대") and _dae_is_sino(n, after, before):
        return sino(n)
    if after.startswith("번째"):
        return "첫" if n == 1 else native(n)     # 1번째 → 첫 번째
    if after.startswith("번") and not after.startswith("번째"):
        rest = after[1:].lstrip()
        return sino(n) if rest.startswith(_NUMBERING_AFTER_BEON) else native(n)
    if after.startswith("분") and 1 <= n <= 99 and (after[1:].startswith(_PERSON_AFTER_BUN)
                                                   or after[1:].lstrip().startswith("손님")):
        return native(n)
    if after.startswith("월"):          # 유월·시월
        return {6: "유", 10: "시"}.get(n, sino(n))
    if 1 <= n <= 99 and after.startswith(_NATIVE_COUNTERS):
        return native(n)
    return sino(n)


_NUM = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")

# 숫자 뒤 단위 기호는 읽는 말로 바꾼다. 예전에는 기호가 입모양·채점에서 빠져 "50% 할인"을 아바타가 "오십 할인"으로 보여 주고,
# 학습자가 "오십 퍼센트"라고 적으면 정답에 없는 음절로 감점됐다(9/27 밤). 모두 한자어 수로 읽는 단위다.
_UNIT_WORDS = {"%": "퍼센트", "％": "퍼센트", "℃": "도", "°C": "도", "°": "도", "km": "킬로미터", "kg": "킬로그램",
               "cm": "센티미터", "mm": "밀리미터", "ml": "밀리리터", "mL": "밀리리터", "L": "리터", "l": "리터",
               "g": "그램", "m": "미터"}
_UNIT = re.compile(r"(\d)\s?(" + "|".join(sorted(map(re.escape, _UNIT_WORDS), key=len, reverse=True)) + r")(?![A-Za-z])")
# 시각 3:30 → 세시 삼십분(시는 고유어, 분은 한자어, 정각은 시만)
_CLOCK = re.compile(r"(?<![\d:])([01]?\d|2[0-4]):([0-5]\d)(?![\d:])")
# 전화번호(0으로 시작하는 지역·휴대전화 번호, 1588-0000 같은 대표번호)는 한 자리씩(0은 공). 수로 읽으면 "010-1234"가
# "십-천이백삼십사"가 됐다. 2024-2025 같은 연도 범위는 수로 읽는다
_PHONE = re.compile(r"(?<![\d-])(?:0\d{1,3}-\d{3,4}-\d{4}|1[5-9]\d{2}-\d{4})(?![\d-])")
_DIGIT_READ = ["공", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"]


def _clock(m) -> str:
    h, mm = int(m.group(1)), int(m.group(2))
    return (native(h) if 1 <= h <= 24 else sino(h)) + "시" + (f" {sino(mm)}분" if mm else "")


def _phone(m) -> str:
    return " ".join("".join(_DIGIT_READ[int(d)] for d in part) for part in m.group().split("-"))


# 범위 1~2개·3-4명. 예전에는 앞 수를 단위 없이 한자어로 읽고 '~'를 남겨 "일~두개", "삼~네명"이 됐고, '~'는 입모양 엔진이
# 중립 프레임으로 그렸다. "1~2개 주세요"에 "한두 개 주세요"라고 적은 답이 76.67점이었다(9/28 감사). 두 번째 수 바로 뒤에
# 단위가 올 때만 범위로 보고, 두 수를 그 단위 규칙으로 읽는다. '-'는 고유어 단위일 때만 범위로 본다(2024-2025는 그대로).
_RANGE = re.compile(r"(?<![\d.,-])(" + _NUM.pattern + r")\s*([~～〜-])\s*(" + _NUM.pattern + r")(?=[가-힣])")
# 이웃한 두 수를 붙여 읽는 말. 고유어(한두 개, 서너 명)와 한자어(이삼 일, 오륙 층)
_NATIVE_PAIR = {1: "한두", 2: "두세", 3: "서너", 4: "네다섯", 5: "대여섯", 6: "예닐곱", 7: "일고여덟", 8: "여덟아홉"}
_SINO_PAIR = {1: "일이", 2: "이삼", 3: "삼사", 4: "사오", 5: "오륙", 6: "육칠", 7: "칠팔", 8: "팔구"}


def _range(m) -> str:
    a, sep, b = m.group(1).replace(",", ""), m.group(2), m.group(3).replace(",", "")
    after = m.string[m.end():]
    rb = _reading(b, after)
    whole = "." not in a + b
    x, y = (int(a), int(b)) if whole else (0, 0)
    is_native = whole and 1 <= y <= 99 and rb == native(y) != sino(y)
    if sep == "-" and not is_native:
        return m.group()
    if whole and y == x + 1 and x in _NATIVE_PAIR:
        if is_native:
            return _NATIVE_PAIR[x]
        if rb == sino(y):
            return _SINO_PAIR[x]
    ra = native(x, attributive=False) if (is_native and 1 <= x <= 99) else _reading(a, "")
    return ra + "에서 " + rb


def normalize_numbers(text: str) -> str:
    """문장 안의 숫자를 한국어 읽기로 바꾼다. 숫자가 없으면 그대로 돌려준다."""
    if not text or not any(ch.isdigit() for ch in text):
        return text
    text = _PHONE.sub(_phone, text)
    text = _CLOCK.sub(_clock, text)
    text = _UNIT.sub(lambda m: m.group(1) + _UNIT_WORDS[m.group(2)], text)
    text = _RANGE.sub(_range, text)
    if not any(ch.isdigit() for ch in text):
        return text
    out: List[str] = []
    pos = 0
    for m in _NUM.finditer(text):
        out.append(text[pos:m.start()])
        num, rest = m.group().replace(",", ""), text[m.end():]
        before = text[:m.start()].rstrip().split(" ")[-1]
        # 1만·1천·1백의 1은 읽지 않는다(만 원, 천 원). 예전에는 "일만 원"이라 같은 금액 "10,000원"(만원)과 달랐고,
        # "1만 원이에요"에 "만 원이에요"라고 적은 답이 84.85점이었다(9/28 감사). 1억은 일억 그대로다.
        if num == "1" and rest[:1] in ("만", "천", "백"):
            out.append("")
        else:
            out.append(_reading(num, rest.lstrip(), before))
        pos = m.end()
    out.append(text[pos:])
    return "".join(out)
