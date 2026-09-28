"""파드: 앱과 같은 설정(faster-whisper base, CPU int8, 빔 1, 온도 0, 한국어)으로 전사한다. vad_filter 없음(앱)·있음 두 가지.
세트: c538(정상 화자 문장 클립), s608(감음신경성 세션을 large-v3 단어 타임스탬프로 문장 단위로 자른 것), noise(무음·잡음 합성).
"""
import difflib
import glob
import json
import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import soundfile as sf

W = "/workspace"
OUT = f"{W}/out"
os.makedirs(OUT, exist_ok=True)
os.makedirs(f"{W}/cuts", exist_ok=True)

_M = None


def base_model():
    global _M
    if _M is None:
        from faster_whisper import WhisperModel
        _M = WhisperModel("base", device="cpu", compute_type="int8", cpu_threads=2)
    return _M


def app_transcribe(path):
    m = base_model()
    out = {}
    for name, vad in (("novad", False), ("vad", True)):
        segs, _ = m.transcribe(path, language="ko", beam_size=1, temperature=0.0, vad_filter=vad)
        out[name] = "".join(s.text for s in segs).strip()
    return path, out


def run_pool(paths, workers):
    res = {}
    with ProcessPoolExecutor(workers) as ex:
        for p, o in ex.map(app_transcribe, paths, chunksize=4):
            res[p] = o
    return res


def hangul(s):
    return re.sub(r"[^가-힣]", "", s)


def cut_608():
    from faster_whisper import WhisperModel
    big = WhisperModel("large-v3", device="cuda", compute_type="float16")
    print("large-v3 loaded", flush=True)
    meta = json.load(open(f"{W}/s608/meta.json"))
    cuts = []
    for m in meta:
        path = f"{W}/s608/{m['file']}"
        audio, sr = sf.read(path)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        a16 = audio.astype(np.float32) if sr == 16000 else None
        if a16 is None:
            raise RuntimeError(f"16kHz 아님: {sr}")
        segs, _ = big.transcribe(a16, language="ko", beam_size=5, word_timestamps=True, vad_filter=True)
        words = [(w.word, w.start, w.end) for s in segs for w in (s.words or [])]
        json.dump(words, open(f"{OUT}/words_{m['file']}.json", "w"), ensure_ascii=False)
        sents = [x.strip() for x in re.split(r"(?<=[.?!])\s+", m["transcript"]) if hangul(x)]
        wh = [hangul(w[0]) for w in words]
        pos = 0
        for si, sent in enumerate(sents):
            target = hangul(sent)
            best = (0.0, None, None)
            for i in range(pos, min(len(words), pos + 60)):
                acc = ""
                for j in range(i, min(len(words), i + 40)):
                    acc += wh[j]
                    if len(acc) > len(target) * 1.6:
                        break
                    if len(acc) < len(target) * 0.5:
                        continue
                    r = difflib.SequenceMatcher(None, target, acc).ratio()
                    if r > best[0]:
                        best = (r, i, j)
            if best[1] is None or best[0] < 0.5:
                cuts.append({"file": m["file"], "si": si, "target": sent, "ratio": round(best[0], 3), "cut": None})
                continue
            r, i, j = best
            a, b = max(0.0, words[i][1] - 0.25), min(len(audio) / sr, words[j][2] + 0.35)
            cp = f"{W}/cuts/{m['file'][:-5]}_{si:03d}.wav"
            sf.write(cp, audio[int(a * sr):int(b * sr)], sr)
            cuts.append({"file": m["file"], "si": si, "target": sent, "ratio": round(r, 3), "cut": cp,
                         "big_text": "".join(w[0] for w in words[i:j + 1]).strip(), "start": a, "end": b})
            pos = j + 1
        print("608", m["file"], sum(1 for c in cuts if c["file"] == m["file"] and c["cut"]), "/", len(sents), flush=True)
    json.dump(cuts, open(f"{OUT}/cuts608.json", "w"), ensure_ascii=False)
    del big
    return cuts


def make_noise():
    rng = np.random.default_rng(0)
    sr = 16000
    os.makedirs(f"{W}/noise", exist_ok=True)
    items = []
    for dur in (1.0, 2.0, 3.0):
        items.append((f"silence_{dur}", np.zeros(int(sr * dur))))
    for rms in (0.001, 0.003, 0.01, 0.03):
        for dur in (1.5, 3.0):
            items.append((f"white_{rms}_{dur}", rng.normal(0, rms, int(sr * dur))))
            pink = np.cumsum(rng.normal(0, 1, int(sr * dur)))
            pink = pink - np.convolve(pink, np.ones(400) / 400, mode="same")
            pink = pink / (np.sqrt(np.mean(pink ** 2)) + 1e-9) * rms
            items.append((f"pink_{rms}_{dur}", pink))
    for k in range(6):   # 숨소리 비슷한 짧은 잡음 덩어리
        y = np.zeros(sr * 2)
        s = rng.integers(0, sr)
        burst = rng.normal(0, 0.02, int(sr * 0.4)) * np.hanning(int(sr * 0.4))
        y[s:s + len(burst)] = burst
        items.append((f"breath_{k}", y))
    paths = []
    for name, y in items:
        p = f"{W}/noise/{name}.wav"
        sf.write(p, np.clip(y, -1, 1).astype(np.float32), sr)
        paths.append(p)
    return paths


if __name__ == "__main__":
    mode = sys.argv[1]
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    if mode == "seg":          # GPU 가상환경(faster-whisper 0.10 + CUDA 11.8): large-v3로 608 세션을 문장 단위로 자른다
        cut_608()
        print("SEG DONE", flush=True)
        sys.exit(0)
    cuts = json.load(open(f"{OUT}/cuts608.json"))   # asr: 앱과 같은 버전(faster-whisper 1.x, CPU int8)
    noise = make_noise()
    c538 = sorted(glob.glob(f"{W}/c538/*.flac"))
    cut_paths = [c["cut"] for c in cuts if c["cut"]]
    print("transcribing", len(c538), len(cut_paths), len(noise), flush=True)
    res = run_pool(noise + cut_paths + c538, workers)
    json.dump({"noise": {p: res[p] for p in noise}, "s608": {p: res[p] for p in cut_paths},
               "c538": {p: res[p] for p in c538}}, open(f"{OUT}/asr.json", "w"), ensure_ascii=False)
    print("DONE", flush=True)
