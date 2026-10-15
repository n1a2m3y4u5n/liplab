"""A1의 꼬리와 녹음 잡음(보고만, docs/phone-tail-2026-10.md 6.3절). 맥, numpy만.

    python a1_noise.py WAV_DIR A1_K_RUN JOBS OUT.json
클립마다 10 ms 프레임 RMS(dB)의 95백분위 − 10백분위(말소리 대 바닥)를 내고, 클립 꼬리 비율(K, 표시 ≤ 1)과의 순위상관, 조용·소음 화자별 값을 낸다.
"""
import json
import sys

import numpy as np
import soundfile as sf
from scipy.stats import spearmanr

sys.path.insert(0, __file__.rsplit("/", 2)[0])
import s2_phone_reliability as S2  # noqa: E402

wav, run, jobs_p, out = sys.argv[1:5]
jobs = {j["clip"]: j for j in (json.loads(l) for l in open(jobs_p, encoding="utf-8"))}
rows = []
for l in open(run, encoding="utf-8"):
    r = json.loads(l)
    j = jobs[r["clip"]]
    sil = set(j["silent_h"])
    v = [S2.disp(x) for i, (t, x) in enumerate(zip(j["tokens"], r["orig"])) if t != "|" and i not in sil and x is not None and i < j["fs"]]
    y, sr = sf.read(f"{wav}/{r['clip']}.wav", dtype="float64")
    n = sr // 100
    m = len(y) // n
    db = 20 * np.log10(np.sqrt((y[:m * n].reshape(m, n) ** 2).mean(1)) + 1e-12)
    rows.append((np.mean([x <= 1 for x in v]), float(np.percentile(db, 95) - np.percentile(db, 10)), r["spk"] in S2.QUIET_A1))
a = np.array(rows, dtype=float)
q = np.quantile(a[:, 1], [.25, .75])
res = {"clips": len(a), "rho_tail_vs_snr": round(float(spearmanr(a[:, 0], a[:, 1])[0]), 3),
       "snr_median_quiet": round(float(np.median(a[a[:, 2] == 1, 1])), 1), "snr_median_noisy": round(float(np.median(a[a[:, 2] == 0, 1])), 1),
       "tail_low_snr_q1": round(float(a[a[:, 1] < q[0], 0].mean()), 4), "tail_high_snr_q4": round(float(a[a[:, 1] >= q[1], 0].mean()), 4),
       "tail_quiet": round(float(a[a[:, 2] == 1, 0].mean()), 4), "tail_noisy": round(float(a[a[:, 2] == 0, 0].mean()), 4)}
json.dump(res, open(out, "w"), indent=1)
print(res)
