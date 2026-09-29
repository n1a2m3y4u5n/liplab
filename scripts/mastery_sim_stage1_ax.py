"""1단계에 '같은지 다른지'(AX) 문항을 섞을 때의 숙달 시뮬레이션(docs/mastery-ewma.md 11절).

    backend/.venv/bin/python scripts/mastery_sim_stage1_ax.py --seed 0 [--only A1] [--out 결과.json]
    backend/.venv/bin/python scripts/mastery_sim_stage1_ax.py --smoke   # 작은 N으로 돌아가는지만 본다(수치는 찍지 않는다)

학습자는 4절(mastery_sim.py)과 같다. 입모양 무리 고르기(4지선다) 정답 확률 p(t) = 0.25 + (pmax − 0.25)(1 − e^(−t/tau)),
tau 3~40, pmax 0.45~0.98, 2만 명, 최대 200번. t는 1단계 답의 순번(고르기·AX 모두 연습으로 센다).
알아보는 몫 k(t) = (p − 0.25) / 0.75. AX 정답 확률은 k' + (1 − k')/2이고 k'은 가정마다 다르다.
  S(같은 능력): 보이는 짝 k' = k, 입 안쪽 짝 k' = k.
  H(입 안쪽이 더 어려움): 보이는 짝 k' = k + e(1 − k), e 0~0.5(둘 비교가 이름 고르기보다 쉬움), 입 안쪽 짝 k' = c·k, c 0.3~0.8.
숙련 학습자 2만 명은 p가 처음부터 0.85~0.98로 일정하고 e·c는 같은 가정에서 뽑는다.

레슨은 12문항. R(지금): 12문항 모두 고르기. A1: 1~6번은 고르기(무리 여섯이 한 번씩), 7~12번 가운데 무작위 4자리가 AX,
AX 4개 중 2개가 입 안쪽 짝(자리는 무작위). A2: A1에 더해 입 안쪽 짝 AX 답이 2개 이상이어야 숙달.
숙달 추정값은 편향 보정 이동 평균(a 0.08), 문턱 85, 최소 8번. 고르기 정답 1·오답 0, AX 정답 1·오답 −1(2지선다 우연 보정).
저장값은 앱(main._ewma_mastery)처럼 매번 0~100으로 자른다. 규칙끼리는 같은 학습자·같은 난수(정답, AX 자리, 입 안쪽 자리)를 쓴다.
"""
import argparse
import json

import numpy as np

T_MAX = 200
N = 20000
ALPHA = 0.08
THR = 85.0
MIN_ATT = 8
LESSON = 12
FIRST_PASS = 6
N_AX = 4
N_INSIDE = 2
N_INSIDE_SEEN = 2      # 11.5절 조건 3의 N
G = 0.25
FALSE_P = 0.65


def draw(seed, case, n=N):
    rng = np.random.default_rng(seed)
    tau = rng.uniform(3, 40, n)
    pmax = rng.uniform(0.45, 0.98, n)
    u_ans = rng.random((n, T_MAX))
    n_les = T_MAX // LESSON + 1
    # 레슨마다 7~12번 자리 6개의 순위: 앞 4개가 AX, 그 가운데 앞 2개가 입 안쪽 짝
    rank = rng.random((n, n_les, LESSON - FIRST_PASS)).argsort(axis=2).argsort(axis=2)
    p_sk = rng.uniform(0.85, 0.98, n)
    u_ans_sk = rng.random((n, T_MAX))
    rank_sk = rng.random((n, n_les, LESSON - FIRST_PASS)).argsort(axis=2).argsort(axis=2)
    # 가정별 e·c는 따로 뽑되 학습자·정답 난수는 두 가정이 같다
    arng = np.random.default_rng([seed, 1 if case == "S" else 2])
    if case == "S":
        e, c, e_sk, c_sk = np.zeros(n), np.ones(n), np.zeros(n), np.ones(n)
    else:
        e, c = arng.uniform(0, 0.5, n), arng.uniform(0.3, 0.8, n)
        e_sk, c_sk = arng.uniform(0, 0.5, n), arng.uniform(0.3, 0.8, n)
    t = np.arange(1, T_MAX + 1)
    p = G + (pmax[:, None] - G) * (1 - np.exp(-t[None, :] / tau[:, None]))
    main = {"p": p, "pmax": pmax, "u_ans": u_ans, "rank": rank, "e": e, "c": c}
    skilled = {"p": np.repeat(p_sk[:, None], T_MAX, axis=1), "pmax": p_sk, "u_ans": u_ans_sk, "rank": rank_sk,
               "e": e_sk, "c": c_sk}
    return main, skilled


def item_kinds(d, i):
    """i번째 답(0부터)의 종류: 0 고르기, 1 보이는 짝 AX, 2 입 안쪽 짝 AX."""
    pos = i % LESSON
    if pos < FIRST_PASS:
        return np.zeros(d["p"].shape[0], dtype=int)
    r = d["rank"][:, i // LESSON, pos - FIRST_PASS]
    return np.where(r < N_INSIDE, 2, np.where(r < N_AX, 1, 0))


def simulate(d, rule):
    """rule: 'R' | 'A1' | 'A2'. 숙달 판정 시점(1부터, 없으면 0)과 그때까지 입 안쪽 짝 AX 답 수."""
    p, u = d["p"], d["u_ans"]
    n = p.shape[0]
    est = np.zeros(n)
    mastered_at = np.zeros(n, dtype=int)
    inside_seen = np.zeros(n, dtype=int)
    inside_at = np.zeros(n, dtype=int)
    for i in range(T_MAX):
        kind = item_kinds(d, i) if rule != "R" else np.zeros(n, dtype=int)
        k = (p[:, i] - G) / (1 - G)
        k_ax = np.where(kind == 2, d["c"] * k, k + d["e"] * (1 - k))
        pc = np.where(kind == 0, p[:, i], k_ax + (1 - k_ax) / 2)
        ok = u[:, i] < pc
        val = np.where(ok, 1.0, np.where(kind == 0, 0.0, -1.0))
        raw = est * (1 - (1 - ALPHA) ** i)
        raw = raw + ALPHA * (100.0 * val - raw)
        est = np.clip(raw / (1 - (1 - ALPHA) ** (i + 1)), 0, 100)
        inside_seen += (kind == 2)
        gate = inside_seen >= N_INSIDE_SEEN if rule == "A2" else True
        hit = (mastered_at == 0) & (i + 1 >= MIN_ATT) & (est >= THR) & gate
        mastered_at[hit] = i + 1
        inside_at[hit] = inside_seen[hit]
    return mastered_at, inside_at


def metrics(d, mastered_at, inside_at):
    p, pmax = d["p"], d["pmax"]
    judged = mastered_at > 0
    idx = np.where(judged)[0]
    p_at = p[idx, mastered_at[idx] - 1]
    over = p >= 0.7
    first = np.where(over.any(axis=1), over.argmax(axis=1) + 1, 0)
    strong = pmax >= 0.8
    k = np.where(strong & (first > 0))[0]
    ma, f = mastered_at[k], first[k]
    delay = np.where(ma > 0, np.maximum(0, ma - f), T_MAX - f)          # 문턱 전 판정은 0(5절 정의)
    after = ma >= f
    delay_x = np.where(ma > 0, ma - f, T_MAX - f)[after | (ma == 0)]      # 참고: 문턱 전 판정을 뺀 4절 정의
    return {
        "false_rate": round(float(np.mean(p_at < FALSE_P)) if len(idx) else 0.0, 4),
        "judged": int(judged.sum()),
        "delay_median": float(np.median(delay)) if len(delay) else None,
        "delay_median_excl_early": float(np.median(delay_x)) if len(delay_x) else None,
        "strong_mastered_share": round(float(np.mean(mastered_at[strong] > 0)), 4),
        "inside_share": round(float(np.mean(inside_at[idx] >= N_INSIDE_SEEN)) if len(idx) else 0.0, 4),
        "mastered_attempts_median": float(np.median(mastered_at[idx])) if len(idx) else None,
    }


def skilled_metrics(d, mastered_at, inside_at):
    idx = np.where(mastered_at > 0)[0]
    return {
        "skilled_median": float(np.median(np.where(mastered_at > 0, mastered_at, T_MAX))),
        "skilled_within_first_lesson": round(float(np.mean((mastered_at > 0) & (mastered_at <= LESSON))), 4),
        "skilled_inside_share": round(float(np.mean(inside_at[idx] >= N_INSIDE_SEEN)) if len(idx) else 0.0, 4),
    }


def check(base, cand):
    """11.5절 조건 1~3."""
    return (cand["false_rate"] <= base["false_rate"]
            and cand["delay_median"] <= 1.2 * base["delay_median"]
            and cand["skilled_median"] <= 1.2 * base["skilled_median"]
            and cand["inside_share"] >= 0.9)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--only", default=None, help="후보 하나만(확인용), 예: A1")
    ap.add_argument("--out", default=None)
    ap.add_argument("--smoke", action="store_true", help="N 200, 시드 12345로 돌아가는지만 확인(수치 출력 없음)")
    a = ap.parse_args()
    n = 200 if a.smoke else N
    seed = 12345 if a.smoke else a.seed
    names = ["R"] + ([a.only] if a.only else ["A1", "A2"])
    out = {"seed": seed, "N": n, "results": {}}
    for case in ("S", "H"):
        d, sk = draw(seed, case, n)
        rows = {}
        for name in names:
            rows[name] = metrics(d, *simulate(d, name))
            rows[name].update(skilled_metrics(sk, *simulate(sk, name)))
        for name in names[1:]:
            rows[name]["pass"] = check(rows["R"], rows[name])
        out["results"][case] = rows
    if a.smoke:
        print("ok")
        return
    passing = [nm for nm in names[1:] if all(out["results"][k][nm]["pass"] for k in out["results"])]
    out["passing"] = passing
    # 11.4절: 둘 다 통과하면 규칙이 더 단순한 A1(숙달 관문 없음)
    out["chosen"] = ("A1" if "A1" in passing else passing[0]) if passing else None
    print(json.dumps(out, ensure_ascii=False, indent=1))
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
            f.write("\n")


if __name__ == "__main__":
    main()
