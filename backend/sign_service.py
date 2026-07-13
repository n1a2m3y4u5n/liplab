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
from typing import List, Dict, Optional

from engine import decompose_hangul, text_to_visemes

# 국립국어원 한국수어사전 표제어 상세(영상) 딥링크 베이스
DICT_VIEW_URL = "https://sldict.korean.go.kr/front/sign/signContentsView.do?origin_no="

DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "ksl_dictionary.csv")

# 사용하는 Claude 모델 (앱의 시나리오 생성과 동일 계열로 일관성 유지)
_SIGN_MODEL = "claude-sonnet-4-6"

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
    """표제어 정확 일치로 수어 항목을 찾는다(없으면 None)."""
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
5) 사전에 없을 법한 고유명사·외래어·숫자는 그대로 두면 지문자로 처리된다.
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


# 규칙기반 폴백에서 어절 끝에서 떼어낼 대표 조사/보조사 (긴 것부터)
_PARTICLES = [
    "으로부터", "에서부터", "에게서", "한테서", "으로서", "으로써", "에서", "에게",
    "한테", "께서", "이라고", "라고", "이나마", "나마", "까지", "부터", "마다",
    "조차", "밖에", "처럼", "만큼", "보다", "이라", "으로", "은", "는", "이", "가",
    "을", "를", "과", "와", "도", "만", "에", "의", "로", "께",
]


def _strip_particle(eojeol: str) -> str:
    for p in _PARTICLES:
        if len(eojeol) > len(p) and eojeol.endswith(p):
            return eojeol[: -len(p)]
    return eojeol


def _gloss_via_rule(text: str) -> Dict:
    """API 키가 없을 때의 규칙기반 근사(어순 재배열은 하지 않음, 조사만 제거)."""
    gloss = []
    for eojeol in text.split():
        token = re.sub(r"[.,!?~…\"'()]", "", eojeol).strip()
        if not token:
            continue
        # 표제어 정확 일치 우선, 아니면 조사 제거 후 재시도
        if lookup_sign(token):
            gloss.append({"word": token})
        else:
            base = _strip_particle(token)
            gloss.append({"word": base or token})
    return {"gloss": gloss, "nonmanual": [], "notes": "규칙기반 근사(조사 제거). LLM 미사용."}


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
        sign = lookup_sign(word)
        # 입모양(mouthing): 해당 한국어 단어의 viseme 시퀀스
        try:
            visemes = await text_to_visemes(word)
        except Exception:
            visemes = []
        if sign:
            matched += 1
            tokens.append({
                "type": "sign",
                "word": word,
                "origin_no": sign["origin_no"],
                "description": sign["description"],
                "dict_url": sign["dict_url"],
                "alt_count": sign["alt_count"],
                "negate": bool(item.get("negate")),
                "visemes": visemes,
            })
        else:
            fingerspelled += 1
            tokens.append({
                "type": "fingerspell",
                "word": word,
                "jamo": fingerspell(word),
                "visemes": visemes,
            })

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
