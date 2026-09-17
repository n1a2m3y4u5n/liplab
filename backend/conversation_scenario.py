"""
다자 대화 시나리오 생성 — 고도화 축 H.

계획서 §3.8: 실제 대화는 화자가 여럿이고 발화 순서가 수시로 바뀌며, 듣는 사람은 '지금 누가
말하는지'부터 가려야 한다. 현행 훈련은 한 화자의 한 문장씩만 다뤄 실제 상황과 거리가 있다.
이 모듈은 여러 화자가 번갈아 말하는 짧은 일상 대화를 생성해, 화자 식별 + 입모양 읽기를 함께
훈련하는 실전 독화의 콘텐츠를 만든다(콘텐츠 대량화 G의 문장을 다화자 상황으로 재조합).
"""
import random
import llm_json
from typing import Dict, List, Optional

from llm_service import anthropic_client

_MODEL = "claude-sonnet-4-6"
_SCENES = ["카페", "병원 대기실", "학교 교실", "가족 저녁 식사", "가게 계산대", "친구 모임"]

# LLM 실패(키 없음·파싱 오류)시 결정론적 폴백 — 500/무한로딩 방지. 장면별 짧은 구어체 대화.
_FALLBACK_LINES = {
    "카페": ["뭐 마실래?", "따뜻한 걸로 줘", "여기 자리 좋다", "그러게 조용하네", "케이크도 먹을까?", "좋아 하나 시키자"],
    "병원 대기실": ["많이 기다렸어?", "삼십 분 됐어", "번호표 뽑았어?", "응 여기 있어", "곧 부를 거야", "다행이다"],
    "학교 교실": ["숙제 했어?", "아직 못 했어", "같이 할까?", "그래 도와줘", "점심 뭐 먹지?", "매점 가자"],
    "가족 저녁 식사": ["밥 다 됐어", "맛있겠다", "국 좀 더 줘", "천천히 먹어", "오늘 어땠어?", "재밌었어요"],
    "가게 계산대": ["이거 얼마예요?", "삼천 원이요", "봉투 주세요", "네 여기요", "카드 될까요?", "그럼요 됩니다"],
    "친구 모임": ["오랜만이야", "잘 지냈어?", "그럭저럭 지냈어", "얼굴 좋아 보여", "다음에 또 보자", "꼭 연락해"],
}


def _fallback_conversation(speakers: int, turns: int, scene: str) -> Dict:
    lines = _FALLBACK_LINES.get(scene) or _FALLBACK_LINES["카페"]
    out = []
    for i in range(turns):
        out.append({"speaker": i % speakers, "text": lines[i % len(lines)]})
    return {"scene": scene, "speakers": speakers, "turns": out, "fallback": True}


async def generate_multi_conversation(speakers: int = 2, turns: int = 6,
                                      scene: Optional[str] = None) -> Dict:
    """N명이 나누는 짧은 일상 대화. 각 턴은 {speaker, text}. 화자가 번갈아 말한다."""
    speakers = max(2, min(speakers, 3))
    turns = max(3, min(turns, 10))
    scene = scene or random.choice(_SCENES)
    system = (
        f"너는 청각장애인 독화 훈련용 '다자 대화' 출제기다.\n"
        f"- {speakers}명이 '{scene}'에서 나누는 자연스러운 일상 대화를 만든다.\n"
        "- 각 턴은 6~14자의 짧은 구어체 한 문장. 화자는 번갈아 말하되 가끔 순서가 바뀌어도 된다.\n"
        f"- 화자 번호는 0~{speakers - 1}. 첫 턴은 0번부터.\n"
        f'반드시 JSON만 출력: {{"turns": [{{"speaker": 0, "text": "문장"}}, ...]}} — 정확히 {turns}턴.'
    )
    try:
        resp = await anthropic_client.messages.create(
            model=_MODEL, max_tokens=600, temperature=1.0, system=system,
            messages=[{"role": "user", "content": f"변주 시드 {random.randint(1000, 9999)}"}],
        )
        data = llm_json.extract_json(resp)
        out_turns: List[Dict] = []
        for t in data.get("turns", []):
            text = str(t.get("text", "")).strip()
            if not text:
                continue
            spk = int(t.get("speaker", 0)) % speakers
            out_turns.append({"speaker": spk, "text": text})
        if len(out_turns) < 3:   # 응답이 부실하면 폴백
            return _fallback_conversation(speakers, turns, scene)
        return {"scene": scene, "speakers": speakers, "turns": out_turns}
    except Exception as e:
        # 키 없음·네트워크·파싱 실패 → 결정론적 대화로 폴백(엔드포인트 500·프론트 무한로딩 방지)
        print(f"[WARN] multi-conversation LLM failed, using fallback: {e}")
        return _fallback_conversation(speakers, turns, scene)
