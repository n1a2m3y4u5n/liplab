"""전사 경로 채점 비교(docs/speak-transcript-scoring.md). 파드 결과 out/asr.json·out/cuts608.json을 읽는다.

    ~/Downloads/liplab/backend/.venv/bin/python analyze.py <out 폴더> <half: 0|1|all> [--vad]

R0(지금): calculate_jamo_score = 맞힌 점수 / 정답 음절 수(재현율). R1: 2PR/(P+R), P = 맞힌 점수 / 전사 음절 수.
맞게 말함: 클립의 자기 문장을 목표로. 다르게 말함: 같은 세트의 다른 문장(음절 수 ±30%)을 목표로(클립마다 3개).
잡음: 무음·잡음 합성의 전사를 5단계 문항 16개에 대어 본다.
화자 절반: 538은 화자 ID, 608은 파일(화자) 해시.
"""
import json
import os
import random
import re
import sys
import zlib

sys.path.insert(0, os.path.expanduser("~/Downloads/liplab-integrate/backend"))
os.environ.setdefault("LIPLAB_CONTENT_WARMUP", "0")
from scoring import align_jamos, _syllable_match_score, to_pronounced_jamos  # noqa: E402
import speak_curriculum as sc  # noqa: E402

out_dir, half = sys.argv[1], sys.argv[2]
key = "vad" if "--vad" in sys.argv else "novad"
asr = json.load(open(f"{out_dir}/asr.json"))
cuts = json.load(open(f"{out_dir}/cuts608.json"))


def clean(s):
    return re.sub(r"[^가-힣0-9]", "", s or "")


def scores(target, trans):
    c, u = to_pronounced_jamos(clean(target)), to_pronounced_jamos(clean(trans))
    if not c or not u:
        return 0.0, 0.0
    ach = sum(_syllable_match_score(a, b) for a, b in align_jamos(c, u) if a and b)
    r = ach / len(c)
    p = ach / len(u)
    f = 2 * p * r / (p + r) if p + r else 0.0
    return 100 * r, 100 * f


def in_half(spk):
    return half == "all" or zlib.crc32(spk.encode()) % 2 == int(half)


rows = []   # (set, spk, target, transcript)
man = {}
for l in open(os.path.expanduser("~/Downloads/liplab_gpu_snapshot/expand538_more/manifest.tsv"), encoding="utf-8"):
    clip, spk, text = l.rstrip("\n").split("\t")
    man[clip.replace(".mp4", "")] = (spk, text)
for p, o in asr["c538"].items():
    stem = os.path.basename(p)[:-5]
    if stem in man:
        rows.append(("538", man[stem][0], man[stem][1], o[key]))
for c in cuts:
    if c["cut"] and c["cut"] in asr["s608"]:
        spk = c["file"].split("-")[4]
        rows.append(("608", spk, c["target"], asr["s608"][c["cut"]][key]))
rows = [r for r in rows if in_half(r[1])]

rng = random.Random(0)
res = {}
for st in ("538", "608"):
    rs = [r for r in rows if r[0] == st]
    same = [scores(t, tr) for _, _, t, tr in rs]
    diff = []
    pool = [r[2] for r in rs]
    for _, _, t, tr in rs:
        n = len(clean(t))
        cand = [x for x in pool if x != t and 0.7 * n <= len(clean(x)) <= 1.3 * n]
        for x in rng.sample(cand, min(3, len(cand))):
            diff.append(scores(x, tr))
    res[st] = {"n": len(rs), "speakers": len({r[1] for r in rs}), "same": same, "diff": diff}

stage5 = [it["target"] for it in sc.get_stage(5)["items"]]
noise = [(os.path.basename(p), o[key]) for p, o in asr["noise"].items()]
noise_scores = [scores(t, tr) for _, tr in noise if clean(tr) for t in stage5]


def rate(xs, i, thr, above=True):
    return round(sum((x[i] >= thr) == above for x in xs) / max(1, len(xs)), 4)


print(f"transcript={key} half={half}")
print("noise transcripts non-empty:", sum(1 for _, t in noise if clean(t)), "/", len(noise), [t for _, t in noise if clean(t)][:8])
for st, d in res.items():
    print(f"[{st}] clips {d['n']} speakers {d['speakers']}")
    for thr in (50, 55, 60, 65, 70):
        print(f"  thr {thr}: R0 false-fail {1 - rate(d['same'], 0, thr):.3f} wrong-pass {rate(d['diff'], 0, thr):.3f} | "
              f"R1 false-fail {1 - rate(d['same'], 1, thr):.3f} wrong-pass {rate(d['diff'], 1, thr):.3f}")
# 탐색용 R1 합격선 격자(맞게 말함 불합격률 · 다르게 말함 합격률)
for st, d in res.items():
    line = f"[{st}] R0@65 ff {1 - rate(d['same'], 0, 65):.3f} wp {rate(d['diff'], 0, 65):.3f} | R1:"
    for thr in range(40, 82, 4):
        line += f" {thr}:{1 - rate(d['same'], 1, thr):.3f}/{rate(d['diff'], 1, thr):.3f}"
    print(line)
if noise_scores:
    for thr in (50, 65):
        print(f"noise vs stage5 thr {thr}: R0 pass {rate(noise_scores, 0, thr):.3f} R1 pass {rate(noise_scores, 1, thr):.3f}")
json.dump({k: {"n": v["n"], "same": v["same"], "diff": v["diff"]} for k, v in res.items()} | {"noise": noise},
          open(f"{out_dir}/scores_{key}_{half}.json", "w"), ensure_ascii=False)
