"""S10·S24 측정의 클립별 값 뽑기(파드에서 돈다, 판정은 하지 않는다).

사전 등록: docs/speak-loudness-intonation-2026-10.md(S10), docs/speak-voice-quality-2026-10.md(S24).
클립별 출력은 앱 저장소 밖(liplab-lab/data/pod_runs/…)에만 둔다.

  python3 speak_s10_s24_extract.py --root DIR --out OUT.jsonl.gz [--procs N] [--limit N]

DIR 구조(맥에서 묶음):
  c538/manifest.tsv, c538/manifest_meta.tsv, c538/clips/<clip>.wav
  s608/<file>.flac, meta/cuts608.json, meta/cuts608_pair.json, meta/asr.json
  pair/<file>.flac
"""
import argparse, gzip, json, math, os, re, sys, zlib
from multiprocessing import Pool

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "backend"))
import speak_loop_port as lp          # noqa: E402
import voice_quality as vq            # noqa: E402

SR = 16000
GAINS = (-12, -6, 0, 6)
SYN_N = 200


def read_audio(path, start=None, end=None):
    import soundfile as sf
    info = sf.info(path)
    sr = info.samplerate
    a = 0 if start is None else max(0, int(round(start * sr)))
    b = -1 if end is None else int(round(end * sr))
    y, sr = sf.read(path, start=a, stop=None if b < 0 else b, dtype="float64", always_2d=True)
    y = y.mean(axis=1)
    if sr != SR:
        from scipy.signal import resample_poly
        g = math.gcd(sr, SR)
        y = resample_poly(y, SR // g, sr // g)
    return y


# ── 합성 신호(사전 등록 2.4절) ──
def _reson(x, f, bw):
    from scipy.signal import lfilter
    r = math.exp(-math.pi * bw / SR)
    return lfilter([1 - r], [1, -2 * r * math.cos(2 * math.pi * f / SR), r * r], x)


def _formants(x):
    for f, bw in ((750, 90), (1200, 110), (2600, 160)):
        x = _reson(x, f, bw)
    return x


def _ramp(n, ms=50):
    e = np.ones(n)
    k = min(n // 2, int(SR * ms / 1000))
    if k > 0:
        e[:k] = np.linspace(0, 1, k)
        e[-k:] = np.linspace(1, 0, k)
    return e


def synth(kind, seed, i):
    from scipy.signal import butter, lfilter
    rng = np.random.default_rng([seed, i, zlib.crc32(kind.encode())])
    dur = rng.uniform(1.5, 3.0)
    lev = rng.uniform(-45, -12)
    n = int(dur * SR)
    if kind == "whisper":
        s = _formants(rng.standard_normal(n)) * _ramp(n)
    elif kind == "breath":
        b, a = butter(4, [200 / (SR / 2), 2000 / (SR / 2)], btype="band")
        t = np.arange(n) / SR
        s = lfilter(b, a, rng.standard_normal(n)) * np.sin(np.pi * t / dur) ** 1.5
    else:   # voiced
        f0 = rng.uniform(90, 260)
        src = np.zeros(n)
        tt = 0.0
        while tt < dur:
            j = int(tt * SR)
            if j < n:
                src[j] = 1.0
            tt += (1 / f0) * (1 + 0.01 * rng.standard_normal())
        src = lfilter([1.0], [1, -1.8, 0.81], src)
        src = src / (np.std(src) + 1e-12)
        asp = rng.standard_normal(n) * 0.1
        s = _formants(src + asp) * _ramp(n)
    s = s / (np.sqrt(np.mean(s[s != 0] ** 2)) + 1e-12) * 10 ** (lev / 20)
    pre = np.zeros(int(0.4 * SR))
    y = np.concatenate([pre, s])
    y = y + rng.standard_normal(len(y)) * 10 ** (-65 / 20)
    return y


# ── 억양 곡선(sentence-intonation.md 538 절과 같은 이식: 클립 최댓값 0.5, 42.7ms 버퍼, 66.7ms 간격) ──
def contour(y):
    pk = np.max(np.abs(y)) or 1.0
    x = y * (0.5 / pk)
    size = int(round(0.04267 * SR)); hop = int(round(0.06667 * SR))
    ps = []
    for s in range(0, len(x) - size, hop):
        p = lp.autocorrelate(x[s:s + size], SR)
        if 70 < p < 500:
            ps.append(round(p))
    return ps


def praat_feats(y):
    try:
        import parselmouth
        from parselmouth.praat import call
    except Exception:
        return None
    out = {}
    try:
        snd = parselmouth.Sound(np.asarray(y, dtype=np.float64), sampling_frequency=SR)
        pitch = snd.to_pitch_ac(time_step=0.01, pitch_floor=75.0, pitch_ceiling=500.0)
        f = pitch.selected_array["frequency"]
        f = f[f > 0]
        if len(f) >= 20:
            out["f0_med_hz"] = float(np.median(f))
            st = 12 * np.log2(f / np.median(f))
            out["f0_sd_st"] = float(np.std(st))
        pp = call(snd, "To PointProcess (periodic, cc)", 75.0, 500.0)
        out["jitter_local"] = 100 * float(call(pp, "Get jitter (local)", 0, 0, 0.0001, 0.02, 1.3))
        out["shimmer_local"] = 100 * float(call([snd, pp], "Get shimmer (local)", 0, 0, 0.0001, 0.02, 1.3, 1.6))
        harm = call(snd, "To Harmonicity (cc)", 0.01, 75.0, 0.1, 1.0)
        out["hnr_db"] = float(call(harm, "Get mean", 0, 0))
    except Exception as e:
        out["err"] = str(e)[:120]
    try:
        pcg = call(snd, "To PowerCepstrogram", 60.0, 0.002, 5000.0, 50.0)
        for args in (("yes", 0.02, 0.0005, 60.0, 330.0, 0.05, "Parabolic", 0.001, 0.05, "Exponential decay", "Robust"),
                     ("no", 0.02, 0.0005, 60.0, 330.0, 0.05, "parabolic", 0.001, 0.0, "exponential decay", "robust slow")):
            try:
                out["cpps_db"] = float(call(pcg, "Get CPPS", *args))
                break
            except Exception:
                continue
    except Exception as e:
        out["err_cpps"] = str(e)[:120]
    for k, v in list(out.items()):
        if isinstance(v, float) and not math.isfinite(v):
            out[k] = None
    return out


def s10_block(y):
    res = {}
    for g in GAINS:
        x = np.clip(y * 10 ** (g / 20), -1, 1)
        L = lp.loop(x, SR)
        res[str(g)] = {"cur": lp.current_rule(L),
                       "trace": [[p["t"], round(p["rms"], 7), p["hz"], p["clarity"]] for p in L["trace"]]}
    return res


def job(item):
    try:
        if item["set"] == "syn":
            y = synth(item["kind"], item["seed"], item["i"])
        elif item["set"] == "538":
            y = read_audio(item["path"])
        else:
            y = read_audio(item["path"], item["start"], item["end"])
        out = {k: v for k, v in item.items() if k not in ("path",)}
        out["dur"] = round(len(y) / SR, 3)
        out["s10"] = s10_block(y)
        if item["set"] in ("538", "608pair"):
            out["ps"] = contour(y)
        if item["set"] in ("538", "608c28", "608pair"):
            f = vq.features(y)
            out["vq"] = {k: (None if v is None else float(v)) for k, v in f.items()}
            out["praat"] = praat_feats(y)
        return out
    except Exception as e:
        return {"id": item.get("id"), "set": item.get("set"), "error": f"{type(e).__name__}: {e}"}


def items(root):
    its = []
    # 538
    meta = {}
    for line in open(os.path.join(root, "c538/manifest_meta.tsv"), encoding="utf-8"):
        if line.startswith("#"):
            continue
        p = line.rstrip("\n").split("\t")
        meta[p[0]] = p[3]
    asr = json.load(open(os.path.join(root, "meta/asr.json"), encoding="utf-8"))
    for line in open(os.path.join(root, "c538/manifest.tsv"), encoding="utf-8"):
        clip, spk, text = line.rstrip("\n").split("\t")[:3]
        cid = clip.replace(".mp4", "")
        a538 = asr["c538"].get(f"/workspace/c538/{cid}.flac")
        its.append({"set": "538", "id": cid, "spk": spk, "sex": meta.get(spk), "half": zlib.crc32(spk.encode()) % 2,
                    "text": text.strip(), "asr": a538["novad"] if a538 else None,
                    "path": os.path.join(root, "c538/clips", cid + ".wav")})
    # 608 범주 28(10/6 컷, 0.4~15초)
    for d in json.load(open(os.path.join(root, "meta/cuts608.json"), encoding="utf-8")):
        if not d.get("cut") or d["cut"] not in asr["s608"]:
            continue
        dur = d["end"] - d["start"]
        if not (0.4 <= dur <= 15.0):
            continue
        ini = d["file"].split("-")[4]
        m = re.search(r"-([FM])-(\d+)-", d["file"])
        its.append({"set": "608c28", "id": os.path.basename(d["cut"])[:-4], "spk": ini, "sex": m.group(1) if m else None,
                    "half": zlib.crc32(ini.encode()) % 2, "text": d["target"], "asr": asr["s608"][d["cut"]]["novad"],
                    "ratio": d["ratio"], "start": d["start"], "end": d["end"], "path": os.path.join(root, "s608", d["file"])})
    # 608 범주 27 짝 세션(평서·의문)
    for d in json.load(open(os.path.join(root, "meta/cuts608_pair.json"), encoding="utf-8")):
        if "end" not in d:
            continue
        p = d["file"][:-5].split("-")
        key = f"{p[4]}-{p[-3]}-{p[-2]}"
        t = d["target"].strip()
        form = "ques" if t.endswith(("?", "？")) else "decl" if t.endswith(".") else None
        its.append({"set": "608pair", "id": f"{d['file'][:-5]}_{d['si']:03d}", "file": d["file"], "si": d["si"], "spk": key,
                    "sex": p[-3], "half": zlib.crc32(key.encode()) % 2, "text": t, "form": form, "ratio": d["ratio"],
                    "start": d["start"], "end": d["end"], "path": os.path.join(root, "pair", d["file"])})
    for seed in (0, 1):
        for kind in ("whisper", "breath", "voiced"):
            for i in range(SYN_N):
                its.append({"set": "syn", "id": f"syn_{kind}_{seed}_{i}", "kind": kind, "seed": seed, "i": i})
    return its


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--procs", type=int, default=os.cpu_count() or 2)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    its = items(a.root)
    if a.limit:
        by = {}
        for it in its:
            by.setdefault(it["set"], []).append(it)
        its = [x for v in by.values() for x in v[: a.limit]]
    from collections import Counter
    print("ITEMS", dict(Counter(i["set"] for i in its)), flush=True)
    n_err = 0
    with gzip.open(a.out, "wt", encoding="utf-8") as fo, Pool(a.procs) as pool:
        for k, r in enumerate(pool.imap_unordered(job, its, chunksize=4)):
            if "error" in r:
                n_err += 1
                print("ERR", r["id"], r["error"], flush=True)
            fo.write(json.dumps(r, ensure_ascii=False) + "\n")
            if (k + 1) % 200 == 0:
                print("PROGRESS", k + 1, len(its), flush=True)
    print(f"EXTRACT_OK n={len(its)} err={n_err}", flush=True)


if __name__ == "__main__":
    main()
