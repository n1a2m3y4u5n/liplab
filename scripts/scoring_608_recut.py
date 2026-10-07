"""608 문장 조각 정제본으로 말하기 채점 결정 다시 확인(docs/scoring-608-recut-2026-10.md 2·4절). 맥에서 점수 파일만 읽는다.

    python3 scripts/scoring_608_recut.py build RUN_DIR      정제판 폴더(V0a, V1, V1s, V2)의 문장별 CSV를 만든다(저장소 밖)
    python3 scripts/scoring_608_recut.py report RUN_DIR [OUT.json]   집계와 판정(기존 분석 스크립트를 SCORES_DIR만 바꿔 함께 돌린다)

RUN_DIR: 파드에서 받은 liplab-lab/data/pod_runs/<날짜>_<파드>/rc(out/recut.json, dgop_full_recut.jsonl, tscore_recut.jsonl, trim_recut.jsonl,
s4_recut.jsonl, lat_*.json, lp/). 출력 폴더 liplab-lab/data/scores_recut_2026-10-07/<판>/. S18 특성은 backend 가상환경(torch)으로 만든다.
"""
import collections
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zlib

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
LAB = os.path.expanduser("~/Downloads/liplab-lab")
BASE = f"{LAB}/data/scores_2026-10-06"
SC = f"{LAB}/data/pod_runs/20261006_35zrgz6wvrqiho/sc/out"
S4 = f"{LAB}/data/pod_runs/20261007_ubn4h922kfnx03/s4/out"
FV = f"{LAB}/data/pod_runs/20261007_gf8ifdceixcoar/fv"
SS = os.path.expanduser("~/Downloads/KSC2026/liplab/data")       # KSC 세션의 10/7 SpeechSuper 점수(읽기만)
OUTROOT = f"{LAB}/data/scores_recut_2026-10-07"
PY_TORCH = os.path.expanduser("~/Downloads/liplab/backend/.venv/bin/python")
PASS = 65.0
B = 2000
VARIANTS = ("V0a", "V1", "V1s", "V2")
MAX_LEN = 20.0

sys.path.insert(0, HERE)
os.environ.setdefault("SCORES_DIR", BASE)
import scoring_analyses_1006 as SA  # noqa: E402

auc, ff, wp = SA.auc, SA.ff, SA.wp


def hangul(s):
    return re.sub(r"[^가-힣]", "", s or "")


def sid_of(text):
    return "s%08x" % zlib.crc32(hangul(text).encode())


def half_of(spk):
    return zlib.crc32(spk.encode()) % 2


def clip_id(c):
    return f"{c['file'][:-5]}:{c['si']:03d}"


def read_csv(p):
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


def write_csv(p, rows, fields):
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def jl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


# ───────────────────────── 조각 분류(2.1·2.3절) ─────────────────────────
def cut_sets(run=None):
    cuts = [c for c in json.load(open(f"{SC}/cuts608.json", encoding="utf-8")) if c.get("cut")]
    length = {clip_id(c): c["end"] - c["start"] for c in cuts}
    syl = {clip_id(c): len(hangul(c["target"])) for c in cuts}
    long_ = {k for k, v in length.items() if v > MAX_LEN}
    word = {clip_id(c) for c in cuts if clip_id(c) in long_ and "-01-01-" in c["file"]}
    recut = long_ - word
    slow = {k for k in length if k not in long_ and length[k] / max(1, syl[k]) > 1.0}
    acc = {}
    if run and os.path.exists(f"{run}/out/recut.json"):
        acc = {r["clip"]: r for r in json.load(open(f"{run}/out/recut.json")) if r["accepted"]}
    drop = {"V0": set(), "V0a": set(), "V1": long_, "V1s": long_ | slow, "V2": word | (recut - set(acc))}
    return {"all": set(length), "long": long_, "word": word, "recut": recut, "slow": slow, "acc": acc, "drop": drop, "length": length}


# ───────────────────────── build ─────────────────────────
def a2_filter(rows, own_field="own_sid"):
    return [r for r in rows if not (r["label"] in ("other", "cohort") and r["target_sid"] == r[own_field])]


def recut_rows(run, acc):
    """다시 자른 조각의 D-GOP 짝 행과 전사 행(10/6 CSV와 같은 열)."""
    dg, tr = [], []
    own = {}
    for j in jl(f"{run}/out/dgop_full_recut.jsonl"):
        if j["set"] != "608" or j["clip"] not in acc:
            continue
        if j["kind"] == "same":
            own[j["clip"]] = sid_of(j["target"])
    for j in jl(f"{run}/out/dgop_full_recut.jsonl"):
        if j["set"] != "608" or j["clip"] not in acc or "error" in j:
            continue
        label = {"same": "own", "diff": "other"}.get(j["kind"], j["kind"])
        dg.append({"set": "608", "spk": j["spk"], "half": half_of(j["spk"]), "clip": j["clip"], "own_sid": own[j["clip"]],
                   "target_sid": sid_of(j["target"]), "label": label, "score": j["score"], "raw": j["raw"]})
    meta = {r["clip"]: r for r in dg}
    for j in jl(f"{run}/out/tscore_recut.jsonl"):
        if j["set"] != "608" or j["clip"] not in acc:
            continue
        m = meta[j["clip"]]
        tr.append({"set": "608", "spk": m["spk"], "half": m["half"], "clip": j["clip"], "own_sid": m["own_sid"], "target_sid": j["target_sid"],
                   "label": {"same": "own", "diff": "other"}.get(j["kind"], j["kind"]), "r0": j["r0"], "r1": j["r1"], "r0_vad": j["r0_vad"],
                   "r0_c": j["r0_c"]})
    return dg, tr


def recut_features(run, acc):
    tmp = tempfile.mkdtemp(prefix="rc_feat_")
    with open(f"{tmp}/dgop_full.jsonl", "w", encoding="utf-8") as f:
        for j in jl(f"{run}/out/dgop_full_recut.jsonl"):
            if j["set"] == "608" and j["clip"] in acc and j["kind"] in ("same", "diff"):
                f.write(json.dumps(j, ensure_ascii=False) + "\n")
    os.symlink(f"{run}/out/lp", f"{tmp}/lp")
    out = f"{tmp}/feat.csv"
    subprocess.run([PY_TORCH, f"{HERE}/scoring_s18_head.py", "features", tmp, out], check=True,
                   env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    rows = read_csv(out)
    shutil.rmtree(tmp)
    return rows


def bridge(run):
    """다리(3절): b675975 재채점이 10/6 값과 같은가(표시 점수 차 ≤ 0.1, 전사 r0 차 ≤ 0.5)."""
    ref = {}
    for j in jl(f"{SC}/dgop_full.jsonl"):
        if j["set"] in ("538", "608") and j["kind"] in ("same", "diff"):
            ref[(j["set"], j["clip"], j["target"])] = j.get("score")
    tref = {}
    for j in jl(f"{SC}/tscore_dgoppairs.jsonl"):
        tref[(j["set"], j["clip"], j["target_sid"], j["kind"])] = j["r0"]
    d, t = [], []
    for j in jl(f"{run}/out/dgop_full_recut.jsonl"):
        if j["set"].startswith("bridge"):
            st = j["set"][6:]
            if j.get("score") is not None and ref.get((st, j["clip"], j["target"])) is not None:
                d.append(abs(j["score"] - ref[(st, j["clip"], j["target"])]))
    for j in jl(f"{run}/out/tscore_recut.jsonl"):
        if j["set"].startswith("bridge"):
            k = (j["set"][6:], j["clip"], j["target_sid"], j["kind"])
            if k in tref:
                t.append(abs(j["r0"] - tref[k]))
    ok = len(d) == 18 and len(t) == 18 and max(d) <= 0.1 and max(t) <= 0.5
    return {"n_dgop": len(d), "max_dgop_diff": round(max(d), 3) if d else None, "n_tr": len(t),
            "max_r0_diff": round(max(t), 3) if t else None, "ok": bool(ok)}


def cmd_build(run):
    cs = cut_sets(run)
    br = bridge(run)
    print("BRIDGE", br)
    dg0 = read_csv(f"{BASE}/dgop_pairs.csv")
    tr0 = read_csv(f"{BASE}/transcript_pairs.csv")
    p928 = read_csv(f"{BASE}/transcript_proto928.csv")
    f18 = read_csv(f"{BASE}/s18_features.csv")
    own_sid = {(r["set"], r["clip"]): r["target_sid"] for r in f18 if r["label"] == "own"}
    for r in f18:
        r["own_sid"] = own_sid[(r["set"], r["clip"])]
    rdg, rtr = recut_rows(run, cs["acc"]) if cs["acc"] else ([], [])
    rf18 = recut_features(run, cs["acc"]) if cs["acc"] else []
    for r in rf18:
        r["own_sid"] = [x for x in rf18 if x["clip"] == r["clip"] and x["label"] == "own"][0]["target_sid"]
    summary = {"bridge": br}
    for v in VARIANTS:
        drop = cs["drop"][v]
        rep = set(cs["acc"]) if v == "V2" else set()
        out = f"{OUTROOT}/{v}"
        os.makedirs(out, exist_ok=True)
        keep = lambda r: not (r["set"] == "608" and (r["clip"] in drop or r["clip"] in rep))     # noqa: E731
        dg = [r for r in dg0 if keep(r)] + (rdg if v == "V2" else [])
        tr = [r for r in tr0 if keep(r)] + (rtr if v == "V2" else [])
        fe = [r for r in f18 if keep(r)] + (rf18 if v == "V2" else [])
        pp = [r for r in p928 if keep(r)]           # 9/28 짝(전사 재현 확인용)은 다시 자른 조각을 넣지 않는다
        dg, tr, fe = a2_filter(dg), a2_filter(tr), a2_filter(fe)
        write_csv(f"{out}/dgop_pairs.csv", dg, ["set", "spk", "half", "clip", "own_sid", "target_sid", "label", "score", "raw"])
        write_csv(f"{out}/transcript_pairs.csv", tr, ["set", "spk", "half", "clip", "own_sid", "target_sid", "label", "r0", "r1", "r0_vad", "r0_c"])
        write_csv(f"{out}/transcript_proto928.csv", pp, list(p928[0].keys()))
        write_csv(f"{out}/s18_features.csv", fe, ["set", "spk", "half", "clip", "target_sid", "label"] + list(
            k for k in f18[0].keys() if k not in ("set", "spk", "half", "clip", "target_sid", "label", "own_sid")))
        for f in ("s14_pairs.csv", "s14_chips.csv"):
            shutil.copy(f"{BASE}/{f}", f"{out}/{f}")
        own608 = [r for r in dg if r["set"] == "608" and r["label"] == "own"]
        summary[v] = {"608_own": len(own608), "608_spk": len({r["spk"] for r in own608}),
                      "608_other": sum(r["set"] == "608" and r["label"] == "other" for r in dg), "recut_in": len(rep)}
    json.dump(summary, open(f"{OUTROOT}/build_summary.json", "w"), ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


# ───────────────────────── 공통 통계 ─────────────────────────
def boot(rows, stat, seed=0):
    """화자 부트스트랩(세트 안 화자 복원 추출) 95% 구간. rows: spk 키가 있는 행."""
    by = collections.defaultdict(list)
    for r in rows:
        by[r["spk"]].append(r)
    spk = sorted(by)
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(B):
        pick = rng.choice(len(spk), len(spk), replace=True)
        v = stat([r for i in pick for r in by[spk[i]]])
        if v == v:
            vals.append(v)
    return [round(float(np.percentile(vals, 2.5)), 4), round(float(np.percentile(vals, 97.5)), 4)]


def load_variant(v):
    SA.D = f"{OUTROOT}/{v}"
    return SA.joined()


def rows608(rows, half=None):
    return [r for r in rows if r["set"] == "608" and r["label"] in ("own", "other") and (half is None or r["half"] == half)]


def auc_of(field):
    return lambda rs: auc([r[field] for r in rs if r["label"] == "own"], [r[field] for r in rs if r["label"] == "other"])


def ff_of(field, t):
    return lambda rs: ff([r[field] for r in rs if r["label"] == "own"], t)


def wp_of(field, t):
    return lambda rs: wp([r[field] for r in rs if r["label"] == "other"], t)


def same_strictness(rows, field):
    o538 = [r[field] for r in rows if r["set"] == "538" and r["label"] == "other" and r[field] is not None]
    for t in range(0, 101):
        if wp(o538, t) <= 0.05:
            return t
    return 100


def metric(rs, fn):
    return [round(float(fn(rs)), 4)] + boot(rs, fn)


# ───────────────────────── report ─────────────────────────
def run_existing(v):
    env = dict(os.environ, SCORES_DIR=f"{OUTROOT}/{v}", PYTHONDONTWRITEBYTECODE="1")
    for args in (["scoring_analyses_1006.py", "s19"], ["scoring_analyses_1006.py", "s15", "explore"], ["scoring_analyses_1006.py", "s15", "confirm"],
                 ["scoring_analyses_1006.py", "s1", "explore"], ["scoring_analyses_1006.py", "s1", "confirm"],
                 ["scoring_s18_head.py", "explore"], ["scoring_s18_head.py", "confirm"]):
        subprocess.run([sys.executable, f"{HERE}/{args[0]}"] + args[1:], check=True, env=env, stdout=subprocess.DEVNULL)
    d = f"{OUTROOT}/{v}"
    return {k: json.load(open(f"{d}/{k}.json")) for k in ("s19_result", "s15_confirm", "s1_confirm", "s18_confirm", "s15_explore", "s18_explore")}


def frozen_s15(rows):
    p = json.load(open(f"{BASE}/s15_params.json"))
    f1, _ = SA.make_fusers(p)
    rs = [r for r in rows if r["half"] == 1 and r["label"] in ("own", "other") and r["r0c"] is not None]
    noise = [r for r in rows if r["label"] == "noise"]
    o = {}
    for st in ("538", "608"):
        own = [f1(r) for r in rs if r["set"] == st and r["label"] == "own"]
        oth = [f1(r) for r in rs if r["set"] == st and r["label"] == "other"]
        o[st] = {"auc": round(auc(own, oth), 4), "ff": round(ff(own, p["thr_f1"]), 4), "wp": round(wp(oth, p["thr_f1"]), 4)}
    o["noise_pass"] = int(sum(f1(r) >= p["thr_f1"] for r in noise))
    return o


def frozen_s18(v):
    p = json.load(open(f"{BASE}/s18_params.json"))
    mu, sd, w = np.array(p["mu"]), np.array(p["sd"]), np.array(p["w"])
    rows = read_csv(f"{OUTROOT}/{v}/s18_features.csv")
    o = {}
    for st in ("538", "608"):
        rs = [r for r in rows if r["set"] == st and int(r["half"]) == 1]
        hv = lambda r: float(1 / (1 + np.exp(-(w[0] + w[1:] @ ((np.array([float(r[k]) for k in p["feats"]]) - mu) / sd)))))   # noqa: E731
        own = [hv(r) for r in rs if r["label"] == "own"]
        oth = [hv(r) for r in rs if r["label"] == "other"]
        o[st] = {"auc": round(auc(own, oth), 4), "wp": round(wp(oth, p["thr"]), 4), "n_other": len(oth), "n_wp": int(sum(x >= p["thr"] for x in oth)),
                 "ff": round(ff(own, p["thr"]), 4)}
    return o


def speechsuper(rows):
    """KSC 10/7 SpeechSuper overall(같은 10/6 조각). 다시 자른 조각에는 점수가 없으므로 그 조각은 뺀다."""
    ss = {}
    for i in range(3):
        p = f"{SS}/ss_out_{i}.jsonl"
        if not os.path.exists(p):
            return None
        for j in jl(p):
            if j.get("status") != "ok":
                continue
            st, clip, label, tsid = j["tag"].split("|")
            ss[(st, clip, label, tsid)] = float(j["result"]["overall"])
    return ss


def ss_report(v, ss, acc):
    SA.D = f"{OUTROOT}/{v}"
    dg = SA.load("dgop_pairs.csv")
    rs = []
    for r in dg:
        if r["label"] not in ("own", "other") or r["set"] not in ("538", "608"):
            continue
        if r["set"] == "608" and v == "V2" and r["clip"] in acc:
            continue
        k = (r["set"], r["clip"], r["label"], r["target_sid"])
        if k in ss and r["score"] not in ("", "None"):
            rs.append({"set": r["set"], "spk": r["spk"], "half": int(r["half"]), "clip": r["clip"], "label": r["label"], "ss": ss[k], "dg": float(r["score"])})
    t_ss = same_strictness(rs, "ss")
    t_dg = same_strictness(rs, "dg")
    r608 = [r for r in rs if r["set"] == "608"]
    out = {"n608_own": sum(r["label"] == "own" for r in r608), "n608_other": sum(r["label"] == "other" for r in r608),
           "n608_spk": len({r["spk"] for r in r608}), "n538_clips": len({r["clip"] for r in rs if r["set"] == "538"}),
           "thr_ss": t_ss, "thr_dg_on_ss538": t_dg,
           "auc_ss": metric(r608, auc_of("ss")), "auc_dg": metric(r608, auc_of("dg")),
           "auc_diff_ss_minus_dg": metric(r608, lambda x: auc_of("ss")(x) - auc_of("dg")(x)),
           "ss_ff_thr": metric(r608, ff_of("ss", t_ss)), "ss_wp_thr": metric(r608, wp_of("ss", t_ss)),
           "auc_ss_half": [round(auc_of("ss")([r for r in r608 if r["half"] == h]), 4) for h in (0, 1)]}
    lo, hi = out["auc_diff_ss_minus_dg"][1:]
    out["verdict"] = "그대로" if lo > 0 else ("바뀜" if hi < 0 else "판정 불가")
    return out


def trim_report(v, run, cs):
    """D11: 끝 자르기 전(R)·후(R_trim50)의 608 짝 점수."""
    rec = {}
    for f in (f"{FV}/merged/main.jsonl", f"{FV}/mainfix.jsonl"):     # mainfix가 30초 넘는 32조각을 고친 값
        for j in jl(f):
            if j["set"] == "608" and j["variant"] in ("R", "R_trim50"):
                rec[(j["variant"], j["clip"])] = j
    out_rows = {"R": [], "T": []}
    drop = cs["drop"][v]
    acc = cs["acc"] if v == "V2" else {}
    for (var, clip), j in rec.items():
        if clip in drop or clip in acc:
            continue
        own = hangul([t for t in j["targets"] if t["kind"] == "same"][0]["target"])
        for t in j["targets"]:
            if t["kind"] == "diff" and hangul(t["target"]) == own:
                continue
            out_rows["R" if var == "R" else "T"].append({"spk": j["spk"], "half": j["half"], "label": "own" if t["kind"] == "same" else "other",
                                                         "s": t["score"] if t["score"] is not None else 0.0})
    if acc:
        own = {}
        for j in jl(f"{run}/out/dgop_full_recut.jsonl"):
            if j["set"] == "608" and j["clip"] in acc and j["kind"] == "same":
                own[j["clip"]] = hangul(j["target"])
        for name, path in (("R", f"{run}/out/dgop_full_recut.jsonl"), ("T", f"{run}/out/trim_recut.jsonl")):
            for j in jl(path):
                if j["set"] != "608" or j["clip"] not in acc or j["kind"] not in ("same", "diff"):
                    continue
                if j["kind"] == "diff" and hangul(j["target"]) == own[j["clip"]]:
                    continue
                out_rows[name].append({"spk": j["spk"], "half": half_of(j["spk"]), "label": "own" if j["kind"] == "same" else "other",
                                       "s": j.get("score") if j.get("score") is not None else 0.0})
    res = {}
    for name, rs in out_rows.items():
        h1 = [r for r in rs if r["half"] == 1]
        res[name] = {"n_own": sum(r["label"] == "own" for r in rs), "auc_all": metric(rs, auc_of("s")), "auc_h1": round(auc_of("s")(h1), 4),
                     "ff65_h1": round(ff_of("s", PASS)(h1), 4), "wp65_h1": round(wp_of("s", PASS)(h1), 4), "ff65_all": round(ff_of("s", PASS)(rs), 4)}
    c2 = res["T"]["auc_h1"] >= res["R"]["auc_h1"] - 0.01
    c3 = res["T"]["ff65_h1"] <= res["R"]["ff65_h1"] + 0.02 and res["T"]["wp65_h1"] <= 0.05
    res["C2"], res["C3"] = bool(c2), bool(c3)
    res["verdict"] = "그대로" if c2 and c3 else "바뀜"
    return res


def s4_report(v, run, cs):
    import s4_analyze as SX
    drop = cs["drop"][v]
    acc = cs["acc"] if v == "V2" else {}
    ref_raw = [r for r in jl(f"{SC}/dgop_full.jsonl") if not (r["set"] == "608" and (r["clip"] in drop or r["clip"] in acc))]
    stu_raw = [r for r in jl(f"{S4}/e1_H.jsonl") if not (r["set"] == "608" and (r["clip"] in drop or r["clip"] in acc))]
    if acc:
        ref_raw += [r for r in jl(f"{run}/out/dgop_full_recut.jsonl") if r["set"] == "608" and r["clip"] in acc]
        stu_raw += [r for r in jl(f"{run}/out/s4_recut.jsonl") if r["set"] == "608" and r["clip"] in acc]
    ref = SX.e1_rows(ref_raw, "score")
    stu = SX.e1_rows(stu_raw, "raw")
    t608 = auc(SX.sel(ref, "608", "own"), SX.sel(ref, "608", "other"))
    s608 = auc(SX.sel(stu, "608", "own"), SX.sel(stu, "608", "other"))
    tau, q, got = SX.matched_tau(stu, ref)
    wp538 = float(np.mean(np.array(SX.sel(stu, "538", "other")) >= tau))
    out = {"n608_own": len(SX.sel(stu, "608", "own")), "teacher_608_auc": round(t608, 4), "student_608_auc": round(s608, 4),
           "C1": bool(s608 >= t608 - 0.01), "auc_diff_ci": [round(x, 4) for x in SX.boot_auc_diff(stu, ref)],
           "tau": round(tau, 2), "q": round(q, 4), "538_wp_tau": round(wp538, 4), "C2": bool(wp538 <= 0.05),
           "608_wp_tau": round(float(np.mean(np.array(SX.sel(stu, "608", "other")) >= tau)), 4)}
    # C3: E2를 다시 돌리지 않으므로 조각 제외(V1)로만
    d = json.load(open(f"{S4}/e2_H.json"))
    bad = {c.replace(":", "_") + ".wav" for c in cs["drop"]["V1"]} if v != "V0a" else set()
    tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump([r for r in d if not (r["group"] == "608" and r["path"] in bad)], tmp)
    tmp.close()
    c3 = SX.cons_decisions(tmp.name)
    os.unlink(tmp.name)
    out["C3_min"] = c3["min"]
    out["C3"] = bool(c3["pass"])
    out["C3_608"] = {k: c3[k]["auc"] for k in c3 if k.startswith("608:") and "보고" not in k}
    out["C4"] = True
    lat = {}
    for name in ("L0", "L1", "L1v1", "L2"):
        p = f"{run}/out/lat_{name}.json"
        if os.path.exists(p):
            L = json.load(open(p))
            secs = np.array([r["sec"] for r in L["rows"]])
            aud = np.array([r["audio_s"] for r in L["rows"]])
            lat[name] = {"n": L["n"], "median": round(L["median"], 3), "p95": round(L["p95"], 3), "max": round(L["max"], 3),
                         "max_audio_s": round(float(aud.max()), 2), "n_over_20s": int((aud > 20).sum()), "cpu": L["cpu"],
                         "p95_le10s": round(float(np.percentile(secs[aud <= 10], 95)), 3)}
    out["latency"] = lat
    if "L0" in lat:
        b = lat["L0"]["p95"]
        out["latency_bridge_ok"] = bool(3.56 <= b <= 4.82)
        key = "L1" if v == "V2" else "L1v1"
        if key in lat:
            out["C5_p95"] = lat[key]["p95"]
            out["C5"] = bool(lat[key]["p95"] <= 3.0)
            out["C5_scaled_ref"] = round(lat[key]["p95"] / b * 4.19, 3)
    return out


def decisions(v, rows, cs):
    r = rows608(rows)
    h1 = rows608(rows, 1)
    res = {}
    # D-GOP·전사 기본 수치
    t57 = same_strictness([x for x in rows if x["label"] in ("own", "other")], "dg")
    res["basic"] = {
        "n_own": sum(x["label"] == "own" for x in r), "n_other": sum(x["label"] == "other" for x in r), "n_spk": len({x["spk"] for x in r}),
        "n_spk_h1": len({x["spk"] for x in h1}), "n_own_h1": sum(x["label"] == "own" for x in h1),
        "dg_auc": metric(r, auc_of("dg")), "dg_auc_h0": round(auc_of("dg")(rows608(rows, 0)), 4), "dg_auc_h1": round(auc_of("dg")(h1), 4),
        "dg_ff65": metric(r, ff_of("dg", PASS)), "dg_wp65": metric(r, wp_of("dg", PASS)),
        "thr_same_strictness": t57, "dg_ff57": metric(r, ff_of("dg", t57)), "dg_wp57": metric(r, wp_of("dg", t57)),
        "tr_r0c_auc": metric([x for x in r if x["r0c"] is not None], auc_of("r0c")),
        "tr_r0_auc": round(auc_of("r0")([x for x in r if x["r0"] is not None]), 4),
        "tr_r0c_ff65": round(ff_of("r0c", PASS)([x for x in r if x["r0c"] is not None]), 4),
        "dg_median_own": round(float(np.median([x["dg"] for x in r if x["label"] == "own"])), 1)}
    # D1 숙달 문턱
    p1 = 1 - ff_of("dg", PASS)(h1)
    ci = boot(h1, lambda rs: 100 * (1 - ff_of("dg", PASS)(rs)) - 5)
    v1 = int(round(100 * p1 - 5))
    res["D1"] = {"pass_h1": round(p1, 4), "rule_value": round(100 * p1 - 5, 2), "v": v1, "ci": ci, "verdict": "그대로" if v1 == 68 else "바뀜"}
    by = collections.defaultdict(list)
    for x in r:
        if x["label"] == "own":
            by[x["spk"]].append(x["dg"] >= PASS)
    rates = sorted(round(float(np.mean(b)), 2) for b in by.values() if len(b) >= 13)
    res["D1"]["spk_passrate_n13plus"] = rates
    res["D1"]["n_spk_below_rule"] = sum(x < v1 / 100 for x in rates)
    res["D1"]["n_spk_below_68"] = sum(x < 0.68 for x in rates)
    # D2 합격선 65(2-1 규칙: 538만)
    h0_538 = [x["dg"] for x in rows if x["set"] == "538" and x["label"] == "other" and x["half"] == 0]
    h1_538 = [x["dg"] for x in rows if x["set"] == "538" and x["label"] == "other" and x["half"] == 1]
    t = next(float(g) for g in np.round(np.arange(0, 100.0001, 0.1), 1) if wp(h0_538, g) <= 0.05)
    res["D2"] = {"t_h0": t, "wp538_h1_at_t": round(wp(h1_538, t), 4), "confirmed": bool(wp(h1_538, t) <= 0.05),
                 "ff608_at_t": round(ff_of("dg", t)(r), 4), "verdict": "그대로" if not wp(h1_538, t) <= 0.05 else "바뀜"}
    # 보고만(사후, 등록 밖): 2-1 규칙에 608 다른 문장 합격 ≤ 5%를 더한 판(S15·S1·S18의 lowest_threshold와 같은 정의)
    h0r = [x for x in rows if x["half"] == 0 and x["label"] in ("own", "other")]
    h1r = [x for x in rows if x["half"] == 1 and x["label"] in ("own", "other")]
    tb = SA.lowest_threshold(np.round(np.arange(0, 100.0001, 0.1), 1), lambda x: x["dg"], h0r)
    oo = lambda rs, st, lab: [x["dg"] for x in rs if x["set"] == st and x["label"] == lab]     # noqa: E731
    res["D2_both_report"] = {"t_h0": tb, "wp538_h1": round(wp(oo(h1r, "538", "other"), tb), 4), "wp608_h1": round(wp(oo(h1r, "608", "other"), tb), 4),
                             "ff608_h1": round(ff(oo(h1r, "608", "own"), tb), 4), "ff608_all": round(ff(oo(r, "608", "own"), tb), 4),
                             "ff608_at_t21_all": round(ff_of("dg", t)(r), 4), "wp608_at_t21_all": round(wp_of("dg", t)(r), 4)}
    # D3 개인 향상 경로 근거
    f = res["basic"]["dg_ff65"]
    res["D3"] = {"ff65": f, "verdict": "그대로" if f[1] > 0.10 else ("판정 불가" if f[0] > 0.10 else "바뀜")}
    return res


def cmd_report(run, out_json=None):
    cs = cut_sets(run)
    ss = speechsuper(None)
    res = {"sets": {"long": len(cs["long"]), "word": len(cs["word"]), "recut": len(cs["recut"]), "recut_accepted": len(cs["acc"]),
                    "slow_extra_V1s": len(cs["slow"])},
           "build": json.load(open(f"{OUTROOT}/build_summary.json"))}
    if os.path.exists(f"{run}/out/recut.json"):
        rc = json.load(open(f"{run}/out/recut.json"))
        res["recut_detail"] = {"accepted": sum(r["accepted"] for r in rc), "reasons": collections.Counter(r.get("reason", "") for r in rc if not r["accepted"]),
                               "len_median": round(float(np.median([r["length"] for r in rc if r["accepted"]])), 2) if cs["acc"] else None,
                               "len_max": round(float(max(r["length"] for r in rc if r["accepted"])), 2) if cs["acc"] else None,
                               "ratio_median": round(float(np.median([r["ratio"] for r in rc if r["accepted"]])), 3) if cs["acc"] else None,
                               "ratio_vs_orig_median": round(float(np.median([r["ratio"] - r["orig_ratio"] for r in rc if r["accepted"]])), 3) if cs["acc"] else None}
    SA.D = BASE
    res["V0"] = {"D": decisions("V0", SA.joined(), cs)}
    for v in VARIANTS:
        rows = load_variant(v)
        res[v] = {"D": decisions(v, rows, cs), "existing": run_existing(v), "S15_frozen_h1": frozen_s15(rows), "S18_frozen_h1": frozen_s18(v)}
        if v in ("V0a", "V1", "V2"):
            res[v]["D11_trim"] = trim_report(v, run, cs)
            res[v]["D4_S4"] = s4_report(v, run, cs)
            if ss:
                res[v]["D10_speechsuper"] = ss_report(v, ss, cs["acc"])
    print(json.dumps(res, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    if out_json:
        json.dump(res, open(out_json, "w"), ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))


if __name__ == "__main__":
    if sys.argv[1] == "build":
        cmd_build(sys.argv[2])
    elif sys.argv[1] == "report":
        cmd_report(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
