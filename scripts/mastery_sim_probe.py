"""말하기 모음·자음(2·3단계) 낱말 속 소리 확인이 숙달까지 시도 수를 얼마나 늘리는지(docs/mastery-ewma.md 8절, 커리큘럼 계획 2-5).

    backend/.venv/bin/python scripts/mastery_sim_probe.py --seed 0 [--n 5 --need 4] [--q-scale 0.82] [--out 결과.json]

학습자와 정답 확률은 scripts/mastery_sim_speak.py와 같다(p(t) = g + (pmax − g)(1 − exp(−t/tau)), 2만 명, t는 음절 문항 시도 수).
지금 규칙: 최소 8번, 편향 보정 이동 평균(a 0.08) ≥ 85이면 숙달. 새 규칙: 그 조건을 처음 채운 뒤부터 확인 낱말 n개와 음절 문항 L개를
번갈아 낸다(화면이 확인 낱말을 지금 문항 뒤에 끼우고, 문항을 한 바퀴 돌면 다시 낸다). 이동 평균 조건을 채운 채로 최근 확인 n번 중
need번 이상 합격하면 숙달. 확인 낱말은 이동 평균에 넣지 않는다.
확인 낱말 합격 확률 q(t) = 0.82 × p(t): 소리를 제대로 낼 확률 p에, 맞게 말한 청각장애 발화가 단어 규칙(65점)을 넘는 비율 0.82
(docs/speak-transcript-scoring.md 'D-GOP 결과')를 곱한 보수적 값이다. 같은 학습자·같은 음절 답 난수로 두 규칙을 비교한다.
리뷰 뒤(docs/mastery-ewma.md 8.6) 확인 합격에 첫 음절 목표 소리 확인을 더해, 소리 확인을 맞게 낸 소리의 0.9로 넘는다고 보고
--q-scale 0.738(= 0.82 × 0.9)로도 돌린다.
"""
import argparse
import json
import os
import sys
import zlib

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mastery_sim_speak import ALPHA, T_MAX  # noqa: E402

MIN_ATT, THR = 8, 85.0
T_REF = 0.65   # 6절과 같은 기준 합격률(예전 누적 문턱 65): 거짓 숙달은 판정 때 p < T_REF − 0.05, 지연 모집단은 pmax ≥ T_REF + 0.10
Q_SCALE = 0.82


def simulate(p_row, correct_row, probe_u, n, need, L, q_scale=Q_SCALE):
    """한 학습자. (지금 규칙 숙달까지 시도 수, 새 규칙 숙달까지 시도 수(확인 포함), 새 규칙 판정 시점의 음절 시도 번호) — 못 하면 None."""
    raw, est = 0.0, 0.0
    old = new = new_t = None
    window, k_probe = [], 0
    carry, phase_left, probes_done = False, 0, 0   # carry: 확인 시작 뒤, phase_left: 이번 묶음에서 남은 확인 수
    total = 0
    t = 0
    while t < T_MAX:
        if carry and phase_left > 0:
            q = q_scale * p_row[max(t - 1, 0)]
            ok = probe_u[k_probe] < q
            k_probe += 1
            window = (window + [ok])[-n:]
            total += 1
            phase_left -= 1
            if est >= THR and t >= MIN_ATT and sum(window) >= need:
                new, new_t = total, t
                break
            if phase_left == 0:
                probes_done = L   # 음절 문항 한 바퀴 뒤 다시 확인
            continue
        c = correct_row[t]
        raw = raw + ALPHA * (100.0 * c - raw)
        est = min(100.0, raw / (1 - (1 - ALPHA) ** (t + 1)))
        t += 1
        total += 1
        gate = t >= MIN_ATT and est >= THR
        if gate and old is None:
            old = t
        if gate and sum(window) >= need:
            new, new_t = total, t
            break
        if gate and not carry:
            carry, phase_left = True, n
        elif carry:
            probes_done -= 1
            if probes_done <= 0:
                phase_left = n
    return old, new, new_t


def run(seed, n_probe, need, L=8, n=20000, q_scale=Q_SCALE):
    rng = np.random.default_rng([seed, zlib.crc32(b"speak_probe")])
    g = rng.uniform(0.0, 0.2, n)
    tau = rng.uniform(3, 40, n)
    pmax = rng.uniform(0.35, 0.98, n)
    t = np.arange(1, T_MAX + 1)
    p = g[:, None] + (pmax - g)[:, None] * (1 - np.exp(-t[None, :] / tau[:, None]))
    correct = rng.random((n, T_MAX)) < p
    probe_u = rng.random((n, 4 * T_MAX))
    sp = rng.uniform(T_REF + 0.10, 0.98, n)
    skilled = rng.random((n, T_MAX)) < sp[:, None]
    skilled_p = np.repeat(sp[:, None], T_MAX, axis=1)
    rows = [simulate(p[i], correct[i], probe_u[i], n_probe, need, L, q_scale) for i in range(n)]
    sk = [simulate(skilled_p[i], skilled[i], probe_u[i], n_probe, need, L, q_scale) for i in range(n)]

    def summary(rs, prow, mask=None):
        idx = [i for i, r in enumerate(rs) if r[0] is not None and (mask is None or mask[i])]
        old = np.array([rs[i][0] for i in idx], float)
        new = np.array([rs[i][1] if rs[i][1] is not None else 2 * T_MAX for i in idx], float)
        never = sum(1 for i in idx if rs[i][1] is None)
        return {"learners": len(idx), "old_median": float(np.median(old)), "new_median": float(np.median(new)),
                "median_increase_pct": round(100 * (np.median(new) - np.median(old)) / np.median(old), 1),
                "added_median": float(np.median(new - old)), "not_mastered_new": never}

    Tp = T_REF
    typical = pmax >= Tp + 0.10          # 6절 지연 지표의 모집단(끝내 기준 합격률을 넉넉히 넘는 학습자)

    def false_rate(which):
        judged = [(i, r) for i, r in enumerate(rows) if r[which] is not None]
        bad = 0
        for i, r in judged:
            tt = r[0] if which == 0 else r[2]
            bad += p[i, tt - 1] < Tp - 0.05
        return round(bad / max(len(judged), 1), 4)

    return {"seed": seed, "n": n, "probe_n": n_probe, "need": need, "L": L, "q_scale": q_scale,
            "all_mastering": summary(rows, p), "typical": summary(rows, p, typical), "skilled": summary(sk, skilled_p),
            "false_mastery": {"old": false_rate(0), "new": false_rate(1)}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--n", type=int, default=5, dest="probe_n")
    ap.add_argument("--need", type=int, default=4)
    ap.add_argument("--L", type=int, default=8)
    ap.add_argument("--learners", type=int, default=20000)
    ap.add_argument("--q-scale", type=float, default=Q_SCALE, dest="q_scale")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    r = run(a.seed, a.probe_n, a.need, a.L, a.learners, a.q_scale)
    print(json.dumps(r, ensure_ascii=False, indent=1))
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(json.dumps(r, ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    main()
