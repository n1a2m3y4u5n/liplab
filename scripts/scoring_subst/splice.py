"""소리 쪽 바꿈 만들기: 실제 초성 구간 잇기(docs/scoring-subst-2026-10.md 3.3절 N1). 보조 학습(C-aug)과 보고에만 쓴다.

자기 문장 클립마다 앱 정렬(assess_text의 음소 시각)로 초성 구간을 찾고, 자격 있는 초성 자리 i(목표 t) 하나를 골라
  - splice_sub: 같은 클립 안에서 K[t]의 경쟁 초성 c가 초성으로 나온 다른 자리 j의 소리로 i 구간을 바꾼다(목표 글은 원래 문장 그대로, y=1)
  - splice_same: 같은 클립 안에서 같은 초성 t가 나온 다른 자리 j'의 소리로 i 구간을 바꾼다(잇기 흔적은 같고 소리는 맞음, y=0 대조)
두 행을 같은 자리 i에 함께 만들 수 있을 때만 만든다(잇기 흔적만으로 가르는 지름길을 막는다). 클립마다 최대 1쌍, random.Random(20261019).

구간: 초성 토큰 구간 [s, e](정렬기 프레임)의 앞은 앞 토큰 끝과의 가운데, 뒤는 뒤 토큰(중성) 시작과의 가운데까지(파열·기식 구간을 포함).
이음매는 5 ms 올린 코사인으로 섞는다. 소리 길이는 바뀐다.

  python splice.py make JOBS OUTDIR      JOBS의 own 목표 → OUTDIR/audio/*.wav + OUTDIR/jobs_splice.json
  python splice.py selftest              합성 신호로 잇기 함수 점검
"""
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import common as C  # noqa: E402

SEED = 20261019
SR = 16000
XF = int(0.005 * SR)


def region(spans, i, sec_per_frame):
    s, e = spans[i]["start"], spans[i]["end"]
    prev_end = spans[i - 1]["end"] if i > 0 and spans[i - 1].get("end") is not None else max(0, s - 2)
    nxt = spans[i + 1]["start"] if i + 1 < len(spans) and spans[i + 1].get("start") is not None else e + 2
    a = (prev_end + 1 + s) / 2.0
    b = (e + 1 + nxt) / 2.0
    return int(round(a * sec_per_frame * SR)), int(round(b * sec_per_frame * SR))


def splice(x, dst, src):
    """x의 dst=(a, b) 구간을 x의 src=(c, d) 소리로 바꾼다. 이음매 양쪽 5 ms 교차."""
    import numpy as np
    a, b = dst
    c, d = src
    piece = x[c:d].astype("float32").copy()
    if len(piece) < 2 * XF + 1 or b - a < 2 * XF + 1:
        return None
    ramp = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, XF, dtype="float32"))
    left = x[:a].astype("float32").copy()
    right = x[b:].astype("float32").copy()
    piece[:XF] = piece[:XF] * ramp + x[a:a + XF] * (1 - ramp)
    piece[-XF:] = piece[-XF:] * (1 - ramp) + x[b - XF:b] * ramp
    return np.concatenate([left, piece, right])


def cmd_make(jobs_path, outdir):
    import numpy as np
    import soundfile as sf
    sys.path.insert(0, HERE)
    import feat as F
    D = F._setup()
    FP = F._S["FP"]
    al, sc = os.environ["DGOP_ALIGNER_ID"], os.environ["DGOP_SCORER_ID"]
    root = os.path.dirname(os.path.abspath(jobs_path))
    jobs = json.load(open(jobs_path, encoding="utf-8"))
    os.makedirs(os.path.join(outdir, "audio"), exist_ok=True)
    rng = random.Random(SEED)
    out, n_try = [], 0
    for job in jobs:
        own = next((t for t in job["targets"] if t["kind"] == "own"), None)
        if own is None:
            continue
        n_try += 1
        path = job["path"] if os.path.isabs(job["path"]) else os.path.join(root, job["path"])
        FP._S["memo"].clear()
        r = D.assess_text(open(path, "rb").read(), own["text"], aligner_id=al, scorer_id=sc)
        spans = FP._S["last"]["spans"]
        phones = r.get("phones") or []
        toks = [s["token"] for s in spans]
        x, sr = sf.read(path, dtype="float32")
        if x.ndim > 1:
            x = x.mean(1)
        if sr != SR:
            continue
        spf = 320 / SR   # wav2vec2 conv 보폭 320표본 = 20 ms/프레임(정렬기·채점기 같음)
        elig = C.eligible_positions(toks, phones)
        onset_at = {}
        for j, t in enumerate(toks):
            if t.startswith("o:") and phones[j].get("aligned") and spans[j].get("start") is not None:
                onset_at.setdefault(t[2:], []).append(j)
        opts = []
        for i in elig:
            t = toks[i][2:]
            subs = [(c, j) for c in C.K[t] for j in onset_at.get(c, []) if j != i]
            sames = [j for j in onset_at.get(t, []) if j != i]
            if subs and sames:
                opts.append((i, subs, sames))
        if not opts:
            continue
        i, subs, sames = rng.choice(opts)
        c, j = rng.choice(subs)
        j2 = rng.choice(sames)
        dst = region(spans, i, spf)
        made = {}
        for kind, src_j in (("splice_sub", j), ("splice_same", j2)):
            y = splice(x, dst, region(spans, src_j, spf))
            if y is None:
                break
            name = f"{job['clip'].replace(':', '_')}_{kind}.wav"
            sf.write(os.path.join(outdir, "audio", name), y, SR)
            made[kind] = name
        if len(made) != 2:
            continue
        for kind, name in made.items():
            out.append({"set": job["set"], "spk": job["spk"], "clip": f"{job['clip']}#{kind}", "path": f"audio/{name}",
                        "targets": [{"text": own["text"], "kind": kind, "tok_idx": i,
                                     "cat": C.CAT.get((toks[i][2:], c), "") if kind == "splice_sub" else "same"}]})
    json.dump(out, open(os.path.join(outdir, "jobs_splice.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print(f"SPLICE_DONE clips={n_try} pairs={len(out) // 2}", flush=True)


def selftest():
    import numpy as np
    x = np.zeros(SR, dtype="float32")
    x[8000:8800] = 1.0
    y = splice(x, (1000, 1800), (8000, 8800))
    assert y is not None and len(y) == len(x) and abs(float(y[1400]) - 1.0) < 1e-6 and float(y[999]) == 0.0
    spans = [{"start": 0, "end": 1}, {"start": 10, "end": 11}, {"start": 20, "end": 21}]
    a, b = region(spans, 1, 0.02)
    assert a < 10 * 0.02 * SR and b > 12 * 0.02 * SR
    print("SPLICE_SELFTEST_OK")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "make":
        cmd_make(a[1], a[2])
    elif a and a[0] == "selftest":
        selftest()
    else:
        print(__doc__)
        sys.exit(2)
