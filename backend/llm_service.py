"""
Adaptive Scenario Generation using Claude API
Generates contextually relevant sentences based on user's weak visemes
"""
import json
import os
import random
import re
import llm_json
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from anthropic import AsyncAnthropic
import llm_budget
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from database import WeakViseme, ScenarioCache
from engine import get_viseme_feature


# Initialize Anthropic client
# 기본값(600초, 재시도 2번)이면 느린 응답 하나가 코칭·채점 응답을 붙잡아 화면 제한(60초)을 넘긴다.
# 이 앱의 호출은 모두 1024토큰 이하라 30초·재시도 1번이면 넉넉하고, 넘으면 각 호출의 대체 경로로 간다.
anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"), timeout=30.0, max_retries=1)
# 하루 호출 한도(서버 전체·IP별). 넘으면 BudgetExceeded가 나고 호출하는 쪽의 대체 경로로 간다(llm_budget.py)
llm_budget.guard(anthropic_client)


async def generate_speaking_coaching(target: str, transcript: str, score: float,
                                     confusions: list = None, metrics: dict = None,
                                     weak_phones: list = None, intonation: bool = False, method: str = None) -> str:
    """발화 채점 + 측정값(크기·억양·길이)을 근거로 '수치 기반·구체적' 발음 코칭.
    Whisper 오인식 가능성을 감안해 발음 부분은 단정하지 않고 부드럽게. 실패 시 규칙 폴백.
    weak_phones: D-GOP가 가장 약하게 잰 소리들 [{label, dgop(0~1), position}] — 전사와 무관하게 목표 소리 자리에서
    잰 값이라, 음성인식이 틀려도 '어느 소리가 약했는지'를 짚을 수 있다(축 B-9). position이 '종성'이면 '받침 ㅂ'처럼 부르고
    받침 조음 문장을 준다(예전에는 받침 ㅂ·ㄱ·ㄷ에도 '떼며 터뜨립니다', 받침 ㄹ에 '한 번 튕깁니다'가 나갔다).
    intonation: 억양(음높이 폭)을 코칭에 넣을지. 문장 연습에서 기대 방향 규칙(speak_curriculum.score_attempt)이 따로
    판정하지 않았을 때만 True다. 한 음절·단어는 음높이가 고른 게 자연스러운데, 예전에는 모든 모드에서 폭 25Hz 미만이면
    '톤이 평평하니 끝을 올리거나 내리라'고 했고, 문장에서는 방향 규칙의 안내('끝을 내려보세요')와 겹쳤다.
    method: 채점 경로(main.speak_assess의 assessment_method). 'dgop'이면 전사를 하지 않으므로 '음성인식 결과' 줄과 '~로 들렸어요'
    주의를 빼고 '발음 채점 점수 N점(음성인식 아님)'으로 적는다. 예전에는 transcript None이 '(잘 인식되지 않음)'으로 들어가, 92점으로
    잘 말한 시도도 모델에게 '인식되지 않았다'는 거짓 입력이 됐다(dev의 2~5단계 코칭 전부)."""
    conf_txt = ""
    if confusions:
        conf_txt = "다르게 들린 소리: " + ", ".join(f"{c.get('correct')}→{c.get('confused_as')}" for c in confusions[:4]) + "\n"
    def _name(j, pos):   # 받침이면 위치를 붙여 부른다(첫소리 ㅂ과 받침 ㅂ은 내는 법이 다르다)
        return f"받침 {j}" if pos == "종성" else j

    weak_txt = ""
    if weak_phones:
        # D-GOP 원점수는 보정 전 값이라 절대 수치로 말하면 잘 낸 소리도 낮아 보인다 — 문장 안의 상대 비교로만 전한다.
        weak_txt = ("이 발화 안에서 다른 소리보다 약하게 잰 소리(음성인식과 무관한 발음 채점, 상대 비교): "
                    + ", ".join(f"'{_name(w['label'], w.get('position'))}'" for w in weak_phones[:3]) + "\n")
    # 다르게 들린 소리·약한 소리의 조음 설명을 참고로 준다(articulation.jamo_tip). 없으면 모델이 조음 설명을 지어낸다.
    import articulation as _art
    tips, seen = [], set()
    refs = ([(c.get("correct"), None) for c in (confusions or [])[:3]]
            + [(w.get("label"), w.get("position")) for w in (weak_phones or [])[:3]])
    for j, pos in refs:
        name = _name(j, pos)
        t = _art.jamo_tip(j, pos) if j and name not in seen else None
        if t:
            seen.add(name)
            tips.append(f"'{name}' — {t}")
    art_txt = ("조음 참고(정확한 설명이니 이것을 바탕으로): " + " / ".join(tips[:3]) + "\n") if tips else ""
    met_txt = ""
    m = metrics or {}
    parts = []
    if m.get("loudness") is not None:
        parts.append(f"목소리 크기 {round(m['loudness'])}/100")
    if intonation and m.get("pitch_range"):
        parts.append(f"억양 변화 {round(m['pitch_range'])}Hz")
    if m.get("duration"):
        parts.append(f"발화 길이 {float(m['duration']):.1f}초")
    if parts:
        met_txt = "측정값 — " + ", ".join(parts) + "\n"

    good_axes = "발음 점수·크기·억양" if intonation else "발음 점수·크기"
    tone_rule = ("   - 억양 변화 25Hz 미만이면 톤이 평평하다고 알리고 문장 끝을 올리거나 내리라고.\n" if intonation
                 else "   - 억양(음높이)은 말하지 않기(이 연습은 소리·발음만 본다).\n")
    dgop = method == "dgop"
    if dgop:
        head = f'목표: "{target}" / 발음 채점 점수 {round(score)}점(음성인식 아님)'
        weak_note, caution = "", ""
    else:
        heard = transcript or "(잘 인식되지 않음)"
        head = f'목표: "{target}" / 음성인식 결과: "{heard}" / 발음 유사도 {round(score)}점'
        weak_note = "(음성인식 결과와 달라도 이 값을 믿어도 됨)"
        caution = '\n주의: 음성인식은 완벽하지 않으니 발음 부분은 단정하지 말고 "~로 들렸어요" 식으로 부드럽게.'
    prompt = f"""당신은 청각장애인의 발음(구화) 연습을 돕는 따뜻하고 구체적인 코치입니다.
{head}
{conf_txt}{weak_txt}{art_txt}{met_txt}
아래 지침으로 한국어 3~5문장(250자 이내, 번호·머리말 없이 자연스럽게):
1) 잘한 점을 측정값 근거로 구체적으로({good_axes} 중 좋았던 것을 수치와 함께).
2) 개선점을 '수치 + 방법'으로 구체적으로:
   - 목소리 크기 40/100 미만이면 더 크게 말하라고 강조.
{tone_rule}   - 다르게 들린 소리가 있으면 그 소리를 입술/혀를 '어떻게' 하는지 구체적으로.
   - 약하게 잰 소리가 있으면 그중 하나를 골라 입술·혀를 어떻게 하는지 알려 주기{weak_note}.
3) 짧은 격려.{caution}
{PLAIN_KO_STYLE}"""
    try:
        resp = await anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception:
        bits = []
        if m.get("loudness", 100) < 40:
            bits.append(f"목소리가 작았어요(크기 {round(m.get('loudness', 0))}/100). 배에 힘을 주고 더 크게 말해보세요.")
        if intonation and m.get("pitch_range") is not None and m.get("pitch_range", 100) < 25:
            bits.append("톤이 평평했어요. 문장 끝을 올리거나 내리며 억양을 넣어보세요.")
        if confusions:
            c = confusions[0]
            tip = _art.jamo_tip(c.get("correct"))
            bits.append(f"'{c.get('correct')}' 소리가 '{c.get('confused_as')}'로 들렸어요. "
                        + (tip or "입모양을 더 또렷하게 해보세요."))
        elif weak_phones:
            w = weak_phones[0]
            tip = _art.jamo_tip(w["label"], w.get("position"))
            bits.append(f"'{_name(w['label'], w.get('position'))}' 소리가 약하게 났어요. "
                        + (tip or "그 음절에서 입을 조금 더 크게, 천천히 움직여 보세요."))
        if not bits:
            bits.append("또렷하게 잘 전달됐어요! 이 느낌을 기억하며 다음 단어도 도전해봐요.")
        return " ".join(bits)


# 학습자가 읽는 글의 문체 규칙(쉬운 한국어 감사 C15, docs/easy-korean-audit.md). 선천·조기 청력 손실 학습자에게 한국어 글은
# 제2언어이거나 읽기 수준이 낮을 수 있다. 길이·형식 같은 로직은 각 프롬프트의 기존 지시를 따르고, 낱말과 문장 끊기만 더한다.
PLAIN_KO_STYLE = ("문체: 학습자에게 한국어 글은 제2언어일 수 있습니다. 일상에서 흔히 쓰는 쉬운 낱말로 쓰고, 한 문장은 짧게(30자 안팎) "
                  "끊으세요. 음소·조음·포먼트 같은 전문 용어는 쓰지 마세요.")
PLAIN_KO_WORDS = "일상에서 흔히 쓰는 쉬운 낱말을 쓰고, 전문 용어나 어려운 한자어는 피하세요(문장 길이는 위 기준을 따릅니다)."

# Situation-based context prompts
# 상황별 시나리오 문장의 글자 수 상한(난이도별 어절 수 지시에 맞춤: 1단계 5~8어절부터 5단계 15어절 이상까지)
SCENARIO_MAX_CHARS = {1: 40, 2: 45, 3: 60, 4: 70, 5: 90}
# 단계별 최소 어절 수(지시 하한보다 2 적게): 3·4단계가 2단계보다 짧은 문장을 내던 것을 거른다. 1단계는 짧아도 된다(대체 문장도 3~4어절)
SCENARIO_MIN_WORDS = {1: 1, 2: 5, 3: 8, 4: 10, 5: 13}

# 대화 실전에서 LLM이 실패했을 때 상대가 말하는 대체 대사(온전한 문장). 없는 상황은 어느 자리에나 맞는 대사.
# 대화가 흘러가는 순서로 적고, 상황마다 1단계 길이(_CONV_MAX_CHARS 9자) 안의 대사를 4개 이상 둔다(fallback_turn이 단계 길이
# 안에서 아직 안 한 대사를 고른다). 9/28 감사 전에는 상황마다 4개뿐이고 1단계에 맞는 것이 2~4개였으며, 대화 기록 길이(학습자
# 턴까지 세어 2씩 는다)로 골라 같은 두 대사만 번갈아 나왔다.
FALLBACK_TURNS = {
    "카페": ["어서 오세요.", "뭘로 드릴까요?", "따뜻한 걸로 드릴까요?", "드시고 가세요?", "진동벨로 알려 드릴게요.",
           "영수증 드릴까요?", "맛있게 드세요."],
    "병원": ["어디가 아프세요?", "언제부터 아프셨어요?", "열도 나세요?", "기침도 하세요?", "여기 누워 보세요.",
           "약은 하루 세 번 드세요.", "푹 쉬세요.", "몸조리 잘하세요."],
    "식당": ["어서 오세요.", "몇 분이세요?", "이쪽으로 앉으세요.", "주문하시겠어요?", "맵게 해 드릴까요?", "음식 나왔습니다.",
           "맛있게 드세요.", "계산 도와드릴게요."],
    "은행": ["번호표 뽑으셨어요?", "어떤 업무 보러 오셨어요?", "신분증 있으세요?", "통장 주세요.", "여기에 서명해 주세요.",
           "처리됐습니다.", "더 필요한 거 있으세요?", "안녕히 가세요."],
    "쇼핑": ["어서 오세요.", "찾으시는 거 있으세요?", "입어 보시겠어요?", "사이즈 맞으세요?", "이건 할인 중이에요.",
           "봉투 필요하세요?", "또 오세요."],
    "대중교통": ["어디까지 가세요?", "카드 대 주세요.", "꽉 잡으세요.", "이 버스 타시면 돼요.", "두 정거장 남았어요.",
             "다음 역에서 내리세요.", "조심히 가세요."],
}
FALLBACK_TURNS_GENERIC = ["안녕하세요.", "무엇을 도와드릴까요?", "네, 알겠습니다.", "잠시만 기다려 주세요.", "감사합니다.",
                          "또 뵐게요."]

# 상황별 문장 생성이 실패하고 같은 상황·단계의 저장 문장도 없을 때 쓰는 단계별 대체 문장(9/27). 예전에는 단계와 상관없이
# 2~4어절 문장만 나가 5단계 학습자도 "안녕하세요."를 받았다. 어절 수는 단계 지시(level_instructions)에 맞췄다.
FALLBACK_BY_LEVEL = {
    1: ["오늘은 날씨가 정말 맑고 좋네요.", "저는 아침마다 공원에서 산책을 해요.", "이 버스는 시청 앞에서 서나요?",
        "물 한 잔만 가져다주실 수 있나요?", "주말에 가족과 함께 영화를 봤어요.", "내일 아침 아홉 시에 만나요."],
    2: ["오늘 퇴근하고 나서 같이 저녁 먹으러 갈래요?", "죄송하지만 제가 잘 못 들어서 조금만 천천히 말씀해 주세요.",
        "이번 주 토요일에 친구 생일 파티가 있어요.", "여기서 지하철역까지 걸어서 가면 시간이 얼마나 걸릴까요?",
        "비가 올 것 같으니까 우산을 꼭 챙겨 가세요.", "어제 산 신발이 조금 작아서 바꾸고 싶어요."],
    3: ["다음 주 월요일에 회의가 있으니까 자료를 미리 준비해 두면 좋겠어요.",
        "제가 지난번에 빌려 간 책을 아직 다 못 읽어서 조금 늦게 돌려드릴게요.",
        "요즘 날씨가 갑자기 추워져서 주변에 감기에 걸린 사람이 많다고 하네요.",
        "은행에 가서 통장을 새로 만들려면 신분증을 꼭 가지고 가야 해요.",
        "주문하신 음식이 주방 사정으로 조금 늦어지고 있으니 잠시만 기다려 주세요.",
        "버스를 타고 가다가 내릴 정류장을 놓쳐서 한 정거장 더 갔어요."],
    4: ["비가 많이 와서 퇴근길 버스가 평소보다 훨씬 붐빌 것 같으니 조금 일찍 출발하세요.",
        "병원에서 받은 약은 밥을 먹고 삼십 분 뒤에 물과 함께 드시면 됩니다.",
        "공항 가는 기차표를 미리 끊어 두지 않으면 주말에는 자리가 금방 없어질 거예요.",
        "제가 카페에서 커피를 주문하면서 케이크도 하나 같이 포장해 달라고 부탁했는데 깜빡하셨나 봐요.",
        "이번 달 전기 요금이 지난달보다 두 배나 많이 나와서 관리사무소에 한번 물어보려고 해요.",
        "오늘은 밖에 바람이 많이 부니까 모자랑 목도리를 꼭 챙기고 따뜻하게 입고 나가세요."],
    5: ["어제 시장에서 산 배가 너무 달아서 배가 부를 때까지 먹었더니 배를 타고 가는 내내 속이 불편했어요.",
        "친구와 밤늦게까지 밤을 까먹으면서 이야기하다 보니 말이 많아져서 결국 하고 싶던 말을 다 하지는 못했어요.",
        "눈이 많이 내린 날 눈이 부셔서 눈을 제대로 뜰 수가 없어 선글라스를 쓰고 천천히 걸어갔어요.",
        "지난주에 다리를 다쳐서 병원에 가려고 강 위의 다리를 건너는데 바람이 세게 불어서 발걸음을 옮기기가 정말 힘들었어요.",
        "따뜻한 차를 마시면서 차를 고치는 방법을 찾아봤는데 부품 값이 생각보다 비싸서 결국 정비소에 맡기기로 했어요.",
        "방금 받은 문자를 보니 모레 오후에 보기로 한 약속이 미뤄져서 다음 주 금요일 저녁에 다시 만나기로 했대요."],
}

SITUATION_CONTEXTS = {
    "카페": {
        "description": "카페에서 주문하고 대화하는 상황",
        "keywords": ["주문", "커피", "음료", "케이크", "자리", "영수증", "포장", "매장"],
        "common_phrases": ["주세요", "부탁드려요", "괜찮아요", "감사합니다"]
    },
    "병원": {
        "description": "병원 진료실이나 약국에서의 상황",
        "keywords": ["증상", "아프다", "처방", "약", "진료", "예약", "접수", "검사"],
        "common_phrases": ["어디가 아프세요", "언제부터", "괜찮으세요", "복용하세요"]
    },
    "식당": {
        "description": "식당에서 주문하고 식사하는 상황",
        "keywords": ["메뉴", "맛", "주문", "반찬", "계산", "포장", "예약", "인분"],
        "common_phrases": ["추천해주세요", "맛있어요", "주세요", "계산해주세요"]
    },
    "은행": {
        "description": "은행 창구나 ATM 사용 상황",
        "keywords": ["계좌", "입금", "출금", "이체", "통장", "카드", "비밀번호", "수수료"],
        "common_phrases": ["처리해주세요", "확인해주세요", "됩니까", "부탁드립니다"]
    },
    "쇼핑": {
        "description": "상점이나 마트에서 쇼핑하는 상황",
        "keywords": ["가격", "할인", "사이즈", "색상", "환불", "교환", "결제", "포장"],
        "common_phrases": ["얼마예요", "있어요", "보여주세요", "할인되나요"]
    },
    "대중교통": {
        "description": "버스, 지하철, 택시 이용 상황",
        "keywords": ["정류장", "노선", "요금", "환승", "목적지", "시간", "표", "카드"],
        "common_phrases": ["가나요", "타야해요", "내려주세요", "얼마나 걸려요"]
    }
}


# Viseme focus mapping for targeting weak areas
VISEME_PHONEME_MAP = {
    1: ["ㅂ", "ㅃ", "ㅍ", "ㅁ"],  # Bilabial
    2: ["ㅏ", "ㅐ", "ㅑ", "ㅒ"],  # Open vowels
    3: ["ㅣ", "ㅔ", "ㅖ"],        # Front vowels
    4: ["ㅗ", "ㅛ", "ㅜ", "ㅠ"],  # Rounded vowels
    5: ["ㅓ", "ㅕ", "ㅡ"],        # Central vowels
    6: ["ㄷ", "ㄸ", "ㅌ", "ㄴ", "ㄹ", "ㅅ", "ㅆ"],  # Alveolar
    7: ["ㄱ", "ㄲ", "ㅋ", "ㅇ"],  # Velar
    8: ["ㅎ"],                    # Glottal
    9: ["ㅘ", "ㅙ", "ㅚ", "ㅝ", "ㅞ", "ㅟ", "ㅢ"],  # Diphthongs
    10: ["ㅈ", "ㅉ", "ㅊ"],       # Palatal
}


async def get_user_weak_visemes(user_id: int, db: AsyncSession, limit: int = 3) -> List[Dict]:
    """
    Retrieve user's top weak visemes from database
    Returns list of {viseme_id, feature, error_rate}
    순위는 지식추적 숙달도가 낮은 순(knowledge_tracing.rank_weak). 예전 오류 횟수 순은 자주 나오는 입모양을 표적으로 삼았다.
    """
    import knowledge_tracing as _kt
    result = await db.execute(select(WeakViseme).where(WeakViseme.user_id == user_id))
    rows = result.scalars().all()
    feature = {wv.viseme_id: wv.phonological_feature for wv in rows}
    ranked = _kt.rank_weak([{"viseme_id": wv.viseme_id, "error_count": wv.error_count,
                             "total_attempts": wv.total_attempts, "last_error_at": wv.last_error_at}
                            for wv in rows], k=limit)
    return [
        {
            "viseme_id": r["viseme_id"],
            "feature": feature.get(r["viseme_id"]) or get_viseme_feature(r["viseme_id"]),
            "error_rate": r["error_rate"],
        }
        for r in ranked
    ]


async def check_scenario_cache(
    situation: str,
    level: int,
    target_visemes: List[int],
    db: AsyncSession
) -> dict:
    """
    Check if a suitable cached scenario exists
    Returns cached scenario or None
    """
    # Look for recent cache (within 7 days) with similar parameters
    week_ago = datetime.utcnow() - timedelta(days=7)

    result = await db.execute(
        select(ScenarioCache)
        .where(
            and_(
                ScenarioCache.situation == situation,
                ScenarioCache.difficulty_level == level,
                ScenarioCache.created_at >= week_ago
            )
        )
        .limit(5)
    )
    caches = result.scalars().all()

    if not caches:
        return None

    # Find best match based on target visemes overlap
    best_cache = None
    best_overlap = 0

    for cache in caches:
        overlap = len(set(cache.target_visemes or []) & set(target_visemes))
        if overlap > best_overlap:
            best_overlap = overlap
            best_cache = cache

    if best_cache and best_cache.use_count < 3:
        # Update usage count
        best_cache.use_count += 1
        await db.commit()

        return {
            "situation": best_cache.situation,
            "level": best_cache.difficulty_level,
            "sentences": best_cache.sentences,
            "scenario_id": f"cache_{best_cache.id}"
        }

    return None


async def generate_adaptive_scenario(
    user_id: int,
    situation: str,
    level: int,
    db: AsyncSession
) -> Dict:
    """
    Generate adaptive learning scenario using Claude API
    Prioritizes user's weak visemes in sentence generation

    Args:
        user_id: User ID for personalization
        situation: Situation context (e.g., "카페", "병원")
        level: Difficulty level (1-5)
        db: Database session

    Returns:
        Dictionary with situation, level, sentences, and scenario_id
    """
    # Get user's weak visemes (safe - fallback to empty list on error)
    try:
        weak_visemes = await get_user_weak_visemes(user_id, db, limit=3)
        target_viseme_ids = [wv["viseme_id"] for wv in weak_visemes]
    except Exception as e:
        print(f"[WARN] get_user_weak_visemes failed: {e}")
        target_viseme_ids = []

    # 캐시 재사용은 '매번 같은 문장'의 주범이라 의도적으로 끈다(변주 우선).
    # (캐시 쓰기는 유지 — 통계/폴백용. 필요 시 LIPLAB_SCENARIO_CACHE=1로 재사용 활성화)
    if os.getenv("LIPLAB_SCENARIO_CACHE", "0") == "1":
        try:
            cached_scenario = await check_scenario_cache(situation, level, target_viseme_ids, db)
            if cached_scenario:
                return cached_scenario
        except Exception as e:
            print(f"[WARN] check_scenario_cache failed: {e}")

    # Get situation context
    context = SITUATION_CONTEXTS.get(situation, {
        "description": f"{situation} 상황",
        "keywords": [],
        "common_phrases": []
    })

    # Build target phonemes from weak visemes
    target_phonemes = []
    for viseme_id in target_viseme_ids[:2]:  # Focus on top 2 weak visemes
        phonemes = VISEME_PHONEME_MAP.get(viseme_id, [])
        target_phonemes.extend(phonemes)

    # Construct adaptive prompt based on level
    # 어절 수(띄어쓰기로 센 덩어리)를 예문과 함께 준다. 예전에는 범위만 적어 3단계 문장이 5~11어절(기준에 든 것 2/10)로
    # 2단계와 겹치고 4단계도 4/10만 맞았다(9/27 밤 표본 단계당 10문장). SCENARIO_MIN_WORDS가 너무 짧은 문장을 거른다.
    level_instructions = {
        1: "매우 쉬운 수준: 짧고 명확한 문장, 띄어쓰기로 센 어절 5~8개(예: '저는 아침마다 공원에서 산책을 해요.' 5어절). 시각적으로 구별이 명확한 음소만 사용. 일상적 표현.",
        2: "쉬운 수준: 일상 대화 문장, 어절 7~10개(예: '이번 주 토요일에 친구 생일 파티가 있어요.' 7어절). 기본적인 문맥이 있는 자연스러운 표현.",
        3: "중간 수준: 자연스러운 대화, 어절 10~13개(예: '다음 주 월요일에 회의가 있으니까 자료를 미리 준비해 두면 좋겠어요.' 11어절). 약간의 시각적 유사 음소 포함. 상황에 맞는 다양한 표현.",
        4: "어려운 수준: 복잡한 문장 구조, 어절 12~15개(예: '비가 많이 와서 퇴근길 버스가 평소보다 훨씬 붐빌 것 같으니 조금 일찍 출발하세요.' 14어절). 시각적으로 유사한 음소(ㅂ/ㅍ, ㄱ/ㅋ 등) 의도적 포함.",
        5: "매우 어려운 수준: 문맥 없이는 구별이 어려운 문장, 어절 15~20개, 90자 이내(예: '지난주에 맡긴 겨울 외투를 찾으러 왔는데 영수증을 집에 두고 와서 이름으로 확인해 주실 수 있을까요?' 16어절). 동음이의어, 시각적 유사 음소를 다량 포함."
    }

    # Build phoneme focus instruction
    phoneme_instruction = ""
    if target_phonemes and level >= 3:
        phoneme_str = ", ".join(target_phonemes[:5])
        phoneme_instruction = f"\n특히 다음 음소들이 포함된 단어를 우선적으로 사용하세요: {phoneme_str}"

    # ── 변주 축 — 매 호출마다 무작위로 골라 프롬프트에 주입 → 같은 상황이어도 결과가 겹치지 않게 ──
    _sub_focus = random.choice([
        "상대에게 무언가를 요청/부탁하는 말", "가격·시간·수량을 묻는 말", "감사·사과를 표현하는 말",
        "길이나 위치를 묻고 답하는 말", "제안하거나 권유하는 말", "가벼운 잡담·안부",
        "문제 상황을 설명하는 말", "선택·결정을 확인하는 말", "감정을 드러내는 말",
    ])
    _tone = random.choice(["정중한 존댓말", "친근한 반말 섞인 구어", "간결하고 담백한 어조", "다정하고 배려하는 어조"])
    _persona = random.choice(["손님", "직원", "친구", "가족", "처음 만난 사람", "이웃"])
    _twist = random.choice([
        "이전에 흔히 나오는 뻔한 표현은 피하고 새로운 어휘를 쓰세요.",
        "서로 다른 소재를 다뤄 5문장이 각기 다른 장면이 되게 하세요.",
        "구체적인 사물·숫자·이름을 넣어 생생하게 만드세요.",
        "너무 교과서적이지 않게, 실제 대화처럼 자연스럽게 변주하세요.",
    ])
    variety_instruction = (
        f"\n**이번 회차 변주(매번 다르게)**:\n"
        f"- 초점: {_sub_focus}\n- 어조: {_tone}\n- 화자 시점: {_persona}\n- 추가 지시: {_twist}\n"
        f"- 변주 시드: {random.randint(1000, 9999)} (이 숫자가 다르면 반드시 다른 문장을 만드세요)"
    )

    system_prompt = f"""당신은 청각장애인의 독화(Speechreading) 훈련을 위한 한국어 문장 생성 전문가입니다.

**목표**: 주어진 상황과 난이도에 맞는 자연스러운 한국어 문장 5개를 생성하세요.

**상황 정보**:
- 상황: {context["description"]}
- 관련 키워드: {", ".join(context["keywords"][:8])}
- 자주 쓰이는 표현: {", ".join(context["common_phrases"])}

**난이도 기준**:
{level_instructions[level]}
{phoneme_instruction}
{variety_instruction}

**중요 규칙**:
1. 모든 문장은 해당 상황에서 실제로 사용될 법한 자연스러운 표현이어야 합니다.
2. 문장은 서로 연결되지 않아도 되지만, 같은 상황 맥락을 유지해야 합니다.
3. 각 문장은 독립적으로 이해 가능해야 합니다.
4. 구어체를 사용하되, 지나치게 축약하지 마세요.
5. 난이도에 따라 문장 길이와 어휘 난이도를 조절하세요.
6. 영어 단어나 로마자는 쓰지 마세요(입모양으로 읽을 수 없어 탈락합니다). 숫자는 아라비아 숫자로 써도 됩니다.

**응답 형식** (반드시 유효한 JSON으로만 응답):
{{
  "sentences": [
    "문장 1",
    "문장 2",
    "문장 3",
    "문장 4",
    "문장 5"
  ]
}}
"""

    user_prompt = f"상황: {situation}, 난이도 레벨: {level}"

    try:
        # LLM 출력 검증(§4.9) + 규칙 게이트(축 G) — 지시 이탈·주입·비정상 문장을 걸러
        # 정상 한글 훈련 문장만 클라이언트로 내보낸다. 부족하면 폴백으로 넘어간다.
        from content_rules import check_sentence
        # 글자 수 상한은 난이도의 어절 수에 맞춘다. 기본 40자로 걸러 4·5단계(12~15어절 이상, 약 42~55자)와 3단계 일부가
        # 늘 탈락해, 요청한 단계 이름을 단 쉬운 대체 문장이 나갔다.
        max_chars = SCENARIO_MAX_CHARS.get(level, 40)
        min_words = SCENARIO_MIN_WORDS.get(level, 1)
        messages = [{"role": "user", "content": user_prompt}]
        sentences: List[str] = []
        # 통과한 문장이 3개보다 적으면 한 번 다시 받는다. 예전에는 바로 대체 문장으로 넘어가, 표본(6상황 × 5단계) 30번 중
        # 2번(3단계는 6~7어절, 5단계는 90자 넘는 문장)이 상황과 무관한 저장·대체 문장을 받았다(9/27 밤).
        for attempt in range(2):
            response = await anthropic_client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                temperature=1.0,  # 변주 극대화 — 매번 다른 문장
                system=system_prompt,
                messages=messages,
            )
            # Parse response — 코드펜스 제거 + 빈 응답 방어(공용 유틸)
            try:
                got = llm_json.extract_json(response).get("sentences", [])
            except Exception:
                got = []
            for s in got:
                if (isinstance(s, str) and s not in sentences and check_sentence(s, max_chars=max_chars)[0]
                        and len(s.split()) >= min_words):
                    sentences.append(s)
            if len(sentences) >= 3:
                break
            messages = messages + [
                {"role": "assistant", "content": json.dumps({"sentences": got}, ensure_ascii=False)},
                {"role": "user", "content": f"기준에 맞는 문장이 {len(sentences)}개뿐입니다. 한 문장이 띄어쓰기로 센 어절 "
                                            f"{min_words}개 이상, {max_chars}자 이내여야 합니다. 같은 상황으로 새 문장 5개를 "
                                            f"같은 JSON 형식으로 다시 만드세요."},
            ]
        sentences = sentences[:5]

        if not sentences or len(sentences) < 3:
            raise ValueError("Generated sentences are insufficient")

        # Cache the generated scenario
        cache_entry = ScenarioCache(
            situation=situation,
            difficulty_level=level,
            target_visemes=target_viseme_ids,
            sentences=sentences,
            use_count=1
        )
        db.add(cache_entry)
        await db.commit()
        await db.refresh(cache_entry)

        scenario_id = f"llm_{cache_entry.id}_{datetime.utcnow().timestamp()}"

        return {
            "situation": situation,
            "level": level,
            "sentences": sentences,
            "scenario_id": scenario_id
        }

    except Exception as e:
        # Fallback to default sentences if API fails
        print(f"LLM API Error: {e}")
        return await _fallback_scenario(situation, level, db)


_SITUATION_DEFAULTS = {
    "카페": ["아메리카노 한 잔 주세요.", "따뜻한 걸로 할게요.", "여기서 마실게요.", "설탕은 빼주세요.", "영수증 주세요."],
    "병원": ["머리가 아파요.", "언제부터 아프셨어요?", "약 처방해 주세요.", "검사 예약하고 싶어요.", "다음 진료 언제예요?"],
    "식당": ["메뉴판 좀 주세요.", "이거 맵나요?", "두 명이에요.", "물 좀 주세요.", "계산해 주세요."],
}


async def _fallback_scenario(situation: str, level: int, db: AsyncSession) -> Dict:
    """문장 생성이 실패했을 때(키 없음·API 장애·게이트 탈락). 순서
    1) 같은 상황·단계로 전에 만든 LLM 문장(ScenarioCache, 성공할 때마다 쌓인다)을 지금 게이트로 다시 걸러 3개 이상이면 쓴다.
       캐시 재사용은 변주를 위해 평소에는 끄지만, 실패했을 때 단계에 맞는 상황 문장을 내는 데는 이것이 가장 낫다.
    2) 1단계는 상황별 짧은 기본 문장, 2단계 이상(또는 기본 문장이 없는 상황)은 단계별 대체 문장(FALLBACK_BY_LEVEL)."""
    from content_rules import check_sentence
    max_chars = SCENARIO_MAX_CHARS.get(level, 40)
    ts = datetime.utcnow().timestamp()
    try:
        await db.rollback()          # 실패한 캐시 쓰기 등으로 트랜잭션이 깨졌으면 정리하고 읽는다
        rows = (await db.execute(
            select(ScenarioCache)
            .where(and_(ScenarioCache.situation == situation, ScenarioCache.difficulty_level == level))
            .order_by(ScenarioCache.created_at.desc()).limit(20))).scalars().all()
        rows = list(rows)
        random.shuffle(rows)
        for row in rows:
            ok = [x for x in (row.sentences or []) if isinstance(x, str) and check_sentence(x, max_chars=max_chars)[0]
                  and len(x.split()) >= SCENARIO_MIN_WORDS.get(level, 1)]
            if len(ok) >= 3:
                return {"situation": situation, "level": level, "sentences": ok[:5],
                        "scenario_id": f"cache_{row.id}_{ts}", "fallback": "cache"}
    except Exception as e:
        print(f"[WARN] scenario cache fallback failed: {e}")
    if level <= 1 and situation in _SITUATION_DEFAULTS:
        sentences = list(_SITUATION_DEFAULTS[situation])
    else:
        bank = FALLBACK_BY_LEVEL.get(max(1, min(5, int(level or 1))), FALLBACK_BY_LEVEL[1])
        sentences = random.sample(bank, k=min(5, len(bank)))
    return {"situation": situation, "level": level, "sentences": sentences[:5],
            "scenario_id": f"fallback_{ts}", "fallback": "static"}


# 대화 턴 길이 상한(공백·문장부호 포함). 아래 level_guide의 글자 수에 30% 여유를 둔 값이다. 지시만 하고 검사하지 않아, 첫 턴 40개
# 표본에서 1단계 2/8, 2단계 5/8, 3단계 4/8이 지시보다 길었다(9/27 밤). 5단계는 지시에 상한이 없다.
_CONV_MAX_CHARS = {1: 9, 2: 13, 3: 20, 4: 26}


def _norm_turn(text: str) -> str:
    """반복 비교용: 한글·숫자만."""
    return re.sub(r"[^가-힣0-9]", "", text or "")


def fallback_turn(situation: str, level: int, history: List[Dict]) -> str:
    """LLM이 실패했을 때 상대의 다음 대사. 이 상황의 대체 대사 가운데 단계 길이 상한(conv_turn_ok) 안이고 이 대화에서 아직 하지 않은
    것을 목록 순서대로 고른다. 모두 했으면 가장 오래전에 한 대사부터 다시 쓴다. 예전에는 len(history) % 대사 수로 골라 학습자 턴까지
    세는 기록 길이가 2씩 늘어 두 대사만 번갈아 나왔고, 1단계에도 18자 대사('어서 오세요. 무엇으로 드릴까요?')가 나갔다(9/28 감사)."""
    lines = FALLBACK_TURNS.get(situation) or FALLBACK_TURNS_GENERIC
    fits = [t for t in lines if conv_turn_ok(t, level)] or [min(lines, key=len)]
    said = [_norm_turn(h.get("content", "")) for h in (history or []) if h.get("role") == "assistant"]
    fresh = [t for t in fits if _norm_turn(t) not in said]
    if fresh:
        return fresh[0]
    last = {k: i for i, k in enumerate(said)}
    return min(fits, key=lambda t: last.get(_norm_turn(t), -1))


def conv_turn_ok(text: str, level: int) -> bool:
    """대화 턴이 단계 길이 상한 안이고 영문이 없는가."""
    if re.search(r"[A-Za-z]", text or ""):
        return False
    lim = _CONV_MAX_CHARS.get(level)
    return lim is None or len(text) <= lim


async def rephrase_turn(text: str, situation: str, level: int) -> Optional[str]:
    """대화 되묻기 '다른 말로 해 주세요'(docs/curriculum-roadmap.md 1-4): 같은 뜻을 다른 낱말·구조의 한 문장으로 바꾼다.
    실제 대화에서 못 알아들은 말을 다시 물으면 상대가 바꿔 말해 주는 상황을 연습한다. 실패·한도 초과·원문과 같으면 None이고,
    화면은 '천천히'로 대신한다. 하루 한도(llm_budget)는 다른 호출과 함께 센다."""
    src = (text or "").strip()[:200]
    if not src:
        return None
    lim = _CONV_MAX_CHARS.get(level)
    system_prompt = (
        "당신은 청각장애인의 독화 훈련 대화 상대입니다. 학습자가 방금 문장을 입모양으로 알아보지 못해 다른 말로 해 달라고 했습니다. "
        "같은 뜻을 다른 낱말이나 문장 구조로 바꾼 자연스러운 한국어 한 문장만 말하세요. 원문을 그대로 되풀이하지 마세요"
        + (f" {lim}자 이하로 쓰세요." if lim else ".")
        + " " + PLAIN_KO_WORDS
        + ' 반드시 JSON 형식으로만 응답: {"text": "문장 내용"}'
    )
    try:
        response = await anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=120,
            temperature=0.7,
            system=system_prompt,
            messages=[{"role": "user", "content": f"상황: {situation}\n원문: {src}"}],
        )
        out = str(llm_json.extract_json(response).get("text", "")).strip()
    except Exception as e:
        print(f"Rephrase API error: {e}")
        return None
    out = "".join(ch for ch in out if ch >= " ")[:300].strip()
    if not out or re.search(r"[A-Za-z]", out) or _norm_turn(out) == _norm_turn(src) or not conv_turn_ok(out, level):
        return None
    return out


async def generate_conversation_turn(
    situation: str,
    level: int,
    history: List[Dict]
) -> Dict:
    """
    Generate a single conversational line for dialogue practice.
    Uses chat history to maintain natural conversation flow.

    Args:
        situation: Conversation context (e.g., "카페", "병원")
        level: Difficulty 1-5
        history: [{"role": "assistant"|"user", "content": str}, ...]

    Returns:
        {"text": str}
    """
    context = SITUATION_CONTEXTS.get(situation, {
        "description": f"{situation} 상황",
        "keywords": [],
        "common_phrases": []
    })

    level_guide = {
        1: "아주 짧고 쉬운 표현 (5-7글자). 흔히 쓰는 인사나 질문.",
        2: "짧고 자연스러운 문장 (10글자 이하).",
        3: "자연스러운 대화 문장 (15글자 이하).",
        4: "약간 긴 자연스러운 표현 (20글자 이하).",
        5: "복잡한 문장이나 관용 표현 포함 (제한 없음).",
    }

    system_prompt = f"""당신은 청각장애인의 독화(Speechreading) 훈련을 위한 대화 시뮬레이터입니다.
'{context["description"]}' 상황에서 자연스러운 대화 상대 역할을 합니다.

규칙:
1. 실제 해당 상황에서 쓰일 법한 자연스러운 한국어 한 문장만 말하세요.
2. 난이도에 맞게: {level_guide.get(level, level_guide[3])}
3. 이전 대화 흐름에 자연스럽게 이어지도록 하세요.
4. 처음 맡은 한 역할(예: 직원·의사)을 끝까지 유지하세요. 사용자 메시지는 대답이 아니라 학습자가 당신의 직전 문장을 입모양으로
   읽고 적은 글입니다. 상대가 자연스럽게 대답했다고 가정하고 대화를 앞으로 진행하세요. 앞에서 한 문장은 되풀이하지 마세요.
5. {PLAIN_KO_WORDS}
6. 반드시 JSON 형식으로만 응답: {{"text": "문장 내용"}}"""

    if not history:
        messages_for_api = [{"role": "user", "content": f"대화를 시작해주세요. 상황: {situation}"}]
    else:
        # Build clean alternating messages for Anthropic API
        clean = []
        for h in history:
            role = "assistant" if h.get("role") == "assistant" else "user"
            content = h.get("content", "").strip()
            if not content:
                continue
            if role == "user":
                # 학습자 입력은 대답이 아니라 직전 문장을 읽고 적은 글이다. 그대로 사용자 턴으로 넘기면 모델이 따라 한 말에
                # 응답해 같은 문장을 되풀이하거나 역할을 바꿨다(9/27 밤: 카페 직원이 첫 문장을 반복한 뒤 손님이 됨, 의사·환자 번갈아).
                content = f"(학습자가 당신의 직전 문장을 '{content[:120]}'(으)로 읽었습니다. 대답이 아닙니다.) 대화를 이어 다음 한 문장을 말하세요."
            # Merge consecutive same-role messages
            if clean and clean[-1]["role"] == role:
                clean[-1]["content"] += " " + content
            else:
                clean.append({"role": role, "content": content})

        # Anthropic requires first message to be user
        if clean and clean[0]["role"] == "assistant":
            clean.insert(0, {"role": "user", "content": f"상황: {situation}에서 대화합니다."})

        # Must end with user message to prompt AI response
        if not clean or clean[-1]["role"] == "assistant":
            clean.append({"role": "user", "content": "대화를 이어가주세요."})

        messages_for_api = clean if clean else [
            {"role": "user", "content": f"대화를 시작해주세요. 상황: {situation}"}
        ]

    try:
        # 단계 길이 상한(conv_turn_ok)을 넘으면 이유를 알려 한 번 다시 받고, 그래도 넘으면 영문이 없고 짧은 쪽을 쓴다.
        cands = []
        msgs = list(messages_for_api)
        prev_lines = {_norm_turn(h.get("content", "")) for h in (history or []) if h.get("role") == "assistant"}
        for attempt in range(2):
            response = await anthropic_client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=150,
                temperature=0.9,
                system=system_prompt,
                messages=msgs
            )

            result = llm_json.extract_json(response)
            text = result.get("text", "").strip()

            # 출력 정규화(§4.9) — 제어문자 제거·길이 상한. 대화 답변은 자유형이라 문장 게이트 대신 경량 필터.
            text = "".join(ch for ch in text if ch >= " " or ch == "\n")[:300].strip()
            if text:
                cands.append(text)
            repeated = bool(text) and _norm_turn(text) in prev_lines
            if text and conv_turn_ok(text, level) and not repeated:
                return {"text": text}
            lim = _CONV_MAX_CHARS.get(level)
            why = ("방금 문장은 앞에서 이미 한 말입니다. 대화를 앞으로 진행하는 새 문장을 말하세요." if repeated
                   else f"방금 문장은 {len(text)}자라 이 난이도에 너무 깁니다. 같은 뜻을 {lim}자 이하 한국어 한 문장으로 다시 말하세요."
                   if lim and text and len(text) > lim else "영문 없이 한국어 한 문장으로 다시 말하세요.")
            msgs = msgs + [{"role": "assistant", "content": json.dumps({"text": text}, ensure_ascii=False)},
                           {"role": "user", "content": why}]

        if not cands:
            raise ValueError("Empty text")
        return {"text": min(cands, key=lambda t: (_norm_turn(t) in prev_lines, bool(re.search(r"[A-Za-z]", t)), len(t)))}

    except Exception as e:
        print(f"Conversation API error: {e}")
        # 대체 대사: 온전한 문장으로 잇는다. 예전에는 '자주 쓰이는 표현'(주세요 같은 조각)을 썼고,
        # 목록에 없는 상황(상황별 시나리오의 자유 입력)은 빈 목록이라 0으로 나눠 500이 났다.
        return {"text": fallback_turn(situation, level, history)}
