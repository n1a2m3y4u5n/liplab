"""
전사 비의존 발음정확도(D-GOP) — 고도화 축 B 핵심 로직.

표준 GOP(Goodness of Pronunciation)는 목표 음소가 놓일 구간의 음향이 그 음소에 얼마나
부합하는지를 사후확률로 점수화한다. 목표 문장을 시스템이 이미 알기 때문에 전사가 필요 없다.
그러나 표준 GOP는 정상 발화를 전제해, 발음이 뭉개진 농인 발화에서 오히려 과신(점수가 붕괴적으로
높아짐)하는 문제가 있다(예비 실증에서 확인). D-GOP는 예측 분포의 불확실성(엔트로피·상위 확률
여유)으로 naive 점수를 보정하고, 음향이 불확실한 구간일수록 영상(입모양) 신호에 더 가중해 후기
융합한다.

이 모듈은 음향 모델이 준 '음소 사후확률 분포'를 입력으로 받는 순수 함수다(모델 비의존 → 결정론적
테스트 가능). 실제 음향 추론(wav2vec2/WavLM 강제정렬)은 dgop_acoustic이 이 함수들에 분포를 공급한다.
"""
import math
from typing import Dict, List, Optional, Sequence

_EPS = 1e-9


def normalized_entropy(probs: Sequence[float]) -> float:
    """분포의 정규화 엔트로피(0=확신, 1=완전 불확실). 클래스 수로 정규화."""
    ps = [max(float(p), 0.0) for p in probs]
    total = sum(ps) or 1.0
    ps = [p / total for p in ps]
    n = len(ps)
    if n <= 1:
        return 0.0
    h = -sum(p * math.log(p + _EPS) for p in ps if p > 0)
    return max(0.0, min(1.0, h / math.log(n)))


def top_margin(probs: Sequence[float]) -> float:
    """최상위와 차상위 확률의 여유값(0~1). 크면 뚜렷, 작으면 헷갈림."""
    ps = sorted((max(float(p), 0.0) for p in probs), reverse=True)
    if not ps:
        return 0.0
    total = sum(ps) or 1.0
    top1 = ps[0] / total
    top2 = ps[1] / total if len(ps) > 1 else 0.0
    return max(0.0, top1 - top2)


def phone_confidence(probs: Sequence[float]) -> float:
    """구간 예측의 신뢰도(0~1). 상위 확률 여유가 크고 엔트로피가 낮을수록 높다."""
    return max(0.0, min(1.0, top_margin(probs) * (1.0 - normalized_entropy(probs))))


def naive_gop(target_prob: float) -> float:
    """표준 GOP 근사 — 목표 음소의 사후확률 그대로(불확실성 미보정)."""
    return max(0.0, min(1.0, float(target_prob)))


def dgop_phone(target_prob: float, probs: Sequence[float]) -> Dict:
    """
    한 음소 구간의 D-GOP. naive(목표 사후확률)를 그 구간 예측의 신뢰도로 보정한다.
    분포가 평평할수록(발음이 뭉갤수록) 신뢰도가 낮아 점수가 과신되지 않는다.
    반환: {naive, confidence, uncertainty, dgop} (모두 0~1).
    """
    conf = phone_confidence(probs)
    naive = naive_gop(target_prob)
    return {
        "naive": round(naive, 4),
        "confidence": round(conf, 4),
        "uncertainty": round(1.0 - conf, 4),
        "dgop": round(naive * conf, 4),
    }


def sentence_dgop(per_phone: List[Dict]) -> Dict:
    """음소별 D-GOP를 문장 점수로 집계. 평균 D-GOP와 평균 불확실성(융합 가중에 사용)."""
    if not per_phone:
        return {"score": 0.0, "uncertainty": 1.0, "phones": []}
    mean_dgop = sum(p["dgop"] for p in per_phone) / len(per_phone)
    mean_unc = sum(p["uncertainty"] for p in per_phone) / len(per_phone)
    return {
        "score": round(mean_dgop * 100, 1),      # 0~100
        "uncertainty": round(mean_unc, 4),
        "phones": per_phone,
    }


def fuse_audio_visual(audio_score: float, audio_uncertainty: float,
                      visual_score: Optional[float],
                      base_visual_weight: float = 0.25,
                      uncertainty_gain: float = 0.5) -> Dict:
    """
    오디오(D-GOP)와 비주얼(웹캠 입모양) 점수의 후기 융합.
    농인은 음성이 불안정한 반면 입모양은 상대적으로 안정적이므로, 음향이 불확실한 구간일수록
    영상 가중치를 높인다. visual_score가 없으면 오디오 점수를 그대로 쓴다.
    (score는 0~100, uncertainty·weight는 0~1)
    """
    if visual_score is None:
        return {"score": round(audio_score, 1), "visual_weight": 0.0,
                "audio_score": round(audio_score, 1), "visual_score": None}
    w_v = base_visual_weight + uncertainty_gain * max(0.0, min(1.0, audio_uncertainty))
    w_v = max(0.0, min(0.9, w_v))  # 영상에 완전히 의존하지는 않음
    fused = (1.0 - w_v) * audio_score + w_v * float(visual_score)
    return {
        "score": round(fused, 1),
        "visual_weight": round(w_v, 3),
        "audio_score": round(audio_score, 1),
        "visual_score": round(float(visual_score), 1),
    }
