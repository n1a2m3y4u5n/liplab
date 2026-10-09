"""608 새 화자 확인 채점(파드 쪽, docs/scoring-608-newspk-2026-10.md 3절). session.sh가 /workspace/ns에 푼 것을 쓴다.
  backend/      앱 커밋 b675975 backend(10/6·10/7과 같은 판, int8)
  backend_new/  지금 앱 backend(integrate a57ee690, 끝 자르기 trim_trailing_silence 포함)
  tools/scores_1006.py, scripts/{speak_asr_pod_run.py, speak_collapse.py}(b675975)
  data/jobs.json, data/n608/*.wav, data/c538n/*.wav, data/bridge608/*.wav

  python newspk.py selftest
  python newspk.py dgop_old W     b675975 D-GOP(scores_1006.clip_job 그대로, 자기·다른 2·반례 8) → out/dgop_old.jsonl
  python newspk.py dgop_new W     지금 앱 D-GOP(끝 자르기, 같은 목표) → out/dgop_new.jsonl
  python newspk.py asr W          전사 경로(faster-whisper base CPU int8, vad 없음·있음)와 점수 → out/tscore.jsonl, out/asr.json
"""
import hashlib
import json
import os
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor

R = os.environ.get("NS_ROOT", "/workspace/ns")
OUT = f"{R}/out"
DATA = f"{R}/data"


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def jobs():
    return json.load(open(f"{DATA}/jobs.json", encoding="utf-8"))


# ───────────────────────── b675975 ─────────────────────────
def _old_job(it):
    os.environ["SC_W"] = R
    sys.path.insert(0, f"{R}/tools")
    import scores_1006 as S
    S.OUT = f"{OUT}/old"          # 로짓 덤프 자리(받지 않는다)
    _, _, rows, sec = S.clip_job((f"{DATA}/{it['path']}", [tuple(t) for t in it["targets"]], f"{it['set']}_{it['clip']}"))
    return it, rows, sec


def cmd_dgop_old(workers):
    os.makedirs(f"{OUT}/old/lp", exist_ok=True)
    J = jobs()
    n, t0 = 0, time.time()
    with open(f"{OUT}/dgop_old.jsonl", "w") as f, ProcessPoolExecutor(workers) as ex:
        for k, (it, rows, sec) in enumerate(ex.map(_old_job, J, chunksize=1), 1):
            for r in rows:
                r.pop("phones", None)
                f.write(json.dumps({"set": it["set"], "spk": it["spk"], "clip": it["clip"], **r}, ensure_ascii=False) + "\n")
                n += 1
            if k % 50 == 0:
                log("DGOP_OLD", k, "/", len(J), round(time.time() - t0), "s")
    log("DGOP_OLD_OK clips", len(J), "rows", n)


# ───────────────────────── 지금 앱(끝 자르기) ─────────────────────────
_NEW = {}


def _new_setup():
    if "D" in _NEW:
        return _NEW["D"]
    bk = f"{R}/backend_new"
    os.environ.update(DGOP_ALIGNER_ID=f"{bk}/models/dgop_ours/aligner", DGOP_SCORER_ID=f"{bk}/models/dgop_ours/scorer",
                      DGOP_CALIBRATION=f"{bk}/data/dgop_calibration_ours.json", BACKBONE_QUANT="int8", HF_HUB_OFFLINE="1",
                      CUDA_VISIBLE_DEVICES="", LIPLAB_CONTENT_WARMUP="0", DGOP_DEVICE="cpu", DGOP_TAIL_TRIM="1")
    sys.path.insert(0, bk)
    import numpy as np
    import torch
    torch.set_num_threads(2)
    import dgop_acoustic as D
    assert hasattr(D, "trim_trailing_silence"), "끝 자르기가 없는 backend"
    orig = D.ctc_outputs
    memo = {}

    def memo_outputs(waveform, sample_rate, model_id=D.DEFAULT_MODEL_ID):
        # scores_1006._setup_worker와 같은 기억: 같은(자른) 파형·같은 모델이면 순전파를 한 번만 한다. 채점 함수는 그대로다
        key = (model_id, int(sample_rate), hashlib.sha1(np.ascontiguousarray(waveform).tobytes()).hexdigest())
        if key not in memo:
            memo[key] = orig(waveform, sample_rate, model_id)
        return memo[key]
    D.ctc_outputs = memo_outputs
    _NEW.update(D=D, memo=memo)
    return D


def _new_job(it):
    D = _new_setup()
    _NEW["memo"].clear()
    al, sc = os.environ["DGOP_ALIGNER_ID"], os.environ["DGOP_SCORER_ID"]
    data = open(f"{DATA}/{it['path']}", "rb").read()
    rows, t0 = [], time.time()
    for target, kind in it["targets"]:
        try:
            r = D.assess_text(data, target, aligner_id=al, scorer_id=sc)
            rows.append({"target": target, "kind": kind, "score": r.get("score"), "raw": r.get("raw_score"), "uncertainty": r.get("uncertainty")})
        except Exception as e:
            rows.append({"target": target, "kind": kind, "error": f"{type(e).__name__}: {e}"})
    return it, rows, round(time.time() - t0, 2)


def cmd_dgop_new(workers):
    J = jobs()
    n, t0 = 0, time.time()
    with open(f"{OUT}/dgop_new.jsonl", "w") as f, ProcessPoolExecutor(workers) as ex:
        for k, (it, rows, sec) in enumerate(ex.map(_new_job, J, chunksize=1), 1):
            for r in rows:
                f.write(json.dumps({"set": it["set"], "spk": it["spk"], "clip": it["clip"], **r}, ensure_ascii=False) + "\n")
                n += 1
            if k % 50 == 0:
                log("DGOP_NEW", k, "/", len(J), round(time.time() - t0), "s")
    log("DGOP_NEW_OK clips", len(J), "rows", n)


# ───────────────────────── 전사 경로(10/7 recut.py cmd_asr와 같은 계산) ─────────────────────────
def _asr_job(p):
    sys.path.insert(0, f"{R}/scripts")
    import speak_asr_pod_run as A
    return A.app_transcribe(p)          # (경로, {"novad": 전사, "vad": 전사})


def cmd_asr(workers):
    sys.path.insert(0, f"{R}/backend")
    os.environ.setdefault("LIPLAB_CONTENT_WARMUP", "0")
    from scoring import _syllable_match_score, align_jamos, to_pronounced_jamos
    sys.path.insert(0, f"{R}/scripts")
    from speak_collapse import collapse_repeats
    J = jobs()
    paths = [f"{DATA}/{it['path']}" for it in J]
    with ProcessPoolExecutor(workers) as ex:
        tr = dict(ex.map(_asr_job, paths, chunksize=1))

    def clean(s):
        return re.sub(r"[^가-힣0-9]", "", s or "")

    def scores(target, trans, collapse=False):      # scores_1006.tscore와 같은 계산
        if collapse:
            trans = collapse_repeats(trans or "")
        c, u = to_pronounced_jamos(clean(target)), to_pronounced_jamos(clean(trans))
        if not c or not u:
            return 0.0, 0.0
        ach = sum(_syllable_match_score(a, b) for a, b in align_jamos(c, u) if a and b)
        r = ach / len(c)
        p = ach / len(u)
        f = 2 * p * r / (p + r) if p + r else 0.0
        return 100 * r, 100 * f
    n = 0
    with open(f"{OUT}/tscore.jsonl", "w") as f:
        for it in J:
            o = tr[f"{DATA}/{it['path']}"]
            for target, kind in it["targets"]:
                if kind not in ("same", "diff"):
                    continue
                s, sv, sc = scores(target, o["novad"]), scores(target, o["vad"]), scores(target, o["novad"], True)
                f.write(json.dumps({"set": it["set"], "spk": it["spk"], "clip": it["clip"], "target": target, "kind": kind,
                                    "r0": round(s[0], 3), "r1": round(s[1], 3), "r0_vad": round(sv[0], 3), "r0_c": round(sc[0], 3)},
                                   ensure_ascii=False) + "\n")
                n += 1
    json.dump({it["set"] + "|" + it["clip"]: tr[f"{DATA}/{it['path']}"] for it in J}, open(f"{OUT}/asr.json", "w"), ensure_ascii=False)
    log("ASR_OK clips", len(paths), "rows", n)


def cmd_selftest():
    J = jobs()
    from collections import Counter
    c = Counter(it["set"] for it in J)
    assert c["608"] == 340 and c["538"] == 600 and c["bridge608"] == 3, c
    for it in J:
        assert os.path.exists(f"{DATA}/{it['path']}"), it["path"]
    print("NS_SELFTEST_OK", dict(c), hashlib.sha1(json.dumps(J, sort_keys=True).encode()).hexdigest()[:12])


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    cmd = sys.argv[1]
    w = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    {"dgop_old": lambda: cmd_dgop_old(w), "dgop_new": lambda: cmd_dgop_new(w), "asr": lambda: cmd_asr(w), "selftest": cmd_selftest}[cmd]()
