"""말하기 단계와 읽기 4단계(대화)의 숙달 판정 시뮬레이션(docs/mastery-ewma.md 6절).

    backend/.venv/bin/python scripts/mastery_sim_speak.py --seed 0 [--only 단계키:문턱] [--out 결과.json]

3단계 시뮬레이션(scripts/mastery_sim_stage3.py)과 같은 모형을 numpy로 한꺼번에 계산한다. 합격 확률
p(t) = g + (pmax − g)(1 − exp(−t/tau)), g 0~0.2(말하기·대화 채점은 찍어서 붙기 어렵다), tau 3~40, pmax 0.35~0.98.
숙련 학습자는 p가 처음부터 (문턱 + 0.10)~0.98로 일정하다. 같은 학습자·같은 답 난수로 두 규칙을 비교한다.

R0(지금): 최소 시도 수, 누적 합격률 ≥ 문턱 T. R1(후보): 최소 시도 수, 편향 보정 이동 평균(main._ewma_mastery와 같은 식, a 0.08) ≥ 문턱.
거짓 숙달: 판정 시점의 실제 p < T − 0.05. 지연: pmax ≥ T + 0.10인 학습자에서 p가 처음 T를 넘은 뒤 판정까지 시도 수(끝까지 못 하면 200 − 그때).
"""
import argparse
import json
import zlib

import numpy as np

T_MAX = 200
ALPHA = 0.08
# (키, 최소 시도, 지금 누적 문턱 %) — speak_curriculum.SPEAK_STAGES와 main._STAGE4_*
STAGES = [("speak0_voicing", 5, 70), ("speak1_prosody", 10, 70), ("speak2_vowel", 8, 65), ("speak3_consonant", 8, 65),
          ("speak4_word", 8, 70), ("speak5_sentence", 6, 70), ("read4_conversation", 4, 60)]


def scores_cum(correct):
    t = np.arange(1, correct.shape[1] + 1)
    return 100.0 * np.cumsum(correct, axis=1) / t


def scores_ewma(correct, alpha=ALPHA):
    n, T = correct.shape
    raw = np.zeros(n)
    out = np.empty((n, T))
    for t in range(T):
        raw = raw + alpha * (100.0 * correct[:, t] - raw)
        out[:, t] = np.clip(raw / (1 - (1 - alpha) ** (t + 1)), 0, 100)
    return out


def judge(scores, min_att, thr):
    ok = scores >= thr
    ok[:, : min_att - 1] = False
    first = np.where(ok.any(axis=1), ok.argmax(axis=1), -1)   # 0부터(시도 수 = +1), 못 하면 -1
    return first


def run_stage(seed, key, min_att, T, thrs, n=20000):
    rng = np.random.default_rng([seed, zlib.crc32(key.encode())])
    g = rng.uniform(0.0, 0.2, n)
    tau = rng.uniform(3, 40, n)
    pmax = rng.uniform(0.35, 0.98, n)
    t = np.arange(1, T_MAX + 1)
    p = g[:, None] + (pmax - g)[:, None] * (1 - np.exp(-t[None, :] / tau[:, None]))
    correct = rng.random((n, T_MAX)) < p
    Tp = T / 100.0
    first_T = np.where((p >= Tp).any(axis=1), (p >= Tp).argmax(axis=1), -1)
    delay_mask = (pmax >= Tp + 0.10) & (first_T >= 0)
    sp = rng.uniform(Tp + 0.10, 0.98, n)
    skilled = rng.random((n, T_MAX)) < sp[:, None]

    def evaluate(score_fn, thr):
        j = judge(score_fn(correct), min_att, thr)
        judged = j >= 0
        p_at = p[np.arange(n), np.where(judged, j, 0)]
        false_rate = float(((p_at < Tp - 0.05) & judged).sum() / max(judged.sum(), 1))
        d = np.where(judged, j - first_T, T_MAX - 1 - first_T)
        delay = float(np.median(np.maximum(0, d[delay_mask]))) if delay_mask.any() else None
        js = judge(score_fn(skilled), min_att, thr)
        sk = float(np.median(np.where(js >= 0, js + 1, T_MAX)))
        return {"false_rate": round(false_rate, 4), "judged": int(judged.sum()), "delay_median": delay, "skilled_median": sk}

    out = {"stage": key, "min_attempts": min_att, "T": T, "R0": evaluate(scores_cum, T), "R1": []}
    for thr in thrs:
        out["R1"].append({"alpha": ALPHA, "thr": thr, **evaluate(scores_ewma, thr)})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--only", default=None, help="키:문턱,키:문턱 … 확인용")
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    only = dict(x.split(":") for x in a.only.split(",")) if a.only else None
    res = {"seed": a.seed, "n": a.n, "alpha": ALPHA, "stages": []}
    for key, m, T in STAGES:
        if only is not None and key not in only:
            continue
        thrs = [float(only[key])] if only else [T, T + 5, T + 10, T + 15, T + 20]
        thrs = [x for x in thrs if x <= 95]
        r = run_stage(a.seed, key, m, T, thrs, a.n)
        res["stages"].append(r)
        print(key, "R0", r["R0"])
        for x in r["R1"]:
            print("   R1", x)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(json.dumps(res, ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    main()
