"""파드: 모음 포먼트 혀 교정(formants.vowel_feedback)의 실제 음성 검증(계획서 E-9 '목표 대비 오차').
D-GOP 정렬기로 문장 속 단모음 구간(t0~t1)을 찾아 잘라, 그 모음을 목표로(특이도: 'ok' 비율) 또 다른 모음을 목표로(민감도: 교정 비율)
vowel_feedback을 돌린다. 538 정상 화자 표본과 608 청각장애 문장 컷. 결과 out/formant.json.
"""
import json
import os
import random
import sys
from concurrent.futures import ProcessPoolExecutor

W = "/workspace"
os.environ.update(BACKBONE_QUANT="int8", HF_HUB_OFFLINE="1", CUDA_VISIBLE_DEVICES="")
sys.path.insert(0, f"{W}/backend")
VOWELS = ["ㅣ", "ㅔ", "ㅐ", "ㅏ", "ㅓ", "ㅗ", "ㅜ", "ㅡ"]
AL, SC = f"{W}/backend/models/dgop_ours/aligner", f"{W}/backend/models/dgop_ours/scorer"


def job(args):
    import numpy as np
    import soundfile as sf
    import torch
    torch.set_num_threads(2)
    import dgop_acoustic as D
    import formants as F
    path, target, group = args
    try:
        data = open(path, "rb").read()
        r = D.assess_text(data, target, aligner_id=AL, scorer_id=SC)
        y, sr = sf.read(path)
        if y.ndim > 1:
            y = y.mean(axis=1)
        if sr != 16000:
            return []
        out = []
        phones = r.get("phones") or []
        for j, p in enumerate(phones):
            tok = p.get("token", "")
            v = tok.split(":", 1)[-1]
            if not tok.startswith("n:") or v not in VOWELS or "t0" not in p:
                continue
            # CTC 정렬 구간은 한두 프레임(20~40ms)으로 뾰족하다. 모음 구간을 다음 음소 시작까지로 잡고(최대 300ms)
            # 앞뒤 동시조음을 줄이려 가운데 60%만 쓴다(130ms 이상일 때)
            nxt = next((q["t0"] for q in phones[j + 1:] if "t0" in q), None)
            end = min(nxt if nxt is not None else p["t0"] + 0.25, p["t0"] + 0.30, len(y) / sr)
            a, b = int(p["t0"] * sr), int(end * sr)
            if b - a < int(0.08 * sr):
                continue
            if b - a >= int(0.13 * sr):
                m = int((b - a) * 0.2)
                a, b = a + m, b - m
            seg = y[a:b].astype(np.float32)
            own = F.vowel_feedback(seg, v)
            if own is None:
                continue
            others = {}
            for w in VOWELS:
                if w != v:
                    fb = F.vowel_feedback(seg, w)
                    if fb is not None:
                        others[w] = fb["height"] == "ok" and fb["front"] == "ok"
            out.append({"group": group, "vowel": v, "dur": round((b - a) / sr, 3), "dgop": p.get("dgop"),
                        "own_ok": own["height"] == "ok" and own["front"] == "ok", "own_height": own["height"],
                        "own_front": own["front"], "f1": own["f1"], "f2": own["f2"], "others_ok": others})
        return out
    except Exception as e:
        return [{"error": f"{type(e).__name__}: {e}", "path": path}]


if __name__ == "__main__":
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    rng = random.Random(1)
    cuts = [c for c in json.load(open(f"{W}/out/cuts608.json")) if c["cut"]]
    man = []
    for l in open(f"{W}/c538/manifest.tsv", encoding="utf-8"):
        clip, spk, text = l.rstrip("\n").split("\t")
        p = f"{W}/c538/{clip.replace('.mp4', '.flac')}"
        if os.path.exists(p):
            man.append((p, text, "538"))
    rng.shuffle(man)
    jobs = [(c["cut"], c["target"], "608") for c in cuts] + man[:500]
    rows = []
    with ProcessPoolExecutor(workers) as ex:
        for i, r in enumerate(ex.map(job, jobs, chunksize=4)):
            rows += r
            if i % 100 == 0:
                print(i, len(rows), flush=True)
    json.dump(rows, open(f"{W}/out/formant.json", "w"), ensure_ascii=False)
    print("DONE", len(rows), flush=True)
