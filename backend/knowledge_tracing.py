"""
LIPLAB 지식추적(Knowledge Tracing) — 고도화 축 G 개인화.

학습 로그(viseme별 정오)에서 음소별 '숙달도'를 추정하고, 다음에 연습할 표적 음소와
난이도를 정한다. 계획서 §3.7: "학습 기록으로 음소별 숙달을 추정하는 지식추적을 두어
다음 문항을 개인화한다."

정통 BKT(Bayesian Knowledge Tracing)의 경량판을 쓴다(프로토타입 수준). 각 viseme의
숙달도를 베타-이항 사후평균으로 추정하고, 최근 오답에 감쇠 가중을 준다. DB에 의존하지
않는 순수 함수라 결정론적으로 테스트된다(now를 주입).

viseme_id는 engine.VISEME_MAP의 1~10 음소 그룹(11~15는 전환·휴지라 학습 대상 아님).
"""
import math
from datetime import datetime
from typing import Dict, List, Optional

# 베타 사전(라플라스): 시도가 적을 때 숙달도를 0.5 근처의 불확실 값으로 끌어당긴다.
_PRIOR_A = 1.0
_PRIOR_B = 1.0
# 최근 오답 감쇠: 최근에 틀린 음소일수록 숙달도를 더 낮게 본다(반감기 약 7일).
_RECENCY_HALFLIFE_DAYS = 7.0
_RECENCY_WEIGHT = 0.25
# 학습 대상 viseme(1~10). 입 안쪽 자음(6·7·8·10)은 독화로는 구별이 어려워 문맥 학습 대상.
TEACHABLE_VISEMES = list(range(1, 11))


def _mastery_one(errors: int, attempts: int, last_error_at: Optional[datetime],
                 now: datetime) -> Optional[float]:
    """viseme 하나의 숙달도(0~1). 시도가 없으면 None(미학습)."""
    if attempts <= 0:
        return None
    correct = max(attempts - errors, 0)
    # 베타-이항 사후평균 = (성공 + a) / (시도 + a + b)
    base = (correct + _PRIOR_A) / (attempts + _PRIOR_A + _PRIOR_B)
    # 최근 오답 감쇠
    if last_error_at is not None and errors > 0:
        days = max((now - last_error_at).total_seconds() / 86400.0, 0.0)
        recency = math.exp(-days / _RECENCY_HALFLIFE_DAYS)  # 최근일수록 1
        base *= (1.0 - _RECENCY_WEIGHT * recency)
    return max(0.0, min(1.0, base))


def estimate_mastery(records: List[Dict], now: Optional[datetime] = None) -> Dict[int, float]:
    """
    WeakViseme 기록에서 viseme별 숙달도를 추정한다.
    records: [{"viseme_id", "error_count", "total_attempts", "last_error_at"}] 형태.
    미학습 viseme은 결과에서 빠진다(호출부가 '데이터 없음'으로 구분).
    """
    now = now or datetime.utcnow()
    out: Dict[int, float] = {}
    for r in records:
        vid = r.get("viseme_id")
        if vid not in TEACHABLE_VISEMES:
            continue
        m = _mastery_one(int(r.get("error_count", 0) or 0),
                         int(r.get("total_attempts", 0) or 0),
                         r.get("last_error_at"), now)
        if m is not None:
            out[vid] = round(m, 3)
    return out


def weakest_visemes(mastery: Dict[int, float], k: int = 2,
                    threshold: float = 0.7) -> List[int]:
    """
    가장 약한(숙달도 낮은) 음소를 최대 k개 고른다. 표적 음소가 된다.
    임계(threshold) 미만인 것만 고르되, 학습한 게 없으면 아직 안 배운 음소를 준다.
    """
    learned = sorted(mastery.items(), key=lambda kv: kv[1])
    targets = [vid for vid, m in learned if m < threshold][:k]
    if targets:
        return targets
    # 약점이 뚜렷하지 않으면(다 잘하거나 데이터 부족) 아직 안 배운 음소로 확장 유도
    unseen = [v for v in TEACHABLE_VISEMES if v not in mastery]
    return unseen[:k] if unseen else [vid for vid, _ in learned[:k]]


def overall_level(mastery: Dict[int, float]) -> int:
    """전체 평균 숙달도로 문장 난이도(1~5)를 제안한다. 데이터 없으면 1."""
    if not mastery:
        return 1
    avg = sum(mastery.values()) / len(mastery)
    # 0.0~1.0 → 1~5 구간
    return max(1, min(5, int(avg * 4) + 1))


def recommend(records: List[Dict], k: int = 2, now: Optional[datetime] = None) -> Dict:
    """학습 기록 → {mastery, target_visemes, level, coverage}. API·selector가 소비한다."""
    mastery = estimate_mastery(records, now=now)
    return {
        "mastery": mastery,
        "target_visemes": weakest_visemes(mastery, k=k),
        "level": overall_level(mastery),
        "coverage": len(mastery),  # 데이터가 있는 viseme 수
    }
