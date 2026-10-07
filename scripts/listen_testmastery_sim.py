"""소음 속 듣기 3차: 검사 기반 4단계 숙달(docs/listen-testmastery-sim-2026-10.md).

4단계 숙달 = 소리만 훈련 시행 ≥ 40 그리고 [최근 검사 역치 ≤ c 또는 사전 검사 대비 향상 ≥ G]. 검사는 2차에서 채택한 절차
(연습 5문장 4 dB, 검사 20문장 처음부터 2 dB)이고 폼 A·B를 번갈아 쓰며, 같은 폼을 다시 쓰면 같은 문장 난이도 오프셋을 쓴다.
지금 규칙(noise_mastered)은 2차와 같은 방법으로 같은 청취자에서 기준선으로 측정한다. 순수 numpy.

사용:
  python scripts/listen_testmastery_sim.py --seed 0 --out docs/listen-testmastery-sim-explore-seed0.json
  python scripts/listen_testmastery_sim.py --seed 1 --rules T1 --out docs/listen-testmastery-sim-confirm-seed1.json
"""
import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import listen_adaptive_sim as S  # noqa: E402
import listen_mastery_sim as M  # noqa: E402

L = S.L
T = M.T                       # 100
N_MIN = 40
C_ABS = -0.8
SCEN = M.SCEN                 # null·imp3·imp5
CONDS = ["C0", "C1", "C2", "C3", "C4", "C5", "M1"]   # M1: C1 + 같은 폼 재사용 때 기억 효과 1 dB(보조)
KP = L.TEST_STAIR["practice"]

RULES = {}
for _i in (40, 20):
    for _g in (2.0, 2.5, 3.0):
        for _m in ("c1", "c2", "m2"):
            RULES[f"i{_i}_g{int(_g * 10)}_{_m}"] = (_i, _g, _m)
RULES["T1"] = RULES["i40_g30_c1"]


def cond_of(cn):
    return dict(S.CONDITIONS["C1"], memory_db=1.0) if cn == "M1" else dict(S.CONDITIONS[cn], memory_db=0.0)


def srt_at(srt0, drop_db, t):
    """훈련 t시행 뒤의 참 SRT(2차와 같은 모양: 21~40번째에 곧게 향상)."""
    return srt0 - np.clip((t - 20) / 20.0, 0, 1) * drop_db


def one_test(rng, srt_now, slope, cond, form_off):
    """검사 한 회차(연습 5 + 20문장). form_off: (N, 20) 그 폼의 문장 오프셋."""
    N = len(srt_now)
    nsent = len(S.TRAIN_WORDS)
    pick = np.argsort(rng.random((N, nsent)), axis=1)[:, :KP]
    nwp = S.TRAIN_WORDS[pick]
    offp = rng.normal(0.0, cond["sd_item"], (N, KP)) if cond["sd_item"] > 0 else np.zeros((N, KP))
    x = np.full(N, S.START)
    for j in range(KP):
        k = S.respond(rng, x, srt_now, slope, offp[:, j], cond["sd_trial"], nwp[:, j])
        x = np.clip(x + np.where(k / nwp[:, j] >= 0.5, -L.TEST_STAIR["big"], L.TEST_STAIR["big"]), S.LO, S.HI)
    xs = np.zeros((N, 20))
    for t in range(20):
        n = int(S.TEST_WORDS[t])
        k = S.respond(rng, x, srt_now, slope, form_off[:, t], cond["sd_trial"], np.full(N, n))
        xs[:, t] = x
        step = L.TEST_STAIR["small"]
        x = np.clip(x + np.where(k / n >= 0.5, -step, step), S.LO, S.HI)
    return (xs[:, 4:20].sum(1) + x) / 17


def schedule_tests(rng, lis, cond, drop_db, interval, off):
    """사전 검사(0)와 interval마다의 재검사. 폼은 A, B, A, … 같은 폼 두 번째부터 기억 효과 memory_db."""
    times = [0] + list(range(interval, T + 1, interval))
    est, used = [], set()
    for k, t in enumerate(times):
        form = "AB"[k % 2]
        mem = cond["memory_db"] if form in used else 0.0
        used.add(form)
        est.append(one_test(rng, srt_at(lis["srt"], drop_db, t) - mem, lis["slope"], cond, off[form]))
    return times, np.stack(est, 1)


def test_mastery(times, est, g, mode, c_abs=C_ABS):
    """처음 숙달한 훈련 시행 수(없으면 inf). 검사 k의 결과로 숙달하면 max(t_k, N_MIN)."""
    N = est.shape[0]
    at = np.full(N, np.inf)
    pre = est[:, 0]
    for k, t in enumerate(times):
        h = est[:, k] <= c_abs
        if k >= 1:
            gain = pre - est[:, k]
            if mode == "c1":
                h |= gain >= g
            elif mode == "c2" and k >= 2:
                h |= (gain >= g) & ((pre - est[:, k - 1]) >= g)
            elif mode == "m2" and k >= 2:
                h |= (pre - (est[:, k] + est[:, k - 1]) / 2) >= g
        when = max(t, N_MIN)
        if when <= T:
            at = np.where(np.isinf(at) & h, when, at)
    return at


def run(seed, n_lis, conds, rules):
    res = {}
    for cn in conds:
        ci = CONDS.index(cn)
        cond = cond_of(cn)
        rng = np.random.default_rng([seed, ci, 51])
        lis = S.make_listeners(rng, n_lis)
        if "slope_fixed" in cond:
            lis["slope"] = np.full(n_lis, cond["slope_fixed"])
        t0 = time.time()
        # 지금 규칙(기준선)
        at_a = {}
        for si, (sc, drop) in enumerate(SCEN.items()):
            xs, ks, nw = M.track(np.random.default_rng([seed, ci, 52, si]), lis, cond, drop, ("stair",))
            at_a[sc] = M.rule_a(M.cur_window_est(xs, ks, nw, 20))
        res[cn] = {"a": M.summarize(lis, at_a)}
        # 검사 기반: 폼 오프셋은 청취자마다 한 번(시나리오끼리는 따로 뽑는다)
        cache = {}
        for name in rules:
            itv, g, mode = RULES[name]
            at = {}
            for si, (sc, drop) in enumerate(SCEN.items()):
                key = (itv, sc)
                if key not in cache:
                    r2 = np.random.default_rng([seed, ci, 53, itv, si])
                    off = {f: (r2.normal(0.0, cond["sd_item"], (n_lis, 20)) if cond["sd_item"] > 0 else np.zeros((n_lis, 20)))
                           for f in "AB"}
                    cache[key] = schedule_tests(r2, lis, cond, drop, itv, off)
                times, est = cache[key]
                at[sc] = test_mastery(times, est, g, mode)
            m = M.summarize(lis, at)
            m["n_tests"] = len(cache[(itv, "null")][0])
            if name == "T1":
                times, est = cache[(itv, "null")]
                m["fm_c0db"] = float(np.isfinite(test_mastery(times, est, g, mode, c_abs=0.0)[lis["srt"] >= 2.0]).mean())
                d = est[:, 1] - est[:, 0]
                m["retest_sd_pre_vs_1"] = float(np.std(d, ddof=1))
                if est.shape[1] > 2:
                    m["retest_sd_pre_vs_2_sameform"] = float(np.std(est[:, 2] - est[:, 0], ddof=1))
            res[cn][name] = m
        print(f"  {cn}: {time.time() - t0:.1f}s", flush=True)
    return res


def judge(res, name):
    fails = []
    for cn in res:
        if cn == "M1":
            continue
        m, a = res[cn][name], res[cn]["a"]
        if m["fm"] > 0.05:
            fails.append(f"{cn} FM {100 * m['fm']:.1f}")
        if m["r3"] < a["r3"] - 0.10:
            fails.append(f"{cn} R3 {100 * (m['r3'] - a['r3']):+.1f}")
        if m["nh"] < 0.95:
            fails.append(f"{cn} NH {100 * m['nh']:.1f}")
    return fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--conds", default=",".join(CONDS))
    ap.add_argument("--rules", default=",".join(r for r in RULES if r != "T1") + ",T1")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    rules = [r for r in a.rules.split(",") if r]
    t0 = time.time()
    res = run(a.seed, a.n, a.conds.split(","), rules)
    print("\n조건 규칙: FM% | R3%(중앙 시행) | R5%(중앙) | 잘하는 학습자%(중앙) | 검사 수")
    for cn, rows in res.items():
        for name, m in rows.items():
            print(f"  {cn} {name:14s} {100 * m['fm']:5.1f} | {100 * m['r3']:5.1f}({m['r3_median_trials']}) | "
                  f"{100 * m['r5']:5.1f}({m['r5_median_trials']}) | {100 * m['nh']:5.1f}({m['nh_median_trials']}) | {m.get('n_tests', '-')}")
    print("\n판정(C0~C5):")
    for name in rules:
        f = judge(res, name)
        print(f"  {name:14s} {'통과' if not f else '미달: ' + ', '.join(f)}")
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump({"seed": a.seed, "n": a.n, "c_abs": C_ABS, "n_min": N_MIN, "results": res,
                       "judge": {r: judge(res, r) for r in rules}, "elapsed_s": round(time.time() - t0, 1)},
                      fh, ensure_ascii=False, indent=1)
        print("저장:", a.out)


if __name__ == "__main__":
    main()
