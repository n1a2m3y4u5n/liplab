"""파드: 말하기 3단계 자음 확장(docs/curriculum-roadmap.md 1-5)의 선행 검증. D-GOP가 초성 하나가 바뀐 것을 음소 단위로 가르는지 잰다.
538 정상 화자 클립을 (가) 자기 문장, (나) 한 음절 초성만 대립 자음으로 바꾼 문장에 대어 채점하고, 바뀐 자리의 음소 D-GOP를 비교한다
(AUC = 제 문장 쪽 음소 점수가 더 높을 확률). 새 자음(ㅅ ㅆ ㅈ ㅊ ㅉ ㅎ)과 기존 자음(ㅂ ㅍ ㄷ ㅌ ㄱ ㅋ ㅁ) 대립을 함께 잰다. 결과 out/cons.json.
    /workspace/vb/bin/python speak_consonant_pod_eval.py 24
"""
import json
import os
import random
import sys
from concurrent.futures import ProcessPoolExecutor

W = "/workspace"
os.environ.update(BACKBONE_QUANT="int8", HF_HUB_OFFLINE="1", CUDA_VISIBLE_DEVICES="")
sys.path.insert(0, f"{W}/backend")
AL, SC = f"{W}/backend/models/dgop_ours/aligner", f"{W}/backend/models/dgop_ours/scorer"
CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
# 목표 초성 → 대립 초성(결과 전에 고정). 앞 넷은 새로 넣을 자음, 뒤는 지금 3단계 대립(기준선)
CONTRASTS = {"ㅅ": ["ㄷ", "ㅆ"], "ㅆ": ["ㅅ"], "ㅈ": ["ㅊ", "ㄷ"], "ㅊ": ["ㅈ"], "ㅉ": ["ㅈ"], "ㅎ": ["ㄱ"],
             "ㅂ": ["ㅍ", "ㅁ"], "ㅍ": ["ㅂ"], "ㄷ": ["ㅌ"], "ㅌ": ["ㄷ"], "ㄱ": ["ㅋ"], "ㅋ": ["ㄱ"], "ㅁ": ["ㅂ"]}


def split(ch):
    c = ord(ch) - 0xAC00
    return (c // 588, (c % 588) // 28, c % 28) if 0 <= c < 11172 else None


def join(i, j, k):
    return chr(0xAC00 + (i * 21 + j) * 28 + k)


def variants(text, rng):
    """(바뀐 글자 위치, 원 초성, 대립 초성, 바뀐 문장). 앞 글자가 받침 있는 한글이면 연음·동화가 끼어 빼고, 대립마다 한 자리만."""
    out = []
    for tgt, cons in CONTRASTS.items():
        spots = []
        for i, ch in enumerate(text):
            s = split(ch)
            if not s or CHO[s[0]] != tgt:
                continue
            prev = split(text[i - 1]) if i else None
            if prev and prev[2] != 0:
                continue
            spots.append(i)
        if not spots:
            continue
        i = rng.choice(spots)
        s = split(text[i])
        for c in cons:
            out.append((i, tgt, c, text[:i] + join(CHO.index(c), s[1], s[2]) + text[i + 1:]))
    return out


def job(args):
    import torch
    torch.set_num_threads(2)
    import dgop_acoustic as D
    path, text, vs = args
    data = open(path, "rb").read()
    try:
        base = D.assess_text(data, text, aligner_id=AL, scorer_id=SC).get("phones") or []
        rows = []
        for i, tgt, c, alt in vs:
            ph = D.assess_text(data, alt, aligner_id=AL, scorer_id=SC).get("phones") or []
            if len(ph) != len(base):
                continue
            diff = [k for k in range(len(ph)) if ph[k].get("token") != base[k].get("token")]
            if len(diff) != 1:
                continue
            k = diff[0]
            a, b = base[k].get("dgop"), ph[k].get("dgop")
            if a is None or b is None:
                continue
            rows.append({"path": path, "target": tgt, "contrast": c, "tok": base[k]["token"], "alt_tok": ph[k]["token"],
                         "same": a, "alt": b})
        return rows
    except Exception as e:
        return [{"error": f"{type(e).__name__}: {e}", "path": path}]


if __name__ == "__main__":
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    rng = random.Random(0)
    man = []
    for l in open(f"{W}/c538/manifest.tsv", encoding="utf-8"):
        clip, spk, text = l.rstrip("\n").split("\t")
        p = f"{W}/c538/{clip.replace('.mp4', '.flac')}"
        if os.path.exists(p):
            man.append((p, spk, text))
    rng.shuffle(man)
    jobs = []
    for p, spk, text in man[:600]:
        vs = variants(text, rng)
        if vs:
            jobs.append((p, text, vs))
    rows = []
    with ProcessPoolExecutor(workers) as ex:
        for i, r in enumerate(ex.map(job, jobs, chunksize=2)):
            rows += r
            if i % 50 == 0:
                print(i, len(jobs), len(rows), flush=True)
    json.dump(rows, open(f"{W}/out/cons.json", "w"), ensure_ascii=False)
    print("DONE", len(rows), flush=True)
