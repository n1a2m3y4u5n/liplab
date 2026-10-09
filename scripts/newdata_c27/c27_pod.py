"""608 범주 27 새 화자 채점(파드 쪽, docs/newdata-608c27-538-2026-10.md 2.1절, docs/newdata-c27-judgments-2026-10.md).
session_c27.sh가 /workspace에 푼 것을 쓴다(s13_newspk.py와 같은 배치).
  backend/       앱 커밋 b675975 backend(10/6~10/9 S18·대치 측정과 같은 판, int8)
  backend_new/   지금 앱 backend(이 브랜치, 끝 자르기·끝 구간 다시 나누기 기본 켬, 같은 int8 가중치)
  tools/{s13_newspk.py, scores_1006.py, build_scores_csv.py, c27_pod.py}, scripts/{speak_asr_pod_run.py(b675975), scoring_s18_head.py}
  n608/s608/*.flac + n608/labels/*.json, bridge/*.wav + bridge.json(10/6 밤 run1의 538 클립 30개와 그 목표)

  python c27_pod.py jobs        cuts608.json → 등록 규칙(20초 넘는 조각 제외, 세션마다 15개, 화자 5개 미만 제외) → out/jobs.json
                                (s13_newspk.py dgop이 그대로 읽는 형식: s18·bridge·dir608)
  python c27_pod.py trim W      지금 앱 D-GOP(음소 덤프 포함): 자기·다른 2·대치 목표 + 다리 → out/trim.jsonl, outb/trim_bridge.jsonl
  python c27_pod.py selftest    모델 없이 고르기 규칙 점검
점수를 보는 단계는 없다. 고르기는 조각 길이와 이름만 쓴다.
"""
import hashlib
import json
import os
import random
import sys
import time
import zlib
from concurrent.futures import ProcessPoolExecutor

W = os.environ.get("SC_W", "/workspace")
os.environ.setdefault("SC_W", W)
TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
OUT, OUTB = f"{W}/out", f"{W}/outb"
MAX_LEN = 20.0
PER_SESSION = 15
MIN_SPK = 5
SEED = 20261009


def clip_id(c):
    return f"{c['file'][:-5]}:{c['si']:03d}"


def select(cuts):
    """등록 2.1절: 조각 길이 > 20초 제외 → 세션마다 조각 ID 순 정렬, 15개 넘으면 random.Random(20261009)로 15개 → 화자 5개 미만 제외.
    돌려주는 순서는 cuts608.json의 순서(세션·문장 순)."""
    import s13_newspk as S13
    ok = [c for c in cuts if c.get("cut") and c["end"] - c["start"] <= MAX_LEN]
    by = {}
    for c in ok:
        by.setdefault(c["file"], []).append(c)
    keep = set()
    for f, cs in by.items():
        ids = sorted(clip_id(c) for c in cs)
        if len(ids) > PER_SESSION:
            ids = random.Random(SEED).sample(ids, PER_SESSION)
        keep |= set(ids)
    spk_n = {}
    for c in ok:
        if clip_id(c) in keep:
            s = S13.spk_of(c["file"][:-5])
            spk_n[s] = spk_n.get(s, 0) + 1
    drop = {s for s, n in spk_n.items() if n < MIN_SPK}
    out = [c for c in ok if clip_id(c) in keep and S13.spk_of(c["file"][:-5]) not in drop]
    info = {"cut": sum(1 for c in cuts if c.get("cut")), "le20": len(ok), "kept": len(out), "speakers": len(spk_n) - len(drop),
            "dropped_speakers": sorted(drop), "sessions": len({c["file"] for c in out})}
    return out, info


def cmd_jobs():
    import s13_newspk as S13
    os.makedirs(OUT, exist_ok=True)
    cuts = json.load(open(f"{W}/n608/out/cuts608.json", encoding="utf-8"))
    kept, info = select(cuts)
    out = {"s18": [], "dir608": [], "select": info}
    items = [(c["cut"], c["target"]) for c in kept]
    meta = {c["cut"]: c for c in kept}
    for p, t, k in S13.pairs_for(items, random.Random(0)):
        c = meta[p]
        stem = c["file"][:-5]
        out["s18"].append({"set": "608", "spk": S13.spk_of(stem), "clip": clip_id(c), "path": p, "target": t, "kind": k})
    br = json.load(open(f"{W}/bridge/bridge.json", encoding="utf-8"))
    out["bridge"] = [{"set": "538", "spk": b["spk"], "clip": b["clip"], "path": f"{W}/bridge/{b['clip']}.wav", "target": b["target"],
                      "kind": b["kind"]} for b in br]
    sys.path.insert(0, f"{W}/backend")
    os.environ.update(HF_HUB_OFFLINE="1")
    import jamo_vocab
    for c in kept:                                   # s13_newspk.jobs의 608 대치 짝과 같은 규칙(짝별 최대 3자리, 시드 crc32(클립 ID))
        cid = clip_id(c)
        text = c["target"]
        base = jamo_vocab.text_to_tokens(text)
        rng = random.Random(zlib.crc32(cid.encode()))
        alts = []
        for y, x in S13.DIR_PAIRS:
            sp = S13.spots(text, y)
            for i in rng.sample(sp, min(S13.MAX_SPOTS, len(sp))):
                alt = S13.with_onset(text, i, x)
                k = S13.locate(base, jamo_vocab.text_to_tokens(alt), y, x)
                if k is not None:
                    alts.append({"pair": f"{y}>{x}", "text": alt, "k": k})
        out["dir608"].append({"spk": S13.spk_of(c["file"][:-5]), "clip": cid, "path": c["cut"], "true": text, "alts": alts})
    json.dump(out, open(f"{OUT}/jobs.json", "w"), ensure_ascii=False)
    from collections import Counter
    print("C27_SELECT", json.dumps(info, ensure_ascii=False), flush=True)
    print("JOBS s18", dict(Counter(j["kind"] for j in out["s18"])), "bridge", len(out["bridge"]), "dir608 alts",
          dict(Counter(a["pair"] for d in out["dir608"] for a in d["alts"])), flush=True)
    print("C27_JOBS_OK", flush=True)


# ───────────────────────── 지금 앱(끝 자르기) D-GOP + 음소 덤프 ─────────────────────────
_NEW = {}
PH_KEYS = ("token", "aligned", "scorable", "silent_h", "t0", "t1", "dgop", "naive", "confidence")


def _new_setup():
    if "D" in _NEW:
        return _NEW["D"]
    bk = f"{W}/backend_new"
    os.environ.update(DGOP_ALIGNER_ID=f"{bk}/models/dgop_ours/aligner", DGOP_SCORER_ID=f"{bk}/models/dgop_ours/scorer",
                      DGOP_CALIBRATION=f"{bk}/data/dgop_calibration_ours.json", BACKBONE_QUANT="int8", HF_HUB_OFFLINE="1",
                      CUDA_VISIBLE_DEVICES="", LIPLAB_CONTENT_WARMUP="0", DGOP_DEVICE="cpu")
    for k in ("DGOP_TAIL_TRIM", "DGOP_TAIL_RESEG"):
        os.environ.pop(k, None)                      # 앱 기본값(둘 다 켬)
    sys.path.insert(0, bk)
    import numpy as np
    import torch
    torch.set_num_threads(2)
    import dgop_acoustic as D
    assert hasattr(D, "trim_trailing_silence"), "끝 자르기가 없는 backend"
    orig = D.ctc_outputs
    memo = {}

    def memo_outputs(waveform, sample_rate, model_id=D.DEFAULT_MODEL_ID):
        key = (model_id, int(sample_rate), hashlib.sha1(np.ascontiguousarray(waveform).tobytes()).hexdigest())
        if key not in memo:
            memo[key] = orig(waveform, sample_rate, model_id)
        return memo[key]
    D.ctc_outputs = memo_outputs                     # 클립마다 순전파 한 번(채점 함수는 그대로)
    _NEW.update(D=D, memo=memo)
    return D


def _trim_job(task):
    path, targets, meta = task
    D = _new_setup()
    _NEW["memo"].clear()
    al, sc = os.environ["DGOP_ALIGNER_ID"], os.environ["DGOP_SCORER_ID"]
    data = open(path, "rb").read()
    rows = []
    for target, kind, extra in targets:
        try:
            r = D.assess_text(data, target, aligner_id=al, scorer_id=sc)
            ph = [{k: p.get(k) for k in PH_KEYS if k in p} for p in (r.get("phones") or [])]
            rows.append({"target": target, "kind": kind, **extra, "score": r.get("score"), "raw": r.get("raw_score"),
                         "uncertainty": r.get("uncertainty"), "phones": ph})
        except Exception as e:
            rows.append({"target": target, "kind": kind, **extra, "error": f"{type(e).__name__}: {e}"})
    return meta, rows


def cmd_trim(workers):
    J = json.load(open(f"{OUT}/jobs.json", encoding="utf-8"))
    alts = {d["clip"]: d for d in J["dir608"]}
    for name, rows, fn in (("c27", J["s18"], f"{OUT}/trim.jsonl"), ("bridge", J["bridge"], f"{OUTB}/trim_bridge.jsonl")):
        os.makedirs(os.path.dirname(fn), exist_ok=True)
        by, order, info = {}, [], {}
        for r in rows:
            if r["path"] not in by:
                by[r["path"]] = []
                order.append(r["path"])
                info[r["path"]] = {"set": r["set"], "spk": r["spk"], "clip": r["clip"]}
            by[r["path"]].append((r["target"], r["kind"], {}))
        if name == "c27":
            for p in order:
                d = alts.get(info[p]["clip"])
                for a in (d["alts"] if d else []):
                    by[p].append((a["text"], "sub", {"pair": a["pair"], "k": a["k"]}))
        tasks = [(p, by[p], info[p]) for p in order]
        t0, n = time.time(), 0
        with open(fn, "w") as fo, ProcessPoolExecutor(workers) as ex:
            for k, (meta, recs) in enumerate(ex.map(_trim_job, tasks, chunksize=1), 1):
                for x in recs:
                    fo.write(json.dumps({**meta, **x}, ensure_ascii=False) + "\n")
                    n += 1
                if k % 50 == 0:
                    print(f"TRIM {name} {k}/{len(tasks)} {time.time() - t0:.0f}s", flush=True)
        print(f"TRIM_{name.upper()}_DONE clips={len(tasks)} rows={n}", flush=True)
    print("C27_TRIM_OK", flush=True)


def cmd_selftest():
    cuts = []
    for s in range(3):
        f = f"ID-02-27-N-AAA-02-0{s + 1}-F-30-KK.flac"
        for i in range(20 if s == 1 else (4 if s == 2 else 10)):
            cuts.append({"file": f, "si": i, "cut": f"/x/{f}_{i}.wav", "target": "가나다라.", "start": 0.0, "end": 25.0 if i == 0 else 3.0})
    cuts.append({"file": "ID-02-27-N-BBB-02-01-M-40-KK.flac", "si": 0, "cut": "/x/b.wav", "target": "가.", "start": 0, "end": 3})
    kept, info = select(cuts)
    assert info["le20"] == len(cuts) - 3, info
    assert sum(1 for c in kept if "-02-02-" in c["file"]) == PER_SESSION, info
    assert "27-BBB-M-40" in info["dropped_speakers"], info
    assert kept == sorted(kept, key=lambda c: (c["file"], c["si"])), "순서"
    again, _ = select(cuts)
    assert [clip_id(c) for c in again] == [clip_id(c) for c in kept]
    print("C27_SELFTEST_OK", json.dumps(info, ensure_ascii=False))


if __name__ == "__main__":
    cmd = sys.argv[1]
    w = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    {"jobs": cmd_jobs, "trim": lambda: cmd_trim(w), "selftest": cmd_selftest}[cmd]()
