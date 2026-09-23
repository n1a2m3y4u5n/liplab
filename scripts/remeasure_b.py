"""B·A 재측정 — AI Hub 538 실발화로 전사 붕괴와 D-GOP 반응을 다시 잰다(파드 GPU용).

docs/dgop-demo.md·deaf-synthesis.md의 첫 판은 macOS TTS 7문장이었다. 여기서는 실제 사람 발화
(538, 10화자 300문장)로 같은 질문을 다시 본다.
  조건: clean / 농인 합성 mild·mod·sev(make_deaf_corpus.PRESETS, 활성 발화 대비 SNR) /
        blur(예전 B 실증과 같은 800Hz 저역통과 + 말속도 1.3배)
  지표: ASR(kresnik wav2vec2 CTC 그리디) 음절 CER, D-GOP 원점수(팀 표준 naive 채점식 dgop.sentence_dgop,
        정렬·채점 모두 kresnik — 비공개 A-2 정렬기 없이 재현 가능한 판)

사용(파드): python remeasure_b.py --clips clips --manifest manifest.tsv --backend backend --out b_remeasure.json
"""
import argparse
import json
import math
import os
import random
import sys
import time
from collections import defaultdict

import numpy as np
import soundfile as sf


def norm_syll(s):
    return "".join(ch for ch in (s or "") if "가" <= ch <= "힣")


def cer(ref, hyp):
    r, h = norm_syll(ref), norm_syll(hyp)
    if not r:
        return None
    prev = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        cur = [i] + [0] * len(h)
        for j in range(1, len(h) + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r[i - 1] != h[j - 1]))
        prev = cur
    return prev[-1] / len(r)


def spearman(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    ok = ~(np.isnan(a) | np.isnan(b))
    a, b = a[ok], b[ok]
    if len(a) < 3:
        return None
    ra, rb = a.argsort().argsort(), b.argsort().argsort()
    return float(np.corrcoef(ra, rb)[0, 1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--backend", required=True, help="liplab backend 디렉토리(dgop·dgop_acoustic)")
    ap.add_argument("--tools", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=0, help="0이면 전부")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    sys.path.insert(0, a.backend)
    sys.path.insert(0, a.tools)
    import torch
    import dgop as D
    import dgop_acoustic as DA
    import make_deaf_corpus as MD

    rows = [l.rstrip("\n").split("\t") for l in open(a.manifest, encoding="utf-8") if l.strip()]
    rows = [(r[0], r[1], r[2]) for r in rows if len(r) >= 3]
    if a.n:
        random.Random(a.seed).shuffle(rows)
        rows = rows[:a.n]
    processor, model = DA._load(DA.DEFAULT_MODEL_ID)
    dev = next(model.parameters()).device

    def asr(y):
        with torch.no_grad():
            iv = processor(y, sampling_rate=16000, return_tensors="pt").input_values.to(dev)
            ids = model(iv).logits.argmax(-1)
        return processor.batch_decode(ids)[0]

    def dgop_score(y, text):
        toks = DA.tokens_for_text(text)
        phones = DA.phone_confidences(y, 16000, toks)
        scored = [p for p in phones if p.get("aligned") and p.get("scorable")]
        if not scored:
            return None, None
        s = D.sentence_dgop(scored)
        return s["score"], s["uncertainty"]

    conds = ["clean", "mild", "mod", "sev", "blur"]
    per = []
    t0 = time.time()
    for k, (base, spk, text) in enumerate(rows):
        wav = os.path.join(a.clips, os.path.splitext(base)[0] + ".wav")
        if not os.path.exists(wav):
            continue
        y, sr = sf.read(wav, dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        if sr != 16000:
            import librosa
            y = librosa.resample(y, orig_sr=sr, target_sr=16000)
        rec = {"base": base, "spk": spk, "text": text}
        for c in conds:
            if c == "clean":
                yc = y
            elif c == "blur":
                yc = MD.muffle_lp(MD.time_stretch(y, 1.3), 16000, 800)
            else:
                p = dict(MD.PRESETS[c])
                yc = MD.perturb_safe(y, 16000, seed=k, **p)
            yc = np.asarray(yc, dtype=np.float32)
            hyp = asr(yc)
            sc, unc = dgop_score(yc, text)
            rec[c] = {"hyp": hyp, "cer": cer(text, hyp), "dgop": sc, "unc": unc}
        per.append(rec)
        if (k + 1) % 25 == 0:
            print(f"[{k + 1}/{len(rows)}] {time.time() - t0:.0f}s", flush=True)

    def agg(c, key):
        v = [r[c][key] for r in per if r[c][key] is not None]
        return {"mean": round(float(np.mean(v)), 4), "median": round(float(np.median(v)), 4),
                "sd": round(float(np.std(v)), 4), "n": len(v)} if v else None
    summary = {c: {"cer": agg(c, "cer"), "dgop": agg(c, "dgop"),
                   "exact_rate": round(float(np.mean([r[c]["cer"] == 0 for r in per if r[c]["cer"] is not None])), 4)}
               for c in conds}
    # 강도 단조성: clip마다 D-GOP가 clean ≥ mild ≥ mod ≥ sev 인 비율
    mono = [all(r[x]["dgop"] is not None for x in ("clean", "mild", "mod", "sev")) and
            r["clean"]["dgop"] >= r["mild"]["dgop"] >= r["mod"]["dgop"] >= r["sev"]["dgop"] for r in per]
    # D-GOP와 전사 정확도(1-CER)의 순위상관(조건 합쳐서 / 조건별)
    pooled_d, pooled_acc = [], []
    for r in per:
        for c in conds:
            if r[c]["dgop"] is not None and r[c]["cer"] is not None:
                pooled_d.append(r[c]["dgop"]); pooled_acc.append(1 - r[c]["cer"])
    by_spk = defaultdict(lambda: defaultdict(list))
    for r in per:
        for c in conds:
            if r[c]["dgop"] is not None:
                by_spk[r["spk"]][c].append(r[c]["dgop"])
    spk_means = {s: {c: round(float(np.mean(v)), 2) for c, v in d.items()} for s, d in by_spk.items()}
    out = {
        "n_clips": len(per), "speakers": len(by_spk), "model": DA.DEFAULT_MODEL_ID,
        "scoring": "dgop.sentence_dgop (naive, raw x100), aligner=scorer=kresnik",
        "presets": {c: MD.PRESETS[c] for c in ("mild", "mod", "sev")},
        "blur": "muffle_lp 800Hz + time_stretch rate 1.3",
        "summary": summary,
        "monotone_clean_to_sev_rate": round(float(np.mean(mono)), 4) if mono else None,
        "spearman_dgop_vs_asr_acc_pooled": spearman(pooled_d, pooled_acc),
        "speaker_mean_dgop": spk_means,
        "elapsed_s": round(time.time() - t0, 1),
    }
    json.dump({"summary": out, "per_clip": per}, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("B_REMEASURE_OK", json.dumps(out["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
