"""음소 칩 꼬리 후보 판정(맥, 점수 파일만). docs/phone-tail-2026-10.md 4·5절.

    python judge.py explore A0_DIR BC_DIR OUT.json                 A0(n)·B 지표, 다리, 고르기(PICK)
    python judge.py confirm A1_DIR PICK OUT.json [--n A1N_DIR]     A1(t) 지표와 판정, n은 보고만
    python judge.py s2 A0_DIR A1_DIR BC_DIR CAND OUT.json          고른 후보의 칩 값으로 S2 판정(S2 6절 기준 그대로)
    python judge.py a2 A2_DIR JOBS OUT.json                        새 538 화자(A2)에서 E1 세 소리 재확인(8절)
    python judge.py export S2_OUT.json APP_JSON                    S2 판정을 통과했을 때만 E1 칩 값용 앱 표(backend/data/phone_reliability_e1.json)

A0_DIR·A1_DIR: offline.py s2의 출력(<후보>/run.0.jsonl), BC_DIR: offline.py dgop의 출력(<후보>/dgop.jsonl). OUT에는 집계만 쓴다.
"""
import glob
import json
import os
import sys
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import s2_phone_reliability as S2  # noqa: E402
import chipval as CV  # noqa: E402

LAB = S2.LAB
S2_1007 = f"{LAB}/data/pod_runs/20261007_9q5h6hblgxungw/s2/s2/out"
S2_1009 = f"{LAB}/data/pod_runs/20261009_jgwejgryojj5aa/s2/s2/out"
RED = S2.RED
BOOT = 2000


def load(d, cand):
    return [json.loads(l) for l in open(f"{d}/{cand}/run.0.jsonl", encoding="utf-8")]


def load_bc(d, cand):
    pairs, own608 = [], []
    for l in open(f"{d}/{cand}/dgop.jsonl", encoding="utf-8"):
        r = json.loads(l)
        (pairs if r["set"] == "pair" else own608).append(r)
    return pairs, own608


def correct_tokens(r, j):
    silent = set(j["silent_h"])
    return [(i, t, S2.disp(v)) for i, (t, v) in enumerate(zip(j["tokens"], r["orig"]))
            if t != "|" and i not in silent and v is not None and i < j["fs"]]


def bridge(recs, ref_dir, st):
    ref = {}
    for p in glob.glob(f"{ref_dir}/run.*.jsonl"):
        for l in open(p, encoding="utf-8"):
            x = json.loads(l)
            if x["set"] == st and "error" not in x:
                ref[x["clip"]] = x["orig"]
    d, miss = [], 0
    for r in recs:
        if r["clip"] not in ref or "error" in r:
            miss += 1
            continue
        for a, b in zip(r["orig"], ref[r["clip"]]):
            if a is not None and b is not None:
                d.append(abs(a - b))
    d = np.array(d)
    out = {"tokens": int(len(d)), "missing": miss, "frac_le_0.002": round(float((d <= 0.002).mean()), 5), "max": round(float(d.max()), 4)}
    out["ok"] = bool(miss == 0 and out["frac_le_0.002"] >= 0.99)
    return out


def metrics(recs, jobs, quiet=None):
    pos, neg, ins = defaultdict(list), defaultdict(list), defaultdict(list)
    per_sent, by_tok = [], defaultdict(list)
    for r in recs:
        if "error" in r:
            continue
        j = jobs[r["clip"]]
        ct = correct_tokens(r, j)
        pos[r["spk"]] += [v for _, _, v in ct]
        per_sent.append(sum(v < RED for _, _, v in ct))
        for _, t, v in ct:
            by_tok[t].append(v)
        for kind, i, y, v, _all in r["subs"]:
            if kind == "near" and v is not None:
                neg[r["spk"]].append(S2.disp(v))
        for x in r.get("ins", []):
            ins[r["spk"]] += [x[3], x[4]]
    spks = sorted(pos)

    def flat(d, ss=None):
        return [v for s in (ss or spks) for v in d.get(s, [])]

    def m(ss=None):
        P, N, I = flat(pos, ss), flat(neg, ss), flat(ins, ss)
        return {"M1_tail": float(np.mean([v <= 1 for v in P])), "M2_fr": float(np.mean([v < RED for v in P])),
                "M3_auc": float(S2.auc_h(S2.hist(P), S2.hist(N))), "M4_detect": float(np.mean([v < RED for v in N])),
                "M5_omission": float(np.mean([v < RED for v in I])) if I else None, "n_pos": len(P), "n_neg": len(N), "n_ins": len(I)}
    out = m()
    fr = [np.mean([v < RED for v in vs]) for t, vs in by_tok.items() if len(vs) >= 50]
    out["fr_by_sound_median"] = float(np.median(fr))
    out["sounds_fr_le_10"] = int(sum(f <= 0.10 for f in fr))
    out["n_sounds"] = len(fr)
    out["red_per_sentence"] = float(np.mean(per_sent))
    if quiet:
        out["quiet"] = m([s for s in spks if s in quiet])
        out["noisy"] = m([s for s in spks if s not in quiet])
    return out, (pos, neg, ins, spks)


def boot_diff(base, cand, seed=0):
    """화자 부트스트랩: (후보 − K)의 M1·M2 차 95% 구간."""
    pb, _, _, spks = base
    pc = cand[0]
    rng = np.random.default_rng(seed)
    r1, r2 = [], []
    t1b = {s: (np.sum(np.array(pb[s]) <= 1), np.sum(np.array(pb[s]) < RED), len(pb[s])) for s in spks}
    t1c = {s: (np.sum(np.array(pc[s]) <= 1), np.sum(np.array(pc[s]) < RED), len(pc[s])) for s in spks}
    for _ in range(BOOT):
        ss = [spks[k] for k in rng.integers(0, len(spks), len(spks))]
        nb = sum(t1b[s][2] for s in ss)
        r1.append((sum(t1c[s][0] for s in ss) - sum(t1b[s][0] for s in ss)) / nb)
        r2.append((sum(t1c[s][1] for s in ss) - sum(t1b[s][1] for s in ss)) / nb)
    q = lambda a: [round(float(np.percentile(a, 2.5)), 4), round(float(np.percentile(a, 97.5)), 4)]
    return {"dM1": q(r1), "dM2": q(r2)}


def protective(c, k, kap_c=None, kap_k=None):
    why = []
    if c["M3_auc"] < k["M3_auc"] - 0.005:
        why.append("M3")
    if c["M4_detect"] < k["M4_detect"] - 0.03:
        why.append("M4")
    if c["M5_omission"] < k["M5_omission"] - 0.05:
        why.append("M5")
    if kap_c is not None and kap_c < kap_k - 0.02:
        why.append("M6")
    return why


def jobs_map():
    return {j["clip"]: j for j in (json.loads(l) for l in open(S2.JOBS, encoding="utf-8"))}


def r4(d):
    return {k: (round(v, 4) if isinstance(v, float) else (r4(v) if isinstance(v, dict) else v)) for k, v in d.items()}


def cmd_explore(a0_dir, bc_dir, out_path):
    jobs = jobs_map()
    res = {"set": "A0", "cands": {}}
    base = None
    for c in CV.CANDIDATES:
        recs = load(a0_dir, c)
        mt, raw = metrics(recs, jobs)
        pairs, own608 = load_bc(bc_dir, c)
        _kap, kap_all = S2.kappa_by_sound(pairs)
        mt["M6_kappa"] = kap_all["kappa"]
        mt["kappa_pairs"] = kap_all["n_pairs"]
        reds = [S2.chip_tokens(r["phones"])[0] for r in own608]
        mt["own608_red"] = float(np.mean([v < RED for x in reds for _, _, v in x]))
        if c == "K":
            base = (mt, raw)
            res["bridge"] = bridge(recs, S2_1007, "A0")
        else:
            mt["boot_vs_K"] = boot_diff(base[1], raw)
        res["cands"][c] = r4(mt)
    k = res["cands"]["K"]
    elig = []
    for c in CV.CANDIDATES[1:]:
        mt = res["cands"][c]
        why = protective(mt, k, mt["M6_kappa"], k["M6_kappa"])
        gain = k["M2_fr"] - mt["M2_fr"]
        if gain < 0.01:
            why.append("M2<1%p")
        mt["protective_fail"] = why
        if not why:
            elig.append((mt["M2_fr"], CV.CANDIDATES.index(c), c))
    pick = None
    if elig:
        best = min(e[0] for e in elig)
        pick = min((e for e in elig if e[0] <= best + 0.001), key=lambda e: e[1])[2]
    res["pick"] = pick
    json.dump(res, open(out_path, "w"), ensure_ascii=False, indent=1)
    print("BRIDGE", res["bridge"])
    for c, mt in res["cands"].items():
        print(c, {x: mt.get(x) for x in ("M1_tail", "M2_fr", "M3_auc", "M4_detect", "M5_omission", "M6_kappa", "fr_by_sound_median",
                                          "sounds_fr_le_10", "red_per_sentence", "own608_red", "protective_fail")})
    print("PICK", pick)


def cmd_confirm(a1_dir, pick, out_path, n_dir=None):
    jobs = jobs_map()
    res = {"set": "A1", "pick": pick, "t": {}, "n": {}}
    for setting, d, ref in (("t", a1_dir, S2_1009), ("n", n_dir, S2_1007)):
        if not d:
            continue
        base = None
        for c in CV.CANDIDATES:
            recs = load(d, c)
            mt, raw = metrics(recs, jobs, quiet=S2.QUIET_A1)
            if c == "K":
                base = (mt, raw)
                res[f"bridge_{setting}"] = bridge(recs, ref, "A1")
            else:
                mt["boot_vs_K"] = boot_diff(base[1], raw)
            res[setting][c] = r4(mt)
    k, c = res["t"]["K"], res["t"].get(pick)
    if c is not None:
        why = protective(c, k)
        if not (c["M1_tail"] <= 0.75 * k["M1_tail"]):
            why.append("M1<25%")
        if not (k["M2_fr"] - c["M2_fr"] >= 0.02):
            why.append("M2<2%p")
        res["verdict"] = "pass" if not why and res["bridge_t"]["ok"] else ("HOLD" if not res["bridge_t"]["ok"] else "fail")
        res["fail_reasons"] = why
    json.dump(res, open(out_path, "w"), ensure_ascii=False, indent=1)
    for s in ("bridge_t", "bridge_n"):
        print(s.upper(), res.get(s))
    for st in ("t", "n"):
        for cn, mt in res[st].items():
            print(st, cn, {x: mt.get(x) for x in ("M1_tail", "M2_fr", "M3_auc", "M4_detect", "M5_omission", "fr_by_sound_median",
                                                   "sounds_fr_le_10", "red_per_sentence")})
    print("VERDICT", res.get("verdict"), res.get("fail_reasons"))


def cmd_s2(a0_dir, a1_dir, bc_dir, cand, out_path):
    """S2 analyze와 같은 계산을 후보의 칩 값으로(다리는 위 explore·confirm에서 따로 봄)."""
    jobs = S2.load_jobs()
    recs = load(a0_dir, cand) + load(a1_dir, cand)
    pairs, own608 = load_bc(bc_dir, cand)
    kap, kap_all = S2.kappa_by_sound(pairs)
    stats = {}
    for st in ("A0", "A1"):
        pos, neg, aneg, fpos, fneg, err = S2.per_set(recs, jobs, st)
        spks = {r["spk"] for r in recs if r["set"] == st}
        boot = S2.Boot(spks)
        stats[st] = {"errors": err, "speakers": len(spks), "sounds": S2.sound_stats(pos, neg, boot, aneg)}
    cand_s, rel, table = [], [], {}
    for tok in sorted(set(stats["A0"]["sounds"]) | set(stats["A1"]["sounds"])):
        e_ok, e_why = S2.passes_naf(stats["A0"]["sounds"].get(tok, {}))
        k_ok = (kap.get(tok) or {}).get("pass", False)
        c_ok, c_why = S2.passes_naf(stats["A1"]["sounds"].get(tok, {}))
        is_c = e_ok and k_ok
        table[tok] = {"explore": e_why or "pass", "kappa": "pass" if k_ok else "fail", "confirm": (c_why or "pass") if is_c else "-",
                      "reliable": bool(is_c and c_ok)}
        if is_c:
            cand_s.append(tok)
            if c_ok:
                rel.append(tok)
    R = set(rel)
    reds = S2.sentence_reds(recs, jobs, R, "A1")
    gate = {"A1_definite_red_per_sentence": round(float(np.mean(reds)), 3) if reds else None,
            "A1_sub_detection": S2.sub_detection(recs, jobs, R, "A1"),
            "A1_all_sounds_red_per_sentence": round(float(np.mean(S2.sentence_reds(recs, jobs, set(stats["A1"]["sounds"]), "A1"))), 3)}
    res = {"cand": cand, "include_final": S2.INCLUDE_FINAL, "kappa_all": kap_all, "kappa": kap, "sets": stats, "decision_table": table,
           "candidates": cand_s, "reliable": rel, "system_gate": gate,
           "pass": bool(R and gate["A1_definite_red_per_sentence"] is not None and gate["A1_definite_red_per_sentence"] <= S2.CRIT["per_sentence"])}
    s608, s608_sent = S2.own608_stats(own608, R)
    res["own608"] = {"red_by_sound": s608, "definite_red_per_sentence": s608_sent, "sentences": len(own608)}
    json.dump(res, open(out_path, "w"), ensure_ascii=False, indent=1)
    print("KAPPA_ALL", kap_all)
    print("CANDIDATES", len(cand_s), cand_s)
    print("RELIABLE", len(rel), rel)
    print("SYSTEM", gate)
    print("PASS", res["pass"])


R3 = ("n:ㅏ", "o:ㄴ", "o:ㄹ")


def cmd_a2(a2_dir, jobs_path, out_path):
    """8절 판정: D1 세 소리 N·A·F(E1), D2 문장 관문(R = 세 소리), D3 E1 대 K 보호 기준."""
    jobs = {j["clip"]: j for j in (json.loads(l) for l in open(jobs_path, encoding="utf-8"))}
    res = {"set": "A2", "jobs_sha_note": "build_a2.py", "metrics": {}, "sounds": {}}
    recs = {c: load(a2_dir, c) for c in ("K", "E1")}
    for c in ("K", "E1"):
        mt, _raw = metrics(recs[c], jobs)
        res["metrics"][c] = r4(mt)
    for c in ("K", "E1"):
        pos, neg, aneg, _fp, _fn, err = S2.per_set(recs[c], jobs, "A2")
        boot = S2.Boot({r["spk"] for r in recs[c] if "error" not in r})
        st = S2.sound_stats(pos, neg, boot, aneg)
        res["sounds"][c] = {t: st.get(t) for t in R3}
        res["errors_" + c] = err
    d1 = {t: S2.passes_naf(res["sounds"]["E1"][t] or {}) for t in R3}
    reds = S2.sentence_reds(recs["E1"], jobs, set(R3), "A2")
    gate = {"definite_red_per_sentence": round(float(np.mean(reds)), 3), "sentences": len(reds),
            "sub_detection": S2.sub_detection(recs["E1"], jobs, set(R3), "A2")}
    d3 = protective(res["metrics"]["E1"], res["metrics"]["K"])
    res.update({"D1": {t: (ok, why) for t, (ok, why) in d1.items()}, "D2": gate, "D3_fail": d3})
    res["pass"] = bool(all(ok for ok, _ in d1.values()) and gate["definite_red_per_sentence"] <= 1.0 and not d3)
    res["passing_sounds"] = [t for t, (ok, _) in d1.items() if ok]
    json.dump(res, open(out_path, "w"), ensure_ascii=False, indent=1)
    for c in ("K", "E1"):
        m = res["metrics"][c]
        print(c, {x: m.get(x) for x in ("M1_tail", "M2_fr", "M3_auc", "M4_detect", "M5_omission", "fr_by_sound_median", "red_per_sentence", "n_pos")})
        for t in R3:
            d = res["sounds"][c][t] or {}
            print("  ", t, {x: d.get(x) for x in ("n_pos", "n_neg", "spk_pos", "spk_neg", "auc", "auc_ci", "fr", "fr_ci")})
    print("D1", res["D1"]); print("D2", gate); print("D3", d3); print("PASS", res["pass"])


def cmd_export(res_path, app_json):
    res = json.load(open(res_path, encoding="utf-8"))
    if not res.get("pass") or res.get("include_final"):
        sys.exit("판정 미통과이거나 끝 음절 포함 판(보고만): 앱 표를 쓰지 않는다")
    a0, a1 = res["sets"]["A0"]["sounds"], res["sets"]["A1"]["sounds"]
    sounds = {}
    for tok, row in res["decision_table"].items():
        d, e, k = a1.get(tok, {}), a0.get(tok, {}), res["kappa"].get(tok, {})
        sounds[tok] = {"reliable": row["reliable"], "auc": d.get("auc"), "auc_ci": d.get("auc_ci"), "false_red": d.get("fr"),
                       "false_red_ci": d.get("fr_ci"), "explore_auc": e.get("auc"), "explore_false_red": e.get("fr"),
                       "n_pos": d.get("n_pos"), "n_neg": d.get("n_neg"), "kappa": k.get("kappa"), "retest_agree": k.get("po"),
                       "n_retest": k.get("n_pair")}
    out = {"version": "2026-10-15", "chip_value": res["cand"],
           "source": "docs/phone-tail-2026-10.md (S2를 칩 값 E1로 다시 잼). 538 인위 치환(탐색 58명·확인 21명)·608 짝 세션 재검사의 소리별 집계값만 담는다.",
           "rule": "reliable = 탐색·확인 모두 AUC ≥ 0.80(하한 ≥ 0.70)·거짓 빨강 ≤ 10%·표본 기준, 재검사 카파 ≥ 0.40(E1 칩 값)",
           "final_syllable": "reference", "reliable": res["reliable"], "system_gate": res["system_gate"], "sounds": sounds}
    json.dump(out, open(app_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(app_json, "a").write("\n")
    print("EXPORT_OK", app_json, res["reliable"])


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "explore":
        cmd_explore(*sys.argv[2:5])
    elif cmd == "confirm":
        args = sys.argv[2:]
        n_dir = None
        if "--n" in args:
            k = args.index("--n")
            n_dir = args[k + 1]
            args = args[:k] + args[k + 2:]
        cmd_confirm(args[0], args[1], args[2], n_dir)
    elif cmd == "s2":
        cmd_s2(*sys.argv[2:7])
    elif cmd == "a2":
        cmd_a2(*sys.argv[2:5])
    elif cmd == "export":
        cmd_export(*sys.argv[2:4])
