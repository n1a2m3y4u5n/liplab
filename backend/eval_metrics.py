"""학습 효과 리포트(/api/eval/summary)의 지표 계산. 순수 함수라 시뮬레이션(scripts/eval_metrics_sim.py)과 테스트가 같은 코드를 쓴다.

예전 지표의 문제(docs/eval-metrics.md):
- 초기 대비 최근: 전체 선다형 시행을 시간순으로 3등분해 비교했다. 학습 경로가 입모양 인지 → 단어 → 문맥 추론 순이라
  처음 1/3은 대개 입모양 인지, 마지막 1/3은 단어·문맥 문항이다. 유형마다 정답률이 달라 실력이 그대로여도 차이가 났다.
- 학습곡선: 같은 이유로 유형이 바뀌는 구간에서 곡선이 계단처럼 움직였다.
- 숙달 도달 시행수: 숙달한 뒤에도 계속 늘어나는 현재 시도 수를 최소 시도 수와 나란히 보여 줬다.

이제
- 초기 대비 최근: 유형마다 그 유형 시행의 처음 1/3과 마지막 1/3을 비교하고, 비교에 쓴 시행 수로 가중 평균한다.
- 학습곡선: 각 시행의 정답(0/1)에서 그 유형의 평균을 빼고 전체 평균을 더한 값(유형 고정효과 보정)을 구간마다 평균한다.
  유형이 시간 순서와 겹치므로 유형 사이의 차이는 난이도로 보고 뺀다. 남는 것은 유형 안의 변화라 보수적인 추정이다.
- 숙달 도달 시행수: 처음 숙달한 순간의 시도 수(StageProgress.mastered_attempts)를 쓴다.
- 문장 점수 추이: 같은 방법으로 문장 난이도(difficulty_level) 차이를 뺀다. 경로가 쉬운 문장에서 어려운 문장으로 가므로
  보정 전 점수는 실력이 늘어도 내려갈 수 있다.
- 개인 전후 차이의 색(9/29): 두 정답률 차이의 Newcombe 95% 구간(Wilson 점수 구간 결합)이 0을 벗어날 때만 좋아짐·나빠짐으로
  칠한다. 예전에는 부호만 보고 칠해 학습 효과가 없어도 사전·사후 비교의 35~46%가 빨강이었다(docs/eval-metrics.md 6절).
"""
import math
from typing import Dict, List, Optional, Sequence, Tuple

Trial = Tuple[str, bool]      # (item_type, correct), 시간순

MIN_PER_TYPE = 9              # 한 유형을 1/3씩(3시행 이상) 나누려면 9시행
TYPE_LABELS = {"viseme": "입모양 인지", "viseme_ax": "입모양 같은지 다른지", "word": "단어", "word_typed": "단어 주관식",
               "context": "단어 레슨 문맥", "closure": "문맥 추론"}


Z95 = 1.959963984540054


def wilson_interval(x: float, n: float, z: float = Z95) -> Optional[Tuple[float, float]]:
    """정답률 x/n의 Wilson 점수 구간. n이 0이면 None."""
    if not n:
        return None
    p = x / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, mid - half), min(1.0, mid + half)


def newcombe_diff(x1: float, n1: float, x2: float, n2: float, z: float = Z95) -> Optional[Dict]:
    """두 독립 정답률의 차이 p2 − p1과 Newcombe(1998) 방법 10의 95% 구간(두 Wilson 구간 결합).
    clear는 구간이 0을 벗어났는지다. 화면은 clear일 때만 좋아짐·나빠짐 색을 쓰고, 아니면 중립으로 둔다.
    문항 난이도가 서로 달라 실제 분산은 이항보다 작으므로 이 구간은 보수적이다."""
    w1, w2 = wilson_interval(x1, n1, z), wilson_interval(x2, n2, z)
    if w1 is None or w2 is None:
        return None
    p1, p2 = x1 / n1, x2 / n2
    d = p2 - p1
    lo = d - math.sqrt((p2 - w2[0]) ** 2 + (w1[1] - p1) ** 2)
    hi = d + math.sqrt((w2[1] - p2) ** 2 + (p1 - w1[0]) ** 2)
    return {"diff": round(d, 3), "ci95": [round(lo, 3), round(hi, 3)], "clear": lo > 0 or hi < 0}


NATURAL_SPEED_TOL = 0.01


def is_natural_trial(speed, is_probe) -> bool:
    """초기 대비 최근·학습곡선에 넣는 시행: 1.0배(속도 기록 없음 포함)로 본 보통 문항. 빠른 말(1.25~2배)은 숙달 뒤에만 나와
    뒤 1/3에 몰려 실력이 그대로여도 떨어져 보이고, 감속(0.75배) 정답은 앞쪽에 몰려 앞을 올린다. 짝 탐색 문항(probe)은 헷갈리는
    대비 단어를 일부러 보기에 넣은 문항이라 보통 문항과 난이도가 다르다(docs/eval-metrics.md 7절)."""
    if is_probe:
        return False
    if speed is None:
        return True
    try:
        return abs(float(speed) - 1.0) <= NATURAL_SPEED_TOL
    except (TypeError, ValueError):
        return True


def _bins(n: int, n_bins: int) -> List[Tuple[int, int]]:
    bins = min(n_bins, n)
    return [((n * b) // bins, (n * (b + 1)) // bins) for b in range(bins)]


def pooled_change(trials: Sequence[Trial]) -> Optional[Dict]:
    """예전 방식: 전체 시행의 처음 1/3과 마지막 1/3 정확도(비교·시뮬레이션용)."""
    n = len(trials)
    if n < MIN_PER_TYPE:
        return None
    k = n // 3
    e = sum(1 for _, c in trials[:k] if c) / k
    l = sum(1 for _, c in trials[-k:] if c) / k
    return {"baseline": e, "recent": l, "delta": l - e, "n_each": k}


def within_type_change(trials: Sequence[Trial], min_n: int = MIN_PER_TYPE) -> Optional[Dict]:
    """유형별 처음 1/3 대 마지막 1/3 정확도를 비교한 시행 수로 가중 평균한다. 9시행 이상인 유형이 없으면 None."""
    by: Dict[str, List[float]] = {}
    for t, c in trials:
        by.setdefault(t, []).append(1.0 if c else 0.0)
    parts = []
    for t, xs in by.items():
        n = len(xs)
        if n < min_n:
            continue
        k = n // 3
        parts.append((t, n, k, sum(xs[:k]) / k, sum(xs[-k:]) / k))
    if not parts:
        return None
    w = sum(k for _, _, k, _, _ in parts)
    base = sum(k * e for _, _, k, e, _ in parts) / w
    rec = sum(k * l for _, _, k, _, l in parts) / w
    order = list(TYPE_LABELS)
    parts.sort(key=lambda p: order.index(p[0]) if p[0] in order else len(order))
    # 가중 평균은 앞·뒤 1/3의 정답 수를 합친 것과 같다(k·e가 정수). 두 묶음을 독립 표본으로 보고 Newcombe 구간을 낸다
    nc = newcombe_diff(base * w, w, rec * w, w)
    return {
        "baseline_acc": round(base * 100, 1), "recent_acc": round(rec * 100, 1),
        "delta_pp": round((rec - base) * 100, 1), "n_each": w,
        "ci95_pp": [round(nc["ci95"][0] * 100, 1), round(nc["ci95"][1] * 100, 1)], "clear": nc["clear"],
        "by_type": [{"item_type": t, "label": TYPE_LABELS.get(t, t), "n": n, "n_each": k,
                     "baseline_acc": round(e * 100, 1), "recent_acc": round(l * 100, 1),
                     "delta_pp": round((l - e) * 100, 1)} for t, n, k, e, l in parts],
        "method": "within_type",
        "note": "유형(입모양·단어·문맥)마다 그 유형의 처음 1/3과 최근 1/3을 비교해 시행 수로 가중 평균했습니다. "
                "단계가 바뀌며 문항 유형이 달라지는 효과는 빠지지만, 통제된 사전·사후 검사는 아닙니다. "
                "빠른 말·느린 재생과 헷갈리는 짝 문항은 난이도가 달라 세지 않습니다.",
    }


def group_adjusted_curve(items: Sequence[Tuple[object, float]], n_bins: int = 8, lo: Optional[float] = None,
                         hi: Optional[float] = None, ndigits: int = 3) -> List[Dict]:
    """시간순 (묶음, 값)을 최대 n_bins개 구간으로 나눠 평균한다. value는 묶음 평균을 빼고 전체 평균을 더한 값
    (묶음 고정효과 보정, [lo, hi]로 자름), raw는 보정 전 평균."""
    n = len(items)
    if not n:
        return []
    vals = [float(v) for _, v in items]
    overall = sum(vals) / n
    sums: Dict[object, List[float]] = {}
    for (g, _), v in zip(items, vals):
        s = sums.setdefault(g, [0.0, 0])
        s[0] += v
        s[1] += 1
    mean_g = {g: tot / k for g, (tot, k) in sums.items()}
    adj = [v - mean_g[g] + overall for (g, _), v in zip(items, vals)]
    out = []
    for b, (a, z) in enumerate(_bins(n, n_bins)):
        if z <= a:
            continue
        m = sum(adj[a:z]) / (z - a)
        if lo is not None:
            m = max(lo, m)
        if hi is not None:
            m = min(hi, m)
        out.append({"bin": b + 1, "n": z - a, "value": round(m, ndigits), "raw": round(sum(vals[a:z]) / (z - a), ndigits)})
    return out


def type_adjusted_curve(trials: Sequence[Trial], n_bins: int = 8) -> List[Dict]:
    """선다형 학습곡선: 유형(입모양·단어·문맥) 고정효과를 뺀 정확도(0~1)."""
    return group_adjusted_curve([(t, 1.0 if c else 0.0) for t, c in trials], n_bins, lo=0.0, hi=1.0)


def criterion_progress(mastered: bool, attempts: int, mastery: float, threshold: float, min_attempts: int) -> float:
    """숙달까지의 진행(0~1). 숙달은 '최소 시도 수'와 '숙달 점수' 두 조건이라 더 모자란 쪽을 보여 준다."""
    if mastered:
        return 1.0
    if not threshold or not min_attempts:
        return 0.0
    return round(max(0.0, min(1.0, (mastery or 0.0) / threshold, (attempts or 0) / min_attempts)), 3)


ANSWER_MODE_LABELS = {"choice": "보기 고름(4지선다)", "typed": "직접 입력(주관식·서술형)", "unknown": "기록 없음"}


def by_answer_mode(rows: Sequence[Tuple[Optional[str], float]], pass_score: float) -> List[Dict]:
    """문장 점수를 답 방식별로 나눈다. rows는 (answer_mode, score). 4지선다는 정확 일치(100 또는 0)라 몰라도 25%가 합격하고,
    직접 입력은 부분 점수라 두 방식의 평균·합격률을 한 값으로 섞으면 어느 쪽 실력인지 알 수 없다(docs/eval-metrics.md 4절).
    answer_mode가 없는 행(9/29 전 기록·옛 화면)은 'unknown'으로 따로 둔다. 행이 있는 방식만 choice·typed·unknown 순서로 돌려준다."""
    groups: Dict[str, List[float]] = {}
    for mode, score in rows:
        key = mode if mode in ("choice", "typed") else "unknown"
        groups.setdefault(key, []).append(float(score or 0.0))
    out = []
    for key in ("choice", "typed", "unknown"):
        seg = groups.get(key)
        if not seg:
            continue
        out.append({"mode": key, "label": ANSWER_MODE_LABELS[key], "n": len(seg),
                    "avg_score": round(sum(seg) / len(seg), 1),
                    "pass_rate": round(sum(1 for s in seg if s >= pass_score) / len(seg) * 100, 1)})
    return out
