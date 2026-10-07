"""S24 판정: 발성 지표(음높이 수준·안정도·목소리 질)가 608(청각장애)과 538(건청)을 가르고 문장 CER과 함께 움직이는가.
사전 등록 docs/speak-voice-quality-2026-10.md.

  python3 speak_s24_analyze.py explore RAW.jsonl.gz PARAMS.json        절반 0: 방향·성별 기준·상관 부호 정하기
  python3 speak_s24_analyze.py confirm RAW.jsonl.gz PARAMS.json OUT.json   절반 1: 판정(PARAMS 고정)

numpy만 쓴다(맥). 출력은 집계만.
"""
import gzip, json, math, re, sys
from collections import defaultdict

import numpy as np

FEATS = ("f0_level_st", "f0_sd_st", "f0_step_st", "jitter_local", "shimmer_local", "hnr_db", "cpps_db")
PRAAT_SAME = ("f0_sd_st", "jitter_local", "shimmer_local", "hnr_db", "cpps_db")
AUC_MIN, RHO_MIN = 0.70, 0.30


def load(path):
    rows = []
    for line in gzip.open(path, "rt", encoding="utf-8"):
        r = json.loads(line)
        if "error" not in r and r["set"] in ("538", "608c28") and r.get("vq"):
            rows.append(r)
    return rows


def norm(t):
    return re.sub(r"[^가-힣0-9a-z]", "", (t or "").lower())


def lev(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def cer(r):
    ref, hyp = norm(r["text"]), norm(r.get("asr"))
    return lev(ref, hyp) / len(ref) if ref and r.get("asr") is not None else None


def rank(x):
    x = np.asarray(x, float)
    o = np.argsort(x, kind="mergesort")
    rk = np.empty(len(x))
    i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and x[o[j + 1]] == x[o[i]]:
            j += 1
        rk[o[i:j + 1]] = (i + j) / 2.0
        i = j + 1
    return rk


def spearman(x, y):
    if len(x) < 5:
        return None
    a, b = rank(x), rank(y)
    if a.std() == 0 or b.std() == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def auc(pos, neg):
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    if not len(pos) or not len(neg):
        return None
    r = rank(np.concatenate([pos, neg]))          # 0부터 센 평균 순위
    return float((r[: len(pos)].sum() - len(pos) * (len(pos) - 1) / 2) / (len(pos) * len(neg)))


def value(r, f, prm, src="vq"):
    d = r.get(src) or {}
    if f == "f0_level_st":
        hz, ref = d.get("f0_med_hz"), prm["sex_ref_hz"].get(r.get("sex") or "")
        return 12 * math.log2(hz / ref) if hz and ref else None
    v = d.get(f)
    return v if v is not None and math.isfinite(v) else None


def boot_auc(p608, p538, d, n=2000, seed=0):
    """화자 단위 부트스트랩(두 집단 각각 화자를 복원 추출)."""
    rng = np.random.default_rng(seed)
    a = defaultdict(list)
    b = defaultdict(list)
    for s, v in p608:
        a[s].append(v)
    for s, v in p538:
        b[s].append(v)
    ka, kb = list(a), list(b)
    out = []
    for _ in range(n):
        pa = [v for s in rng.choice(ka, len(ka)) for v in a[s]]
        pb = [v for s in rng.choice(kb, len(kb)) for v in b[s]]
        out.append(auc(np.array(pa) * d, np.array(pb) * d))
    return [round(float(np.percentile(out, 2.5)), 4), round(float(np.percentile(out, 97.5)), 4)]


def boot_rho(pairs, n=2000, seed=0):
    rng = np.random.default_rng(seed)
    by = defaultdict(list)
    for s, x, y in pairs:
        by[s].append((x, y))
    ks = list(by)
    out = []
    for _ in range(n):
        xs = [p for s in rng.choice(ks, len(ks)) for p in by[s]]
        r = spearman([p[0] for p in xs], [p[1] for p in xs])
        if r is not None:
            out.append(r)
    return [round(float(np.percentile(out, 2.5)), 4), round(float(np.percentile(out, 97.5)), 4)] if out else None


def measure(rows, half, prm, f, src="vq", detail=True):
    s608 = [r for r in rows if r["set"] == "608c28" and r["half"] == half]
    s538 = [r for r in rows if r["set"] == "538" and r["half"] == half]
    v608 = [(r["spk"], value(r, f, prm, src), r) for r in s608]
    v538 = [(r["spk"], value(r, f, prm, src), r) for r in s538]
    v608 = [x for x in v608 if x[1] is not None]
    v538 = [x for x in v538 if x[1] is not None]
    d = prm["direction"].get(f, 1)
    a = auc(np.array([x[1] for x in v608]) * d, np.array([x[1] for x in v538]) * d)
    cr = [(s, v, cer(r)) for s, v, r in v608 if cer(r) is not None]
    rho = spearman([x[1] for x in cr], [x[2] for x in cr])
    out = {"n608": len(v608), "n538": len(v538), "spk608": len({x[0] for x in v608}), "spk538": len({x[0] for x in v538}),
           "direction": d, "auc": None if a is None else round(a, 4), "rho_cer_608": None if rho is None else round(rho, 4),
           "n_cer": len(cr),
           "median_608": round(float(np.median([x[1] for x in v608])), 3) if v608 else None,
           "median_538": round(float(np.median([x[1] for x in v538])), 3) if v538 else None}
    if detail and v608 and v538:
        out["auc_ci"] = boot_auc([(s, v) for s, v, _ in v608], [(s, v) for s, v, _ in v538], d)
        out["rho_ci"] = boot_rho(cr)
        sm6 = defaultdict(list)
        sm5 = defaultdict(list)
        for s, v, _ in v608:
            sm6[s].append(v)
        for s, v, _ in v538:
            sm5[s].append(v)
        out["auc_speaker_means"] = round(auc(np.array([np.mean(v) for v in sm6.values()]) * d,
                                             np.array([np.mean(v) for v in sm5.values()]) * d), 4)
        for sx in ("F", "M"):
            p = [v for s, v, r in v608 if r.get("sex") == sx]
            q = [v for s, v, r in v538 if r.get("sex") == sx]
            out[f"auc_sex_{sx}"] = round(auc(np.array(p) * d, np.array(q) * d), 4) if p and q else None
        c538 = [(v, cer(r)) for s, v, r in v538 if cer(r) is not None]
        rr = spearman([x[0] for x in c538], [x[1] for x in c538])
        out["rho_cer_538_report"] = None if rr is None else round(rr, 4)
    return out


def main():
    cmd, raw = sys.argv[1], sys.argv[2]
    rows = load(raw)
    if cmd == "explore":
        ref = {}
        for sx in ("F", "M"):
            v = [r["vq"]["f0_med_hz"] for r in rows if r["set"] == "538" and r["half"] == 0 and r.get("sex") == sx and r["vq"].get("f0_med_hz")]
            ref[sx] = float(np.median(v)) if v else None
        prm = {"sex_ref_hz": ref, "direction": {}, "rho_sign": {}}
        res = {}
        for f in FEATS:
            m = measure(rows, 0, dict(prm, direction={f: 1}), f, detail=False)
            prm["direction"][f] = 1 if (m["auc"] or 0.5) >= 0.5 else -1
            prm["rho_sign"][f] = 1 if (m["rho_cer_608"] or 0) >= 0 else -1
            res[f] = measure(rows, 0, prm, f)
        out = {"params": prm, "explore": res}
        json.dump(out, open(sys.argv[3], "w"), ensure_ascii=False, indent=1)
        print("S24_EXPLORE_OK", json.dumps(prm, ensure_ascii=False))
    elif cmd == "confirm":
        prm = json.load(open(sys.argv[3]))["params"]
        res, verdict = {}, {}
        for f in FEATS:
            m = measure(rows, 1, prm, f)
            ok_auc = m["auc"] is not None and m["auc"] >= AUC_MIN
            ok_rho = m["rho_cer_608"] is not None and abs(m["rho_cer_608"]) >= RHO_MIN and \
                (1 if m["rho_cer_608"] >= 0 else -1) == prm["rho_sign"][f]
            res[f] = m
            verdict[f] = {"auc_ok": ok_auc, "rho_ok": ok_rho, "pass": ok_auc and ok_rho}
        # 보고만: Praat 값과 이 구현의 순위상관(모든 클립), Praat 값의 같은 판정 수치, 잡음 바닥으로 본 녹음 조건 차
        agree = {}
        for f in PRAAT_SAME + ("f0_med_hz",):
            xs = [(r["vq"].get(f), (r.get("praat") or {}).get(f)) for r in rows]
            xs = [(a, b) for a, b in xs if a is not None and b is not None and math.isfinite(a) and math.isfinite(b)]
            agree[f] = {"n": len(xs), "spearman": None if len(xs) < 5 else round(spearman([a for a, _ in xs], [b for _, b in xs]), 4)}
        praat = {f: measure(rows, 1, prm, f, src="praat", detail=False) for f in PRAAT_SAME}
        floor = measure(rows, 1, dict(prm, direction={"floor_db": 1}), "floor_db", detail=False)
        out = {"params": prm, "confirm": res, "verdict": verdict, "praat_agreement_all": agree,
               "praat_confirm_report": praat, "floor_db_report": floor}
        json.dump(out, open(sys.argv[4], "w"), ensure_ascii=False, indent=1)
        print("S24_CONFIRM_OK", json.dumps({f: (res[f]["auc"], res[f]["rho_cer_608"], verdict[f]["pass"]) for f in FEATS}))


if __name__ == "__main__":
    main()
