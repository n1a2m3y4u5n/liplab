"""학습 효과 리포트 지표 시뮬레이션(docs/eval-metrics.md).

    backend/.venv/bin/python scripts/eval_metrics_sim.py --seed 1 [--out 결과.json]

가상 학습자가 입모양 인지 → 단어 → 문맥 추론 순으로 푼다(뒤 단계에서는 앞 유형 복습이 섞인다). 유형마다 기초 정답률이
다르고, 같은 유형을 풀수록 정답률이 오른다(향상 폭 gain, 시상수 TAU). 예전 '초기 대비 최근'(전체 3등분)과
새 방식(유형별 3등분 가중 평균)을 참값과 비교한다. 순수 파이썬, 시드 고정.

참값 두 가지
  T_fixed   고정된 문항 구성(세 유형 같은 비율)으로 '처음 1/3 가운데 시점'과 '마지막 1/3 가운데 시점'에 검사했다면
            나왔을 기대 정답률의 차이. 아직 풀지 않은 유형은 기초 정답률 그대로다. 통제된 사전·사후 검사가 재는 값.
  T_within  새 방식이 겨냥하는 값(유형별 처음 1/3 대 마지막 1/3의 기대 정답률 차이, 같은 가중). 표집 잡음 확인용.
"""
import argparse
import json
import math
import os
import random
import statistics as st
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))
from eval_metrics import MIN_PER_TYPE, pooled_change, type_adjusted_curve, within_type_change  # noqa: E402

N = 4000
TAU = 10.0
TYPES = ("viseme", "word", "closure")
BASE = {"viseme": (0.80, 0.05), "word": (0.60, 0.07), "closure": (0.55, 0.07)}   # 기초 정답률(평균, 학습자 간 SD)
REVIEW_SHARE = 0.2
SCENARIOS = {"null": (0.0, 0.0), "learn": (0.15, 0.15), "mixed": (-0.05, 0.25)}   # gain ~ U(lo, hi)


def path(rng):
    n1, n2, n3 = rng.randint(12, 30), rng.randint(15, 45), rng.randint(10, 30)
    seq = ["viseme"] * n1
    seq += ["viseme" if rng.random() < REVIEW_SHARE else "word" for _ in range(n2)]
    seq += [rng.choice(["viseme", "word"]) if rng.random() < REVIEW_SHARE else "closure" for _ in range(n3)]
    return seq


def p_of(base, gain, j):
    """j번째(1부터) 같은 유형 시행의 정답 확률. j=0이면 아직 안 푼 상태."""
    return min(0.99, max(0.01, base + gain * (1 - math.exp(-j / TAU))))


def one(rng, lo, hi):
    base = {t: min(0.95, max(0.3, rng.gauss(m, s))) for t, (m, s) in BASE.items()}
    gain = rng.uniform(lo, hi)
    seq = path(rng)
    seen = {t: 0 for t in TYPES}
    trials, probs, opp_at = [], [], []
    for t in seq:
        seen[t] += 1
        p = p_of(base[t], gain, seen[t])
        trials.append((t, rng.random() < p))
        probs.append((t, p))
        opp_at.append(dict(seen))
    n = len(seq)
    k = n // 3
    early, late = opp_at[k // 2], opp_at[n - 1 - k // 2]
    t_fixed = st.mean(p_of(base[t], gain, late[t]) - p_of(base[t], gain, early[t]) for t in TYPES)
    by = {}
    for t, p in probs:
        by.setdefault(t, []).append(p)
    parts = [(len(v) // 3, st.mean(v[-(len(v) // 3):]) - st.mean(v[:len(v) // 3])) for v in by.values() if len(v) >= MIN_PER_TYPE]
    t_within = sum(kk * d for kk, d in parts) / sum(kk for kk, _ in parts) if parts else None
    return trials, t_fixed, t_within


def run(seed):
    out = {}
    for name, (lo, hi) in SCENARIOS.items():
        rng = random.Random(f"{seed}-{name}")
        old_err, new_err, new_w_err, olds, news, tf = [], [], [], [], [], []
        wrong_old = wrong_new = eligible = 0
        curve_raw, curve_adj = [[] for _ in range(8)], [[] for _ in range(8)]
        for _ in range(N):
            trials, t_fixed, t_within = one(rng, lo, hi)
            o, w = pooled_change(trials), within_type_change(trials)
            if o is None or w is None:
                continue
            od, nd = o["delta"] * 100, w["delta_pp"]
            olds.append(od); news.append(nd); tf.append(t_fixed * 100)
            old_err.append(od - t_fixed * 100); new_err.append(nd - t_fixed * 100)
            if t_within is not None:
                new_w_err.append(nd - t_within * 100)
            if abs(t_fixed * 100) >= 5:
                eligible += 1
                wrong_old += (od * t_fixed < 0)
                wrong_new += (nd * t_fixed < 0)
            for b in type_adjusted_curve(trials):
                curve_raw[b["bin"] - 1].append(b["raw"]); curve_adj[b["bin"] - 1].append(b["value"])
        rmse = lambda e: math.sqrt(st.mean(x * x for x in e))   # noqa: E731
        mc_raw = [st.mean(c) for c in curve_raw]
        mc_adj = [st.mean(c) for c in curve_adj]
        out[name] = {
            "n": len(olds), "T_fixed_mean": round(st.mean(tf), 2),
            "old_mean": round(st.mean(olds), 2), "new_mean": round(st.mean(news), 2),
            "old_bias": round(st.mean(old_err), 2), "new_bias": round(st.mean(new_err), 2),
            "old_rmse": round(rmse(old_err), 2), "new_rmse": round(rmse(new_err), 2),
            "new_bias_vs_T_within": round(st.mean(new_w_err), 2) if new_w_err else None,
            "direction_wrong_old": round(wrong_old / eligible, 4) if eligible else None,
            "direction_wrong_new": round(wrong_new / eligible, 4) if eligible else None,
            "curve_raw": [round(x, 3) for x in mc_raw], "curve_adj": [round(x, 3) for x in mc_adj],
            "curve_raw_range_pp": round((max(mc_raw) - min(mc_raw)) * 100, 2),
            "curve_adj_range_pp": round((max(mc_adj) - min(mc_adj)) * 100, 2),
        }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    res = {"seed": a.seed, "N": N, "base": BASE, "tau": TAU, "review_share": REVIEW_SHARE, "scenarios": run(a.seed)}
    txt = json.dumps(res, ensure_ascii=False, indent=1)
    print(txt)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(txt + "\n")


if __name__ == "__main__":
    main()
