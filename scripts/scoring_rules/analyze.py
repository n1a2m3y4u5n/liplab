"""맥: 문장 점수 규칙 후보 집계·판정(docs/scoring-rules-2026-10.md 3~6절). 집계 수치만 출력한다(문장별 값은 저장소 밖).

    python scripts/scoring_rules/analyze.py explore FEAT_EXPLORE.jsonl OUT.json
    python scripts/scoring_rules/analyze.py confirm FEAT_CONFIRM.jsonl FEAT_B2.jsonl OUT.json   (frozen.json을 읽는다)
    python scripts/scoring_rules/analyze.py selftest
"""
import json
import math
import os
import random
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, "..", ".."))
LAB = os.path.expanduser("~/Downloads/LIPLAB_ALL/liplab-lab")
TRIM27 = f"{LAB}/data/pod_runs/20261009_0b7hmamwk96ebn/c27/out/trim.jsonl"
NSNEW = f"{LAB}/data/pod_runs/20261009_o11jkbqreech6s/ns/out/dgop_new.jsonl"
FROZEN = f"{HERE}/frozen.json"
PASS = 65.0
B, SEED = 2000, 20261015
OP_TARGET = 0.04
LEN_BINS = (0, 20, 35, 50, 10 ** 9)
KAPPAS, COUNTS = (0.3, 0.5, 0.7, 0.9), (1, 2)
SUBS = ("min", "min2")
SPECIAL = {"|", "<unk>", "<pad>"}


# ───────────────────────── 특성 ─────────────────────────
def final_cut(tokens):
    idx = [i for i, t in enumerate(tokens) if (t or "").startswith("n:")]
    if not idx:
        return len(tokens)
    i = idx[-1]
    return i - 1 if i > 0 and (tokens[i - 1] or "").startswith("o:") else i


def lev(a, b):
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def quantile(xs, q):
    """선형 보간 분위수(numpy 기본과 같다)."""
    if not xs:
        return None
    s = sorted(xs)
    pos = (len(s) - 1) * q
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def spk_key(set_, spk):
    if set_ == "c27b1" and spk in ("27-KHY-F-28", "27-KHY-F-29"):
        return "27-KHY-F-28|29"
    return f"{set_}:{spk}"


def features(r, clip):
    ph = r["phones"]
    toks = [p.get("token") or "" for p in ph]
    cut = final_cut(toks)
    scored = [(i, p) for i, p in enumerate(ph) if p.get("aligned") and p.get("scorable") and not p.get("silent_h")
              and p.get("dgop") is not None]
    nonfinal = [p["dgop"] for i, p in scored if i < cut]
    f = {"m": len(scored)}
    S = len(toks)
    for name in ("sc", "al"):
        c, b = r["ll"][name]
        f[f"lr_{name}_T"] = None if c is None else (c - b) / max(1, r["T"])
        f[f"lr_{name}_S"] = None if c is None else (c - b) / max(1, S)
    tgt = [t for t in toks if t not in SPECIAL]
    for name in ("sc", "al"):
        g = [t for t in (clip.get(f"g_{name}") or "").split() if t not in SPECIAL] if clip else None
        f[f"per_{name}"] = None if g is None or not tgt else lev(g, tgt) / len(tgt)
    f["q10"] = quantile(nonfinal, 0.10)
    f["q25"] = quantile(nonfinal, 0.25)
    ev = {}
    for k in KAPPAS:
        ev[k] = sum(1 for i, p in scored if i < cut and toks[i].startswith("o:") and p.get("cmp")
                    and p["cmp"][1] >= k and p["cmp"][1] > p["dgop"])
    f["ev"] = ev
    return f


def load(path):
    rows, clips, errs = [], {}, Counter()
    for l in open(path, encoding="utf-8"):
        j = json.loads(l)
        if j.get("rec") == "clip":
            clips[(j["set"], j["clip"])] = j
        elif j.get("rec") == "t":
            if "error" in j or j.get("score") is None:
                errs[j["set"]] += 1
                continue
            rows.append(j)
    out = []
    for r in rows:
        r["f"] = features(r, clips.get((r["set"], r["clip"])))
        r["pass"] = r["score"] >= PASS
        r["sk"] = spk_key(r["set"], r["spk"])
        r["grp"] = r["clip"].split(":")[0].split("-")[6] if r["set"].startswith("c27") else ""
        out.append(r)
    return out, errs


# ───────────────────────── 후보 ─────────────────────────
GATES = [("G-LR(sc,T)", "lr_sc_T", "ge"), ("G-LR(sc,S)", "lr_sc_S", "ge"), ("G-LR(al,T)", "lr_al_T", "ge"),
         ("G-LR(al,S)", "lr_al_S", "ge"), ("G-PER(sc)", "per_sc", "le"), ("G-PER(al)", "per_al", "le"),
         ("G-Q(0.1)", "q10", "ge"), ("G-Q(0.25)", "q25", "ge")]
HOLDS = [(f"H({k},{c})", k, c) for k in KAPPAS for c in COUNTS]


def len_bin(m):
    for i in range(len(LEN_BINS) - 1):
        if LEN_BINS[i] <= m < LEN_BINS[i + 1]:
            return i
    return len(LEN_BINS) - 2


def blocks(cand, r):
    """지금 합격인 시도를 후보가 합격에서 빼는가(불합격 시도에는 작용하지 않는다)."""
    if not r["pass"]:
        return False
    kind, a, b = cand
    f = r["f"]
    if kind == "gate":
        key, op, thr = a, b[0], b[1]
        v = f[key]
        if v is None:
            return False                              # 특성을 못 내면 지금 판정 그대로
        return not (v >= thr if op == "ge" else v <= thr)
    if kind == "len":
        return r["score"] < a[len_bin(f["m"])]
    if kind == "hold":
        return f["ev"][a] >= b
    raise ValueError(kind)


def fit_gate(rows27, key, op):
    others = [r for r in rows27 if r["kind"] == "other"]
    n = len(others)
    kmax = int(math.floor(OP_TARGET * n + 1e-9))
    vals = sorted({r["f"][key] for r in others if r["pass"] and r["f"][key] is not None})
    passing = [r["f"][key] for r in others if r["pass"]]
    none_pass = sum(1 for v in passing if v is None)       # 특성 없는 행은 관문이 막지 못한다
    order = vals if op == "ge" else vals[::-1]               # 느슨한 쪽부터
    for v in order:
        c = none_pass + sum(1 for x in passing if x is not None and (x >= v if op == "ge" else x <= v))
        if c <= kmax:
            return v
    return None


def fit_len(rows608):
    others = [r for r in rows608 if r["kind"] == "other"]
    out = []
    for b in range(len(LEN_BINS) - 1):
        ob = [r for r in others if len_bin(r["f"]["m"]) == b]
        t = PASS
        while ob and sum(1 for r in ob if r["score"] >= t) > OP_TARGET * len(ob) and t < 100:
            t += 0.5
        out.append(t)
    return out


# ───────────────────────── 지표·구간 ─────────────────────────
def units(rows, cand):
    """화자마다 (FH 분자·분모, OP 분자, OP65 분자, OP 분모, CS 분자·분모)."""
    u = defaultdict(lambda: [0] * 7)
    for r in rows:
        x = u[r["sk"]]
        if r["kind"] == "own" and r["pass"]:
            x[1] += 1
            x[0] += cand is not None and blocks(cand, r)
        elif r["kind"] == "other":
            x[4] += 1
            x[3] += r["pass"]
            x[2] += r["pass"] and not (cand is not None and blocks(cand, r))
        elif r["kind"] in SUBS and r["pass"]:
            x[6] += 1
            x[5] += cand is not None and blocks(cand, r)
    return dict(u)


def stats_of(agg):
    fh = agg[0] / agg[1] if agg[1] else float("nan")
    op = agg[2] / agg[4] if agg[4] else float("nan")
    op65 = agg[3] / agg[4] if agg[4] else float("nan")
    cs = agg[5] / agg[6] if agg[6] else float("nan")
    return {"FH": fh, "OP": op, "OP65": op65, "dOP": op - op65, "CS": cs, "NG": cs - fh}


def summarize(rows, cand, boot=True):
    u = units(rows, cand)
    keys = sorted(u)
    tot = [sum(u[k][i] for k in keys) for i in range(7)]
    point = stats_of(tot)
    out = {k: round(v * 100, 2) for k, v in point.items()}
    out.update(n_own_pass=tot[1], n_other=tot[4], n_sub_pass=tot[6], n_spk=len(keys))
    if boot and keys:
        rng = random.Random(SEED)
        bs = defaultdict(list)
        for _ in range(B):
            pick = [keys[rng.randrange(len(keys))] for _ in keys]
            agg = [sum(u[k][i] for k in pick) for i in range(7)]
            for k, v in stats_of(agg).items():
                if v == v:
                    bs[k].append(v)
        for k, vs in bs.items():
            vs.sort()
            out[k + "_ci"] = [round(vs[int(0.025 * len(vs))] * 100, 2), round(vs[min(len(vs) - 1, int(0.975 * len(vs)))] * 100, 2)]
    return out


def auc(pos, neg):
    pos = [x for x in pos if x is not None]
    neg = [x for x in neg if x is not None]
    if not pos or not neg:
        return None
    allv = sorted([(v, 1) for v in pos] + [(v, 0) for v in neg])
    rank, i, rs = 1, 0, 0.0
    while i < len(allv):
        j = i
        while j < len(allv) and allv[j][0] == allv[i][0]:
            j += 1
        r = (rank + rank + (j - i) - 1) / 2
        rs += r * sum(1 for k in range(i, j) if allv[k][1])
        rank += j - i
        i = j
    return round((rs - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)), 4)


def feature_aucs(rows):
    out = {}
    for key, _, sign in [(g[1], None, 1 if g[2] == "ge" else -1) for g in GATES] + [("score", None, 1)]:
        def val(r):
            v = r["score"] if key == "score" else r["f"][key]
            return None if v is None else sign * v
        out[key] = auc([val(r) for r in rows if r["kind"] == "own"], [val(r) for r in rows if r["kind"] == "other"])
    return out


# ───────────────────────── 다리 ─────────────────────────
def bridge(rows):
    ref = {}
    if os.path.exists(TRIM27):
        for l in open(TRIM27, encoding="utf-8"):
            j = json.loads(l)
            if j.get("kind") in ("same", "diff") and j.get("score") is not None:
                ref[("c27b1", j["clip"], j["target"])] = j["score"]
    for l in open(NSNEW, encoding="utf-8"):
        j = json.loads(l)
        if j.get("kind") in ("same", "diff") and j.get("score") is not None:
            ref[({"538": "538", "608": "c28"}.get(j["set"], j["set"]), j["clip"], j["target"])] = j["score"]
    out = {}
    for s in sorted({r["set"] for r in rows}):
        d = [abs(r["score"] - ref[(s, r["clip"], r["target"])]) for r in rows if r["set"] == s and (s, r["clip"], r["target"]) in ref]
        out[s] = {"matched": len(d), "max_abs_diff": round(max(d), 3) if d else None, "over_0.1": sum(1 for x in d if x > 0.1)}
    return out


def cand_of(name, frozen):
    for g in GATES:
        if g[0] == name:
            return ("gate", g[1], (g[2], frozen["thr"][name]))
    if name == "G-LEN":
        return ("len", frozen["thr"]["G-LEN"], None)
    for h in HOLDS:
        if h[0] == name:
            return ("hold", h[1], h[2])
    raise KeyError(name)


# ───────────────────────── 탐색 ─────────────────────────
def cmd_explore(feat, out):
    rows, errs = load(feat)
    by = {s: [r for r in rows if r["set"] == s] for s in ("538", "c28", "c27b1")}
    res = {"errors": dict(errs), "bridge": bridge(rows), "n_rows": {s: len(v) for s, v in by.items()},
           "baseline": {s: summarize(v, None) for s, v in by.items()}, "auc": {s: feature_aucs(v) for s, v in by.items()}}
    thr = {}
    for name, key, op in GATES:
        thr[name] = fit_gate(by["c27b1"], key, op)
    thr["G-LEN"] = fit_len(by["c28"] + by["c27b1"])
    res["thr"] = thr
    gate_tab, hold_tab = {}, {}
    for name in [g[0] for g in GATES] + ["G-LEN"]:
        if thr[name] is None:
            gate_tab[name] = {"feasible": False}
            continue
        c = cand_of(name, {"thr": thr})
        t = {s: summarize(by[s], c, boot=False) for s in by}
        ok = (t["538"]["FH"] <= 2 and t["c28"]["FH"] <= 3 and t["c27b1"]["FH"] <= 3 and t["538"]["OP"] <= 5 and t["c28"]["OP"] <= 5)
        gate_tab[name] = {"feasible": True, "eligible": ok, **{s: t[s] for s in t}}
    for name, k, c in HOLDS:
        cd = cand_of(name, {"thr": thr})
        t = {s: summarize(by[s], cd, boot=False) for s in by}
        ok = (t["538"]["FH"] <= 3 and t["c28"]["FH"] <= 8 and t["c27b1"]["FH"] <= 8 and t["538"]["CS"] >= 30
              and t["c28"]["NG"] >= 0 and t["c27b1"]["NG"] >= 0)
        hold_tab[name] = {"eligible": ok, **t}
    res["gates"], res["holds"] = gate_tab, hold_tab
    feas = [n for n, v in gate_tab.items() if v.get("feasible")]
    elig = [n for n in feas if gate_tab[n]["eligible"]]
    keyf = lambda n: (gate_tab[n]["c28"]["FH"] + gate_tab[n]["c27b1"]["FH"], gate_tab[n]["538"]["FH"])  # noqa: E731
    res["gate_pick"] = {"name": min(elig, key=keyf) if elig else (min(feas, key=keyf) if feas else None), "eligible": bool(elig)}
    helig = [n for n, v in hold_tab.items() if v["eligible"]]
    hkey = lambda n: (-hold_tab[n]["538"]["NG"], hold_tab[n]["538"]["FH"])  # noqa: E731
    res["hold_pick"] = {"name": min(helig, key=hkey) if helig else min(hold_tab, key=hkey), "eligible": bool(helig)}
    for s in by:                                           # 범주 27 갈래별(보고)
        if s == "c27b1":
            res["baseline_by_group"] = {g: summarize([r for r in by[s] if r["grp"] == g], None, boot=False) for g in ("01", "02")}
    json.dump(res, open(out, "w"), ensure_ascii=False, indent=1)
    print_explore(res)


def print_explore(res):
    print("errors", res["errors"], "rows", res["n_rows"])
    print("bridge", json.dumps(res["bridge"], ensure_ascii=False))
    for s, v in res["baseline"].items():
        print(f"baseline {s}: OP65 {v['OP65']} FH0 n_own_pass {v['n_own_pass']} n_other {v['n_other']} n_sub_pass {v['n_sub_pass']} spk {v['n_spk']}")
    print("auc", json.dumps(res["auc"], ensure_ascii=False))
    print("thr", json.dumps(res["thr"], ensure_ascii=False))
    print(f"{'gate':12s} elig | 538 FH OP | c28 FH OP | c27 FH OP | CS538")
    for n, v in res["gates"].items():
        if not v.get("feasible"):
            print(f"{n:12s} infeasible")
            continue
        print(f"{n:12s} {str(v['eligible'])[0]}    | {v['538']['FH']:5.1f} {v['538']['OP']:4.1f} | {v['c28']['FH']:5.1f} {v['c28']['OP']:4.1f} |"
              f" {v['c27b1']['FH']:5.1f} {v['c27b1']['OP']:4.1f} | {v['538']['CS']:5.1f}")
    print(f"{'hold':12s} elig | 538 FH CS NG | c28 FH CS NG | c27 FH CS NG")
    for n, v in res["holds"].items():
        print(f"{n:12s} {str(v['eligible'])[0]}    | {v['538']['FH']:5.1f} {v['538']['CS']:5.1f} {v['538']['NG']:6.1f} |"
              f" {v['c28']['FH']:5.1f} {v['c28']['CS']:5.1f} {v['c28']['NG']:6.1f} | {v['c27b1']['FH']:5.1f} {v['c27b1']['CS']:5.1f} {v['c27b1']['NG']:6.1f}")
    print("gate_pick", res["gate_pick"], "hold_pick", res["hold_pick"])


# ───────────────────────── 확인 ─────────────────────────
def cmd_confirm(feat_c, feat_b2, out):
    fr = json.load(open(FROZEN, encoding="utf-8"))
    rc, ec = load(feat_c)
    rb, eb = load(feat_b2)
    rows = rc + rb
    by = {s: [r for r in rows if r["set"] == s] for s in ("538", "c28", "c27b2")}
    res = {"frozen": fr, "errors": {**dict(ec), **dict(eb)}, "bridge": bridge(rc), "n_rows": {s: len(v) for s, v in by.items()},
           "n_spk": {s: len({r["sk"] for r in v}) for s, v in by.items()},
           "n_own": {s: sum(1 for r in v if r["kind"] == "own") for s, v in by.items()},
           "baseline": {s: summarize(v, None) for s, v in by.items()}, "auc": {s: feature_aucs(v) for s, v in by.items()}}
    enough = res["n_spk"]["c27b2"] >= 20 and res["n_own"]["c27b2"] >= 300
    res["enough_data"] = enough
    allc = {}
    names = [g[0] for g in GATES] + ["G-LEN"] + [h[0] for h in HOLDS]
    for n in names:
        if n.startswith("G") and fr["thr"].get(n) is None:
            continue
        c = cand_of(n, fr)
        allc[n] = {s: summarize(by[s], c) for s in by}
        allc[n]["by_group"] = {g: summarize([r for r in by["c27b2"] if r["grp"] == g], c, boot=False) for g in ("01", "02")}
        allc[n]["cs_by_cat"] = {k: summarize([r for r in by["538"] if r["kind"] not in SUBS or k in (r.get("cat") or "")], c,
                                             boot=False)["CS"] for k in ("기식", "비음", "마찰")}
    res["candidates"] = allc
    g, h = fr["gate_pick"], fr["hold_pick"]
    verdict = {}
    if g:
        v = allc[g]
        j = {"GJ1": v["c27b2"]["OP"] <= 5 and v["c27b2"]["dOP_ci"][1] < 0,
             "GJ2": v["c27b2"]["FH"] <= 3 and v["c27b2"]["FH_ci"][1] <= 5,
             "GJ3": v["538"]["FH"] <= 2 and v["538"]["FH_ci"][1] <= 4 and v["c28"]["FH"] <= 3 and v["c28"]["FH_ci"][1] <= 6,
             "GJ4": v["538"]["OP"] <= 5}
        verdict["G"] = {"name": g, "criteria": j, "pass": all(j.values()) and enough and fr.get("gate_eligible", False)}
    if h:
        v = allc[h]
        k = {"HK1": v["538"]["FH"] <= 3 and v["538"]["FH_ci"][1] <= 5,
             "HK2": all(v[s]["FH"] <= 8 and v[s]["FH_ci"][1] <= 12 for s in ("c28", "c27b2")),
             "HK3": v["538"]["CS"] >= 30 and v["538"]["NG_ci"][0] > 0,
             "HK4": v["c28"]["NG"] >= 0 and v["c27b2"]["NG"] >= 0}
        verdict["H"] = {"name": h, "criteria": k, "pass": all(k.values()) and enough and fr.get("hold_eligible", False)}
    res["verdict"] = verdict
    json.dump(res, open(out, "w"), ensure_ascii=False, indent=1)
    print("errors", res["errors"], "n_spk", res["n_spk"], "n_own", res["n_own"], "enough", enough)
    print("bridge", json.dumps(res["bridge"], ensure_ascii=False))
    for s, v in res["baseline"].items():
        print(f"baseline {s}: OP65 {v['OP65']} {v.get('OP65_ci')} n_own_pass {v['n_own_pass']} n_other {v['n_other']}")
    for n, v in allc.items():
        print(n, {s: {k: v[s][k] for k in ("FH", "FH_ci", "OP", "OP_ci", "dOP_ci", "CS", "NG", "NG_ci") if k in v[s]}
                  for s in ("538", "c28", "c27b2")})
    print("verdict", json.dumps(verdict, ensure_ascii=False))


def cmd_selftest():
    assert final_cut(["o:ㄱ", "n:ㅏ", "|", "o:ㄴ", "n:ㅏ"]) == 3
    assert lev(list("abc"), list("abd")) == 1 and lev([], list("ab")) == 2
    assert quantile([0, 1, 2, 3, 4], 0.25) == 1.0
    r = {"pass": True, "f": {"lr_sc_T": -0.5, "m": 30, "ev": {0.5: 1}}, "score": 70}
    assert blocks(("gate", "lr_sc_T", ("ge", -0.4)), r) and not blocks(("gate", "lr_sc_T", ("ge", -0.6)), r)
    assert blocks(("hold", 0.5, 1), r) and not blocks(("hold", 0.5, 2), r)
    assert blocks(("len", [65, 75, 65, 65], None), r) and not blocks(("len", [65, 70, 65, 65], None), r)
    assert not blocks(("hold", 0.5, 1), {**r, "pass": False})
    rows = [{"kind": "other", "pass": True, "f": {"x": v}} for v in range(100)] + [{"kind": "other", "pass": False, "f": {"x": 1000}}] * 0
    assert fit_gate(rows, "x", "ge") == 96            # 100개 가운데 4개(96~99)만 통과
    assert fit_gate(rows, "x", "le") == 3
    assert auc([1, 2, 3], [0, 0.5]) == 1.0 and auc([1], [1]) == 0.5
    print("SR_ANALYZE_SELFTEST_OK")


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "explore":
        cmd_explore(sys.argv[2], sys.argv[3])
    elif c == "confirm":
        cmd_confirm(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        cmd_selftest()
