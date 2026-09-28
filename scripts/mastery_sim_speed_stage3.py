"""3단계(문장) 재생 속도를 숙달에 어떻게 넣을지 시뮬레이션(docs/mastery-ewma.md 9절, 7절 후속).

    backend/.venv/bin/python scripts/mastery_sim_speed_stage3.py --seed 0 [--only C3] [--out 결과.json]

구조는 scripts/mastery_sim_speed.py(1·2단계)와 같고 학습자는 5절 3단계 모형이다(g 0~0.33, tau 3~40, pmax 0.35~0.98, 최대 200번,
편향 보정 이동 평균 a 0.08 ≥ 80, 최소 5번). 감속은 두 갈래다.
- 적응 감속(모두): 학습자마다 θ를 0.60~0.90에서 뽑고 p < θ인 동안 모든 시도가 적응 감속된다. 합격 확률 +0.03.
- 학습자 선택 감속(절반): A(시도마다 확률 s, s 0.1~0.6) 또는 B(확률 s(1 − p)/(1 − g), s 0.2~1.0). 합격 확률 +GAIN(0.10 또는 0.20).
numpy로 학습자 전체를 한꺼번에 계산하고, 규칙끼리 같은 난수를 쓴다.

R: 속도와 상관없이 합격 1. C1: 유효 속도 1.0배 미만 합격은 0.5. C2(g): C1 + 추정값 g 이상이면 적응 감속을 끔.
C3: 학습자가 고른 감속의 합격만 0.5. C4(g): C3 + 추정값 g 이상이면 적응 감속을 끔.
"""
import argparse
import json

import numpy as np

T_MAX = 200
N = 20000
ALPHA = 0.08
THR = 80.0
MIN_ATT = 5
ADAPT_GAIN = 0.03
FALSE_P = 0.60


def draw(seed):
    rng = np.random.default_rng(seed)
    g = rng.uniform(0.0, 0.33, N)
    tau = rng.uniform(3, 40, N)
    pmax = rng.uniform(0.35, 0.98, N)
    theta = rng.uniform(0.60, 0.90, N)
    slower = rng.random(N) < 0.5
    s_a = np.where(slower, rng.uniform(0.1, 0.6, N), 0.0)
    s_b = np.where(slower, rng.uniform(0.2, 1.0, N), 0.0)
    u_ans = rng.random((N, T_MAX))
    u_slow = rng.random((N, T_MAX))
    t = np.arange(1, T_MAX + 1)
    p = g[:, None] + (pmax[:, None] - g[:, None]) * (1 - np.exp(-t[None, :] / tau[:, None]))
    return {"g": g, "pmax": pmax, "theta": theta, "slower": slower, "s": {"A": s_a, "B": s_b},
            "u_ans": u_ans, "u_slow": u_slow, "p": p}


def simulate(d, pattern, gain, rule):
    """rule = (감속 합격 인정 방식 'none'|'any'|'chosen', 게이트 g 또는 None). 숙달 판정 시점(t, 1부터; 없으면 0)."""
    mode, gate = rule
    p, u_ans, u_slow, g = d["p"], d["u_ans"], d["u_slow"], d["g"]
    s = d["s"][pattern]
    raw = np.zeros(N)
    mastered_at = np.zeros(N, dtype=int)
    for i in range(T_MAX):
        n = i
        est = raw / (1 - (1 - ALPHA) ** n) if n > 0 else np.zeros(N)
        prob = s if pattern == "A" else np.clip(s * (1 - p[:, i]) / (1 - g), 0, 1)
        chosen = u_slow[:, i] < prob
        adapt = p[:, i] < d["theta"]
        if gate is not None:
            adapt &= est < gate          # 자연 속도 확인 구간: 적응 감속만 끈다(학습자가 고른 속도는 그대로)
        pc = np.minimum(0.99, p[:, i] + np.where(chosen, gain, 0.0) + np.where(adapt, ADAPT_GAIN, 0.0))
        passed = u_ans[:, i] < pc
        if mode == "any":
            half = chosen | adapt
        elif mode == "chosen":
            half = chosen
        else:
            half = np.zeros(N, dtype=bool)
        val = np.where(passed, np.where(half, 0.5, 1.0), 0.0)
        raw = raw + ALPHA * (100.0 * val - raw)
        score = np.clip(raw / (1 - (1 - ALPHA) ** (n + 1)), 0, 100)
        hit = (mastered_at == 0) & (i + 1 >= MIN_ATT) & (score >= THR)
        mastered_at[hit] = i + 1
    return mastered_at


def metrics(d, mastered_at):
    p, pmax, slower = d["p"], d["pmax"], d["slower"]
    judged = mastered_at > 0
    idx = np.where(judged)[0]
    p_at = p[idx, mastered_at[idx] - 1]
    false_rate = float(np.mean(p_at < FALSE_P)) if len(idx) else 0.0
    over = p >= 0.65
    first = np.where(over.any(axis=1), over.argmax(axis=1) + 1, 0)

    def delays(mask):
        m = mask & (pmax >= 0.75) & (first > 0)
        k = np.where(m)[0]
        ma, f = mastered_at[k], first[k]
        done = ma > 0
        out = np.where(done, ma - f, T_MAX - f)
        keep = ~done | (ma >= f)           # 문턱을 넘기 전에 판정된 경우는 지연에서 뺀다(1·2단계 스크립트와 같다)
        return out[keep]

    dn, ds = delays(~slower), delays(slower)
    strong_slow = slower & (pmax >= 0.75)
    return {
        "false_rate": round(false_rate, 4), "judged": int(judged.sum()),
        "delay_noslow_median": float(np.median(dn)) if len(dn) else None,
        "delay_slow_median": float(np.median(ds)) if len(ds) else None,
        "slow_strong_mastered_share": round(float(np.mean(mastered_at[strong_slow] > 0)), 4),
    }


CANDIDATES = {
    "R": ("none", None), "C1": ("any", None),
    "C2:50": ("any", 50.0), "C2:60": ("any", 60.0), "C2:70": ("any", 70.0),
    "C3": ("chosen", None),
    "C4:50": ("chosen", 50.0), "C4:60": ("chosen", 60.0), "C4:70": ("chosen", 70.0),
}


def check(base, cand):
    return (cand["false_rate"] < base["false_rate"]
            and cand["delay_noslow_median"] - base["delay_noslow_median"] <= 3
            and cand["slow_strong_mastered_share"] >= base["slow_strong_mastered_share"] - 0.05)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--only", default=None, help="후보 하나만(확인용), 예: C3")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    d = draw(a.seed)
    names = ["R"] + ([a.only] if a.only else [k for k in CANDIDATES if k != "R"])
    out = {"seed": a.seed, "N": N, "results": {}}
    for gain in (0.10, 0.20):
        for pattern in ("A", "B"):
            key = f"gain{gain:.2f}_{pattern}"
            rows = {}
            for name in names:
                rows[name] = metrics(d, simulate(d, pattern, gain, CANDIDATES[name]))
            for name in names[1:]:
                rows[name]["pass"] = check(rows["R"], rows[name])
            out["results"][key] = rows
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
