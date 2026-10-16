"""소리 듣기 배치검사 3차 가상 청취자 시뮬레이션(docs/listen-placement3-2026-10.md, 사전 등록 8614b44e).

후보 C '1단계 수준 + 낱말 확인': 2차 A 배치 그대로, 위 단계 ≥ 3이면 낱말 수준 3 확인(미달이면 2단계만 연다)(1절).
후보 D '1·2단계 건너뛰지 않기': 위 단계 3~5와 1단계·2단계 시작 수준을 정한다(2절).
청취자·조건·채점 모형은 1·2차(listen_placement_sim, listen_placement_model, listen_placement2_sim)를 그대로 불러 쓴다.

사용:
  python scripts/listen_placement3_sim.py smoke --seeds 999 --n 40
  python scripts/listen_placement3_sim.py explore --seeds 0 --n 2000 --out docs/listen-placement3-explore-seed0.json --workers 6
  python scripts/listen_placement3_sim.py confirm --seeds 101 102 --n 2000 --pick-c '<C 조합>' --pick-d '<D 조합>' --out ...
"""
import argparse
import json
import os
import sys
import time
from multiprocessing import get_context

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import listen_placement_model as LP  # noqa: E402
import listen_placement_sim as LS  # noqa: E402
import listen_placement2_sim as P2  # noqa: E402

CONDS = list(LS.CONDITIONS)
WPROBES = {"W10": (10, 8), "W15": (15, 13), "W20": (20, 17), "W20s": (20, 18)}

# ── 후보 D 채점 모형(2.3절) ─────────────────────────────────────────────
WLEVEL_TH = [LP.C_WORD - P2.KAPPA_M * (3 - lv) for lv in (1, 2)]
PASS_LW = [(LP._ZD >= th).astype(float) for th in WLEVEL_TH]     # (G, D) 낱말 수준 1·2 숙달
U3 = np.stack([1 - LP.Q_PASS, LP.Q_PASS * (1 - LP.N_PASS), LP.Q_PASS * LP.N_PASS], -1)   # (G, 3) T₃ = 3, 4, 5


def level_matrix3(rs):
    r1, r2 = rs
    return np.clip(np.stack([1 - r1, r1 - r2, r2], -1), 0.0, 1.0)


class BatchD(LP.Batch):
    def post_d(self):
        la, ra = P2._task_multi(self.na, self.ka, LP.LP_A, LP.LQ_A, P2.PASS_L)
        lw, rw = P2._task_multi(self.nw, self.kw, LP.LP_W, LP.LQ_W, PASS_LW)
        w = LP._norm(LP.LOGPRIOR[None] + self.ll + la + lw)
        return w, P2.level_matrix(ra), level_matrix3(rw), la, lw

    def probs_d(self):
        w, V1, V2, _, _ = self.post_d()
        return w @ U3, np.einsum("bg,bgs->bs", w, V1), np.einsum("bg,bgs->bs", w, V2)

    def choose_d(self, gamma, avail):
        w, V1, V2, la, lw = self.post_d()
        E = LP._entropy
        H0 = E(w @ U3) + E(np.einsum("bg,bgs->bs", w, V1)) + E(np.einsum("bg,bgs->bs", w, V2))
        b = w.shape[0]
        names = LP.KIND_OF
        score = np.full((b, len(names)), -np.inf)

        def gain_pmf(pmf):
            wk = w[:, None, :] * pmf[None]                    # (B, K, G)
            pred = wk.sum(-1)
            d = np.maximum(pred[..., None], 1e-300)
            hu = E((wk @ U3) / d)
            h1 = E(np.einsum("bkg,bgs->bks", wk, V1) / d)
            h2 = E(np.einsum("bkg,bgs->bks", wk, V2) / d)
            return H0 - (pred * (hu + h1 + h2)).sum(-1)

        def gain_task(kind):
            out = 0.0
            for ok in (1.0, 0.0):
                if kind == "pa":
                    l2, r2 = P2._task_multi(self.na + 1, self.ka + ok, LP.LP_A, LP.LQ_A, P2.PASS_L)
                    w2 = w * np.exp(l2 - la)
                    A1, A2 = P2.level_matrix(r2), V2
                else:
                    l2, r2 = P2._task_multi(self.nw + 1, self.kw + ok, LP.LP_W, LP.LQ_W, PASS_LW)
                    w2 = w * np.exp(l2 - lw)
                    A1, A2 = V1, level_matrix3(r2)
                pred = w2.sum(-1)
                d = np.maximum(pred[:, None], 1e-300)
                h = E((w2 @ U3) / d) + E(np.einsum("bg,bgs->bs", w2, A1) / d) + E(np.einsum("bg,bgs->bs", w2, A2) / d)
                out = out + pred * h
            return H0 - out

        for ci, name in enumerate(names):
            if name == "pa":
                g = gain_task("pa")
            elif name == "pw":
                g = gain_task("pw")
            elif name == "pq":
                g = gain_pmf(LP._PMF_Q)
            else:
                g = gain_pmf(LP._PMF_N[ci - 3])
            score[:, ci] = np.where(avail[name], g / (LP.COST[name] ** gamma), -np.inf)
        best = score.argmax(-1)
        snr = np.array([LP.SNR_CANDS[i - 3] if i >= 3 else np.nan for i in best])
        return best, snr


def run_chunk_d(rng, L, cfg, gamma, dtab):
    """P2.run_chunk_a와 같은 응답 모형·난수 차례, 문항 고르기만 후보 D 목적."""
    b = len(L["srt"])
    st = BatchD(b)
    used = np.zeros((b, len(LS.POOL)), bool)
    n_sent = np.zeros(b, int)
    elapsed = np.zeros(b)
    active = np.ones(b, bool)
    T = LP.MAX_ITEMS
    pu = np.zeros((b, T + 1, 3))
    p1 = np.zeros((b, T + 1, 4))
    p2 = np.zeros((b, T + 1, 3))
    times = np.zeros((b, T + 1))
    pu[:, 0], p1[:, 0], p2[:, 0] = st.probs_d()
    last = np.zeros(b, int)
    sig = LS.sig
    for t in range(T):
        rem = LP.MAX_SECONDS - elapsed
        avail = {k: (rem >= LP.COST[k]) for k in LP.COST}
        for k in ("pq", "pn"):
            avail[k] = avail[k] & (n_sent < len(LS.POOL))
        any_ok = np.zeros(b, bool)
        for k in avail:
            any_ok |= avail[k]
        active &= any_ok
        idx = np.where(active)[0]
        if not len(idx):
            break
        best, snr = P2._sub(st, idx, BatchD).choose_d(gamma, {k: v[idx] for k, v in avail.items()})
        for name in ("pa", "pw", "pq", "pn"):
            sel = np.array([LP.KIND_OF[i] == name for i in best])
            if not sel.any():
                continue
            ii = idx[sel]
            m = len(ii)
            if name == "pa":
                p = 0.5 + 0.5 * sig(L["za"][ii] + rng.normal(0, cfg["item_sd"], m))
                ok = rng.random(m) < p
                lap = rng.random(m) < cfg["lapse_item"]
                st.add_ax(ii, np.where(lap, rng.random(m) < 0.5, ok))
            elif name == "pw":
                p = 0.25 + 0.75 * sig(L["zw"][ii] + rng.normal(0, cfg["item_sd"], m))
                ok = rng.random(m) < p
                lap = rng.random(m) < cfg["lapse_item"]
                st.add_word(ii, np.where(lap, rng.random(m) < 0.25, ok))
            else:
                r = rng.random((m, len(LS.POOL))) + used[ii] * 10
                j = r.argmin(-1)
                used[ii, j] = True
                vi = n_sent[ii] % 2
                n_sent[ii] += 1
                if name == "pq":
                    zq = L["z"][ii] + rng.normal(0, cfg["sig_q"], m)
                    if cfg["q_pres"]:
                        zq = zq + rng.normal(0, cfg["q_pres"], m)
                    k = rng.binomial(LP.N_WORDS, sig(zq) * (1 - cfg["lapse_word"]))
                    st.add_quiet(ii, k, np.full(m, LP.N_WORDS))
                else:
                    x = snr[sel]
                    d = dtab[j, vi, L["group"][ii]]
                    eps = rng.normal(0, cfg["eps"], m) if cfg["eps"] else 0.0
                    p = sig(4.0 * L["slope"][ii] * (x - L["srt"][ii] - d - eps))
                    k = rng.binomial(LP.N_WORDS, p * (1 - cfg["lapse_word"]))
                    xe = x - np.array([LS.VOFF[LS.VOICES[v]] for v in vi])
                    st.add_noise(ii, xe, k, np.full(m, LP.N_WORDS))
            elapsed[ii] += LP.COST[name]
        pu[idx, t + 1], p1[idx, t + 1], p2[idx, t + 1] = P2._sub(st, idx, BatchD).probs_d()
        times[idx, t + 1] = elapsed[idx]
        last[idx] = t + 1
    return {"pu": pu, "p1": p1, "p2": p2, "times": times, "last": last}


# ── 참 값 ───────────────────────────────────────────────────────────────
def true_up3(L):
    return np.where(L["z"] < LP.C_Q, 3, np.where(L["srt"] > LP.SRT_MASTER, 4, 5))


def true_level2(L, kappa):
    return 1 + sum((L["zw"] >= LP.C_WORD - kappa * (3 - lv)).astype(int) for lv in (1, 2))


# ── 작업 ────────────────────────────────────────────────────────────────
def job(args):
    cand, gamma, cname, seed, n, chunk = args
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    ci = CONDS.index(cname)
    if cand == "C":
        key, L, traj, dt = P2.job(("A", gamma, cname, seed, n, chunk))
        # 낱말 확인 응답(1.1절): 배치 흐름과 다른 난수 [시드, 조건, 8], 사람마다 20문항
        cfg = {**LS.BASE, **LS.CONDITIONS[cname]}
        r2 = np.random.default_rng([seed, ci, 8])
        pw = 0.25 + 0.75 * LS.sig(L["zw"][:, None] + r2.normal(0, cfg["item_sd"], (n, 20)))
        ok_w = r2.random((n, 20)) < pw
        lap = r2.random((n, 20)) < cfg["lapse_item"]
        traj["ok_w"] = np.where(lap, r2.random((n, 20)) < 0.25, ok_w)
        return ("C", gamma, cname, seed), L, traj, dt
    cfg = {**LS.BASE, **LS.CONDITIONS[cname]}
    rng = np.random.default_rng([seed, ci])
    L = LS.make_listeners(rng, n, cfg)
    dtab = LS.delta_table()
    t0 = time.time()
    parts = []
    for a in range(0, n, chunk):
        Lc = {k: v[a:a + chunk] for k, v in L.items()}
        parts.append(run_chunk_d(rng, Lc, cfg, gamma, dtab))
    traj = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    return ("D", gamma, cname, seed), L, traj, time.time() - t0


# ── 평가 ────────────────────────────────────────────────────────────────
def decide_n(probs, rule):
    """(..., S) → 색인 1..S(mode 또는 P(≥ k) ≥ q인 가장 큰 k)."""
    S = probs.shape[-1]
    if rule == "mode":
        return probs.argmax(-1) + 1
    q = float(rule[1:])
    tail = np.cumsum(probs[..., ::-1], -1)[..., ::-1]
    return np.where(tail >= q - 1e-12, np.arange(1, S + 1), 0).max(-1)


def _lev_metrics(lv, tl, nlev):
    return {"agree": float(np.mean(lv == tl)), "over": float(np.mean(lv > tl)), "severe": float(np.mean(lv >= tl + 2)),
            "baseline": float(np.mean(tl == 1)), "placed_dist": [float(np.mean(lv == k)) for k in range(1, nlev + 1)],
            "true_dist": [float(np.mean(tl == k)) for k in range(1, nlev + 1)]}


def _up_metrics(L, up, tu, base_k, kvals):
    return {"agree": float(np.mean(up == tu)), "over": float(np.mean(up > tu)), "severe": float(np.mean(up >= tu + 2)),
            "under": float(np.mean(up < tu)), "baseline": float(np.mean(tu == base_k)), **P2._group_over(L, up, tu),
            "placed_dist": [float(np.mean(up == k)) for k in kvals], "true_dist": [float(np.mean(tu == k)) for k in kvals]}


def place_a(traj, m, s, target, ur, lr):
    pu, pv, times, last = traj["pu"], traj["pv"], traj["times"], traj["last"]
    ok = pu.max(-1) >= s
    if target == "both":
        ok = ok & (pv.max(-1) >= s)
    stop = P2._stop(ok, last, m)
    ar = np.arange(len(last))
    return P2.decide4(pu[ar, stop], ur) + 1, P2.decide4(pv[ar, stop], lr), stop, times[ar, stop]


def eval_c(L, traj, placed, probe):
    up, lv, stop, sec = placed
    tu = P2.true_upper(L)
    final = up.copy()
    psec = np.zeros(len(up))
    nconf = np.zeros(len(up))
    if probe is not None:
        n_, c_ = WPROBES[probe]
        ok, nn = P2._probe(traj["ok_w"], n_, c_)
        do = up >= 3
        psec = np.where(do, nn * LP.COST["pw"], 0.0)
        nconf = np.where(do, nn, 0)
        final = np.where(do & ~ok, 2, up)
    tot = sec + psec
    row = {**_up_metrics(L, final, tu, 2, (2, 3, 4, 5)), "items": float(np.mean(stop)), "sec": float(np.mean(sec)),
           "sec95": float(np.percentile(sec, 95)), "probe_sec": float(np.mean(psec)), "total_sec": float(np.mean(tot)),
           "total_sec95": float(np.percentile(tot, 95)), "probed_share": float(np.mean(up >= 3)),
           "probe_items_if_probed": float(nconf[up >= 3].mean()) if (up >= 3).any() else 0.0,
           "true_mastered_dropped": float(np.mean((final < up) & (up <= tu)))}
    lev = {"base": _lev_metrics(lv, P2.true_level(L, 1.0), 4)}
    for kname, kap in P2.KAPPA_COND.items():
        lev[kname] = _lev_metrics(lv, P2.true_level(L, kap), 4)
    row["level"] = lev["base"]
    return row, {k: v for k, v in lev.items() if k != "base"}


def eval_d(L, traj, m, s, target, ur, lr):
    pu, p1, p2, times, last = traj["pu"], traj["p1"], traj["p2"], traj["times"], traj["last"]
    ok = pu.max(-1) >= s
    if target == "all":
        ok = ok & (p1.max(-1) >= s) & (p2.max(-1) >= s)
    stop = P2._stop(ok, last, m)
    ar = np.arange(len(last))
    up = decide_n(pu[ar, stop], ur) + 2
    l1 = decide_n(p1[ar, stop], lr)
    l2 = decide_n(p2[ar, stop], lr)
    sec = times[ar, stop]
    tu = true_up3(L)
    row = {**_up_metrics(L, up, tu, 3, (3, 4, 5)), "items": float(np.mean(stop)), "sec": float(np.mean(sec)),
           "sec95": float(np.percentile(sec, 95))}
    lev = {}
    for kname, kap in [("base", 1.0)] + list(P2.KAPPA_COND.items()):
        lev[kname] = {"l1": _lev_metrics(l1, P2.true_level(L, kap), 4), "l2": _lev_metrics(l2, true_level2(L, kap), 3)}
    row["level"] = lev["base"]
    # 보고용(4.3절)
    w3 = L["zw"] >= LP.C_WORD
    row["l2_3_of_stage2_mastered"] = float(np.mean(l2[w3] == 3)) if w3.any() else None
    tup2 = P2.true_upper(L) == 2
    row["l2_of_tup2"] = [float(np.mean(l2[tup2] == k)) for k in (1, 2, 3)] if tup2.any() else None
    return row, {k: v for k, v in lev.items() if k != "base"}


def _lev_fails(tag, v, fails):
    if v["severe"] > 0.05:
        fails.append(f"L1 {tag}")
    if v["agree"] < v["baseline"] + 0.20:
        fails.append(f"L2 {tag}")


def judge_c(rows, hrows):
    fails = []
    for c, r in rows.items():
        P2.k_fails(c, r, fails)
        if r["probe_sec"] > 180 or r["total_sec"] > 360:
            fails.append(f"K6 {c}")
        _lev_fails(c, r["level"], fails)
    if np.mean([r["agree"] for r in rows.values()]) < 0.60:
        fails.append("K3b 평균")
    for h, v in hrows.items():
        _lev_fails(h, v, fails)
    return fails


def judge_d(rows, hrows):
    fails = []
    for c, r in rows.items():
        P2.k_fails(c, r, fails)
        for lk in ("l1", "l2"):
            _lev_fails(f"{c}{lk}", r["level"][lk], fails)
    if np.mean([r["agree"] for r in rows.values()]) < 0.60:
        fails.append("K3b 평균")
    for h, v in hrows.items():
        for lk in ("l1", "l2"):
            _lev_fails(f"{h}{lk}", v[lk], fails)
    return fails


def combos_c():
    for name, g, m, s, tg, ur, lr in P2.combos_a():
        for pr in WPROBES:
            yield "C" + name[1:] + f"|{pr}", g, m, s, tg, ur, lr, pr


def combos_d():
    for g in (0, 1):
        for m in LS.STOP_M:
            for s in LS.STOP_S:
                for tg in ("upper", "all"):
                    for ur in ("mode", "q0.6", "q0.7", "q0.8"):
                        for lr in ("mode", "q0.7", "q0.8"):
                            yield f"D|g{g}|m{m}|s{s:.2f}|{tg}|{ur}|{lr}", g, m, s, tg, ur, lr


def evaluate_all(sims, cc, cd):
    out = {}
    cache = {}
    for name, g, m, s, tg, ur, lr, pr in cc:
        rows, hrows = {}, {}
        for c in CONDS:
            L, T = sims[("C", g, c)]
            ck = (g, m, s, tg, ur, lr, c)
            if ck not in cache:
                cache[ck] = place_a(T, m, s, tg, ur, lr)
            rows[c], h = eval_c(L, T, cache[ck], pr)
            if c == "G0":
                hrows = h
        fails = judge_c(rows, hrows)
        out[name] = {"pass": not fails, "fails": fails, "rows": rows, "level_H": hrows,
                     "min_agree": min(r["agree"] for r in rows.values()),
                     "mean_agree": float(np.mean([r["agree"] for r in rows.values()])),
                     "max_severe": max(r["severe"] for r in rows.values()),
                     "min_level_agree": min([r["level"]["agree"] for r in rows.values()] + [v["agree"] for v in hrows.values()]),
                     "mean_time": float(np.mean([r["total_sec"] for r in rows.values()]))}
    for name, g, m, s, tg, ur, lr in cd:
        rows, hrows = {}, {}
        for c in CONDS:
            L, T = sims[("D", g, c)]
            rows[c], h = eval_d(L, T, m, s, tg, ur, lr)
            if c == "G0":
                hrows = h
        fails = judge_d(rows, hrows)
        la = [r["level"][k]["agree"] for r in rows.values() for k in ("l1", "l2")] + [v[k]["agree"] for v in hrows.values() for k in ("l1", "l2")]
        out[name] = {"pass": not fails, "fails": fails, "rows": rows, "level_H": hrows,
                     "min_agree": min(r["agree"] for r in rows.values()),
                     "mean_agree": float(np.mean([r["agree"] for r in rows.values()])),
                     "max_severe": max(r["severe"] for r in rows.values()),
                     "min_level_agree": min(la), "mean_time": float(np.mean([r["sec"] for r in rows.values()]))}
    return out


def pick(res, cand):
    """5절: 통과한 것 가운데 최소 일치 → 최소 수준 일치 → 평균 시간."""
    ok = [(k, v) for k, v in res.items() if k.startswith(cand + "|") and v["pass"]]
    if not ok:
        return None
    ok.sort(key=lambda kv: (-kv[1]["min_agree"], -kv[1]["min_level_agree"], kv[1]["mean_time"]))
    return ok[0][0]


def check_round2(sims, path):
    """1.1절 코드 점검: 시드 0에서 확인을 뺀 C가 2차 A 탐색 결과와 같은지(최대 차)."""
    r2 = json.load(open(path, encoding="utf-8"))["combos"]
    worst = 0.0
    for name, g, m, s, tg, ur, lr in P2.combos_a():
        for c in CONDS:
            L, T = sims[("C", g, c)]
            row, _ = eval_c(L, T, place_a(T, m, s, tg, ur, lr), None)
            ref = r2[name]["rows"][c]
            pairs = [(row[f], ref[f]) for f in ("agree", "over", "severe", "sec")]
            pairs.append((row["level"]["agree"], ref["level"]["agree"] if "level" in ref else ref["level_agree"]))
            worst = max([worst] + [abs(a - b) for a, b in pairs])
    return worst


def _ranked(res, cand):
    ks = [k for k in res if k.startswith(cand + "|")]
    return sorted(ks, key=lambda k: (not res[k]["pass"], len(res[k]["fails"]), -res[k]["min_agree"]))


def _small(v):
    """줄인 지표(6절)."""
    return {"pass": v["pass"], "n_fails": len(v["fails"]), "fails": v["fails"][:8], "min_agree": v["min_agree"],
            "mean_agree": v["mean_agree"], "max_severe": v["max_severe"], "min_level_agree": v["min_level_agree"],
            "mean_time": v["mean_time"],
            "severe": {c: r["severe"] for c, r in v["rows"].items()},
            "probe_sec": {c: r["probe_sec"] for c, r in v["rows"].items()} if "probe_sec" in next(iter(v["rows"].values())) else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["explore", "confirm", "smoke"])
    ap.add_argument("--seeds", type=int, nargs="+", default=[0])
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--chunk", type=int, default=500)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--pick-c", default=None)
    ap.add_argument("--pick-d", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    if a.mode == "confirm":
        cc = [c for c in combos_c() if c[0] == a.pick_c] if a.pick_c else []
        cd = [c for c in combos_d() if c[0] == a.pick_d] if a.pick_d else []
        need = {("C", c[1]) for c in cc} | {("D", c[1]) for c in cd}
    else:
        cc, cd = list(combos_c()), list(combos_d())
        need = {(x, g) for x in "CD" for g in (0, 1)}
    # D 작업이 더 오래 걸려 먼저 낸다
    jobs = [(x, g, c, sd, a.n, a.chunk) for (x, g) in sorted(need, key=lambda t: (t[0] != "D", t[1])) for c in CONDS for sd in a.seeds]
    t0 = time.time()
    results = _run_jobs(jobs, a.workers)
    print(f"시뮬레이션 {time.time() - t0:.0f}s", flush=True)
    sims = P2.pool_seeds(results)
    if a.mode == "smoke":
        res = evaluate_all(sims, cc[:4], cd[:3])
        print("smoke 통과(지표는 기록하지 않음):", len(res), "조합")
        return
    t1 = time.time()
    res = evaluate_all(sims, cc, cd)
    print(f"평가 {time.time() - t1:.0f}s", flush=True)
    picks = {"C": pick(res, "C"), "D": pick(res, "D")}
    keep_full = set(picks.values())
    for cand in "CD":
        keep_full |= set(_ranked(res, cand)[:10])
    out = {"seeds": a.seeds, "n_per_seed": a.n, "prereg": "8614b44e", "kappa_m": P2.KAPPA_M, "wprobes": WPROBES,
           "pick_C": picks["C"], "pick_D": picks["D"],
           "n_pass": {c: sum(v["pass"] for k, v in res.items() if k.startswith(c + "|")) for c in "CD"},
           "combos": {k: (P2._round(v) if k in keep_full else P2._round(_small(v))) for k, v in res.items()},
           "note": "상위 10개·고른 조합만 전체 지표, 나머지는 줄인 지표(같은 코드로 다시 만들 수 있음)"}
    if a.mode == "explore" and a.seeds == [0]:
        out["round2_check_maxdiff"] = check_round2(sims, os.path.join(os.path.dirname(_HERE), "docs", "listen-placement2-explore-seed0.json"))
        print("2차 A 일치 점검 최대 차:", out["round2_check_maxdiff"])
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    for cand in "CD":
        ks = _ranked(res, cand)
        print(f"[{cand}] 통과 {out['n_pass'][cand]}/{len(ks)}, 고른 것 {picks[cand]}")
        for k in ks[:8]:
            v = res[k]
            print(f"  {k:48s} pass={v['pass']} min_agree={v['min_agree']:.3f} mean={v['mean_agree']:.3f} "
                  f"max_severe={v['max_severe']:.4f} t={v['mean_time']:.0f} fails={v['fails'][:6]}")


def _run_jobs(jobs, workers):
    if workers <= 1:
        return [job(j) for j in jobs]
    with get_context("spawn").Pool(workers) as pool:
        out = []
        for r in pool.imap_unordered(job, jobs):
            print(f"  {r[0]} {r[3]:.0f}s", flush=True)
            out.append(r)
        return out


if __name__ == "__main__":
    main()
