"""608 문장 조각 다시 자르기와 다시 자른 조각의 채점(파드 쪽, docs/scoring-608-recut-2026-10.md 2.5·3·4.3절).

session.sh가 /workspace/rc에 푼 것을 쓴다:
  backend/      앱 커밋 b675975 backend(10/6 점수 재생성·S4와 같은 판, models/dgop_ours는 int8 + 설정)
  backend_new/  지금 브랜치 backend(끝 자르기 trim_trailing_silence가 들어간 앱 경로)
  tools/scores_1006.py, scripts/{speak_asr_pod_run.py, speak_collapse.py, s4_eval_pod.py}(b675975·S4와 같은 파일)
  data/hi608/wav16/*.flac(세션 27), data/c538wav/*.wav(다리·지연 표본), data/jobs.json, data/bridge.json, data/lat.json
  models/student_w8.onnx(S4 학생 H)

  python recut.py recut                 다시 자르기(GPU large-v3) → out/recut.json, out/cuts/*.wav
  python recut.py dgop_old WORKERS      b675975 D-GOP(자기·다른 2·반례 8, 로짓 덤프) → out/dgop_full_recut.jsonl, out/lp/
  python recut.py asr WORKERS           전사 경로(base CPU int8, vad 없음·있음)와 점수 → out/tscore_recut.jsonl
  python recut.py dgop_new              지금 backend(끝 자르기) 자기·다른 2 → out/trim_recut.jsonl
  python recut.py s4                    학생 ONNX 자기·다른 2 → out/s4_recut.jsonl
  python recut.py latency               지연 표본 L0(원래 100)·L1(V2)·L1v1(V1)·L2 → out/lat_<이름>.json
  python recut.py selftest
"""
import difflib
import hashlib
import json
import os
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

R = os.environ.get("RC_ROOT", "/workspace/rc")
OUT = f"{R}/out"
DATA = f"{R}/data"
SR = 16000
VAD = dict(threshold=0.5, min_speech_duration_ms=100, min_silence_duration_ms=300, speech_pad_ms=0)
MERGE_GAP = 1.5
MAX_SPAN = 19.4
PAD0, PAD1 = 0.25, 0.35
MAX_LEN = 20.0


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def hangul(s):
    return re.sub(r"[^가-힣]", "", s or "")


def session_audio(f, cache={}):
    import soundfile as sf
    if f not in cache:
        cache.clear()
        y, sr = sf.read(f"{DATA}/hi608/wav16/{f}")
        if y.ndim > 1:
            y = y.mean(axis=1)
        assert sr == SR, sr
        cache[f] = y
    return cache[f]


def cut_path(clip):
    return f"{OUT}/cuts/{clip.replace(':', '_')}.wav"


def orig_cut_path(clip):
    return f"{OUT}/cuts_orig/{clip.replace(':', '_')}.wav"


def write_cut(path, f, start, end):
    """10/6 자르기(speak_asr_pod_run.cut_608)와 같은 방식: sf.write(audio[int(a*sr):int(b*sr)])."""
    import soundfile as sf
    y = session_audio(f)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sf.write(path, y[int(start * SR):int(end * SR)], SR)


# ───────────────────────── 다시 자르기(2.5절) ─────────────────────────
def blocks_of(w):
    from faster_whisper.vad import VadOptions, get_speech_timestamps
    ts = get_speech_timestamps(w.astype(np.float32), VadOptions(**VAD))
    segs = [(t["start"] / SR, t["end"] / SR) for t in ts]
    blocks = []
    for s, e in segs:
        if blocks and s - blocks[-1][1] < MERGE_GAP:
            blocks[-1][1] = e
        else:
            blocks.append([s, e])
    return segs, blocks


def cmd_recut():
    from faster_whisper import WhisperModel
    big = WhisperModel("large-v3", device="cuda", compute_type="float16")
    log("large-v3 loaded")
    jobs = json.load(open(f"{DATA}/jobs.json", encoding="utf-8"))
    res = []
    for j in jobs:
        y = session_audio(j["file"])
        a0, b0 = j["start"], j["end"]
        w = y[int(a0 * SR):int(b0 * SR)]
        segs, blocks = blocks_of(w)
        target = hangul(j["target"])
        cands = []
        for p in range(len(blocks)):
            for q in range(p, len(blocks)):
                s, e = blocks[p][0], blocks[q][1]
                if e - s > MAX_SPAN:
                    break
                x = w[int(s * SR):int(e * SR)].astype(np.float32)
                out, _ = big.transcribe(x, language="ko", beam_size=5, temperature=0.0, vad_filter=False,
                                        condition_on_previous_text=False)
                text = "".join(t.text for t in out).strip()
                r = difflib.SequenceMatcher(None, target, hangul(text)).ratio()
                cands.append({"p": p, "q": q, "s": round(s, 3), "e": round(e, 3), "ratio": round(r, 4), "n_hangul": len(hangul(text))})
        best = None
        for c in cands:
            key = (c["ratio"], -(c["e"] - c["s"]), c["s"])
            if best is None or key > best[0]:
                best = (key, c)
        rec = {"clip": j["clip"], "file": j["file"], "si": j["si"], "spk": j["spk"], "orig_start": a0, "orig_end": b0,
               "orig_ratio": j["ratio"], "n_vad": len(segs), "n_blocks": len(blocks), "n_cand": len(cands)}
        if best is None:
            rec.update(accepted=False, reason="no_candidate")
        else:
            c = best[1]
            ns, ne = max(0.0, c["s"] - PAD0), min(len(w) / SR, c["e"] + PAD1)
            start, end = round(a0 + ns, 3), round(a0 + ne, 3)
            ok = c["ratio"] >= 0.5 and c["ratio"] >= j["ratio"] - 0.15 and end - start <= MAX_LEN
            reason = "" if ok else ("ratio<0.5" if c["ratio"] < 0.5 else "ratio<orig-0.15" if c["ratio"] < j["ratio"] - 0.15 else "len>20")
            rec.update(accepted=bool(ok), reason=reason, ratio=c["ratio"], start=start, end=end, length=round(end - start, 3),
                       best_blocks=[c["p"], c["q"]])
            if ok:
                write_cut(cut_path(j["clip"]), j["file"], start, end)
        res.append(rec)
        log("RECUT", j["clip"], rec.get("accepted"), rec.get("ratio"), rec.get("length"), rec.get("reason"))
    json.dump(res, open(f"{OUT}/recut.json", "w"), ensure_ascii=False, indent=1)
    log("RECUT_OK", sum(r["accepted"] for r in res), "/", len(res))


def accepted():
    return {r["clip"]: r for r in json.load(open(f"{OUT}/recut.json")) if r["accepted"]}


# ───────────────────────── b675975 D-GOP(3절) ─────────────────────────
def score_tasks():
    """(경로, [(목표, 종류)], 덤프 ID, set, spk, clip): 다시 자른 조각 + 다리."""
    jobs = {j["clip"]: j for j in json.load(open(f"{DATA}/jobs.json", encoding="utf-8"))}
    acc = accepted()
    tasks = []
    for clip in sorted(acc):
        j = jobs[clip]
        tasks.append((cut_path(clip), [tuple(t) for t in j["targets"]], f"608_{clip}", "608", j["spk"], clip))
    for b in json.load(open(f"{DATA}/bridge.json", encoding="utf-8")):
        if b["set"] == "608":
            p = orig_cut_path(b["clip"])
            if not os.path.exists(p):
                write_cut(p, b["file"], b["start"], b["end"])
        else:
            p = f"{DATA}/c538wav/{b['clip']}.wav"
        tasks.append((p, [tuple(t) for t in b["targets"]], f"bridge_{b['set']}_{b['clip']}", "bridge" + b["set"], b["spk"], b["clip"]))
    return tasks


def _dgop_job(t):
    os.environ["SC_W"] = R
    sys.path.insert(0, f"{R}/tools")
    import scores_1006 as S
    path, targets, cid, st, spk, clip = t
    _, _, rows, sec = S.clip_job((path, targets, cid))
    return st, spk, clip, rows, sec


def cmd_dgop_old(workers):
    os.makedirs(f"{OUT}/lp", exist_ok=True)
    tasks = score_tasks()
    n = 0
    with open(f"{OUT}/dgop_full_recut.jsonl", "w") as f, ProcessPoolExecutor(workers) as ex:
        for st, spk, clip, rows, sec in ex.map(_dgop_job, tasks, chunksize=1):
            for r in rows:
                f.write(json.dumps({"set": st, "spk": spk, "clip": clip, **r}, ensure_ascii=False) + "\n")
                n += 1
            log("DGOP", clip, len(rows), sec)
    log("DGOP_OLD_OK", len(tasks), "rows", n)


# ───────────────────────── 전사 경로(3절) ─────────────────────────
def _asr_job(p):
    sys.path.insert(0, f"{R}/scripts")
    import speak_asr_pod_run as A
    return A.app_transcribe(p)


def cmd_asr(workers):
    sys.path.insert(0, f"{R}/backend")
    os.environ.setdefault("LIPLAB_CONTENT_WARMUP", "0")
    from scoring import _syllable_match_score, align_jamos, to_pronounced_jamos
    sys.path.insert(0, f"{R}/scripts")
    from speak_collapse import collapse_repeats
    sys.path.insert(0, f"{R}/tools")
    os.environ["SC_W"] = R
    from scores_1006 import sid_of
    tasks = score_tasks()
    paths = sorted({t[0] for t in tasks})
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
    with open(f"{OUT}/tscore_recut.jsonl", "w") as f:
        for path, targets, cid, st, spk, clip in tasks:
            o = tr[path]
            for target, kind in targets:
                s, sv, sc = scores(target, o["novad"]), scores(target, o["vad"]), scores(target, o["novad"], True)
                f.write(json.dumps({"set": st, "clip": clip, "target_sid": sid_of(target), "kind": kind, "r0": round(s[0], 3),
                                    "r1": round(s[1], 3), "r0_vad": round(sv[0], 3), "r0_c": round(sc[0], 3)}) + "\n")
                n += 1
    json.dump({t[5] + "|" + t[3]: tr[t[0]] for t in tasks}, open(f"{OUT}/asr_recut.json", "w"), ensure_ascii=False)
    log("ASR_OK", len(paths), "rows", n)


# ───────────────────────── 지금 backend(끝 자르기) ─────────────────────────
def cmd_dgop_new():
    bk = f"{R}/backend_new"
    os.environ.update(DGOP_ALIGNER_ID=f"{bk}/models/dgop_ours/aligner", DGOP_SCORER_ID=f"{bk}/models/dgop_ours/scorer",
                      DGOP_CALIBRATION=f"{bk}/data/dgop_calibration_ours.json", BACKBONE_QUANT="int8", HF_HUB_OFFLINE="1",
                      CUDA_VISIBLE_DEVICES="", LIPLAB_CONTENT_WARMUP="0", DGOP_DEVICE="cpu")
    sys.path.insert(0, bk)
    import torch
    torch.set_num_threads(int(os.environ.get("OMP_NUM_THREADS", "4")))
    import dgop_acoustic as D
    assert hasattr(D, "trim_trailing_silence"), "끝 자르기가 없는 backend"
    al, sc = os.environ["DGOP_ALIGNER_ID"], os.environ["DGOP_SCORER_ID"]
    n = 0
    with open(f"{OUT}/trim_recut.jsonl", "w") as f:
        for path, targets, cid, st, spk, clip in score_tasks():
            data = open(path, "rb").read()
            for target, kind in targets:
                if kind not in ("same", "diff"):
                    continue
                try:
                    r = D.assess_text(data, target, aligner_id=al, scorer_id=sc)
                    row = {"score": r.get("score"), "raw": r.get("raw_score")}
                except Exception as e:
                    row = {"error": f"{type(e).__name__}: {e}"}
                f.write(json.dumps({"set": st, "spk": spk, "clip": clip, "target": target, "kind": kind, **row}, ensure_ascii=False) + "\n")
                n += 1
    log("DGOP_NEW_OK rows", n)


# ───────────────────────── S4 학생 ─────────────────────────
def _s4_setup(threads=2):
    os.environ["S4_W"] = R
    sys.path.insert(0, f"{R}/scripts")
    import s4_eval_pod as E
    D = E.setup(f"onnx:{R}/models/student_w8.onnx", threads)
    return E, D


def cmd_s4():
    E, D = _s4_setup(int(os.environ.get("OMP_NUM_THREADS", "4")))
    al, sc = E._STATE["ids"]
    n = 0
    with open(f"{OUT}/s4_recut.jsonl", "w") as f:
        for path, targets, cid, st, spk, clip in score_tasks():
            data = open(path, "rb").read()
            for target, kind in targets:
                if kind not in ("same", "diff"):
                    continue
                r = D.assess_text(data, target, aligner_id=al, scorer_id=sc)
                f.write(json.dumps({"set": st, "spk": spk, "clip": clip, "target": target, "kind": kind, "score": r.get("score"),
                                    "raw": r.get("raw_score")}, ensure_ascii=False) + "\n")
                n += 1
    log("S4_OK rows", n)


def lat_sets():
    """data/lat.json: 538 표본(50), 608 원래 E1 조각 목록(363, 자기 문장·시작·끝), V1 목록, 단어 목록 조각, 원래 지연 표본 100."""
    L = json.load(open(f"{DATA}/lat.json", encoding="utf-8"))
    acc = accepted()
    c608 = {c["clip"]: c for c in L["e1_608"]}

    def p608(clip):
        if clip in acc:
            return cut_path(clip)
        c = c608[clip]
        p = orig_cut_path(clip)
        if not os.path.exists(p):
            write_cut(p, c["file"], c["start"], c["end"])
        return p

    def pick(clips):        # s4_eval_pod.latency_sentences와 같은 규칙: 이름 순 등간격 50
        js = sorted(clips)
        step = len(js) / 50.0
        return [js[int(k * step)] for k in range(50)]
    s538 = [(f"{DATA}/c538wav/{x['clip']}.wav", x["own"], "538", x["clip"]) for x in L["s538"]]
    recut_all = set(L["recut25"])
    v2 = [c for c in c608 if c not in L["wordlist"] and (c not in recut_all or c in acc)]
    v1 = [c for c in c608 if c not in L["wordlist"] and c not in recut_all]
    out = {
        "L0": s538 + [(p608(c) if c not in acc else orig_cut_path(c), c608[c]["own"], "608", c) for c in L["orig100_608"]],
        "L1": s538 + [(p608(c), c608[c]["own"], "608", c) for c in pick(v2)],
        "L1v1": s538 + [(p608(c), c608[c]["own"], "608", c) for c in pick(v1)],
        "L2": s538 + [(p608(c), c608[c]["own"], "608", c) for c in L["orig100_608"] if c not in L["wordlist"] and (c not in recut_all or c in acc)],
    }
    for c in L["orig100_608"]:          # L0의 다시 자른 조각은 원래 소리여야 한다
        if c in acc and not os.path.exists(orig_cut_path(c)):
            write_cut(orig_cut_path(c), c608[c]["file"], c608[c]["start"], c608[c]["end"])
    return out


def cmd_latency():
    import soundfile as sf
    threads = int(os.environ.get("LAT_THREADS", "2"))
    os.environ["OMP_NUM_THREADS"] = str(threads)
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    sets = lat_sets()
    E, D = _s4_setup(threads)
    al, sc = E._STATE["ids"]
    be = E._STATE["be"]
    cpu = next((l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name")), "")
    for name in ("L0", "L1", "L1v1", "L2"):
        sel = sets[name]
        for p, t, _, _ in sel[:3]:        # 데우기 3문장(등록 절차와 같다)
            D.assess_text(open(p, "rb").read(), t, aligner_id=al, scorer_id=sc)
        be.fwd.clear()
        rows = []
        for p, t, st, clip in sel:
            data = open(p, "rb").read()
            t0 = time.perf_counter()
            r = D.assess_text(data, t, aligner_id=al, scorer_id=sc)
            dt = time.perf_counter() - t0
            info = sf.info(p)
            rows.append({"set": st, "clip": clip, "sec": round(dt, 4), "audio_s": round(info.frames / info.samplerate, 3), "raw": r.get("raw_score")})
        secs = np.array([r["sec"] for r in rows])
        res = {"set": name, "threads": threads, "cpu": cpu, "n": len(rows), "median": float(np.median(secs)),
               "p95": float(np.percentile(secs, 95)), "max": float(secs.max()), "mean_audio_s": float(np.mean([r["audio_s"] for r in rows])),
               "fwd_median": float(np.median(be.fwd)) if be.fwd else None, "rows": rows}
        json.dump(res, open(f"{OUT}/lat_{name}.json", "w"), indent=1)
        log("LATENCY", name, res["n"], "median", round(res["median"], 3), "p95", round(res["p95"], 3), cpu)
    log("LATENCY_OK")


def cmd_selftest():
    jobs = json.load(open(f"{DATA}/jobs.json", encoding="utf-8"))
    L = json.load(open(f"{DATA}/lat.json", encoding="utf-8"))
    assert len(jobs) == 25 and len(L["wordlist"]) == 9 and len(L["s538"]) == 50 and len(L["orig100_608"]) == 50, (len(jobs), len(L["wordlist"]))
    for j in jobs:
        assert os.path.exists(f"{DATA}/hi608/wav16/{j['file']}"), j["file"]
    for x in L["s538"]:
        assert os.path.exists(f"{DATA}/c538wav/{x['clip']}.wav"), x["clip"]
    print("RC_SELFTEST_OK", hashlib.sha1(json.dumps(jobs, sort_keys=True).encode()).hexdigest()[:12])


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    cmd = sys.argv[1]
    if cmd == "recut":
        cmd_recut()
    elif cmd == "dgop_old":
        cmd_dgop_old(int(sys.argv[2]))
    elif cmd == "asr":
        cmd_asr(int(sys.argv[2]))
    elif cmd == "dgop_new":
        cmd_dgop_new()
    elif cmd == "s4":
        cmd_s4()
    elif cmd == "latency":
        cmd_latency()
    elif cmd == "selftest":
        cmd_selftest()
    else:
        sys.exit(f"알 수 없는 명령 {cmd}")
