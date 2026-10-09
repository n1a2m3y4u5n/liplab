"""S2 음소 피드백 신뢰도 지도 측정(파드). docs/phoneme-feedback-reliability-2026-10.md 4절.

    python measure.py selftest ROOT                         재구현이 앱 assess_text와 같은지(클립 2개)
    python measure.py run ROOT OUT.jsonl [--shard i/n]      클립마다 순전파 한 번, 원래 목표 1개 + 대치 목표 31개 채점

ROOT: backend/(앱 코드, models/dgop_ours int8), data/jobs.jsonl, data/wav/<clip>.wav. 줄마다 클립 하나의 결과.
이미 적은 클립은 건너뛴다. 끝 표식 MEASURE_OK. 값은 칩과 같은 naive(0~1)이고, 분석은 맥에서 한다.
"""
import argparse
import json
import os
import sys
import time

import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("part")
ap.add_argument("root")
ap.add_argument("out", nargs="?")
ap.add_argument("--shard", default="0/1")
ap.add_argument("--limit", type=int, default=0)
ap.add_argument("--threads", type=int, default=1)
a = ap.parse_args()

ROOT = os.path.abspath(a.root)
BK = os.path.join(ROOT, "backend")
sys.path.insert(0, BK)
os.environ.setdefault("BACKBONE_QUANT", "int8")
os.environ.setdefault("OMP_NUM_THREADS", str(a.threads))
os.environ.setdefault("LIPLAB_CONTENT_WARMUP", "0")
import torch  # noqa: E402

torch.set_num_threads(a.threads)
torch.set_grad_enabled(False)
if os.environ.get("DGOP_DEVICE") == "cuda":
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
import soundfile as sf  # noqa: E402
import dgop as G  # noqa: E402
import dgop_acoustic as DA  # noqa: E402

SR = 16000
AL = os.path.join(BK, "models", "dgop_ours", "aligner")
SC = os.path.join(BK, "models", "dgop_ours", "scorer")
_memo = {}


def outputs(y, model_id):
    key = model_id
    if key not in _memo:
        lp, _lg, vocab = DA.ctc_outputs(np.asarray(y, dtype=np.float32), SR, model_id)
        _memo[key] = (lp, vocab)
    return _memo[key]


def naive_for(y, tokens):
    """dgop_acoustic.phone_confidences와 같은 계산(정렬기로 구간, 채점기 구간 평균 분포의 목표 확률). 토큰마다 naive 또는 None."""
    lp, vocab = outputs(y, AL)
    slp, svocab = outputs(y, SC)
    assert slp.shape[0] == lp.shape[0]
    spans = DA.align_targets(lp, vocab, tokens)
    out = []
    for sp in spans:
        tok = sp["token"]
        if not DA._is_scorable(tok):
            out.append(None)
            continue
        dist = DA.span_distribution(slp, sp["start"], sp["end"])
        if not dist or tok not in svocab:
            out.append(None)
            continue
        out.append(G.dgop_phone(dist[svocab[tok]], dist)["naive"])
    return out


# S2_TRIM=1이면 앱과 같이 정렬 전 끝 무음을 자른다(dgop_acoustic.trim_trailing_silence, docs/dgop-final-vowel-fix2-2026-10.md 6절).
# 10/7 S2는 자르지 않고 쟀다(그때 앱도 자르지 않았다). 시각만 바꾸는 끝 구간 다시 나누기는 점수를 바꾸지 않으므로 여기서는 필요 없다.
S2_TRIM = os.environ.get("S2_TRIM", "0") == "1"


def read(root, clip):
    y, sr = sf.read(f"{root}/data/wav/{clip}.wav", dtype="float32")
    assert sr == SR, (clip, sr)
    if y.ndim > 1:
        y = y.mean(1)
    if S2_TRIM:
        old = os.environ.get("DGOP_TAIL_TRIM")
        os.environ["DGOP_TAIL_TRIM"] = "1"
        y = DA.trim_trailing_silence(y, SR)
        if old is None:
            os.environ.pop("DGOP_TAIL_TRIM", None)
        else:
            os.environ["DGOP_TAIL_TRIM"] = old
    return y


def jobs(root):
    return [json.loads(l) for l in open(f"{root}/data/jobs.jsonl", encoding="utf-8")]


def selftest():
    js = jobs(ROOT)
    for j in (js[0], js[-1]):
        _memo.clear()
        y = read(ROOT, j["clip"])
        mine = naive_for(y, j["tokens"])
        data = open(f"{ROOT}/data/wav/{j['clip']}.wav", "rb").read()
        r = DA.assess_text(data, j["target"], aligner_id=AL, scorer_id=SC)
        app = [p.get("naive") if p.get("aligned") and p.get("scorable") else None for p in r["phones"]]
        assert [p["token"] for p in r["phones"]] == j["tokens"], "토큰열 다름"
        d = max(abs(x - y_) for x, y_ in zip(mine, app) if x is not None and y_ is not None)
        assert d <= 1e-4, d   # 앱은 faster-whisper로 디코드한다(16 kHz 단일 채널 wav라 같아야 한다)
        print("APPCHECK", j["clip"], "max_diff", d, flush=True)
    print("S2_SELFTEST_OK", flush=True)


def run():
    i, n = (int(x) for x in a.shard.split("/"))
    js = [j for k, j in enumerate(jobs(ROOT)) if k % n == i]
    if a.limit:
        js = js[:a.limit]
    done = set()
    if os.path.exists(a.out):
        for l in open(a.out, encoding="utf-8"):
            try:
                done.add(json.loads(l)["clip"])
            except Exception:
                pass
    f = open(a.out, "a", encoding="utf-8")
    t0 = time.time()
    k = 0
    for j in js:
        if j["clip"] in done:
            continue
        _memo.clear()
        rec = {"set": j["set"], "clip": j["clip"], "spk": j["spk"]}
        try:
            y = read(ROOT, j["clip"])
            rec["orig"] = naive_for(y, j["tokens"])
            subs = []
            for s in j["subs"]:
                toks = list(j["tokens"])
                assert toks[s["i"]] == s["x"]
                toks[s["i"]] = s["y"]
                v = naive_for(y, toks)
                # 바꾼 자리의 naive와, 칩 표시 값(정수) 전체(다른 자리에 칠한 빨강을 보기 위해)
                subs.append([s["kind"], s["i"], s["y"], v[s["i"]],
                             [None if x is None else int(np.floor(100.0 * x + 0.5)) for x in v]])
            rec["subs"] = subs
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {e}"
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()
        k += 1
        if k % 20 == 0:
            print(f"S2 {i}/{n} {k}/{len(js)} {time.time() - t0:.0f}s", flush=True)
    f.close()
    print("MEASURE_OK run", i, n, k, flush=True)


if __name__ == "__main__":
    {"selftest": selftest, "run": run}[a.part]()
