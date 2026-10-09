"""옛 538·608 자료의 저장된 로짓으로 끝 자르기 없는(n) 설정을 다시 계산한다(맥, 모델 추론 없음).
docs/dgop-final-vowel-fix2-2026-10.md 4절. 10/6 538 600클립 소리는 10/8 정리 뒤 남아 있지 않아, 10/7 측정(dgop_tail_pod, 파드
20261007_gf8ifdceixcoar)이 저장한 정렬기·채점기 로그확률(끝 자르기 없는 R·T, int8, GPU TF32 끔)만 쓴다.

    python offline.py FV_OUT OUT.jsonl [--half 0|1|all]

변형: K0_n(지금 정렬·채점, 자르기 없음), N1a_n·N1l_n(같은 채점 + 끝 구간 다시 나누기, 문 all·late). 채점은 세 변형이 같다.
줄 형식은 measure.py main과 같다(phones = [토큰, t0, t1, naive, silent_h]). 빠르기는 rate_pause의 rate(음절 수 / 구간)만 낸다
(쉼 계산에는 소리가 필요하다).
"""
import argparse
import glob
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(APP, "backend"))
import torch  # noqa: E402

import dgop as G  # noqa: E402
import dgop_acoustic as DA  # noqa: E402
import jamo_vocab as JV  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("fv")
ap.add_argument("out")
ap.add_argument("--half", default="all")
ap.add_argument("--vocab", default=os.path.expanduser("~/Downloads/liplab-lab/models/dgop_ours_2026-09-25_int8/aligner/vocab.json"))
a = ap.parse_args()

VOCAB = json.load(open(a.vocab, encoding="utf-8"))
CAL = DA.load_calibration(os.path.join(APP, "backend", "data", "dgop_calibration_ours.json"))
GATES = {"N1a": "all", "N1l": "late"}


def rate_of(ph):
    """speak_cues.rate_pause의 rate와 같은 정의(정렬된 첫 토큰 시작 ~ 마지막 토큰 끝, 어절 경계 제외, 음절 = 중성 수)."""
    al = [p for p in ph if p[0] != "|"]
    n = sum(1 for p in al if p[0].startswith("n:"))
    if not al or n < 3:
        return None
    span = al[-1][2] - al[0][1]
    return None if span < 0.5 else {"n_syll": n, "span": round(span, 3), "rate": round(n / span, 3)}


def score(lp, slp, toks, target, timing_variants, end_frame, spf):
    ids = [VOCAB[t] for t in toks]
    spans = DA.align_targets(torch.from_numpy(lp), VOCAB, toks)
    probs = torch.softmax(torch.from_numpy(slp), -1)
    naive = []
    for sp in spans:
        dist = probs[sp["start"]:sp["end"] + 1].mean(0).tolist()
        naive.append(G.dgop_phone(dist[VOCAB[sp["token"]]], dist)["naive"])
    silent = set(JV.silent_linking_h(target))
    scored = [{"naive": naive[i], "confidence": 1.0, "dgop": naive[i], "uncertainty": 0.0}
              for i, t in enumerate(toks) if DA._is_scorable(t)]
    raw = G.sentence_dgop(scored)["score"]
    out = {}
    for name, gate in timing_variants.items():
        ts = spans if gate is None else DA.retime_tail(lp, VOCAB, toks, spans, end_frame, gate=gate)
        ph = [[t, round(s["start"] * spf, 3), round((s["end"] + 1) * spf, 3), round(naive[i], 4), 1 if i in silent else 0]
              for i, (t, s) in enumerate(zip(toks, ts))]
        out[name] = (ph, any(s.get("retimed") for s in ts))
    assert len(ids) == len(naive)
    return raw, G.calibrate_score(raw, CAL), out


rows = []
for f in sorted(glob.glob(os.path.join(a.fv, "main.*.jsonl"))):
    for l in open(f, encoding="utf-8"):
        r = json.loads(l)
        if r["variant"] in ("R", "T") and r["set"] in ("538", "608") and (a.half == "all" or str(r["half"]) == a.half):
            rows.append(r)
out = open(a.out, "w", encoding="utf-8")
n = 0
for r in rows:
    key = f"{r['set']}_{r['clip'].replace(':', '__')}_{r['variant']}"
    z = np.load(os.path.join(a.fv, "lp", key + ".npz"))
    lp, slp = z["al"].astype(np.float32), z["sc"].astype(np.float32)
    T = lp.shape[0]
    spf = r["dur_in"] / T
    se = r.get("speech_end")
    end_frame = None if se is None else int(round((se + DA.TAIL_TRIM_MARGIN_S) / spf))
    res = {v: {"set": r["set"], "clip": r["clip"], "spk": r["spk"], "half": r["half"], "variant": f"{v}_n_{r['variant']}",
               "dur": r["dur"], "dur_in": r["dur_in"], "dur_raw": r["dur_raw"], "speech_end": se,
               "speech_end_raw": r["speech_end_raw"], "n_frames": T, "src": "offline", "targets": []}
           for v in ("K0", "N1a", "N1l")}
    for k, t in enumerate(r["targets"]):
        if t["kind"] not in ("same", "diff"):
            continue
        toks = JV.text_to_tokens(t["target"])
        tv = {"K0": None, **GATES} if t["kind"] == "same" else {"K0": None}
        raw, sc, ph = score(lp, slp, toks, t["target"], tv, end_frame, spf)
        for v in res:
            p, moved = ph.get(v, ph["K0"])
            res[v]["targets"].append({"kind": t["kind"], "target": t["target"], "raw": raw, "score": sc,
                                      "rate": rate_of(p), "phones": p, "retimed": moved})
    for v in res.values():
        out.write(json.dumps(v, ensure_ascii=False) + "\n")
    n += 1
print("OFFLINE_OK", n, "clip·조건")
