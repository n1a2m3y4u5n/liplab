"""
전사 비의존 발음정확도(D-GOP) — 고도화 축 B 핵심 로직.

표준 GOP(Goodness of Pronunciation)는 목표 음소가 놓일 구간의 음향이 그 음소에 얼마나
부합하는지를 사후확률로 점수화한다. 목표 문장을 시스템이 이미 알기 때문에 전사가 필요 없다.
그러나 표준 GOP는 정상 발화를 전제해, 발음이 뭉개진 농인 발화에서 오히려 과신(점수가 붕괴적으로
높아짐)하는 문제가 있다(예비 실증에서 확인). D-GOP는 예측 분포의 불확실성(엔트로피·상위 확률
여유)으로 naive 점수를 보정하고, 음향이 불확실한 구간일수록 영상(입모양) 신호에 더 가중해 후기
융합한다.

⚠️ **이 모듈의 채점식(dgop_phone)은 재설계 대상이다**(2026-09-09). 과신이라는 문제 인식은
문헌이 지지하지만(Yeo et al., Interspeech 2023), naive×confidence라는 곱셈 형태는 그 문제를
잡지 못한다 — 두 항이 중복이고 보정 방향이 반대다. 같은 논문이 한국어 구음장애 발화에서
엔트로피·마진 기반 GOP가 베이스라인보다 **나쁘고**(τ −0.264 / −0.443 vs −0.524) softmax를
탈출하는 MaxLogit만 이긴다(−0.544)고 보고한다. 상세는 docs/deaf-speech-data-research.md §0.

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
    반환: {naive, confidence, uncertainty, dgop} (모두 0~1).

    ⚠️ 2026-09-09 — 이 식은 의도한 일을 하지 못한다. 원래 주석은 "분포가 평평할수록 신뢰도가
    낮아 점수가 과신되지 않는다"였는데 **방향이 틀렸다**. 과신이란 분포가 *뾰족한데* 틀린
    것이고, confidence가 재는 것이 바로 그 뾰족함이라 과신 구간을 그대로 통과시킨다. 실제로
    걷히는 것은 과소확신(평평한 분포)이다. 게다가 naive와 confidence는 둘 다 첨도의 단조
    함수라 순위상관이 0.98이어서, 곱셈이 순위 정보를 더하지 못하고 잡음만 더한다.
    재현: scripts/analyze_dgop_redundancy.py · 근거·대안: docs/deaf-speech-data-research.md §0
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


# ── 표시용 점수 보정(calibration) ────────────────────────────────────────────
# A-3 실행(2026-09-08)이 남긴 한계 ②: D-GOP 원점수는 변별력은 충분하지만 스케일이 압축돼
# 있다. 깨끗한 발화가 9.51/100이라 학습자에게 그대로 보여줄 수 없다(구간 평균 분포에 CTC
# blank가 지배적인 프레임이 섞여 target_prob이 구조적으로 낮게 나온다).
#
# 원점수는 손대지 않고 **표시용 점수**를 따로 만든다. 기준 발화 집합의 severity별 대표
# 원점수를 앵커로 잡고 그 사이를 단조 보간한다. 보간은 log 공간에서 한다 — 원점수가
# severity에 따라 대략 기하급수로 줄기 때문이다(9.51 → 2.74 → 1.49 → 0.61 → 0.30).
#
# 보정은 **단조 증가 변환**이라 A-3 변별력 지표(순위상관·AUC)는 보정 전후가 같다.
# 바뀌는 것은 사람이 읽는 숫자뿐이다 — 변별력을 사후에 만들어내지 않는다.
#
# 체크포인트를 바꾸면 원점수 스케일도 바뀐다. scripts/fit_dgop_calibration.py로 다시
# 맞춰 JSON을 갈아끼운다(dgop_acoustic.load_calibration).

CALIBRATION_FLOOR = 0.05
"""log 변환의 유사계수. 원점수 0(정렬은 됐으나 전부 빗나감)도 다룰 수 있게 한다."""

DISPLAY_TARGETS_BY_SEVERITY = [90.0, 72.0, 58.0, 40.0, 20.0]
"""
severity 0~4의 대표 원점수를 각각 몇 점으로 보이게 할지 — 제품 결정이다.
기준은 speak_curriculum의 합격선(음소 50, 단어·문장 65): 정상 발화(0)는 넉넉히 통과(90),
경도 저하(1)는 통과선 바로 위(72), 중등도(2)는 단어·문장 합격선 아래지만 음소는 통과(58),
중증(3·4)은 확실히 미달(40·20). 만점(100)은 앵커에서 외삽한다 — 정상 발화 대표값보다
뚜렷하게 좋아야 100이 나오게 하기 위함이다.
"""


def fit_calibration(raw_by_severity: Sequence[float],
                    targets: Optional[Sequence[float]] = None,
                    source: str = "") -> Dict:
    """
    severity별 대표 원점수(중앙값 권장) → 보정 앵커. 순수 함수라 결정론적으로 테스트된다.

    앵커는 raw 오름차순으로 **엄격히 단조**여야 보간이 성립한다. 원점수가 severity를
    거스르는 구간(예: A-3 베이스라인의 severity 3→4 역전)은 앵커에서 버리고 dropped에
    남긴다 — 역전을 그대로 앵커로 삼으면 보정이 뒤집혀 더 나쁜 발음에 더 높은 점수가 간다.

    양끝: 원점수 0은 0점, 최상위 앵커의 기울기를 그대로 연장한 지점을 100점으로 둔다.
    """
    tg = list(targets if targets is not None else DISPLAY_TARGETS_BY_SEVERITY)
    raws = [float(r) for r in raw_by_severity]
    if len(raws) < 2:
        raise ValueError("앵커를 만들려면 severity 대표값이 최소 2개 필요합니다")
    if len(tg) < len(raws):
        raise ValueError(f"표시 목표({len(tg)}개)가 severity({len(raws)}개)보다 적습니다")

    pairs = sorted(zip(raws, tg[:len(raws)], range(len(raws))))  # raw 오름차순
    anchors: List[List[float]] = [[0.0, 0.0]]
    dropped: List[int] = []
    for raw, display, sev in pairs:
        if raw > anchors[-1][0] and display > anchors[-1][1]:
            anchors.append([round(raw, 4), float(display)])
        else:
            dropped.append(sev)          # 단조를 깨는 severity
    if len(anchors) < 3:                 # (0,0) 외에 앵커가 둘은 있어야 기울기가 나온다
        raise ValueError(f"단조인 앵커가 부족합니다(버려진 severity: {dropped})")

    # 최상위 구간의 기울기(점/decade)를 연장해 100점 지점을 잡는다.
    (r1, d1), (r2, d2) = anchors[-2], anchors[-1]
    x1, x2 = _cal_x(r1, CALIBRATION_FLOOR), _cal_x(r2, CALIBRATION_FLOOR)
    slope = (d2 - d1) / (x2 - x1)
    if d2 < 100.0 and slope > 0:
        top = 10 ** (x2 + (100.0 - d2) / slope) - CALIBRATION_FLOOR
        anchors.append([round(top, 4), 100.0])

    return {"source": source, "floor": CALIBRATION_FLOOR,
            "anchors": anchors, "dropped_severities": dropped}


def _cal_x(raw: float, floor: float) -> float:
    """보간 좌표. 원점수를 log 공간으로 옮긴다(floor는 0을 다루기 위한 유사계수)."""
    return math.log10(max(float(raw), 0.0) + floor)


# 축 A A-4 실측(2026-09-09, zeroth_korean test 50발화 × severity 0~4)의 severity별 **중앙값**.
# 앱이 별도 보정 파일 없이도 사람이 읽을 수 있는 점수를 내도록 이 값을 기본 앵커로 쓴다.
# backend/data/dgop_calibration.json과 같은 값이라, 파일이 없어도 동작이 달라지지 않는다.
#
# 2026-09-08에 잰 [9.51, 2.74, 1.49, 0.61, 0.30]을 대체한 값이다. 그때는 align_targets에
# 구간 뭉갬 버그가 있어 원점수가 구조적으로 낮게 나왔다(중복 출현 토큰의 구간을 '첫 출현~
# 마지막 출현'으로 잡아 발화 대부분을 삼켰다). 버그 수정 후 같은 체크포인트에서 깨끗한
# 발화가 9.51 → 78.15로 올랐다 — 한계 ②(스케일 압축)의 실제 원인이 이 버그였다.
#
# ⚠️ 체크포인트를 바꾸면 이 값도 무효다 — scripts/fit_dgop_calibration.py로 재적합한다(런북 §6.5).
AXIS_A_SEVERITY_SCORES = [78.15, 31.65, 15.2, 2.9, 0.85]

DEFAULT_CALIBRATION = fit_calibration(
    AXIS_A_SEVERITY_SCORES,
    source="axis-a/2026-09-09 zeroth_korean test 50발화 severity 중앙값")


def calibrate_score(raw_score: Optional[float], calibration: Optional[Dict] = None) -> Optional[float]:
    """
    원점수(0~100) → 표시용 점수(0~100). 앵커 사이를 log 공간에서 선형 보간하고 양끝은 고정한다.
    raw_score가 None이면 None을 그대로 돌려준다(채점 불가를 점수 0으로 둔갑시키지 않는다).
    """
    if raw_score is None:
        return None
    cal = calibration or DEFAULT_CALIBRATION
    anchors = cal["anchors"]
    floor = float(cal.get("floor", CALIBRATION_FLOOR))
    x = _cal_x(raw_score, floor)

    if x <= _cal_x(anchors[0][0], floor):
        return round(float(anchors[0][1]), 1)
    for (r1, d1), (r2, d2) in zip(anchors, anchors[1:]):
        x1, x2 = _cal_x(r1, floor), _cal_x(r2, floor)
        if x <= x2:
            t = (x - x1) / (x2 - x1) if x2 > x1 else 1.0
            return round(max(0.0, min(100.0, d1 + t * (d2 - d1))), 1)
    return round(float(anchors[-1][1]), 1)   # 최상위 앵커 초과 — 만점에서 멈춘다
