"""3단계(문장) 4지선다 정답을 숙달에 얼마로 넣을지 시뮬레이션(docs/mastery-ewma.md 10절).

    backend/.venv/bin/python scripts/mastery_sim_choice_stage3.py --seed 0 [--only C:0.75] [--out 결과.json]

학습자는 5·9절 3단계 모형을 두 답 방식으로 나눈 것이다. 주관식·서술형 합격 확률 q(t) = q0 + (qmax − q0)(1 − e^(−t/tau)),
q0 0~0.05, tau 3~40, qmax 0.35~0.98, 2만 명, 최대 200번. 4지선다 정답 확률은 k + (1 − k)/4, k = q + b(1 − q)(보기 넷 가운데서는
알아보는 몫 b, 가정 L 0~0.2·H 0.2~0.5). 문항 유형은 앱 규칙(lib/openSet.sentenceQuestionTypes, 레슨 5문장)을 따른다: 레슨을 열 때
저장된 추정값이 50 미만(기록 없음 포함)이면 4지선다 2개, 50~70이면 1개, 70 이상이면 0개, 자리는 무작위.
숙달은 편향 보정 이동 평균(a 0.08) 80 이상, 최소 5번. 저장값은 앱(main._ewma_mastery)처럼 매번 0~100으로 자른다.

R: 4지선다 정답 1. C(c): 4지선다 정답 c. CC: 4지선다 정답 1, 오답 −1/3(우연 보정). 주관식·서술형은 합격 1, 불합격 0.
numpy로 학습자 전체를 한꺼번에 계산하고, 규칙끼리 같은 난수(정답, 유형 자리)를 쓴다.
"""
import argparse
import json

import numpy as np

T_MAX = 200
N = 20000
ALPHA = 0.08
THR = 80.0
MIN_ATT = 5
LESSON = 5
FALSE_Q = 0.60
B_RANGES = {"L": (0.0, 0.2), "H": (0.2, 0.5)}


def n_choice(est, has_record):
    """레슨 5문장 가운데 4지선다 수(lib/openSet.sentenceQuestionTypes와 같다)."""
    two = np.full(est.shape, 2)            # 50 미만: test·multiple·essay를 돌려 5개 중 2개
    one = np.full(est.shape, int(np.ceil(LESSON / 6)))
    out = np.where(est >= 70, 0, np.where(est >= 50, one, two))
    return np.where(has_record, out, 2)


def draw(seed, b_case):
    rng = np.random.default_rng(seed)
    q0 = rng.uniform(0.0, 0.05, N)
    tau = rng.uniform(3, 40, N)
    qmax = rng.uniform(0.35, 0.98, N)
    u_ans = rng.random((N, T_MAX))
    u_slot = rng.random((N, T_MAX // LESSON, LESSON))
    q_sk = rng.uniform(0.8, 0.98, N)
    u_ans_sk = rng.random((N, T_MAX))
    u_slot_sk = rng.random((N, T_MAX // LESSON, LESSON))
    # b는 가정마다 따로 뽑되 학습자·정답 난수는 두 가정이 같다
    brng = np.random.default_rng([seed, 1 if b_case == "L" else 2])
    lo, hi = B_RANGES[b_case]
    b = brng.uniform(lo, hi, N)
    b_sk = brng.uniform(lo, hi, N)
    t = np.arange(1, T_MAX + 1)
    q = q0[:, None] + (qmax[:, None] - q0[:, None]) * (1 - np.exp(-t[None, :] / tau[:, None]))
    main = {"q": q, "qmax": qmax, "b": b, "u_ans": u_ans, "slot_rank": u_slot.argsort(axis=2).argsort(axis=2)}
    skilled = {"q": np.repeat(q_sk[:, None], T_MAX, axis=1), "qmax": q_sk, "b": b_sk, "u_ans": u_ans_sk,
               "slot_rank": u_slot_sk.argsort(axis=2).argsort(axis=2)}
    return main, skilled


def simulate(d, rule):
    """rule = ('credit', c) 또는 ('cc', None). 숙달 판정 시점(t, 1부터; 없으면 0)과 4지선다 답 수."""
    kind, c = rule
    q, b, u_ans, rank = d["q"], d["b"], d["u_ans"], d["slot_rank"]
    est = np.zeros(N)
    mastered_at = np.zeros(N, dtype=int)
    nchoice = np.zeros(N, dtype=int)
    k_lesson = np.zeros(N, dtype=int)
    for i in range(T_MAX):
        n = i
        if i % LESSON == 0:
            k_lesson = n_choice(est, np.full(N, n > 0))
        choice = rank[:, i // LESSON, i % LESSON] < k_lesson
        know = q[:, i] + b * (1 - q[:, i])
        pc = np.where(choice, know + (1 - know) / 4, q[:, i])
        ok = u_ans[:, i] < pc
        if kind == "cc":
            val = np.where(choice, np.where(ok, 1.0, -1.0 / 3), np.where(ok, 1.0, 0.0))
        else:
            val = np.where(ok, np.where(choice, c, 1.0), 0.0)
        raw = est * (1 - (1 - ALPHA) ** n)
        raw = raw + ALPHA * (100.0 * val - raw)
        est = np.clip(raw / (1 - (1 - ALPHA) ** (n + 1)), 0, 100)
        nchoice += choice
        hit = (mastered_at == 0) & (i + 1 >= MIN_ATT) & (est >= THR)
        mastered_at[hit] = i + 1
    return mastered_at, nchoice


def metrics(d, mastered_at, nchoice):
    q, qmax = d["q"], d["qmax"]
    judged = mastered_at > 0
    idx = np.where(judged)[0]
    q_at = q[idx, mastered_at[idx] - 1]
    over = q >= 0.65
    first = np.where(over.any(axis=1), over.argmax(axis=1) + 1, 0)
    strong = qmax >= 0.75
    k = np.where(strong & (first > 0))[0]
    ma, f = mastered_at[k], first[k]
    delay = np.where(ma > 0, np.maximum(0, ma - f), T_MAX - f)   # 5절과 같이 문턱 전 판정은 0
    return {
        "false_rate": round(float(np.mean(q_at < FALSE_Q)) if len(idx) else 0.0, 4),
        "judged": int(judged.sum()),
        "delay_median": float(np.median(delay)) if len(delay) else None,
        "strong_mastered_share": round(float(np.mean(mastered_at[strong] > 0)), 4),
        "choice_answers_mean": round(float(np.mean(nchoice)), 2),
    }


def skilled_median(d, mastered_at):
    return float(np.median(np.where(mastered_at > 0, mastered_at, T_MAX)))


CANDIDATES = {
    "R": ("credit", 1.0), "C:0.5": ("credit", 0.5), "C:0.67": ("credit", 0.67), "C:0.75": ("credit", 0.75),
    "CC": ("cc", None),
}


def check(base, cand):
    return (cand["false_rate"] < base["false_rate"]
            and cand["delay_median"] - base["delay_median"] <= 3
            and cand["strong_mastered_share"] >= base["strong_mastered_share"] - 0.05)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--only", default=None, help="후보 하나만(확인용), 예: C:0.75")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    names = ["R"] + ([a.only] if a.only else [k for k in CANDIDATES if k != "R"])
    out = {"seed": a.seed, "N": N, "results": {}}
    for case in ("L", "H"):
        d, sk = draw(a.seed, case)
        rows = {}
        for name in names:
            ma, nc = simulate(d, CANDIDATES[name])
            rows[name] = metrics(d, ma, nc)
            rows[name]["skilled_median"] = skilled_median(sk, simulate(sk, CANDIDATES[name])[0])
        for name in names[1:]:
            rows[name]["pass"] = check(rows["R"], rows[name])
        out["results"][case] = rows
    passing = [n for n in names[1:] if all(out["results"][k][n]["pass"] for k in out["results"])]
    mean_false = {n: float(np.mean([out["results"][k][n]["false_rate"] for k in out["results"]])) for n in passing}
    out["passing"] = passing
    out["chosen"] = min(passing, key=lambda n: mean_false[n]) if passing else None
    print(json.dumps(out, ensure_ascii=False, indent=1))
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
            f.write("\n")


if __name__ == "__main__":
    main()
