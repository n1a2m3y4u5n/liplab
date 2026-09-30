"""SpeechSuper 대조군 비교 분석(docs/speak-transcript-scoring.md). speechsuper_compare.py 결과(jsonl)를 읽는다.
꼬리표는 '세트:same|diff:D-GOP점수'. 세트별 AUC(맞게 말함 대 다르게 말함), 538 다르게 말함 합격 5% 이하인 가장 낮은 합격선에서
608 맞게 말함 불합격률, 맞게 말함 안의 순위상관을 D-GOP와 나란히 낸다.
    python scripts/speechsuper_analyze.py <결과.jsonl> [요약.json]
"""
import json
import os
import sys
import zlib


def auc(pos, neg):
    return sum((a > b) + 0.5 * (a == b) for a in pos for b in neg) / (len(pos) * len(neg))


def rank(v):
    o = sorted(range(len(v)), key=lambda i: v[i]); r = [0.0] * len(v); i = 0
    while i < len(o):
        j = i
        while j < len(o) and v[o[j]] == v[o[i]]:
            j += 1
        for k in range(i, j):
            r[o[k]] = (i + j - 1) / 2
        i = j
    return r


def spearman(a, b):
    ra, rb = rank(a), rank(b); n = len(a); ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return num / den if den else float("nan")


def spk(path, st):
    b = os.path.basename(path)
    return b.split("-")[4] if st == "608" else b.split("_")[0]


rows = []
for l in open(sys.argv[1], encoding="utf-8"):
    j = json.loads(l)
    if j.get("status") != "ok":
        continue
    st, kind, dg = j["tag"].split(":")
    res = j["result"]
    rows.append({"set": st, "kind": kind, "dgop": float(dg), "ss": float(res.get("overall", 0)), "pron": float(res.get("pronunciation", 0)),
                 "half": zlib.crc32(spk(j["path"], st).encode()) % 2})
out = {"n": len(rows)}
for st in ("538", "608"):
    for key in ("dgop", "ss", "pron"):
        for half in ("all", 0, 1):
            rs = [r for r in rows if r["set"] == st and (half == "all" or r["half"] == half)]
            s, d = [r[key] for r in rs if r["kind"] == "same"], [r[key] for r in rs if r["kind"] == "diff"]
            if s and d:
                out[f"auc_{st}_{key}_{half}"] = round(auc(s, d), 4)
    rs = [r for r in rows if r["set"] == st]
    out[f"n_{st}_same"] = sum(r["kind"] == "same" for r in rs); out[f"n_{st}_diff"] = sum(r["kind"] == "diff" for r in rs)
    same = [r for r in rs if r["kind"] == "same"]
    out[f"rho_{st}_same"] = round(spearman([r["dgop"] for r in same], [r["ss"] for r in same]), 3)
    out[f"median_{st}_same_ss"] = sorted(r["ss"] for r in same)[len(same) // 2]
    out[f"median_{st}_diff_ss"] = sorted(r["ss"] for r in rs if r["kind"] == "diff")[sum(r["kind"] == "diff" for r in rs) // 2]
for key in ("dgop", "ss"):
    d538 = [r[key] for r in rows if r["set"] == "538" and r["kind"] == "diff"]
    thr = next(t for t in range(0, 101) if sum(x >= t for x in d538) / len(d538) <= 0.05)
    for st in ("538", "608"):
        s = [r[key] for r in rows if r["set"] == st and r["kind"] == "same"]
        d = [r[key] for r in rows if r["set"] == st and r["kind"] == "diff"]
        out[f"thr_{key}"] = thr
        out[f"ff_{st}_{key}"] = round(sum(x < thr for x in s) / len(s), 4)
        out[f"wp_{st}_{key}"] = round(sum(x >= thr for x in d) / len(d), 4)
print(json.dumps(out, ensure_ascii=False, indent=1))
if len(sys.argv) > 2:
    json.dump(out, open(sys.argv[2], "w"), ensure_ascii=False)
