"""S17(GOP-SF)·S16(slplab AND 관문) 새 화자 측정 분석(사전 등록 docs/scoring-analyses-2026-10.md 8.4~8.6절). 파이썬 표준 + numpy만 쓴다.

    python scripts/s16_s17_newspk.py <s1617_raw.json.gz> [더 있으면 나열] [--out 결과.json]

입력은 파드의 liplab-lab/tools/s13_newspk.py measure가 만든 레코드(문장별 값, 저장소 밖). 출력은 집계만.
규칙(토큰 = 정렬됐고 채점 대상인 자모 토큰, 앱 음소 칩과 같은 단위):
  A     표시 점수 floor(100·dgop + 0.5) < 45(지금 앱)
  B3    dgop 가장 낮은 3개(동점은 앞 토큰)
  SF3   GOP-SF 사후확률(post) 가장 낮은 3개
  SFR   GOP-SF lpr < 0(같은 종류의 대치나 삭제가 목표보다 그럴듯함) = S17 빨강
  G16   B3 이면서 slplab이 정렬 구간에서 다른 소리를 들음 = S16 빨강(주)
  G16A  A 이면서 slplab이 다른 소리를 들음(보고만)
"""
import gzip
import json
import math
import sys
from collections import defaultdict

import numpy as np

RED = 45
BOOT, BOOT_AUC, SEED = 10000, 2000, 0
JUDGE_PAIRS, REPORT_PAIRS = ("ㅋ>ㄱ", "ㅍ>ㅂ"), ("ㄱ>ㅋ", "ㅂ>ㅍ")
MIN_538_SPK, MIN_538_SWAP, MIN_DIR_N = 10, 100, 20


def disp(g):
    return math.floor(100 * g + 0.5)


def units(u):
    return [i for i, g in enumerate(u["dg"]) if g is not None]


def flags(u, rule):
    U = units(u)
    dg = u["dg"]
    if rule == "A":
        return [i for i in U if disp(dg[i]) < RED]
    if rule == "B3":
        return sorted(U, key=lambda i: (dg[i], i))[:3]
    if rule == "SF3":
        V = [i for i in U if u["sf_post"][i] is not None]
        return sorted(V, key=lambda i: (u["sf_post"][i], i))[:3]
    if rule == "SFR":
        return [i for i in U if u["sf_lpr"][i] is not None and u["sf_lpr"][i] < 0]
    diff = {i for i in U if u["slp"][i] is not None and u["slp"][i]["diff"]}
    if rule == "G16":
        return [i for i in flags(u, "B3") if i in diff]
    if rule == "G16A":
        return [i for i in flags(u, "A") if i in diff]
    raise ValueError(rule)


RULES = ("A", "B3", "SF3", "SFR", "G16", "G16A")


class Boot:
    def __init__(self, spks, B, seed=SEED):
        self.spks = sorted(spks)
        self.ix = {s: i for i, s in enumerate(self.spks)}
        self.idx = np.random.default_rng(seed).integers(0, len(self.spks), size=(B, len(self.spks)))

    def _arr(self, pairs):
        num, den = np.zeros(len(self.spks)), np.zeros(len(self.spks))
        for s, n, d in pairs:
            num[self.ix[s]] += n
            den[self.ix[s]] += d
        return num, den

    def rate(self, pairs):
        num, den = self._arr(pairs)
        pt = num.sum() / den.sum() if den.sum() else float("nan")
        with np.errstate(invalid="ignore", divide="ignore"):
            bs = num[self.idx].sum(1) / den[self.idx].sum(1)
        bs = bs[np.isfinite(bs)]
        return {"est": round(float(pt), 4), "ci": [round(float(np.percentile(bs, q)), 4) for q in (2.5, 97.5)] if len(bs) else None,
                "num": float(num.sum()), "den": float(den.sum())}

    def diff(self, p1, p0):
        n1, d1 = self._arr(p1)
        n0, d0 = self._arr(p0)
        with np.errstate(invalid="ignore", divide="ignore"):
            pt = n1.sum() / d1.sum() - n0.sum() / d0.sum()
            bs = n1[self.idx].sum(1) / d1[self.idx].sum(1) - n0[self.idx].sum(1) / d0[self.idx].sum(1)
        bs = bs[np.isfinite(bs)]
        return {"est": round(float(pt), 4), "ci": [round(float(np.percentile(bs, q)), 4) for q in (2.5, 97.5)]}


def auc(pos, neg):
    if not pos or not neg:
        return float("nan")
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    gt = (pos[:, None] > neg[None, :]).sum()
    eq = (pos[:, None] == neg[None, :]).sum()
    return float((gt + 0.5 * eq) / (len(pos) * len(neg)))


def auc_boot(rows, seed=SEED):
    """rows = [(spk, 양성 점수, 음성 점수)] 화자 부트스트랩 구간."""
    spks = sorted({s for s, _, _ in rows})
    by = defaultdict(list)
    for s, p, n in rows:
        by[s].append((p, n))
    rng = np.random.default_rng(seed)
    bs = []
    for _ in range(BOOT_AUC):
        pick = rng.integers(0, len(spks), len(spks))
        pp = [p for i in pick for p, _ in by[spks[i]]]
        nn = [n for i in pick for _, n in by[spks[i]]]
        bs.append(auc(pp, nn))
    bs = [b for b in bs if b == b]
    return [round(float(np.percentile(bs, 2.5)), 4), round(float(np.percentile(bs, 97.5)), 4)] if bs else None


def onset_top1(rt, rs, mm, key):
    """초성 단위 loc_top1(phone_feedback_eval.onset_loc_top1과 같은 꼴): 교체 문장의 초성 점수 가운데 가장 낮은 것이 바뀐 음절인가."""
    on_t, on_s = rt.get("on_idx"), rs.get("on_idx")
    if on_t is None or on_s is None or len(on_t) != len(on_s):
        return None
    val = rs[key]
    us = [(val[k] if k is not None and rs["dg"][k] is not None else None) for k in on_s]
    sw = [j for j, k in enumerate(on_s) if k is not None and k in mm and us[j] is not None]
    valid = [(v, j) for j, v in enumerate(us) if v is not None]
    if not sw or len(valid) < 3:
        return None
    return int(sorted(valid)[0][1] in sw)


def load(paths):
    recs, seen = [], set()
    for p in paths:
        with gzip.open(p, "rt", encoding="utf-8") as f:
            obj = json.load(f)
        for r in obj["records"]:
            key = (r["set"], r["clip"], r["cond"])
            if key in seen:
                continue
            seen.add(key)
            recs.append(r)
    return recs


def s538(recs):
    out = {}
    rs = [r for r in recs if r["set"] == "538" and "fail" not in r and "swap" in r.get("u", {})]
    spks = sorted({r["spk"] for r in rs})
    boot = Boot(spks, BOOT)
    for cond in ("clean", "mod"):
        rc = [r for r in rs if r["cond"] == cond]
        sw, tr = [], []
        for r in rc:
            ut, us = r["u"]["true"], r["u"]["swap"]
            mm = [i for i in r.get("mm", []) if us["dg"][i] is not None]
            if mm and len(units(us)) >= 3:
                sw.append((r, set(mm)))
            if units(ut):
                tr.append(r)
        e = {"n_swap": len(sw), "n_true": len(tr), "n_spk": len({r["spk"] for r in rc}), "rules": {}}
        for rule in RULES:
            e["rules"][rule] = {
                "hit": boot.rate([(r["spk"], int(bool(set(flags(r["u"]["swap"], rule)) & mm)), 1) for r, mm in sw]),
                "ff_true": boot.rate([(r["spk"], len(flags(r["u"]["true"], rule)), 1) for r in tr])}
        e["d_hit3_SF3_minus_B3"] = boot.diff([(r["spk"], int(bool(set(flags(r["u"]["swap"], "SF3")) & mm)), 1) for r, mm in sw],
                                             [(r["spk"], int(bool(set(flags(r["u"]["swap"], "B3")) & mm)), 1) for r, mm in sw])
        for key, nm in (("sf_post", "SF"), ("dg", "DG")):
            vals = [(r["spk"], onset_top1(r["u"]["true"], r["u"]["swap"], mm, key)) for r, mm in sw]
            e[f"onset_loc_top1_{nm}"] = boot.rate([(s, v, 1) for s, v in vals if v is not None])
        if cond == "clean":
            bpos = [(r["spk"], int(i in set(flags(r["u"]["swap"], "G16"))), 1) for r, mm in sw for i in mm
                    if r["u"]["swap"]["toks"][i] == "o:ㅂ"]
            e["onset_b_detect_G16"] = {"flagged": int(sum(x for _, x, _ in bpos)), "n": len(bpos)}
            e["onset_b_detect_A"] = {"flagged": int(sum(int(i in set(flags(r["u"]["swap"], "A"))) for r, mm in sw for i in mm
                                                        if r["u"]["swap"]["toks"][i] == "o:ㅂ")), "n": len(bpos)}
            e["slp_heard_ok_true"] = boot.rate([(r["spk"], sum(1 for x in r["u"]["true"]["slp"] if x is not None and not x["diff"]),
                                                 sum(1 for x in r["u"]["true"]["slp"] if x is not None)) for r in tr])
        out[cond] = e
    out["speakers"] = spks
    return out


def s608(recs):
    rs = [r for r in recs if r["set"] == "608" and "fail" not in r and "true" in r.get("u", {})]
    if not rs:
        return {"n_clip": 0, "n_spk": 0, "ff_true": {}, "dir": {}}
    spks = sorted({r["spk"] for r in rs})
    boot = Boot(spks, BOOT)
    out = {"n_clip": len(rs), "n_spk": len(spks), "n_spk_P28": sum(1 for s in spks if s.startswith("28-")),
           "n_spk_P27": sum(1 for s in spks if s.startswith("27-")), "ff_true": {}, "dir": {}}
    tr = [r for r in rs if units(r["u"]["true"])]
    for rule in RULES:
        out["ff_true"][rule] = boot.rate([(r["spk"], len(flags(r["u"]["true"], rule)), 1) for r in tr])
        for st in ("28-", "27-"):
            out["ff_true"][f"{rule}_{st[:2]}"] = round(float(np.mean([len(flags(r["u"]["true"], rule)) for r in tr
                                                                      if r["spk"].startswith(st)])), 4) if any(
                r["spk"].startswith(st) for r in tr) else None
    for pair in JUDGE_PAIRS + REPORT_PAIRS:
        rows = {"dg": [], "sf": [], "gate": []}
        for r in rs:
            ut = r["u"]["true"]
            for name, ua in r["u"].items():
                if not name.startswith("alt") or ua.get("pair") != pair:
                    continue
                k = ua["k_alt"]
                if ut["dg"][k] is None or ua["dg"][k] is None:
                    continue
                rows["dg"].append((r["spk"], ut["dg"][k], ua["dg"][k]))
                if ut["sf_post"][k] is not None and ua["sf_post"][k] is not None:
                    rows["sf"].append((r["spk"], ut["sf_post"][k], ua["sf_post"][k]))

                def gate(u):
                    s = u["slp"][k]
                    return u["dg"][k] if (s is not None and s["diff"]) else 1.0
                rows["gate"].append((r["spk"], gate(ut), gate(ua)))
        e = {}
        for key, rr in rows.items():
            e[key] = {"auc": round(auc([p for _, p, _ in rr], [n for _, _, n in rr]), 4), "n": len(rr),
                      "n_spk": len({s for s, _, _ in rr}), "ci": auc_boot(rr) if rr else None}
            for st in ("28-", "27-"):
                sub = [x for x in rr if x[0].startswith(st)]
                e[key][f"auc_{st[:2]}"] = round(auc([p for _, p, _ in sub], [n for _, _, n in sub]), 4) if sub else None
                e[key][f"n_{st[:2]}"] = len(sub)
        e["gate_minus_dg"] = round(e["gate"]["auc"] - e["dg"]["auc"], 4) if e["dg"]["n"] else None
        out["dir"][pair] = e
    return out


def verdicts(a538, a608):
    """기준마다 True/False, 자료가 없으면 None(미측정). 608이 없으면 538 기준만 판정하고 전체 판정은 보류한다."""
    c, m = a538["clean"], a538["mod"]
    valid538 = len(a538["speakers"]) >= MIN_538_SPK and c["n_swap"] >= MIN_538_SWAP
    has608 = a608["n_clip"] > 0
    dir_ok = has608 and all(a608["dir"][p]["sf"]["n"] >= MIN_DIR_N for p in JUDGE_PAIRS)
    r538 = c["rules"]["G16"]["ff_true"]["est"]
    s17 = {"C1_clean_onset_loc_top1_SF>=0.93": c["onset_loc_top1_SF"]["est"] >= 0.93,
           "C2_mod_hit3_SF3-B3>=+0.03_and_CIlo>0": (m["d_hit3_SF3_minus_B3"]["est"] >= 0.03 and m["d_hit3_SF3_minus_B3"]["ci"][0] > 0),
           "C3_608_auc_SF>=0.80(ㅋ>ㄱ,ㅍ>ㅂ)": (all(a608["dir"][p]["sf"]["auc"] >= 0.80 for p in JUDGE_PAIRS) if dir_ok else None),
           "C4_538_clean_true_SFR_per_sentence<=1": c["rules"]["SFR"]["ff_true"]["est"] <= 1.0}
    s16 = {"C1_538_clean_true_G16_per_sentence<=1": r538 <= 1.0,
           "C2_538_clean_detect_G16>=0.80_CIlo>=0.70": (c["rules"]["G16"]["hit"]["est"] >= 0.80 and c["rules"]["G16"]["hit"]["ci"][0] >= 0.70),
           "C3_onset_b_detect>0": c["onset_b_detect_G16"]["flagged"] > 0,
           "C4_608_false_red<=2x538": (a608["ff_true"]["G16"]["est"] <= 2 * max(r538, 0.01) if has608 else None),
           "C5_608_gate_auc_drop<=0.03(ㅋ>ㄱ,ㅍ>ㅂ)": (all(a608["dir"][p]["gate_minus_dg"] >= -0.03 for p in JUDGE_PAIRS) if dir_ok else None)}

    def v(c_):
        if not valid538:
            return "판정 불가(538 표본 부족)"
        if any(x is False for x in c_.values()):
            return "실패"
        if any(x is None for x in c_.values()):
            return "보류(608 기준 미측정, 538 기준은 모두 통과)"
        return "통과"
    return {"S17": {"criteria": s17, "verdict": v(s17)}, "S16": {"criteria": s16, "verdict": v(s16)},
            "valid": {"538": valid538, "608_present": has608, "dir_n": dir_ok}}


def main():
    args = sys.argv[1:]
    out_path = None
    if "--out" in args:
        i = args.index("--out")
        out_path = args[i + 1]
        args = args[:i] + args[i + 2:]
    recs = load(args)
    a538, a608 = s538(recs), s608(recs)
    res = {"n_records": len(recs), "n_fail": sum(1 for r in recs if "fail" in r), "538": a538, "608": a608,
           "verdicts": verdicts(a538, a608)}
    txt = json.dumps(res, ensure_ascii=False, indent=1)
    if out_path:
        open(out_path, "w").write(txt)
    print(json.dumps(res["verdicts"], ensure_ascii=False, indent=1))
    print("S17_VERDICT", res["verdicts"]["S17"]["verdict"], "S16_VERDICT", res["verdicts"]["S16"]["verdict"])


if __name__ == "__main__":
    main()
