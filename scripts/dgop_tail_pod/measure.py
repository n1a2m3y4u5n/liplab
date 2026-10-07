"""문장 끝 모음 정렬 결함 측정(파드, docs/dgop-final-vowel-2026-10.md 4~5절). 정렬기·채점기는 배포와 같은 int8 파일.

    python measure.py main  ROOT OUT.jsonl [--shard i/n] [--limit N] [--dump DIR]   538·608 채점(소리 조건 × 방법 × 목표)
    python measure.py tts   ROOT OUT.jsonl [--shard i/n] [--limit N]                 서버 음성 문장 클립 정렬 시각
    python measure.py hyp   ROOT OUT.jsonl [--shard i/n] [--limit N] [--which int8,fp32,kresnik]   원인 가설(탐욕 복호 끝 출력 위치)
    python measure.py zeroth ROOT OUT.jsonl [--n-test 500 --n-train 1000]           학습 자료(Zeroth)의 끝 무음·끝 출력 위치
    python measure.py selftest ROOT                                                  재구현이 dgop_acoustic.phone_confidences와 같은지

ROOT: backend/(이 브랜치 코드, models/dgop_ours int8), data/jobs.jsonl·tts_jobs.jsonl, data/c538wav, data/hi608/wav16, data/tts/*.ogg,
models/aligner_fp32(가설용). 줄마다 결과 JSON. 이미 적은 (clip, variant)는 건너뛴다. 끝 표식 MEASURE_OK.
"""
import argparse
import hashlib
import json
import math
import os
import sys
import zlib

import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("part")
ap.add_argument("root")
ap.add_argument("out", nargs="?")
ap.add_argument("--shard", default="0/1")
ap.add_argument("--limit", type=int, default=0)
ap.add_argument("--dump", default="")
ap.add_argument("--which", default="int8,fp32,kresnik")
ap.add_argument("--n-test", type=int, default=500)
ap.add_argument("--n-train", type=int, default=1000)
ap.add_argument("--threads", type=int, default=2)
a = ap.parse_args()

ROOT = os.path.abspath(a.root)
BK = os.path.join(ROOT, "backend")
sys.path.insert(0, BK)
os.environ.setdefault("BACKBONE_QUANT", "int8")
os.environ.setdefault("OMP_NUM_THREADS", str(a.threads))
import torch  # noqa: E402

torch.set_num_threads(a.threads)
torch.set_grad_enabled(False)
if os.environ.get("DGOP_DEVICE") == "cuda":
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
import soundfile as sf  # noqa: E402
import dgop as G  # noqa: E402
import dgop_acoustic as DA  # noqa: E402
import jamo_vocab as JV  # noqa: E402
import speak_cues  # noqa: E402

SR = 16000
AL = os.path.join(BK, "models", "dgop_ours", "aligner")
SC = os.path.join(BK, "models", "dgop_ours", "scorer")
CAL = DA.load_calibration(os.path.join(BK, "data", "dgop_calibration_ours.json"))
TAIL_S = 1.0          # 앱 녹음처럼 끝에 붙이는 소리 길이
PAD_S = 0.2           # 방법 M1(끝에 무음 덧붙이기)
MARGINS = (0, 50, 150)
CON_MS = 50           # 방법 M3(구간 제약) 여유


# ───────── 신호 ─────────
def win_db(y, win=0.01):
    n = int(SR * win)
    m = len(y) // n
    if m < 1:
        return np.zeros(0)
    r = np.sqrt(np.mean(np.asarray(y[:m * n], dtype=np.float64).reshape(m, n) ** 2, 1) + 1e-12)
    return 20 * np.log10(r)


def speech_end(y):
    """10 ms 창 RMS(dB)가 max(99백분위 − 35, 10백분위 + 6)를 넘는 마지막 창의 끝(초). 넘는 창이 없으면 None."""
    db = win_db(y)
    if len(db) < 3:
        return None
    thr = max(np.percentile(db, 99) - 35.0, np.percentile(db, 10) + 6.0)
    idx = np.where(db > thr)[0]
    return None if not len(idx) else (idx[-1] + 1) * 0.01


def room_tail(y, key, secs=TAIL_S):
    """끝에 붙일 소리: 그 클립 10 ms 창 RMS 10백분위 수준의 가우스 잡음(시드는 클립 이름)."""
    db = win_db(y)
    rms = max(10 ** (np.percentile(db, 10) / 20.0), 1e-4) if len(db) else 1e-4
    rng = np.random.default_rng(zlib.crc32(key.encode()))
    return (rng.standard_normal(int(SR * secs)) * rms).astype(np.float32)


# ───────── 모델 ─────────
_memo = {}


def outputs(y, model_id):
    key = (model_id, hashlib.sha1(np.ascontiguousarray(y, dtype=np.float32).tobytes()).hexdigest())
    if key not in _memo:
        if len(_memo) > 64:
            _memo.clear()
        lp, lg, vocab = DA.ctc_outputs(np.asarray(y, dtype=np.float32), SR, model_id)
        _memo[key] = (lp, lg, vocab)
    return _memo[key]


def phones_for(y_in, tokens, con_end_s=None):
    """dgop_acoustic.phone_confidences와 같은 계산. con_end_s가 있으면 그 시각 뒤 프레임을 정렬·채점에서 뺀다(방법 M3)."""
    lp, _, vocab = outputs(y_in, AL)
    slp, _, svocab = outputs(y_in, SC)
    n_frames = int(lp.shape[0])
    spf = (len(y_in) / float(SR)) / n_frames
    if con_end_s is not None:
        E = max(1, min(n_frames, int(math.ceil(con_end_s / spf))))
        lp, slp = lp[:E], slp[:E]
    spans = DA.align_targets(lp, vocab, tokens)
    out = []
    for sp in spans:
        tok = sp["token"]
        dist = DA.span_distribution(slp, sp["start"], sp["end"])
        tp = dist[svocab[tok]]
        r = G.dgop_phone(tp, dist)
        out.append({"token": tok, "aligned": True, "scorable": DA._is_scorable(tok),
                    "t0": round(sp["start"] * spf, 3), "t1": round((sp["end"] + 1) * spf, 3),
                    "naive": r["naive"], "confidence": r["confidence"], "dgop": r["dgop"], "uncertainty": r["uncertainty"]})
    return out, n_frames, spf


def sentence(phones, target):
    for i in JV.silent_linking_h(target):
        if i < len(phones):
            phones[i]["silent_h"] = True
    sc = [p for p in phones if p.get("aligned") and p.get("scorable")]
    raw = G.sentence_dgop(sc)["score"]
    return raw, G.calibrate_score(raw, CAL)


def slim(ph):
    return [[p["token"], p["t0"], p["t1"], p["naive"], 1 if p.get("silent_h") else 0] for p in ph]


def read_audio(job):
    if job["set"] == "538":
        y, sr = sf.read(os.path.join(ROOT, "data", "c538wav", job["clip"] + ".wav"), dtype="float32")
    elif job["set"] == "608":
        y, sr = sf.read(os.path.join(ROOT, "data", "hi608", "wav16", job["file"]), dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        y = y[int(job["start"] * sr):int(job["end"] * sr)]
    else:
        f = os.path.join(ROOT, "data", "tts", job["file"])
        try:
            from faster_whisper.audio import decode_audio
            return decode_audio(f, sampling_rate=SR).astype(np.float32)
        except ImportError:          # 맥 점검용(faster-whisper 없는 가상환경)
            from scipy.signal import resample_poly
            y, sr = sf.read(f, dtype="float32")
            return resample_poly(y, SR, sr).astype(np.float32)
    assert sr == SR, sr
    return y.astype(np.float32)


def variants(y, key, with_pad=True):
    """(이름, 정렬기에 넣는 소리, 앱이 받은 녹음(빠르기 계산용), 구간 제약 끝 초) 목록."""
    yT = np.concatenate([y, room_tail(y, key)])
    out = [("R", y, y, None), ("T", yT, yT, None)]
    if with_pad:
        z = np.zeros(int(SR * PAD_S), np.float32)
        out += [("Rp", np.concatenate([y, z]), y, None), ("Tp", np.concatenate([yT, z]), yT, None)]
    for nm, base in (("R", y), ("T", yT)):
        e = speech_end(base)
        for m in MARGINS:
            if e is None:
                out.append((f"{nm}_trim{m}", base, base, None))
            else:
                cut = min(len(base), int(round((e + m / 1000.0) * SR)))
                out.append((f"{nm}_trim{m}", base[:max(cut, int(0.1 * SR))], base, None))
        if with_pad:
            out.append((f"{nm}_con{CON_MS}", base, base, None if e is None else e + CON_MS / 1000.0))
    return out


def shard(items):
    i, n = map(int, a.shard.split("/"))
    items = items[i::n]
    return items[:a.limit] if a.limit else items


def done_keys(path):
    s = set()
    if path and os.path.exists(path):
        for l in open(path):
            try:
                r = json.loads(l)
                s.add((r["clip"], r.get("variant", "")))
            except Exception:
                pass
    return s


def load_jobs(name):
    return [json.loads(l) for l in open(os.path.join(ROOT, "data", name), encoding="utf-8") if l.strip()]


# ───────── 부분 ─────────
def run_main():
    jobs = shard(load_jobs("jobs.jsonl"))
    done = done_keys(a.out)
    out = open(a.out, "a")
    for j in jobs:
        y = read_audio(j)
        key = f"{j['set']}:{j['clip']}"
        for vname, y_in, y_rec, con in variants(y, key):
            if (j["clip"], vname) in done:
                continue
            row = {"set": j["set"], "clip": j["clip"], "spk": j["spk"], "half": j["half"], "variant": vname,
                   "dur": round(len(y_rec) / SR, 3), "dur_in": round(len(y_in) / SR, 3), "dur_raw": round(len(y) / SR, 3),
                   "speech_end": speech_end(y_rec), "speech_end_raw": speech_end(y), "targets": []}
            try:
                for t in j["targets"]:
                    toks = JV.text_to_tokens(t["target"])
                    ph, nf, spf = phones_for(y_in, toks, con)
                    raw, score = sentence(ph, t["target"])
                    rp = speak_cues.rate_pause(y_rec, ph, SR)
                    row["targets"].append({"kind": t["kind"], "target": t["target"], "raw": raw, "score": score,
                                           "rate": rp, "phones": slim(ph)})
                row["n_frames"] = nf
            except Exception as e:
                row["err"] = f"{type(e).__name__}: {e}"
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
            if a.dump and vname in ("R", "T"):
                os.makedirs(a.dump, exist_ok=True)
                np.savez_compressed(os.path.join(a.dump, f"{j['set']}_{j['clip'].replace(':', '__')}_{vname}.npz"),
                                    al=outputs(y_in, AL)[1].numpy().astype(np.float16),
                                    sc=outputs(y_in, SC)[1].numpy().astype(np.float16))
    print("MEASURE_OK main", len(jobs), flush=True)


def run_tts():
    jobs = shard(load_jobs("tts_jobs.jsonl"))
    done = done_keys(a.out)
    out = open(a.out, "a")
    for j in jobs:
        y = read_audio(j)
        key = f"tts:{j['clip']}"
        toks = JV.text_to_tokens(j["target"])
        for vname, y_in, y_rec, con in variants(y, key, with_pad=False):
            if (j["clip"], vname) in done:
                continue
            row = {"set": "tts", "clip": j["clip"], "voice": j["voice"], "variant": vname, "dur": round(len(y_rec) / SR, 3),
                   "dur_in": round(len(y_in) / SR, 3), "dur_raw": round(len(y) / SR, 3),
                   "speech_end": speech_end(y_rec), "speech_end_raw": speech_end(y), "target": j["target"]}
            try:
                ph, nf, spf = phones_for(y_in, toks, con)
                raw, score = sentence(ph, j["target"])
                row.update({"raw": raw, "score": score, "phones": slim(ph), "rate": speak_cues.rate_pause(y_rec, ph, SR)})
            except Exception as e:
                row["err"] = f"{type(e).__name__}: {e}"
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
    print("MEASURE_OK tts", len(jobs), flush=True)


def greedy_last(lg, blank):
    """탐욕 복호의 출력 (토큰 id, 프레임) 목록."""
    am = lg.argmax(-1).tolist()
    res, prev = [], None
    for t, x in enumerate(am):
        if x != prev and x != blank:
            res.append((x, t))
        prev = x
    return res


def hyp_models():
    ms = {}
    for w in a.which.split(","):
        if w == "int8":
            ms[w] = AL
        elif w == "fp32":
            ms[w] = os.path.join(ROOT, "models", "aligner_fp32")
        elif w == "kresnik":
            ms[w] = DA.DEFAULT_MODEL_ID
    return ms


def run_hyp():
    jobs = [j for j in load_jobs("jobs.jsonl") if j["set"] == "538"]
    jobs = shard(jobs)
    ms = hyp_models()
    out = open(a.out, "a")
    for j in jobs:
        y = read_audio(j)
        own = next(t["target"] for t in j["targets"] if t["kind"] == "same")
        yT = np.concatenate([y, room_tail(y, f"{j['set']}:{j['clip']}")])
        yZ = np.concatenate([y, np.zeros(int(SR * TAIL_S), np.float32)])
        se = speech_end(y)
        for vname, yy in (("R", y), ("T", yT), ("Z", yZ)):
            for w, mid in ms.items():
                lp, lg, vocab = outputs(yy, mid)
                inv = {v: k for k, v in vocab.items()}
                blank = DA.blank_id_for(vocab)
                g = greedy_last(lg, blank)
                n = int(lg.shape[0])
                spf = len(yy) / SR / n
                if w == "kresnik":
                    toks = DA.tokens_for_text(own, model_id=mid)
                else:
                    toks = JV.text_to_tokens(own)
                last = toks[-1]
                # 마지막 목표 토큰이 탐욕 출력에 나온 마지막 프레임
                fr = [t for x, t in g if inv.get(x) == last]
                row = {"clip": j["clip"], "variant": vname, "model": w, "n_frames": n, "spf": spf, "speech_end": se,
                       "dur_raw": len(y) / SR, "last_tok": last, "greedy_tail": [[inv.get(x), t] for x, t in g[-4:]],
                       "last_frames": fr[-3:]}
                try:
                    spans = DA.align_targets(lp, vocab, toks)
                    row["final_t0"] = spans[-1]["start"] * spf
                    row["prev_t1"] = (spans[-2]["end"] + 1) * spf if len(spans) > 1 else None
                    pr = torch.softmax(lg, -1)[:, vocab[last]].numpy()
                    e = int((se or len(y) / SR) / spf)
                    row["pmax_in_speech"] = float(pr[:max(1, e)].max())
                    row["pmax_after"] = float(pr[max(0, e + 3):].max()) if e + 3 < n else 0.0
                except Exception as ex:
                    row["err"] = f"{type(ex).__name__}: {ex}"
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                out.flush()
    print("MEASURE_OK hyp", len(jobs), flush=True)


def run_zeroth():
    from datasets import load_dataset, Audio
    out = open(a.out, "a")
    blank = JV.VOCAB["<pad>"]
    for split, n in (("test", a.n_test), ("train", a.n_train)):
        ds = load_dataset("kresnik/zeroth_korean", split=split, streaming=True)
        ds = ds.cast_column("audio", Audio(sampling_rate=SR))
        k = 0
        for ex in ds:
            if k >= n:
                break
            k += 1
            import hf_audio
            y = np.asarray(hf_audio.to_waveform(ex["audio"]), dtype=np.float32)
            text = ex["text"]
            toks = JV.text_to_tokens(text)
            if not toks:
                continue
            se = speech_end(y)
            row = {"split": split, "i": k, "dur": len(y) / SR, "speech_end": se, "last_char": (text.strip() or " ")[-1],
                   "last_tok": toks[-1]}
            try:
                for vname, yy in (("R", y), ("T", np.concatenate([y, room_tail(y, f"z{split}{k}")]))):
                    lp, lg, vocab = outputs(yy, AL)
                    nfr = int(lg.shape[0])
                    spf = len(yy) / SR / nfr
                    g = greedy_last(lg, blank)
                    fr = [t for x, t in g if JV.ID_TO_TOKEN[x] == toks[-1]]
                    spans = DA.align_targets(lp, vocab, toks)
                    row[vname] = {"n_frames": nfr, "spf": spf, "last_frames": fr[-3:], "final_t0": spans[-1]["start"] * spf,
                                  "greedy_last": [JV.ID_TO_TOKEN[x] for x, _ in g[-3:]]}
            except Exception as e:
                row["err"] = f"{type(e).__name__}: {e}"
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
    print("MEASURE_OK zeroth", flush=True)


def selftest():
    j = load_jobs("jobs.jsonl")[0]
    y = read_audio(j)
    t = j["targets"][0]["target"]
    toks = JV.text_to_tokens(t)
    mine, _, _ = phones_for(y, toks)
    ref = DA.phone_confidences(y, SR, toks, aligner_id=AL, scorer_id=SC)
    for p, q in zip(mine, ref):
        assert p["token"] == q["token"] and abs(p["t0"] - q["t0"]) < 1e-6 and abs(p["naive"] - q["naive"]) < 1e-6, (p, q)
    print("SELFTEST_OK", len(mine), speech_end(y), [v[0] for v in variants(y, "x")], flush=True)


{"main": run_main, "tts": run_tts, "hyp": run_hyp, "zeroth": run_zeroth}.get(a.part, lambda: None)() if a.part != "selftest" else selftest()
