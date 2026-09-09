#!/usr/bin/env python
"""
D-GOP 채점식의 구조적 결함 재현 — 축 B 진단.

`dgop.dgop_phone`의 점수는 `naive × confidence`다. 설계 의도는 "표준 GOP(naive)가 뭉갠
발화에서 과신하므로 불확실성으로 보정한다"였다. 이 스크립트는 그 의도가 **식의 형태 때문에
달성되지 않음**을 데이터·GPU 없이 결정론적으로 보인다.

두 가지를 잰다.

1. **중복성** — 목표 음소가 argmax인 구간(정렬 성공 조건)에서 `naive`와 `confidence`의
   순위상관. 둘 다 "분포가 얼마나 뾰족한가"의 단조 함수라 상관이 1에 가깝다. 그러면 곱셈은
   순위 정보를 더하지 못하고 추정 잡음만 더하므로, `-ρ(severity, score)`가 구조적으로
   naive 이하가 된다. A-3/A-5 실측(축 A 1.000→0.998, 베이스라인 0.914→0.813)이 그 예측이다.

2. **방향 오류** — 세 시나리오에서 보정이 실제로 무엇을 벌하는지. 과신이란 '분포가 뾰족한데
   틀린 것'인데, `confidence`가 재는 것이 바로 그 뾰족함이라 과신 구간을 그대로 통과시킨다.
   실제로 걷히는 것은 **과소확신**(평평한 분포)이다 — 설계 의도와 반대다.

문헌 대조: Yeo, Choi, Kim, Chung, "Speech Intelligibility Assessment of Dysarthric Speech
by using Goodness of Pronunciation with Uncertainty Quantification", Interspeech 2023
(arXiv:2305.18392). 구음장애 발화(한국어 포함 3개 언어)에서 엔트로피·마진 기반 GOP는
베이스라인보다 **나빴고**(한국어 τ −0.264 / −0.443 vs 베이스라인 −0.524), softmax를
탈출하는 MaxLogit만 이겼다(−0.544, 상대 개선 3.91%). 우리가 곱한 두 신호가 그 표에서
가장 성능이 낮은 둘이다.

실행: python scripts/analyze_dgop_redundancy.py
"""
import argparse
import os
import random
import statistics
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "backend"))

import dgop as D  # noqa: E402

REDUNDANCY_THRESHOLD = 0.90
"""이 이상이면 confidence는 naive의 재표현이고 곱셈이 순위 정보를 더할 수 없다."""


def spearman(x, y):
    """동점 보정 포함 순위상관. scipy 의존을 만들지 않는다(이 저장소 관례)."""
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = rank(x), rank(y)
    n = len(x)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx) ** 0.5
    dy = sum((b - my) ** 2 for b in ry) ** 0.5
    return num / (dx * dy) if dx and dy else 0.0


def sample_distributions(n: int, classes: int, seed: int = 0):
    """
    목표 음소가 argmax인 분포를 첨도를 넓게 스윕하며 생성한다.
    argmax 조건을 거는 이유: 강제정렬이 성공한 구간이 채점 대상이기 때문이다.
    """
    rng = random.Random(seed)
    naive, conf, dgop = [], [], []
    for _ in range(n):
        alpha = 10 ** rng.uniform(-2.5, 1.0)          # 평평 ~ 뾰족
        p = [rng.gammavariate(alpha, 1.0) + 1e-12 for _ in range(classes)]
        s = sum(p)
        p = [v / s for v in p]
        t = max(range(classes), key=lambda i: p[i])   # 목표 = argmax
        naive.append(p[t])
        conf.append(D.phone_confidence(p))
        dgop.append(D.dgop_phone(p[t], p)["dgop"])
    return naive, conf, dgop


def _peaked(classes: int, peak_idx: int, mass: float):
    rest = (1.0 - mass) / (classes - 1)
    p = [rest] * classes
    p[peak_idx] = mass
    return p


def report_direction(classes: int):
    """보정이 실제로 무엇을 벌하는가 — 세 시나리오 대조."""
    rows = []
    p = _peaked(classes, 0, 0.95)
    rows.append(("A 목표에 포화 (= 과신)", D.dgop_phone(p[0], p)))
    p = _peaked(classes, 1, 0.95)
    rows.append(("B 다른 음소에 확신 (체계적 치환)", D.dgop_phone(p[0], p)))
    p = [1.0 / classes] * classes
    p[0] = 1.2 / classes
    s = sum(p)
    p = [v / s for v in p]
    rows.append(("C 평평, 목표가 간신히 1등 (과소확신)", D.dgop_phone(p[0], p)))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=int, default=20000)
    ap.add_argument("--classes", type=int, default=49, help="자모 vocab 크기")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    naive, conf, dgop = sample_distributions(args.samples, args.classes, args.seed)
    rho_conf = spearman(naive, conf)
    rho_dgop = spearman(naive, dgop)

    print(f"목표=argmax 분포 {args.samples:,}개 (vocab {args.classes}클래스, seed {args.seed})\n")
    print("1) 중복성 — confidence는 naive와 독립된 신호인가")
    print(f"   ρ(naive, confidence) = {rho_conf:.3f}   (기준 {REDUNDANCY_THRESHOLD})")
    print(f"   ρ(naive, dgop)       = {rho_dgop:.3f}")
    hi = [(n, c) for n, c in zip(naive, conf) if n >= 0.8]
    if hi:
        print(f"   naive≥0.8 구간(n={len(hi)}): ρ = "
              f"{spearman([a for a, _ in hi], [b for _, b in hi]):.3f}, "
              f"confidence 중앙값 {statistics.median([b for _, b in hi]):.3f}")
    verdict = "중복 — 곱셈이 순위 정보를 더하지 못한다" if rho_conf >= REDUNDANCY_THRESHOLD \
        else "독립 — 곱셈에 정보 이득이 있을 수 있다"
    print(f"   → {verdict}\n")

    print("2) 방향 — 보정이 실제로 무엇을 벌하는가")
    print("   시나리오                                naive   conf   D-GOP")
    print("   --------------------------------------+-------+------+-------")
    for label, r in report_direction(args.classes):
        print(f"   {label:<38}{r['naive']:.3f}  {r['confidence']:.3f}  {r['dgop']:.3f}")
    print("\n   과신(A)은 confidence가 높아 통과되고, 실제로 걷히는 것은 과소확신(C)이다.")
    print("   설계 의도('과신을 막는다')와 반대 방향이다.\n")

    print("문헌 대조: Yeo et al., Interspeech 2023 (arXiv:2305.18392) —")
    print("  구음장애 발화 한국어 Kendall τ: 베이스라인 −0.524 / 엔트로피 −0.264 /")
    print("  마진 −0.443 / Prior+MaxLogit −0.544. 엔트로피·마진은 베이스라인보다 나쁘다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
