"""속삭임 거부(조화성 규칙) 재등록의 클립별 값 뽑기(판정은 하지 않는다). docs/speak-cues-rereg-2026-10.md 3절.

S10의 녹음 루프 이식(scripts/speak_loop_port.py)에 trace 점마다 두 주기 지연 선명도 c2(지연 2T의 정규화 상호상관)와\n버퍼 켑스트럼 봉우리 돌출 cpp(dB)를 더한다.
클립마다 크기 변화 −12·−6·0·+6dB에서 trace [t, rms, hz, c1, c2, cpp]와 지금 규칙 판정을 남긴다.
출력은 앱 저장소 밖(liplab-lab/data/cues_rereg_2026-10-09/)에만 둔다.

  python whisper_extract.py --out OUT.jsonl.gz [--procs 5] [--limit N] [--sets o608,n608,v538,syn]
"""
import argparse, gzip, json, math, os, re, sys, zlib
from multiprocessing import Pool

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", "backend"))
import speak_loop_port as lp          # noqa: E402

SR = 16000
GAINS = (-12, -6, 0, 6)
SYN_N = 200
HOME = os.path.expanduser("~/Downloads")
RAW1007 = f"{HOME}/liplab-lab/data/pod_runs/20261007_e4s7108qvq9tua/s1024/out/s1024_raw.jsonl.gz"
HI608 = f"{HOME}/liplab-lab/data/hi608"
S20 = f"{HOME}/liplab-lab/data/s20_stage/root/data"
V538 = f"{HOME}/liplab-lab/data/v1_538"

# 합성 속삭임 사양(공명 대역폭 Hz). W1 = 10/7 S10 생성기 그대로, W2 = 좁은 대역(부하 시험, 보고만), W3 = 넓은 대역.
W_SPECS = {"w1": (90, 110, 160), "w2": (60, 70, 100), "w3": (200, 250, 300)}
FORMANTS = (750, 1200, 2600)


def read_audio(path, start=None, end=None):
    import soundfile as sf
    info = sf.info(path)
    sr = info.samplerate
    a = 0 if start is None else max(0, int(round(start * sr)))
    b = None if end is None else int(round(end * sr))
    y, sr = sf.read(path, start=a, stop=b, dtype="float64", always_2d=True)
    y = y.mean(axis=1)
    if sr != SR:
        from scipy.signal import resample_poly
        g = math.gcd(int(sr), SR)
        y = resample_poly(y, SR // g, int(sr) // g)
    return y


def _reson(x, f, bw):
    from scipy.signal import lfilter
    r = math.exp(-math.pi * bw / SR)
    return lfilter([1 - r], [1, -2 * r * math.cos(2 * math.pi * f / SR), r * r], x)


def _formants(x, bws=W_SPECS["w1"]):
    for f, bw in zip(FORMANTS, bws):
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
    """S10 생성기(speak_s10_s24_extract.synth)와 같은 사양에 속삭임 대역폭 세 가지와 기식 유성을 더했다."""
    from scipy.signal import butter, lfilter
    rng = np.random.default_rng([seed, i, zlib.crc32(kind.encode())])
    dur = rng.uniform(1.5, 3.0)
    lev = rng.uniform(-45, -12)
    n = int(dur * SR)
    if kind.startswith("whisper_"):
        s = _formants(rng.standard_normal(n), W_SPECS[kind.split("_")[1]]) * _ramp(n)
    elif kind == "breath":
        b, a = butter(4, [200 / (SR / 2), 2000 / (SR / 2)], btype="band")
        t = np.arange(n) / SR
        s = lfilter(b, a, rng.standard_normal(n)) * np.sin(np.pi * t / dur) ** 1.5
    else:   # voiced(기식 0.1), voiced_breathy(기식 0.5)
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
        asp = rng.standard_normal(n) * (0.5 if kind == "voiced_breathy" else 0.1)
        s = _formants(src + asp) * _ramp(n)
    s = s / (np.sqrt(np.mean(s[s != 0] ** 2)) + 1e-12) * 10 ** (lev / 20)
    y = np.concatenate([np.zeros(int(0.4 * SR)), s])
    return y + rng.standard_normal(len(y)) * 10 ** (-65 / 20)


def clarity2(buf, hz):
    """설계 R 선명도와 같은 계산을 지연 2T에서(버퍼 최댓값 0.5로 맞춤). 겹침이 64표본보다 짧으면 None."""
    if hz <= 0:
        return None
    pk = float(np.max(np.abs(buf)))
    if pk <= 0:
        return None
    b = buf * (0.5 / pk)
    T2 = int(round(2 * SR / hz))
    if T2 >= len(b) - 64:
        return None
    u, v = b[:-T2], b[T2:]
    den = math.sqrt(float(np.dot(u, u)) * float(np.dot(v, v)))
    return max(0.0, float(np.dot(u, v)) / den) if den > 0 else 0.0


_HANN = np.hanning(lp.BUF)
_NFFT = 1024
_Q = np.arange(_NFFT // 2) / SR
_FIT = (_Q >= 0.001) & (_Q <= 0.025)
_LO, _HI = int(np.floor(SR / 500.0)), int(np.ceil(SR / 70.0))


def buf_cpp(buf):
    """버퍼 하나(42.7ms)의 켑스트럼 봉우리 돌출(dB): Hann 창, 1,024점 파워 스펙트럼 dB의 켑스트럼을 10·log10(c²)로,
    70~500Hz(2~14.3ms) 봉우리에서 1~25ms 최소제곱 직선까지의 높이. 평활 없음."""
    x = (buf - buf.mean()) * _HANN
    if not np.any(x):
        return None
    spec = 10 * np.log10(np.abs(np.fft.rfft(x, _NFFT)) ** 2 + 1e-20)
    c = np.fft.irfft(spec, _NFFT)[: _NFFT // 2]
    cdb = 10 * np.log10(c * c + 1e-20)
    m, b0 = np.polyfit(_Q[_FIT], cdb[_FIT], 1)
    j = _LO + int(np.argmax(cdb[_LO:_HI + 1]))
    return float(cdb[j] - (m * _Q[j] + b0))


def block(y):
    res = {}
    for g in GAINS:
        x = np.clip(y * 10 ** (g / 20), -1, 1)
        L = lp.loop(x, SR)
        tr = []
        k = 0
        for p in L["trace"]:
            end = int(round(lp.BUF + k * lp.FRAME_HOP))
            buf = x[end - lp.BUF:end]
            c2 = clarity2(buf, p["hz"])
            cp = buf_cpp(buf)
            tr.append([p["t"], round(p["rms"], 7), p["hz"], p["clarity"], None if c2 is None else round(c2, 4),
                       None if cp is None else round(cp, 3)])
            k += lp.TRACE_EVERY
        res[str(g)] = {"cur": lp.current_rule(L), "trace": tr}
    return res


def job(it):
    try:
        if it["set"] == "syn":
            y = synth(it["kind"], it["seed"], it["i"])
        else:
            y = read_audio(it["path"], it.get("start"), it.get("end"))
        out = {k: v for k, v in it.items() if k != "path"}
        out["dur"] = round(len(y) / SR, 3)
        out["s10"] = block(y)
        return out
    except Exception as e:
        return {"id": it.get("id"), "set": it.get("set"), "error": f"{type(e).__name__}: {e}"}


def items(sets):
    its = []
    if "o608" in sets:   # 이미 본 608: 10/7 S10과 같은 컷(범주 28 정제본 322, 범주 27 짝 844)
        for line in gzip.open(RAW1007, "rt", encoding="utf-8"):
            r = json.loads(line)
            if r["set"] == "608c28":
                its.append({"set": "o608", "layer": "c28", "id": r["id"], "spk": "c28:" + r["spk"], "start": r["start"], "end": r["end"],
                            "path": f"{HI608}/wav16/{r['id'].rsplit('_', 1)[0]}.flac"})
            elif r["set"] == "608pair" and r["ratio"] >= 0.6 and 0.4 <= r["dur"] <= 6.0:
                its.append({"set": "o608", "layer": "c27", "id": r["id"], "spk": "c27:" + r["spk"], "start": r["start"], "end": r["end"],
                            "path": f"{HI608}/pair16/{r['file']}"})
    if "n608" in sets:   # 새 화자: KSC 컷(S20 묶음 N과 같은 파일)
        for c in json.load(open(f"{S20}/clips.json", encoding="utf-8")):
            if c["set"] == "N":
                its.append({"set": "n608", "id": c["clip"], "spk": c["spk"], "sex": c["sex"], "path": f"{S20}/{c['path']}"})
    if "v538" in sets:   # 538 V1(10/7 S10에 쓰지 않은 건청 화자)
        for line in open(f"{V538}/manifest.tsv", encoding="utf-8"):
            clip, spk = line.rstrip("\n").split("\t")[:2]
            wav = f"{V538}/clips/{clip.replace('.mp4', '.wav')}"
            if os.path.exists(wav):
                its.append({"set": "v538", "id": clip[:-4], "spk": spk, "half": zlib.crc32(spk.encode()) % 2, "path": wav})
    if "syn" in sets:
        for seed in (0, 1):
            for kind in ("whisper_w1", "whisper_w2", "whisper_w3", "breath", "voiced", "voiced_breathy"):
                for i in range(SYN_N):
                    its.append({"set": "syn", "id": f"syn_{kind}_{seed}_{i}", "kind": kind, "seed": seed, "i": i})
    return its


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--procs", type=int, default=5)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sets", default="o608,n608,v538,syn")
    a = ap.parse_args()
    its = items(set(a.sets.split(",")))
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
            if (k + 1) % 500 == 0:
                print("PROGRESS", k + 1, len(its), flush=True)
    print(f"EXTRACT_OK n={len(its)} err={n_err}", flush=True)


if __name__ == "__main__":
    main()
