"""소음 속 듣기 5차: 결합 숙달(훈련 기록 선별 + 재검사)과 두 폼 평균 기준(docs/listen-combined5-sim-2026-10.md).

4차 결합안 A1(지금 추정량 20시행 창, 처음 창 대비 2 dB 또는 절대 기준 + 2 dB 이하면 재검사 권유, 직전 재검사에서 20시행 뒤)에
사전 검사·재검사를 폼 두 개 평균으로 하는 변형을 더한다. 폼은 4개(A·B·C·D) 재사용 없음이 기본(F4)이고, 폼 2개뿐일 때의 대체 흐름(F2m1, 같은
폼 재사용 때 기억 효과 1 dB)을 참고로 함께 측정한다. 훈련 문장 어절 수는 listen_curriculum.TRAIN_SENTENCES(120개)에서 다시 센다.

사용:
  python scripts/listen_combined5_sim.py --seed 0 --out docs/listen-combined5-sim-explore-seed0.json
  python scripts/listen_combined5_sim.py --seed 1 --cands a --out docs/listen-combined5-sim-confirm-seed1.json
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
import listen_combined_mastery_sim as C4  # noqa: E402

T, N_MIN, C_ABS, COOLDOWN, G = M.T, 40, -0.8, 20, 3.0
SCEN = M.SCEN
CONDS = ["C0", "C1", "C2", "C3", "C4", "C5"]

# 후보: 사전 검사 폼(평균), 재검사 폼 묶음 목록. F4는 폼 4개 재사용 없음, F2m1은 폼 2개뿐일 때(재사용, 기억 1 dB).
CANDS = {
    "a": {"F4": ("AB", ["C", "D"]), "F2m1": ("AB", ["A", "B"])},
    "b": {"F4": ("AB", ["CD"]), "F2m1": ("AB", ["AB"])},
    "c": {"F4": ("A", ["B", "C", "D"]), "F2m1": ("A", ["B", "A", "B"])},
}
MEMORY = {"F4": 0.0, "F2m1": 1.0}


def n_sentences(pre, retests_used):
    """검사에 든 문장 수(회차마다 연습 5 + 20)."""
    return 25 * (len(pre) + sum(len(r) for r in retests_used))


def run_cand(rng, lis, cond, drop, trig, pre_forms, retests, memory):
    N = len(lis["srt"])
    forms = set(pre_forms) | set("".join(retests))
    off = {f: (rng.normal(0.0, cond["sd_item"], (N, 20)) if cond["sd_item"] > 0 else np.zeros((N, 20))) for f in sorted(forms)}
    seen = set()
    pres = []
    for f in pre_forms:
        mem = memory if f in seen else 0.0
        pres.append(TM.one_test(rng, lis["srt"] - mem, lis["slope"], cond, off[f]))
        seen.add(f)
    pre = np.mean(pres, 0)
    at = np.where(pre <= C_ABS, float(N_MIN), np.inf)
    used = np.zeros(N, int)
    last = np.full(N, -10 ** 6)
    n_sent = np.full(N, 25.0 * len(pre_forms))
    for n in range(N_MIN, T + 1):
        cand = np.isinf(at) & (used < len(retests)) & trig[:, n] & (n - last >= COOLDOWN)
        idx = np.flatnonzero(cand)
        for k in np.unique(used[idx]):
            sub = idx[used[idx] == k]
            group = retests[k]
            prior = set(pre_forms) | set("".join(retests[:k]))
            ests = []
            for f in group:
                mem = memory if f in prior else 0.0
                ests.append(TM.one_test(rng, TM.srt_at(lis["srt"][sub], drop, n) - mem, lis["slope"][sub], cond, off[f][sub]))
            est = np.mean(ests, 0)
            hit = ((pre[sub] - est) >= G) | (est <= C_ABS)
            at[sub[hit]] = n
            n_sent[sub] += 25.0 * len(group)
        used[idx] += 1
        last[idx] = n
    return at, used, n_sent


def run(seed, n_lis, conds, cands, form_keys):
    res = {}
    rule = C4.RULES["A1"]
    for cn in conds:
        ci = CONDS.index(cn)
        cond = dict(S.CONDITIONS[cn])
        rng = np.random.default_rng([seed, ci, 71])
        lis = S.make_listeners(rng, n_lis)
        if "slope_fixed" in cond:
            lis["slope"] = np.full(n_lis, cond["slope_fixed"])
        t0 = time.time()
        trigs, at_a = {}, {}
        for si, (sc, drop) in enumerate(SCEN.items()):
            xs, ks, nw = M.track(np.random.default_rng([seed, ci, 72, si]), lis, cond, drop, ("stair",))
            est20 = M.cur_window_est(xs, ks, nw, 20)
            trigs[sc] = C4.trigger(rule, est20, None)
            at_a[sc] = M.rule_a(est20)
        res[cn] = {"now": M.summarize(lis, at_a)}
        for fk in form_keys:
            for cname in cands:
                pre_forms, retests = CANDS[cname][fk]
                at, used, ns = {}, {}, {}
                for si, (sc, drop) in enumerate(SCEN.items()):
                    r2 = np.random.default_rng([seed, ci, 73, si, list(MEMORY).index(fk), list(CANDS).index(cname)])
                    at[sc], u, s = run_cand(r2, lis, cond, drop, trigs[sc], pre_forms, retests, MEMORY[fk])
                    used[sc], ns[sc] = float(u.mean()), float(s.mean())
                m = M.summarize(lis, at)
                m.update({"retests_null": used["null"], "retests_imp3": used["imp3"],
                          "sentences_null": ns["null"], "sentences_imp3": ns["imp3"]})
                res[cn][f"{fk}:{cname}"] = m
        print(f"  {cn}: {time.time() - t0:.1f}s", flush=True)
    return res


def judge(res, key):
    fails = []
    for cn in res:
        m = res[cn][key]
        if m["fm"] > 0.05:
            fails.append(f"{cn} FM {100 * m['fm']:.1f}")
        if m["r3"] < 0.70:
            fails.append(f"{cn} R3 {100 * m['r3']:.1f}")
        if m["r5"] < 0.90:
            fails.append(f"{cn} R5 {100 * m['r5']:.1f}")
        if m["nh"] < 0.95:
            fails.append(f"{cn} NH {100 * m['nh']:.1f}")
    return fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--conds", default=",".join(CONDS))
    ap.add_argument("--cands", default=",".join(CANDS))
    ap.add_argument("--forms", default=",".join(MEMORY))
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    t0 = time.time()
    res = run(a.seed, a.n, a.conds.split(","), a.cands.split(","), a.forms.split(","))
    print("\n조건 후보: FM% | R3%(중앙) | R5%(중앙) | 잘하는%(중앙) | 재검사 수(없음/3 dB) | 검사 문장 수(없음/3 dB)")
    for cn, rows in res.items():
        for key, m in rows.items():
            extra = (f"{m['retests_null']:.2f}/{m['retests_imp3']:.2f} | {m['sentences_null']:.0f}/{m['sentences_imp3']:.0f}"
                     if "retests_null" in m else "-")
            print(f"  {cn} {key:8s} {100 * m['fm']:5.1f} | {100 * m['r3']:5.1f}({m['r3_median_trials']}) | "
                  f"{100 * m['r5']:5.1f}({m['r5_median_trials']}) | {100 * m['nh']:5.1f}({m['nh_median_trials']}) | {extra}")
    keys = [k for k in res[next(iter(res))] if k != "now"]
    print("\n판정(C0~C5, 새 기준):")
    for key in keys:
        f = judge(res, key)
        print(f"  {key:8s} {'통과' if not f else '미달: ' + ', '.join(f)}")
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump({"seed": a.seed, "n": a.n, "train_word_counts": {int(k): int(v) for k, v in zip(*np.unique(S.TRAIN_WORDS, return_counts=True))},
                       "results": res, "judge": {k: judge(res, k) for k in keys}, "elapsed_s": round(time.time() - t0, 1)},
                      fh, ensure_ascii=False, indent=1)
        print("저장:", a.out)


if __name__ == "__main__":
    main()
