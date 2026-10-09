"""Praat식 CPPS 재등록 판정(608 새 화자 18명). 사전 등록 docs/speak-cues-rereg-2026-10.md 2절.

  python cpps_newspk.py extract OUT_FEATS.jsonl [--procs 4]     클립별 CPPS·말소리 창 비율(CER은 읽지 않음)
  python cpps_newspk.py judge FEATS.jsonl OUT.json              판정(S20의 base·large-v3 전사와 잡음 바닥을 읽는다)

자료: S20 묶음 N(KSC 컷, ~/Downloads/liplab-lab/data/s20_stage/root/data/clips/N, 읽기만).
전사·잡음 바닥: ~/Downloads/liplab-lab/data/pod_runs/20261009_mw1qp1djnxt56q/s20/out/{asr_base,asr_v3,acoustic}.jsonl.
출력 JSON은 집계만 담고 화자 ID는 넣지 않는다.
"""
import argparse, json, math, os, re, sys, zlib
from collections import defaultdict
from multiprocessing import Pool

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "backend"))
import voice_quality as vq  # noqa: E402

HOME = os.path.expanduser("~/Downloads")
S20 = f"{HOME}/liplab-lab/data/s20_stage/root/data"
S20OUT = f"{HOME}/liplab-lab/data/pod_runs/20261009_mw1qp1djnxt56q/s20/out"
DUR = (0.4, 15.0)
RHO_MAX, PARTIAL_MAX = -0.30, -0.20
NBOOT = 2000


def speech_fraction(y, sr=16000):
    """25ms 창·10ms 간격 RMS가 최댓값 −30dB 이상인 창의 비율."""
    w, h = int(0.025 * sr), int(0.010 * sr)
    if len(y) < w:
        return None
    db = np.array([20 * np.log10(np.sqrt(np.mean(y[i:i + w] ** 2)) + 1e-12) for i in range(0, len(y) - w + 1, h)])
    return float(np.mean(db >= db.max() - 30.0))


def ejob(c):
    import soundfile as sf
    y, sr = sf.read(f"{S20}/{c['path']}", dtype="float64", always_2d=True)
    y = y.mean(axis=1)
    assert sr == 16000
    return {"clip": c["clip"], "spk": c["spk"], "sex": c["sex"], "dur": round(len(y) / sr, 3),
            "cpps": vq.cpps_praat(y), "cpps_speech": vq.cpps_praat(y, speech_only=True),
            "cpps_old": vq.cpps(y), "speech_frac": speech_fraction(y)}


# ── 통계 ──
def rank(x):
    x = np.asarray(x, float)
    o = np.argsort(x, kind="mergesort")
    r = np.empty(len(x))
    i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and x[o[j + 1]] == x[o[i]]:
            j += 1
        r[o[i:j + 1]] = (i + j) / 2.0
        i = j + 1
    return r


def spearman(a, b):
    a, b = rank(a), rank(b)
    if len(a) < 5 or a.std() == 0 or b.std() == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def partial(a, b, covs):
    """순위 편상관: rank(a)·rank(b)를 [1, rank(공변량)…]에 최소제곱 회귀한 잔차의 피어슨 상관."""
    ra, rb = rank(a), rank(b)
    X = np.column_stack([np.ones(len(ra))] + [rank(c) for c in covs])
    ea = ra - X @ np.linalg.lstsq(X, ra, rcond=None)[0]
    eb = rb - X @ np.linalg.lstsq(X, rb, rcond=None)[0]
    if ea.std() == 0 or eb.std() == 0:
        return None
    return float(np.corrcoef(ea, eb)[0, 1])


def boot(rows, fn, n=NBOOT, seed=0):
    """화자 단위 부트스트랩 95% 구간."""
    rng = np.random.default_rng(seed)
    by = defaultdict(list)
    for r in rows:
        by[r["spk"]].append(r)
    ks = sorted(by)
    out = []
    for _ in range(n):
        s = [r for k in rng.choice(ks, len(ks)) for r in by[k]]
        v = fn(s)
        if v is not None and math.isfinite(v):
            out.append(v)
    return [round(float(np.percentile(out, 2.5)), 4), round(float(np.percentile(out, 97.5)), 4)] if out else None


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


def cer(ref, hyp):
    ref, hyp = norm(ref), norm(hyp)
    return lev(ref, hyp) / len(ref) if ref and hyp is not None else None


def jl(p):
    return {d["clip"]: d for d in (json.loads(l) for l in open(p, encoding="utf-8"))}


def r4(v):
    return None if v is None else round(v, 4)


def judge(feats_path, out_path):
    feats = jl(feats_path)
    clips = {c["clip"]: c for c in json.load(open(f"{S20}/clips.json", encoding="utf-8")) if c["set"] == "N"}
    base, v3, ac = jl(f"{S20OUT}/asr_base.jsonl"), jl(f"{S20OUT}/asr_v3.jsonl"), jl(f"{S20OUT}/acoustic.jsonl")
    allrows = []
    for k, f in feats.items():
        c = clips[k]
        allrows.append(dict(f, cer=cer(c["target"], base[k]["text"]), cer_v3=cer(c["target"], v3[k]["text"]),
                            nf=ac[k]["nf"], snrp=ac[k]["snrp"], nsyl=len(norm(c["target"]))))
    ok = [r for r in allrows if r["cpps"] is not None and r["cer"] is not None and r["nf"] is not None]
    rows = [r for r in ok if DUR[0] <= r["dur"] <= DUR[1]]

    def rho(x, y="cer"):
        return lambda s: spearman([r[x] for r in s], [r[y] for r in s])

    def prt(x, covs, y="cer"):
        return lambda s: partial([r[x] for r in s], [r[y] for r in s], [[r[c] for r in s] for c in covs])

    p1 = rho("cpps")(rows)
    p1ci = boot(rows, rho("cpps"))
    p2 = prt("cpps", ["nf", "snrp"])(rows)
    p2ci = boot(rows, prt("cpps", ["nf", "snrp"]))
    v = {"P1": bool(p1 is not None and p1 <= RHO_MAX and p1ci and p1ci[1] < 0),
         "P2": bool(p2 is not None and p2 <= PARTIAL_MAX and p2ci and p2ci[1] < 0)}
    v["pass"] = v["P1"] and v["P2"]
    # 보고만
    sp = defaultdict(list)
    for r in rows:
        sp[r["spk"]].append(r)
    spk_mean = [{k: float(np.mean([r[k] for r in rs])) for k in ("cpps", "cer", "cer_v3", "nf")} for rs in sp.values()]
    cen = []
    for rs in sp.values():
        mc, me = np.mean([r["cpps"] for r in rs]), np.mean([r["cer"] for r in rs])
        cen += [{"spk": r["spk"], "cpps": r["cpps"] - mc, "cer": r["cer"] - me} for r in rs]
    sp_rho = spearman([m["cpps"] for m in spk_mean], [m["cer"] for m in spk_mean])
    rep = {
        "rho_cer_v3": r4(rho("cpps", "cer_v3")(rows)), "rho_cer_v3_ci": boot(rows, rho("cpps", "cer_v3")),
        "partial_v3_nf_snrp": r4(prt("cpps", ["nf", "snrp"], "cer_v3")(rows)),
        "partial_nf_only": r4(prt("cpps", ["nf"])(rows)),
        "partial_nf_snrp_speechfrac": r4(prt("cpps", ["nf", "snrp", "speech_frac"])(rows)),
        "partial_nf_snrp_speechfrac_ci": boot(rows, prt("cpps", ["nf", "snrp", "speech_frac"])),
        "rho_cpps_speech_only": r4(rho("cpps_speech")(rows)), "rho_cpps_speech_only_ci": boot(rows, rho("cpps_speech")),
        "partial_cpps_speech_only_nf_snrp": r4(prt("cpps_speech", ["nf", "snrp"])(rows)),
        "rho_cpps_old_s24": r4(rho("cpps_old")(rows)),
        "rho_speechfrac_cer": r4(rho("speech_frac")(rows)), "rho_nf_cer": r4(rho("nf")(rows)), "rho_snrp_cer": r4(rho("snrp")(rows)),
        "rho_cpps_nf": r4(rho("cpps", "nf")(rows)), "rho_cpps_snrp": r4(rho("cpps", "snrp")(rows)),
        "rho_cpps_speechfrac": r4(rho("cpps", "speech_frac")(rows)), "rho_cpps_nsyl": r4(rho("cpps", "nsyl")(rows)),
        "speaker_level_rho": r4(sp_rho), "speaker_level_rho_v3": r4(spearman([m["cpps"] for m in spk_mean], [m["cer_v3"] for m in spk_mean])),
        "speaker_level_partial_nf": r4(partial([m["cpps"] for m in spk_mean], [m["cer"] for m in spk_mean], [[m["nf"] for m in spk_mean]])),
        "within_speaker_rho": r4(spearman([r["cpps"] for r in cen], [r["cer"] for r in cen])),
        "within_speaker_rho_ci": boot(cen, lambda s: spearman([r["cpps"] for r in s], [r["cer"] for r in s])),
        "all_durations_rho": r4(rho("cpps")(ok)), "all_durations_partial": r4(prt("cpps", ["nf", "snrp"])(ok)), "n_all_durations": len(ok),
        "by_sex": {sx: {"n": len(s), "n_spk": len({r["spk"] for r in s}), "rho": r4(rho("cpps")(s))}
                   for sx in ("F", "M") for s in [[r for r in rows if r["sex"] == sx]]},
        "describe": {k: [round(float(np.percentile([r[k] for r in rows], q)), 3) for q in (5, 50, 95)]
                     for k in ("cpps", "cpps_speech", "speech_frac", "cer", "cer_v3", "nf", "snrp", "dur")},
    }
    out = {"n": len(rows), "n_spk": len(sp), "P1_rho": r4(p1), "P1_ci": p1ci, "P2_partial_nf_snrp": r4(p2), "P2_ci": p2ci,
           "verdict": v, "report": rep, "thresholds": {"P1": RHO_MAX, "P2": PARTIAL_MAX}}
    json.dump(out, open(out_path, "w"), ensure_ascii=False, indent=1)
    print("CPPS_JUDGE_OK", json.dumps({k: out[k] for k in ("n", "n_spk", "P1_rho", "P1_ci", "P2_partial_nf_snrp", "P2_ci", "verdict")}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd")
    ap.add_argument("a")
    ap.add_argument("b", nargs="?")
    ap.add_argument("--procs", type=int, default=4)
    a = ap.parse_args()
    if a.cmd == "extract":
        cl = [c for c in json.load(open(f"{S20}/clips.json", encoding="utf-8")) if c["set"] == "N"]
        with Pool(a.procs) as p:
            res = p.map(ejob, cl, chunksize=4)
        with open(a.a, "w", encoding="utf-8") as f:
            for r in res:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print("CPPS_EXTRACT_OK", len(res), sum(r["cpps"] is None for r in res))
    elif a.cmd == "judge":
        judge(a.a, a.b)


if __name__ == "__main__":
    main()
