"""감속 재생 정답을 숙달에 어떻게 넣을지 시뮬레이션(docs/mastery-ewma.md 7절, 커리큘럼 개선 계획 1-1).

    backend/.venv/bin/python scripts/mastery_sim_speed.py --seed 0 [--only C2:60] [--out 결과.json]

학습자 모형은 scripts/mastery_sim.py와 같다(4지선다 우연 0.25, tau 3~40, pmax 0.45~0.98, 최대 200번). 여기에 감속을 더한다.
절반은 감속을 보지 않고, 나머지는 A(시도마다 확률 s, s 0.1~0.6) 또는 B(확률 s(1 − p)/(1 − 0.25), s 0.2~1.0)로 감속을 본다.
감속해 보면 정답 확률이 min(0.99, p + 0.10)이다. numpy로 학습자 전체를 한꺼번에 계산하고, 규칙끼리 같은 난수를 쓴다.

R: 편향 보정 이동 평균(main._ewma_mastery, a 0.08) ≥ 85, 감속 정답도 1.
C1: 감속 정답을 0.5로. C2(g): C1 + 추정값이 g 이상이면 감속을 끄고 자연 속도로 낸다.
"""
import argparse
import json

import numpy as np

G = 0.25
T_MAX = 200
N = 20000
ALPHA = 0.08
THR = 85.0
SLOW_GAIN = 0.10
FALSE_P = 0.65


def draw(seed):
    rng = np.random.default_rng(seed)
    tau = rng.uniform(3, 40, N)
    pmax = rng.uniform(0.45, 0.98, N)
    slower = rng.random(N) < 0.5
    s_a = np.where(slower, rng.uniform(0.1, 0.6, N), 0.0)
    s_b = np.where(slower, rng.uniform(0.2, 1.0, N), 0.0)
    u_ans = rng.random((N, T_MAX))
    u_slow = rng.random((N, T_MAX))
    t = np.arange(1, T_MAX + 1)
    p = G + (pmax[:, None] - G) * (1 - np.exp(-t[None, :] / tau[:, None]))
    return {"pmax": pmax, "slower": slower, "s": {"A": s_a, "B": s_b}, "u_ans": u_ans, "u_slow": u_slow, "p": p}


def simulate(d, pattern, credit_slow, gate, min_att):
    """숙달 판정 시점(t, 1부터; 없으면 0)을 돌려준다."""
    p, u_ans, u_slow = d["p"], d["u_ans"], d["u_slow"]
    s = d["s"][pattern]
    raw = np.zeros(N)
    mastered_at = np.zeros(N, dtype=int)
    for i in range(T_MAX):
        n = i                      # 이번 시도 전 시도 수
        est = raw / (1 - (1 - ALPHA) ** n) if n > 0 else np.zeros(N)
        prob = s if pattern == "A" else np.clip(s * (1 - p[:, i]) / (1 - G), 0, 1)
        slow = u_slow[:, i] < prob
        if gate is not None:
            slow &= est < gate     # 자연 속도 확인 구간: 추정값이 gate 이상이면 감속을 끈다
        pc = np.where(slow, np.minimum(0.99, p[:, i] + SLOW_GAIN), p[:, i])
        correct = u_ans[:, i] < pc
        val = np.where(correct, np.where(slow, credit_slow, 1.0), 0.0)
        raw = raw + ALPHA * (100.0 * val - raw)
        score = np.clip(raw / (1 - (1 - ALPHA) ** (n + 1)), 0, 100)
        hit = (mastered_at == 0) & (i + 1 >= min_att) & (score >= THR)
        mastered_at[hit] = i + 1
    return mastered_at


def metrics(d, mastered_at):
    p, pmax, slower = d["p"], d["pmax"], d["slower"]
    judged = mastered_at > 0
    idx = np.where(judged)[0]
    p_at = p[idx, mastered_at[idx] - 1]
    false_rate = float(np.mean(p_at < FALSE_P)) if len(idx) else 0.0
    # 처음 p >= 0.7인 시점(1부터), 없으면 0
    over = p >= 0.7
    first70 = np.where(over.any(axis=1), over.argmax(axis=1) + 1, 0)

    def delays(mask):
        m = mask & (pmax >= 0.8) & (first70 > 0)
        out = []
        for k in np.where(m)[0]:
            if mastered_at[k] > 0:
                if mastered_at[k] >= first70[k]:
                    out.append(mastered_at[k] - first70[k])
            else:
                out.append(T_MAX - first70[k])   # 끝까지 못 받음(검열)
        return out

    dn = delays(~slower)
    ds = delays(slower)
    strong_slow = slower & (pmax >= 0.8)
    return {
        "false_rate": round(false_rate, 4), "judged": int(judged.sum()),
        "delay_noslow_median": float(np.median(dn)) if dn else None,
        "delay_slow_median": float(np.median(ds)) if ds else None,
        "slow_strong_mastered_share": round(float(np.mean(mastered_at[strong_slow] > 0)), 4),
    }


CANDIDATES = {"R": (1.0, None), "C1": (0.5, None), "C2:50": (0.5, 50.0), "C2:60": (0.5, 60.0), "C2:70": (0.5, 70.0)}


def check(base, cand):
    return (cand["false_rate"] < base["false_rate"]
            and cand["delay_noslow_median"] - base["delay_noslow_median"] <= 3
            and cand["slow_strong_mastered_share"] >= base["slow_strong_mastered_share"] - 0.05)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--only", default=None, help="후보 하나만(확인용), 예: C2:60")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    d = draw(a.seed)
    names = ["R"] + ([a.only] if a.only else [k for k in CANDIDATES if k != "R"])
    out = {"seed": a.seed, "results": {}}
    for min_att in (8, 6):
        for pattern in ("A", "B"):
            key = f"min{min_att}_{pattern}"
            rows = {}
            for name in names:
                credit, gate = CANDIDATES[name]
                rows[name] = metrics(d, simulate(d, pattern, credit, gate, min_att))
            for name in names[1:]:
                rows[name]["pass"] = check(rows["R"], rows[name])
            out["results"][key] = rows
    passing = [n for n in names[1:] if all(out["results"][k][n]["pass"] for k in out["results"])]
    mean_false = {n: float(np.mean([out["results"][k][n]["false_rate"] for k in out["results"]])) for n in passing}
    out["passing"] = passing
    out["chosen"] = min(passing, key=lambda n: mean_false[n]) if passing else None
    print(json.dumps(out, ensure_ascii=False, indent=1))
    if a.out:
        json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
