"""소음 속 듣기 4차: 훈련 기록이 향상을 가리킬 때만 재검사를 권하고 재검사로 숙달을 판정하는 결합안(docs/listen-combined-mastery-sim-2026-10.md).

1~3차 스크립트의 청취자·응답·계단·검사 함수를 쓴다. 순수 numpy.

사용:
  python scripts/listen_combined_mastery_sim.py --seed 0 --out docs/listen-combined-mastery-sim-explore-seed0.json
  python scripts/listen_combined_mastery_sim.py --seed 1 --rules A1 --out docs/listen-combined-mastery-sim-confirm-seed1.json
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
import listen_testmastery_sim as TM  # noqa: E402

T, N_MIN, C_ABS, COOLDOWN = M.T, 40, -0.8, 20
SCEN = M.SCEN
CONDS = ["C0", "C1", "C2", "C3", "C4", "C5"]
FORMS = {"F4": ("ABCD", 0.0), "F2m1": ("ABAB", 1.0), "F2m0": ("ABAB", 0.0)}

RULES = {}
for _e in ("cur20", "ml30"):
    for _g in (1.5, 2.0):
        for _k in (2, 3):
            RULES[f"a_{_e}_g{int(_g * 10)}_k{_k}"] = {"est": _e, "gt": _g, "k": _k, "G": 3.0, "cool": COOLDOWN}
RULES["A1"] = RULES["a_cur20_g20_k3"]
RULES["b_sched"] = {"est": "always", "gt": 0.0, "k": 2, "G": 5.0, "cool": 40}
RULES["b_comb"] = dict(RULES["A1"], G=5.0)


def trigger(rule, est20, mu30):
    """trig[:, n] = n번째 시행 뒤 재검사 권유(n = 0..T)."""
    N = est20.shape[0]
    trig = np.zeros((N, T + 1), bool)
    for n in range(N_MIN, T + 1):
        if rule["est"] == "always":
            trig[:, n] = True
        elif rule["est"] == "cur20":
            rec = est20[:, n - 20]
            trig[:, n] = (est20[:, 0] - rec >= rule["gt"]) | (rec <= C_ABS + 2.0)
        else:
            rec = mu30[:, n - 30]
            trig[:, n] = (mu30[:, 0] - rec >= rule["gt"]) | (rec <= 0.0 + 2.0)
    return trig


def run_rule(rng, lis, cond, drop, rule, trig, forms, memory):
    N = len(lis["srt"])
    off = {f: (rng.normal(0.0, cond["sd_item"], (N, 20)) if cond["sd_item"] > 0 else np.zeros((N, 20))) for f in set(forms)}
    pre = TM.one_test(rng, lis["srt"], lis["slope"], cond, off[forms[0]])
    at = np.where(pre <= C_ABS, float(N_MIN), np.inf)
    used = np.zeros(N, int)
    last = np.full(N, -10 ** 6)
    for n in range(N_MIN, T + 1):
        cand = np.isinf(at) & (used < rule["k"]) & trig[:, n] & (n - last >= rule["cool"])
        idx = np.flatnonzero(cand)
        for k in np.unique(used[idx]):
            sub = idx[used[idx] == k]
            form = forms[k + 1]
            mem = memory if form in forms[:k + 1] else 0.0
            est = TM.one_test(rng, TM.srt_at(lis["srt"][sub], drop, n) - mem, lis["slope"][sub], cond, off[form][sub])
            hit = ((pre[sub] - est) >= rule["G"]) | (est <= C_ABS)
            at[sub[hit]] = n
        used[idx] += 1
        last[idx] = n
    return at, used


def run(seed, n_lis, conds, rules, form_keys):
    res = {}
    for cn in conds:
        ci = CONDS.index(cn)
        cond = dict(S.CONDITIONS[cn])
        rng = np.random.default_rng([seed, ci, 61])
        lis = S.make_listeners(rng, n_lis)
        if "slope_fixed" in cond:
            lis["slope"] = np.full(n_lis, cond["slope_fixed"])
        t0 = time.time()
        tracks = {}
        at_a = {}
        for si, (sc, drop) in enumerate(SCEN.items()):
            xs, ks, nw = M.track(np.random.default_rng([seed, ci, 62, si]), lis, cond, drop, ("stair",))
            est20 = M.cur_window_est(xs, ks, nw, 20)
            mu30 = M.ml_window_stats(xs, ks, nw, ws=(30,))[30][0] if any(RULES[r]["est"] == "ml30" for r in rules) else None
            tracks[sc] = (est20, mu30)
            at_a[sc] = M.rule_a(est20)
        res[cn] = {"a": M.summarize(lis, at_a)}
        for fk in form_keys:
            forms, memory = FORMS[fk]
            for name in rules:
                rule = RULES[name]
                at, nre = {}, {}
                for si, (sc, drop) in enumerate(SCEN.items()):
                    trig = trigger(rule, *tracks[sc])
                    r2 = np.random.default_rng([seed, ci, 63, si, list(FORMS).index(fk), list(RULES).index(name)])
                    at[sc], used = run_rule(r2, lis, cond, drop, rule, trig, forms, memory)
                    nre[sc] = float(used.mean())
                m = M.summarize(lis, at)
                m["retests_null"], m["retests_imp3"] = nre["null"], nre["imp3"]
                res[cn][f"{fk}:{name}"] = m
        print(f"  {cn}: {time.time() - t0:.1f}s", flush=True)
    return res


def judge(res, key):
    fails = []
    for cn in res:
        m, a = res[cn][key], res[cn]["a"]
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
    ap.add_argument("--rules", default=",".join(r for r in RULES if r != "A1") + ",A1")
    ap.add_argument("--forms", default=",".join(FORMS))
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    rules = [r for r in a.rules.split(",") if r]
    t0 = time.time()
    res = run(a.seed, a.n, a.conds.split(","), rules, a.forms.split(","))
    print("\n조건 규칙: FM% | R3%(중앙) | R5%(중앙) | 잘하는%(중앙) | 재검사 수(향상 없음/3 dB)")
    for cn, rows in res.items():
        for key, m in rows.items():
            rt = f"{m['retests_null']:.2f}/{m['retests_imp3']:.2f}" if "retests_null" in m else "-"
            print(f"  {cn} {key:22s} {100 * m['fm']:5.1f} | {100 * m['r3']:5.1f}({m['r3_median_trials']}) | "
                  f"{100 * m['r5']:5.1f}({m['r5_median_trials']}) | {100 * m['nh']:5.1f}({m['nh_median_trials']}) | {rt}")
    keys = [k for k in res[next(iter(res))] if k != "a"]
    print("\n판정(C0~C5):")
    for key in keys:
        f = judge(res, key)
        print(f"  {key:22s} {'통과' if not f else '미달: ' + ', '.join(f)}")
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump({"seed": a.seed, "n": a.n, "results": res, "judge": {k: judge(res, k) for k in keys},
                       "elapsed_s": round(time.time() - t0, 1)}, fh, ensure_ascii=False, indent=1)
        print("저장:", a.out)


if __name__ == "__main__":
    main()
