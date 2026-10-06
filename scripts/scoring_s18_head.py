"""S18(나13) GOP 특성 융합 헤드: 세션 12 덤프(정렬기·채점기 로짓, 음소별 점수)로 문장 단위 특성을 만들고 작은 로지스틱 헤드를 학습한다.
사전 등록은 docs/scoring-analyses-2026-10.md 6절. 음향 모델은 그대로 두고 헤드만 학습한다(전사 점수는 넣지 않는다, 그것은 S15).

    python scripts/scoring_s18_head.py features <pod_runs/.../sc> [출력 csv]   특성 CSV(저장소 밖, scores_2026-10-06/s18_features.csv)
    python scripts/scoring_s18_head.py explore | confirm

특성(문장마다): D-GOP 보정 점수, 음소 naive의 평균·최솟값·10백분위·45 미만 비율, confidence 평균,
채점기·정렬기 로짓에서 목표 자모열의 CTC 로그우도/프레임, 같은 로짓의 최선 경로 대비 로그우도비/프레임, 목표 길이/프레임.
"""
import csv
import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

D = os.environ.get("SCORES_DIR", os.path.expanduser("~/Downloads/liplab-lab/data/scores_2026-10-06"))
LAB_M = os.path.expanduser("~/Downloads/liplab-lab/models/dgop_ours_2026-09-25_int8")
FEATS = ["dg", "naive_mean", "naive_min", "naive_p10", "frac_bad", "conf_mean", "ll_sc", "ll_al", "lpr_sc", "lpr_al", "len_ratio"]


def _np(o):
    return o.item() if hasattr(o, "item") else str(o)


def features(src, out_csv):
    import torch
    import torch.nn.functional as F
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    o = f"{src}/out" if os.path.isdir(f"{src}/out") else src
    voc = {m: json.load(open(f"{LAB_M}/{m}/vocab.json")) for m in ("aligner", "scorer")}
    assert voc["aligner"] == voc["scorer"]
    vocab = voc["scorer"]
    blank = vocab["<pad>"]
    sys.path.insert(0, os.path.expanduser("~/Downloads/liplab-lab/tools"))
    from build_scores_csv import sid_of, half_of  # 같은 ID 규칙
    cache = {}
    rows = []
    for l in open(f"{o}/dgop_full.jsonl", encoding="utf-8"):
        j = json.loads(l)
        if j["set"] not in ("538", "608") or j["kind"] not in ("same", "diff") or "error" in j or j.get("score") is None:
            continue
        cid = f"{j['set']}_{j['clip']}".replace(":", "__")
        if cid not in cache:
            z = np.load(f"{o}/lp/{cid}.npz")
            cache = {cid: {k: F.log_softmax(torch.from_numpy(z[k].astype(np.float32)), -1) for k in ("al", "sc")}}
        lp = cache[cid]
        toks = [p["token"] for p in j["phones"]]
        ids = torch.tensor([vocab[t] for t in toks], dtype=torch.long)
        T = lp["sc"].shape[0]
        f = {}
        for k in ("al", "sc"):
            nll = F.ctc_loss(lp[k][:, None, :], ids[None], torch.tensor([T]), torch.tensor([len(ids)]), blank=blank,
                             reduction="sum", zero_infinity=True).item()
            best = lp[k].max(-1).values.sum().item()
            f[f"ll_{k}"] = -nll / T
            f[f"lpr_{k}"] = (-nll - best) / T
        sc = [p for p in j["phones"] if p.get("aligned") and p.get("scorable")]
        nv = np.array([p["naive"] for p in sc], float)
        cf = np.array([p["confidence"] for p in sc], float)
        rows.append({"set": j["set"], "spk": j["spk"], "half": half_of(j["spk"]), "clip": j["clip"], "target_sid": sid_of(j["target"]),
                     "label": "own" if j["kind"] == "same" else "other", "dg": j["score"],
                     "naive_mean": nv.mean(), "naive_min": nv.min(), "naive_p10": np.percentile(nv, 10),
                     "frac_bad": float((nv < 0.45).mean()), "conf_mean": cf.mean(), "len_ratio": len(ids) / T, **f})
    with open(out_csv, "w", newline="") as fo:
        w = csv.DictWriter(fo, fieldnames=["set", "spk", "half", "clip", "target_sid", "label"] + FEATS)
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()})
    print("S18_FEATURES", len(rows), out_csv)


def load():
    with open(os.path.join(D, "s18_features.csv")) as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["half"] = int(r["half"])
        for k in FEATS:
            r[k] = float(r[k])
    return rows


def fit_ridge_logistic(X, y, lam=1.0, iters=100):
    X1 = np.column_stack([np.ones(len(X)), X])
    w = np.zeros(X1.shape[1])
    P = lam * np.eye(len(w))
    P[0, 0] = 0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-X1 @ w))
        g = X1.T @ (y - p) - P @ w
        H = X1.T @ (X1 * (p * (1 - p))[:, None]) + P
        step = np.linalg.solve(H, g)
        w += step
        if np.abs(step).max() < 1e-10:
            break
    return w


def run(phase):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from scoring_analyses_1006 import auc, ff, wp, lowest_threshold, sel
    rows = load()
    pfile = os.path.join(D, "s18_params.json")
    if phase == "explore":
        h0 = [r for r in rows if r["half"] == 0]
        X = np.array([[r[k] for k in FEATS] for r in h0])
        y = np.array([r["label"] == "own" for r in h0], float)
        mu, sd = X.mean(0), X.std(0) + 1e-9
        w = fit_ridge_logistic((X - mu) / sd, y)
        p = {"mu": mu.tolist(), "sd": sd.tolist(), "w": w.tolist(), "feats": FEATS}
        head = lambda r: float(1 / (1 + np.exp(-(w[0] + w[1:] @ ((np.array([r[k] for k in FEATS]) - mu) / sd)))))
        p["thr"] = lowest_threshold(np.round(np.arange(0, 1.0001, 0.001), 3), head, h0)
        json.dump(p, open(pfile, "w"), default=_np)
        rs, title = h0, "explore(절반 0)"
    else:
        p = json.load(open(pfile))
        mu, sd, w = np.array(p["mu"]), np.array(p["sd"]), np.array(p["w"])
        head = lambda r: float(1 / (1 + np.exp(-(w[0] + w[1:] @ ((np.array([r[k] for k in FEATS]) - mu) / sd)))))
        rs, title = [r for r in rows if r["half"] == 1], "confirm(절반 1)"
    out = {"phase": title, "thr": p["thr"], "coef": dict(zip(["b0"] + FEATS, [round(x, 3) for x in p["w"]]))}
    for name, fn, thr in (("HEAD", head, p["thr"]), ("DGOP65", lambda r: r["dg"], 65.0)):
        for st in ("538", "608"):
            own, oth = [fn(r) for r in sel(rs, st, "own")], [fn(r) for r in sel(rs, st, "other")]
            out[f"{name}_{st}"] = {"auc": round(auc(own, oth), 4), "ff": round(ff(own, thr), 4), "wp": round(wp(oth, thr), 4),
                                   "n_own": len(own), "n_other": len(oth)}
    if phase == "confirm":
        c = {"auc608>=0.92": out["HEAD_608"]["auc"] >= 0.92, "wp538<=5%": out["HEAD_538"]["wp"] <= 0.05,
             "wp608<=5%": out["HEAD_608"]["wp"] <= 0.05, "사자차하_auc>=0.80": "이 자료로 잴 수 없음"}
        out["criteria"] = c
        out["pass_sentence_criteria"] = bool(c["auc608>=0.92"] and c["wp538<=5%"] and c["wp608<=5%"])
    print(json.dumps(out, ensure_ascii=False, indent=1, default=_np))
    json.dump(out, open(os.path.join(D, f"s18_{phase}.json"), "w"), ensure_ascii=False, indent=1, default=_np)


if __name__ == "__main__":
    if sys.argv[1] == "features":
        features(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else os.path.join(D, "s18_features.csv"))
    else:
        run(sys.argv[1])
