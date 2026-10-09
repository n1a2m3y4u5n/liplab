"""S20 화자 발음 지수(전사 대리) 분석(맥, docs/speak-intelligibility-index-2026-10.md). 조각 결과만 읽고 모델은 쓰지 않는다.

  python scripts/s20_intelligibility.py explore --run <파드 결과 폴더>    절반 0만 읽어 식(표준화·가중치)을 정하고 params를 쓴다
  python scripts/s20_intelligibility.py confirm --run <파드 결과 폴더>    고정된 params로 절반 1을 연다(판정), 보고용 계산 포함

입력: <run>/out/{asr_v3,asr_base,dgop,acoustic}.jsonl, lab 묶음의 clips.json, 자르기 기록(T3).
출력: lab data/s20_2026-10-09/{speakers_half0.json, params.json, explore.json, confirm.json}. 화자 단위 값은 lab에만 둔다.
"""
import argparse
import hashlib
import json
import os
import re
import sys

import numpy as np
from scipy.optimize import nnls
from scipy.stats import spearmanr, rankdata

LAB = os.path.expanduser(os.environ.get("LAB", "~/Downloads/liplab-lab"))
CLIPS = f"{LAB}/data/s20_stage/root/data/clips.json"
OUTD = f"{LAB}/data/s20_2026-10-09"
CUTS_O = f"{LAB}/data/pod_runs/20261006_35zrgz6wvrqiho/sc/out/cuts608.json"
CUTS_N = os.path.expanduser("~/Downloads/KSC2026/liplab/data/expand/pod_out/cuts608.json")
FEATS = ["Fc", "Fv", "FCR", "Rate"]
SIGN = {"Fc": -1, "Fv": -1, "FCR": +1, "Rate": -1, "Fs": -1, "VSA": -1}   # z를 '클수록 나쁨'으로
N_BOOT, SEED = 2000, 0


def norm(s):
    return re.sub(r"[^가-힣0-9a-z]", "", (s or "").lower())


def lev(a, b):
    if not a:
        return len(b)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def jl(p):
    return {r["clip"]: r for r in (json.loads(l) for l in open(p))}


def cut_yield():
    """T3: 화자별 세션 라벨 문장 가운데 large-v3 일치율 0.5 이상으로 잘린 비율(보고만)."""
    y = {}
    for path in (CUTS_O, CUTS_N):
        for c in json.load(open(path)):
            spk = c["file"].split("-")[4]
            t = y.setdefault((path, spk), [0, 0])
            t[0] += 1
            t[1] += c.get("cut") is not None
    return {"O": {s: v[1] / v[0] for (p, s), v in y.items() if p == CUTS_O},
            "N": {s: v[1] / v[0] for (p, s), v in y.items() if p == CUTS_N}}


def speaker_table(run, halves):
    clips = [c for c in json.load(open(CLIPS)) if c["half"] in halves]
    v3, base = jl(f"{run}/out/asr_v3.jsonl"), jl(f"{run}/out/asr_base.jsonl")
    dg, ac = jl(f"{run}/out/dgop.jsonl"), jl(f"{run}/out/acoustic.jsonl")
    ty = cut_yield()
    sp = {}
    for c in clips:
        s = sp.setdefault(c["spk"], {"spk": c["spk"], "set": c["set"], "half": c["half"], "sex": c["sex"], "cer": [], "ed": 0, "nref": 0,
                                     "cer_base": [], "fc": [], "fv": [], "fs": [], "rate": [], "vow": {"ㅏ": [], "ㅣ": [], "ㅜ": []},
                                     "nf": [], "snrp": [], "len": [], "n": 0, "dgop_err": 0})
        s["n"] += 1
        ref = norm(c["target"])
        s["len"].append(len(re.sub(r"[^가-힣]", "", c["target"])))
        e = lev(ref, norm(v3[c["clip"]]["text"]))
        s["cer"].append(min(1.0, e / len(ref)))
        s["ed"] += e
        s["nref"] += len(ref)
        s["cer_base"].append(min(1.0, lev(ref, norm(base[c["clip"]]["text"])) / len(ref)))
        d = dg[c["clip"]]
        if "error" in d:
            s["dgop_err"] += 1
        else:
            ph = [p for p in d["phones"] if p.get("aligned") and p.get("scorable") and not p.get("silent_h")]
            cons = [p["dgop"] >= 0.5 for p in ph if p["token"][:2] in ("o:", "c:")]
            vows = [p["dgop"] >= 0.5 for p in ph if p["token"][:2] == "n:"]
            if cons:
                s["fc"].append(np.mean(cons))
            if vows:
                s["fv"].append(np.mean(vows))
            if d.get("raw") is not None:
                s["fs"].append(d["raw"])
            if d.get("rate") and d["rate"].get("rate") is not None:
                s["rate"].append(d["rate"]["rate"])
        a = ac[c["clip"]]
        if a.get("nf") is not None:
            s["nf"].append(a["nf"])
            s["snrp"].append(a["snrp"])
        for v, f1, f2, _ in a["vowels"]:
            s["vow"][v].append((f1, f2))
    out = []
    for k, s in sorted(sp.items()):
        med = {v: (np.median([x[0] for x in t]), np.median([x[1] for x in t])) if len(t) >= 3 else None for v, t in s["vow"].items()}
        fcr = vsa = None
        if all(med.values()):
            (f1a, f2a), (f1i, f2i), (f1u, f2u) = med["ㅏ"], med["ㅣ"], med["ㅜ"]
            fcr = (f2u + f2a + f1i + f1u) / (f2i + f1a)
            vsa = 0.5 * abs(f1a * (f2i - f2u) + f1i * (f2u - f2a) + f1u * (f2a - f2i))
        order_ok = None
        if all(med.values()):
            order_ok = bool(med["ㅏ"][0] > med["ㅣ"][0] and med["ㅏ"][0] > med["ㅜ"][0] and med["ㅣ"][1] > med["ㅜ"][1] and med["ㅣ"][1] > med["ㅏ"][1])
        out.append({"spk": k, "set": s["set"], "half": s["half"], "sex": s["sex"], "n": s["n"], "dgop_err": s["dgop_err"],
                    "T1": float(np.mean(s["cer"])), "T1p": s["ed"] / s["nref"], "T2": float(np.mean(s["cer_base"])),
                    "T3": ty[s["set"]].get(k),
                    "Fc": float(np.mean(s["fc"])), "Fv": float(np.mean(s["fv"])), "Fs": float(np.mean(s["fs"])),
                    "Rate": float(np.mean(s["rate"])) if len(s["rate"]) >= 3 else None, "n_rate": len(s["rate"]),
                    "FCR": fcr, "VSA": vsa, "vowel_n": {v: len(t) for v, t in s["vow"].items()},
                    "vowel_med": {v: (None if m is None else [round(m[0], 1), round(m[1], 1)]) for v, m in med.items()},
                    "order_ok": order_ok, "NF": float(np.mean(s["nf"])), "SNRp": float(np.mean(s["snrp"])),
                    "len_syl": float(np.mean(s["len"]))})
    return out


def zmat(rows, params, feats):
    Z = np.zeros((len(rows), len(feats)))
    for j, f in enumerate(feats):
        m, sd = params["mean"][f], params["sd"][f]
        for i, r in enumerate(rows):
            Z[i, j] = 0.0 if r[f] is None else SIGN[f] * (r[f] - m) / sd
    return Z


def fit(rows, feats, target="T1"):
    mean = {f: float(np.mean([r[f] for r in rows if r[f] is not None])) for f in feats}
    sd = {f: float(np.std([r[f] for r in rows if r[f] is not None], ddof=1)) for f in feats}
    p = {"feats": feats, "mean": mean, "sd": sd, "missing": {f: sum(r[f] is None for r in rows) for f in feats}}
    Z = zmat(rows, p, feats)
    y = np.array([r[target] for r in rows])
    w, _ = nnls(Z - Z.mean(axis=0), y - y.mean())
    p["w"] = {f: float(x) for f, x in zip(feats, w)}
    return p


def index(rows, p, eq=False):
    Z = zmat(rows, p, p["feats"])
    w = np.ones(len(p["feats"])) / len(p["feats"]) if eq else np.array([p["w"][f] for f in p["feats"]])
    return Z @ w


def rho(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    if np.ptp(x) == 0 or np.ptp(y) == 0:
        return float("nan")
    return float(spearmanr(x, y).correlation)


def partial_rho(x, y, nf, setv):
    rx, ry, rn = rankdata(x), rankdata(y), rankdata(nf)
    X = np.column_stack([np.ones(len(x)), rn, setv])
    ex = rx - X @ np.linalg.lstsq(X, rx, rcond=None)[0]
    ey = ry - X @ np.linalg.lstsq(X, ry, rcond=None)[0]
    if np.std(ex) == 0 or np.std(ey) == 0:
        return float("nan")
    return float(np.corrcoef(ex, ey)[0, 1])


def boot(n, fn):
    rng = np.random.default_rng(SEED)
    vals = []
    for _ in range(N_BOOT):
        idx = rng.integers(0, n, n)
        vals.append(fn(idx))
    v = np.array(vals, float)
    v = v[np.isfinite(v)]
    return [round(float(np.percentile(v, 2.5)), 3), round(float(np.percentile(v, 97.5)), 3)], int(N_BOOT - len(v))


def formant_gate(rows):
    ok = [r["order_ok"] for r in rows]
    known = [x for x in ok if x is not None]
    return {"n_speakers": len(rows), "n_with_fcr": len(known), "n_order_ok": int(sum(known)),
            "rate_ok": (sum(known) / len(rows)) if rows else None, "pass": (sum(known) / len(rows)) >= 0.80}


def sha16(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]


def explore(run):
    rows = speaker_table(run, {0})
    gate_all = formant_gate(speaker_table_feats_only(run))
    feats = FEATS if gate_all["pass"] else [f for f in FEATS if f != "FCR"]
    p = fit(rows, feats)
    p.update(formant_gate=gate_all, n_half0=len(rows), run=os.path.abspath(run))
    os.makedirs(OUTD, exist_ok=True)
    json.dump(rows, open(f"{OUTD}/speakers_half0.json", "w"), ensure_ascii=False, indent=1)
    json.dump(p, open(f"{OUTD}/params.json", "w"), ensure_ascii=False, indent=1, sort_keys=True)
    y = [r["T1"] for r in rows]
    rep = {"n": len(rows), "params_sha16": sha16(f"{OUTD}/params.json"), "w": p["w"], "missing": p["missing"],
           "formant_gate": gate_all,
           "rho_half0": {"M1": rho(index(rows, p), y), "M0": rho(index(rows, p, eq=True), y),
                         **{f: rho([SIGN[f] * (r[f] if r[f] is not None else np.nan) for r in rows], y) for f in FEATS + ["Fs"]
                            if all(r[f] is not None for r in rows)}},
           "T1_median": float(np.median(y)), "T1_range": [float(min(y)), float(max(y))],
           "by_set": {s: sum(r["set"] == s for r in rows) for s in ("O", "N")}}
    json.dump(rep, open(f"{OUTD}/explore.json", "w"), ensure_ascii=False, indent=1)
    print(json.dumps(rep, ensure_ascii=False, indent=1))


def speaker_table_feats_only(run):
    """포먼트 관문(4절): 모든 화자의 모음 중앙값 순서만 본다. CER은 쓰지 않는다(speaker_table이 계산하지만 여기서는 버린다)."""
    rows = speaker_table(run, {0, 1})
    return [{"spk": r["spk"], "order_ok": r["order_ok"]} for r in rows]


def confirm(run):
    p = json.load(open(f"{OUTD}/params.json"))
    rows = speaker_table(run, {1})
    n = len(rows)
    y = np.array([r["T1"] for r in rows])
    nf = np.array([r["NF"] for r in rows])
    setv = np.array([1.0 if r["set"] == "N" else 0.0 for r in rows])
    m1 = index(rows, p)
    m0 = index(rows, p, eq=True)
    res = {"n": n, "params_sha16": sha16(f"{OUTD}/params.json"), "by_set": {s: int(sum(r["set"] == s for r in rows)) for s in ("O", "N")}}
    r1 = rho(m1, y)
    ci1, _ = boot(n, lambda i: rho(m1[i], y[i]))
    pr = partial_rho(m1, y, nf, setv)
    cip, nanp = boot(n, lambda i: partial_rho(m1[i], y[i], nf[i], setv[i]))
    res["C1"] = {"rho": round(r1, 3), "ci": ci1, "pass": r1 >= 0.60}
    res["C2"] = {"rho_partial": round(pr, 3), "ci": cip, "boot_nan": nanp, "pass": pr >= 0.50}
    res["verdict"] = "통과" if (r1 >= 0.60 and pr >= 0.50) else ("판정 보류(녹음 조건)" if r1 >= 0.60 else "실패")
    rep = {}
    rep["M0"] = (round(rho(m0, y), 3), boot(n, lambda i: rho(m0[i], y[i]))[0])
    for f in FEATS + ["Fs", "VSA"]:
        k = np.array([r[f] is not None for r in rows])
        if k.sum() < 5:
            rep[f] = None
            continue
        x = SIGN[f] * np.array([r[f] for r in rows if r[f] is not None], float)
        yk = y[k]
        rep[f] = (round(rho(x, yk), 3), boot(int(k.sum()), lambda i, x=x, yk=yk: rho(x[i], yk[i]))[0], int(k.sum()))
    fs = -np.array([r["Fs"] for r in rows])
    rep["M1_minus_Fs"] = (round(rho(m1, y) - rho(fs, y), 3), boot(n, lambda i: rho(m1[i], y[i]) - rho(fs[i], y[i]))[0])
    for t in ("T1p", "T2", "T3"):
        yt = np.array([r[t] if r[t] is not None else np.nan for r in rows], float)
        ok = np.isfinite(yt)
        if t == "T3":
            yt = -yt   # 자르기 합격 비율은 클수록 좋음 → 부호를 바꿔 CER과 같은 방향
        rep[f"M1_vs_{t}"] = round(rho(m1[ok], yt[ok]), 3)
    rep["rho_T1_T3"] = round(rho(y, -np.array([r["T3"] for r in rows], float)), 3)
    rep["rho_NF_T1"] = round(rho(nf, y), 3)
    rep["rho_NF_M1"] = round(rho(nf, m1), 3)
    rep["rho_SNRp_T1"] = round(rho([r["SNRp"] for r in rows], y), 3)
    rep["rho_len_T1"] = round(rho([r["len_syl"] for r in rows], y), 3)
    rep["rho_len_M1"] = round(rho([r["len_syl"] for r in rows], m1), 3)
    for s in ("O", "N"):
        k = setv == (1.0 if s == "N" else 0.0)
        rep[f"within_{s}"] = {"n": int(k.sum()), "rho": round(rho(m1[k], y[k]), 3) if k.sum() >= 3 else None}
    rep["T1_median"] = float(np.median(y))
    rep["T1_range"] = [float(y.min()), float(y.max())]
    res["report"] = rep
    # 보고만: 절반 바꾼 교차, 33명 하나 빼기
    allrows = speaker_table(run, {0, 1})
    h0 = [r for r in allrows if r["half"] == 0]
    p_sw = fit(rows, p["feats"])
    res["swap"] = {"w": p_sw["w"], "rho_half0": round(rho(index(h0, p_sw), [r["T1"] for r in h0]), 3)}
    pred = []
    for i in range(len(allrows)):
        tr = allrows[:i] + allrows[i + 1:]
        pp = fit(tr, p["feats"])
        pred.append(float(index([allrows[i]], pp)[0]))
    ya = [r["T1"] for r in allrows]
    res["loso33"] = {"n": len(allrows), "rho": round(rho(pred, ya), 3)}
    fsa = -np.array([r["Fs"] for r in allrows])
    res["all33_Fs_rho"] = round(rho(fsa, ya), 3)
    nfa = np.array([r["NF"] for r in allrows])
    sa = np.array([1.0 if r["set"] == "N" else 0.0 for r in allrows])
    rk = rankdata(nfa)
    n1, n0 = int(sa.sum()), int((sa == 0).sum())
    res["NF_auc_N_vs_O"] = round(float((rk[sa == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)), 3)   # P(N의 바닥 > O의 바닥)
    res["NF_median"] = {"O": float(np.median(nfa[sa == 0])), "N": float(np.median(nfa[sa == 1]))}
    json.dump(res, open(f"{OUTD}/confirm.json", "w"), ensure_ascii=False, indent=1)
    json.dump(rows, open(f"{OUTD}/speakers_half1.json", "w"), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["explore", "confirm"])
    ap.add_argument("--run", required=True)
    a = ap.parse_args()
    (explore if a.mode == "explore" else confirm)(a.run)
