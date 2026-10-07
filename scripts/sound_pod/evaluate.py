"""합성 소리를 앱의 채점 경로로 잰다(score 가상환경, CPU, 배포와 같은 int8 정렬기·채점기).
    python evaluate.py TEXTS.json WAVDIR OUT.jsonl [--asr base,large-v3-turbo] [--no-dgop] [--shard i/n]
줄마다 {id, key, dur, asr: {모델: 전사}, cer: {모델: CER}, app_score: {모델: 앱 채점 점수}, dgop, dgop_raw, syl(음절 [t0,t1] ms), n_syl, timing_ok, phones}.
- 전사 채점: 앱 말하기 경로와 같은 faster-whisper(base, CPU int8, beam 1)와 더 강한 large-v3-turbo(beam 5)
- D-GOP: dgop_acoustic.assess_text(정렬기·채점기 = 자체 학습 int8, 앵커 dgop_calibration_ours.json)
- 음절 시각: sound_clips.syllable_times(정렬기의 자모 구간)"""
import argparse, asyncio, hashlib, io, json, os, re, sys, time

ap = argparse.ArgumentParser()
ap.add_argument("texts"); ap.add_argument("wavdir"); ap.add_argument("out")
ap.add_argument("--asr", default="base,large-v3-turbo"); ap.add_argument("--no-dgop", action="store_true")
ap.add_argument("--shard", default="0/1"); ap.add_argument("--vid", default="")
ap.add_argument("--threads", type=int, default=4)
ap.add_argument("--check", action="store_true", help="두 번째 정렬기(채점기)로 음절 시각 일치 점검")
ap.add_argument("--align-only", action="store_true", help="정렬기만(음절 시각), D-GOP 점수 없음")
a = ap.parse_args()
os.environ.setdefault("OMP_NUM_THREADS", str(a.threads))
os.environ.setdefault("BACKBONE_QUANT", "int8")
os.environ.setdefault("DGOP_DEVICE", "cpu")
os.environ.setdefault("DGOP_CALIBRATION", "/workspace/tts/backend/data/dgop_calibration_ours.json")
sys.path.insert(0, "/workspace/tts/backend")
import torch
torch.set_num_threads(a.threads)
torch.set_grad_enabled(False)
import numpy as np
import soundfile as sf

ALIGNER = "/workspace/tts/models/dgop_ours/aligner"
SCORER = "/workspace/tts/models/dgop_ours/scorer"
items = json.load(open(a.texts))
si, sn = map(int, a.shard.split("/"))
items = items[si::sn]

done = set()
if os.path.exists(a.out):
    for line in open(a.out):
        try:
            done.add(json.loads(line)["id"])
        except Exception:
            pass


def cid(key):
    return hashlib.sha1(f"{a.vid}\n{key}".encode("utf-8")).hexdigest()[:16]


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


from faster_whisper import WhisperModel
asr_models = {}
for name in [x for x in a.asr.split(",") if x]:
    asr_models[name] = WhisperModel(name, device="cpu", compute_type="int8", cpu_threads=a.threads)
import speak_service
import scoring
import sound_clips as S
import jamo_vocab
if not a.no_dgop:
    import dgop_acoustic as DA

out = open(a.out, "a")
for e in items:
    i = cid(e["key"])
    if i in done:
        continue
    p = os.path.join(a.wavdir, i + ".wav")
    if not os.path.exists(p):
        continue
    wav, sr = sf.read(p, dtype="float32")
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    # 16k로(정렬기·전사 모두 16k). 앱과 같은 디코더(faster-whisper의 PyAV 리샘플러)
    from faster_whisper.audio import decode_audio
    w16 = decode_audio(p, sampling_rate=16000)
    buf = io.BytesIO(); sf.write(buf, w16, 16000, format="WAV", subtype="PCM_16"); audio_bytes = buf.getvalue()
    rec = {"id": i, "key": e["key"], "dur": round(len(wav) / sr, 3), "asr": {}, "cer": {}, "app_score": {}}
    for name, m in asr_models.items():
        t0 = time.time()
        if name == "base":
            segs, _ = m.transcribe(w16, language="ko", beam_size=1, temperature=0.0)
        else:
            segs, _ = m.transcribe(w16, language="ko", beam_size=5)
        txt = speak_service.collapse_repeats("".join(s.text for s in segs).strip())
        rec["asr"][name] = txt
        rec["cer"][name] = cer(e["text"], txt)
        try:
            sc = asyncio.run(scoring.calculate_score(e["text"], txt))
            rec["app_score"][name] = sc.get("score") if isinstance(sc, dict) else None
        except Exception as ex:
            rec["app_score"][name] = None
    if not a.no_dgop:
        try:
            if a.align_only:
                phones = DA.phone_confidences(w16, 16000, jamo_vocab.text_to_tokens(e["text"]), aligner_id=ALIGNER, scorer_id=ALIGNER)
            else:
                r = DA.assess_text(audio_bytes, e["text"], aligner_id=ALIGNER, scorer_id=SCORER)
                rec["dgop"] = r.get("score"); rec["dgop_raw"] = r.get("raw_score")
                phones = r.get("phones") or []
            toks = jamo_vocab.text_to_tokens(e["text"])
            syl = S.syllable_times(phones, toks, duration_ms=len(wav) / sr * 1000.0)
            rec["syl"] = syl
            rec["n_syl"] = e.get("n_syl")
            rec["timing_ok"] = bool(syl) and len(syl) == e.get("n_syl")
            rec["phones"] = [{k: ph.get(k) for k in ("token", "t0", "t1", "dgop")} for ph in phones]
            if a.check:
                # 동기 품질 점검: 채점기를 정렬기로도 써서(따로 미세조정한 다른 모델) 음절 시각이 얼마나 같은지
                ph2 = DA.phone_confidences(w16, 16000, toks, aligner_id=SCORER, scorer_id=SCORER)
                rec["syl_alt"] = S.syllable_times(ph2, toks, duration_ms=len(wav) / sr * 1000.0)
        except Exception as ex:
            rec["dgop_err"] = f"{type(ex).__name__}: {ex}"[:300]
    out.write(json.dumps(rec, ensure_ascii=False) + "\n"); out.flush()
print(f"EVAL_OK {a.wavdir} shard={a.shard}")
