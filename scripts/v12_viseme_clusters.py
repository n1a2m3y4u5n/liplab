"""V12 데이터 기반 한국어 비심 군. 설계와 판정 기준은 docs/v12-viseme-clusters-2026-10.md(측정 전에 커밋).

538 실제 화자(V2 선택 75명 900클립)의 MediaPipe 52계수와 V2 CTC 정렬을 그대로 쓰고, 정렬 프레임마다 자모를 되살려
자모 단위 입모양(V2 RSA 특징 13개, 화자 안 z 점수)을 만든다. 단위 평균 입모양을 Ward 군집으로 나누고, 화자 부트스트랩으로
안정성을, 규칙 분류(backend/engine.py VISEME_MAP)와 ARI·AMI로 일치도를 측정한다.

  extract  (맥, 가벼움) 클립 → 화자별 자모 단위 평균(538 파생, liplab-lab/data/v12/에만 저장)
  analyze  (맥) 군집·부트스트랩·일치도 → summary.json(집계만)
  selftest   합성 자료로 분석 배관 점검
"""
import argparse
import json
import math
import os
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

MIN_SEG_SPK = 2        # 화자 단위 평균을 만들 최소 구간 수
MIN_SPK_UNIT = 50      # 주 분석에 넣을 단위의 최소 화자 수(75명의 2/3)
B_BOOT = 1000
N_PERM = 10000
SEED = 0
K_SWEEP = range(2, 16)
VOWEL_CTX = (2, 3, 4, 5)   # 보조 분석 2: 자음 뒤 모음의 규칙 무리(단모음 계열)

# 판정 규칙(문서 3절과 같은 값)
STAB_PART = (0.75, 0.50)       # 부트스트랩 ARI 중앙값: ≥0.75 안정, ≥0.50 중간, 그 밑 불안정
STAB_CLUS = (0.85, 0.75, 0.60)  # 군집별 Jaccard: 매우 안정, 안정, 약한 패턴, 그 밑 불안정
AGREE = (0.65, 0.30)            # ARI(자료, 규칙): ≥0.65 대체로 일치, ≥0.30 부분 일치, 그 밑 크게 다름
SPLIT_MIN = 0.60
COASSIGN_MIN = 0.80


# ───────────────────────────── extract ─────────────────────────────
def unit_segments(engine, C, text, row, lag):
    """정렬 행 → [(단위, 위치, t0, t1)]. 위치: on(초성) nu(중성, 이중모음은 nu+nu2를 한 구간) co(종성). 엔진 프레임이 정렬과
    다르면 None."""
    ef = C.engine_frames(engine, text)
    if ef is None:
        return None
    frames, roles, syls_idx, n_syl = ef
    if [f["viseme"] for f in frames] != row["visemes"] or n_syl != row["n_syl"]:
        return None
    toks = engine.to_pronounced_syllables(unicodedata.normalize("NFC", text).strip())
    st = row["starts"]
    keep = [i for i, s in enumerate(st) if s is not None]
    out = []
    for n_, i in enumerate(keep):
        t0 = st[i]
        t1 = st[keep[n_ + 1]] if n_ + 1 < len(keep) else row["t_last"]
        if t1 <= t0:
            continue
        role = roles[i]
        tok = toks[frames[i]["text_index"]] if role != "pause" else None
        if role == "nu2":
            if out and out[-1][1] == "nu" and out[-1][4] == frames[i]["text_index"]:
                out[-1] = (out[-1][0], "nu", out[-1][2], t1 + lag, out[-1][4])
            continue
        if role == "on":
            out.append((tok[0], "on", t0 + lag, t1 + lag, frames[i]["text_index"]))
        elif role == "nu":
            out.append((tok[1], "nu", t0 + lag, t1 + lag, frames[i]["text_index"]))
        elif role == "co":
            out.append((tok[2], "co", t0 + lag, t1 + lag, frames[i]["text_index"]))
    # 초성 자음 뒤 모음(보조 분석 2용): 같은 음절의 중성
    nu_of = {ti: u for u, pos, _, _, ti in out if pos == "nu"}
    return [(u, pos, a, b, nu_of.get(ti)) for u, pos, a, b, ti in out], (row["t_first"] + lag, row["t_last"] + lag)


def cmd_extract(a):
    import numpy as np
    import v2_avatar_validity as V
    sys.path.insert(0, os.path.abspath(a.backend))
    import engine
    import coart_pod_eval as C
    sel = json.load(open(a.sel, encoding="utf-8"))
    align = {}
    for path in a.align:
        for l in open(path, encoding="utf-8"):
            r = json.loads(l)
            align[r["key"]] = r
    qc = {"clips": 0, "no_bs": 0, "align_err": 0, "frame_mismatch": 0, "face_qc": 0, "ok": 0, "segs": 0, "segs_none": 0}
    per_spk = {}
    for c in sel["clips"]:
        qc["clips"] += 1
        bp = os.path.join(a.real_bs, c["clip"] + ".json")
        r = align.get("real:" + c["clip"])
        if not os.path.exists(bp):
            qc["no_bs"] += 1
            continue
        if r is None or "error" in r:
            qc["align_err"] += 1
            continue
        us = unit_segments(engine, C, c["text"], r, V.LAG_S)
        if us is None:
            qc["frame_mismatch"] += 1
            continue
        segs, span = us
        ser = V.load_series(bp)
        lab = [(u, pos, nxt) for u, pos, _, _, nxt in segs]
        rec, _ = V.clip_record(ser, [((u, pos, nxt), t0, t1) for u, pos, t0, t1, nxt in segs], span)
        if rec is None:
            qc["face_qc"] += 1
            continue
        qc["ok"] += 1
        qc["segs"] += len(rec["segs"])
        qc["segs_none"] += len(lab) - len(rec["segs"])
        d = per_spk.setdefault(c["spk"], [])
        for (u, pos, nxt), v in rec["segs"]:
            d.append((u, pos, nxt, [v[k] for k in V.RSA_FEATS]))
    # 화자 안 z 점수 → 단위별 평균(초성·중성·종성 각각, 초성은 뒤 모음 규칙 무리별로도)
    vm = viseme_map(a.backend)
    half = {s["spk"]: s["half"] for s in sel["speakers"]}
    spk_out = {}
    for spk, segs in per_spk.items():
        X = np.array([s[3] for s in segs], dtype=float)
        mu, sd = np.nanmean(X, axis=0), np.nanstd(X, axis=0)
        ok = sd > 1e-4
        Z = np.where(ok, (X - mu) / np.where(ok, sd, 1), 0.0)
        units, ctx = {}, {}
        for (u, pos, nxt, _), z in zip(segs, Z):
            if not np.all(np.isfinite(z)):
                continue
            units.setdefault(f"{pos}:{u}", []).append(z)
            if pos == "on" and nxt is not None and vm.get(nxt) in VOWEL_CTX:
                ctx.setdefault(f"on:{u}|{vm[nxt]}", []).append(z)
        spk_out[spk] = {"half": half.get(spk),
                        "n": {k: len(v) for k, v in units.items()},
                        "mean": {k: np.mean(v, axis=0).round(5).tolist() for k, v in units.items() if len(v) >= MIN_SEG_SPK},
                        "ctx_mean": {k: np.mean(v, axis=0).round(5).tolist() for k, v in ctx.items() if len(v) >= 1}}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump({"qc": qc, "feats": list(V.RSA_FEATS), "lag_s": V.LAG_S, "speakers": spk_out}, open(a.out, "w", encoding="utf-8"),
              ensure_ascii=False)
    print("EXTRACT_DONE", json.dumps(qc, ensure_ascii=False))


def viseme_map(backend):
    sys.path.insert(0, os.path.abspath(backend))
    import engine
    return dict(engine.VISEME_MAP)


# ───────────────────────────── analyze ─────────────────────────────
def unit_profiles(spk_means, spks, units):
    """화자 목록(중복 허용) → {단위: 화자 평균의 평균}. 화자가 없는 단위는 뺀다."""
    import numpy as np
    out = {}
    for u in units:
        vs = [spk_means[s][u] for s in spks if u in spk_means[s]]
        if vs:
            out[u] = np.mean(vs, axis=0)
    return out


def ward_labels(prof, units, k):
    import numpy as np
    from scipy.cluster.hierarchy import fcluster, linkage
    X = np.array([prof[u] for u in units])
    if len(units) <= k:
        return list(range(len(units)))
    Z = linkage(X, method="ward")
    return [int(x) for x in fcluster(Z, t=k, criterion="maxclust")]


def ari(a, b):
    from sklearn.metrics import adjusted_rand_score
    return float(adjusted_rand_score(a, b))


def ami(a, b):
    from sklearn.metrics import adjusted_mutual_info_score
    return float(adjusted_mutual_info_score(a, b))


def silhouette(prof, units, labels):
    import numpy as np
    from sklearn.metrics import silhouette_score
    if len(set(labels)) < 2 or len(set(labels)) >= len(units):
        return None
    return float(silhouette_score(np.array([prof[u] for u in units]), labels))


def clusters_of(units, labels):
    d = {}
    for u, l in zip(units, labels):
        d.setdefault(l, set()).add(u)
    return list(d.values())


def level(x, cuts, names):
    for c, n in zip(cuts, names):
        if x >= c:
            return n
    return names[-1]


def analyze_set(spk_means, spk_list, units, rule, k, rng, B, n_perm, half_of=None):
    """단위 집합 하나의 주 분석. rule: {단위: 규칙 무리}."""
    import numpy as np
    prof = unit_profiles(spk_means, spk_list, units)
    lab = ward_labels(prof, units, k)
    rl = [rule[u] for u in units]
    full_cl = clusters_of(units, lab)
    res = {"k": k, "n_units": len(units), "partition": {}, "ari_rule": round(ari(lab, rl), 4), "ami_rule": round(ami(lab, rl), 4),
           "silhouette_data": silhouette(prof, units, lab), "silhouette_rule": silhouette(prof, units, rl)}
    for u, l in zip(units, lab):
        res["partition"].setdefault(str(l), []).append(u)
    # 순열 영분포(규칙 무리 크기 유지)
    perm = []
    rl_arr = np.array(rl)
    for _ in range(n_perm):
        perm.append(ari(lab, rng.permutation(rl_arr)))
    perm = np.array(perm)
    res["perm"] = {"p_ge": float((np.sum(perm >= res["ari_rule"]) + 1) / (n_perm + 1)), "p95": round(float(np.percentile(perm, 95)), 4)}
    # 화자 부트스트랩
    boot_full, boot_rule, jac = [], [], [[] for _ in full_cl]
    co = {u: {v: [0, 0] for v in units} for u in units}
    spk_arr = np.array(spk_list)
    for _ in range(B):
        samp = list(rng.choice(spk_arr, size=len(spk_arr), replace=True))
        pb = unit_profiles(spk_means, samp, units)
        ub = [u for u in units if u in pb]
        lb = ward_labels(pb, ub, k)
        idx = {u: i for i, u in enumerate(units)}
        boot_full.append(ari([lab[idx[u]] for u in ub], lb))
        boot_rule.append(ari([rule[u] for u in ub], lb))
        bcl = clusters_of(ub, lb)
        ubs = set(ub)
        for ci, c in enumerate(full_cl):
            c2 = c & ubs
            if not c2:
                continue
            jac[ci].append(max(len(c2 & b) / len(c2 | b) for b in bcl))
        lab_b = dict(zip(ub, lb))
        for u in ub:
            for v in ub:
                co[u][v][1] += 1
                if lab_b[u] == lab_b[v]:
                    co[u][v][0] += 1
    bf, br = np.array(boot_full), np.array(boot_rule)
    res["boot"] = {"B": B, "ari_full_median": round(float(np.median(bf)), 4),
                   "ari_full_ci": [round(float(np.percentile(bf, 2.5)), 4), round(float(np.percentile(bf, 97.5)), 4)],
                   "ari_rule_median": round(float(np.median(br)), 4),
                   "ari_rule_ci": [round(float(np.percentile(br, 2.5)), 4), round(float(np.percentile(br, 97.5)), 4)]}
    res["cluster_jaccard"] = []
    for ci, c in enumerate(full_cl):
        m = float(np.mean(jac[ci])) if jac[ci] else None
        res["cluster_jaccard"].append({"units": sorted(c), "jaccard": None if m is None else round(m, 3),
                                       "level": None if m is None else level(m, STAB_CLUS, ("매우 안정", "안정", "약한 패턴", "불안정"))})
    res["coassign"] = {u: {v: round(co[u][v][0] / co[u][v][1], 3) for v in units if co[u][v][1] and v != u} for u in units}
    # 화자 절반 재현
    if half_of:
        h0 = [s for s in spk_list if half_of.get(s) == 0]
        h1 = [s for s in spk_list if half_of.get(s) == 1]
        p0, p1 = unit_profiles(spk_means, h0, units), unit_profiles(spk_means, h1, units)
        uc = [u for u in units if u in p0 and u in p1]
        l0, l1 = ward_labels(p0, uc, k), ward_labels(p1, uc, k)
        res["split_half"] = {"n0": len(h0), "n1": len(h1), "n_units": len(uc), "ari_halves": round(ari(l0, l1), 4),
                             "ari_rule_h0": round(ari([rule[u] for u in uc], l0), 4), "ari_rule_h1": round(ari([rule[u] for u in uc], l1), 4)}
    # k 쓸기(보고만)
    sweep = []
    for kk in K_SWEEP:
        if kk >= len(units):
            break
        lk = ward_labels(prof, units, kk)
        sweep.append({"k": kk, "ari_rule": round(ari(lk, rl), 4), "silhouette": silhouette(prof, units, lk)})
    res["k_sweep"] = sweep
    # 판정 단어
    res["verdict"] = {
        "partition_stability": level(res["boot"]["ari_full_median"], STAB_PART, ("안정", "중간", "불안정")),
        "agreement": level(res["ari_rule"], AGREE, ("대체로 일치", "부분 일치", "크게 다름")),
        "rule_outside_cloud": bool(res["ari_rule"] < res["boot"]["ari_full_ci"][0]),
    }
    return res, prof


def proposals(res, rule, units):
    """문서 3.4절 조건을 모두 넘을 때만 단위 이동 제안을 만든다."""
    v = res["verdict"]
    cond = {"a_stable": v["partition_stability"] == "안정", "b_large_diff": v["agreement"] == "크게 다름",
            "c_split_half": bool(res.get("split_half", {}).get("ari_halves", 0) >= SPLIT_MIN), "d_outside_cloud": v["rule_outside_cloud"]}
    out = {"conditions": cond, "moves": []}
    if not all(cond.values()):
        return out
    for cj in res["cluster_jaccard"]:
        if cj["jaccard"] is None or cj["jaccard"] < STAB_CLUS[1]:
            continue
        members = cj["units"]
        rules_in = [rule[u] for u in members]
        major = max(set(rules_in), key=rules_in.count)
        for u in members:
            if rule[u] == major:
                continue
            others = [w for w in members if w != u]
            m = min(res["coassign"][u][w] for w in others) if others else 0
            if m >= COASSIGN_MIN:
                out["moves"].append({"unit": u, "rule_group": rule[u], "to_group_of": major, "min_coassign": m, "cluster_jaccard": cj["jaccard"]})
    return out


def cmd_analyze(a):
    import numpy as np
    d = json.load(open(a.inp, encoding="utf-8"))
    vm = viseme_map(a.backend) if not a.rule_json else json.load(open(a.rule_json, encoding="utf-8"))
    spk = d["speakers"]
    spk_list = sorted(spk)
    half_of = {s: spk[s]["half"] for s in spk_list}
    spk_means = {s: {k: np.array(v) for k, v in spk[s]["mean"].items()} for s in spk_list}
    rng = np.random.default_rng(SEED)
    # 단위 수 표
    tot_n, n_spk = {}, {}
    for s in spk_list:
        for u, n in spk[s]["n"].items():
            tot_n[u] = tot_n.get(u, 0) + n
        for u in spk[s]["mean"]:
            n_spk[u] = n_spk.get(u, 0) + 1
    def rule_of(u):
        return vm.get(u.split(":", 1)[1], 15)
    all_units = sorted(tot_n)
    summary = {"qc": d["qc"], "feats": d["feats"], "n_speakers": len(spk_list),
               "units": {u: {"segs": tot_n[u], "speakers": n_spk.get(u, 0), "rule": rule_of(u)} for u in all_units}}
    prim = [u for u in all_units if u.split(":")[0] in ("on", "nu") and n_spk.get(u, 0) >= MIN_SPK_UNIT and rule_of(u) <= 10]
    summary["primary_units"] = prim
    summary["excluded_onnu"] = [u for u in all_units if u.split(":")[0] in ("on", "nu") and u not in prim]
    rule = {u: rule_of(u) for u in all_units}
    k = len({rule[u] for u in prim})
    res, prof = analyze_set(spk_means, spk_list, prim, rule, k, rng, a.B, a.perm, half_of)
    res["proposals"] = proposals(res, rule, prim)
    summary["primary"] = res
    summary["profiles"] = {u: [round(float(x), 3) for x in prof[u]] for u in prim}
    # 보조 1: 자음만, 모음만
    for name, pos in (("consonants_only", "on"), ("vowels_only", "nu")):
        us = [u for u in prim if u.startswith(pos + ":")]
        kk = len({rule[u] for u in us})
        if kk >= 2:
            r2, _ = analyze_set(spk_means, spk_list, us, rule, kk, rng, a.B_aux, a.perm_aux, half_of)
            for key in ("coassign",):
                r2.pop(key, None)
            summary[name] = r2
    # 보조 2: 모음 맥락 균형 자음(뒤 모음 규칙 무리 2·3·4·5별 화자 평균 → 맥락 평균)
    bal = {}
    for s in spk_list:
        cm = spk[s]["ctx_mean"]
        per = {}
        for key, v in cm.items():
            u, g = key.split("|")
            per.setdefault(u, []).append(np.array(v))
        bal[s] = {u: np.mean(vs, axis=0) for u, vs in per.items() if len(vs) >= 2}
    cons = [u for u in prim if u.startswith("on:") and sum(1 for s in spk_list if u in bal[s]) >= MIN_SPK_UNIT]
    kk = len({rule[u] for u in cons})
    if kk >= 2:
        r3, _ = analyze_set(bal, spk_list, cons, rule, kk, rng, a.B_aux, a.perm_aux, half_of)
        r3.pop("coassign", None)
        summary["consonants_ctx_balanced"] = r3
    # 보조 3: 종성(규칙 무리와 함께 초성·중성 군집에 넣어 본다)
    codas = [u for u in all_units if u.startswith("co:") and n_spk.get(u, 0) >= MIN_SPK_UNIT and rule[u] <= 10]
    if codas:
        us = prim + codas
        kk = len({rule[u] for u in us})
        r4, p4 = analyze_set(spk_means, spk_list, us, rule, kk, rng, a.B_aux, a.perm_aux, half_of)
        r4.pop("coassign", None)
        r4["codas"] = codas
        summary["with_codas"] = r4
    json.dump(summary, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    v = res["verdict"]
    print("ANALYZE_DONE k=%d units=%d ARI_rule=%.3f boot_median=%.3f %s %s" % (k, len(prim), res["ari_rule"], res["boot"]["ari_full_median"],
                                                                         v["partition_stability"], v["agreement"]))


# ───────────────────────────── selftest ─────────────────────────────
def cmd_selftest(_a):
    """규칙 무리대로 만든 합성 화자 → ARI 1 근처·안정, 무작위 화자 → ARI 0 근처·불안정."""
    import numpy as np
    rng = np.random.default_rng(1)
    units = [f"nu:v{i}" for i in range(12)] + [f"on:c{i}" for i in range(12)]
    rule = {u: (i // 3) + 1 for i, u in enumerate(units)}
    centers = {g: rng.normal(0, 2, 13) for g in set(rule.values())}

    def make(struct):
        sm = {}
        for s in range(40):
            sm[f"s{s}"] = {u: (centers[rule[u]] if struct else rng.normal(0, 2, 13)) + rng.normal(0, 0.3, 13) for u in units}
        return sm
    half = {f"s{s}": s % 2 for s in range(40)}
    for struct, want in ((True, "high"), (False, "low")):
        sm = make(struct)
        if not struct:   # 화자마다 독립 잡음만: 단위 평균이 서로 비슷해 군집이 흔들린다
            for s in sm:
                for u in units:
                    sm[s][u] = rng.normal(0, 1, 13)
        res, _ = analyze_set(sm, sorted(sm), units, rule, 8, np.random.default_rng(0), 100, 200, half)
        print(want, res["ari_rule"], res["boot"]["ari_full_median"], res["verdict"])
        if want == "high":
            assert res["ari_rule"] > 0.95 and res["boot"]["ari_full_median"] > 0.9, res
            assert proposals(res, rule, units)["moves"] == []
        else:
            assert res["ari_rule"] < 0.3 and res["boot"]["ari_full_median"] < 0.5, res
    # 한 단위를 다른 무리 중심으로 옮기면 이동 제안이 그 단위 하나만 나온다(규칙과 크게 다름 조건은 일부러 끈다)
    sm = make(True)
    mv = units[0]
    for s in sm:
        sm[s][mv] = centers[rule[units[5]]] + rng.normal(0, 0.3, 13)
    res, _ = analyze_set(sm, sorted(sm), units, rule, 8, np.random.default_rng(0), 100, 200, half)
    res["verdict"]["agreement"] = "크게 다름"
    res["verdict"]["rule_outside_cloud"] = True
    pr = proposals(res, rule, units)
    assert [m["unit"] for m in pr["moves"]] == [mv], pr
    print("V12_SELFTEST_OK")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract")
    e.add_argument("--sel", required=True)
    e.add_argument("--align", nargs="+", required=True)
    e.add_argument("--real-bs", required=True)
    e.add_argument("--backend", default=os.path.join(HERE, "..", "backend"))
    e.add_argument("--out", required=True)
    n = sub.add_parser("analyze")
    n.add_argument("--inp", required=True)
    n.add_argument("--backend", default=os.path.join(HERE, "..", "backend"))
    n.add_argument("--rule-json", default=None)
    n.add_argument("--out", required=True)
    n.add_argument("--B", type=int, default=B_BOOT)
    n.add_argument("--perm", type=int, default=N_PERM)
    n.add_argument("--B-aux", type=int, default=300)
    n.add_argument("--perm-aux", type=int, default=2000)
    sub.add_parser("selftest")
    a = ap.parse_args()
    {"extract": cmd_extract, "analyze": cmd_analyze, "selftest": cmd_selftest}[a.cmd](a)


if __name__ == "__main__":
    main()
