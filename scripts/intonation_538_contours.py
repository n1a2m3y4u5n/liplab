"""538 음성에서 문장 끝 억양 척도 비교. 프론트 lib/pitch.js autoCorrelate와 녹음 루프(약 42.7ms 버퍼, 66.7ms 간격)를 재현한다."""
import json, math, os, re, sys, wave
import numpy as np

ROOT = os.path.expanduser("~/Downloads/liplab_gpu_snapshot/expand538_more")
WH = re.compile(r"(뭐|뭘|무엇|무슨|어디|언제|누구|누가|누굴|왜|어떻게|어떤|어느|몇|얼마)")


CLARITY = float(os.environ.get("CLARITY", "0"))


def acf_pitch(buf, sr):
    SIZE = len(buf)
    rms = math.sqrt(float(np.mean(buf * buf)))
    if rms < 0.006:
        return -1
    thres = 0.2
    r1, r2 = 0, SIZE - 1
    small = np.where(np.abs(buf[: SIZE // 2]) < thres)[0]
    if len(small): r1 = int(small[0])
    for i in range(1, SIZE // 2):
        if abs(buf[SIZE - i]) < thres:
            r2 = SIZE - i; break
    b = buf[r1:r2]
    n = len(b)
    if n < 8: return -1
    maxLag = min(n - 1, math.ceil(sr / 70) + 2)
    full = np.correlate(b, b, mode="full")[n - 1:]
    c = full[: maxLag + 1]
    d = 0
    while d < maxLag and c[d] > c[d + 1]: d += 1
    seg = c[d:]
    maxpos = d + int(np.argmax(seg))
    T0 = float(maxpos)
    if T0 <= 0: return -1
    if CLARITY and c[maxpos] / (c[0] or 1) < CLARITY: return -1
    x1 = c[maxpos - 1] if maxpos - 1 >= 0 else 0
    x2 = c[maxpos]
    x3 = c[maxpos + 1] if maxpos + 1 <= maxLag else 0
    a = (x1 + x3 - 2 * x2) / 2
    bb = (x3 - x1) / 2
    if a: T0 = T0 - bb / (2 * a)
    return sr / T0


def contour(path):
    w = wave.open(path)
    sr = w.getframerate()
    x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64) / 32768.0
    pk = np.max(np.abs(x)) or 1.0
    x = x * (0.5 / pk)            # 브라우저 자동 이득을 흉내
    size = int(round(0.04267 * sr)); hop = int(round(0.06667 * sr))
    ps = []
    for s in range(0, len(x) - size, hop):
        p = acf_pitch(x[s:s + size], sr)
        if 70 < p < 500:
            ps.append(round(p))
    return ps


def main():
    rows = [l.rstrip("\n").split("\t") for l in open(os.path.join(ROOT, "manifest.tsv"), encoding="utf-8")]
    out = []
    for clip, spk, text in rows:
        t = text.strip()
        last = re.split(r"(?<=[.?!])\s+", t)[-1]
        if t.endswith("?"):
            grp = "whq" if WH.search(last) else "ynq"
        elif t.endswith("."):
            grp = "stmt"
        else:
            continue
        wav = os.path.join(ROOT, "clips", clip.replace(".mp4", ".wav"))
        if not os.path.exists(wav):
            continue
        out.append({"clip": clip, "spk": spk, "grp": grp, "text": t, "ps": contour(wav)})
    json.dump(out, open(sys.argv[1], "w"), ensure_ascii=False)
    from collections import Counter
    print(Counter(r["grp"] for r in out))


main()
