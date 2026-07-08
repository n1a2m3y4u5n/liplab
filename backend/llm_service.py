"""
Adaptive Scenario Generation using Claude API
Generates contextually relevant sentences based on user's weak visemes
"""
import os
import json
from typing import List, Dict
from datetime import datetime, timedelta
from anthropic import AsyncAnthropic
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from database import WeakViseme, ScenarioCache
from engine import get_viseme_feature


# Initialize Anthropic client
anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


# Situation-based context prompts
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
    """
    result = await db.execute(
        select(WeakViseme)
        .where(WeakViseme.user_id == user_id)
        .order_by(WeakViseme.error_count.desc())
        .limit(limit)
    )
    weak_visemes = result.scalars().all()

    return [
        {
            "viseme_id": wv.viseme_id,
            "feature": wv.phonological_feature or get_viseme_feature(wv.viseme_id),
            "error_rate": wv.error_count / wv.total_attempts if wv.total_attempts > 0 else 0
        }
        for wv in weak_visemes
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

    # Check cache first (safe - skip cache on error)
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
    level_instructions = {
        1: "매우 쉬운 수준: 짧고 명확한 문장 (5-8어절). 시각적으로 구별이 명확한 음소만 사용. 일상적 표현.",
        2: "쉬운 수준: 일상 대화 문장 (7-10어절). 기본적인 문맥이 있는 자연스러운 표현.",
        3: "중간 수준: 자연스러운 대화 (10-13어절). 약간의 시각적 유사 음소 포함. 상황에 맞는 다양한 표현.",
        4: "어려운 수준: 복잡한 문장 구조 (12-15어절). 시각적으로 유사한 음소(ㅂ/ㅍ, ㄱ/ㅋ 등) 의도적 포함.",
        5: "매우 어려운 수준: 문맥 없이는 구별이 어려운 문장 (15어절 이상). 동음이의어, 시각적 유사 음소를 다량 포함."
    }

    # Build phoneme focus instruction
    phoneme_instruction = ""
    if target_phonemes and level >= 3:
        phoneme_str = ", ".join(target_phonemes[:5])
        phoneme_instruction = f"\n특히 다음 음소들이 포함된 단어를 우선적으로 사용하세요: {phoneme_str}"

    system_prompt = f"""당신은 청각장애인의 독화(Speechreading) 훈련을 위한 한국어 문장 생성 전문가입니다.

**목표**: 주어진 상황과 난이도에 맞는 자연스러운 한국어 문장 5개를 생성하세요.

**상황 정보**:
- 상황: {context["description"]}
- 관련 키워드: {", ".join(context["keywords"][:8])}
- 자주 쓰이는 표현: {", ".join(context["common_phrases"])}

**난이도 기준**:
{level_instructions[level]}
{phoneme_instruction}

**중요 규칙**:
1. 모든 문장은 해당 상황에서 실제로 사용될 법한 자연스러운 표현이어야 합니다.
2. 문장은 서로 연결되지 않아도 되지만, 같은 상황 맥락을 유지해야 합니다.
3. 각 문장은 독립적으로 이해 가능해야 합니다.
4. 구어체를 사용하되, 지나치게 축약하지 마세요.
5. 난이도에 따라 문장 길이와 어휘 난이도를 조절하세요.

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
        # Call Claude API
        response = await anthropic_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            temperature=0.8,  # Add creativity for varied sentences
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )

        # Parse response
        content = response.content[0].text.strip()

        # Extract JSON from potential markdown code blocks
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        result = json.loads(content)
        sentences = result.get("sentences", [])

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

        default_sentences = {
            "카페": [
                "아메리카노 한 잔 주세요.",
                "따뜻한 걸로 할게요.",
                "여기서 마실게요.",
                "설탕은 빼주세요.",
                "영수증 주세요."
            ],
            "병원": [
                "머리가 아파요.",
                "언제부터 아프셨어요?",
                "약 처방해 주세요.",
                "검사 예약하고 싶어요.",
                "다음 진료 언제예요?"
            ],
            "식당": [
                "메뉴판 좀 주세요.",
                "이거 맵나요?",
                "두 명이에요.",
                "물 좀 주세요.",
                "계산해 주세요."
            ]
        }

        fallback = default_sentences.get(situation, [
            "안녕하세요.",
            "감사합니다.",
            "네, 알겠습니다.",
            "괜찮습니다.",
            "다시 한 번 말씀해 주세요."
        ])

        return {
            "situation": situation,
            "level": level,
            "sentences": fallback[:5],
            "scenario_id": f"fallback_{datetime.utcnow().timestamp()}"
        }


async def generate_analysis_recommendation(analysis: dict) -> str:
    """
    Generate personalized Korean learning recommendation using Claude.
    analysis: {
      "total_sessions": int,
      "average_score": float,
      "strengths": [{"name": str, "accuracy": float}],
      "weaknesses": [{"name": str, "accuracy": float}],
      "viseme_stats": [{"name": str, "accuracy": float, "attempts": int}]
    }
    Returns: Korean recommendation string
    """
    strengths_text = ", ".join(
        f'{s["name"]}({s["accuracy"]:.0f}%)' for s in analysis.get("strengths", [])
    ) or "아직 데이터 부족"
    weaknesses_text = ", ".join(
        f'{w["name"]}({w["accuracy"]:.0f}%)' for w in analysis.get("weaknesses", [])
    ) or "아직 데이터 부족"

    prompt = f"""다음은 청각장애인 독화(Speechreading) 학습자의 테스트 성과 데이터입니다.

총 연습 횟수: {analysis.get('total_sessions', 0)}회
평균 점수: {analysis.get('average_score', 0):.1f}점
잘하는 유형: {strengths_text}
취약한 유형: {weaknesses_text}

이 학습자를 위해 다음을 한국어로 작성해주세요:
1. 현재 수준 평가 (1-2문장)
2. 취약한 부분의 원인 설명 (해당 입모양의 특성)
3. 구체적인 학습 전략 3가지 (번호 매겨서)
4. 격려 메시지 (1문장)

300자 이내로 친절하고 실용적으로 작성하세요."""

    try:
        response = await anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text.strip()
    except Exception as e:
        print(f"Analysis recommendation error: {e}")
        return "더 많은 연습을 통해 데이터가 쌓이면 맞춤형 학습 조언을 받을 수 있습니다. 꾸준히 연습해보세요!"


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
4. 반드시 JSON 형식으로만 응답: {{"text": "문장 내용"}}"""

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
        response = await anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            temperature=0.9,
            system=system_prompt,
            messages=messages_for_api
        )

        content = response.content[0].text.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        result = json.loads(content)
        text = result.get("text", "").strip()

        if not text:
            raise ValueError("Empty text")

        return {"text": text}

    except Exception as e:
        print(f"Conversation API error: {e}")
        # Fallback openings
        fallbacks = context.get("common_phrases", ["안녕하세요.", "무엇을 도와드릴까요?", "네, 알겠습니다."])
        idx = len(history) % len(fallbacks)
        return {"text": fallbacks[idx]}
