"""608 도메인 적응 판정(docs/dgop-608-adapt-2026-10.md 5~7절). 파드와 맥 공용(numpy만, 앵커 다시 맞추기에 backend/dgop.py).

    python analyze.py explore OUT_DIR                    F1 탐색: A 절반 0 + 538로 후보 고르기 → PICK
    python analyze.py confirm OUT_DIR F1|F2 NAME [BRIDGE.json]  확인 1(F1, A 절반 1) 또는 확인 2(F2, B)
    python analyze.py report OUT_DIR                     전체 표(보고용, 모든 세트·후보)
OUT_DIR에는 rows_<이름>.jsonl(evaluate.py pairs)과 e2_<이름>.json(evaluate.py e2), ROOT/meta/eval_*.json이 있어야 한다.
이름: R0(기준선), F1_<후보>, F2_<후보>. 판정 결과는 OUT_DIR/judge_*.json·txt.
"""
import collections
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("AD_ROOT", os.path.abspath(os.path.join(HERE, "..")))
for p in (os.path.join(ROOT, "backend"), os.path.join(HERE, "..", "..", "backend"), os.path.join(ROOT, "scripts"), os.path.join(HERE, "..")):
    if os.path.isdir(p) and p not in sys.path:
        sys.path.append(p)

B_BOOT, SEED = 2000, 0
CANDS = ["S1", "S2", "U1", "U2", "S1A", "S2A"]      # 고르기 동점 순서: 채점기만 → 낮은 lr·λ
PASS = 65.0
E2_ITEMS = [("ㅅ", [("ㄷ", "ㅅ")], "same"), ("ㅈ", [("ㄷ", "ㅈ"), ("ㅊ", "ㅈ")], "same"), ("ㅊ", [("ㅈ", "ㅊ")], "same"),
            ("ㅎ(ㄱ→ㅎ)", [("ㄱ", "ㅎ")], "same"), ("ㅎ 탈락", [("ㅇ", "ㅎ")], "fixed")]


def auc(pos, neg):
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    allv = np.concatenate([pos, neg])
    order = allv.argsort(kind="mergesort")
    sv = allv[order]
    ranks = np.empty(len(allv))
    i = 0
    while i < len(sv):
        j = i
        while j + 1 < len(sv) and sv[j + 1] == sv[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2 + 1
        i = j + 1
    return float((ranks[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def spearman(x, y):
    from scipy.stats import spearmanr  # noqa: PLC0415
    return float(spearmanr(x, y).correlation) if len(x) > 2 else float("nan")


# ───────── 읽기 ─────────
def load_rows(out, name):
    p = f"{out}/rows_{name}.jsonl"
    rows = [json.loads(l) for l in open(p, encoding="utf-8")]
    for r in rows:
        if r.get("score") is None:              # 채점 실패는 원점수 0(5.1절)
            r["score"], r["raw"] = 0.0, 0.0
    return rows


def load_e2(out, name):
    p = f"{out}/e2_{name}.json"
    return json.load(open(p)) if os.path.exists(p) else None


def intel_map():
    m = {}
    for s in ("A", "B"):
        p = f"{ROOT}/meta/eval_{s}.json"
        if os.path.exists(p):
            for j in json.load(open(p, encoding="utf-8")):
                m[(s, j["clip"])] = j.get("intel")
    return m


def subset(rows, st, half=None):
    return [r for r in rows if r["set"] == st and (half is None or int(r["half"]) == half)]


# ───────── 지표 ─────────
def t_star(rows538):
    oth = np.array([r["score"] for r in rows538 if r["kind"] == "other"])
    for t in range(0, 101):
        if np.mean(oth >= t) <= 0.05:
            return t
    return 101


def by_spk(rows, key="score"):
    d = collections.defaultdict(lambda: {"own": [], "other": []})
    for r in rows:
        if r["kind"] in ("own", "other"):
            d[r["spk"]][r["kind"]].append(r[key])
    return d


def basic(rows, t, cal2=None):
    own = np.array([r["score"] for r in rows if r["kind"] == "own"])
    oth = np.array([r["score"] for r in rows if r["kind"] == "other"])
    out = {"n_own": int(len(own)), "n_other": int(len(oth)), "n_spk": len({r["spk"] for r in rows}),
           "auc": auc(own, oth), "fail_t": float(np.mean(own < t)), "pass_t": float(np.mean(oth >= t)),
           "fail65": float(np.mean(own < PASS)), "pass65": float(np.mean(oth >= PASS))}
    out["E"] = out["fail_t"] + out["pass_t"]
    if cal2 is not None:
        import dgop
        o2 = np.array([dgop.calibrate_score(r["raw"], cal2) for r in rows if r["kind"] == "own"])
        p2 = np.array([dgop.calibrate_score(r["raw"], cal2) for r in rows if r["kind"] == "other"])
        out["fail65_refit"], out["pass65_refit"] = float(np.mean(o2 < PASS)), float(np.mean(p2 >= PASS))
    return out


def phone_pairs(rows):
    """위치 앎 음소: [(화자, 양성 naive, 음성 naive)]."""
    own = {(r["set"], r["clip"]): r for r in rows if r["kind"] == "own"}
    out = []
    for r in rows:
        if r["kind"] != "min" or "naive_at" not in r:
            continue
        o = own.get((r["set"], r["clip"]))
        k = str(r["tok_idx"])
        if not o or "naive_at" not in o:
            continue
        p, n = o["naive_at"].get(k), r["naive_at"].get(k)
        if p is None or n is None:
            continue
        out.append((r["spk"], p, n))
    return out


def phone_auc(pp):
    return auc([p for _, p, _ in pp], [n for _, _, n in pp])


def degr(rows538):
    by = collections.defaultdict(dict)
    for r in rows538:
        if r["kind"] in ("own", "deg_mild", "deg_mod", "deg_sev"):
            by[r["clip"]][r["kind"]] = r["raw"]
    full = [v for v in by.values() if len(v) == 4]
    mono = [v["own"] >= v["deg_mild"] >= v["deg_mod"] >= v["deg_sev"] for v in full]
    return {"n": len(full), "mono": float(np.mean(mono)) if mono else float("nan"),
            "auc_sev": auc([v["own"] for v in full], [v["deg_sev"] for v in full]),
            "med": {k: float(np.median([v[k] for v in full])) for k in ("own", "deg_mild", "deg_mod", "deg_sev")} if full else {}}


def refit_cal(dg):
    m = dg["med"]
    top = m["own"] * 110.7977 / 86.0
    return {"floor": 0.05, "anchors": [[0.0, 0.0], [m["deg_sev"], 40.0], [m["deg_mod"], 58.0], [m["deg_mild"], 72.0], [m["own"], 90.0], [top, 100.0]]}


def e2_values(e2, group, keep=None):
    """사·자·차·하 다섯 값(같은 녹음 AUC, ㅎ 탈락은 고정 목표 AUC). keep: 남길 (set, clip) 집합."""
    pairs, trues = collections.defaultdict(list), collections.defaultdict(list)
    for r in e2 or []:
        if "error" in r or r["group"] != group or (keep is not None and (r["set"], r["clip"]) not in keep):
            continue
        for c in r["cons"]:
            c = dict(c, spk=r["spk"])
            if c["kind"] == "pair":
                pairs[(c["y"], c["x"])].append(c)
            elif c.get("dgop") is not None:
                trues[c["cons"]].append(c)
    out = {}
    for name, plist, kind in E2_ITEMS:
        rows = [c for p in plist for c in pairs.get(p, []) if c["alt"] is not None]
        if kind == "same":
            rows = [c for c in rows if c["same"] is not None]
            pos = [c["same"] for c in rows]
        else:
            pos = [c["dgop"] for x in {p[1] for p in plist} for c in trues.get(x, [])]
        out[name] = {"auc": auc(pos, [c["alt"] for c in rows]), "n": len(rows)}
    return out


def rho(rows, st, intel):
    d = collections.defaultdict(lambda: ([], []))
    for r in rows:
        if r["kind"] == "own" and intel.get((st, r["clip"])) is not None:
            d[r["spk"]][0].append(r["raw"])
            d[r["spk"]][1].append(intel[(st, r["clip"])])
    spk = sorted(d)
    return spearman([np.mean(d[s][0]) for s in spk], [np.mean(d[s][1]) for s in spk])


def boot_diff(rows_b, rows_c, t_b, t_c):
    """화자 짝지은 부트스트랩: ΔE, ΔAUC, Δ위치 앎 음소 AUC의 95% 구간."""
    sb, sc = by_spk(rows_b), by_spk(rows_c)
    pb, pc = phone_pairs(rows_b), phone_pairs(rows_c)
    ppb, ppc = collections.defaultdict(list), collections.defaultdict(list)
    for s, p, n in pb:
        ppb[s].append((p, n))
    for s, p, n in pc:
        ppc[s].append((p, n))
    spk = sorted(set(sb) & set(sc))
    rng = np.random.default_rng(SEED)
    dE, dA, dP = [], [], []
    for _ in range(B_BOOT):
        pick = [spk[k] for k in rng.choice(len(spk), len(spk), replace=True)]

        def cat(d, kind):
            return np.array([v for s in pick for v in d[s][kind]])
        ob, xb, oc, xc = cat(sb, "own"), cat(sb, "other"), cat(sc, "own"), cat(sc, "other")
        eb = np.mean(ob < t_b) + np.mean(xb >= t_b)
        ec = np.mean(oc < t_c) + np.mean(xc >= t_c)
        dE.append(ec - eb)
        dA.append(auc(oc, xc) - auc(ob, xb))
        qb = [x for s in pick for x in ppb.get(s, [])]
        qc = [x for s in pick for x in ppc.get(s, [])]
        if qb and qc:
            dP.append(auc([p for p, _ in qc], [n for _, n in qc]) - auc([p for p, _ in qb], [n for _, n in qb]))
    ci = lambda v: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))] if v else [float("nan")] * 2
    return {"dE_ci": ci(dE), "dAUC_ci": ci(dA), "dPhone_ci": ci(dP), "n_spk": len(spk)}


def model_summary(out, name, st, half, intel):
    rows = load_rows(out, name)
    r538 = subset(rows, "538")
    t = t_star(r538)
    dg = degr(r538)
    cal2 = refit_cal(dg) if dg["med"] else None
    s608 = subset(rows, st, half)
    e2 = load_e2(out, name)
    keep = {(r["set"], r["clip"]) for r in s608}
    res = {"name": name, "t_star": t, "608": basic(s608, t, cal2), "538": basic(r538, t, cal2), "degr": dg, "cal_refit": cal2,
           "phone_608": phone_auc(phone_pairs(s608)), "phone_538": phone_auc(phone_pairs(r538)),
           "n_phone_608": len(phone_pairs(s608)), "rho": rho(s608, st, intel) if st in ("A", "B") else None,
           "e2_538": e2_values(e2, "538") if e2 else None, "e2_608": e2_values(e2, "608", keep) if e2 else None}
    return res, rows


def guards(b, c, scope):
    """scope: 'explore'(7.3절) | 'confirm'(7.2절). 돌려줌: {이름: (통과, 설명)}."""
    g = {}
    g["G1"] = (c["608"]["auc"] >= b["608"]["auc"] - 0.005, f"608 AUC {c['608']['auc']:.4f} ≥ {b['608']['auc']:.4f} − 0.005")
    ok2 = c["608"]["pass65"] <= 0.05
    txt2 = f"608 다르게 말함 합격 65 {c['608']['pass65']:.3f}"
    if scope == "confirm":
        ok2 = ok2 and c["608"].get("pass65_refit", 1) <= 0.05
        txt2 += f", 다시 맞춘 앵커 {c['608'].get('pass65_refit', float('nan')):.3f}"
    g["G2"] = (ok2, txt2 + " ≤ 0.05")
    g["G3"] = (c["538"]["auc"] >= b["538"]["auc"] - 0.003 and c["538"]["fail_t"] <= b["538"]["fail_t"] + 0.01,
               f"538 AUC {c['538']['auc']:.4f} (R0 {b['538']['auc']:.4f}), 538 t* 불합격 {c['538']['fail_t']:.3f} (R0 {b['538']['fail_t']:.3f})")
    groups = ["538"] if scope == "explore" else ["538", "608"]
    bad = []
    for gname in groups:
        cb, cc = b[f"e2_{gname}"], c[f"e2_{gname}"]
        if not cc or not cb:
            bad.append(f"{gname} 없음")
            continue
        for k in cc:
            v, v0 = cc[k]["auc"], cb[k]["auc"]
            floor_ok = v >= 0.80 if v0 >= 0.80 else True     # R0 자신이 0.80 아래인 항목은 비열등만 본다(12.1절 측정 전 변경)
            if not (floor_ok and v >= v0 - 0.03):
                bad.append(f"{gname} {k} {v:.3f}(R0 {v0:.3f})")
    g["G4"] = (not bad, "사·자·차·하 " + ("모두 통과" if not bad else "; ".join(bad)))
    g["G5"] = (c["phone_608"] >= b["phone_608"] - 0.01 and c["phone_538"] >= b["phone_538"] - 0.01,
               f"위치 앎 음소 AUC 608 {c['phone_608']:.4f} (R0 {b['phone_608']:.4f}), 538 {c['phone_538']:.4f} (R0 {b['phone_538']:.4f})")
    g["G6"] = (c["degr"]["mono"] >= b["degr"]["mono"] - 0.01 and c["degr"]["auc_sev"] >= b["degr"]["auc_sev"] - 0.005,
               f"538 단조 {c['degr']['mono']:.3f} (R0 {b['degr']['mono']:.3f}), 원본>심 AUC {c['degr']['auc_sev']:.4f} (R0 {b['degr']['auc_sev']:.4f})")
    if scope == "confirm":
        g["G7"] = (c["rho"] >= b["rho"] - 0.10, f"화자 명료도 ρ {c['rho']:.3f} (R0 {b['rho']:.3f})")
    return g


def fmt_model(m):
    a, s = m["608"], m["538"]
    e2 = lambda e: ", ".join(f"{k} {v['auc']:.3f}" for k, v in e.items()) if e else "-"
    return (f"{m['name']}: t*={m['t_star']} | 608 AUC {a['auc']:.4f}, 불합격(t*) {a['fail_t']:.3f}, 다르게 합격(t*) {a['pass_t']:.3f}, E {a['E']:.3f}, "
            f"65 불합격 {a['fail65']:.3f}·다르게 합격 {a['pass65']:.3f}, 다시 맞춘 65 {a.get('fail65_refit', float('nan')):.3f}·"
            f"{a.get('pass65_refit', float('nan')):.3f} (자기 {a['n_own']}, 다르게 {a['n_other']}, 화자 {a['n_spk']})\n"
            f"    538 AUC {s['auc']:.4f}, 불합격(t*) {s['fail_t']:.3f}, 65 불합격 {s['fail65']:.3f}·다르게 합격 {s['pass65']:.3f} | 단조 {m['degr']['mono']:.3f}, "
            f"원본>심 {m['degr']['auc_sev']:.4f}, 중앙값 {json.dumps({k: round(v, 1) for k, v in m['degr']['med'].items()})}\n"
            f"    위치 앎 음소 AUC 608 {m['phone_608']:.4f}(n {m['n_phone_608']}), 538 {m['phone_538']:.4f} | ρ {m['rho'] if m['rho'] is None else round(m['rho'], 3)}\n"
            f"    사·자·차·하 538: {e2(m['e2_538'])}\n    사·자·차·하 608: {e2(m['e2_608'])}")


def cmd_explore(out):
    intel = intel_map()
    b, rb = model_summary(out, "R0", "A", 0, intel)
    a_all = auc([r["score"] for r in subset(rb, "A") if r["kind"] == "own"], [r["score"] for r in subset(rb, "A") if r["kind"] == "other"])
    hold = abs(a_all - 0.954) > 0.003
    lines = ["== 탐색(F1, A 절반 0 + 538) ==", f"다리(5.5절): R0 E-A 두 절반 AUC {a_all:.4f}(기준 0.954 ± 0.003) → {'HOLD' if hold else '통과'}",
             fmt_model(b)]
    res = {"R0": b, "cands": {}, "bridge_R0_A_auc": a_all, "hold": hold}
    best = None
    for name in CANDS:
        if not os.path.exists(f"{out}/rows_F1_{name}.jsonl"):
            lines.append(f"{name}: 결과 없음(학습·채점 실패 또는 예산으로 뺌)")
            continue
        c, rc = model_summary(out, f"F1_{name}", "A", 0, intel)
        g = guards(b, c, "explore")
        dE = c["608"]["E"] - b["608"]["E"]
        bt = boot_diff(subset(rb, "A", 0), subset(rc, "A", 0), b["t_star"], c["t_star"])
        ok = all(v[0] for v in g.values()) and dE < 0
        res["cands"][name] = {"summary": c, "guards": {k: list(v) for k, v in g.items()}, "dE": dE, "boot": bt, "eligible": ok}
        lines += [fmt_model(c), f"    ΔE {dE:+.4f} {bt['dE_ci']}, ΔAUC {c['608']['auc'] - b['608']['auc']:+.4f} {bt['dAUC_ci']}, "
                  f"Δ위치 앎 음소 {c['phone_608'] - b['phone_608']:+.4f} {bt['dPhone_ci']}"]
        lines += [f"    {k} {'통과' if v[0] else '미달'}: {v[1]}" for k, v in g.items()]
        if ok and (best is None or c["608"]["E"] < best[1] - 1e-12):
            best = (name, c["608"]["E"])
    pick = best[0] if best else None
    res["pick"] = pick
    lines.append(f"PICK {pick}")
    json.dump(res, open(f"{out}/judge_explore.json", "w"), ensure_ascii=False, indent=1, default=float)
    open(f"{out}/judge_explore.txt", "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


def cmd_confirm(out, fold, name, bridge=None):
    intel = intel_map()
    st, half = ("A", 1) if fold == "F1" else ("B", None)
    b, rb = model_summary(out, "R0", st, half, intel)
    c, rc = model_summary(out, f"{fold}_{name}", st, half, intel)
    g = guards(b, c, "confirm")
    br = json.load(open(bridge)) if bridge and os.path.exists(bridge) else None
    g["G8"] = (bool(br and br.get("ok")), f"int8 변환·CPU 다리 {json.dumps(br, ensure_ascii=False) if br else '없음'}")
    dE = c["608"]["E"] - b["608"]["E"]
    bt = boot_diff(subset(rb, st, half), subset(rc, st, half), b["t_star"], c["t_star"])
    p1 = (dE < 0 and bt["dE_ci"][1] < 0) if fold == "F2" else dE < 0
    passed = p1 and all(v[0] for v in g.values())
    lines = [f"== 확인 {'2(F2, B 18명)' if fold == 'F2' else '1(F1, A 절반 1)'}: {name} ==", fmt_model(b), fmt_model(c),
             f"P1 {'통과' if p1 else '미달'}: ΔE {dE:+.4f} {bt['dE_ci']}",
             f"    ΔAUC {c['608']['auc'] - b['608']['auc']:+.4f} {bt['dAUC_ci']}, Δ위치 앎 음소 {c['phone_608'] - b['phone_608']:+.4f} {bt['dPhone_ci']}"]
    lines += [f"{k} {'통과' if v[0] else '미달'}: {v[1]}" for k, v in g.items()]
    orig = {"auc>=0.92": c["608"]["auc"] >= 0.92, "fail_t<=0.10": c["608"]["fail_t"] <= 0.10, "pass_t<=0.05": c["608"]["pass_t"] <= 0.05,
            "pass65<=0.05": c["608"]["pass65"] <= 0.05}
    lines.append(f"원안 절대 기준(보고): {orig}")
    if st == "B":
        for nm, sub in (("W28", {"CBC", "CSI", "HBM", "KBS", "KJH", "KMJ", "LUA", "PKS", "RJA"}),):
            xb = [r for r in subset(rb, "B") if r["spk"] in sub]
            xc = [r for r in subset(rc, "B") if r["spk"] in sub]
            yb = [r for r in subset(rb, "B") if r["spk"] not in sub]
            yc = [r for r in subset(rc, "B") if r["spk"] not in sub]
            lines.append(f"하위군(보고) W28: R0 {basic(xb, b['t_star'])['auc']:.4f}·E {basic(xb, b['t_star'])['E']:.3f} → "
                         f"{basic(xc, c['t_star'])['auc']:.4f}·E {basic(xc, c['t_star'])['E']:.3f}; Z28+N28: R0 {basic(yb, b['t_star'])['auc']:.4f}·"
                         f"E {basic(yb, b['t_star'])['E']:.3f} → {basic(yc, c['t_star'])['auc']:.4f}·E {basic(yc, c['t_star'])['E']:.3f}")
    lines.append(f"JUDGE {fold} {name} {'PASS' if passed else 'FAIL'}")
    res = {"fold": fold, "name": name, "R0": b, "cand": c, "guards": {k: list(v) for k, v in g.items()}, "dE": dE, "boot": bt,
           "P1": p1, "pass": passed, "orig": orig}
    json.dump(res, open(f"{out}/judge_confirm_{fold}.json", "w"), ensure_ascii=False, indent=1, default=float)
    open(f"{out}/judge_confirm_{fold}.txt", "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


def cmd_bridge(out, name, export_logs):
    """5.5절: CPU 앱 경로(rows_cpu_<이름>) 대 GPU(rows_<이름>) 표시 점수 차 최대 ≤ 0.5, int8 변환 점검 통과."""
    g = {(r["set"], r["clip"], r["kind"], r["text"]): r["score"] for r in load_rows(out, name)}
    diffs = [abs(r["score"] - g[k]) for r in load_rows(out, f"cpu_{name}") if (k := (r["set"], r["clip"], r["kind"], r["text"])) in g]
    exp = []
    for p in [x for x in export_logs.split(",") if x]:
        exp.append(os.path.exists(p) and "결과: 통과" in open(p, encoding="utf-8").read())
    res = {"name": name, "n": len(diffs), "max_diff": float(max(diffs)) if diffs else None, "export_ok": all(exp) if exp else None,
           "ok": bool(diffs) and max(diffs) <= 0.5 and (all(exp) if exp else True)}
    json.dump(res, open(f"{out}/bridge_{name}.json", "w"), ensure_ascii=False, indent=1)
    print("BRIDGE", json.dumps(res, ensure_ascii=False))


def cmd_report(out):
    intel = intel_map()
    lines = []
    names = sorted(f[5:-6] for f in os.listdir(out) if f.startswith("rows_") and f.endswith(".jsonl"))
    for name in names:
        rows = load_rows(out, name)
        for st, half in (("A", None), ("A", 0), ("A", 1), ("B", None)):
            if not subset(rows, st, half):
                continue
            m, _ = model_summary(out, name, st, half, intel)
            lines.append(f"[{st}{'' if half is None else ' 절반 ' + str(half)}] " + fmt_model(m))
    open(f"{out}/report.txt", "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "explore":
        cmd_explore(sys.argv[2])
    elif c == "confirm":
        cmd_confirm(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5] if len(sys.argv) > 5 else None)
    elif c == "report":
        cmd_report(sys.argv[2])
    elif c == "bridge":
        cmd_bridge(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "")
    else:
        sys.exit(f"알 수 없는 명령 {c}")
