"""소리 쪽 바꿈 만들기: 바꾼 글을 합성(docs/scoring-subst-2026-10.md 3.3절 N2). 보조 학습(C-aug)과 보고에만 쓴다(고르기·확인 판정에 쓰지 않는다).

앱 소리와 같은 엔진(Supertonic 3, backend/sound_tts.synthesize_raw, 8단계·속도 1.05)과 훈련 목소리 넷(M1·F1·M2·F2)으로
탐색 자기 문장 가운데 바꾼 목표(min)가 있는 문장의 원래 글과 바꾼 글을 합성한다. 목표는 둘 다 **원래 글**이다:
  - tts_own: 원래 글을 합성한 소리 + 원래 글 목표(y=0)
  - tts_min: 바꾼 글을 합성한 소리 + 원래 글 목표(바꾼 자리 y=1). 학습자가 실제 낱말을 목표로 바꾼 소리를 낸 경우와 같은 방향이다.
합성 목소리는 예사·거센·된소리 대조를 구별되게 내지 못하는 경우가 있어(docs/listen-voice-contrast-2026-10.md, 소리 세기 0.583 미달)
독립 판정 모델(kresnik/wav2vec2-large-xlsr-korean, 음절 CTC)로 걸러 낸다: tts_min 소리에서 ll(바꾼 글) − ll(원래 글) > 0이고
tts_own 소리에서 ll(원래 글) − ll(바꾼 글) > 0인 짝만 남긴다(listen_voice_avoid.json과 같은 판정식).

  python tts_pairs.py texts JOBS OUT.json [--n N]            JOBS의 own·min 짝 → 합성할 글 목록(문장 N개, Random(20261019))
  python tts_pairs.py synth OUT.json OUTDIR                  (supertonic 가상환경) 합성 → OUTDIR/audio/*.wav(16 kHz)
  python tts_pairs.py judge OUT.json OUTDIR                  (torch 가상환경) kresnik 판정 → OUTDIR/judge.jsonl, OUTDIR/jobs_tts.json
"""
import hashlib
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BK = os.environ.get("SUB_BACKEND") or os.path.join(HERE, "..", "..", "backend")
VOICES = ["M1", "F1", "M2", "F2"]
SEED = 20261019
JUDGE = "kresnik/wav2vec2-large-xlsr-korean"


def cid(*parts):
    return hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()[:16]


def cmd_texts(jobs_path, out, n):
    jobs = json.load(open(jobs_path, encoding="utf-8"))
    pairs = []
    for j in jobs:
        own = next((t for t in j["targets"] if t["kind"] == "own"), None)
        mins = [t for t in j["targets"] if t["kind"] == "min"]
        if own and mins:
            pairs.append({"set": j["set"], "spk": j["spk"], "own": own["text"], "min": mins[0]})
    rng = random.Random(SEED)
    pick = rng.sample(pairs, min(n, len(pairs))) if n else pairs
    items = []
    for k, p in enumerate(pick):
        v = VOICES[k % len(VOICES)]
        items.append({"id": cid(v, p["own"], p["min"]["text"]), "voice": v, "set": p["set"], "own": p["own"],
                      "min": p["min"]["text"], "tok_idx": p["min"]["tok_idx"], "cat": p["min"]["cat"]})
    json.dump(items, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(f"TTS_TEXTS {len(items)}", flush=True)


def cmd_synth(items_path, outdir):
    import numpy as np
    import soundfile as sf
    sys.path.insert(0, BK)
    import sound_tts as T
    items = json.load(open(items_path, encoding="utf-8"))
    os.makedirs(os.path.join(outdir, "audio"), exist_ok=True)
    for it in items:
        for kind, text in (("own", it["own"]), ("min", it["min"])):
            f = os.path.join(outdir, "audio", f"{it['id']}_{kind}.wav")
            if os.path.exists(f):
                continue
            x, sr = T.synthesize_raw(text, it["voice"])
            x = T.trim_silence(T.to16k(x, sr), 16000)
            sf.write(f, np.asarray(x, dtype="float32"), 16000)
    print(f"TTS_SYNTH_DONE {len(items)}", flush=True)


def cmd_judge(items_path, outdir):
    import soundfile as sf
    import torch
    from transformers import AutoModelForCTC, AutoProcessor
    proc = AutoProcessor.from_pretrained(JUDGE)
    model = AutoModelForCTC.from_pretrained(JUDGE).eval()
    torch.set_num_threads(int(os.environ.get("TTS_JUDGE_THREADS", "2")))
    blank = proc.tokenizer.pad_token_id

    def ll(lp, text):
        ids = proc.tokenizer(text.replace(".", "").replace("?", "").replace("!", "").replace(",", "")).input_ids
        loss = torch.nn.functional.ctc_loss(lp.unsqueeze(1), torch.tensor([ids]), torch.tensor([lp.shape[0]]),
                                            torch.tensor([len(ids)]), blank=blank, reduction="sum", zero_infinity=True)
        return -float(loss)

    items = json.load(open(items_path, encoding="utf-8"))
    jobs, kept = [], 0
    with open(os.path.join(outdir, "judge.jsonl"), "w", encoding="utf-8") as fo:
        for it in items:
            m = {}
            for kind in ("own", "min"):
                x, sr = sf.read(os.path.join(outdir, "audio", f"{it['id']}_{kind}.wav"), dtype="float32")
                with torch.no_grad():
                    lp = torch.log_softmax(model(proc(x, sampling_rate=sr, return_tensors="pt").input_values).logits[0], -1)
                m[kind] = ll(lp, it["own"]) - ll(lp, it["min"])     # 원래 글 쪽이 크면 양수
            ok = m["own"] > 0 and m["min"] < 0
            fo.write(json.dumps({"id": it["id"], "voice": it["voice"], "cat": it["cat"], "margin_own": round(m["own"], 3),
                                 "margin_min": round(-m["min"], 3), "keep": ok}, ensure_ascii=False) + "\n")
            if not ok:
                continue
            kept += 1
            for kind, y_kind in (("own", "tts_own"), ("min", "tts_min")):
                t = {"text": it["own"], "kind": y_kind, "voice": it["voice"], "cat": it["cat"]}
                if kind == "min":
                    t["tok_idx"] = it["tok_idx"]
                jobs.append({"set": f"tts_{it['set']}", "spk": f"tts-{it['voice']}", "clip": f"tts_{it['id']}_{kind}",
                             "path": f"audio/{it['id']}_{kind}.wav", "targets": [t]})
    json.dump(jobs, open(os.path.join(outdir, "jobs_tts.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print(f"TTS_JUDGE_DONE items={len(items)} kept={kept}", flush=True)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "texts":
        cmd_texts(a[1], a[2], int(a[a.index("--n") + 1]) if "--n" in a else 0)
    elif a and a[0] == "synth":
        cmd_synth(a[1], a[2])
    elif a and a[0] == "judge":
        cmd_judge(a[1], a[2])
    else:
        print(__doc__)
        sys.exit(2)
