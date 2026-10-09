"""S2 음소 피드백 신뢰도 지도 분석(맥, numpy, 점수 파일만). docs/phoneme-feedback-reliability-2026-10.md 5·6절.

    python s2_phone_reliability.py analyze RUN_DIR OUT.json     파드 결과(run.*.jsonl) + 작업 목록 + 10/6 점수 → 소리별 집계·판정
    python s2_phone_reliability.py export OUT.json APP_JSON      판정을 통과했을 때만 앱 표(backend/data/phone_reliability.json)를 쓴다

RUN_DIR: 파드에서 받은 s2/out(run.*.jsonl). 작업 목록은 liplab-lab/data/s2stage/data/jobs.jsonl, 10/6 점수는 dgop_full.jsonl.
OUT.json에는 소리별 집계만 들어간다(문장·음소별 값 없음).
"""
import glob
import json
import math
import os
import re
import sys
import zlib
from collections import defaultdict

import numpy as np

LAB = os.environ.get("LAB", os.path.expanduser("~/Downloads/liplab-lab"))
JOBS = f"{LAB}/data/s2stage/data/jobs.jsonl"
DGOP_1006 = f"{LAB}/data/pod_runs/20261006_35zrgz6wvrqiho/sc/out/dgop_full.jsonl"
QUIET_A1 = {"spk332", "spk334", "spk337", "spk339", "spk342", "spk344", "spk347", "spk349", "spk352"}   # S16·S17의 조용 환경 9명
RED, GREEN = 45, 70
B, SEED = 2000, 0
# 끝 음절 포함 판정(docs/dgop-final-vowel-fix2-2026-10.md 6절): S2_INCLUDE_FINAL=1이면 끝 음절 토큰을 주 분석(양성)에 넣고 끝 모음 대치를
# 가까운 대치(음성)에 넣는다. 재검사 카파(B)는 평서·의문의 억양 차이 때문에 끝 음절을 계속 뺀다(S14와 같은 이유, 정렬과 무관).
INCLUDE_FINAL = os.environ.get("S2_INCLUDE_FINAL", "0") == "1"
CRIT = {"n_pos": 50, "n_neg": 30, "n_spk": 8, "auc": 0.80, "auc_lo": 0.70, "fr": 0.10,
        "kappa": 0.40, "n_pair": 30, "pe_hi": 0.85, "po_hi": 0.90, "per_sentence": 1.0}


def disp(x):
    """앱 칩 숫자: Math.round(naive * 100) = floor(100x + 0.5)."""
    return None if x is None else int(math.floor(100.0 * float(x) + 0.5))


def color(v):
    return "good" if v >= GREEN else "warn" if v >= RED else "bad"


def hangul(s):
    return re.sub(r"[^가-힣]", "", s or "")


def sid_of(text):
    return "s%08x" % zlib.crc32(hangul(text).encode())


def final_syllable_start(toks):
    idx = [i for i, t in enumerate(toks) if (t or "").startswith("n:")]
    if not idx:
        return len(toks)
    i = idx[-1]
    return i - 1 if i > 0 and (toks[i - 1] or "").startswith("o:") else i


# ───────── 히스토그램 기반 AUC(값이 0~100 정수) ─────────
def hist(vals):
    h = np.zeros(101)
    for v in vals:
        h[min(100, max(0, v))] += 1
    return h


def auc_h(hp, hn):
    """hp·hn: (..., 101). P(양성 > 음성) + 0.5 P(같음)."""
    np_, nn = hp.sum(-1), hn.sum(-1)
    above = np.cumsum(hp[..., ::-1], -1)[..., ::-1]          # above[v] = Σ_{u ≥ v} hp[u]
    gt = np.concatenate([above[..., 1:], np.zeros(hp.shape[:-1] + (1,))], -1)
    s = (hn * (gt + 0.5 * hp)).sum(-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return s / (np_ * nn)


class Boot:
    """화자 단위 부트스트랩. 소리마다 화자별 히스토그램을 두고 뽑힌 횟수로 더한다."""

    def __init__(self, spks, seed=SEED):
        self.spks = sorted(spks)
        rng = np.random.default_rng(seed)
        n = len(self.spks)
        self.M = np.stack([np.bincount(rng.integers(0, n, n), minlength=n) for _ in range(B)]).astype(float)   # (B, n)

    def mat(self, by_spk):
        return np.stack([hist(by_spk.get(s, [])) for s in self.spks])   # (n, 101)

    def auc_ci(self, pos_by, neg_by):
        hp, hn = self.M @ self.mat(pos_by), self.M @ self.mat(neg_by)
        a = auc_h(hp, hn)
        a = a[~np.isnan(a)]
        return [round(float(np.percentile(a, 2.5)), 4), round(float(np.percentile(a, 97.5)), 4)] if len(a) else [None, None]

    def rate_ci(self, by_spk, thr=RED):
        h = self.M @ self.mat(by_spk)
        with np.errstate(invalid="ignore", divide="ignore"):
            r = h[:, :thr].sum(1) / h.sum(1)
        r = r[~np.isnan(r)]
        return [round(float(np.percentile(r, 2.5)), 4), round(float(np.percentile(r, 97.5)), 4)] if len(r) else [None, None]


def kappa3(a, b):
    n = len(a)
    if not n:
        return None, None, None
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in ("good", "warn", "bad"))
    k = (po - pe) / (1 - pe) if pe < 1 else None
    return k, po, pe


# ───────── 자료 읽기 ─────────
def load_jobs():
    jobs = {j["clip"]: j for j in (json.loads(l) for l in open(JOBS, encoding="utf-8"))}
    if INCLUDE_FINAL:
        for j in jobs.values():
            j["fs"] = len(j["tokens"])
    return jobs


def load_run(run_dir):
    out = []
    for p in sorted(glob.glob(f"{run_dir}/run.*.jsonl")):
        for l in open(p, encoding="utf-8"):
            out.append(json.loads(l))
    return out


def load_1006():
    own538, own608, pairs = {}, [], []
    for l in open(DGOP_1006, encoding="utf-8"):
        r = json.loads(l)
        if "error" in r:
            continue
        if r["set"] == "538" and r["kind"] == "same":
            own538[r["clip"]] = r
        elif r["set"] == "608" and r["kind"] == "same":
            own608.append(r)
        elif r["set"] == "pair":
            pairs.append(r)
    return own538, own608, pairs


def chip_tokens(phones):
    """10/6 덤프의 phones → (자리, 토큰, 표시 값) 가운데 칩에 나오는 것(끝 음절 제외)과 끝 음절 것."""
    toks = [p["token"] for p in phones]
    cut = final_syllable_start(toks)
    main, fin = [], []
    for i, p in enumerate(phones):
        if p.get("aligned") and p.get("scorable") and not p.get("silent_h") and p.get("naive") is not None:
            (main if i < cut else fin).append((i, p["token"], disp(p["naive"])))
    return main, fin


# ───────── 분석 ─────────
def per_set(recs, jobs, st):
    pos, neg, aneg, fpos, fneg = (defaultdict(lambda: defaultdict(list)) for _ in range(5))
    errors = 0
    for r in recs:
        if r["set"] != st:
            continue
        if "error" in r:
            errors += 1
            continue
        j = jobs[r["clip"]]
        toks, fs, silent, spk = j["tokens"], j["fs"], set(j["silent_h"]), r["spk"]
        for i, (tok, v) in enumerate(zip(toks, r["orig"])):
            if tok == "|" or i in silent or v is None:
                continue
            (pos if i < fs else fpos)[tok][spk].append(disp(v))
        for kind, i, y, v, _all in r["subs"]:
            if v is None:
                continue
            if INCLUDE_FINAL and kind == "final":
                kind = "near"
            {"near": neg, "any": aneg, "final": fneg}[kind][y][spk].append(disp(v))
    return pos, neg, aneg, fpos, fneg, errors


def sound_stats(pos, neg, boot, aneg=None):
    out = {}
    for tok in sorted(set(pos) | set(neg)):
        p = [v for vs in pos.get(tok, {}).values() for v in vs]
        n = [v for vs in neg.get(tok, {}).values() for v in vs]
        d = {"n_pos": len(p), "n_neg": len(n), "spk_pos": len(pos.get(tok, {})), "spk_neg": len(neg.get(tok, {}))}
        if p and n:
            d["auc"] = round(float(auc_h(hist(p), hist(n))), 4)
            d["auc_ci"] = boot.auc_ci(pos[tok], neg[tok])
            d["detect_red"] = round(float(np.mean([v < RED for v in n])), 4)
            d["detect_notgreen"] = round(float(np.mean([v < GREEN for v in n])), 4)
        if p:
            d["fr"] = round(float(np.mean([v < RED for v in p])), 4)
            d["fr_ci"] = boot.rate_ci(pos[tok])
            d["pos_colors"] = {c: round(float(np.mean([color(v) == c for v in p])), 4) for c in ("good", "warn", "bad")}
        if aneg is not None:
            an = [v for vs in aneg.get(tok, {}).values() for v in vs]
            if p and an:
                d["auc_any"] = round(float(auc_h(hist(p), hist(an))), 4)
                d["n_any"] = len(an)
        out[tok] = d
    return out


def passes_naf(d):
    why = []
    if not (d.get("n_pos", 0) >= CRIT["n_pos"] and d.get("n_neg", 0) >= CRIT["n_neg"]
            and d.get("spk_pos", 0) >= CRIT["n_spk"] and d.get("spk_neg", 0) >= CRIT["n_spk"]):
        why.append("N")
    if not (d.get("auc") is not None and d["auc"] >= CRIT["auc"] and (d.get("auc_ci") or [None])[0] is not None
            and d["auc_ci"][0] >= CRIT["auc_lo"]):
        why.append("A")
    if not (d.get("fr") is not None and d["fr"] <= CRIT["fr"]):
        why.append("F")
    return not why, why


def kappa_by_sound(pairs):
    first = {}
    for r in pairs:
        sess = r["clip"].split(":")[0]
        form = "ques" if r["target"].rstrip()[-1:] in "?？" else "decl"
        first.setdefault((sess, sid_of(r["target"]), form), r)
    by = defaultdict(lambda: ([], []))
    allA, allB = [], []
    n_sent = 0
    for (sess, sid, form), r in first.items():
        if form != "decl" or (sess, sid, "ques") not in first:
            continue
        q = first[(sess, sid, "ques")]
        md = {i: (t, v) for i, t, v in chip_tokens(r["phones"])[0]}
        mq = {i: (t, v) for i, t, v in chip_tokens(q["phones"])[0]}
        n_sent += 1
        for i in sorted(set(md) & set(mq)):
            if md[i][0] != mq[i][0]:
                continue
            a, b = color(md[i][1]), color(mq[i][1])
            by[md[i][0]][0].append(a)
            by[md[i][0]][1].append(b)
            allA.append(a)
            allB.append(b)
    res = {}
    for tok, (a, b) in by.items():
        k, po, pe = kappa3(a, b)
        ok = len(a) >= CRIT["n_pair"] and ((pe is not None and pe >= CRIT["pe_hi"] and po >= CRIT["po_hi"])
                                           or (pe is not None and pe < CRIT["pe_hi"] and k is not None and k >= CRIT["kappa"]))
        res[tok] = {"n_pair": len(a), "kappa": None if k is None else round(k, 4), "po": round(po, 4), "pe": round(pe, 4),
                    "rule": "po" if (pe is not None and pe >= CRIT["pe_hi"]) else "kappa", "pass": bool(ok)}
    k, po, pe = kappa3(allA, allB)
    return res, {"n_sentences": n_sent, "n_pairs": len(allA), "kappa": round(k, 4), "po": round(po, 4)}


def bridge(recs, jobs, own538):
    diffs, agree, n, missing = [], 0, 0, 0
    for r in recs:
        if r["set"] != "A0" or "error" in r:
            continue
        ref = own538.get(r["clip"])
        if ref is None:
            missing += 1
            continue
        rt = [p["token"] for p in ref["phones"]]
        if rt != jobs[r["clip"]]["tokens"]:
            missing += 1
            continue
        for p, v in zip(ref["phones"], r["orig"]):
            if v is None or not (p.get("aligned") and p.get("scorable")) or p.get("naive") is None:
                continue
            diffs.append(abs(v - p["naive"]))
            agree += color(disp(v)) == color(disp(p["naive"]))
            n += 1
    d = np.array(diffs)
    out = {"tokens": n, "clips_missing": missing, "frac_le_0.001": round(float((d <= 0.001).mean()), 5) if n else None,
           "max_diff": round(float(d.max()), 5) if n else None, "chip_agree": round(agree / n, 5) if n else None}
    out["ok"] = bool(n and missing == 0 and out["frac_le_0.001"] >= 0.99 and out["chip_agree"] >= 0.995)
    return out


def sentence_reds(recs, jobs, R, st, spk_filter=None):
    """맞게 읽은 문장의 확정 빨강(R 소리, 끝 음절 밖, 표시 < 45) 수."""
    counts = []
    for r in recs:
        if r["set"] != st or "error" in r or (spk_filter and r["spk"] not in spk_filter):
            continue
        j = jobs[r["clip"]]
        silent = set(j["silent_h"])
        counts.append(sum(1 for i, (t, v) in enumerate(zip(j["tokens"], r["orig"]))
                          if i < j["fs"] and i not in silent and t in R and v is not None and disp(v) < RED))
    return counts


def sub_detection(recs, jobs, R, st):
    det, n, elsewhere = 0, 0, []
    for r in recs:
        if r["set"] != st or "error" in r:
            continue
        j = jobs[r["clip"]]
        silent = set(j["silent_h"])
        for kind, i, y, v, alld in r["subs"]:
            if kind not in (("near", "final") if INCLUDE_FINAL else ("near",)) or y not in R or v is None:
                continue
            n += 1
            det += disp(v) < RED
            elsewhere.append(sum(1 for k, (t, dv) in enumerate(zip(j["tokens"], alld))
                                 if k != i and k < j["fs"] and k not in silent and t in R and dv is not None and dv < RED))
    return {"n": n, "detect_red": round(det / n, 4) if n else None,
            "other_reds_per_sentence": round(float(np.mean(elsewhere)), 3) if elsewhere else None}


def own608_stats(own608, R):
    red = defaultdict(list)
    per_sent = []
    for r in own608:
        main, _fin = chip_tokens(r["phones"])
        if INCLUDE_FINAL:
            main = main + _fin
        for _i, t, v in main:
            red[t].append(v < RED)
        per_sent.append(sum(1 for _i, t, v in main if t in R and v < RED))
    return ({t: {"n": len(v), "red": round(float(np.mean(v)), 4)} for t, v in sorted(red.items())},
            round(float(np.mean(per_sent)), 3) if per_sent else None)


def analyze(run_dir, out_path):
    jobs = load_jobs()
    recs = load_run(run_dir)
    own538, own608, pairs = load_1006()
    res = {"criteria": CRIT, "records": len(recs), "jobs": len(jobs), "include_final": INCLUDE_FINAL}
    res["bridge"] = bridge(recs, jobs, own538)
    kap, kap_all = kappa_by_sound(pairs)
    res["kappa_all"] = kap_all
    res["kappa"] = kap
    stats = {}
    for st in ("A0", "A1"):
        pos, neg, aneg, fpos, fneg, err = per_set(recs, jobs, st)
        spks = {r["spk"] for r in recs if r["set"] == st}
        boot = Boot(spks)
        stats[st] = {"errors": err, "speakers": len(spks), "sounds": sound_stats(pos, neg, boot, aneg),
                     "final": sound_stats(fpos, fneg, boot)}
    res["sets"] = stats
    cand, rel, table = [], [], {}
    for tok in sorted(set(stats["A0"]["sounds"]) | set(stats["A1"]["sounds"])):
        e_ok, e_why = passes_naf(stats["A0"]["sounds"].get(tok, {}))
        k_ok = (kap.get(tok) or {}).get("pass", False)
        c_ok, c_why = passes_naf(stats["A1"]["sounds"].get(tok, {}))
        is_cand = e_ok and k_ok
        table[tok] = {"explore": e_why or "pass", "kappa": "pass" if k_ok else "fail", "confirm": (c_why or "pass") if is_cand else "-",
                      "reliable": bool(is_cand and c_ok)}
        if is_cand:
            cand.append(tok)
            if c_ok:
                rel.append(tok)
    res["decision_table"] = table
    res["candidates"] = cand
    res["reliable"] = rel
    R = set(rel)
    reds = sentence_reds(recs, jobs, R, "A1")
    res["system_gate"] = {
        "A1_definite_red_per_sentence": round(float(np.mean(reds)), 3) if reds else None,
        "A1_sentences": len(reds),
        "A1_quiet": round(float(np.mean(sentence_reds(recs, jobs, R, "A1", QUIET_A1))), 3) if reds else None,
        "A1_noisy": round(float(np.mean(sentence_reds(recs, jobs, R, "A1", {r["spk"] for r in recs if r["set"] == "A1"} - QUIET_A1))), 3) if reds else None,
        "A0_definite_red_per_sentence": round(float(np.mean(sentence_reds(recs, jobs, R, "A0"))), 3) if R else None,
        "A1_sub_detection": sub_detection(recs, jobs, R, "A1"),
        "A1_all_sounds_red_per_sentence": round(float(np.mean(sentence_reds(recs, jobs, set(stats["A1"]["sounds"]), "A1"))), 3),
    }
    g = res["system_gate"]
    res["pass"] = bool(res["bridge"]["ok"] and R and g["A1_definite_red_per_sentence"] is not None
                       and g["A1_definite_red_per_sentence"] <= CRIT["per_sentence"])
    s608, s608_sent = own608_stats(own608, R)
    res["own608"] = {"red_by_sound": s608, "definite_red_per_sentence": s608_sent, "sentences": len(own608)}
    json.dump(res, open(out_path, "w"), ensure_ascii=False, indent=1)
    print("BRIDGE", res["bridge"])
    print("KAPPA_ALL", kap_all)
    print("CANDIDATES", len(cand), cand)
    print("RELIABLE", len(rel), rel)
    print("SYSTEM", g)
    print("PASS", res["pass"])


def export(res_path, app_json):
    res = json.load(open(res_path))
    if not res.get("pass"):
        sys.exit("판정 미통과: 앱 표를 쓰지 않는다")
    a1 = res["sets"]["A1"]["sounds"]
    sounds = {}
    for tok, row in res["decision_table"].items():
        d = a1.get(tok, {})
        k = res["kappa"].get(tok, {})
        sounds[tok] = {"reliable": row["reliable"], "auc": d.get("auc"), "auc_ci": d.get("auc_ci"), "false_red": d.get("fr"),
                       "n_pos": d.get("n_pos"), "n_neg": d.get("n_neg"), "kappa": k.get("kappa"), "retest_agree": k.get("po"),
                       "n_retest": k.get("n_pair")}
    out = {
        "version": "2026-10-07",
        "source": "docs/phoneme-feedback-reliability-2026-10.md (S2). 538 인위 치환(확인 21명)·608 짝 세션 재검사의 소리별 집계값만 담는다.",
        "rule": "reliable = 탐색 58명·확인 21명 모두 AUC ≥ 0.80(하한 ≥ 0.70)·거짓 빨강 ≤ 10%·표본 기준, 재검사 카파 ≥ 0.40",
        "final_syllable": "reference",
        "final_syllable_note": "문장 끝 음절은 정렬기 끝 모음 결함(docs/dgop-final-vowel-2026-10.md) 수정 전까지 늘 참고. 수정 뒤 다시 측정한다.",
        "reliable": res["reliable"],
        "sounds": sounds,
    }
    json.dump(out, open(app_json, "w"), ensure_ascii=False, indent=1)
    open(app_json, "a").write("\n")
    print("EXPORT_OK", app_json, len(res["reliable"]))


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "analyze":
        analyze(sys.argv[2], sys.argv[3])
    elif cmd == "export":
        export(sys.argv[2], sys.argv[3])
    else:
        sys.exit(__doc__)
