"""
한국어 → 한국수어(KSL) 학습 보조 서비스
------------------------------------------------------------------
LIPLAB 내부 "학습·이해 보조(베타)" 모듈. 통역 서비스가 아니다.

파이프라인(둘 다 실제 처리, 하드코딩 아님):
  Stage A  한국어 문장 → 수어 gloss (Claude가 KSL 문법으로 번역;
           조사 제거·어순 재배열·비수지 표지 주석. API 키 없으면 규칙기반 폴백)
  Stage B  gloss 단어 → 국립국어원 한국수어사전 조회(표제어→표제어번호/수형설명/영상 딥링크)
           사전에 없는 단어 → 지문자(지화) 자모 분해로 폴백
  + 시너지 각 수어 단어의 '입모양(mouthing)'을 LIPLAB viseme 엔진으로 함께 제공

데이터 출처: 국립국어원 한국수어사전 「한국어대응표현정보」(공공데이터포털, 공공누리 출처표시).
영상: 국립국어원 한국수어사전(sldict.korean.go.kr) 표제어 딥링크.
"""
import os
import re
import csv
import json
import asyncio
import urllib.request
from typing import List, Dict, Optional

from engine import decompose_hangul, text_to_visemes

SLDICT_BASE = "https://sldict.korean.go.kr"
# 국립국어원 한국수어사전 표제어 상세(영상) 딥링크 베이스
DICT_VIEW_URL = SLDICT_BASE + "/front/sign/signContentsView.do?origin_no="

DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "ksl_dictionary.csv")

# 사용하는 Claude 모델 (앱의 시나리오 생성과 동일 계열로 일관성 유지)
_SIGN_MODEL = "claude-sonnet-4-6"

# 별칭표(수기 검증): 사전에 없는 흔한 단어 → 사전에 있는 **근접 동의어**.
# 각 항목을 사람이 확인했고, UI에는 치환을 **투명하게 표시**("밥 → 식사")한다.
# 블라인드 절단(정규화)과 달리 명시적·감사 가능하며, 알고리즘 오탐 위험이 없다.
# 값(동의어)은 실제 사전 표제어라야 한다(로드 시 검증).
_ALIASES = {
    '밥': '식사', '스마트폰': '휴대폰', '선생님': '교사', '자동차': '차',
    '편의점': '가게', '사용하다': '이용', '고치다': '수리', '도와주다': '돕다',
    '많이': '많다', '열심히': '열심', '천천히': '느리다',
}

# 아라비아 숫자 → 한국수어 숫자 수어. 1~9는 고유어 수사(하나~아홉), 0은 '영'(零).
# 조회는 lookup_number_sign이 동형어 중 '개념 > 수' 카테고리를 우선 선택하므로,
# 영(천주교)·셋(기독교) 같은 비숫자 동형어를 피해 숫자 수어만 정확히 고른다.
_DIGIT_TO_KO = {
    '0': '영', '1': '하나', '2': '둘', '3': '셋', '4': '넷', '5': '다섯',
    '6': '여섯', '7': '일곱', '8': '여덟', '9': '아홉',
}

# ---------------------------------------------------------------------------
# 사전 인덱스: 정제된 한국어 표제어 → [ {origin_no, description, word, category} ]
# ---------------------------------------------------------------------------
_INDEX: Optional[Dict[str, List[Dict]]] = None


def _clean_expressions(raw: str) -> List[str]:
    """'한국어 대응표현' 필드를 조회 가능한 표제어 리스트로 정제.

    예) '(맛이)짜다'            → ['짜다']
        '복직,복임'             → ['복직', '복임']
        '튀르키예공화국(약칭 …),터키' → ['튀르키예공화국', '터키']
        '-셔요,-세요,묻다'       → ['묻다']  (문법 접사(-…)는 제외)
    """
    words: List[str] = []
    for part in raw.split(","):
        w = re.sub(r"\([^)]*\)", "", part)   # 괄호 보충어 제거
        w = re.sub(r"\d+$", "", w).strip()   # 동형어 구분 숫자 제거
        if not w or w.startswith("-"):       # 빈 문자열/문법 접사 제외
            continue
        words.append(w)
    return words


def load_index() -> Dict[str, List[Dict]]:
    """CSV를 1회 로드해 표제어 인덱스를 만든다."""
    global _INDEX
    if _INDEX is not None:
        return _INDEX
    index: Dict[str, List[Dict]] = {}
    with open(DATA_PATH, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            origin = (row.get("수어 표제어 번호") or "").strip()
            desc = (row.get("수형설명") or "").strip()
            category = (row.get("대/중 분류") or "").strip()
            for word in _clean_expressions(row.get("한국어 대응표현") or ""):
                index.setdefault(word, []).append({
                    "origin_no": origin,
                    "description": desc,
                    "word": word,
                    "category": category,
                })
    _INDEX = index
    return index


def lookup_sign(word: str) -> Optional[Dict]:
    """표제어를 **완전일치**로만 찾는다(없으면 None).

    규칙기반 조사 제거·용언 원형화는 시도하지 않는다. 이유(적대적 리뷰에서 확인):
    자모 복원 없는 절단은 ㅅ/ㄷ 불규칙 활용형이나 명사를 '사전에 실재하는 다른 표제어'로
    오매칭시킨다(지었다→지다, 물었다→물다=bite, 정의→정). 존재 여부만 보는 index-gate로는
    막지 못하고, 학습자에게 '틀린 수어'를 확신 있게 보여주게 된다(미매칭보다 나쁨).
    → 기본형 변환은 **LLM 경로(Claude가 기본형 표제어를 출력)**에 맡기고, 완전일치에
    실패하면 정직하게 지문자로 폴백한다.
    """
    index = load_index()
    entries = index.get(word)
    if not entries:
        return None
    first = entries[0]
    return {
        "origin_no": first["origin_no"],
        "description": first["description"],
        "dict_url": DICT_VIEW_URL + first["origin_no"] if first["origin_no"] else None,
        "alt_count": len(entries),   # 동형어(같은 표제어의 다른 수어) 개수
    }


def lookup_number_sign(word: str) -> Optional[Dict]:
    """숫자 수어 조회. 동형어 중 '개념 > 수' 카테고리를 우선 선택한다.
    (예: '영'은 entries[0]이 천주교 수어라 일반 조회론 숫자 0을 못 잡음 → 여기서 origin 1214 선택)"""
    index = load_index()
    entries = index.get(word)
    if not entries:
        return None
    num = next((e for e in entries if e.get("category", "").split(">")[-1].strip() == "수"), entries[0])
    return {
        "origin_no": num["origin_no"],
        "description": num["description"],
        "dict_url": DICT_VIEW_URL + num["origin_no"] if num["origin_no"] else None,
        "alt_count": len(entries),
    }


# ---------------------------------------------------------------------------
# 수어 영상 URL 해석 — origin_no → 실제 mp4 (화면 안에서 인라인 재생용)
# ---------------------------------------------------------------------------
# 표제어 상세 페이지(raw HTML)에는 영상 썸네일 경로
#   //sldict.korean.go.kr/multimedia/multimedia_files/convert/DATE/ID/MOV{num}_105X105.jpg
# 가 들어 있고, 실제 영상은 같은 경로의 MOV{num}_700X466.mp4 (HTTPS 재생 가능)다.
# origin_no에서 이 경로를 유도할 공식이 없어(항목마다 DATE/ID 상이), 상세 페이지를
# 1회 조회해 추출하고 캐시한다. (robots.txt의 /front/sign 차단은 Googlebot 전용)
_VIDEO_CACHE: Dict[str, Optional[str]] = {}
_MOV_RE = re.compile(r'(multimedia/multimedia_files/convert/\d+/\d+/MOV\d+)_\d+X\d+\.(?:jpg|png)', re.I)


def _resolve_video_url_sync(origin_no: str) -> Optional[str]:
    if not origin_no:
        return None
    if origin_no in _VIDEO_CACHE:
        return _VIDEO_CACHE[origin_no]
    url = None
    try:
        req = urllib.request.Request(
            DICT_VIEW_URL + origin_no,
            headers={"User-Agent": "Mozilla/5.0 (LIPLAB learning aid)"},
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            html = resp.read().decode("utf-8", "replace")
        m = _MOV_RE.search(html)
        if m:
            url = f"{SLDICT_BASE}/{m.group(1)}_700X466.mp4"
    except Exception:
        url = None
    _VIDEO_CACHE[origin_no] = url
    return url


async def resolve_video_url(origin_no: str) -> Optional[str]:
    """상세 페이지에서 mp4 URL을 유도(블로킹 fetch는 스레드로). 실패 시 None."""
    return await asyncio.to_thread(_resolve_video_url_sync, origin_no)


# ---------------------------------------------------------------------------
# 지문자(지화) 폴백 — 사전에 없는 단어를 한글 자모로 분해
# ---------------------------------------------------------------------------
def fingerspell(word: str) -> List[List[str]]:
    """단어를 음절별 자모 그룹으로 분해. 한글이 아니면 문자 그대로.

    예) '밥' → [['ㅂ','ㅏ','ㅂ']]   '수여' → [['ㅅ','ㅜ'],['ㅇ','ㅕ']]
    """
    groups: List[List[str]] = []
    for ch in word:
        initial, medial, final = decompose_hangul(ch)
        if initial is None:            # 한글 음절이 아님(숫자/영문/기호)
            if not ch.isspace():
                groups.append([ch])
            continue
        jamo = [initial, medial]
        if final:
            jamo.append(final)
        groups.append(jamo)
    return groups


# ---------------------------------------------------------------------------
# Stage A — 한국어 → 수어 gloss
# ---------------------------------------------------------------------------
_KSL_SYSTEM_PROMPT = """당신은 한국어를 한국수어(KSL) 문법으로 옮기는 번역기다.
한국수어는 한국어와 문법이 다른 독립 언어다. 다음 규칙으로 '수어 gloss'를 만들어라.

규칙:
1) 조사(은/는/이/가/을/를/에/에서/도/만/의/으로 등)는 제거한다.
2) 어순은 한국수어를 따른다: 시간·장소를 앞에, 주제-설명(topic-comment) 순서, 서술어는 뒤.
3) 부정(안/못/없다)·의문은 서술어 뒤에서 표현한다(negate 표시).
4) 각 단어는 한국수어사전에서 찾을 수 있는 '기본형 한국어 표제어'로 낸다
   (동사는 '가다/먹다'처럼 기본형, 명사는 단독형).
5) 사전에 없을 법한 고유명사·외래어는 그대로 두면 지문자로 처리된다.
   아라비아 숫자는 **숫자 자체로 별도 토큰**으로 분리해 낸다(예: "3시" → "3","시").
6) 얼굴표정·고개 등 비수지 표지가 문법상 중요하면 nonmanual에 적는다.

반드시 아래 JSON만 출력한다(설명 금지):
{"gloss":[{"word":"학교"},{"word":"가다","negate":true}],
 "nonmanual":[{"marker":"부정","note":"고개 젓기 + 부정 표정"}],
 "notes":"간단한 번역 메모"}"""


async def _gloss_via_llm(text: str) -> Optional[Dict]:
    """Claude로 KSL gloss 생성. 실패(키 없음/오류/파싱실패) 시 None."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model=_SIGN_MODEL,
            max_tokens=800,
            system=_KSL_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text}],
        )
        content = response.content[0].text.strip()
        # 코드펜스 방어
        content = re.sub(r"^```(?:json)?|```$", "", content, flags=re.MULTILINE).strip()
        data = json.loads(content)
        if not isinstance(data.get("gloss"), list):
            return None
        return data
    except Exception:
        return None


def _gloss_via_rule(text: str) -> Dict:
    """API 키가 없을 때의 규칙기반 근사(어순 재배열·정규화 없음).
    각 어절을 그대로 조회하고, 완전일치에 실패하면 지문자로 폴백한다(정직).
    조사 제거·용언 원형화는 오탐 위험이 커 하지 않는다 → 기본형 변환은 LLM 경로가 담당."""
    gloss = []
    for eojeol in text.split():
        token = re.sub(r"[.,!?~…\"'()]", "", eojeol).strip()
        if token:
            gloss.append({"word": token})
    return {"gloss": gloss, "nonmanual": [], "notes": "규칙기반 근사(원어절, LLM 미사용). 미등재 어절은 지문자."}


# ---------------------------------------------------------------------------
# 조립 — gloss → 재생 토큰(수어 영상 / 지문자) + 입모양
# ---------------------------------------------------------------------------
async def translate_to_ksl(text: str) -> Dict:
    """한국어 문장을 KSL 학습 보조 토큰 시퀀스로 변환."""
    text = (text or "").strip()
    if not text:
        return {"source": "", "method": "none", "tokens": [], "annotations": [],
                "notes": "", "coverage": {"total": 0, "matched": 0, "fingerspelled": 0}}

    llm = await _gloss_via_llm(text)
    if llm is not None:
        method, parsed = "llm", llm
    else:
        method, parsed = "rule", _gloss_via_rule(text)

    tokens: List[Dict] = []
    matched = fingerspelled = 0
    for item in parsed.get("gloss", []):
        word = (item.get("word") or "").strip()
        if not word:
            continue

        # 숫자: 아라비아 숫자를 자리별로 한국수어 숫자 수어(영상)로 표시. 원 숫자는 남기고
        # signed_as에 한국어 수사를 넣어 투명 표시("3 → 셋"). 매핑 없는 자리(0)는 지문자.
        if word.isdigit():
            for d in word:
                kw = _DIGIT_TO_KO.get(d)
                s = lookup_number_sign(kw) if kw else None
                try:
                    dv = await text_to_visemes(kw or d)
                except Exception:
                    dv = []
                if s:
                    matched += 1
                    tokens.append({
                        "type": "sign", "word": d, "signed_as": kw,
                        "origin_no": s["origin_no"], "description": s["description"],
                        "dict_url": s["dict_url"], "alt_count": s["alt_count"],
                        "negate": False, "visemes": dv,
                    })
                else:
                    fingerspelled += 1
                    tokens.append({"type": "fingerspell", "word": d, "jamo": [[d]], "visemes": dv})
            continue

        sign = lookup_sign(word)
        # 완전일치 실패 시 별칭표로 근접 동의어를 시도(투명 치환)
        signed_as = None
        if not sign:
            alias = _ALIASES.get(word)
            if alias:
                a_sign = lookup_sign(alias)
                if a_sign:
                    sign, signed_as = a_sign, alias
        # 입모양(mouthing)은 사용자가 입력한 원어 기준(밥을 배우는 중이므로 '밥')
        try:
            visemes = await text_to_visemes(word)
        except Exception:
            visemes = []
        if sign:
            matched += 1
            token = {
                "type": "sign",
                "word": word,                 # 원어(사용자 입력)
                "origin_no": sign["origin_no"],
                "description": sign["description"],
                "dict_url": sign["dict_url"],
                "alt_count": sign["alt_count"],
                "negate": bool(item.get("negate")),
                "visemes": visemes,
            }
            if signed_as:
                token["signed_as"] = signed_as   # 실제 표시된 수어 표제어(근접 동의어)
            tokens.append(token)
        else:
            fingerspelled += 1
            tokens.append({
                "type": "fingerspell",
                "word": word,
                "jamo": fingerspell(word),
                "visemes": visemes,
            })

    # 수어 토큰의 실제 영상 URL을 병렬로 해석해 인라인 재생에 쓴다(캐시됨).
    sign_tokens = [t for t in tokens if t["type"] == "sign" and t.get("origin_no")]
    if sign_tokens:
        urls = await asyncio.gather(*(resolve_video_url(t["origin_no"]) for t in sign_tokens))
        for t, u in zip(sign_tokens, urls):
            t["video_url"] = u

    return {
        "source": text,
        "method": method,
        "tokens": tokens,
        "annotations": parsed.get("nonmanual", []),
        "notes": parsed.get("notes", ""),
        "coverage": {
            "total": len(tokens),
            "matched": matched,
            "fingerspelled": fingerspelled,
        },
    }
