"""3단계(문장·문맥 추론) 숙달 판정 시뮬레이션(docs/mastery-ewma.md 5절).

    backend/.venv/bin/python scripts/mastery_sim_stage3.py --seed 1 [--only a,thr] [--out 결과.json]

3단계 기록은 문장 채점 합격(60점 이상, 관계없는 답은 거의 0점)과 문맥 추론 정답(3지선다, 우연 1/3)이 섞인 정오 열이다.
그래서 1·2단계 모형(우연 0.25)과 달리 우연 수준 g를 학습자마다 0~0.33에서 뽑는다. 실제 합격 확률
p(t) = g + (pmax − g)(1 − exp(−t/tau)), tau 3~40, pmax 0.35~0.98. 숙련 학습자 집단은 처음부터 p가 0.8~0.98로 일정하다.

R0(지금): 최소 5번, 누적 합격률 ≥ 65%.
R1(후보): 최소 5번, 편향 보정 지수 이동 평균(main._ewma_mastery와 같은 식) ≥ 문턱.
거짓 숙달: 판정 시점의 실제 p < 0.60(문턱 65보다 5점 아래). 지연: pmax ≥ 0.75인 학습자에서 p가 처음 0.65를 넘은 뒤 판정까지 시도 수.
"""
import argparse
import json
import math
import random
import statistics as st

N = 20000
T_MAX = 200
MIN_ATT = 5


def learners(rng):
    for _ in range(N):
        yield rng.uniform(0.0, 0.33), rng.uniform(3, 40), rng.uniform(0.35, 0.98)


def p_at(t, g, tau, pmax):
    return g + (pmax - g) * (1 - math.exp(-t / tau))


def r0(state, correct):
    a, c = state or (0, 0)
    a, c = a + 1, c + (1 if correct else 0)
    return (a, c), 100.0 * c / a


def r1(alpha):
    def f(state, correct):
        n, est = state or (0, 0.0)
        raw = est * (1 - (1 - alpha) ** n)
        raw += alpha * ((100.0 if correct else 0.0) - raw)
        est = min(100.0, max(0.0, raw / (1 - (1 - alpha) ** (n + 1))))
        return (n + 1, est), est
    return f


def run(rule, thr, seed):
    rng = random.Random(f"{seed}-learners")
    draw = random.Random(f"{seed}-answers")
    false_m = judged = 0
    delays = []
    for g, tau, pmax in learners(rng):
        state, first65 = None, None
        for t in range(1, T_MAX + 1):
            p = p_at(t, g, tau, pmax)
            if first65 is None and p >= 0.65:
                first65 = t
            state, score = rule(state, draw.random() < p)
            if t >= MIN_ATT and score >= thr:
                judged += 1
                false_m += p < 0.60
                if pmax >= 0.75 and first65 is not None:
                    delays.append(max(0, t - first65))
                break
        else:
            if pmax >= 0.75 and first65 is not None:
                delays.append(T_MAX - first65)
    skilled = []
    srng = random.Random(f"{seed}-skilled")
    for _ in range(N):
        p = srng.uniform(0.8, 0.98)
        state = None
        for t in range(1, T_MAX + 1):
            state, score = rule(state, srng.random() < p)
            if t >= MIN_ATT and score >= thr:
                skilled.append(t)
                break
        else:
            skilled.append(T_MAX)
    return {"false_rate": round(false_m / max(judged, 1), 4), "judged": judged,
            "delay_median": st.median(delays) if delays else None, "skilled_median": st.median(skilled)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--only", default=None, help="a,thr 한 조합만(확인용)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    out = {"seed": a.seed, "N": N, "min_attempts": MIN_ATT, "R0": run(r0, 65.0, a.seed), "R1": []}
    combos = ([tuple(float(x) for x in a.only.split(","))] if a.only else
              [(al, th) for al in (0.08, 0.10, 0.15, 0.20) for th in (65.0, 70.0, 75.0, 80.0)])
    for alpha, thr in combos:
        out["R1"].append({"alpha": alpha, "thr": thr, **run(r1(alpha), thr, a.seed)})
    txt = json.dumps(out, ensure_ascii=False, indent=1)
    print(txt)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(txt + "\n")


if __name__ == "__main__":
    main()
