"""자연스러움 대리 지표: UTMOS22 strong(SpeechMOS, 영어 MOS로 학습. 한국어에는 상대 비교로만 쓴다).
    python utmos.py DIR [DIR ...]  → DIR/utmos.jsonl {id, mos}"""
import json, os, sys
import torch
torch.set_num_threads(6)
from faster_whisper.audio import decode_audio

pred = torch.hub.load("tarepan/SpeechMOS:v1.2.0", "utmos22_strong", trust_repo=True)
pred.eval()
for d in sys.argv[1:]:
    out = open(os.path.join(d, "utmos.jsonl"), "w")
    for f in sorted(os.listdir(d)):
        if not f.endswith(".wav"):
            continue
        w = torch.from_numpy(decode_audio(os.path.join(d, f), sampling_rate=16000))[None]
        with torch.no_grad():
            m = float(pred(w, 16000).item())
        out.write(json.dumps({"id": f[:-4], "mos": round(m, 4)}) + "\n")
    out.close()
    print("UTMOS_OK", d)
