"""
말하기·촉각(타도마) 연습용 '단어/문장' AI 생성기.

핵심 목표: 매번 다른 문제. 같은 프롬프트를 반복하면 LLM도 비슷한 답을 내므로,
호출마다 무작위 '변주 축'(범주·주제·기능)과 시드, 그리고 '제외 목록'을 주입해
결과가 겹치지 않게 한다. 실패 시 호출부가 큐레이션 풀로 폴백한다(내부 except 없음 — 호출부 책임).
"""
import json
import random
from typing import List

from llm_service import anthropic_client

_MODEL = "claude-sonnet-4-6"

# 단어 생성용 범주 — 매 호출 몇 개를 무작위로 골라 다양성을 강제
_WORD_CATEGORIES = [
    "음식", "과일·채소", "동물", "자연·날씨", "사물·도구", "장소", "신체 부위",
    "탈것", "옷·색깔", "가족·사람", "학교·공부", "감정", "집안 물건", "직업",
]
# 문장 생성용 의사소통 기능 + 장면
_SENT_FUNCTIONS = ["요청·부탁", "질문", "감사", "인사", "사과", "제안·권유", "감탄", "안내·설명", "약속", "확인"]
_SENT_SCENES = ["카페·식당", "길 찾기", "쇼핑", "병원·약국", "학교", "가족·집", "날씨·계절", "취미·여가", "여행", "일상 대화"]


async def _call(system: str, expect_key: str = "items") -> List[str]:
    """LLM 호출 → JSON {expect_key: [...]} 파싱. 실패는 예외로 올려 호출부가 폴백."""
    resp = await anthropic_client.messages.create(
        model=_MODEL,
        max_tokens=512,
        temperature=1.0,           # 변주 극대화
        system=system,
        messages=[{"role": "user", "content": f"변주 시드 {random.randint(1000, 9999)} — 새롭게 생성"}],
    )
    content = resp.content[0].text.strip()
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()
    data = json.loads(content)
    items = data.get(expect_key, [])
    items = [str(x).strip() for x in items if str(x).strip()]
    return items


async def generate_words(n: int = 10, max_syllable: int = 3, avoid: List[str] = None) -> List[str]:
    """발음/촉각 연습용 한국어 단어 n개. 매번 다른 범주·어휘."""
    avoid = avoid or []
    cats = random.sample(_WORD_CATEGORIES, k=min(4, len(_WORD_CATEGORIES)))
    system = (
        "너는 청각장애인의 발음·촉각 훈련용 한국어 '단어' 출제기다.\n"
        f"- 아래 범주에서 골고루 뽑아 다양하게: {', '.join(cats)}\n"
        f"- 1~{max_syllable}음절의 실제 자주 쓰는 일반 명사만. 외래어·고유명사·비속어·추상어 금지.\n"
        "- 발음이 또렷한 기본 어휘 위주(아이도 아는 수준).\n"
        "- 매 회차 새롭고 겹치지 않게. 아래 '제외' 목록 단어는 절대 쓰지 말 것.\n"
        f"제외: {', '.join(avoid[:50]) if avoid else '(없음)'}\n"
        f'반드시 JSON만 출력: {{"items": ["단어", ...]}} — 정확히 {n}개.'
    )
    return await _call(system)


async def generate_sentences(n: int = 8, avoid: List[str] = None, with_intonation: bool = False) -> List[dict]:
    """연습용 짧은 문장 n개. with_intonation이면 [{target, intonation}] 형태."""
    avoid = avoid or []
    funcs = random.sample(_SENT_FUNCTIONS, k=min(4, len(_SENT_FUNCTIONS)))
    scene = random.choice(_SENT_SCENES)
    kind = (
        '{"target": "문장", "intonation": "fall|rise"}  (평서문=fall, 의문문=rise)'
        if with_intonation else '"문장"'
    )
    system = (
        "너는 청각장애인의 발화·촉각 훈련용 한국어 '짧은 문장' 출제기다.\n"
        f"- 장면: {scene} / 의사소통 기능을 섞어 다양하게: {', '.join(funcs)}\n"
        "- 6~12자 내외의 일상 구어체 한 문장. 너무 길거나 복잡하지 않게.\n"
        "- 매 회차 새롭고 겹치지 않게. 아래 '제외' 문장은 쓰지 말 것.\n"
        f"제외: {', '.join(avoid[:40]) if avoid else '(없음)'}\n"
        f'반드시 JSON만 출력: {{"items": [{kind}, ...]}} — 정확히 {n}개.'
    )
    if with_intonation:
        resp = await anthropic_client.messages.create(
            model=_MODEL, max_tokens=512, temperature=1.0, system=system,
            messages=[{"role": "user", "content": f"변주 시드 {random.randint(1000, 9999)} — 새롭게 생성"}],
        )
        content = resp.content[0].text.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        data = json.loads(content)
        out = []
        for it in data.get("items", []):
            t = str(it.get("target", "")).strip()
            if not t:
                continue
            into = it.get("intonation") or ("rise" if t.rstrip().endswith("?") else "fall")
            out.append({"target": t, "intonation": "rise" if into == "rise" else "fall"})
        return out
    return [{"target": t} for t in await _call(system)]
