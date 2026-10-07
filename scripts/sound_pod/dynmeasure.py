"""동적 문장 합성 경로(backend/sound_tts.py)를 서버와 같은 조건으로 잰다: CPU 2코어(taskset), 정렬기 int8 먼저 적재(서버 상태),
그 위에 Supertonic을 올렸을 때 늘어나는 상주 메모리(RSS)와 문장 하나의 지연(합성·인코딩·정렬).
    taskset -c 0,1 venv/score/bin/python dynmeasure.py SENTENCES.json OUT.json"""
import json, os, sys, time
os.environ["OMP_NUM_THREADS"] = "2"
os.environ.setdefault("BACKBONE_QUANT", "int8")
os.environ.setdefault("DGOP_DEVICE", "cpu")
os.environ["DGOP_ALIGNER_ID"] = "/workspace/tts/models/dgop_ours/aligner"
os.environ["LIPLAB_SOUND_THREADS"] = "2"
sys.path.insert(0, "/workspace/tts/backend")


def rss_mb():
    for line in open("/proc/self/status"):
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) / 1024
    return None


import torch
torch.set_num_threads(2)
torch.set_grad_enabled(False)
out = {"rss_start_mb": rss_mb()}
import dgop_acoustic as DA
import numpy as np
DA._load(os.environ["DGOP_ALIGNER_ID"])
DA.phone_confidences(np.zeros(16000, np.float32), 16000, ["n:ㅏ"], aligner_id=os.environ["DGOP_ALIGNER_ID"])
out["rss_after_aligner_mb"] = rss_mb()
import sound_tts
t0 = time.time()
sound_tts._load()
out["supertonic_load_s"] = round(time.time() - t0, 2)
out["rss_after_supertonic_mb"] = rss_mb()
sents = [e["text"] for e in json.load(open(sys.argv[1]))]
rows = []
for s in sents:
    t0 = time.time()
    r = sound_tts.synthesize(s, "F1")
    t1 = time.time()
    wav16, ms, files = r
    syl = sound_tts.align_syllables(wav16, s, ms)
    t2 = time.time()
    rows.append({"text": s, "audio_ms": round(ms), "synth_encode_s": round(t1 - t0, 3), "align_s": round(t2 - t1, 3),
                 "bytes": {k: len(v) for k, v in files.items()}, "timing_ok": syl is not None})
out["rss_peak_mb"] = rss_mb()
import resource
out["maxrss_mb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
out["rows"] = rows
out["mean_total_s"] = round(sum(r["synth_encode_s"] + r["align_s"] for r in rows) / len(rows), 3)
json.dump(out, open(sys.argv[2], "w"), ensure_ascii=False, indent=1)
print("DYN_OK", out["mean_total_s"], out["rss_after_aligner_mb"], out["rss_after_supertonic_mb"], out["maxrss_mb"])
