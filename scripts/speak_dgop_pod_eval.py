"""파드: 앱의 D-GOP(자체 정렬기·채점기 int8, CPU)로 608 청각장애 문장 컷과 538 표본을 채점한다.
목표 문장: 자기 문장(맞게 말함)과 음절 수가 비슷한 다른 문장 2개(다르게 말함). 결과 out/dgop.json.
"""
import json
import os
import random
import re
import sys
from concurrent.futures import ProcessPoolExecutor

W = "/workspace"
os.environ.update(DGOP_ALIGNER_ID=f"{W}/backend/models/dgop_ours/aligner", DGOP_SCORER_ID=f"{W}/backend/models/dgop_ours/scorer",
                  DGOP_CALIBRATION=f"{W}/backend/data/dgop_calibration_ours.json", BACKBONE_QUANT="int8",
                  HF_HUB_OFFLINE="1", CUDA_VISIBLE_DEVICES="")
sys.path.insert(0, f"{W}/backend")


def hangul(s):
    return re.sub(r"[^가-힣]", "", s or "")


def job(args):
    import torch
    torch.set_num_threads(2)
    import dgop_acoustic as D
    path, target, kind = args
    data = open(path, "rb").read()
    try:
        r = D.assess_text(data, target, aligner_id=os.environ["DGOP_ALIGNER_ID"], scorer_id=os.environ["DGOP_SCORER_ID"])
        return {"path": path, "target": target, "kind": kind, "score": r.get("score"), "raw": r.get("raw_score"),
                "uncertainty": r.get("uncertainty")}
    except Exception as e:
        return {"path": path, "target": target, "kind": kind, "error": f"{type(e).__name__}: {e}"}


if __name__ == "__main__":
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    rng = random.Random(0)
    cuts = [c for c in json.load(open(f"{W}/out/cuts608.json")) if c["cut"]]
    man = {}
    for l in open(f"{W}/c538/manifest.tsv", encoding="utf-8"):
        clip, spk, text = l.rstrip("\n").split("\t")
        man[clip.replace(".mp4", "")] = (spk, text)
    c538 = [(f"{W}/c538/{k}.flac", v[1]) for k, v in man.items() if os.path.exists(f"{W}/c538/{k}.flac")]
    rng.shuffle(c538)
    c538 = c538[:600]
    jobs = []
    for items in ([(c["cut"], c["target"]) for c in cuts], c538):
        pool = [t for _, t in items]
        for p, t in items:
            jobs.append((p, t, "same"))
            n = len(hangul(t))
            cand = [x for x in pool if x != t and 0.7 * n <= len(hangul(x)) <= 1.3 * n]
            for x in rng.sample(cand, min(2, len(cand))):
                jobs.append((p, x, "diff"))
    print("jobs", len(jobs), flush=True)
    out = []
    with ProcessPoolExecutor(workers) as ex:
        for i, r in enumerate(ex.map(job, jobs, chunksize=8)):
            out.append(r)
            if i % 200 == 0:
                print(i, flush=True)
    json.dump(out, open(f"{W}/out/dgop.json", "w"), ensure_ascii=False)
    print("DONE", flush=True)
