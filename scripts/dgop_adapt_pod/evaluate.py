"""파드: 608 도메인 적응 후보 채점(docs/dgop-608-adapt-2026-10.md 5절). 앱 backend의 assess_text·phone_confidences를 그대로 부르고
정렬기·채점기만 int8 폴더로 바꾼다(GPU, TF32 끔). 한 클립의 순전파는 한 번(같은 파형·모델의 ctc_outputs를 기억).

    python evaluate.py pairs NAME AL_DIR SC_DIR SETS OUT.jsonl [--workers N] [--device cuda|cpu] [--limit-per-set N]
    python evaluate.py e2    NAME AL_DIR SC_DIR SETS OUT.json  [--workers N]
SETS: 쉼표로 A,B,538. pairs는 자기 문장·다른 문장·대치 목표와 538 저하 3단계(자기 문장), e2는 사·자·차·하 앱 방향 대치.
"""
import argparse
import hashlib
import io
import json
import os
import random
import sys
import time
import zlib
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = os.environ.get("AD_ROOT", os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))
BK = os.path.join(ROOT, "backend")
SR = 16000
_S = {}


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def _init(al, sc, device, threads):
    os.environ.update(BACKBONE_QUANT="int8", DGOP_DEVICE=device, HF_HUB_OFFLINE="1", LIPLAB_CONTENT_WARMUP="0",
                      DGOP_CALIBRATION=os.path.join(BK, "data", "dgop_calibration_ours.json"), OMP_NUM_THREADS=str(threads))
    sys.path.insert(0, BK)
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import torch
    torch.set_num_threads(threads)
    torch.set_grad_enabled(False)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    import dgop_acoustic as DA
    orig = DA.ctc_outputs
    cache = {}

    def cached(waveform, sample_rate, model_id=DA.DEFAULT_MODEL_ID):
        k = (model_id, hashlib.sha1(np.ascontiguousarray(waveform, dtype=np.float32).tobytes()).hexdigest())
        if k not in cache:
            if len(cache) > 16:
                cache.clear()
            cache[k] = orig(waveform, sample_rate, model_id)
        return cache[k]
    DA.ctc_outputs = cached
    _S.update(DA=DA, al=al, sc=sc)


def _wav_bytes(y):
    import soundfile as sf
    b = io.BytesIO()
    sf.write(b, np.clip(y, -1, 1), SR, format="WAV", subtype="PCM_16")
    return b.getvalue()


def pair_job(job):
    DA, al, sc = _S["DA"], _S["al"], _S["sc"]
    data = open(os.path.join(ROOT, job["path"]), "rb").read()
    base = {k: job[k] for k in ("set", "spk", "half", "clip")}
    min_idx = sorted({t["tok_idx"] for t in job["targets"] if t["kind"] == "min"})
    out = []

    def run(blob, text):
        r = DA.assess_text(blob, text, aligner_id=al, scorer_id=sc)
        ph = r.get("phones") or []
        return r, ph

    for t in job["targets"]:
        try:
            r, ph = run(data, t["text"])
            row = base | {"kind": t["kind"], "text": t["text"], "score": r.get("score"), "raw": r.get("raw_score"),
                          "n_ph": sum(1 for p in ph if p.get("aligned") and p.get("scorable"))}
            idx = min_idx if t["kind"] == "own" else ([t["tok_idx"]] if t["kind"] == "min" else [])
            if idx:
                row["naive_at"] = {str(k): (ph[k].get("naive") if k < len(ph) and ph[k].get("aligned") else None) for k in idx}
            if t["kind"] == "min":
                row["tok_idx"], row["cat"] = t["tok_idx"], t.get("cat")
            out.append(row)
        except Exception as e:
            out.append(base | {"kind": t["kind"], "text": t["text"], "error": f"{type(e).__name__}: {e}"})
    if job.get("degrade"):
        import make_deaf_corpus as MD
        from faster_whisper.audio import decode_audio
        y = decode_audio(io.BytesIO(data), sampling_rate=SR)
        seed = zlib.crc32(job["clip"].encode())
        for c in MD.PRESET_ORDER:
            try:
                yc = MD.perturb_safe(y, SR, seed=seed, **MD.PRESETS[c])
                r, ph = run(_wav_bytes(yc), job["own"])
                out.append(base | {"kind": f"deg_{c}", "text": job["own"], "score": r.get("score"), "raw": r.get("raw_score")})
            except Exception as e:
                out.append(base | {"kind": f"deg_{c}", "text": job["own"], "error": f"{type(e).__name__}: {e}"})
    return out


def e2_job(job):
    """scripts/s4_eval_pod.cons_job과 같은 계산(자음 부분). 자리 고르기 씨앗은 crc32(세트:클립)."""
    import speak_app_direction_pod_eval as A
    from faster_whisper.audio import decode_audio
    DA, al, sc = _S["DA"], _S["al"], _S["sc"]
    text = job["own"]
    group = "538" if job["set"] == "538" else "608"
    try:
        data = open(os.path.join(ROOT, job["path"]), "rb").read()
        wave = decode_audio(io.BytesIO(data), sampling_rate=SR)[:SR * 30]
        base_toks = DA.tokens_for_text(text, model_id=al)
        base = DA.phone_confidences(wave, SR, base_toks, aligner_id=al, scorer_id=sc)
        rng = random.Random(zlib.crc32(f"{job['set']}:{job['clip']}".encode()))
        cons = []

        def dg(ph, k):
            p = ph[k] if k < len(ph) else {}
            return p.get("dgop") if p.get("aligned") else None

        for c in A.TRUE_CONS:
            sp = A.spots(text, c)
            for i in rng.sample(sp, min(A.MAX_SPOTS, len(sp))):
                probe = "ㄱ" if c != "ㄱ" else "ㄷ"
                k = A.locate(base_toks, DA.tokens_for_text(A.with_onset(text, i, probe), model_id=al), c, probe)
                if k is None:
                    continue
                cons.append({"kind": "true", "cons": c, "k": k, "i": i, "wi": A.word_initial(text, i), "dgop": dg(base, k)})
        for y, x in A.PAIRS:
            sp = A.spots(text, y)
            for i in rng.sample(sp, min(A.MAX_SPOTS, len(sp))):
                alt_toks = DA.tokens_for_text(A.with_onset(text, i, x), model_id=al)
                k = A.locate(base_toks, alt_toks, y, x)
                if k is None:
                    continue
                alt = DA.phone_confidences(wave, SR, alt_toks, aligner_id=al, scorer_id=sc)
                cons.append({"kind": "pair", "y": y, "x": x, "k": k, "i": i, "wi": A.word_initial(text, i),
                             "same": dg(base, k) if y != "ㅇ" else None, "alt": dg(alt, k)})
        return {"set": job["set"], "clip": job["clip"], "spk": job["spk"], "half": job["half"], "group": group, "cons": cons}
    except Exception as e:
        return {"set": job["set"], "clip": job["clip"], "spk": job["spk"], "half": job["half"], "group": group,
                "error": f"{type(e).__name__}: {e}"}


def load_jobs(sets, limit=0):
    jobs = []
    for s in sets:
        js = json.load(open(f"{ROOT}/meta/eval_{s}.json", encoding="utf-8"))
        if limit:
            step = max(1, len(js) // limit)
            js = js[::step][:limit]
        jobs += js
    return jobs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["pairs", "e2"])
    ap.add_argument("name")
    ap.add_argument("al")
    ap.add_argument("sc")
    ap.add_argument("sets")
    ap.add_argument("out")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--limit-per-set", type=int, default=0)
    ap.add_argument("--no-degrade", action="store_true")
    a = ap.parse_args()
    if a.device == "cpu":
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    if a.cmd == "e2":
        import speak_app_direction_pod_eval  # noqa: F401  가져오며 CUDA_VISIBLE_DEVICES를 비우므로 여기서 되돌린다
        if a.device != "cpu":
            os.environ.pop("CUDA_VISIBLE_DEVICES", None)
    jobs = load_jobs(a.sets.split(","), a.limit_per_set)
    if a.no_degrade:
        for j in jobs:
            j.pop("degrade", None)
    fn = pair_job if a.cmd == "pairs" else e2_job
    log(a.cmd, a.name, "jobs", len(jobs), "workers", a.workers, a.device)
    t0, n, err = time.time(), 0, 0
    res = []
    with ProcessPoolExecutor(a.workers, initializer=_init, initargs=(a.al, a.sc, a.device, a.threads)) as ex:
        for i, r in enumerate(ex.map(fn, jobs, chunksize=2)):
            rows = r if isinstance(r, list) else [r]
            for x in rows:
                x["model"] = a.name
                err += "error" in x
            res += rows
            n += len(rows)
            if i % 200 == 0:
                log(i, len(jobs), "rows", n, "errors", err, round(time.time() - t0), "s")
    if a.cmd == "pairs":
        with open(a.out + ".tmp", "w", encoding="utf-8") as f:
            for x in res:
                f.write(json.dumps(x, ensure_ascii=False) + "\n")
    else:
        json.dump(res, open(a.out + ".tmp", "w"), ensure_ascii=False)
    os.replace(a.out + ".tmp", a.out)
    log(f"EVAL_OK {a.cmd} {a.name} rows {n} errors {err} {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
