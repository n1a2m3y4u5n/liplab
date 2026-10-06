"""말하기 채점 분석 묶음(docs/scoring-analyses-2026-10.md): 재현 확인, S19, S15, S1, S14.

문장별 CSV(liplab-lab/data/scores_2026-10-06/, 저장소 밖)를 읽는다. 저장소에는 이 스크립트와 집계만 둔다.
    python scripts/scoring_analyses_1006.py verify
    python scripts/scoring_analyses_1006.py s19
    python scripts/scoring_analyses_1006.py s15 explore|confirm     (explore가 절반 0에서 정한 값을 params에 쓰고, confirm은 그것만 읽는다)
    python scripts/scoring_analyses_1006.py s1 explore|confirm
    python scripts/scoring_analyses_1006.py s14
화자 절반: crc32(화자) % 2. 절반 0 탐색, 절반 1 확인. 합격선 65(보정 점수).
"""
import csv
import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

D = os.environ.get("SCORES_DIR", os.path.expanduser("~/Downloads/liplab-lab/data/scores_2026-10-06"))
PASS = 65.0


def _np(o):
    """numpy 값(bool_·float64 등)을 JSON으로."""
    return o.item() if hasattr(o, "item") else str(o)


def load(name):
    with open(os.path.join(D, name), newline="") as f:
        return list(csv.DictReader(f))


def auc(pos, neg):
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    if not len(pos) or not len(neg):
        return float("nan")
    allv = np.concatenate([pos, neg])
    order = allv.argsort(kind="mergesort")
    ranks = np.empty(len(allv))
    sv = allv[order]
    i = 0
    while i < len(sv):
        j = i
        while j < len(sv) and sv[j] == sv[i]:
            j += 1
        ranks[order[i:j]] = (i + j - 1) / 2 + 1
        i = j
    return (ranks[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def ff(own, thr):
    own = np.asarray(own, float)
    return float((own < thr).mean()) if len(own) else float("nan")


def wp(oth, thr):
    oth = np.asarray(oth, float)
    return float((oth >= thr).mean()) if len(oth) else float("nan")


def pct(x):
    return f"{100 * x:.1f}%"


def joined():
    """D-GOP 짝과 같은 짝의 전사 점수를 합친 행(538·608·잡음, own/other/cohort/noise)."""
    tr = {(r["set"], r["clip"], r["target_sid"], r["label"]): r for r in load("transcript_pairs.csv")}
    rows = []
    for r in load("dgop_pairs.csv"):
        if r["score"] in ("", "None"):
            continue
        t = tr.get((r["set"], r["clip"], r["target_sid"], r["label"]))
        rows.append({"set": r["set"], "spk": r["spk"], "half": int(r["half"]) if r["half"] != "" else None,
                     "clip": r["clip"], "label": r["label"], "dg": float(r["score"]),
                     "r0": float(t["r0"]) if t else None, "r0c": float(t["r0_c"]) if t else None})
    return rows


def sel(rows, st=None, label=None, half=None):
    return [r for r in rows if (st is None or r["set"] == st) and (label is None or r["label"] == label)
            and (half is None or r["half"] == half)]


# ───────────────────────── 재현 확인 ─────────────────────────
def verify():
    rows = joined()
    out = {}
    for st in ("538", "608"):
        for h in (None, 0, 1):
            own, oth = sel(rows, st, "own", h), sel(rows, st, "other", h)
            key = f"{st}_{'all' if h is None else h}"
            out[key] = {"clips": len({r["clip"] for r in own}), "spk": len({r["spk"] for r in own}), "n_other": len(oth),
                        "auc_dgop": round(auc([r["dg"] for r in own], [r["dg"] for r in oth]), 4),
                        "ff65_dgop": round(ff([r["dg"] for r in own], PASS), 4), "wp65_dgop": round(wp([r["dg"] for r in oth], PASS), 4),
                        "median_own_dgop": round(float(np.median([r["dg"] for r in own])), 1)}
    # 전사 경로: 9/28 분석과 같은 짝(클립마다 다른 문장 3개)
    tp = load("transcript_proto928.csv")
    for st in ("538", "608"):
        for h in (None, 0, 1):
            rs = [r for r in tp if r["set"] == st and (h is None or int(r["half"]) == h)]
            own = [float(r["r0_novad"]) for r in rs if r["label"] == "own"]
            oth = [float(r["r0_novad"]) for r in rs if r["label"] == "other"]
            ownc = [float(r["r0_novad_c"]) for r in rs if r["label"] == "own"]
            othc = [float(r["r0_novad_c"]) for r in rs if r["label"] == "other"]
            out[f"{st}_{'all' if h is None else h}"].update({
                "t_clips": len(own), "auc_tr928": round(auc(own, oth), 4), "ff65_tr928": round(ff(own, PASS), 4),
                "wp65_tr928": round(wp(oth, PASS), 4), "auc_tr928_collapse": round(auc(ownc, othc), 4),
                "ff65_tr928_collapse": round(ff(ownc, PASS), 4), "wp65_tr928_collapse": round(wp(othc, PASS), 4)})
    print(json.dumps(out, ensure_ascii=False, default=_np, indent=1))
    return out


# ───────────────────────── S19 ─────────────────────────
def s19(B=2000, seed=0):
    rows = [r for r in joined() if r["r0"] is not None and r["label"] in ("own", "other")]
    rng = np.random.default_rng(seed)
    rgrid = np.round(np.arange(0.5, 2.0001, 0.1), 2)
    res = {}
    for st in ("538", "608"):
        rs = sel(rows, st)
        spks = sorted({r["spk"] for r in rs})
        by = defaultdict(list)
        for r in rs:
            by[r["spk"]].append(r)

        def stats(sample):
            own = [r for r in sample if r["label"] == "own"]
            oth = [r for r in sample if r["label"] == "other"]
            a_d = auc([r["dg"] for r in own], [r["dg"] for r in oth])
            a_t = auc([r["r0"] for r in own], [r["r0"] for r in oth])
            f_d, f_t = ff([r["dg"] for r in own], PASS), ff([r["r0"] for r in own], PASS)
            w_d, w_t = wp([r["dg"] for r in oth], PASS), wp([r["r0"] for r in oth], PASS)
            cost = [(f_d + r * w_d) - (f_t + r * w_t) for r in rgrid]
            return [a_d, a_t, a_d - a_t, f_d, f_t, f_d - f_t, w_d, w_t, w_d - w_t] + cost
        point = stats(rs)
        boots = []
        for _ in range(B):
            pick = rng.choice(len(spks), len(spks), replace=True)
            boots.append(stats([r for i in pick for r in by[spks[i]]]))
        boots = np.array(boots)
        lo, hi = np.nanpercentile(boots, 2.5, axis=0), np.nanpercentile(boots, 97.5, axis=0)
        names = ["auc_dgop", "auc_tr", "d_auc", "ff_dgop", "ff_tr", "d_ff", "wp_dgop", "wp_tr", "d_wp"]
        r_ = {n: [round(point[i], 4), round(lo[i], 4), round(hi[i], 4)] for i, n in enumerate(names)}
        cost = {f"{rv:.1f}": [round(point[9 + i], 4), round(lo[9 + i], 4), round(hi[9 + i], 4)] for i, rv in enumerate(rgrid)}
        r_["cost_diff_dgop_minus_tr"] = cost
        r_["r_where_dgop_lower"] = [k for k, v in cost.items() if v[0] < 0]
        r_["n_spk"], r_["n_own"], r_["n_other"] = len(spks), sum(r["label"] == "own" for r in rs), sum(r["label"] == "other" for r in rs)
        res[st] = r_
    print(json.dumps(res, ensure_ascii=False, default=_np, indent=1))
    json.dump(res, open(os.path.join(D, "s19_result.json"), "w"), ensure_ascii=False, default=_np, indent=1)
    return res


# ───────────────────────── 공통: 합격선 고르기 ─────────────────────────
def lowest_threshold(grid, score_fn, rows_h0):
    """절반 0에서 538·608 다르게 말함 합격 ≤ 5% 안의 가장 낮은 합격선."""
    o538 = [score_fn(r) for r in sel(rows_h0, "538", "other")]
    o608 = [score_fn(r) for r in sel(rows_h0, "608", "other")]
    for t in grid:
        if wp(o538, t) <= 0.05 and wp(o608, t) <= 0.05:
            return float(t)
    return float(grid[-1])


# ───────────────────────── S15 ─────────────────────────
def logistic_fit(X, y, iters=50):
    X1 = np.column_stack([np.ones(len(X)), X])
    w = np.zeros(X1.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-X1 @ w))
        g = X1.T @ (y - p)
        H = X1.T @ (X1 * (p * (1 - p))[:, None])
        step = np.linalg.solve(H + 1e-9 * np.eye(len(w)), g)
        w += step
        if np.abs(step).max() < 1e-10:
            break
    return w


def s15(phase):
    rows = [r for r in joined() if r["r0c"] is not None]
    pfile = os.path.join(D, "s15_params.json")
    h0 = [r for r in rows if r["half"] == 0 and r["label"] in ("own", "other")]
    if phase == "explore":
        X = np.array([[r["dg"], r["r0c"]] for r in h0])
        y = np.array([1.0 if r["label"] == "own" else 0.0 for r in h0])
        mu, sd = X.mean(0), X.std(0)
        w = logistic_fit((X - mu) / sd, y)
        ecdf_dg, ecdf_tr = np.sort(X[:, 0]), np.sort(X[:, 1])
        params = {"mu": mu.tolist(), "sd": sd.tolist(), "w": w.tolist(),
                  "ecdf_dg": ecdf_dg.tolist(), "ecdf_tr": ecdf_tr.tolist()}
        f1, f2 = make_fusers(params)
        grid = np.round(np.arange(0, 1.0001, 0.001), 3)
        params["thr_f1"] = lowest_threshold(grid, f1, h0)
        params["thr_f2"] = lowest_threshold(grid, f2, h0)
        json.dump(params, open(pfile, "w"))
        report_s15(h0, params, "explore(절반 0)", rows)
    else:
        params = json.load(open(pfile))
        h1 = [r for r in rows if r["half"] == 1 and r["label"] in ("own", "other")]
        report_s15(h1, params, "confirm(절반 1)", rows, confirm=True)


def make_fusers(p):
    mu, sd, w = np.array(p["mu"]), np.array(p["sd"]), np.array(p["w"])
    ed, et = np.array(p["ecdf_dg"]), np.array(p["ecdf_tr"])

    def f1(r):
        z = (np.array([r["dg"], r["r0c"]]) - mu) / sd
        return float(1 / (1 + np.exp(-(w[0] + w[1:] @ z))))

    def f2(r):
        return float((np.searchsorted(ed, r["dg"], side="right") / len(ed) + np.searchsorted(et, r["r0c"], side="right") / len(et)) / 2)
    return f1, f2


def report_s15(rs, p, title, allrows, confirm=False):
    f1, f2 = make_fusers(p)
    noise = [r for r in allrows if r["label"] == "noise"]
    out = {"phase": title, "w": [round(x, 4) for x in p["w"]], "thr_f1": p["thr_f1"], "thr_f2": p["thr_f2"]}
    for name, fn, thr in (("F1", f1, p["thr_f1"]), ("F2", f2, p["thr_f2"]), ("DGOP65", lambda r: r["dg"], PASS),
                          ("TR65", lambda r: r["r0c"], PASS)):
        for st in ("538", "608"):
            own, oth = [fn(r) for r in sel(rs, st, "own")], [fn(r) for r in sel(rs, st, "other")]
            out[f"{name}_{st}"] = {"auc": round(auc(own, oth), 4), "ff": round(ff(own, thr), 4), "wp": round(wp(oth, thr), 4)}
        out[f"{name}_noise_pass"] = int(sum(fn(r) >= thr for r in noise))
        out[f"{name}_noise_n"] = len(noise)
    if confirm:
        c1 = out["F1_608"]["auc"] >= 0.92
        c2 = out["F1_608"]["ff"] <= out["DGOP65_608"]["ff"] - 0.05
        c3 = out["F1_538"]["wp"] <= 0.05
        c4 = out["F1_noise_pass"] == 0
        out["criteria"] = {"C1_auc608>=0.92": c1, "C2_ff608<=dgop-5pp": c2, "C3_wp538<=5%": c3, "C4_noise0": c4,
                           "C5_latency": "미측정", "adopt_candidate": bool(c1 and c2 and c3 and c4)}
    print(json.dumps(out, ensure_ascii=False, default=_np, indent=1))
    json.dump(out, open(os.path.join(D, f"s15_{'confirm' if confirm else 'explore'}.json"), "w"), ensure_ascii=False, default=_np, indent=1)


# ───────────────────────── S1 ─────────────────────────
def var_components(groups):
    """일원 무선효과(불균형) 적률 추정: σ²_b, σ²_w."""
    groups = [np.asarray(g, float) for g in groups if len(g)]
    N, a = sum(len(g) for g in groups), len(groups)
    grand = np.concatenate(groups).mean()
    ssb = sum(len(g) * (g.mean() - grand) ** 2 for g in groups)
    ssw = sum(((g - g.mean()) ** 2).sum() for g in groups)
    msb, msw = ssb / max(1, a - 1), ssw / max(1, N - a)
    n0 = (N - sum(len(g) ** 2 for g in groups) / N) / max(1, a - 1)
    return max(0.0, (msb - msw) / n0), msw, grand


def s1_scores(rows, p):
    """방법별 판정용 점수 함수. A1은 클립의 반례 점수, A2는 화자의 다른 맞게 말함 클립(그 클립 제외)으로."""
    cohort = defaultdict(list)
    own_by_spk = defaultdict(dict)
    for r in rows:
        if r["label"] == "cohort":
            cohort[(r["set"], r["clip"])].append(r["dg"])
        elif r["label"] == "own":
            own_by_spk[(r["set"], r["spk"])][r["clip"]] = r["dg"]

    def a1(r):
        c = cohort.get((r["set"], r["clip"]), [])
        if len(c) < 3:
            return None
        sd = float(np.std(c, ddof=1)) or 1e-6
        return (r["dg"] - float(np.mean(c))) / sd

    def a2(r):
        others = [v for k, v in own_by_spk[(r["set"], r["spk"])].items() if k != r["clip"]]
        if not others:
            return r["dg"]
        n = len(others)
        wgt = n / (n + p["s2w"] / p["s2b"]) if p["s2b"] > 0 else 0.0
        return r["dg"] - wgt * (float(np.mean(others)) - p["mu538"])
    return a1, a2


def s1(phase):
    rows = joined()
    pfile = os.path.join(D, "s1_params.json")
    if phase == "explore":
        h0 = [r for r in rows if r["half"] == 0]
        g = defaultdict(list)
        for r in sel(h0, "608", "own"):
            g[r["spk"]].append(r["dg"])
        s2b, s2w, _ = var_components(list(g.values()))
        p = {"s2b": s2b, "s2w": s2w, "mu538": float(np.mean([r["dg"] for r in sel(h0, "538", "own")])), "alpha": 0.10}
        a1, a2 = s1_scores(rows, p)
        # A1: 반례가 없으면 A0 판정(65)으로 대신하므로, z 합격선은 반례가 있는 클립만으로 고른다
        h0a1 = [r for r in h0 if a1(r) is not None]
        p["thr_a1"] = lowest_threshold(np.round(np.arange(-5, 5.0001, 0.01), 2), a1, h0a1)
        p["thr_a2"] = lowest_threshold(np.round(np.arange(0, 100.0001, 0.1), 1), a2, h0)
        for st in ("538", "608"):
            own = np.sort([r["dg"] for r in sel(h0, st, "own")])
            k = int(math.floor(p["alpha"] * (len(own) + 1)))
            p[f"thr_a3_{st}"] = float(own[max(0, k - 1)])
        json.dump(p, open(pfile, "w"), indent=1, default=_np)
        report_s1(h0, rows, p, "explore(절반 0)")
    else:
        p = json.load(open(pfile))
        report_s1([r for r in rows if r["half"] == 1], rows, p, "confirm(절반 1)", confirm=True)


def report_s1(rs, allrows, p, title, confirm=False):
    a1, a2 = s1_scores(allrows, p)

    def dec(name, r):
        if name == "A0":
            return r["dg"] >= PASS
        if name == "A1":
            z = a1(r)
            return r["dg"] >= PASS if z is None else z >= p["thr_a1"]
        if name == "A2":
            return a2(r) >= p["thr_a2"]
        return r["dg"] >= p[f"thr_a3_{r['set']}"]
    out = {"phase": title, "params": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in p.items()}}
    for m in ("A0", "A1", "A2", "A3"):
        d = {}
        for st in ("538", "608"):
            own, oth = sel(rs, st, "own"), sel(rs, st, "other")
            d[f"ff_{st}"] = round(1 - np.mean([dec(m, r) for r in own]), 4)
            d[f"wp_{st}"] = round(float(np.mean([dec(m, r) for r in oth])), 4)
        by = defaultdict(list)
        for r in sel(rs, "608", "own"):
            by[r["spk"]].append(dec(m, r))
        d["spk608_passrate_n13plus"] = sorted(round(float(np.mean(v)), 2) for v in by.values() if len(v) >= 13)
        if m == "A1":
            d["no_cohort_clips"] = sum(a1(r) is None for r in rs if r["label"] in ("own", "other"))
        if confirm:
            d["criteria"] = {"ff608<=18%": d["ff_608"] <= 0.18, "wp538<=5%": d["wp_538"] <= 0.05, "wp608<=5%": d["wp_608"] <= 0.05}
            d["pass_all"] = all(d["criteria"].values())
        out[m] = d
    if confirm:
        ok = [m for m in ("A1", "A2", "A3") if out[m]["pass_all"]]
        out["candidate"] = min(ok, key=lambda m: out[m]["ff_608"]) if ok else None
    print(json.dumps(out, ensure_ascii=False, default=_np, indent=1))
    json.dump(out, open(os.path.join(D, f"s1_{'confirm' if confirm else 'explore'}.json"), "w"), ensure_ascii=False, default=_np, indent=1)


# ───────────────────────── S14 ─────────────────────────
def icc_a1(x):
    """x: (n, k). ICC(A,1) 두 방향 무선, 절대 일치, 단일 측정(Shrout·Fleiss / McGraw·Wong)."""
    n, k = x.shape
    gm = x.mean()
    msr = k * ((x.mean(1) - gm) ** 2).sum() / (n - 1)
    msc = n * ((x.mean(0) - gm) ** 2).sum() / (k - 1)
    sse = ((x - x.mean(1, keepdims=True) - x.mean(0, keepdims=True) + gm) ** 2).sum()
    mse = sse / ((n - 1) * (k - 1))
    return (msr - mse) / (msr + (k - 1) * mse + k * (msc - mse) / n)


def kappa(a, b, cats=("good", "warn", "bad")):
    n = len(a)
    if not n:
        return float("nan")
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in cats)
    return (po - pe) / (1 - pe) if pe < 1 else float("nan")


def s14(B=2000, seed=0):
    pr = load("s14_pairs.csv")
    items = defaultdict(dict)
    for r in pr:
        key = (r["session"], r["item"])
        if r["form"] not in items[key] and r["score_nolast"] not in ("", "None") and r["score"] not in ("", "None"):
            items[key][r["form"]] = (float(r["score_nolast"]), float(r["score"]))
    pairs = [(k, v["decl"], v["ques"]) for k, v in items.items() if "decl" in v and "ques" in v]
    sess = sorted({k[0] for k, _, _ in pairs})
    res = {"n_sessions": len(sess), "n_pairs": len(pairs)}

    def stats(ps, j):
        x = np.array([[a[j], b[j]] for _, a, b in ps])
        icc = icc_a1(x)
        sd = x.std(ddof=1)
        sem = sd * math.sqrt(max(0.0, 1 - icc))
        d = x[:, 0] - x[:, 1]
        return icc, sem, math.sqrt((d ** 2).mean() / 2), 1.96 * math.sqrt(2) * sem, float(d.mean())
    rng = np.random.default_rng(seed)
    by = defaultdict(list)
    for p in pairs:
        by[p[0][0]].append(p)
    for j, name in ((0, "nolast"), (1, "full")):
        icc, sem, semd, mdc, bias = stats(pairs, j)
        bs = []
        for _ in range(B):
            pick = rng.choice(len(sess), len(sess), replace=True)
            bs.append(stats([p for i in pick for p in by[sess[i]]], j)[:4])
        lo, hi = np.percentile(bs, 2.5, axis=0), np.percentile(bs, 97.5, axis=0)
        res[name] = {"icc": [round(icc, 3), round(lo[0], 3), round(hi[0], 3)], "sem": [round(sem, 2), round(lo[1], 2), round(hi[1], 2)],
                     "sem_diff": round(semd, 2), "mdc95": [round(mdc, 2), round(lo[3], 2), round(hi[3], 2)],
                     "mean_decl_minus_ques": round(bias, 2)}
    sem = res["nolast"]["sem"][0]
    mdc = res["nolast"]["mdc95"][0]
    # 칩 카파
    ch = defaultdict(dict)
    for r in load("s14_chips.csv"):
        ch[(r["session"], r["item"], int(r["idx"]))].setdefault(r["form"], r["color"])
    a = [v["decl"] for v in ch.values() if "decl" in v and "ques" in v]
    b = [v["ques"] for v in ch.values() if "decl" in v and "ques" in v]
    kp = kappa(a, b)
    res["chip"] = {"n_phones": len(a), "kappa": round(kp, 3), "agree": round(sum(x == y for x, y in zip(a, b)) / max(1, len(a)), 3),
                   "dist_decl": {c: a.count(c) for c in ("good", "warn", "bad")}}
    # 결정 규칙
    own608 = [float(r["score"]) for r in load("dgop_pairs.csv") if r["set"] == "608" and r["label"] == "own" and r["score"] not in ("", "None")]
    inband = float(np.mean([(PASS - sem) <= s <= (PASS + sem) for s in own608]))
    band = sem if inband <= 0.15 else 0.5 * sem
    inband_final = float(np.mean([(PASS - band) <= s <= (PASS + band) for s in own608]))
    res["rules"] = {"gain_threshold": round(max(15.0, mdc), 2), "hold_band_half_width": round(band, 2),
                    "hold_band": [round(PASS - band, 2), round(PASS + band, 2)], "inband_608_at_1sem": round(inband, 4),
                    "inband_608_final": round(inband_final, 4), "chip_reference_only": bool(kp < 0.4)}
    # 보조: Φ(65)
    g = defaultdict(list)
    for r in load("dgop_pairs.csv"):
        if r["set"] == "608" and r["label"] == "own" and r["score"] not in ("", "None"):
            g[r["spk"]].append(float(r["score"]))
    s2p, s2e, mu = var_components(list(g.values()))
    npers = len(g)

    def phi(n):
        corr = s2p / npers + s2e / (npers * n)
        num = s2p + (mu - PASS) ** 2 - corr
        return num / (num + s2e / n)
    need = next((n for n in range(1, 201) if phi(n) >= 0.80), None)
    res["phi"] = {"var_person": round(s2p, 1), "var_resid": round(s2e, 1), "mean": round(mu, 1), "phi65_n1": round(phi(1), 3),
                  "phi65_n5": round(phi(5), 3), "phi65_n10": round(phi(10), 3), "n_for_phi_0.80": need}
    print(json.dumps(res, ensure_ascii=False, default=_np, indent=1))
    json.dump(res, open(os.path.join(D, "s14_result.json"), "w"), ensure_ascii=False, default=_np, indent=1)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "verify":
        verify()
    elif cmd == "s19":
        s19()
    elif cmd == "s15":
        s15(sys.argv[2])
    elif cmd == "s1":
        s1(sys.argv[2])
    elif cmd == "s14":
        s14()
