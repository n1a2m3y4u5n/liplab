"""전사 채점만 GPU로(faster-whisper, CUDA float16). evaluate.py의 전사 부분과 같은 설정(base는 beam 1·temperature 0, 앱 말하기 경로와 같음).
    python asr_gpu.py TEXTS.json OUT_DIR WAVDIR [WAVDIR ...]   → OUT_DIR/<WAVDIR 이름>.asr.jsonl {id, key, asr, cer, app_score}"""
import asyncio, hashlib, json, os, re, sys
sys.path.insert(0, "/workspace/tts/backend")
from faster_whisper import WhisperModel
from faster_whisper.audio import decode_audio
import scoring, speak_service

texts, outdir, dirs = sys.argv[1], sys.argv[2], sys.argv[3:]
items = json.load(open(texts))
models = {n: WhisperModel(n, device="cuda", compute_type="float16") for n in ("base", "large-v3-turbo")}


def norm(t):
    return re.sub(r"[^가-힣]", "", t or "")


def cer(ref, hyp):
    r, h = norm(ref), norm(hyp)
    if not r:
        return None
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = d[j]
            d[j] = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev = cur
    return d[len(h)] / len(r)


os.makedirs(outdir, exist_ok=True)
for d in dirs:
    vid = os.environ.get("VID", "")
    out = open(os.path.join(outdir, os.path.basename(d.rstrip("/")) + ".asr.jsonl"), "w")
    for e in items:
        i = hashlib.sha1(f"{vid}\n{e['key']}".encode("utf-8")).hexdigest()[:16]
        p = os.path.join(d, i + ".wav")
        if not os.path.exists(p):
            continue
        w = decode_audio(p, sampling_rate=16000)
        rec = {"id": i, "key": e["key"], "asr": {}, "cer": {}, "app_score": {}}
        for n, m in models.items():
            segs, _ = (m.transcribe(w, language="ko", beam_size=1, temperature=0.0) if n == "base"
                       else m.transcribe(w, language="ko", beam_size=5))
            t = speak_service.collapse_repeats("".join(s.text for s in segs).strip())
            rec["asr"][n] = t
            rec["cer"][n] = cer(e["text"], t)
            try:
                rec["app_score"][n] = asyncio.run(scoring.calculate_score(e["text"], t)).get("score")
            except Exception:
                rec["app_score"][n] = None
        out.write(json.dumps(rec, ensure_ascii=False) + "\n")
    out.close()
    print("ASR_OK", d, flush=True)
