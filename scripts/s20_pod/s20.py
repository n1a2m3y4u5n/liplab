"""S20 파드 계산(docs/speak-intelligibility-index-2026-10.md 3·4·6절). run.sh가 단계마다 부른다.

  python s20.py selftest | asr_v3 | asr_base W | dgop W | acoustic W

입력 $S20_ROOT/data/clips.json과 조각 소리, 출력 $S20_ROOT/out/*.jsonl(조각 단위 원자료, 맥 lab으로만 받는다).
- asr_v3: faster-whisper large-v3(GPU float16, ko, 빔 5, 온도 0, vad 없음, 앞 문장 조건 끔). T1.
- asr_base: 앱 전사 설정(base, CPU int8, 빔 1, 온도 0, vad 없음). T2(보고만).
- dgop: 앱 경로 dgop_acoustic.assess_text(자체 정렬기·채점기 int8, CPU)로 자기 대본 문장. 음소 정렬·D-GOP·말 빠르기(rate_pause).
- acoustic: 잡음 바닥(25ms 창 RMS dB 10백분위 − 최댓값), 신호 대 바닥 폭(95 − 10백분위), ㅏ·ㅣ·ㅜ 포먼트(Praat Burg, parselmouth, 측정용).
"""
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

R = os.environ.get("S20_ROOT", "/workspace/s20")
D = f"{R}/data"
OUT = f"{R}/out"
BK = f"{R}/backend"
SR = 16000
VOWELS = ("n:ㅏ", "n:ㅣ", "n:ㅜ")


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def clips():
    return json.load(open(f"{D}/clips.json"))


def dump(name, rows):
    tmp = f"{OUT}/{name}.tmp"
    with open(tmp, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, f"{OUT}/{name}")


# ───────────────────────── 전사 ─────────────────────────
def run_asr_v3(cl):
    from faster_whisper import WhisperModel
    m = WhisperModel("large-v3", device="cuda", compute_type="float16")
    log("large-v3 loaded")
    rows = []
    for i, c in enumerate(cl):
        segs, _ = m.transcribe(f"{D}/{c['path']}", language="ko", beam_size=5, temperature=0.0, vad_filter=False,
                               condition_on_previous_text=False)
        rows.append({"clip": c["clip"], "text": "".join(s.text for s in segs).strip()})
        if i % 100 == 0:
            log("ASR_V3", i, rows[-1]["text"][:20])
    return rows


_BASE = [None]


def _base_job(c):
    from faster_whisper import WhisperModel
    if _BASE[0] is None:
        _BASE[0] = WhisperModel("base", device="cpu", compute_type="int8", cpu_threads=2)
    segs, _ = _BASE[0].transcribe(f"{D}/{c['path']}", language="ko", beam_size=1, temperature=0.0, vad_filter=False)
    return {"clip": c["clip"], "text": "".join(s.text for s in segs).strip()}


# ───────────────────────── D-GOP(앱 경로) ─────────────────────────
_DA = [None]


def _setup_dgop():
    if _DA[0] is None:
        os.environ.update(DGOP_ALIGNER_ID=f"{BK}/models/dgop_ours/aligner", DGOP_SCORER_ID=f"{BK}/models/dgop_ours/scorer",
                          DGOP_CALIBRATION=f"{BK}/data/dgop_calibration_ours.json", BACKBONE_QUANT="int8",
                          HF_HUB_OFFLINE="1", CUDA_VISIBLE_DEVICES="")
        if BK not in sys.path:
            sys.path.insert(0, BK)
        import torch
        torch.set_num_threads(2)
        import dgop_acoustic
        _DA[0] = dgop_acoustic
    return _DA[0]


def _dgop_job(c):
    DA = _setup_dgop()
    al, sc = os.environ["DGOP_ALIGNER_ID"], os.environ["DGOP_SCORER_ID"]
    data = open(f"{D}/{c['path']}", "rb").read()
    t0 = time.time()
    try:
        r = DA.assess_text(data, c["target"], aligner_id=al, scorer_id=sc)
        ph = [{k: p.get(k) for k in ("token", "aligned", "scorable", "silent_h", "t0", "t1", "dgop")} for p in (r.get("phones") or [])]
        return {"clip": c["clip"], "score": r.get("score"), "raw": r.get("raw_score"), "rate": r.get("rate"), "phones": ph,
                "sec": round(time.time() - t0, 2)}
    except Exception as e:
        return {"clip": c["clip"], "error": f"{type(e).__name__}: {e}"}


# ───────────────────────── 잡음 바닥·포먼트 ─────────────────────────
def noise_floor(y):
    import numpy as np
    hop, win = int(0.010 * SR), int(0.025 * SR)
    if len(y) < win:
        return None, None
    n = 1 + (len(y) - win) // hop
    idx = np.arange(win)[None, :] + hop * np.arange(n)[:, None]
    fr = y[idx].astype(np.float64)
    e = 10.0 * np.log10(np.maximum((fr ** 2).mean(axis=1), 1e-12))
    p10, p95, mx = np.percentile(e, 10), np.percentile(e, 95), e.max()
    return round(float(p10 - mx), 2), round(float(p95 - p10), 2)


def _acoustic_job(args):
    c, phones = args
    import numpy as np
    import parselmouth
    import soundfile as sf
    y, sr = sf.read(f"{D}/{c['path']}", dtype="float64")
    if y.ndim > 1:
        y = y.mean(axis=1)
    nf, snrp = noise_floor(y)
    out = {"clip": c["clip"], "nf": nf, "snrp": snrp, "vowels": []}
    if not phones:
        return out
    snd = parselmouth.Sound(y, sampling_frequency=sr)
    ceiling = 5000.0 if c["sex"] == "M" else 5500.0
    fm = snd.to_formant_burg(time_step=0.005, max_number_of_formants=5, maximum_formant=ceiling, window_length=0.025,
                             pre_emphasis_from=50.0)
    al = [p for p in phones if p.get("aligned") and p.get("t0") is not None and p.get("token") != "|"]
    for i, p in enumerate(al):
        if p["token"] not in VOWELS:
            continue
        a = float(p["t0"])
        nxt = next((float(q["t0"]) for q in al[i + 1:] if float(q["t0"]) > a), None)
        b = a + 0.10 if nxt is None else min(a + 0.10, nxt)
        if b - a < 0.03:
            continue
        f1s, f2s = [], []
        for t in np.arange(a, b + 1e-9, 0.005):
            f1, f2 = fm.get_value_at_time(1, t), fm.get_value_at_time(2, t)
            if np.isfinite(f1) and np.isfinite(f2):
                f1s.append(f1)
                f2s.append(f2)
        if not f1s:
            continue
        F1, F2 = float(np.median(f1s)), float(np.median(f2s))
        if not (150 <= F1 <= 1200 and 500 <= F2 <= 3500):
            continue
        out["vowels"].append([p["token"][2:], round(F1, 1), round(F2, 1), round(b - a, 3)])
    return out


def selftest():
    import numpy as np
    t = np.arange(SR) / SR
    y = 0.001 * np.random.default_rng(0).standard_normal(SR)
    y[4000:12000] += 0.3 * np.sin(2 * np.pi * 150 * t[4000:12000])
    nf, snrp = noise_floor(y)
    assert nf < -30 and snrp > 30, (nf, snrp)
    import parselmouth  # noqa: F401
    log("S20_SELFTEST_OK", nf, snrp)


def main():
    os.makedirs(OUT, exist_ok=True)
    cmd = sys.argv[1]
    cl = clips()
    if cmd == "selftest":
        selftest()
    elif cmd == "asr_v3":
        dump("asr_v3.jsonl", run_asr_v3(cl))
        log("ASR_V3_OK", len(cl))
    elif cmd == "asr_base":
        with ProcessPoolExecutor(int(sys.argv[2])) as ex:
            rows = list(ex.map(_base_job, cl, chunksize=4))
        dump("asr_base.jsonl", rows)
        log("ASR_BASE_OK", len(rows))
    elif cmd == "dgop":
        rows = []
        with ProcessPoolExecutor(int(sys.argv[2])) as ex:
            for i, r in enumerate(ex.map(_dgop_job, cl, chunksize=2)):
                rows.append(r)
                if i % 50 == 0:
                    log("DGOP", i, r.get("score"), r.get("sec"), r.get("error"))
        dump("dgop.jsonl", rows)
        log("DGOP_OK", len(rows), "errors", sum("error" in r for r in rows))
    elif cmd == "acoustic":
        dg = {}
        for line in open(f"{OUT}/dgop.jsonl"):
            r = json.loads(line)
            dg[r["clip"]] = r.get("phones")
        with ProcessPoolExecutor(int(sys.argv[2])) as ex:
            rows = list(ex.map(_acoustic_job, [(c, dg.get(c["clip"])) for c in cl], chunksize=4))
        dump("acoustic.jsonl", rows)
        log("ACOUSTIC_OK", len(rows), "vowel_tokens", sum(len(r["vowels"]) for r in rows))
    else:
        raise SystemExit(f"unknown {cmd}")


if __name__ == "__main__":
    main()
