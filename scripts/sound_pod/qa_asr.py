"""품질 점검 전사(docs/sound-qa-2026-10.md 1.1절): faster-whisper large-v3, GPU float16. score 가상환경.

    python qa_asr.py TARGETS.jsonl OUT.jsonl --cands orig|c0,c1… --clips DIR --cand-root DIR [--shard i/n] [--uids F]

줄마다 {uid, cand, hyp}. 이미 적은 (uid, 후보)는 건너뛴다. 표식 ASR_OK."""
import argparse
import json
import os
import sys

ap = argparse.ArgumentParser()
ap.add_argument("targets"); ap.add_argument("out")
ap.add_argument("--cands", required=True); ap.add_argument("--clips", required=True); ap.add_argument("--cand-root", required=True)
ap.add_argument("--shard", default="0/1"); ap.add_argument("--uids", default="")
ap.add_argument("--model", default="large-v3")
a = ap.parse_args()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qa_rules as Q  # noqa: E402

targets = Q.load_targets(a.targets)
if a.uids:
    keep = set(open(a.uids).read().split())
    targets = [t for t in targets if t["uid"] in keep]
si, sn = map(int, a.shard.split("/"))
items = list(Q.iter_items(targets, a.cands.split(","), a.clips, a.cand_root))[si::sn]
# 같은 폴더의 다른 조각·미리 돌린 결과도 끝난 것으로 본다(합성 중에 미리 잰 결과를 다시 재지 않게)
import glob  # noqa: E402
done = {(r["uid"], r["cand"]) for r in Q.read_jsonl(glob.glob(os.path.join(os.path.dirname(os.path.abspath(a.out)), "*.jsonl")))}
items = [it for it in items if (it[0], it[1]) not in done]

from faster_whisper import WhisperModel  # noqa: E402
from faster_whisper.audio import decode_audio  # noqa: E402
import speak_service  # noqa: E402

m = WhisperModel(a.model, device="cuda", compute_type="float16")
out = open(a.out, "a")
for uid, cand, p in items:
    w = decode_audio(p, sampling_rate=16000)
    segs, _ = m.transcribe(w, language="ko", beam_size=5, temperature=0.0, condition_on_previous_text=False,
                           without_timestamps=True, vad_filter=False)
    hyp = speak_service.collapse_repeats("".join(s.text for s in segs).strip())
    out.write(json.dumps({"uid": uid, "cand": cand, "hyp": hyp}, ensure_ascii=False) + "\n")
    out.flush()
print(f"ASR_OK {a.cands} shard={a.shard} n={len(items)}", flush=True)
