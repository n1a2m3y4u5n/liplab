"""
복습 스케줄러 FSRS 그림자 모드(종합 계획 C11, idea-sweep 다4).

`srs.py`는 SM-2에 자료 없이 정한 값을 쓴다. 여기서는 공개 FSRS-5 기본 매개변수로 복습마다 회상 확률 R을 예측해 결과와 함께
기록만 한다. **간격은 바꾸지 않는다**(다음 예정일은 계속 srs.schedule이 정한다). 기록이 쌓이면 `compare`로 FSRS·상수 예측·SM-2 대리
예측의 log loss와 보정표를 낸다. 교체 판단(복습 300건 이상, 학습자 단위 시간순 분할, FSRS log loss가 두 비교 대상보다 낮고 예측 R 구간별
실제 통과율 차이가 평균 5%p 이내)은 나중에 사람이 한다. 이 모듈은 보고만 한다.

출처(식과 기본값을 직접 옮겼다. 외부 라이브러리를 쓰지 않아 의존성·라이선스 확인이 필요 없다):
- Ye, Su, Cao 2022 KDD "A Stochastic Shortest Path Algorithm for Optimizing Spaced Repetition Scheduling"
  https://dl.acm.org/doi/10.1145/3534678.3539081
- open-spaced-repetition 'The Algorithm' 위키의 FSRS-5 절(망각 곡선, 초기 안정도·난이도, 난이도 선형 감쇠와 평균 회귀,
  같은 날 복습의 단기 안정도, 기본 매개변수 19개) https://github.com/open-spaced-repetition/awesome-fsrs/wiki/The-Algorithm
  회상·망각 뒤 안정도 식은 FSRS-4.5와 같고, 망각 뒤 안정도는 FSRS-5에서 S / e^(w17·w18) 이하로 자른다.
  (py-fsrs 5.x의 기본값은 매개변수 21개인 FSRS-6이라 이 값과 다르다. 2026-10-06 위키에서 FSRS-5 기본값을 확인했다.)

**순수 함수**만 둔다. DB·현재 시각을 쓰지 않는다. 날짜 계산과 저장은 main.py(_srs_apply)가 한다.

앱의 답을 FSRS 등급으로 옮기는 규칙(idea-sweep 다4):
- 오답 → Again(1). 감속(1.0배 미만) 정답 → Hard(2).
- 복습 화면의 정답(보기 고름·자연 속도 직접 입력)과 문장 4지선다 정답 → Good(3). 찍기 몫은 등급이 아니라 관측 확률에서 다룬다:
  4지선다 답의 관측 정답 확률 = 0.25 + 0.75·R(`observed_probability`).
- 점수로 채점하는 답(문장 직접 입력, 말하기)은 SM-2 품질 3·4·5를 Hard·Good·Easy로 옮긴다.
"""
import math
from typing import Dict, Iterable, List, Optional, Sequence

# FSRS-5 기본 매개변수(w0~w18). 위 위키의 FSRS-5 기본값 그대로다.
DEFAULT_W = (0.40255, 1.18385, 3.173, 15.69105, 7.1949, 0.5345, 1.4604, 0.0046, 1.54575, 0.1192,
             1.01925, 1.9395, 0.11, 0.29605, 2.2698, 0.2315, 2.9898, 0.51655, 0.6621)
DECAY = -0.5
FACTOR = 19.0 / 81.0        # R(S, S) = 0.9가 되게 하는 값
S_MIN = 0.01                # 안정도(일) 하한. 0으로 나누지 않게
D_MIN, D_MAX = 1.0, 10.0
AGAIN, HARD, GOOD, EASY = 1, 2, 3, 4
CHOICE_GUESS = 0.25         # 4지선다 찍기 확률(복습 입모양·단어, 문장 4지선다)
SM2_PROXY_RETENTION = 0.9   # SM-2 대리 예측: 예정 간격에서 회상 0.9라고 보는 지수 망각(아래 sm2_proxy)
MIN_REVIEWS = 300           # 교체 판단을 볼 최소 복습 수(idea-sweep 다4)
CALIBRATION_GAP_MAX = 0.05  # 예측 구간별 실제 통과율 차이 평균의 상한(5%p)


def _clamp_d(d: float) -> float:
    return min(D_MAX, max(D_MIN, d))


def retrievability(elapsed_days: float, stability: float) -> float:
    """망각 곡선 R(t, S) = (1 + FACTOR·t/S)^DECAY. t는 마지막 복습 뒤 지난 날수."""
    t = max(0.0, float(elapsed_days))
    s = max(S_MIN, float(stability))
    return (1.0 + FACTOR * t / s) ** DECAY


def init_stability(grade: int, w: Sequence[float] = DEFAULT_W) -> float:
    return max(S_MIN, w[int(grade) - 1])


def init_difficulty(grade: int, w: Sequence[float] = DEFAULT_W, clamp: bool = True) -> float:
    """D0(G) = w4 − e^(w5·(G−1)) + 1."""
    d = w[4] - math.exp(w[5] * (int(grade) - 1)) + 1.0
    return _clamp_d(d) if clamp else d


def next_difficulty(d: float, grade: int, w: Sequence[float] = DEFAULT_W) -> float:
    """ΔD = −w6·(G−3), 선형 감쇠 D' = D + ΔD·(10−D)/9, 평균 회귀 D'' = w7·D0(4) + (1−w7)·D'."""
    delta = -w[6] * (int(grade) - 3)
    d1 = d + delta * (10.0 - d) / 9.0
    d2 = w[7] * init_difficulty(EASY, w, clamp=False) + (1.0 - w[7]) * d1
    return _clamp_d(d2)


def recall_stability(d: float, s: float, r: float, grade: int, w: Sequence[float] = DEFAULT_W) -> float:
    """기억해 낸 뒤 안정도: S·(1 + e^w8·(11−D)·S^(−w9)·(e^(w10·(1−R)) − 1)·hard·easy)."""
    hard = w[15] if grade == HARD else 1.0
    easy = w[16] if grade == EASY else 1.0
    inc = math.exp(w[8]) * (11.0 - d) * (s ** -w[9]) * (math.exp(w[10] * (1.0 - r)) - 1.0) * hard * easy
    return max(S_MIN, s * (1.0 + inc))


def forget_stability(d: float, s: float, r: float, w: Sequence[float] = DEFAULT_W) -> float:
    """잊은 뒤 안정도: w11·D^(−w12)·((S+1)^w13 − 1)·e^(w14·(1−R)), 단 S / e^(w17·w18) 이하(FSRS-5)."""
    long_term = w[11] * (d ** -w[12]) * ((s + 1.0) ** w[13] - 1.0) * math.exp(w[14] * (1.0 - r))
    cap = s / math.exp(w[17] * w[18])
    return max(S_MIN, min(long_term, cap))


def short_term_stability(s: float, grade: int, w: Sequence[float] = DEFAULT_W) -> float:
    """같은 날 다시 본 복습: S' = S·e^(w17·(G−3+w18))."""
    return max(S_MIN, s * math.exp(w[17] * (int(grade) - 3 + w[18])))


def step(state: Optional[Dict], grade: int, elapsed_days: Optional[float], w: Sequence[float] = DEFAULT_W) -> Dict:
    """한 번의 복습을 반영한다. state = {stability, difficulty} 또는 None(처음 본 항목).

    반환: {stability, difficulty, r}. r은 이 복습 **전에** 예측한 회상 확률이다(처음이면 None)."""
    g = max(AGAIN, min(EASY, int(grade)))
    if not state or state.get("stability") is None or state.get("difficulty") is None:
        return {"stability": init_stability(g, w), "difficulty": init_difficulty(g, w), "r": None}
    s, d = float(state["stability"]), float(state["difficulty"])
    t = max(0.0, float(elapsed_days or 0))
    r = retrievability(t, s)
    if t < 1:
        s2 = short_term_stability(s, g, w)
    elif g == AGAIN:
        s2 = forget_stability(d, s, r, w)
    else:
        s2 = recall_stability(d, s, r, g, w)
    return {"stability": s2, "difficulty": next_difficulty(d, g, w), "r": r}


def grade_for(quality: int, answer_mode: Optional[str] = None, speed: Optional[float] = None) -> int:
    """앱의 답을 FSRS 등급으로(머리말 규칙). quality는 srs 품질등급(0~5, 3 이상이 합격)."""
    q = int(quality)
    if q < 3:
        return AGAIN
    try:
        slowed = speed is not None and float(speed) < 0.999
    except (TypeError, ValueError):
        slowed = False
    if slowed:
        return HARD
    if answer_mode in ("choice", "typed"):
        return GOOD
    return {3: HARD, 4: GOOD}.get(q, EASY)


def guess_rate(answer_mode: Optional[str]) -> float:
    """답 방식별 찍기 확률. 4지선다만 0.25, 나머지(직접 입력·말하기)는 0."""
    return CHOICE_GUESS if answer_mode == "choice" else 0.0


def observed_probability(r: Optional[float], guess: float = 0.0) -> Optional[float]:
    """회상 확률 R을 관측 정답 확률로: guess + (1 − guess)·R. 4지선다는 0.25 + 0.75·R."""
    if r is None:
        return None
    g = max(0.0, min(1.0, float(guess)))
    return g + (1.0 - g) * max(0.0, min(1.0, float(r)))


def sm2_proxy(elapsed_days: Optional[float], interval_days: Optional[float]) -> Optional[float]:
    """SM-2 대리 예측: SM-2는 확률을 내지 않으므로 '예정 간격 I에서 회상 0.9'인 지수 망각 0.9^(t/I)로 본다.
    간격이 없으면 None."""
    if elapsed_days is None or not interval_days:
        return None
    return SM2_PROXY_RETENTION ** (max(0.0, float(elapsed_days)) / max(1.0, float(interval_days)))


# ── 분석(보고만 한다) ──

def log_loss(ps: Iterable[float], ys: Iterable[int], eps: float = 1e-4) -> Optional[float]:
    ps, ys = list(ps), list(ys)
    if not ps:
        return None
    tot = 0.0
    for p, y in zip(ps, ys):
        p = min(1 - eps, max(eps, float(p)))
        tot += -(math.log(p) if y else math.log(1 - p))
    return tot / len(ps)


def calibration_table(ps: Sequence[float], ys: Sequence[int], bins: int = 10) -> Dict:
    """예측 확률을 같은 폭 구간으로 나눠 구간별 (문항 수, 평균 예측, 실제 통과율, 차이). gap_mean은 문항 수로 가중한 |차이| 평균."""
    rows = []
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, p in enumerate(ps) if (lo <= p < hi) or (b == bins - 1 and p >= hi)]
        if not idx:
            continue
        mp = sum(ps[i] for i in idx) / len(idx)
        obs = sum(ys[i] for i in idx) / len(idx)
        rows.append({"bin": [round(lo, 2), round(hi, 2)], "n": len(idx), "mean_pred": round(mp, 4),
                     "observed": round(obs, 4), "gap": round(obs - mp, 4)})
    n = sum(r["n"] for r in rows)
    gap = sum(abs(r["gap"]) * r["n"] for r in rows) / n if n else None
    return {"bins": rows, "gap_mean": None if gap is None else round(gap, 4)}


def time_split(rows: Sequence[Dict], train_frac: float = 0.7):
    """학습자 단위 시간순 분할: 학습자마다 시간순으로 앞 train_frac은 학습, 뒤는 평가. 복습이 1건뿐인 학습자는 학습 쪽."""
    by_user: Dict = {}
    for r in rows:
        by_user.setdefault(r.get("user_id"), []).append(r)
    train, test = [], []
    for rs in by_user.values():
        rs = sorted(rs, key=lambda r: (str(r.get("t") or ""), r.get("id") or 0))
        k = len(rs) if len(rs) < 2 else max(1, min(len(rs) - 1, int(len(rs) * train_frac)))
        train += rs[:k]
        test += rs[k:]
    return train, test


def compare(rows: Sequence[Dict], train_frac: float = 0.7, bins: int = 10, min_reviews: int = MIN_REVIEWS) -> Dict:
    """기록된 복습(rows)으로 FSRS·상수·SM-2 대리 예측을 비교한다.

    rows의 키: user_id, t(시각, 정렬용), passed(bool), p_fsrs·p_sm2(관측 척도, 찍기 반영한 예측), guess(0 또는 0.25).
    세 예측이 모두 있는 행만 쓴다. 상수 예측은 학습 쪽의 답 방식(찍기 확률)별 통과율이다(평가 쪽에는 맞추지 않는다).
    FSRS와 SM-2 대리는 기본 매개변수라 학습 쪽에서 맞추는 것이 없어, 평가 쪽 수치만 비교한다.
    criterion_met은 참고용이다(복습 min_reviews건 미만이면 None). 간격 교체는 사람이 결정한다."""
    usable = [r for r in rows if r.get("p_fsrs") is not None and r.get("p_sm2") is not None
              and r.get("passed") is not None]
    train, test = time_split(usable, train_frac)
    out = {"n_rows": len(rows), "n_usable": len(usable), "n_train": len(train), "n_test": len(test),
           "users": len({r.get("user_id") for r in usable}), "min_reviews": min_reviews,
           "enough": len(usable) >= min_reviews}
    if not test:
        out.update(log_loss=None, calibration=None, criterion_met=None)
        return out
    base: Dict = {}
    for r in train:
        g = float(r.get("guess") or 0.0)
        n, k = base.get(g, (0, 0))
        base[g] = (n + 1, k + (1 if r["passed"] else 0))
    all_n = sum(n for n, _ in base.values())
    all_rate = (sum(k for _, k in base.values()) / all_n) if all_n else 0.5

    def const(r):
        n, k = base.get(float(r.get("guess") or 0.0), (0, 0))
        return k / n if n else all_rate

    ys = [1 if r["passed"] else 0 for r in test]
    pf = [float(r["p_fsrs"]) for r in test]
    ps = [float(r["p_sm2"]) for r in test]
    pc = [const(r) for r in test]
    ll = {"fsrs": log_loss(pf, ys), "constant": log_loss(pc, ys), "sm2_proxy": log_loss(ps, ys)}
    out["log_loss"] = {k: round(v, 4) for k, v in ll.items()}
    out["pass_rate_test"] = round(sum(ys) / len(ys), 4)
    out["calibration"] = {"fsrs": calibration_table(pf, ys, bins), "sm2_proxy": calibration_table(ps, ys, bins)}
    gap = out["calibration"]["fsrs"]["gap_mean"]
    met = ll["fsrs"] < ll["constant"] and ll["fsrs"] < ll["sm2_proxy"] and gap is not None and gap <= CALIBRATION_GAP_MAX
    out["criterion_met"] = met if out["enough"] else None
    out["note"] = ("참고 판정이다. 교체는 복습 300건 이상에서 사람이 결정한다(docs/master-plan-2026-10.md C11)."
                   if out["enough"] else f"복습 {len(usable)}건으로 판단하지 않는다({min_reviews}건 이상 필요).")
    return out
