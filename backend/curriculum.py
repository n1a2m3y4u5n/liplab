"""
LIPLAB 커리큘럼 콘텐츠 — 큐레이션 학습 자료 (기존엔 없던 '기초 단계'의 토대).

기존 앱은 문장 연습(LLM 생성)만 있었고 입모양 15종은 아바타 애니메이션에만 쓰였다.
이 모듈은 **입모양 자체를 가르치는** 1단계(입모양 인지) 콘텐츠를 정의한다.
순수 데이터 + 순수 함수 (DB·네트워크 의존 없음) → 결정론적으로 테스트 가능.

교육 원리
  · 모음(2·3·4·5·9)은 가장 잘 보이는 '닻' — 문장 뼈대를 여기서 잡는다.
  · 양순음(1: ㅁ/ㅂ/ㅃ/ㅍ)은 입술 닫힘이라 잘 보이지만 서로 구별 불가(동구형이음).
  · 입 안쪽 자음(6 치경·7 연구개·8 성문·10 경구개)은 겉모습이 거의 같아 문맥이 필요.
'무엇이 보이고 무엇이 안 보이는가'를 명시적으로 가르치는 것이 1단계의 목표.

viseme_id는 backend/engine.py VISEME_MAP(1~10 음소 그룹)과 1:1로 맞춘다.
"""
from typing import Dict, List, Optional

# visibility: 겉으로 드러나는 정도 (독화 난이도의 핵심 축)
#   high   = 뚜렷이 보임 (모음 닻, 양순 폐쇄)
#   medium = 어느 정도 보임
#   low    = 거의 안 보임 → 문맥 의존
VISEME_LESSONS: List[Dict] = [
    {
        "viseme_id": 1, "name": "양순음", "kind": "consonant",
        "phonemes": ["ㅁ", "ㅂ", "ㅃ", "ㅍ"], "visibility": "high",
        "look": "두 입술을 완전히 붙였다 뗀다. 닫히는 순간이 뚜렷이 보인다.",
        "teach": "잘 보이지만 ㅁ·ㅂ·ㅃ·ㅍ 서로는 똑같아 구별 못 한다(동구형이음). '입술이 닫혔다'까지만 읽고 나머지는 문맥으로.",
        "example_words": ["밥", "물", "팔", "엄마"],
    },
    {
        "viseme_id": 2, "name": "개방모음", "kind": "vowel",
        "phonemes": ["ㅏ", "ㅐ", "ㅑ", "ㅒ"], "visibility": "high",
        "look": "턱을 크게 아래로 내려 입을 크게 벌린다.",
        "teach": "가장 크게 벌어지는 모음. 문장에서 눈에 잘 띄는 닻이 된다.",
        "example_words": ["사과", "아빠", "하나", "나비"],
    },
    {
        "viseme_id": 3, "name": "전설모음", "kind": "vowel",
        "phonemes": ["ㅣ", "ㅔ", "ㅖ"], "visibility": "high",
        "look": "입술을 좌우로 길게 당긴다(옆으로 웃는 모양). 윗니가 살짝 보인다.",
        "teach": "좌우로 퍼지는 '이' 계열. 둥근 원순모음과 정반대라 구별이 쉽다.",
        "example_words": ["이", "시계", "비", "기린"],
    },
    {
        "viseme_id": 4, "name": "원순모음", "kind": "vowel",
        "phonemes": ["ㅗ", "ㅛ", "ㅜ", "ㅠ"], "visibility": "high",
        "look": "입술을 둥글게 오므려 앞으로 내민다('오/우' 모양).",
        "teach": "둥글게 내미는 모양이 뚜렷해 좋은 닻. 좌우로 퍼지는 전설모음과 확실히 다르다.",
        "example_words": ["오이", "우유", "소", "우산"],
    },
    {
        "viseme_id": 5, "name": "중설모음", "kind": "vowel",
        "phonemes": ["ㅓ", "ㅕ", "ㅡ"], "visibility": "medium",
        "look": "크게 벌리지도 둥글지도 않은 중립에 가깝게 살짝 벌린다.",
        "teach": "특징이 옅어 개방모음·원순모음보다 읽기 어렵다. 앞뒤 소리로 보완.",
        "example_words": ["어머니", "그림", "서점", "느낌"],
    },
    {
        "viseme_id": 6, "name": "치경음", "kind": "consonant",
        "phonemes": ["ㄷ", "ㄸ", "ㅌ", "ㄴ", "ㄹ", "ㅅ", "ㅆ"], "visibility": "low",
        "look": "혀끝을 윗잇몸 뒤에 대지만, 밖에서는 입이 살짝 벌어진 정도만 보인다.",
        "teach": "조음이 입 안쪽이라 ㄷ·ㄴ·ㄹ·ㅅ… 서로 거의 구별 불가. 문맥으로 판단.",
        "example_words": ["다리", "나무", "라디오", "사자"],
    },
    {
        "viseme_id": 7, "name": "연구개음", "kind": "consonant",
        "phonemes": ["ㄱ", "ㄲ", "ㅋ", "ㅇ"], "visibility": "low",
        "look": "혀 뒤를 목 안쪽에 붙인다. 겉으로는 거의 변화가 없다.",
        "teach": "가장 안 보이는 자음 중 하나. 입만 봐서는 있는지조차 알기 어렵다 → 전적으로 문맥.",
        "example_words": ["가방", "코", "강", "콩"],
    },
    {
        "viseme_id": 8, "name": "성문음", "kind": "consonant",
        "phonemes": ["ㅎ"], "visibility": "low",
        "look": "목에서 숨을 내쉬며 입을 살짝 연다. 고유한 입모양이 거의 없다.",
        "teach": "ㅎ은 겉으로 표시가 약하다. 종종 뒤 모음의 입모양에 묻힌다.",
        "example_words": ["하늘", "학교", "해", "호수"],
    },
    {
        "viseme_id": 9, "name": "이중모음", "kind": "vowel",
        "phonemes": ["ㅘ", "ㅙ", "ㅚ", "ㅝ", "ㅞ", "ㅟ", "ㅢ"], "visibility": "medium",
        "look": "둥글게 벌렸다가 다른 모음으로 미끄러지듯 움직인다.",
        "teach": "입모양이 '움직이는' 것이 단서. 한 컷이 아니라 변화를 읽는다.",
        "example_words": ["과자", "왜", "의사", "위"],
    },
    {
        "viseme_id": 10, "name": "경구개음", "kind": "consonant",
        "phonemes": ["ㅈ", "ㅉ", "ㅊ"], "visibility": "low",
        "look": "입술을 살짝 앞으로 내밀며 옆으로 조금 당긴다.",
        "teach": "치경음과 겉모습이 비슷해 헷갈린다. 살짝 내미는 느낌이 유일한 힌트.",
        "example_words": ["자전거", "차", "주스", "축구"],
    },
]

# 동구형이음 무리 — '서로 비슷하게 보여 독화로 구별하기 어려운' viseme 그룹들.
# 1단계의 핵심 교육 포인트: 이 무리 안에서는 입모양만으로 못 가르니 문맥이 필수.
HOMOPHENE_CLUSTERS: List[Dict] = [
    {
        "id": "lips", "name": "입술 닫힘", "viseme_ids": [1],
        "note": "ㅁ·ㅂ·ㅃ·ㅍ은 입술이 닫혀 겉으로는 똑같이 보인다. 무리 안 구별은 문맥으로.",
    },
    {
        "id": "inside", "name": "입 안쪽 자음", "viseme_ids": [6, 7, 8, 10],
        "note": "치경·연구개·성문·경구개음은 혀·목 안쪽 조음이라 겉모습이 거의 같다. 독화로 가장 어려운 무리.",
    },
]

# 가장 뚜렷한 '닻' — 문장 골격을 잡는 출발점(교육 강조용).
VISIBLE_ANCHORS: List[int] = [2, 3, 4]  # 개방·전설·원순 모음

# 최소대립쌍 — 한 음소만 다른 단어쌍으로 '같아 보임/다르게 보임'을 체감시킨다.
#   same_looking=True  → 입모양이 같아 구별 불가(문맥 필요)를 가르침
#   same_looking=False → 입모양이 달라 구별 가능함을 가르침
MINIMAL_PAIRS: List[Dict] = [
    {"a": "밥", "b": "맘", "visemes": [1], "same_looking": True,
     "note": "ㅂ↔ㅁ 양순음. 입술 닫힘이 똑같아 구별 불가."},
    {"a": "바다", "b": "파도", "visemes": [1], "same_looking": True,
     "note": "ㅂ↔ㅍ 양순음. 첫 입모양이 동일."},
    {"a": "물", "b": "불", "visemes": [1], "same_looking": True,
     "note": "ㅁ↔ㅂ 양순음."},
    {"a": "달", "b": "탈", "visemes": [6], "same_looking": True,
     "note": "ㄷ↔ㅌ 치경음. 입 안쪽이라 겉모습 동일."},
    {"a": "살", "b": "쌀", "visemes": [6], "same_looking": True,
     "note": "ㅅ↔ㅆ. 구별 불가."},
    {"a": "자요", "b": "차요", "visemes": [10], "same_looking": True,
     "note": "ㅈ↔ㅊ 경구개음."},
    {"a": "밥", "b": "입", "visemes": [1, 2], "same_looking": False,
     "note": "입술 닫힘(밥) vs 크게 벌림(입) — 뚜렷이 다르다."},
    {"a": "우유", "b": "이유", "visemes": [4, 3], "same_looking": False,
     "note": "둥근 입(우) vs 옆으로 퍼진 입(이) — 정반대."},
    {"a": "말", "b": "발", "visemes": [1], "same_looking": True,
     "note": "ㅁ↔ㅂ 양순음."},
    {"a": "자", "b": "차", "visemes": [10], "same_looking": True,
     "note": "ㅈ↔ㅊ 경구개음."},
]

# 각 그룹의 대표 음절 — 아바타로 그 입모양 하나를 명확히 보여줄 때 사용.
#   자음은 초성으로, 모음은 그 자체로 해당 viseme가 도드라진다.
DEMO_SYLLABLE: Dict[int, str] = {
    1: "마", 2: "아", 3: "이", 4: "우", 5: "어",
    6: "다", 7: "가", 8: "하", 9: "와", 10: "자",
}

# 단계형 커리큘럼 척추(5단계). 0·1은 신설, 2는 Phase 2 예정, 3·4는 기존 모드에 연결.
STAGES: List[Dict] = [
    {"stage": 0, "key": "onboarding", "title": "입문·배치", "desc": "독화가 뭔지 + 나에게 맞는 시작점", "kind": "intro"},
    {"stage": 1, "key": "viseme", "title": "입모양 인지", "desc": "10개 입모양 그룹을 익힌다", "kind": "literacy", "route": "/learn/viseme"},
    {"stage": 2, "key": "word", "title": "음절·단어", "desc": "최소대립쌍으로 단어 독화", "kind": "word", "route": "/learn/word"},
    {"stage": 3, "key": "sentence", "title": "문장 (상황별)", "desc": "상황별 문장 독화 연습", "kind": "sentence", "route": "/practice"},
    {"stage": 4, "key": "conversation", "title": "대화 실전", "desc": "AI와 실전 대화", "kind": "conversation", "route": "/conversation"},
]

_BY_ID: Dict[int, Dict] = {l["viseme_id"]: l for l in VISEME_LESSONS}


def lesson_by_id(viseme_id: int) -> Optional[Dict]:
    """viseme_id(1~10)로 레슨 1건 조회. 없으면 None."""
    return _BY_ID.get(viseme_id)


def consonant_lessons() -> List[Dict]:
    return [l for l in VISEME_LESSONS if l["kind"] == "consonant"]


def vowel_lessons() -> List[Dict]:
    return [l for l in VISEME_LESSONS if l["kind"] == "vowel"]


def homophene_cluster_of(viseme_id: int) -> Optional[Dict]:
    """해당 viseme가 속한 동구형이음 무리(없으면 None)."""
    for c in HOMOPHENE_CLUSTERS:
        if viseme_id in c["viseme_ids"]:
            return c
    return None


def same_homophene_cluster(a: int, b: int) -> bool:
    """두 viseme가 '서로 비슷하게 보이는' 같은 무리인지."""
    if a == b:
        return True
    ca = homophene_cluster_of(a)
    return ca is not None and b in ca["viseme_ids"]


def all_viseme_ids() -> List[int]:
    """가르치는 viseme 그룹 id 목록(1~10)."""
    return [l["viseme_id"] for l in VISEME_LESSONS]


def quizzable_lessons() -> List[Dict]:
    """겉으로 구별 가능한 그룹만(인지퀴즈 대상). 입 안쪽 자음(visibility='low')은
    애초에 입모양만으로 구별 불가라 퀴즈에서 제외하고 '문맥 필요'로 가르친다."""
    return [l for l in VISEME_LESSONS if l["visibility"] != "low"]


# ── 2단계: 큐레이션 단어(음절·단어) ──────────────────────────────────────────
# tier 1: 시각적으로 뚜렷이 구별되는 쉬운 단어 / tier 2: 최소대립(비슷하게 보이는)이 섞임
WORD_BANK: List[Dict] = [
    {"word": "밥", "tier": 1}, {"word": "물", "tier": 1}, {"word": "이", "tier": 1},
    {"word": "우유", "tier": 1}, {"word": "사과", "tier": 1}, {"word": "가방", "tier": 1},
    {"word": "하늘", "tier": 1}, {"word": "바다", "tier": 1}, {"word": "나무", "tier": 1},
    {"word": "오이", "tier": 1}, {"word": "코", "tier": 1}, {"word": "자", "tier": 1},
    {"word": "맘", "tier": 2}, {"word": "불", "tier": 2}, {"word": "파도", "tier": 2},
    {"word": "달", "tier": 2}, {"word": "탈", "tier": 2}, {"word": "살", "tier": 2},
    {"word": "쌀", "tier": 2}, {"word": "말", "tier": 2}, {"word": "발", "tier": 2},
    {"word": "차", "tier": 2}, {"word": "그림", "tier": 2}, {"word": "서점", "tier": 2},
]

_WORDS = {w["word"] for w in WORD_BANK}

# 최소대립 파트너 색인(양방향) — 비슷하게 보이는 단어를 오답 보기로 우선 제시
_PAIR_PARTNER: Dict[str, set] = {}
for _m in MINIMAL_PAIRS:
    _PAIR_PARTNER.setdefault(_m["a"], set()).add(_m["b"])
    _PAIR_PARTNER.setdefault(_m["b"], set()).add(_m["a"])


def is_word(word: str) -> bool:
    return word in _WORDS


def word_partners(word: str) -> List[str]:
    """해당 단어와 '비슷하게 보이는' 최소대립 파트너(단어은행에 있는 것만)."""
    return [p for p in _PAIR_PARTNER.get(word, ()) if p in _WORDS]


# ── 3단계: 문맥 추론(closure) — 같아 보이는 단어를 문맥으로 판단 ──────────────
# options는 입모양이 비슷해 눈으로는 구별이 어렵다 → 문장의 '문맥'으로 답을 골라야 한다.
# display의 ___에 answer를 넣으면 전체 문장(아바타 애니메이션용).
CLOSURE_ITEMS = [
    {"id": "c1", "display": "___을 먹었어요", "answer": "밥", "options": ["밥", "맘", "발"], "hint": "'먹다'와 어울리는 건?"},
    {"id": "c2", "display": "___을 마셔요", "answer": "물", "options": ["물", "불", "풀"], "hint": "'마시다'와 어울리는 건?"},
    {"id": "c3", "display": "___이 밝아요", "answer": "달", "options": ["달", "탈", "살"], "hint": "'밝다'와 어울리는 건?"},
    {"id": "c4", "display": "___를 마셔요", "answer": "차", "options": ["차", "자", "짜"], "hint": "마시는 것 중 하나."},
    {"id": "c5", "display": "___을 던져요", "answer": "공", "options": ["공", "곰", "콩"], "hint": "'던지다'와 어울리는 둥근 것?"},
]
