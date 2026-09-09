"""
GOP 채점식 변형 모음 — 축 B 재설계.

`dgop.dgop_phone`의 `naive × confidence`가 구조적으로 결함임이 드러났다
(ρ(naive, confidence)=0.980, 보정 방향이 반대 — `scripts/analyze_dgop_redundancy.py`).
그래서 문헌의 표준 변형들을 같은 표본 위에 올려 직접 비교한다.

**전부 순수 함수다.** 구간별로 미리 집계해 둔 통계(평균 확률·평균 로그확률·평균 로짓)만
입력받으므로 모델·GPU·오디오가 필요 없다. GPU는 그 통계를 한 번 덤프할 때만 쓰고
(`scripts/dump_gop_features.py`), 이후 채점식 비교는 무한히 재실행해도 공짜다
(`scripts/sweep_gop_scorers.py`).

── 왜 로짓까지 보관하는가 ────────────────────────────────────────────────
Yeo, Choi, Kim, Chung (Interspeech 2023, arXiv:2305.18392)이 구음장애 발화에서 GOP 변형을
비교한 결과, 엔트로피·마진 기반은 베이스라인보다 **나빴고**(한국어 Kendall τ −0.264 / −0.443
vs 베이스라인 −0.524) **MaxLogit만 이겼다**(−0.544). 이유는 명확하다 — softmax가 로짓의
크기 정보를 정규화로 지워 버리는데, OOD 입력(병리 발화)에서는 '모든 로짓이 낮다'는 그
정보가 바로 과신을 드러내는 신호이기 때문이다. 논문 표현으로 *"Softmax function is often
known to squash the useful information inside logits."*

우리 기존 세 항(naive·margin·엔트로피)은 전부 softmax **안에서** 계산된다. 그래서 로짓
기반 변형을 비교군에 반드시 넣어야 한다.

── blank는 이미 제외돼 있다 (2026-09-09 확인) ────────────────────────────
Cao, Fan, Svendsen, Salvi (Interspeech 2024)는 CTC 음소 평가에서 *"only non-blank tokens
contribute to the estimation, while the blank tokens are skipped"*라고 명시한다. 이 지적은
**A-5 이전 구현에는 유효했다** — 그때 align_targets가 정렬 경로를 토큰 id로 필터링해
`min~max` 구간을 잡았고, 그 안에 blank가 잔뜩 들어갔다.

A-5의 구간 뭉갬 수정으로 이 문제도 함께 사라졌다. `ctc_align.token_spans`는 '같은 비blank
라벨이 이어지는 run'만 구간으로 잡으므로 **구간 안에 blank가 원리적으로 0개**다(실측 확인).
그래서 blank 제외 변형을 따로 두지 않는다. 정렬 방식이 바뀌어 blank가 섞이기 시작하면
`dump_gop_features.span_aggregates`의 불변 검사(nb_frames != frames)가 알려준다.
"""
import math
from typing import Dict, Optional, Sequence

import dgop as _dgop

_NEG_INF = float("-inf")


def naive(mean_prob: Sequence[float], target_id: int, **_) -> float:
    """표준 GOP 근사 — 목표 음소의 평균 사후확률. 현행 대조군."""
    return float(mean_prob[target_id])


def dgop(mean_prob: Sequence[float], target_id: int, **_) -> float:
    """현행 D-GOP — naive × confidence. 결함이 밝혀졌으나 비교 기준으로 남긴다."""
    return float(_dgop.dgop_phone(mean_prob[target_id], mean_prob)["dgop"])


def gmm_gop(mean_logprob: Sequence[float], target_id: int, **_) -> float:
    """
    Witt & Young (2000) 계열 — 구간 평균 **로그**확률.
    확률 평균과 다르다: 한 프레임이라도 확률이 0에 가까우면 크게 벌한다.
    """
    return float(mean_logprob[target_id])


def nn_gop(mean_logprob: Sequence[float], target_id: int, **_) -> float:
    """
    Hu, Qian, Soong & Wang (2015)의 LPR(log posterior ratio) 형태 —
    목표 음소와 **최적 경쟁 음소**(목표 제외)의 로그확률 차이.

    ⚠️ 구현 선택: 경쟁 집합에서 목표를 **뺀다**. 문헌에는 전체 음소에 대해 max를 취하는
    형태도 있는데(`log P(p) − max_q log P(q)`, q가 p를 포함), 그러면 목표가 argmax인 순간
    값이 **0으로 포화**해 '아슬아슬하게 1등'과 '압도적 1등'을 구별하지 못한다. 정확히 그
    구간이 우리가 해상도를 필요로 하는 곳이라(정상 발화 대부분이 여기 있다) 포화형은
    순위 매기기에 쓸 수 없다. test_scorers_reward_correct_pronunciation이 이를 잡아냈다.
    """
    best_other = max((v for i, v in enumerate(mean_logprob) if i != target_id),
                     default=_NEG_INF)
    return float(mean_logprob[target_id] - best_other)


def dnn_gop(mean_prob: Sequence[float], target_id: int,
            prior: Optional[Sequence[float]] = None, **_) -> float:
    """
    사후확률을 사전확률로 나눈 값(로그). 빈도가 높은 음소가 그냥 높은 점수를 받는 편향을 걷는다.
    prior가 없으면 균등분포로 둔다(= naive의 단조 변환이 되어 순위가 같아진다).
    """
    p = float(mean_prob[target_id])
    if p <= 0:
        return _NEG_INF
    pr = 1.0 / len(mean_prob) if prior is None else float(prior[target_id])
    if pr <= 0:
        return _NEG_INF
    return math.log(p) - math.log(pr)


def maxlogit(mean_logit: Sequence[float], target_id: int, **_) -> float:
    """
    Yeo et al. (2023)에서 **유일하게 베이스라인을 이긴** 변형 — 목표 음소의 평균 로짓 그대로.
    softmax를 거치지 않아 '모든 로짓이 낮다'(=OOD)는 신호가 살아남는다.
    """
    return float(mean_logit[target_id])


def prior_maxlogit(mean_logit: Sequence[float], target_id: int,
                   prior: Optional[Sequence[float]] = None, **_) -> float:
    """Yeo et al. (2023)의 최고 성능 조합 — MaxLogit에 prior normalization."""
    lg = float(mean_logit[target_id])
    if prior is None:
        return lg
    pr = float(prior[target_id])
    return lg - math.log(pr) if pr > 0 else _NEG_INF


def logit_margin(mean_logit: Sequence[float], target_id: int, **_) -> float:
    """목표 로짓과 최고 경쟁 로짓의 차. 로짓 공간에서의 여유값."""
    best_other = max((v for i, v in enumerate(mean_logit) if i != target_id),
                     default=_NEG_INF)
    return float(mean_logit[target_id] - best_other)


def confidence_only(mean_prob: Sequence[float], target_id: int, **_) -> float:
    """
    confidence 항 단독 — naive와 얼마나 겹치는지 스윕에서 직접 보이기 위한 진단용.
    채점식 후보가 아니다.
    """
    return float(_dgop.phone_confidence(mean_prob))


# 스윕 대상. 값은 (함수, 필요한 집계 키) — 덤프에 그 키가 없으면 건너뛴다.
SCORERS: Dict[str, tuple] = {
    "naive":          (naive,          "mean_prob"),
    "dgop":           (dgop,           "mean_prob"),
    "confidence":     (confidence_only, "mean_prob"),
    "gmm_gop":        (gmm_gop,        "mean_logprob"),
    "nn_gop":         (nn_gop,         "mean_logprob"),
    "dnn_gop":        (dnn_gop,        "mean_prob"),
    "maxlogit":       (maxlogit,       "mean_logit"),
    "prior_maxlogit": (prior_maxlogit, "mean_logit"),
    "logit_margin":   (logit_margin,   "mean_logit"),
}
"""
문헌 대응:
  naive / dgop                    현행 (대조군)
  gmm_gop                         Witt & Young 2000
  nn_gop                          Hu et al. 2015 (LPR)
  dnn_gop                         Hu et al. 2015 (prior 정규화)
  maxlogit / prior_maxlogit       Yeo et al. 2023 — 후자가 그 논문의 최고 성능
  logit_margin                    Yeo et al. 2023
  confidence                      진단용(채점식 후보 아님)
"""


def score_span(name: str, span: Dict, prior: Optional[Sequence[float]] = None) -> Optional[float]:
    """
    집계 통계 딕셔너리 하나에 채점식 하나를 적용한다.
    span은 {"target_id": int, "mean_prob": [...], "mean_logprob": [...], "mean_logit": [...]}
    형태이며, 필요한 키가 없으면 None을 돌려준다(그 변형은 스윕에서 제외된다).
    """
    fn, key = SCORERS[name]
    vec = span.get(key)
    if vec is None:
        return None
    return fn(**{key: vec}, target_id=int(span["target_id"]), prior=prior)
