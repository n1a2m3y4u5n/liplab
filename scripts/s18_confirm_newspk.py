"""S18 고정 헤드의 새 화자 확인(사전 등록 docs/scoring-analyses-2026-10.md 8절). 헤드와 합격선은 scripts/s18_head_frozen_2026-10-06.json
그대로 쓰고 다시 적합하지 않는다. 특성은 파드에서 scripts/scoring_s18_head.py features(10/6 등록판 563f1da)로 만든다.

    python scripts/s18_confirm_newspk.py selfcheck                    고정본을 10/6 특성 CSV 절반 1에 다시 적용(0.941·5.9%가 나와야 함)
    python scripts/s18_confirm_newspk.py bridge <다리 특성 csv>       옛 538 클립 30개를 새 파드에서 다시 만든 특성이 10/6 값과 같은지
    python scripts/s18_confirm_newspk.py confirm <새 특성 csv> [다리 특성 csv] [출력 json]

층: 608 화자 ID가 '28-'로 시작하면 P28(감음신경성, 주 판정), '27-'이면 P27(전음성, 보조). 538은 새 화자(v1_538).
수치는 집계만 출력한다. 문장별 CSV는 저장소 밖(liplab-lab/data/scores_newspk_2026-10-06/)에 둔다.
"""
import csv
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scoring_analyses_1006 import auc, ff, wp  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FROZEN = os.path.join(HERE, "s18_head_frozen_2026-10-06.json")
OLD = os.path.expanduser("~/Downloads/liplab-lab/data/scores_2026-10-06/s18_features.csv")
B = 2000
MIN_P28_SPK, MIN_P28_OWN = 5, 50
BRIDGE_TOL_P, BRIDGE_TOL_DG, BRIDGE_MIN = 0.005, 0.1, 25


def frozen():
    p = json.load(open(FROZEN, encoding="utf-8"))
    mu, sd, w = np.array(p["mu"]), np.array(p["sd"]), np.array(p["w"])
    feats = p["feats"]

    def head(r):
        x = (np.array([float(r[k]) for k in feats]) - mu) / sd
        return float(1 / (1 + np.exp(-(w[0] + w[1:] @ x))))
    return p, head


def load(path):
    with open(path) as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["dg"] = float(r["dg"])
    return rows


def stratum(r):
    if r["set"] == "538":
        return "538"
    return "P28" if r["spk"].startswith("28-") else ("P27" if r["spk"].startswith("27-") else "608?")


def metrics(rows, score, thr):
    own = [score(r) for r in rows if r["label"] == "own"]
    oth = [score(r) for r in rows if r["label"] == "other"]
    return {"auc": auc(own, oth), "ff": ff(own, thr), "wp": wp(oth, thr), "n_own": len(own), "n_other": len(oth),
            "n_spk": len({r["spk"] for r in rows})}


def boot(rows, score, thr, seed=0):
    """화자 단위 부트스트랩(보고만, 판정에 쓰지 않음)."""
    spks = sorted({r["spk"] for r in rows})
    by = {s: [r for r in rows if r["spk"] == s] for s in spks}
    sc = {id(r): score(r) for r in rows}
    rng = np.random.default_rng(seed)
    out = {"auc": [], "ff": [], "wp": []}
    for _ in range(B):
        pick = rng.integers(0, len(spks), len(spks))
        own = [sc[id(r)] for i in pick for r in by[spks[i]] if r["label"] == "own"]
        oth = [sc[id(r)] for i in pick for r in by[spks[i]] if r["label"] == "other"]
        if own and oth:
            out["auc"].append(auc(own, oth))
            out["ff"].append(ff(own, thr))
            out["wp"].append(wp(oth, thr))
    return {k: [round(float(np.percentile(v, 2.5)), 4), round(float(np.percentile(v, 97.5)), 4)] for k, v in out.items() if v}


def selfcheck():
    p, head = frozen()
    rows = [r for r in load(OLD) if r["half"] == "1"]
    out = {}
    for st in ("538", "608"):
        m = metrics([r for r in rows if r["set"] == st], head, p["thr"])
        out[st] = {k: round(v, 4) if isinstance(v, float) else v for k, v in m.items()}
    ok = abs(out["608"]["auc"] - 0.9414) < 1e-4 and abs(out["608"]["wp"] - 0.0594) < 1e-4 and abs(out["538"]["wp"] - 0.0033) < 1e-4
    print(json.dumps(out, ensure_ascii=False))
    print("S18_SELFCHECK_OK" if ok else "S18_SELFCHECK_FAIL")
    return ok


def bridge(path):
    p, head = frozen()
    old = {(r["clip"], r["target_sid"], r["label"]): r for r in load(OLD) if r["set"] == "538"}
    new = load(path)
    dp, ddg, n, miss = [], [], 0, 0
    for r in new:
        o = old.get((r["clip"], r["target_sid"], r["label"]))
        if o is None:
            miss += 1
            continue
        n += 1
        dp.append(abs(head(r) - head(o)))
        ddg.append(abs(r["dg"] - o["dg"]))
    res = {"n": n, "missing": miss, "max_dp": round(max(dp), 6) if dp else None, "max_ddg": round(max(ddg), 4) if ddg else None}
    res["ok"] = bool(n >= BRIDGE_MIN and miss == 0 and res["max_dp"] <= BRIDGE_TOL_P and res["max_ddg"] <= BRIDGE_TOL_DG)
    print("S18_BRIDGE", json.dumps(res))
    return res


def confirm(path, bridge_path=None, out_path=None):
    p, head = frozen()
    sc_ok = selfcheck()
    br = bridge(bridge_path) if bridge_path else {"ok": False, "note": "다리 특성 없음"}
    rows = load(path)
    for r in rows:
        r["st"] = stratum(r)
    out = {"frozen_sha256_note": "scripts/s18_head_frozen_2026-10-06.json", "thr": p["thr"], "selfcheck": sc_ok, "bridge": br,
           "strata": {}}
    for st in ("P28", "P27", "538"):
        rs = [r for r in rows if r["st"] == st]
        if not rs:
            continue
        e = {}
        for name, fn, thr in (("HEAD", head, p["thr"]), ("DGOP65", lambda r: r["dg"], 65.0)):
            m = metrics(rs, fn, thr)
            e[name] = {k: round(v, 4) if isinstance(v, float) else v for k, v in m.items()}
            e[name]["ci"] = boot(rs, fn, thr)
        out["strata"][st] = e
    rs = [r for r in rows if r["st"] in ("P28", "P27")]
    if rs:
        out["strata"]["P28+P27"] = {"HEAD": {k: round(v, 4) if isinstance(v, float) else v
                                             for k, v in metrics(rs, head, p["thr"]).items()}}
    s28, s538 = out["strata"].get("P28"), out["strata"].get("538")
    valid = bool(sc_ok and br.get("ok") and s28 and s538 and s28["HEAD"]["n_spk"] >= MIN_P28_SPK
                 and s28["HEAD"]["n_own"] >= MIN_P28_OWN)
    if s28 and s538:
        c = {"auc608>=0.92": s28["HEAD"]["auc"] >= 0.92, "wp608<=5%": s28["HEAD"]["wp"] <= 0.05,
             "wp538<=5%": s538["HEAD"]["wp"] <= 0.05, "사자차하_auc>=0.80": "이 자료로 잴 수 없음"}
        out["criteria"] = c
        allp = c["auc608>=0.92"] and c["wp608<=5%"] and c["wp538<=5%"]
        out["verdict"] = ("HOLD(유효성 미달)" if not valid else ("통과(S3 축소 조건의 일부 충족)" if allp else "실패"))
        if s28["HEAD"]["n_spk"] < MIN_P28_SPK or s28["HEAD"]["n_own"] < MIN_P28_OWN:
            out["verdict"] = "판정 불가(P28 표본 부족)"
    if "P27" in out["strata"] and s538:
        h = out["strata"]["P27"]["HEAD"]
        out["p27_secondary"] = {"auc608>=0.92": h["auc"] >= 0.92, "wp608<=5%": h["wp"] <= 0.05}
    txt = json.dumps(out, ensure_ascii=False, indent=1)
    print(txt)
    if out_path:
        open(out_path, "w").write(txt)
    print("S18_CONFIRM_VERDICT", out.get("verdict"))
    return out


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "selfcheck":
        sys.exit(0 if selfcheck() else 1)
    elif cmd == "bridge":
        sys.exit(0 if bridge(sys.argv[2])["ok"] else 1)
    elif cmd == "confirm":
        confirm(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None, sys.argv[4] if len(sys.argv) > 4 else None)
