"""품질 점검 후보 합성(docs/sound-qa-2026-10.md 3절). Supertonic 가상환경에서 돈다.

    python qa_synth.py TARGETS.jsonl OUT_DIR --cands c0,c1 [--uids UIDS.txt] [--shard i/n] [--threads 2] [--gpu]

후보마다 OUT_DIR/<후보>/<uid>.wav(정리한 소리, 문서 5절, PCM 16비트, 엔진 표본율)와 OUT_DIR/<후보>/synth.<shard>.jsonl
({uid, cand, ok, sec, raw_dur, dur, sr, raw_level_db, raw_peak_db, raw_clip_n, gain_db, peak_limited_db, tts_text}).
이미 있는 wav는 건너뛴다(끊겼다 다시 돌려도 이어서). 표식: SYNTH_OK …
"""
import argparse
import inspect
import json
import os
import sys
import time
import traceback

ap = argparse.ArgumentParser()
ap.add_argument("targets"); ap.add_argument("out")
ap.add_argument("--cands", required=True)
ap.add_argument("--uids", default="")
ap.add_argument("--shard", default="0/1")
ap.add_argument("--threads", type=int, default=2)
ap.add_argument("--gpu", action="store_true")
a = ap.parse_args()
for k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[k] = str(a.threads)
import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qa_rules as Q  # noqa: E402

# 문서 3절 후보 표: (total_steps, speed, 마침표 붙이기, 시드)
CANDS = {
    "c0": (8, 1.05, False, 0), "c1": (16, 1.05, False, 1), "c2": (8, 1.05, False, 2), "c3": (32, 1.05, False, 3),
    "c4": (16, 1.00, False, 4), "c5": (16, 1.05, True, 5), "c6": (32, 0.95, False, 6), "c7": (16, 1.10, False, 7),
}

targets = [json.loads(l) for l in open(a.targets, encoding="utf-8") if l.strip()]
if a.uids:
    keep = set(open(a.uids).read().split())
    targets = [t for t in targets if t["uid"] in keep]
si, sn = map(int, a.shard.split("/"))
targets = targets[si::sn]
cands = [c for c in a.cands.split(",") if c]

from supertonic import TTS  # noqa: E402
init_kw = {"auto_download": True}
sig = inspect.signature(TTS.__init__).parameters
if "intra_op_num_threads" in sig:
    init_kw.update(intra_op_num_threads=a.threads, inter_op_num_threads=1)
if a.gpu:
    for name in ("providers", "execution_providers"):
        if name in sig:
            init_kw[name] = ["CUDAExecutionProvider", "CPUExecutionProvider"]
            break
    else:
        if "device" in sig:
            init_kw["device"] = "cuda"
        elif "use_gpu" in sig:
            init_kw["use_gpu"] = True
tts = TTS(**init_kw)
syn_sig = inspect.signature(tts.synthesize).parameters
print("TTS init", {k: v for k, v in init_kw.items()}, "synthesize params", list(syn_sig), file=sys.stderr, flush=True)
sr = getattr(tts, "sample_rate", None) or 44100
styles = {}


def style(ev):
    if ev not in styles:
        styles[ev] = tts.get_voice_style(voice_name=ev)
    return styles[ev]


def tts_text(t, period):
    s = t["tts_text"].strip()
    if period and s and s[-1] not in ".?!":
        s = s + "."
    return s


def gen(t, cand):
    steps, speed, period, seed = CANDS[cand]
    np.random.seed(seed)
    try:
        import random
        random.seed(seed)
    except Exception:
        pass
    kw = {"voice_style": style(t["engine_voice"]), "lang": "ko", "total_steps": steps, "speed": speed}
    if "seed" in syn_sig:
        kw["seed"] = seed
    text = tts_text(t, period)
    wav, _dur = tts.synthesize(text, **kw)
    return np.asarray(wav, dtype=np.float32).reshape(-1), text


try:
    gen({"tts_text": "안녕하세요.", "engine_voice": targets[0]["engine_voice"] if targets else "M1"}, "c0")   # 예열
except Exception:
    traceback.print_exc()

n_ok = n_skip = n_fail = 0
for cand in cands:
    od = os.path.join(a.out, cand)
    os.makedirs(od, exist_ok=True)
    log = open(os.path.join(od, f"synth.{si}.jsonl"), "a")
    for t in targets:
        p = os.path.join(od, t["uid"] + ".wav")
        if os.path.exists(p):
            n_skip += 1
            continue
        t0 = time.time()
        try:
            wav, text = gen(t, cand)
            sec = time.time() - t0
            y, info = Q.postprocess(wav, sr)
            if info.get("empty"):
                raise ValueError("empty synthesis")
            sf.write(p + ".tmp.wav", y, sr, subtype="PCM_16")
            os.replace(p + ".tmp.wav", p)
            rec = {"uid": t["uid"], "cand": cand, "ok": True, "sec": round(sec, 3), "raw_dur": round(len(wav) / sr, 3),
                   "dur": round(len(y) / sr, 3), "sr": sr, "tts_text": text, **info}
            n_ok += 1
        except Exception as ex:
            rec = {"uid": t["uid"], "cand": cand, "ok": False, "err": f"{type(ex).__name__}: {ex}"[:300]}
            n_fail += 1
        log.write(json.dumps(rec, ensure_ascii=False) + "\n"); log.flush()
import resource  # noqa: E402
print(f"SYNTH_OK shard={a.shard} cands={a.cands} ok={n_ok} skip={n_skip} fail={n_fail} "
      f"maxrss_mb={resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024:.0f}", flush=True)
