"""SNR 계단의 목표 정답률·단계 크기·반전 규칙: P3 SNR 맞추기와 소리 듣기 검사(docs/listen-stair-target-sim-2026-10.md).

1차(listen_adaptive_sim.py)의 가상 청취자·응답·격자와 2차(listen_mastery_sim.py)의 연습 문장 검사 흐름을 쓴다. 순수 numpy.

사용:
  python scripts/listen_stair_target_sim.py --seed 2 --out docs/listen-stair-target-sim-explore-seed2.json
  python scripts/listen_stair_target_sim.py --seed 3 --p P0,P0w,P5 --t Ta,Tt --out docs/listen-stair-target-sim-confirm-seed3.json
"""
import argparse
import json
import math
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import listen_adaptive_sim as S  # noqa: E402

L = S.L
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
import pilot_battery as PB  # noqa: E402

COND_JUDGE = ["C0", "C1", "C2", "C3", "C4", "C5"]
CONDS = dict(S.CONDITIONS)
CONDS["C6"] = {"sd_item": 1.0, "sd_trial": 0.0, "sd_item_ci": 3.0}   # 보조: 인공와우 집단 문장 난이도 SD 3 dB
GROUPS = S.GROUPS

_M = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend", "data", "pilot",
                                 "battery_manifest.json"), encoding="utf-8"))
P3_WORDS = np.array([len(it["text"].split()) for it in _M["layers"]["snr"]["items"]])
AV_A_WORDS = np.array([len(it["text"].split()) for it in _M["layers"]["av"]["items"]["A"][:10]])
P3_CFG = dict(_M["layers"]["snr"]["staircase"])
assert len(P3_WORDS) == P3_CFG["max_trials"] == 24
LN40 = math.log(0.4 / 0.6)
BAND = (0.30, 0.50)
EXCL = (0.15, 0.85)

P_VARIANTS = {
    "P0": {"down": 3.0, "up": 2.0, "lo": -20.0, "hi": 10.0, "stop_rev": 8, "est": "rev"},
    "P0w": {"down": 3.0, "up": 2.0, "lo": -20.0, "hi": 25.0, "stop_rev": 8, "est": "rev"},
    "P1": {"down": 3.0, "up": 2.0, "lo": -20.0, "hi": 25.0, "stop_rev": None, "est": "rev"},
    "P2": {"down": 3.0, "up": 2.0, "big": (6.0, 4.0), "big_rev": 2, "lo": -20.0, "hi": 25.0, "stop_rev": 8, "est": "rev_small"},
    "P3s": {"down": 2.0, "up": 4.0 / 3.0, "lo": -20.0, "hi": 25.0, "stop_rev": 8, "est": "rev"},
    "P4": {"kind": "bk", "lo": -20.0, "hi": 25.0, "stop_rev": None, "est": "post40"},
    "P5": {"down": 3.0, "up": 2.0, "lo": -20.0, "hi": 25.0, "stop_rev": None, "est": "post40"},
}
T_VARIANTS = ("Ta", "Tt", "Tb")

# ── 공통 ─────────────────────────────────────────────────────────────

_GH_X, _GH_W = np.polynomial.hermite_e.hermegauss(24)
_GH_W = _GH_W / _GH_W.sum()


def make_lis(rng, n, pop, cond):
    if pop == "nh":
        srt = rng.normal(-4.0, 1.0, n)
        lis = {"group": np.zeros(n, int), "srt": srt,
               "slope": np.clip(0.16 - 0.004 * (srt + 4.0) + rng.normal(0.0, 0.015, n), 0.05, 0.20)}
    else:
        lis = S.make_listeners(rng, n)
    if "slope_fixed" in cond:
        lis["slope"] = np.full(n, cond["slope_fixed"])
    sdi = np.full(n, cond["sd_item"])
    if "sd_item_ci" in cond:
        sdi = np.where(lis["group"] == 2, cond["sd_item_ci"], sdi)
    lis["sd_item"] = sdi
    return lis


def offsets(rng, lis, t):
    return rng.normal(0.0, 1.0, (len(lis["srt"]), t)) * lis["sd_item"][:, None]


def expected_a(x, lis, cond):
    """x에서 기대 낱말 정답률(문장 난이도·흔들림을 적분)."""
    sd = np.sqrt(lis["sd_item"] ** 2 + cond["sd_trial"] ** 2)
    z = x[:, None] - lis["srt"][:, None] - sd[:, None] * _GH_X[None]
    return (_GH_W[None] / (1.0 + np.exp(-4.0 * lis["slope"][:, None] * z))).sum(1)


def x_at(target, lis, cond):
    lo, hi = np.full(len(lis["srt"]), -60.0), np.full(len(lis["srt"]), 80.0)
    for _ in range(50):
        mid = (lo + hi) / 2
        up = expected_a(mid, lis, cond) < target
        lo, hi = np.where(up, mid, lo), np.where(up, hi, mid)
    return (lo + hi) / 2


def post_x(logpost, target):
    xg = S.THg + math.log(target / (1 - target)) / (4.0 * S.SLg)
    lp = logpost - logpost.max(-1, keepdims=True)
    w = np.exp(lp)
    return (w * xg).sum(-1) / w.sum(-1)


# ── P3 SNR 맞추기 ────────────────────────────────────────────────────

def run_p(rng, lis, cond, var):
    N = len(lis["srt"])
    T = len(P3_WORDS)
    order = np.argsort(rng.random((N, T)), axis=1)
    words = P3_WORDS[order]
    offs = offsets(rng, lis, T)
    x = np.full(N, float(P3_CFG["start_db"]))
    lo, hi = var["lo"], var["hi"]
    last = np.zeros(N)
    nrev = np.zeros(N, int)
    revs = np.full((N, T), np.nan)
    rev_small = np.zeros((N, T), bool)
    hist = np.full((N, T), np.nan)
    active = np.ones(N, bool)
    logpost = np.tile(S.log_prior("flat"), (N, 1)) if var["est"] == "post40" else None
    bk = S.BK(N, 0.40, 0.15, 0.1, False) if var.get("kind") == "bk" else None
    ntr = np.zeros(N, int)
    for t in range(T):
        n = words[:, t]
        k = S.respond(rng, x, lis["srt"], lis["slope"], offs[:, t], cond["sd_trial"], n)
        prop = k / n
        hist[active, t] = x[active]
        ntr += active
        if logpost is not None:
            ll = S.loglik(x, k, n)
            logpost = logpost + np.where(active[:, None], ll, 0.0)
        if bk is not None:
            xn = bk.step(x, prop)
            xn = np.clip(xn, lo, hi)
        else:
            ok = prop >= P3_CFG["criterion"]
            d = np.where(ok, -1, 1)
            rev = (last != 0) & (d != last) & active
            big = ("big" in var) & (nrev < var.get("big_rev", 0))
            revs[rev, t] = x[rev]
            rev_small[rev, t] = ~big[rev] if "big" in var else True
            nrev = nrev + rev
            last = np.where(active, d, last)
            down = np.where(big, var["big"][0], var["down"]) if "big" in var else var["down"]
            up = np.where(big, var["big"][1], var["up"]) if "big" in var else var["up"]
            xn = np.clip(np.where(ok, x - down, x + up), lo, hi)
        x = np.where(active, xn, x)
        if var["stop_rev"]:
            active = active & (nrev < var["stop_rev"])
    if var["est"] == "post40":
        est = post_x(logpost, 0.40)
    else:
        est = np.zeros(N)
        for i in range(N):
            r = revs[i][~np.isnan(revs[i])]
            if var["est"] == "rev_small":
                r = revs[i][rev_small[i] & ~np.isnan(revs[i])]
            h = hist[i][~np.isnan(hist[i])]
            est[i] = r[-6:].mean() if len(r) >= 6 else h[-6:].mean()
    return est, ntr, hist


def check_p0_matches_app(seed=0, n=300):
    """P0 벡터 구현이 pilot_battery.staircase_run과 같은지(무작위 판정)."""
    rng = np.random.default_rng([seed, 55])
    for _ in range(n):
        oks = list(rng.random(24) < rng.uniform(0.2, 0.8))
        r = PB.staircase_run(P3_CFG, oks)
        # 같은 판정을 시뮬레이션 규칙으로
        x, last, revs, hist = 0.0, 0, [], []
        for ok in oks[:r["n_trials"]]:
            hist.append(x)
            d = -1 if ok else 1
            if last and d != last:
                revs.append(x)
            last = d
            x = min(10.0, max(-20.0, x - 3 if ok else x + 2))
        est = sum(revs[-6:]) / 6 if len(revs) >= 6 else sum(hist[-6:]) / 6
        assert r["history"] == hist and abs(r["estimate_db"] - est) < 0.006, (r, hist, est)


def a_block(rng, x, lis, cond):
    n = len(AV_A_WORDS)
    offs = offsets(rng, lis, n)
    k = np.zeros(len(x))
    for j in range(n):
        k += S.respond(rng, x, lis["srt"], lis["slope"], offs[:, j], cond["sd_trial"], np.full(len(x), AV_A_WORDS[j]))
    return k / AV_A_WORDS.sum()


def summarize_p(lis, cond, est, ntr, hi, rng):
    a = expected_a(est, lis, cond)
    x40 = x_at(0.40, lis, cond)
    obs = a_block(rng, est, lis, cond)
    inb = (a >= BAND[0]) & (a <= BAND[1])
    exc = (obs < EXCL[0]) | (obs > EXCL[1])
    ceil = (x40 > hi) & (est >= hi - 1e-9)

    def stats(m):
        nn = int(m.sum())
        return {"n": nn, "inband": float(inb[m].mean()), "excl": float(exc[m].mean()), "mean_a": float(a[m].mean()),
                "sd_a": float(a[m].std()), "rmse": float(np.sqrt(((est - x40)[m] ** 2).mean())),
                "bias": float((est - x40)[m].mean()), "ceiling": float(ceil[m].mean()),
                "unreachable": float((x40 > hi)[m].mean()), "trials": float(ntr[m].mean()),
                "inband_se": float(np.sqrt(inb[m].mean() * (1 - inb[m].mean()) / max(1, nn)))}
    out = stats(np.ones(len(est), bool))
    out["groups"] = {g: stats(lis["group"] == gi) for gi, g in enumerate(GROUPS) if (lis["group"] == gi).any()}
    return out


def run_p_all(seed, n, variants, conds):
    check_p0_matches_app()
    res = {}
    for pop in ("nh", "mix"):
        res[pop] = {}
        for cn in conds:
            ci = list(CONDS).index(cn)
            cond = CONDS[cn]
            lis = make_lis(np.random.default_rng([seed, ci, 61, pop == "mix"]), n, pop, cond)
            res[pop][cn] = {}
            for vn in variants:
                var = P_VARIANTS[vn]
                vr = np.random.default_rng([seed, ci, 62, pop == "mix", list(P_VARIANTS).index(vn)])
                t0 = time.time()
                est, ntr, _ = run_p(vr, lis, cond, var)
                res[pop][cn][vn] = summarize_p(lis, cond, est, ntr, var["hi"], vr)
                print(f"  P {pop} {cn} {vn}: {time.time() - t0:.1f}s", flush=True)
    return res


# ── 소리 듣기 검사 ───────────────────────────────────────────────────

def run_t(rng, lis, cond, var):
    N = len(lis["srt"])
    kp = L.TEST_STAIR["practice"]
    nsent = len(S.TRAIN_WORDS)
    x = np.full(N, S.START)
    pick = np.argsort(rng.random((N, nsent)), axis=1)[:, :kp]
    nwp = S.TRAIN_WORDS[pick]
    offp = offsets(rng, lis, kp)
    tie = var in ("Tt", "Tb")
    for j in range(kp):
        k = S.respond(rng, x, lis["srt"], lis["slope"], offp[:, j], cond["sd_trial"], nwp[:, j])
        p = k / nwp[:, j]
        step = np.where(p > 0.5, -L.TEST_STAIR["big"], L.TEST_STAIR["big"]) if tie else \
            np.where(p >= 0.5, -L.TEST_STAIR["big"], L.TEST_STAIR["big"])
        if tie:
            step = np.where(p == 0.5, 0.0, step)
        x = np.clip(x + step, S.LO, S.HI)
    words = S.TEST_WORDS
    offs = offsets(rng, lis, 20)
    xs, props, nxt = np.zeros((N, 20)), np.zeros((N, 20)), np.zeros((N, 20))
    bk = S.BK(N, 0.5, 0.15, 0.1, False) if var == "Tb" else None
    logpost = np.tile(S.log_prior("flat"), (N, 1)) if var == "Tb" else None
    for t in range(20):
        n = int(words[t])
        k = S.respond(rng, x, lis["srt"], lis["slope"], offs[:, t], cond["sd_trial"], np.full(N, n))
        p = k / n
        xs[:, t], props[:, t] = x, p
        if var == "Tb":
            logpost = logpost + S.loglik(x, k, np.full(N, n))
            x = bk.step(x, p)
        else:
            s = L.TEST_STAIR["small"]
            step = np.where(p >= 0.5, -s, s) if var == "Ta" else np.where(p == 0.5, 0.0, np.where(p > 0.5, -s, s))
            x = np.clip(x + step, S.LO, S.HI)
        nxt[:, t] = x
    est = post_x(logpost, 0.5) if var == "Tb" else S.mean_est(xs, nxt, 20)
    blocked = ((xs >= S.HI - 1e-9) & (props < 0.5)).any(1)
    return est, blocked


def run_t_all(seed, n, variants, conds):
    import listen_mastery_sim as M
    M.check_practice_matches_app()
    res = {}
    for cn in conds:
        ci = list(CONDS).index(cn)
        cond = CONDS[cn]
        lis = make_lis(np.random.default_rng([seed, ci, 71]), n, "mix", cond)
        res[cn] = {}
        for vn in variants:
            vr = np.random.default_rng([seed, ci, 72, T_VARIANTS.index(vn)])
            t0 = time.time()
            e1, b1 = run_t(vr, lis, cond, vn)
            e2, b2 = run_t(vr, lis, cond, vn)
            res[cn][vn] = S.summarize_test(lis, e1, e2, np.concatenate([b1, b2]))
            print(f"  T {cn} {vn}: {time.time() - t0:.1f}s", flush=True)
    return res


# ── 판정(사전 기준 5.1·5.2) ──────────────────────────────────────────

def judge_p(res, cand, conds=COND_JUDGE):
    rows = {}
    ok_all = True
    for cn in conds:
        nh, nh0 = res["nh"][cn][cand], res["nh"][cn]["P0"]
        mx, mx0 = res["mix"][cn][cand], res["mix"][cn]["P0"]
        c1 = nh["inband"] - nh0["inband"] >= 0.05
        c2 = nh["excl"] <= nh0["excl"] + 0.005
        c3 = all(0.35 <= mx["groups"][g]["mean_a"] <= 0.45 for g in GROUPS)
        c4 = all(mx["groups"][g]["excl"] <= mx0["groups"][g]["excl"] + 0.005 for g in ("HA", "CI"))
        rows[cn] = {"c1": c1, "c2": c2, "c3": c3, "c4": c4, "d_inband_nh": round(nh["inband"] - nh0["inband"], 4)}
        ok_all &= c1 and c2 and c3 and c4
    return ok_all, rows


def judge_p0w(res, conds=COND_JUDGE):
    rows, ok_all = {}, True
    for cn in conds:
        a = res["nh"][cn]["P0w"]["inband"] - res["nh"][cn]["P0"]["inband"] >= -0.01
        b = all(res["mix"][cn]["P0w"]["groups"][g]["excl"] < res["mix"][cn]["P0"]["groups"][g]["excl"] for g in ("HA", "CI"))
        rows[cn] = {"nh_noninf": a, "haci_excl_lower": b}
        ok_all &= a and b
    return ok_all, rows


def judge_t(res, cand, conds=COND_JUDGE):
    rows, ok_all = {}, True
    for cn in conds:
        r, r0 = res[cn][cand], res[cn]["Ta"]
        c1 = abs(r["bias"]) <= 0.3 and all(abs(r["groups"][g]["bias"]) <= 0.5 for g in GROUPS)
        c2 = r["retest_sd"] <= 1.05 * r0["retest_sd"]
        c3 = r["blocked"] <= r0["blocked"] + 0.01
        rows[cn] = {"c1": c1, "c2": c2, "c3": c3, "sd_ratio": round(r["retest_sd"] / r0["retest_sd"], 3), "bias": round(r["bias"], 3)}
        ok_all &= c1 and c2 and c3
    return ok_all, rows


def print_tables(res):
    if "p" in res:
        for pop in ("nh", "mix"):
            print(f"\n[P3 SNR 맞추기, {pop}] 띠 안 / 관측 제외 / 평균 A / RMSE / 시행")
            for cn, r in res["p"][pop].items():
                for vn, s in r.items():
                    g = " ".join(f"{k}:{v['inband']:.2f}/{v['excl']:.3f}/{v['mean_a']:.2f}" for k, v in s["groups"].items()) if pop == "mix" else ""
                    print(f"  {cn} {vn:4s} {s['inband']:.3f} {s['excl']:.3f} {s['mean_a']:.3f} {s['rmse']:.2f} {s['trials']:.1f} {g}")
    if "t" in res:
        print("\n[소리 듣기 검사] 편향 / 재검사 SD / 막힘 / 집단 편향")
        for cn, r in res["t"].items():
            for vn, s in r.items():
                g = " ".join(f"{k}:{v['bias']:+.2f}" for k, v in s["groups"].items())
                print(f"  {cn} {vn} {s['bias']:+.3f} {s['retest_sd']:.3f} {s['blocked']:.4f} {g}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--p", default=",".join(P_VARIANTS))
    ap.add_argument("--t", default=",".join(T_VARIANTS))
    ap.add_argument("--conds", default="C0,C1,C2,C3,C4,C5,C6")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    conds = [c for c in a.conds.split(",") if c]
    res = {"seed": a.seed, "n": a.n, "conds": conds}
    pv = [v for v in a.p.split(",") if v]
    tv = [v for v in a.t.split(",") if v]
    if pv:
        res["p"] = run_p_all(a.seed, a.n, pv, conds)
        jc = [c for c in COND_JUDGE if c in conds]
        res["judge_p"] = {v: judge_p(res["p"], v, jc) for v in pv if v not in ("P0", "P0w")}
        if "P0w" in pv:
            res["judge_p0w"] = judge_p0w(res["p"], jc)
    if tv:
        res["t"] = run_t_all(a.seed, a.n, tv, conds)
        res["judge_t"] = {v: judge_t(res["t"], v, [c for c in COND_JUDGE if c in conds]) for v in tv if v != "Ta"}
    print_tables(res)
    for k in ("judge_p", "judge_p0w", "judge_t"):
        if k in res:
            print(k, json.dumps({v: j[0] for v, j in res[k].items()} if k != "judge_p0w" else res[k][0], ensure_ascii=False))
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))


if __name__ == "__main__":
    main()
