import json, math, sys, zlib
import numpy as np
d = json.load(open(sys.argv[1]))
half = sys.argv[2] if len(sys.argv) > 2 else "all"
def st(a, b): return 12 * math.log2(b / a) if a > 0 and b > 0 else 0.0
def med3(ps):
    return [float(np.median(ps[max(0, i - 1): i + 2])) for i in range(len(ps))]
def m0(ps):
    h = ps[: max(1, round(len(ps) * 0.3))]; t = ps[int(len(ps) * 0.7):]
    return st(np.mean(h), np.mean(t))
def m1(ps, k=3, back=8):
    q = med3(ps)
    end = np.median(q[-k:]); base = min(q[-back:-k]) if len(q) > back else min(q[:-k] or q)
    return st(base, end)
def m2(ps, k=3):
    q = med3(ps); return st(np.median(q), np.median(q[-k:]))
def m3(ps, k=3, back=8):
    q = med3(ps); end = np.median(q[-k:]); base = np.median(q[-back:-k]) if len(q) > back else np.median(q[:-k] or q)
    return st(base, end)
def auc(pos, neg):
    pos, neg = np.array(pos), np.array(neg)
    return float(((pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()) / (len(pos) * len(neg)))
rows = [r for r in d if len(r["ps"]) >= 6]
if half != "all":
    rows = [r for r in rows if (zlib.crc32(r["spk"].encode()) % 2) == int(half)]
g = {k: [r for r in rows if r["grp"] == k] for k in ("ynq", "whq", "stmt")}
print("n", {k: len(v) for k, v in g.items()}, "speakers", len({r['spk'] for r in rows}))
for name, f in (("M0 앞30/뒤30", m0), ("M1 끝3 vs 직전최저", m1), ("M2 끝3 vs 전체중앙", m2), ("M3 끝3 vs 직전중앙", m3),
                ("M1 k2 b6", lambda p: m1(p, 2, 6)), ("M1 k2 b8", lambda p: m1(p, 2, 8)), ("M3 k2 b6", lambda p: m3(p, 2, 6))):
    v = {k: [f(r["ps"]) for r in g[k]] for k in g}
    line = f"{name:18s} AUC(예/아니오 vs 평서) {auc(v['ynq'], v['stmt']):.3f}  AUC(의문사 vs 평서) {auc(v['whq'], v['stmt']):.3f}"
    for T in (1.0, 1.33, 2.0, 3.0):
        line += f" | T{T}: ynq↑{np.mean(np.array(v['ynq']) > T):.2f} whq↑{np.mean(np.array(v['whq']) > T):.2f} stmt↑{np.mean(np.array(v['stmt']) > T):.2f} stmt↓{np.mean(np.array(v['stmt']) < -T):.2f}"
    print(line)
