"""소리 듣기 배치검사 가상 청취자 시뮬레이션(docs/listen-placement-2026-10.md).

청취자는 기존 소음 속 듣기 시뮬레이션(scripts/listen_adaptive_sim.py 2.1~2.3절)과 같은 집단·SRT·기울기를 갖고, 조용한 곳 능력 z와
과제별 편차(소리 구별 d_a, 낱말 d_w)를 연결 가정(3.2절)으로 더한다. 소음 속 문장의 난이도는 V1(docs/listen-virtual-listener-2026-10.json)의
배치검사 문장 풀 SRT40이다. 채점은 앱과 같은 backend/listen_placement.py다.

사용:
  python scripts/listen_placement_sim.py explore --seed 0 --n 2000 --out docs/listen-placement-explore-seed0.json
  python scripts/listen_placement_sim.py confirm --seed 1 --n 4000 --pick '<조합 이름>' --out docs/listen-placement-confirm-seed1.json
"""
import argparse
import json
import os
import sys
import time

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "backend"))
import listen_placement as LP  # noqa: E402

# 4.2절 풀(V1 번호)과 목소리 보정(사전 등록 값)
POOL = ["t002", "t003", "t004", "t009", "t011", "t012", "t014", "t023", "t029", "t042", "t076", "t087", "t092"]
VOICES = ["m1", "f1"]
VOFF = {"m1": -2.35, "f1": -1.18}
SIMS = ["nh", "ha", "ci"]        # 집단 0 NH → 정상 모의, 1 HA → 보청기 모의, 2 CI → 인공와우 모의

BASE = {"a0": 3.9, "b": 0.175, "sig_u": 0.7, "tau": 0.7, "delta": 0.0, "sig_q": 0.5, "eps": 0.0, "q_pres": 0.0,
        "item_sd": 0.5, "lapse_item": 0.0, "lapse_word": 0.0, "slope_fixed": None}
CONDITIONS = {
    "G0": {},
    "G1": {"eps": 2.0, "q_pres": 0.5},
    "G2": {"eps": 4.0, "q_pres": 1.0},
    "G3": {"sig_u": 1.2, "tau": 1.2},
    "G4": {"delta": -1.0},
    "G5": {"delta": 1.0},
    "G6": {"b": 0.125, "a0": 3.3},
    "G7": {"b": 0.225, "a0": 4.5},
    "G8": {"lapse_item": 0.05, "lapse_word": 0.03, "slope_fixed": 0.09},
}
PROCS = {"mix_g0": {"gamma": 0.0, "allowed": ("pa", "pw", "pq", "pn")},
         "mix_g1": {"gamma": 1.0, "allowed": ("pa", "pw", "pq", "pn")},
         "sent_only": {"gamma": 1.0, "allowed": ("pn",)}}
STOP_M = (2, 4)
STOP_S = (0.80, 0.85, 0.90, 0.95)
RULES = ("mode", "q0.6", "q0.7", "q0.8")


def delta_table():
    """(문장 13, 목소리 2, 모의 3) V1 SRT40 − 그 모의의 풀·네 훈련 목소리 평균."""
    fits = json.load(open(os.path.join(_ROOT, "docs", "listen-virtual-listener-2026-10.json"), encoding="utf-8"))["fits"]
    F = {(f["sid"], f["voice"], f["listener"]): f["srt40"] for f in fits if f["noise"] == "babble" and str(f["reps"]) == "0"}
    out = np.zeros((len(POOL), len(VOICES), len(SIMS)))
    for gi, g in enumerate(SIMS):
        allm = np.mean([F[(s, v, g)] for s in POOL for v in ("m1", "f1", "m2", "f2")])
        for si, s in enumerate(POOL):
            for vi, v in enumerate(VOICES):
                out[si, vi, gi] = F[(s, v, g)] - allm
    return out


def make_listeners(rng, n, cfg):
    g = rng.choice(3, size=n, p=[0.2, 0.4, 0.4])
    srt = np.where(g == 0, rng.normal(-4.0, 1.0, n), np.where(g == 1, rng.uniform(-1.0, 8.0, n), rng.uniform(2.0, 22.0, n)))
    slope = np.clip(0.16 - 0.004 * (srt + 4.0) + rng.normal(0.0, 0.015, n), 0.05, 0.20)
    if cfg["slope_fixed"]:
        slope = np.full(n, float(cfg["slope_fixed"]))
    z = cfg["a0"] - cfg["b"] * srt + rng.normal(0.0, cfg["sig_u"], n)
    za = z - cfg["delta"] + rng.normal(0.0, cfg["tau"], n)
    zw = z - cfg["delta"] + rng.normal(0.0, cfg["tau"], n)
    true = np.where(za < LP.C_AX, 1, np.where(zw < LP.C_WORD, 2, np.where(z < LP.C_Q, 3, np.where(srt > LP.SRT_MASTER, 4, 5))))
    return {"group": g, "srt": srt, "slope": slope, "z": z, "za": za, "zw": zw, "true": true}


def sig(x):
    return 1.0 / (1.0 + np.exp(-x))


def run_chunk(rng, L, cfg, proc, dtab):
    b = len(L["srt"])
    st = LP.Batch(b)
    used = np.zeros((b, len(POOL)), bool)
    n_sent = np.zeros(b, int)
    elapsed = np.zeros(b)
    active = np.ones(b, bool)
    T = LP.MAX_ITEMS
    probs = np.zeros((b, T + 1, 5))
    times = np.zeros((b, T + 1))
    kinds = np.full((b, T), -1)
    probs[:, 0] = st.stage_probs()
    last = np.zeros(b, int)
    for t in range(T):
        rem = LP.MAX_SECONDS - elapsed
        avail = {k: (rem >= LP.COST[k]) for k in LP.COST}
        for k in ("pq", "pn"):
            avail[k] = avail[k] & (n_sent < len(POOL))
        any_ok = np.zeros(b, bool)
        for k in proc["allowed"]:
            any_ok |= avail[k]
        active &= any_ok
        idx = np.where(active)[0]
        if not len(idx):
            break
        sub = LP.Batch(len(idx))
        sub.ll, sub.na, sub.ka, sub.nw, sub.kw = st.ll[idx], st.na[idx], st.ka[idx], st.nw[idx], st.kw[idx]
        best, snr, _ = sub.choose(proc["gamma"], proc["allowed"], {k: v[idx] for k, v in avail.items()})
        kinds[idx, t] = best
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
                ok = np.where(lap, rng.random(m) < 0.5, ok)
                st.add_ax(ii, ok)
            elif name == "pw":
                p = 0.25 + 0.75 * sig(L["zw"][ii] + rng.normal(0, cfg["item_sd"], m))
                ok = rng.random(m) < p
                lap = rng.random(m) < cfg["lapse_item"]
                ok = np.where(lap, rng.random(m) < 0.25, ok)
                st.add_word(ii, ok)
            else:
                # 쓰지 않은 풀 문장 하나(무작위), 목소리는 문장 문항마다 m1·f1 번갈아
                r = rng.random((m, len(POOL))) + used[ii] * 10
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
                    xe = x - np.array([VOFF[VOICES[v]] for v in vi])
                    st.add_noise(ii, xe, k, np.full(m, LP.N_WORDS))
            elapsed[ii] += LP.COST[name]
        sub_p = LP.Batch(len(idx))
        sub_p.ll, sub_p.na, sub_p.ka, sub_p.nw, sub_p.kw = st.ll[idx], st.na[idx], st.ka[idx], st.nw[idx], st.kw[idx]
        probs[idx, t + 1] = sub_p.stage_probs()
        times[idx, t + 1] = elapsed[idx]
        last[idx] = t + 1
    return {"probs": probs, "times": times, "last": last, "kinds": kinds}


def evaluate(L, traj, m, s, rule):
    probs, times, last = traj["probs"], traj["times"], traj["last"]
    b = len(last)
    tt = np.arange(probs.shape[1])[None, :]
    hit = (probs.max(-1) >= s) & (tt >= m) & (tt <= last[:, None])
    stop = np.where(hit.any(-1), hit.argmax(-1), last)
    p = probs[np.arange(b), stop]
    placed = LP.decide(p, rule)
    true = L["true"]
    sec = times[np.arange(b), stop]
    out = {"agree": float(np.mean(placed == true)), "over": float(np.mean(placed > true)),
           "severe": float(np.mean(placed >= true + 2)), "under": float(np.mean(placed < true)),
           "items": float(np.mean(stop)), "sec": float(np.mean(sec)), "sec95": float(np.percentile(sec, 95)),
           "baseline": float(np.mean(true == 1))}
    for gi, gname in enumerate(("NH", "HA", "CI")):
        mk = L["group"] == gi
        out[f"over_{gname}"] = float(np.mean(placed[mk] > true[mk]))
        out[f"agree_{gname}"] = float(np.mean(placed[mk] == true[mk]))
    out["placed_dist"] = [float(np.mean(placed == k)) for k in range(1, 6)]
    out["true_dist"] = [float(np.mean(true == k)) for k in range(1, 6)]
    return out


def passes(rows):
    """조건별 지표 {조건: 지표} → (통과 여부, 실패한 기준 목록). 6.2절 K1~K5."""
    fails = []
    for c, r in rows.items():
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
    if np.mean([r["agree"] for r in rows.values()]) < 0.60:
        fails.append("K3b 평균")
    return not fails, fails


def simulate(seed, n, procs, chunk=500):
    dtab = delta_table()
    res = {}
    for pname in procs:
        proc = PROCS[pname]
        for cname, over in CONDITIONS.items():
            cfg = {**BASE, **over}
            rng = np.random.default_rng([seed, list(CONDITIONS).index(cname)])
            L = make_listeners(rng, n, cfg)
            t0 = time.time()
            parts = []
            for a in range(0, n, chunk):
                Lc = {k: v[a:a + chunk] for k, v in L.items()}
                parts.append(run_chunk(rng, Lc, cfg, proc, dtab))
            traj = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
            res[(pname, cname)] = (L, traj)
            print(f"  {pname} {cname} {time.time() - t0:.0f}s", flush=True)
    return res


def kind_share(traj, stop):
    kinds = traj["kinds"]
    cnt = {"pa": 0, "pw": 0, "pq": 0, "pn": 0}
    for row, s in zip(kinds, stop):
        for i in row[:s]:
            if i >= 0:
                cnt[LP.KIND_OF[i]] += 1
    return {k: round(v / len(kinds), 3) for k, v in cnt.items()}


def combos(procs):
    for p in procs:
        for m in STOP_M:
            for s in STOP_S:
                for r in RULES:
                    yield f"{p}|m{m}|s{s:.2f}|{r}", p, m, s, r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["explore", "confirm"])
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--pick", default=None)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.mode == "explore":
        procs = list(PROCS)
        todo = list(combos(procs))
    else:
        p, m, s, r = a.pick.split("|")
        procs = [p]
        todo = [(a.pick, p, int(m[1:]), float(s[1:]), r)]
    sims = simulate(a.seed, a.n, procs)
    out = {"seed": a.seed, "n": a.n, "conditions": CONDITIONS, "base": BASE, "voff": VOFF, "pool": POOL, "combos": {}}
    for name, p, m, s, r in todo:
        rows = {}
        for c in CONDITIONS:
            L, traj = sims[(p, c)]
            rows[c] = evaluate(L, traj, m, s, r)
        ok, fails = passes(rows)
        out["combos"][name] = {"pass": ok, "fails": fails, "rows": rows,
                               "min_agree": min(x["agree"] for x in rows.values()),
                               "mean_agree": float(np.mean([x["agree"] for x in rows.values()])),
                               "mean_sec": float(np.mean([x["sec"] for x in rows.values()]))}
    # 문항 종류 비율(조합마다 멈춘 지점까지, 조건 G0)
    for name, p, m, s, r in todo:
        L, traj = sims[(p, "G0")]
        probs, last = traj["probs"], traj["last"]
        tt = np.arange(probs.shape[1])[None, :]
        hit = (probs.max(-1) >= s) & (tt >= m) & (tt <= last[:, None])
        stop = np.where(hit.any(-1), hit.argmax(-1), last)
        out["combos"][name]["kinds_G0"] = kind_share(traj, stop)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    ranked = sorted(out["combos"].items(), key=lambda kv: (not kv[1]["pass"], -kv[1]["min_agree"], kv[1]["mean_sec"]))
    for name, v in ranked[:15]:
        worst = max(v["rows"].values(), key=lambda r: r["over"])
        print(f"{name:32s} pass={v['pass']} min_agree={v['min_agree']:.3f} mean={v['mean_agree']:.3f} "
              f"sec={v['mean_sec']:.0f} max_over={worst['over']:.3f} fails={v['fails'][:4]}")


if __name__ == "__main__":
    main()
