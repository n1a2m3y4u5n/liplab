#!/usr/bin/env python
"""
0점 음소가 있어도 합격하는 문장 점수: 최저 음소 규칙 확인(docs/speak-phoneme-floor-2026-10.md, 사전 등록).

기존 D-GOP 음소 덤프만 읽는다(새 추론 없음). 문장별 값은 출력하지 않고 집계만 낸다.

  python scripts/speak_phoneme_floor.py                    # 탐색(절반 0) → 후보 선택 → 확인(절반 1), JSON 요약
  python scripts/speak_phoneme_floor.py --out x.json       # 요약을 파일로

자료 위치는 LIPLAB_LAB(기본 ~/Downloads/liplab-lab)/data/pod_runs 아래(등록 문서 3절).
"""
import argparse
import gzip
import json
import os
import random
import re
import sys
import zlib
from collections import defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(ROOT, "backend"))
import dgop  # noqa: E402
from phone_reliability import final_syllable_start  # noqa: E402

LAB = os.environ.get("LIPLAB_LAB", os.path.expanduser("~/Downloads/liplab-lab"))
PR = os.path.join(LAB, "data", "pod_runs")
CAL = json.load(open(os.path.join(ROOT, "backend", "data", "dgop_calibration_ours.json"), encoding="utf-8"))
PASS = 65.0

SRC = {
    "538a_full": "20261006_uoqtuk2pyq0nty/s13/out/dgop_full.jsonl",
    "538a_sub": "20261006_uoqtuk2pyq0nty/s13/out/s1617_raw.json.gz",
    "sc_full": "20261006_35zrgz6wvrqiho/sc/out/dgop_full.jsonl",
    "608own": "20261009_mw1qp1djnxt56q/s20/out/dgop.jsonl",
    "608s18_full": "20261009_mbcupc334etjby/s13/out/dgop_full.jsonl",
    "608s18_sub": "20261009_mbcupc334etjby/s13/out/s1617_raw.json.gz",
}

CANDS = [("F", t) for t in (0.005, 0.01, 0.02, 0.05, 0.10)] + [("W", w) for w in (0.1, 0.2, 0.3)]


def hangul(s):
    return re.sub(r"[^가-힣]", "", s or "")


def spk608(clip):
    """세션 파일 이름의 화자 부분: 이니셜 3글자(절반), 이니셜-성별-나이(화자 키)."""
    f = clip.split(":")[0].split("-")
    j = next(k for k in range(5, len(f)) if f[k] in ("M", "F"))
    return f[4], f"{f[4]}-{f[j]}-{f[j + 1]}"


def half_of(s):
    return zlib.crc32(s.encode("utf-8")) % 2


def rec_from_phones(phones):
    """dgop_full·s20 덤프의 phones → (평균용 값 목록, 최저용 값 목록)."""
    key = "naive" if phones and "naive" in phones[0] else "dgop"
    toks = [p.get("token") or "" for p in phones]
    cut = final_syllable_start(toks)
    mean_vals = [p[key] for p in phones if p.get("aligned") and p.get("scorable") and p.get(key) is not None]
    min_vals = [p[key] for i, p in enumerate(phones) if i < cut and p.get("aligned") and p.get("scorable")
                and not p.get("silent_h") and p.get(key) is not None]
    return mean_vals, min_vals


def rec_from_toks(toks, dg):
    cut = final_syllable_start(toks)
    mean_vals = [g for g in dg if g is not None]
    min_vals = [g for i, g in enumerate(dg) if i < cut and g is not None]
    return mean_vals, min_vals


def make(group, kind, spk, half, score, mean_vals, min_vals):
    return {"group": group, "kind": kind, "spk": spk, "half": half, "score": float(score),
            "mean": sum(mean_vals) / len(mean_vals) if mean_vals else 0.0,
            "min": min(min_vals) if min_vals else None}


def load():
    rows = []
    own608 = {}
    # 608 자기 문장(지금 앱 경로, 끝 자르기)
    for line in open(os.path.join(PR, SRC["608own"]), encoding="utf-8"):
        d = json.loads(line)
        ini, key = spk608(d["clip"])
        mv, nv = rec_from_phones(d["phones"])
        rows.append(make("608", "own", key, half_of(ini), d["score"], mv, nv))
        own608[d["clip"]] = True
    # 608-s18 다른 문장
    for line in open(os.path.join(PR, SRC["608s18_full"]), encoding="utf-8"):
        d = json.loads(line)
        if d["kind"] != "diff":
            continue
        ini, key = spk608(d["clip"])
        mv, nv = rec_from_phones(d["phones"])
        rows.append(make("608", "other", key, half_of(ini), d["score"], mv, nv))
    # 608-s18 대치 목표
    for x in json.load(gzip.open(os.path.join(PR, SRC["608s18_sub"])))["records"]:
        ini, key = spk608(x["clip"])
        for k, u in x["u"].items():
            if k == "true":
                continue
            mv, nv = rec_from_toks(u["toks"], u["dg"])
            rows.append(make("608", "sub", key, half_of(ini), u["disp"], mv, nv))
    # 10/6 sc: 538 자기·다른·반례, 608 다른·반례(조각이 608-own에 있는 것만, 자기 문장과 같은 한글 문자열 제외)
    own_txt = {}
    sc = [json.loads(l) for l in open(os.path.join(PR, SRC["sc_full"]), encoding="utf-8")]
    for d in sc:
        if d["kind"] == "same":
            own_txt[(d["set"], d["clip"])] = hangul(d["target"])
    for d in sc:
        kind = {"same": "own", "diff": "other", "cohort": "cohort"}.get(d["kind"])
        if kind is None or d["set"] not in ("538", "608"):
            continue
        if d["set"] == "608":
            if kind == "own" or d["clip"] not in own608:
                continue
            if hangul(d["target"]) == own_txt.get(("608", d["clip"])):
                continue
            ini, key = spk608(d["clip"])
            h = half_of(ini)
        else:
            key = d["spk"]
            h = half_of(key)
        mv, nv = rec_from_phones(d["phones"])
        rows.append(make(d["set"], kind, key, h, d["score"], mv, nv))
    # 538-a 자기·다른
    for line in open(os.path.join(PR, SRC["538a_full"]), encoding="utf-8"):
        d = json.loads(line)
        kind = {"same": "own", "diff": "other"}[d["kind"]]
        mv, nv = rec_from_phones(d["phones"])
        rows.append(make("538", kind, d["spk"], half_of(d["spk"]), d["score"], mv, nv))
    # 538-a 교체 목표(조용·중)
    for x in json.load(gzip.open(os.path.join(PR, SRC["538a_sub"])))["records"]:
        u = x["u"]["swap"]
        mv, nv = rec_from_toks(u["toks"], u["dg"])
        rows.append(make("538", "sub" if x["cond"] == "clean" else "sub_mod", x["spk"], half_of(x["spk"]), u["disp"], mv, nv))
    return rows


def passes(r, cand):
    """후보 규칙 아래 합격인가(지금 합격인 시도에만 작용)."""
    if r["score"] < PASS:
        return False
    if cand is None or r["min"] is None:
        return True
    kind, v = cand
    if kind == "F":
        return r["min"] >= v
    raw = ((1 - v) * r["mean"] + v * r["min"]) * 100.0
    return dgop.calibrate_score(raw, CAL) >= PASS


def drop_rate(rs, cand):
    base = [r for r in rs if r["score"] >= PASS]
    if not base:
        return None, 0
    return sum(not passes(r, cand) for r in base) / len(base), len(base)


def pass_rate(rs, cand):
    return (sum(passes(r, cand) for r in rs) / len(rs)) if rs else None


def metrics(rows, cand):
    out = {}
    for g in ("538", "608"):
        own = [r for r in rows if r["group"] == g and r["kind"] == "own"]
        sub = [r for r in rows if r["group"] == g and r["kind"] == "sub"]
        fh, n_own = drop_rate(own, cand)
        cs, n_sub = drop_rate(sub, cand)
        out[g] = {"FH": fh, "CS": cs, "NG": None if fh is None or cs is None else cs - fh, "n_own_pass": n_own, "n_sub_pass": n_sub}
    return out


def meets_point(m):
    return (m["538"]["FH"] <= 0.03 and m["608"]["FH"] <= 0.08 and m["538"]["CS"] >= 0.30 and m["608"]["NG"] >= 0)


def boot(rows, cand, n=2000, seed=20261009):
    rng = random.Random(seed)
    res = {"538": defaultdict(list), "608": defaultdict(list)}
    for g in ("538", "608"):
        rs = [r for r in rows if r["group"] == g and r["kind"] in ("own", "sub")]
        by = defaultdict(list)
        for r in rs:
            by[r["spk"]].append(r)
        spks = sorted(by)
        pre = {s: {} for s in spks}
        for s in spks:
            for kind in ("own", "sub"):
                b = [r for r in by[s] if r["kind"] == kind and r["score"] >= PASS]
                pre[s][kind] = (len(b), sum(not passes(r, cand) for r in b))
        for _ in range(n):
            pick = [rng.choice(spks) for _ in spks]
            no = sum(pre[s]["own"][0] for s in pick)
            do = sum(pre[s]["own"][1] for s in pick)
            ns = sum(pre[s]["sub"][0] for s in pick)
            ds = sum(pre[s]["sub"][1] for s in pick)
            if no == 0 or ns == 0:
                continue
            res[g]["FH"].append(do / no)
            res[g]["CS"].append(ds / ns)
            res[g]["NG"].append(ds / ns - do / no)

    def ci(xs):
        xs = sorted(xs)
        return [round(xs[int(0.025 * len(xs))], 4), round(xs[min(len(xs) - 1, int(0.975 * len(xs)))], 4)]
    return {g: {k: ci(v) for k, v in d.items()} for g, d in res.items()}


def report(rows, cand):
    """보고 지표: 다른 문장·반례·중 조건 교체의 합격률 변화, 자기 문장 합격률, 화자별 거짓 보류."""
    out = {}
    for g in ("538", "608"):
        for kind in ("own", "other", "cohort", "sub", "sub_mod"):
            rs = [r for r in rows if r["group"] == g and r["kind"] == kind]
            if not rs:
                continue
            out[f"{g}_{kind}"] = {"n": len(rs), "spk": len({r["spk"] for r in rs}),
                                  "pass_now": round(pass_rate(rs, None), 4), "pass_rule": round(pass_rate(rs, cand), 4),
                                  "no_min": sum(r["min"] is None for r in rs)}
        own = [r for r in rows if r["group"] == g and r["kind"] == "own"]
        per = {}
        for s in sorted({r["spk"] for r in own}):
            fh, n = drop_rate([r for r in own if r["spk"] == s], cand)
            if fh is not None:
                per[s] = (round(fh, 3), n)
        vals = sorted(v for v, _ in per.values())
        out[f"{g}_own_FH_by_speaker"] = {"speakers": len(vals), "zero": sum(v == 0 for v in vals),
                                         "median": vals[len(vals) // 2] if vals else None, "max": vals[-1] if vals else None,
                                         "over_20pct": sum(v > 0.2 for v in vals)}
    return out


def r4(m):
    return {g: {k: (round(v, 4) if isinstance(v, float) else v) for k, v in d.items()} for g, d in m.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    a = ap.parse_args()
    rows = load()
    explore = [r for r in rows if r["half"] == 0]
    confirm = [r for r in rows if r["half"] == 1]
    counts = {}
    for h, rs in (("explore", explore), ("confirm", confirm)):
        c = defaultdict(int)
        sp = defaultdict(set)
        for r in rs:
            c[f"{r['group']}_{r['kind']}"] += 1
            sp[f"{r['group']}_{r['kind']}"].add(r["spk"])
        counts[h] = {k: [v, len(sp[k])] for k, v in sorted(c.items())}
    ex = {f"{k}({v})": r4(metrics(explore, (k, v))) for k, v in CANDS}
    ok = [(k, v) for k, v in CANDS if meets_point(metrics(explore, (k, v)))]
    if ok:
        pick = max(ok, key=lambda c: (metrics(explore, c)["538"]["NG"], -metrics(explore, c)["538"]["FH"]))
        stage = "확인"
    else:
        pick = max(CANDS, key=lambda c: (metrics(explore, c)["538"]["NG"], -metrics(explore, c)["538"]["FH"]))
        stage = "실패(탐색)"
    cm = metrics(confirm, pick)
    ci = boot(confirm, pick)
    k = {
        "K1": cm["538"]["FH"] <= 0.03 and ci["538"]["FH"][1] <= 0.05,
        "K2": cm["608"]["FH"] <= 0.08 and ci["608"]["FH"][1] <= 0.12,
        "K3": cm["538"]["CS"] >= 0.30 and ci["538"]["NG"][0] > 0,
        "K4": cm["608"]["NG"] >= 0,
    }
    verdict = "통과" if stage == "확인" and all(k.values()) else ("실패(탐색)" if stage != "확인" else "실패(확인)")
    out = {"counts": counts, "explore": ex, "explore_meets_point": [f"{c}({v})" for c, v in ok],
           "picked": f"{pick[0]}({pick[1]})", "stage": stage,
           "confirm": r4(cm), "confirm_ci": ci, "criteria": k, "verdict": verdict,
           "confirm_report": report(confirm, pick), "explore_report_picked": report(explore, pick),
           "confirm_all_candidates": {f"{c}({v})": r4(metrics(confirm, (c, v))) for c, v in CANDS}}
    s = json.dumps(out, ensure_ascii=False, indent=1)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(s)
    print(s)


if __name__ == "__main__":
    main()
