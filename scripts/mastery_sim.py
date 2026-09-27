"""단계 숙달 판정 규칙 시뮬레이션(docs/mastery-ewma.md 3절).

    backend/.venv/bin/python scripts/mastery_sim.py [--min 8] [--out 결과.json]

누적 정답률(R0)과 지수 이동 평균(R1: a, 문턱)을 가상 학습자로 비교한다. 순수 파이썬, 시드 고정.
"""
import argparse
import json
import math
import random
import statistics as st

G = 0.25          # 4지선다 우연
T_MAX = 200
N = 20000


def learners(seed=0):
    rng = random.Random(seed)
    for _ in range(N):
        yield rng.uniform(3, 40), rng.uniform(0.45, 0.98), rng.random()


def p_at(t, tau, pmax):
    return G + (pmax - G) * (1 - math.exp(-t / tau))


def run(rule, min_att, seed=0):
    """rule(state, correct) -> (state, score); 숙달 판정 시점 t와 그때 실제 p, 처음 p>=0.7이 된 시점을 모은다."""
    false_m = judged = 0
    delays = []
    rng = random.Random(seed + 1)
    for tau, pmax, _ in learners(seed):
        state = None
        first70 = None
        for t in range(1, T_MAX + 1):
            p = p_at(t, tau, pmax)
            if first70 is None and p >= 0.7:
                first70 = t
            correct = rng.random() < p
            state, score, thr = rule(state, correct)
            if t >= min_att and score >= thr:
                judged += 1
                if p < 0.65:
                    false_m += 1
                if pmax >= 0.8 and first70 is not None:
                    delays.append(t - first70)
                break
        else:
            if pmax >= 0.8 and first70 is not None:
                delays.append(T_MAX - first70)   # 끝까지 못 받음(검열)
    return {"false_rate": round(false_m / max(judged, 1), 4), "judged": judged,
            "delay_median": st.median(delays) if delays else None}


def r0(thr):
    def f(state, correct):
        a, c = state or (0, 0)
        a, c = a + 1, c + (1 if correct else 0)
        return (a, c), 100.0 * c / a, thr
    return f


def r1(alpha, thr):
    def f(state, correct):
        e = 0.0 if state is None else state
        e += alpha * ((100.0 if correct else 0.0) - e)
        return e, e, thr
    return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=int, default=8)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    base = run(r0(70.0), a.min)
    rows = []
    for alpha in (0.10, 0.15, 0.20, 0.25, 0.30):
        for thr in (65.0, 70.0, 75.0):
            rows.append({"alpha": alpha, "thr": thr, **run(r1(alpha, thr), a.min)})
    ok = [r for r in rows if r["false_rate"] <= base["false_rate"] and r["delay_median"] < base["delay_median"]]
    best = min(ok, key=lambda r: (r["delay_median"], r["false_rate"])) if ok else None
    out = {"min_attempts": a.min, "R0": base, "R1": rows, "chosen": best}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    if a.out:
        json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
