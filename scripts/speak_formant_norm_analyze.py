"""모음 포먼트 혀 교정의 화자 정규화 비교(2026-09-29 사전 등록, docs/formant-validation.md).
파드 결과 out/app_dir.json(speak_app_direction_pod_eval.py)의 formant 행(화자 번호, 추정 F1·F2·F0)을 읽어 세 방법의 특이도·민감도를
538·608 각각, 화자 해시 절반(crc32 % 2)별로 낸다. 목표값·허용 폭은 backend/formants.py 그대로(문헌값, 이 자료에 맞추지 않음).
  B0 지금 앱: 문헌 목표 × F0 구간 배율
  N1 Lobanov: 평가 모음을 뺀 같은 화자 모음의 범주 평균(범주당 2개 이상, 범주 5개 이상)으로 z점수 → 같은 범주 문헌 목표의 평균·표준편차로
     되돌려 배율 없는 목표와 비교
  N2 모서리 모음 비: 평가 모음을 뺀 같은 화자 ㅏ·ㅣ·ㅜ 평균(각 2개 이상)이 문헌 목표의 몇 배인지 F1·F2 따로 기하평균해 목표에 곱함
판정(방법마다): 두 절반 모두 특이도가 B0보다 15%p 이상 오르고 민감도 88% 이상.
    python scripts/speak_formant_norm_analyze.py out/app_dir.json [요약.json]
"""
import collections
import json
import math
import os
import statistics
import sys
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
import formants as F  # noqa: E402

VOWELS = ["ㅣ", "ㅔ", "ㅐ", "ㅏ", "ㅓ", "ㅗ", "ㅜ", "ㅡ"]
CORNERS = ["ㅏ", "ㅣ", "ㅜ"]
T = F.VOWEL_TARGETS
MIN_CAT_TOK, MIN_CATS, MIN_CORNER_TOK = 2, 5, 2
SPEC_GAIN, SENS_MIN = 0.15, 0.88


def ok(f1, f2, t1, t2):
    """formants.vowel_feedback과 같은 판정: 높낮이·앞뒤 모두 'ok'인가."""
    r1, r2 = f1 / t1, f2 / t2
    return (1 / F._F1_TOL <= r1 <= F._F1_TOL) and (1 / F._F2_TOL <= r2 <= F._F2_TOL)


def b0(tok, _ctx):
    s = F.speaker_scale(tok.get("f0"))
    return {v: ok(tok["f1"], tok["f2"], T[v]["f1"] * s, T[v]["f2"] * s) for v in VOWELS}


def _loo_means(ctx, tok):
    """같은 화자·같은 무리의 범주별 (F1 평균, F2 평균, 개수), 평가 모음 하나를 뺀 값."""
    sums = ctx[(tok["group"], tok["spk"])]
    out = {}
    for v, (s1, s2, n) in sums.items():
        if v == tok["vowel"]:
            s1, s2, n = s1 - tok["f1"], s2 - tok["f2"], n - 1
        if n > 0:
            out[v] = (s1 / n, s2 / n, n)
    return out


def n1(tok, ctx):
    m = {v: x for v, x in _loo_means(ctx, tok).items() if x[2] >= MIN_CAT_TOK}
    if len(m) < MIN_CATS:
        return None
    cats = sorted(m)
    res = {}
    fh = []
    for i, key in ((0, "f1"), (1, "f2")):
        spk = [m[v][i] for v in cats]
        ref = [T[v][key] for v in cats]
        mu_s, sd_s = statistics.fmean(spk), statistics.pstdev(spk)
        mu_r, sd_r = statistics.fmean(ref), statistics.pstdev(ref)
        if sd_s <= 0:
            return None
        fh.append(mu_r + sd_r * (tok[key] - mu_s) / sd_s)
    if fh[0] <= 0 or fh[1] <= 0:
        return {v: False for v in VOWELS}
    for v in VOWELS:
        res[v] = ok(fh[0], fh[1], T[v]["f1"], T[v]["f2"])
    return res


def n2(tok, ctx):
    m = _loo_means(ctx, tok)
    if any(c not in m or m[c][2] < MIN_CORNER_TOK for c in CORNERS):
        return None
    k1 = math.exp(statistics.fmean(math.log(m[c][0] / T[c]["f1"]) for c in CORNERS))
    k2 = math.exp(statistics.fmean(math.log(m[c][1] / T[c]["f2"]) for c in CORNERS))
    return {v: ok(tok["f1"], tok["f2"], T[v]["f1"] * k1, T[v]["f2"] * k2) for v in VOWELS}


METHODS = {"B0": b0, "N1": n1, "N2": n2}


def rates(rows):
    spec = sum(r["v"][r["vowel"]] for r in rows) / len(rows)
    oth = [not r["v"][w] for r in rows for w in VOWELS if w != r["vowel"]]
    return spec, sum(oth) / len(oth)


def main(path, out=None):
    d = json.load(open(path))
    toks = [dict(f, group=r["group"], spk=r["spk"]) for r in d if "error" not in r for f in r.get("formant", [])]
    ctx = collections.defaultdict(lambda: collections.defaultdict(lambda: [0.0, 0.0, 0]))
    for t in toks:
        s = ctx[(t["group"], t["spk"])][t["vowel"]]
        s[0] += t["f1"]; s[1] += t["f2"]; s[2] += 1
    mism = 0
    ev = {m: [] for m in METHODS}
    n_all = collections.Counter(t["group"] for t in toks)
    for t in toks:
        vs = {m: f(t, ctx) for m, f in METHODS.items()}
        if vs["B0"][t["vowel"]] != t["own_ok_app"]:
            mism += 1
        if vs["N1"] is None or vs["N2"] is None:
            continue
        for m in METHODS:
            ev[m].append({"group": t["group"], "spk": t["spk"], "vowel": t["vowel"], "v": vs[m]})
    print(f"모음 {len(toks)} ({dict(n_all)}), B0 재계산이 앱 판정과 다른 수 {mism}")
    summary = {"n_tokens": dict(n_all), "b0_mismatch": mism, "groups": {}}
    for g in ("538", "608"):
        base = [r for r in ev["B0"] if r["group"] == g]
        spk_all = {t["spk"] for t in toks if t["group"] == g}
        spk_ev = {r["spk"] for r in base}
        print(f"\n===== {g}: 비교 모음 {len(base)} / {n_all[g]} ({len(base) / max(1, n_all[g]):.1%}), 화자 {len(spk_ev)} / {len(spk_all)}")
        G = summary["groups"][g] = {"n_eval": len(base), "n_all": n_all[g], "spk_eval": len(spk_ev), "spk_all": len(spk_all),
                                    "halves": {}, "verdict": {}, "per_vowel_spec": {}}
        for h in ("0", "1", "all"):
            G["halves"][h] = {}
            line = []
            for m in METHODS:
                rs = [r for r in ev[m] if r["group"] == g and (h == "all" or zlib.crc32(r["spk"].encode()) % 2 == int(h))]
                if not rs:
                    continue
                sp, se = rates(rs)
                G["halves"][h][m] = {"n": len(rs), "spk": len({r["spk"] for r in rs}), "spec": sp, "sens": se}
                line.append(f"{m} 특이도 {sp:.3f} 민감도 {se:.3f} (n {len(rs)}, 화자 {len({r['spk'] for r in rs})})")
            print(f"  절반 {h}: " + " | ".join(line))
        for m in ("N1", "N2"):
            checks = []
            for h in ("0", "1"):
                hb, hm = G["halves"][h].get("B0"), G["halves"][h].get(m)
                if not hb or not hm:
                    checks.append(False)
                    continue
                checks.append(hm["spec"] - hb["spec"] >= SPEC_GAIN and hm["sens"] >= SENS_MIN)
            G["verdict"][m] = all(checks)
            gains = [G["halves"][h][m]["spec"] - G["halves"][h]["B0"]["spec"] for h in ("0", "1") if m in G["halves"][h]]
            print(f"  판정 {m}: {'통과' if all(checks) else '미달'} (특이도 증가 절반별 " + ", ".join(f"{x:+.3f}" for x in gains) + ")")
        for m in METHODS:
            pv = {}
            for v in VOWELS:
                rs = [r for r in ev[m] if r["group"] == g and r["vowel"] == v]
                if rs:
                    pv[v] = [sum(r["v"][v] for r in rs) / len(rs), len(rs)]
            G["per_vowel_spec"][m] = pv
            print(f"  {m} 모음별 특이도: " + " ".join(f"{v} {x[0]:.2f}" for v, x in pv.items()))
    if out:
        json.dump(summary, open(out, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "out/app_dir.json", sys.argv[2] if len(sys.argv) > 2 else None)
