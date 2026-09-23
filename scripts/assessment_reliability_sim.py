"""표준검사(축 I) 신뢰도 소규모 실증 — 합성 응답 시뮬레이션.

파일럿 응답이 아직 없으므로, 동결한 동형 폼(backend/data/assessment/forms_v1.json)의 문항 난이도로
가상의 응답자 집단을 만들어 KR-20(내적 일관성)과 A·B 동형 폼 상관을 추정한다. 폼 길이를 정하는
근거(스피어만-브라운)와 파일럿 표본 설계의 출발점으로 쓴다. 실제 응답이 쌓이면 같은 계산을
PlacementResult.item_log로 다시 한다(docs/assessment-design.md).

응답 모형: 4지선다 3모수 문항반응(추측 c=0.25, 변별 a=1.2).
  P(정답) = c + (1-c) / (1 + exp(-a(θ - b))),  θ ~ N(0, 1),  b = (지수난이도 − 0.5) × 4
지수 난이도(0~1)를 로짓 척도로 옮기는 배율 4는 가정이다(파일럿 뒤 실측 문항모수로 교체).

사용: python scripts/assessment_reliability_sim.py [--n 300] [--reps 200] [--out docs/assessment-sim.json]
"""
import argparse
import json
import os

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_FORMS = os.path.join(os.path.dirname(_HERE), "backend", "data", "assessment", "forms_v1.json")
A_DISC, GUESS, SCALE = 1.2, 0.25, 4.0


def simulate(b: np.ndarray, theta: np.ndarray, rng) -> np.ndarray:
    p = GUESS + (1 - GUESS) / (1 + np.exp(-A_DISC * (theta[:, None] - b[None, :])))
    return (rng.random(p.shape) < p).astype(float)


def kr20(x: np.ndarray) -> float:
    k = x.shape[1]
    p = x.mean(0)
    var_total = x.sum(1).var(ddof=1)
    if var_total <= 0 or k < 2:
        return float("nan")
    return float(k / (k - 1) * (1 - (p * (1 - p)).sum() / var_total))


def spearman_brown(r: float, factor: float) -> float:
    return factor * r / (1 + (factor - 1) * r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300, help="가상 응답자 수")
    ap.add_argument("--reps", type=int, default=200, help="반복 횟수")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    forms = json.load(open(_FORMS, encoding="utf-8"))
    bA = (np.array([i["difficulty"] for i in forms["A"]]) - 0.5) * SCALE
    bB = (np.array([i["difficulty"] for i in forms["B"]]) - 0.5) * SCALE
    rng = np.random.default_rng(a.seed)
    k20a, k20b, k20ab, rab = [], [], [], []
    for _ in range(a.reps):
        theta = rng.standard_normal(a.n)
        xa, xb = simulate(bA, theta, rng), simulate(bB, theta, rng)
        k20a.append(kr20(xa)); k20b.append(kr20(xb)); k20ab.append(kr20(np.hstack([xa, xb])))
        rab.append(float(np.corrcoef(xa.sum(1), xb.sum(1))[0, 1]))

    def summ(v):
        v = np.array(v)
        return {"mean": round(float(v.mean()), 3), "ci95": [round(float(np.percentile(v, 2.5)), 3),
                                                             round(float(np.percentile(v, 97.5)), 3)]}
    L = len(bA)
    r_form = float(np.mean(k20a))
    out = {
        "forms_version": forms.get("version"), "items_per_form": L, "n_examinees": a.n, "reps": a.reps,
        "model": {"discrimination": A_DISC, "guessing": GUESS, "difficulty_scale": SCALE},
        "kr20_A": summ(k20a), "kr20_B": summ(k20b), "kr20_A_plus_B": summ(k20ab),
        "parallel_form_r_A_B": summ(rab),
        # 폼 한 개의 KR-20에서 문항 수를 바꿨을 때의 예측(스피어만-브라운)
        "spearman_brown_by_length": {str(k): round(spearman_brown(r_form, k / L), 3) for k in (8, 16, 24, 32, 40)},
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
