"""Praat식 CPPS 구현 맞추기(개발용, 판정과 무관). 10/7 S24 파드 실행이 남긴 Praat CPPS 값(parselmouth 0.4.7)과
이 구현의 값을 같은 컷에서 비교한다. 쓰는 자료는 이미 본 608 범주 28 정제본 컷과 범주 27 짝 컷뿐이고 CER은 읽지 않는다.

  python cpps_devfit.py RAW.jsonl.gz HI608_DIR OUT.json [--procs 4] [--limit N]
"""
import argparse, gzip, json, math, os, sys
from multiprocessing import Pool

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "backend"))
import voice_quality as vq  # noqa: E402

VARIANTS = {
    "base": {},
    "clip": {"clip_flat": True},
    "clip_q6": {"clip_flat": True, "q_avg": 0.0006},
    "clip_speech": {"clip_flat": True, "speech_only": True},
}
HI = None


def read(path, start, end):
    import soundfile as sf
    info = sf.info(path)
    y, sr = sf.read(path, start=int(round(start * info.samplerate)), stop=int(round(end * info.samplerate)), dtype="float64", always_2d=True)
    y = y.mean(axis=1)
    if sr != 16000:
        y = vq._resample_fft(y, sr, 16000)
    return y


def _init(h):
    global HI
    HI = h


def job(r):
    sub = "wav16" if r["set"] == "608c28" else "pair16"
    fn = r["id"].rsplit("_", 1)[0] + ".flac" if r["set"] == "608c28" else r["file"]
    y = read(os.path.join(HI, sub, fn), r["start"], r["end"])
    out = {"id": r["id"], "set": r["set"], "praat": r["praat"]["cpps_db"], "old": r["vq"].get("cpps_db"), "dur": len(y) / 16000}
    for k, kw in VARIANTS.items():
        out[k] = vq.cpps_praat(y, **kw)
    return out


def spearman(a, b):
    from scipy.stats import spearmanr
    return float(spearmanr(a, b).correlation)


def main():
    global HI
    ap = argparse.ArgumentParser()
    ap.add_argument("raw"); ap.add_argument("hi"); ap.add_argument("out")
    ap.add_argument("--procs", type=int, default=4); ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    HI = a.hi
    rows = [json.loads(l) for l in gzip.open(a.raw, "rt")]
    rows = [r for r in rows if r["set"] in ("608c28", "608pair") and (r.get("praat") or {}).get("cpps_db") is not None]
    if a.limit:
        rows = rows[: a.limit]
    with Pool(a.procs, initializer=_init, initargs=(a.hi,)) as p:
        res = p.map(job, rows, chunksize=8)
    summ = {}
    for k in list(VARIANTS) + ["old"]:
        xs = [(r[k], r["praat"]) for r in res if r[k] is not None]
        d = np.array([x - y for x, y in xs])
        summ[k] = {"n": len(xs), "spearman": round(spearman([x for x, _ in xs], [y for _, y in xs]), 4),
                   "pearson": round(float(np.corrcoef([x for x, _ in xs], [y for _, y in xs])[0, 1]), 4),
                   "median_diff": round(float(np.median(d)), 3), "mad_diff": round(float(np.median(np.abs(d - np.median(d)))), 3)}
    json.dump({"summary": summ, "rows": res}, open(a.out, "w"))
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
