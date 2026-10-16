"""소리 듣기 배치검사 2차 가상 청취자 시뮬레이션(docs/listen-placement2-2026-10.md, 사전 등록 a6a02ba4).

후보 A '1단계 안 수준 정하기': 1단계를 건너뛰지 않고 위 단계(2~5)와 1단계 시작 수준(1~4)을 정한다(1절).
후보 B '건너뛴 단계 짧은 확인': 1차 섞은 절차로 배치한 뒤 1단계(와 2단계)를 짧게 확인한다(2절).
청취자·조건·채점 모형은 1차(scripts/listen_placement_sim.py, scripts/listen_placement_model.py)를 그대로 불러 쓴다.

사용:
  python scripts/listen_placement2_sim.py explore --seeds 0 --n 2000 --out docs/listen-placement2-explore-seed0.json --workers 6
  python scripts/listen_placement2_sim.py confirm --seeds 101 102 --n 2000 --pick-a '<A 조합>' --pick-b '<B 조합>' --out ...
"""
import argparse
import json
import math
import os
import sys
import time
from multiprocessing import get_context

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import listen_placement_model as LP  # noqa: E402
import listen_placement_sim as LS  # noqa: E402

# ── 후보 A 채점 모형(1.3절) ─────────────────────────────────────────────
KAPPA_M = 1.0                                     # 채점 모형의 수준 간격(로짓)
LEVEL_TH = [LP.C_AX - KAPPA_M * (4 - lv) for lv in (1, 2, 3)]
PASS_L = [(LP._ZD >= th).astype(float) for th in LEVEL_TH]   # (G, D) 수준 1·2·3 숙달
KAPPA_COND = {"H1": 0.5, "H2": 1.5}              # 수준 기준 전용 조건(G0 흐름에 참 L*만 바꿈)


def _task_multi(n, k, LPm, LQm, passes):
    n = np.asarray(n, float)[:, None, None]
    k = np.asarray(k, float)[:, None, None]
    L = k * LPm[None] + (n - k) * LQm[None]
    m = L.max(-1, keepdims=True)
    e = np.exp(L - m) * LP.PD
    s = e.sum(-1)
    return np.log(s) + m[..., 0], [(e * P[None]).sum(-1) / s for P in passes]


def upper_matrix(pi_w):
    """격자 점마다 위 단계 T_up = 2, 3, 4, 5 확률 (B, G, 4)."""
    q, nn = LP.Q_PASS[None], LP.N_PASS[None]
    return np.stack([1 - pi_w, pi_w * (1 - q), pi_w * q * (1 - nn), pi_w * q * nn], -1)


def level_matrix(rs):
    """r_1 ≥ r_2 ≥ r_3 → L* = 1..4 확률 (B, G, 4)."""
    r1, r2, r3 = rs
    return np.clip(np.stack([1 - r1, r1 - r2, r2 - r3, r3], -1), 0.0, 1.0)


class BatchA(LP.Batch):
    def post_a(self):
        la, ra = _task_multi(self.na, self.ka, LP.LP_A, LP.LQ_A, PASS_L)
        lw, pw = LP._task(self.nw, self.kw, LP.LP_W, LP.LQ_W, LP.PASS_W)
        w = LP._norm(LP.LOGPRIOR[None] + self.ll + la + lw)
        return w, upper_matrix(pw), level_matrix(ra), la, lw

    def probs_a(self):
        w, U, V, _, _ = self.post_a()
        return np.einsum("bg,bgs->bs", w, U), np.einsum("bg,bgs->bs", w, V)

    def choose_a(self, gamma, avail):
        w, U, V, la, lw = self.post_a()
        H0 = LP._entropy(np.einsum("bg,bgs->bs", w, U)) + LP._entropy(np.einsum("bg,bgs->bs", w, V))
        b = w.shape[0]
        names = LP.KIND_OF
        score = np.full((b, len(names)), -np.inf)

        def gain_pmf(pmf):
            uU = np.einsum("bg,kg,bgs->bks", w, pmf, U)
            uV = np.einsum("bg,kg,bgs->bks", w, pmf, V)
            pred = uU.sum(-1)
            d = np.maximum(pred[..., None], 1e-300)
            return H0 - (pred * (LP._entropy(uU / d) + LP._entropy(uV / d))).sum(-1)

        def gain_task(kind):
            out = 0.0
            for ok in (1.0, 0.0):
                if kind == "pa":
                    l2, r2 = _task_multi(self.na + 1, self.ka + ok, LP.LP_A, LP.LQ_A, PASS_L)
                    w2 = w * np.exp(l2 - la)
                    U2, V2 = U, level_matrix(r2)
                else:
                    l2, p2 = LP._task(self.nw + 1, self.kw + ok, LP.LP_W, LP.LQ_W, LP.PASS_W)
                    w2 = w * np.exp(l2 - lw)
                    U2, V2 = upper_matrix(p2), V
                pred = w2.sum(-1)
                d = np.maximum(pred[:, None], 1e-300)
                pu = np.einsum("bg,bgs->bs", w2, U2) / d
                pv = np.einsum("bg,bgs->bs", w2, V2) / d
                out = out + pred * (LP._entropy(pu) + LP._entropy(pv))
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


def _sub(st, idx, cls):
    s = cls(len(idx))
    s.ll, s.na, s.ka, s.nw, s.kw = st.ll[idx], st.na[idx], st.ka[idx], st.nw[idx], st.kw[idx]
    return s


def run_chunk_a(rng, L, cfg, gamma, dtab):
    """LS.run_chunk와 같은 응답 모형, 문항 고르기만 후보 A 목적(위 단계 + 수준 엔트로피)."""
    b = len(L["srt"])
    st = BatchA(b)
    used = np.zeros((b, len(LS.POOL)), bool)
    n_sent = np.zeros(b, int)
    elapsed = np.zeros(b)
    active = np.ones(b, bool)
    T = LP.MAX_ITEMS
    pu = np.zeros((b, T + 1, 4))
    pv = np.zeros((b, T + 1, 4))
    times = np.zeros((b, T + 1))
    pu[:, 0], pv[:, 0] = st.probs_a()
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
        best, snr = _sub(st, idx, BatchA).choose_a(gamma, {k: v[idx] for k, v in avail.items()})
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
        pu[idx, t + 1], pv[idx, t + 1] = _sub(st, idx, BatchA).probs_a()
        times[idx, t + 1] = elapsed[idx]
        last[idx] = t + 1
    return {"pu": pu, "pv": pv, "times": times, "last": last}


# ── 참 값 ───────────────────────────────────────────────────────────────
def true_upper(L):
    return np.where(L["zw"] < LP.C_WORD, 2, np.where(L["z"] < LP.C_Q, 3, np.where(L["srt"] > LP.SRT_MASTER, 4, 5)))


def true_level(L, kappa):
    n = sum((L["za"] >= LP.C_AX - kappa * (4 - lv)).astype(int) for lv in (1, 2, 3))
    return 1 + n


# ── 작업(조건 하나 × 절차 하나 × 시드 하나) ──────────────────────────────
def job(args):
    cand, gamma, cname, seed, n, chunk = args
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    cfg = {**LS.BASE, **LS.CONDITIONS[cname]}
    rng = np.random.default_rng([seed, list(LS.CONDITIONS).index(cname)])
    L = LS.make_listeners(rng, n, cfg)
    dtab = LS.delta_table()
    t0 = time.time()
    parts = []
    proc = {"gamma": gamma, "allowed": ("pa", "pw", "pq", "pn")}
    for a in range(0, n, chunk):
        Lc = {k: v[a:a + chunk] for k, v in L.items()}
        parts.append(run_chunk_a(rng, Lc, cfg, gamma, dtab) if cand == "A" else LS.run_chunk(rng, Lc, cfg, proc, dtab))
    traj = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    if cand == "B":
        # 확인 문항 응답(2.1절): 배치 흐름과 다른 난수, 사람마다 소리 구별 20개·낱말 20개를 미리 뽑고 변형마다 앞에서부터 쓴다
        r2 = np.random.default_rng([seed, list(LS.CONDITIONS).index(cname), 7])
        pa = 0.5 + 0.5 * LS.sig(L["za"][:, None] + r2.normal(0, cfg["item_sd"], (n, 20)))
        ok_a = r2.random((n, 20)) < pa
        lap = r2.random((n, 20)) < cfg["lapse_item"]
        ok_a = np.where(lap, r2.random((n, 20)) < 0.5, ok_a)
        pw = 0.25 + 0.75 * LS.sig(L["zw"][:, None] + r2.normal(0, cfg["item_sd"], (n, 20)))
        ok_w = r2.random((n, 20)) < pw
        lap = r2.random((n, 20)) < cfg["lapse_item"]
        ok_w = np.where(lap, r2.random((n, 20)) < 0.25, ok_w)
        traj["ok_a"], traj["ok_w"] = ok_a, ok_w
        traj.pop("kinds", None)
    return (cand, gamma, cname, seed), L, traj, time.time() - t0


def run_jobs(jobs, workers):
    if workers <= 1:
        return [job(j) for j in jobs]
    with get_context("spawn").Pool(workers) as pool:
        out = []
        for r in pool.imap_unordered(job, jobs):
            print(f"  {r[0]} {r[3]:.0f}s", flush=True)
            out.append(r)
        return out


def pool_seeds(results):
    """(후보, γ, 조건) → 시드를 이어 붙인 (L, traj)."""
    grp = {}
    for key, L, traj, _ in sorted(results, key=lambda r: r[0][3]):
        grp.setdefault(key[:3], []).append((L, traj))
    out = {}
    for k, lst in grp.items():
        L = {f: np.concatenate([x[0][f] for x in lst]) for f in lst[0][0]}
        T = {f: np.concatenate([x[1][f] for x in lst]) for f in lst[0][1]}
        out[k] = (L, T)
    return out


# ── 평가 ────────────────────────────────────────────────────────────────
def decide4(probs, rule):
    """(..., 4) → 색인 1..4(mode 또는 P(≥ k) ≥ q인 가장 큰 k)."""
    if rule == "mode":
        return probs.argmax(-1) + 1
    q = float(rule[1:])
    tail = np.cumsum(probs[..., ::-1], -1)[..., ::-1]
    return np.where(tail >= q - 1e-12, np.arange(1, 5), 0).max(-1)


def _stop(maxp_ok, last, m):
    tt = np.arange(maxp_ok.shape[1])[None, :]
    hit = maxp_ok & (tt >= m) & (tt <= last[:, None])
    return np.where(hit.any(-1), hit.argmax(-1), last)


def _group_over(L, placed, true):
    return {f"over_{g}": float(np.mean(placed[L["group"] == gi] > true[L["group"] == gi])) for gi, g in enumerate(("NH", "HA", "CI"))}


def eval_a(L, traj, m, s, target, ur, lr):
    pu, pv, times, last = traj["pu"], traj["pv"], traj["times"], traj["last"]
    ok = pu.max(-1) >= s
    if target == "both":
        ok = ok & (pv.max(-1) >= s)
    stop = _stop(ok, last, m)
    ar = np.arange(len(last))
    up = decide4(pu[ar, stop], ur) + 1
    lv = decide4(pv[ar, stop], lr)
    tu = true_upper(L)
    sec = times[ar, stop]
    row = {"agree": float(np.mean(up == tu)), "over": float(np.mean(up > tu)), "severe": float(np.mean(up >= tu + 2)),
           "under": float(np.mean(up < tu)), "baseline": float(np.mean(tu == 2)), "items": float(np.mean(stop)),
           "sec": float(np.mean(sec)), "sec95": float(np.percentile(sec, 95)), **_group_over(L, up, tu),
           "placed_dist": [float(np.mean(up == k)) for k in (2, 3, 4, 5)], "true_dist": [float(np.mean(tu == k)) for k in (2, 3, 4, 5)]}
    lev = {}
    for kname, kap in [("base", 1.0)] + list(KAPPA_COND.items()):
        tl = true_level(L, kap)
        lev[kname] = {"agree": float(np.mean(lv == tl)), "over": float(np.mean(lv > tl)), "severe": float(np.mean(lv >= tl + 2)),
                      "baseline": float(np.mean(tl == 1)), "placed_dist": [float(np.mean(lv == k)) for k in (1, 2, 3, 4)],
                      "true_dist": [float(np.mean(tl == k)) for k in (1, 2, 3, 4)]}
    row["level"] = lev["base"]
    # 보고용(4.3절): 1차 참 1단계(소리 구별 수준 4 미숙달) 학습자의 수준 배치, 1단계 숙달자의 수준 4 출발 비율
    t1 = L["true"] == 1
    row["r1_level_of_true1"] = [float(np.mean(lv[t1] == k)) for k in (1, 2, 3, 4)] if t1.any() else None
    mast = L["za"] >= LP.C_AX
    row["lv4_of_stage1_mastered"] = float(np.mean(lv[mast] == 4)) if mast.any() else None
    return row, {k: v for k, v in lev.items() if k != "base"}


PROBES = {"P10": ((10, 9), (10, 8)), "P15": ((15, 14), (15, 13)), "P20": ((20, 18), (20, 17)), "P20s": ((20, 19), (20, 18))}
PSETS = ("1", "12")


def _probe(ok, n, c):
    """확인 n문항 중 c개 이상이면 통과, 결과가 정해지는 순간 멈춤. → (통과 (B,), 낸 문항 수 (B,))."""
    o = ok[:, :n].astype(int)
    cc = np.cumsum(o, 1)
    ce = np.cumsum(1 - o, 1)
    done_pass = cc >= c
    done_fail = ce > n - c
    done = done_pass | done_fail
    first = done.argmax(1)
    passed = done_pass[np.arange(len(o)), first]
    return passed, first + 1


def eval_b(L, traj, m, s, rule, probe, pset):
    probs, times, last = traj["probs"], traj["times"], traj["last"]
    stop = _stop(probs.max(-1) >= s, last, m)
    ar = np.arange(len(last))
    placed = LP.decide(probs[ar, stop], rule)
    sec_p = times[ar, stop]
    true = L["true"]
    final = placed.copy()
    psec = np.zeros(len(placed))
    if probe is not None:
        (na, ca), (nw, cw) = PROBES[probe]
        pa_ok, pa_n = _probe(traj["ok_a"], na, ca)
        do1 = placed >= 2
        psec += np.where(do1, pa_n * LP.COST["pa"], 0)
        final = np.where(do1 & ~pa_ok, 1, final)
        if pset == "12":
            pw_ok, pw_n = _probe(traj["ok_w"], nw, cw)
            do2 = (placed >= 3) & pa_ok
            psec += np.where(do2, pw_n * LP.COST["pw"], 0)
            final = np.where(do2 & ~pw_ok, 2, final)
    tot = sec_p + psec
    row = {"agree": float(np.mean(final == true)), "over": float(np.mean(final > true)), "severe": float(np.mean(final >= true + 2)),
           "under": float(np.mean(final < true)), "baseline": float(np.mean(true == 1)), "items": float(np.mean(stop)),
           "sec": float(np.mean(sec_p)), "sec95": float(np.percentile(sec_p, 95)), "probe_sec": float(np.mean(psec)),
           "total_sec": float(np.mean(tot)), "total_sec95": float(np.percentile(tot, 95)), **_group_over(L, final, true),
           "placed_dist": [float(np.mean(final == k)) for k in range(1, 6)],
           "true_mastered_dropped": float(np.mean((final < placed) & (placed <= true)))}
    return row


def k_fails(c, r, fails):
    if r["over"] > 0.10:
        fails.append(f"K1 {c}")
    if r["severe"] > 0.02:
        fails.append(f"K2 {c}")
    if r["agree"] < r["baseline"] + 0.20:
        fails.append(f"K3a {c}")
    if r["items"] > 12 or r["sec"] > 240 or r["sec95"] > 300:
        fails.append(f"K4 {c}")
    if max(r["over_NH"], r["over_HA"], r["over_CI"]) > 0.15:
        fails.append(f"K5 {c}")


def judge_a(rows, hrows):
    fails = []
    for c, r in rows.items():
        k_fails(c, r, fails)
    if np.mean([r["agree"] for r in rows.values()]) < 0.60:
        fails.append("K3b 평균")
    levs = {c: r["level"] for c, r in rows.items()}
    levs.update(hrows)
    for c, v in levs.items():
        if v["severe"] > 0.05:
            fails.append(f"L1 {c}")
        if v["agree"] < v["baseline"] + 0.20:
            fails.append(f"L2 {c}")
    return fails


def judge_b(rows):
    fails = []
    for c, r in rows.items():
        k_fails(c, r, fails)
        if r["probe_sec"] > 180 or r["total_sec"] > 360:
            fails.append(f"K6 {c}")
    if np.mean([r["agree"] for r in rows.values()]) < 0.60:
        fails.append("K3b 평균")
    return fails


def combos_a():
    for g in (0, 1):
        for m in LS.STOP_M:
            for s in LS.STOP_S:
                for tg in ("upper", "both"):
                    for ur in ("mode", "q0.6", "q0.7", "q0.8"):
                        for lr in ("mode", "q0.7", "q0.8"):
                            yield f"A|g{g}|m{m}|s{s:.2f}|{tg}|{ur}|{lr}", g, m, s, tg, ur, lr


def combos_b():
    for g in (0, 1):
        for m in LS.STOP_M:
            for s in LS.STOP_S:
                for r in LS.RULES:
                    for pr in PROBES:
                        for ps in PSETS:
                            yield f"B|g{g}|m{m}|s{s:.2f}|{r}|{pr}|{ps}", g, m, s, r, pr, ps


def _round(x):
    if isinstance(x, float):
        return round(x, 5)
    if isinstance(x, dict):
        return {k: _round(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_round(v) for v in x]
    return x


def evaluate_all(sims, ca, cb):
    out = {}
    for name, g, m, s, tg, ur, lr in ca:
        rows, hrows = {}, {}
        for c in LS.CONDITIONS:
            L, T = sims[("A", g, c)]
            rows[c], h = eval_a(L, T, m, s, tg, ur, lr)
            if c == "G0":
                hrows = h
        fails = judge_a(rows, hrows)
        out[name] = {"pass": not fails, "fails": fails, "rows": rows, "level_H": hrows,
                     "min_agree": min(r["agree"] for r in rows.values()),
                     "mean_agree": float(np.mean([r["agree"] for r in rows.values()])),
                     "min_level_agree": min([r["level"]["agree"] for r in rows.values()] + [v["agree"] for v in hrows.values()]),
                     "mean_sec": float(np.mean([r["sec"] for r in rows.values()]))}
    for name, g, m, s, r, pr, ps in cb:
        rows = {}
        for c in LS.CONDITIONS:
            L, T = sims[("B", g, c)]
            rows[c] = eval_b(L, T, m, s, r, pr, ps)
        fails = judge_b(rows)
        out[name] = {"pass": not fails, "fails": fails, "rows": rows,
                     "min_agree": min(x["agree"] for x in rows.values()),
                     "mean_agree": float(np.mean([x["agree"] for x in rows.values()])),
                     "mean_total_sec": float(np.mean([x["total_sec"] for x in rows.values()]))}
    return out


def pick(res, cand):
    ok = [(k, v) for k, v in res.items() if k.startswith(cand + "|") and v["pass"]]
    if not ok:
        return None
    if cand == "A":
        ok.sort(key=lambda kv: (-kv[1]["min_agree"], -kv[1]["min_level_agree"], kv[1]["mean_sec"]))
    else:
        ok.sort(key=lambda kv: (-kv[1]["min_agree"], kv[1]["mean_total_sec"]))
    return ok[0][0]


def check_round1(sims, path):
    """2.1절 코드 점검: 시드 0에서 확인을 뺀 B가 1차 탐색 결과와 같은지."""
    r1 = json.load(open(path, encoding="utf-8"))["combos"]
    worst = 0.0
    for g, p in ((0, "mix_g0"), (1, "mix_g1")):
        for m in LS.STOP_M:
            for s in LS.STOP_S:
                for r in LS.RULES:
                    for c in LS.CONDITIONS:
                        L, T = sims[("B", g, c)]
                        row = eval_b(L, T, m, s, r, None, None)
                        ref = r1[f"{p}|m{m}|s{s:.2f}|{r}"]["rows"][c]
                        for f in ("agree", "over", "severe", "sec"):
                            worst = max(worst, abs(row[f] - ref[f]))
    return worst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["explore", "confirm", "smoke"])
    ap.add_argument("--seeds", type=int, nargs="+", default=[0])
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--chunk", type=int, default=500)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--pick-a", default=None)
    ap.add_argument("--pick-b", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    if a.mode == "confirm":
        ca = [c for c in combos_a() if c[0] == a.pick_a] if a.pick_a else []
        cb = [c for c in combos_b() if c[0] == a.pick_b] if a.pick_b else []
        need = {("A", c[1]) for c in ca} | {("B", c[1]) for c in cb}
    else:
        ca, cb = list(combos_a()), list(combos_b())
        need = {(x, g) for x in "AB" for g in (0, 1)}
    jobs = [(x, g, c, sd, a.n, a.chunk) for (x, g) in sorted(need) for c in LS.CONDITIONS for sd in a.seeds]
    t0 = time.time()
    results = run_jobs(jobs, a.workers)
    print(f"시뮬레이션 {time.time() - t0:.0f}s", flush=True)
    sims = pool_seeds(results)
    if a.mode == "smoke":
        res = evaluate_all(sims, ca[:3], cb[:3])
        print("smoke 통과(지표는 기록하지 않음):", len(res), "조합")
        return
    res = evaluate_all(sims, ca, cb)
    out = {"seeds": a.seeds, "n_per_seed": a.n, "prereg": "a6a02ba4", "kappa_m": KAPPA_M, "probes": PROBES,
           "pick_A": pick(res, "A"), "pick_B": pick(res, "B"), "combos": _round(res)}
    if a.mode == "explore" and a.seeds == [0]:
        out["round1_check_maxdiff"] = check_round1(sims, os.path.join(os.path.dirname(_HERE), "docs", "listen-placement-explore-seed0.json"))
        print("1차 일치 점검 최대 차:", out["round1_check_maxdiff"])
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    for cand in "AB":
        ks = [k for k in res if k.startswith(cand + "|")]
        n_pass = sum(res[k]["pass"] for k in ks)
        ranked = sorted(ks, key=lambda k: (not res[k]["pass"], -res[k]["min_agree"]))
        print(f"[{cand}] 통과 {n_pass}/{len(ks)}, 고른 것 {out['pick_' + cand]}")
        for k in ranked[:8]:
            v = res[k]
            worst = max(v["rows"].values(), key=lambda r: r["severe"])
            print(f"  {k:44s} pass={v['pass']} min_agree={v['min_agree']:.3f} mean={v['mean_agree']:.3f} "
                  f"max_severe={worst['severe']:.3f} fails={v['fails'][:5]}")


if __name__ == "__main__":
    main()
