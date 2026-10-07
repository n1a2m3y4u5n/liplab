"""모델 하나로 글 목록을 합성한다. 각 가상환경에서 돈다.
    python synth.py MODEL TEXTS.json OUTDIR [--voice V] [--device cuda|cpu] [--limit N] [--threads T]
OUTDIR/<id>.wav(원래 표본율 그대로)와 OUTDIR/synth.jsonl({id, key, sec(합성 시간), dur(소리 길이), ok}).
이미 있는 wav는 건너뛴다(끊겼다 다시 돌려도 이어서). id = sha1(key)[:16]."""
import argparse, hashlib, json, os, sys, time, traceback

ap = argparse.ArgumentParser()
ap.add_argument("model"); ap.add_argument("texts"); ap.add_argument("out")
ap.add_argument("--voice", default=""); ap.add_argument("--device", default="cuda")
ap.add_argument("--limit", type=int, default=0); ap.add_argument("--threads", type=int, default=0)
ap.add_argument("--steps", type=int, default=0)
ap.add_argument("--vid", default="", help="목록의 목소리 id(파일 이름에 들어간다)")
ap.add_argument("--speed", type=float, default=0)
a = ap.parse_args()
# 파드는 코어가 96개로 보이지만 할당은 약 7.6개다(cpu.max). 스레드 수를 정하지 않으면 과다 구독으로 수십 배 느려진다
a.threads = a.threads or 6
if a.threads:
    for k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[k] = str(a.threads)
import numpy as np
import soundfile as sf

items = json.load(open(a.texts))
if a.limit:
    items = items[:a.limit]
os.makedirs(a.out, exist_ok=True)


def cid(key):
    return hashlib.sha1(f"{a.vid}\n{key}".encode("utf-8")).hexdigest()[:16]


if a.model == "supertonic":
    import supertonic
    from supertonic import TTS
    kw = {}
    tts = TTS(auto_download=True, intra_op_num_threads=a.threads, inter_op_num_threads=1)
    if a.threads:
        try:
            import onnxruntime as ort
            print("ort providers", ort.get_available_providers(), file=sys.stderr)
        except Exception:
            pass
    style = tts.get_voice_style(voice_name=a.voice or "F1")
    sr = getattr(tts, "sample_rate", None) or 44100

    def gen(text):
        kw = {"voice_style": style, "lang": "ko"}
        if a.steps:
            kw["total_steps"] = a.steps
        if a.speed:
            kw["speed"] = a.speed
        wav, dur = tts.synthesize(text, **kw)
        return np.asarray(wav, dtype=np.float32).reshape(-1), sr
elif a.model == "melo":
    import torch
    if a.threads:
        torch.set_num_threads(a.threads)
    from melo.api import TTS
    m = TTS(language="KR", device=a.device)
    spk = m.hps.data.spk2id["KR"]
    sr = m.hps.data.sampling_rate

    def gen(text):
        wav = m.tts_to_file(text, spk, None, speed=1.0, quiet=True)
        return np.asarray(wav, dtype=np.float32).reshape(-1), sr
elif a.model == "chatterbox":
    import torch
    if a.threads:
        torch.set_num_threads(a.threads)
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    m = ChatterboxMultilingualTTS.from_pretrained(device=a.device)
    sr = m.sr

    def gen(text):
        torch.manual_seed(0)
        wav = m.generate(text, language_id="ko")
        return wav.squeeze().detach().cpu().numpy().astype(np.float32), sr
else:
    sys.exit("unknown model")

def trim(wav, sr, margin_ms=100, rel_db=-45.0):
    """앞뒤 무음 자르기(10ms 창 RMS가 최대보다 45dB 낮은 구간). 앞뒤 100ms는 남긴다. 엔진마다 같은 규칙."""
    if wav.size == 0:
        return wav
    w = max(1, int(sr * 0.01))
    n = len(wav) // w
    if n < 3:
        return wav
    rms = np.sqrt(np.mean(wav[:n * w].reshape(n, w) ** 2, axis=1) + 1e-12)
    thr = rms.max() * (10 ** (rel_db / 20))
    on = np.where(rms > thr)[0]
    if not on.size:
        return wav
    m = int(sr * margin_ms / 1000)
    a0 = max(0, on[0] * w - m)
    a1 = min(len(wav), (on[-1] + 1) * w + m)
    return wav[a0:a1]


log = open(os.path.join(a.out, "synth.jsonl"), "a")
fail_path = os.path.join(a.out, "failed.txt")
failed = set(open(fail_path).read().split()) if os.path.exists(fail_path) else set()
# 첫 호출(예열)은 시간에서 뺀다
try:
    gen("안녕하세요.")
except Exception:
    traceback.print_exc()
n_ok = 0
for e in items:
    i = cid(e["key"])
    p = os.path.join(a.out, i + ".wav")
    if os.path.exists(p):
        n_ok += 1
        continue
    if i in failed:
        continue
    t0 = time.time()
    try:
        wav, sr_ = gen(e["tts_text"])
        sec = time.time() - t0
        raw_dur = len(wav) / sr_
        wav = trim(wav, sr_)
        peak = float(np.max(np.abs(wav))) if wav.size else 0.0
        if peak > 1.0:
            wav = wav / peak
        sf.write(p + ".tmp.wav", wav, sr_, subtype="PCM_16")
        os.replace(p + ".tmp.wav", p)
        rec = {"id": i, "key": e["key"], "sec": round(sec, 4), "dur": round(len(wav) / sr_, 4), "raw_dur": round(raw_dur, 4), "sr": sr_, "ok": True}
        n_ok += 1
    except Exception as ex:
        rec = {"id": i, "key": e["key"], "ok": False, "err": f"{type(ex).__name__}: {ex}"[:300]}
        with open(fail_path, "a") as ff:
            ff.write(i + "\n")
        if "CUDA error" in str(ex):
            # CUDA 장치 단언이 한 번 나면 그 프로세스의 GPU 문맥이 망가진다 → 기록하고 끝낸다(감싸는 루프가 다시 띄운다)
            log.write(json.dumps(rec, ensure_ascii=False) + "\n"); log.flush()
            print("SYNTH_CUDA_ABORT", i)
            sys.exit(3)
    log.write(json.dumps(rec, ensure_ascii=False) + "\n"); log.flush()
import resource
print(f"SYNTH_OK model={a.model} voice={a.voice} n={n_ok}/{len(items)} maxrss_mb={resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024:.0f}")
