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
"""
from typing import Dict, List, Optional, Sequence, Tuple

Trial = Tuple[str, bool]      # (item_type, correct), 시간순

MIN_PER_TYPE = 9              # 한 유형을 1/3씩(3시행 이상) 나누려면 9시행
TYPE_LABELS = {"viseme": "입모양 인지", "word": "단어", "word_typed": "단어 주관식", "closure": "문맥 추론"}


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
    return {
        "baseline_acc": round(base * 100, 1), "recent_acc": round(rec * 100, 1),
        "delta_pp": round((rec - base) * 100, 1), "n_each": w,
        "by_type": [{"item_type": t, "label": TYPE_LABELS.get(t, t), "n": n, "n_each": k,
                     "baseline_acc": round(e * 100, 1), "recent_acc": round(l * 100, 1),
                     "delta_pp": round((l - e) * 100, 1)} for t, n, k, e, l in parts],
        "method": "within_type",
        "note": "유형(입모양·단어·문맥)마다 그 유형의 처음 1/3과 최근 1/3을 비교해 시행 수로 가중 평균했습니다. "
                "단계가 바뀌며 문항 유형이 달라지는 효과는 빠지지만, 통제된 사전·사후 검사는 아닙니다.",
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
