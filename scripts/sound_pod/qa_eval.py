"""품질 점검 D-GOP·음절 시각·신호(docs/sound-qa-2026-10.md 1.2~1.4절). score 가상환경, CPU(배포와 같은 int8 정렬기·채점기).

    python qa_eval.py TARGETS.jsonl OUT.jsonl --cands orig|c0,c1… --clips DIR --cand-root DIR --models DIR [--shard i/n] [--threads 2]

줄마다 {uid, cand, dgop, dgop_raw, syl, phones[{token,t0,t1}], metrics{…신호…}, sr}. 이미 적은 (uid, 후보)는 건너뛴다. 표식 EVAL_OK."""
import argparse
import io
import json
import os
import sys

ap = argparse.ArgumentParser()
ap.add_argument("targets"); ap.add_argument("out")
ap.add_argument("--cands", required=True); ap.add_argument("--clips", required=True); ap.add_argument("--cand-root", required=True)
ap.add_argument("--models", required=True)
ap.add_argument("--shard", default="0/1"); ap.add_argument("--uids", default="")
ap.add_argument("--threads", type=int, default=2)
a = ap.parse_args()
os.environ.setdefault("OMP_NUM_THREADS", str(a.threads))
os.environ.setdefault("BACKBONE_QUANT", "int8")
os.environ.setdefault("DGOP_DEVICE", "cpu")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qa_rules as Q  # noqa: E402

os.environ.setdefault("DGOP_CALIBRATION", os.path.join(Q.BACKEND, "data", "dgop_calibration_ours.json"))
import torch  # noqa: E402
torch.set_num_threads(a.threads)
torch.set_grad_enabled(False)
import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from faster_whisper.audio import decode_audio  # noqa: E402
import dgop_acoustic as DA  # noqa: E402
import jamo_vocab  # noqa: E402
import sound_clips as S  # noqa: E402

ALIGNER = os.path.join(a.models, "aligner")
SCORER = os.path.join(a.models, "scorer")
targets = Q.load_targets(a.targets)
if a.uids:
    keep = set(open(a.uids).read().split())
    targets = [t for t in targets if t["uid"] in keep]
tmap = {t["uid"]: t for t in targets}
si, sn = map(int, a.shard.split("/"))
items = list(Q.iter_items(targets, a.cands.split(","), a.clips, a.cand_root))[si::sn]
done = {(r["uid"], r["cand"]) for r in Q.read_jsonl([a.out])}
items = [it for it in items if (it[0], it[1]) not in done]

out = open(a.out, "a")
for uid, cand, p in items:
    t = tmap[uid]
    if p.endswith(".ogg"):
        sr = 48000
        x = decode_audio(p, sampling_rate=sr)
    else:
        x, sr = sf.read(p, dtype="float32")
        if x.ndim > 1:
            x = x.mean(axis=1)
    w16 = decode_audio(p, sampling_rate=16000)
    buf = io.BytesIO()
    sf.write(buf, w16, 16000, format="WAV", subtype="PCM_16")
    rec = {"uid": uid, "cand": cand, "sr": sr}
    toks = jamo_vocab.text_to_tokens(t["text"])
    phones = []
    try:
        r = DA.assess_text(buf.getvalue(), t["text"], aligner_id=ALIGNER, scorer_id=SCORER)
        rec["dgop"] = r.get("score")
        rec["dgop_raw"] = r.get("raw_score")
        phones = r.get("phones") or []
        dur_ms = len(x) / sr * 1000.0
        rec["syl"] = S.syllable_times(phones, toks, duration_ms=dur_ms)
        rec["phones"] = [{k: ph.get(k) for k in ("token", "t0", "t1")} for ph in phones]
    except Exception as ex:
        rec["dgop"] = None
        rec["err"] = f"{type(ex).__name__}: {ex}"[:300]
    try:
        rec["metrics"] = Q.signal_metrics(x, sr, phones if len(phones) == len(toks) else None, toks)
    except Exception as ex:
        rec["metrics"] = {}
        rec["metrics_err"] = f"{type(ex).__name__}: {ex}"[:300]
    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
    out.flush()
print(f"EVAL_OK {a.cands} shard={a.shard} n={len(items)}", flush=True)
