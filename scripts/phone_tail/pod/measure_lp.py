"""A1 538 클립의 정렬기·채점기 로그확률 덤프(파드 GPU int8, TF32 끔). docs/phone-tail-2026-10.md 1절.

    python measure_lp.py ROOT OUT_DIR [--shard i/n]

ROOT: backend/(앱 코드, models/dgop_ours int8), data/jobs.jsonl(A1), data/wav/<clip>.wav. 설정 n(자르기 없음)과 t(앱과 같은 끝 자르기)마다
OUT_DIR/lp_<설정>/538_<clip>.npz(키 al·sc, float16)를 쓴다. 끝 표식 LP_OK.
"""
import argparse
import json
import os
import sys

import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("root")
ap.add_argument("out")
ap.add_argument("--shard", default="0/1")
a = ap.parse_args()
ROOT = os.path.abspath(a.root)
BK = os.path.join(ROOT, "backend")
sys.path.insert(0, BK)
os.environ.setdefault("BACKBONE_QUANT", "int8")
os.environ.setdefault("LIPLAB_CONTENT_WARMUP", "0")
import torch  # noqa: E402

torch.set_num_threads(1)
torch.set_grad_enabled(False)
torch.backends.cuda.matmul.allow_tf32 = False
torch.backends.cudnn.allow_tf32 = False
import soundfile as sf  # noqa: E402
import dgop_acoustic as DA  # noqa: E402

SR = 16000
AL = os.path.join(BK, "models", "dgop_ours", "aligner")
SC = os.path.join(BK, "models", "dgop_ours", "scorer")
i, n = (int(x) for x in a.shard.split("/"))
jobs = [json.loads(l) for l in open(f"{ROOT}/data/jobs.jsonl", encoding="utf-8")]
jobs = [j for k, j in enumerate(jobs) if k % n == i]
for s in ("n", "t"):
    os.makedirs(f"{a.out}/lp_{s}", exist_ok=True)
k = 0
for j in jobs:
    y, sr = sf.read(f"{ROOT}/data/wav/{j['clip']}.wav", dtype="float32")
    assert sr == SR
    if y.ndim > 1:
        y = y.mean(1)
    os.environ["DGOP_TAIL_TRIM"] = "1"
    yt = DA.trim_trailing_silence(y, SR)
    for s, w in (("n", y), ("t", yt)):
        p = f"{a.out}/lp_{s}/538_{j['clip']}.npz"
        if os.path.exists(p):
            continue
        al = DA.ctc_outputs(np.asarray(w, dtype=np.float32), SR, AL)[1].numpy()
        sc = DA.ctc_outputs(np.asarray(w, dtype=np.float32), SR, SC)[1].numpy()
        assert al.shape == sc.shape
        np.savez_compressed(p, al=al.astype(np.float16), sc=sc.astype(np.float16))
    k += 1
    if k % 50 == 0:
        print("LP", i, n, k, len(jobs), flush=True)
print("LP_OK", i, n, k, flush=True)
