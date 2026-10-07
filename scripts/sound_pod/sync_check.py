"""음절 시각 품질 점검: 정렬기(자체 학습 정렬기)와 두 번째 정렬기(채점기를 정렬기로)의 음절 시작 차, 정렬 성공률, 소리 길이 안에 드는지.
    python sync_check.py EVAL_JSONL... → 요약 JSON"""
import json, statistics as st, sys

recs = []
for p in sys.argv[1:]:
    for line in open(p, encoding="utf-8"):
        try:
            recs.append(json.loads(line))
        except ValueError:
            pass
n = len(recs)
ok = [r for r in recs if r.get("timing_ok")]
diffs, ends, firsts, cover = [], [], [], []
for r in ok:
    a, b = r.get("syl"), r.get("syl_alt")
    if b and len(a) == len(b):
        diffs += [abs(x[0] - y[0]) for x, y in zip(a, b)]
        ends += [abs(x[1] - y[1]) for x, y in zip(a, b)]
    dur = r["dur"] * 1000
    firsts.append(a[0][0])
    cover.append((a[-1][1] - a[0][0]) / dur)


def q(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))] if xs else None


out = {"clips": n, "timing_ok": len(ok), "timing_ok_rate": round(len(ok) / n, 4) if n else None,
       "start_diff_ms": {"n": len(diffs), "median": q(diffs, 0.5), "p90": q(diffs, 0.9), "p99": q(diffs, 0.99),
                         "within_40ms": round(sum(d <= 40 for d in diffs) / len(diffs), 4) if diffs else None},
       "end_diff_ms": {"median": q(ends, 0.5), "p90": q(ends, 0.9)},
       "first_syllable_start_ms": {"median": q(firsts, 0.5), "p10": q(firsts, 0.1), "p90": q(firsts, 0.9)},
       "speech_span_over_duration": {"median": round(q(cover, 0.5), 3) if cover else None}}
asr = [r for r in recs if "cer" in r and r["cer"].get("base") is not None]
if asr:
    out["asr_base_exact"] = round(sum(r["cer"]["base"] == 0 for r in asr) / len(asr), 4)
dg = [r["dgop"] for r in recs if r.get("dgop") is not None]
if dg:
    out["dgop_mean"] = round(st.mean(dg), 2)
    out["dgop_p10"] = q(dg, 0.1)
print(json.dumps(out, ensure_ascii=False, indent=1))
