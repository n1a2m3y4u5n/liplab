"""끝 무음 증강 재학습 정렬기·채점기 측정(파드, docs/dgop-aligner-tailaug-2026-10.md 4~5절). 모델은 모두 배포와 같은 int8 파일.

    python measure.py main   ROOT OUT.jsonl [--shard i/n] [--limit N]   538·608: 짝(K0·A·B) × 끝 자르기(n·t) × 소리(R·T) × 목표 문장
    python measure.py tts    ROOT OUT.jsonl [--shard i/n] [--limit N]   서버 음성 문장 클립(같은 변형)
    python measure.py hyp    ROOT OUT.jsonl [--shard i/n]               탐욕 복호 끝 출력 위치(538 R·T·Z, 정렬기·채점기 넷)
    python measure.py zeroth ROOT OUT.jsonl [--n-test 300 --n-train 600]  Zeroth에서 끝 출력 위치(새 정렬기·채점기)
    python measure.py mfaprep ROOT DIR                                   MFA 말뭉치(538 자기 문장, 서버 음성)
    python measure.py mfaparse ROOT DIR OUT.jsonl                        MFA TextGrid → 모음 시작 시각
    python measure.py latency ROOT OUT.json                              CPU 2스레드 채점 지연(배포와 같은 phone_confidences)
    python measure.py selftest ROOT                                      재구현이 dgop_acoustic.phone_confidences와 같은지

ROOT: backend/(이 브랜치 코드, models/dgop_ours = 지금 int8), models/ta/{aligner,scorer}(새 int8), data/jobs.jsonl·tts_jobs.jsonl,
data/c538wav, data/hi608/wav16, data/tts/*.ogg. 줄마다 결과 JSON. 이미 적은 (clip, variant)는 건너뛴다. 끝 표식 MEASURE_OK.
"""
import argparse
import glob
import hashlib
import json
import math
import os
import re
import statistics
import sys
import time
import zlib

import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("part")
ap.add_argument("root")
ap.add_argument("out", nargs="?")
ap.add_argument("out2", nargs="?")
ap.add_argument("--shard", default="0/1")
ap.add_argument("--limit", type=int, default=0)
ap.add_argument("--n-test", type=int, default=300)
ap.add_argument("--n-train", type=int, default=600)
ap.add_argument("--threads", type=int, default=2)
ap.add_argument("--pair", default="K0", help="latency: 측정할 짝(짝마다 따로 띄운다. 한 프로세스에서 두 짝을 올리면 특징 추출부 공유가 앞 짝에 묶인다)")
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
AL0 = os.path.join(BK, "models", "dgop_ours", "aligner")
SC0 = os.path.join(BK, "models", "dgop_ours", "scorer")
AL1 = os.path.join(ROOT, "models", "ta", "aligner")
SC1 = os.path.join(ROOT, "models", "ta", "scorer")
CAL = DA.load_calibration(os.path.join(BK, "data", "dgop_calibration_ours.json"))
TAIL_S = 1.0          # 앱 녹음처럼 끝에 붙이는 소리 길이(10/7 T 조건과 같다)
MAX_S = 30            # assess_text와 같이 앞 30초만


def _have(d):
    return os.path.exists(os.path.join(d, "model.int8.safetensors"))


PAIRS = {"K0": (AL0, SC0)}
if _have(AL1):
    PAIRS["A"] = (AL1, SC0)
    if _have(SC1):
        PAIRS["B"] = (AL1, SC1)


# ───────── 신호 ─────────
def win_db(y, win=0.01):
    n = int(SR * win)
    m = len(y) // n
    if m < 1:
        return np.zeros(0)
    r = np.sqrt(np.mean(np.asarray(y[:m * n], dtype=np.float64).reshape(m, n) ** 2, 1) + 1e-12)
    return 20 * np.log10(r)


def speech_end(y):
    return DA.speech_end_seconds(y, SR)


def room_tail(y, key, secs=TAIL_S):
    """끝에 붙일 소리: 그 클립 10 ms 창 RMS 10백분위 수준의 가우스 잡음(시드는 클립 이름). 10/7 측정과 같다."""
    db = win_db(y)
    rms = max(10 ** (np.percentile(db, 10) / 20.0), 1e-4) if len(db) else 1e-4
    rng = np.random.default_rng(zlib.crc32(key.encode()))
    return (rng.standard_normal(int(SR * secs)) * rms).astype(np.float32)


def trim(y):
    """앱과 같은 끝 자르기(dgop_acoustic.trim_trailing_silence, 말소리 끝 + 50 ms)."""
    old = os.environ.get("DGOP_TAIL_TRIM")
    os.environ["DGOP_TAIL_TRIM"] = "1"
    try:
        return DA.trim_trailing_silence(y, SR)
    finally:
        if old is None:
            os.environ.pop("DGOP_TAIL_TRIM", None)
        else:
            os.environ["DGOP_TAIL_TRIM"] = old


# ───────── 모델 ─────────
_memo = {}


def outputs(y, model_id):
    key = (model_id, hashlib.sha1(np.ascontiguousarray(y, dtype=np.float32).tobytes()).hexdigest())
    if key not in _memo:
        if len(_memo) > 96:
            _memo.clear()
        _memo[key] = DA.ctc_outputs(np.asarray(y, dtype=np.float32), SR, model_id)
    return _memo[key]


def phones_for(y_in, tokens, al, sc):
    """dgop_acoustic.phone_confidences(끝 자르기 뒤)와 같은 계산. 자르기는 부르는 쪽이 이미 한 소리를 넣는다."""
    lp, _, vocab = outputs(y_in, al)
    slp, _, svocab = outputs(y_in, sc)
    n_frames = int(lp.shape[0])
    spf = (len(y_in) / float(SR)) / n_frames
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
    return y.astype(np.float32)[:SR * MAX_S]


def variants(y, key):
    """(이름, 짝, 정렬기에 넣는 소리, 앱이 받은 녹음(빠르기 계산용)). 이름 = 짝_자르기_소리(예: A_n_T)."""
    yT = np.concatenate([y, room_tail(y, key)])[:SR * MAX_S]
    out = []
    for cond, base in (("R", y), ("T", yT)):
        ins = {"n": base, "t": trim(base)}
        for pair in PAIRS:
            for tr in ("n", "t"):
                out.append((f"{pair}_{tr}_{cond}", pair, ins[tr], base))
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
        for vname, pair, y_in, y_rec in variants(y, key):
            if (j["clip"], vname) in done:
                continue
            al, sc = PAIRS[pair]
            row = {"set": j["set"], "clip": j["clip"], "spk": j["spk"], "half": j["half"], "variant": vname,
                   "dur": round(len(y_rec) / SR, 3), "dur_in": round(len(y_in) / SR, 3), "dur_raw": round(len(y) / SR, 3),
                   "speech_end": speech_end(y_rec), "speech_end_raw": speech_end(y), "targets": []}
            try:
                for t in j["targets"]:
                    toks = JV.text_to_tokens(t["target"])
                    ph, nf, spf = phones_for(y_in, toks, al, sc)
                    raw, score = sentence(ph, t["target"])
                    rp = speak_cues.rate_pause(y_rec, ph, SR)
                    row["targets"].append({"kind": t["kind"], "target": t["target"], "raw": raw, "score": score,
                                           "rate": rp, "phones": slim(ph)})
                row["n_frames"] = nf
            except Exception as e:
                row["err"] = f"{type(e).__name__}: {e}"
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
    print("MEASURE_OK main", len(jobs), flush=True)


def run_tts():
    jobs = shard(load_jobs("tts_jobs.jsonl"))
    done = done_keys(a.out)
    out = open(a.out, "a")
    for j in jobs:
        y = read_audio(j)
        key = f"tts:{j['clip']}"
        toks = JV.text_to_tokens(j["target"])
        for vname, pair, y_in, y_rec in variants(y, key):
            if (j["clip"], vname) in done:
                continue
            al, sc = PAIRS[pair]
            row = {"set": "tts", "clip": j["clip"], "voice": j["voice"], "variant": vname, "dur": round(len(y_rec) / SR, 3),
                   "dur_in": round(len(y_in) / SR, 3), "dur_raw": round(len(y) / SR, 3),
                   "speech_end": speech_end(y_rec), "speech_end_raw": speech_end(y), "target": j["target"]}
            try:
                ph, nf, spf = phones_for(y_in, toks, al, sc)
                raw, score = sentence(ph, j["target"])
                row.update({"raw": raw, "score": score, "phones": slim(ph), "rate": speak_cues.rate_pause(y_rec, ph, SR)})
            except Exception as e:
                row["err"] = f"{type(e).__name__}: {e}"
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
    print("MEASURE_OK tts", len(jobs), flush=True)


def greedy(lg, blank):
    am = lg.argmax(-1).tolist()
    res, prev = [], None
    for t, x in enumerate(am):
        if x != prev and x != blank:
            res.append((x, t))
        prev = x
    return res


def hyp_models():
    ms = {"al0": AL0, "sc0": SC0}
    if _have(AL1):
        ms["al1"] = AL1
    if _have(SC1):
        ms["sc1"] = SC1
    return ms


def run_hyp():
    jobs = shard([j for j in load_jobs("jobs.jsonl") if j["set"] == "538"])
    ms = hyp_models()
    out = open(a.out, "a")
    for j in jobs:
        y = read_audio(j)
        own = next(t["target"] for t in j["targets"] if t["kind"] == "same")
        yT = np.concatenate([y, room_tail(y, f"{j['set']}:{j['clip']}")])
        yZ = np.concatenate([y, np.zeros(int(SR * TAIL_S), np.float32)])
        se = speech_end(y)
        toks = JV.text_to_tokens(own)
        last = toks[-1]
        for vname, yy in (("R", y), ("T", yT), ("Z", yZ)):
            for w, mid in ms.items():
                lp, lg, vocab = outputs(yy, mid)
                inv = {v: k for k, v in vocab.items()}
                g = greedy(lg, DA.blank_id_for(vocab))
                n = int(lg.shape[0])
                spf = len(yy) / SR / n
                fr = [t for x, t in g if inv.get(x) == last]
                row = {"clip": j["clip"], "half": j["half"], "variant": vname, "model": w, "n_frames": n, "spf": spf,
                       "speech_end": se, "dur_raw": len(y) / SR, "last_tok": last, "last_frames": fr[-3:],
                       "greedy_tail": [[inv.get(x), t] for x, t in g[-4:]]}
                try:
                    spans = DA.align_targets(lp, vocab, toks)
                    row["final_t0"] = spans[-1]["start"] * spf
                    pr = torch.softmax(lg, -1)[:, vocab[last]].numpy()
                    e = int((se or len(y) / SR) / spf)
                    row["pmax_in_speech"] = float(pr[:max(1, e)].max())
                except Exception as ex:
                    row["err"] = f"{type(ex).__name__}: {ex}"
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                out.flush()
    print("MEASURE_OK hyp", len(jobs), flush=True)


def run_zeroth():
    from datasets import load_dataset, Audio
    import hf_audio
    ms = {k: v for k, v in hyp_models().items() if k != "al0"}
    out = open(a.out, "a")
    for split, n in (("test", a.n_test), ("train", a.n_train)):
        ds = load_dataset("kresnik/zeroth_korean", split=split).cast_column("audio", Audio(sampling_rate=SR))
        for k in range(min(n, len(ds))):
            ex = ds[k]
            y = np.asarray(hf_audio.to_waveform(ex["audio"]), dtype=np.float32)
            toks = JV.text_to_tokens(ex["text"])
            if not toks:
                continue
            se = speech_end(y)
            row = {"split": split, "i": k, "dur": len(y) / SR, "speech_end": se, "last_tok": toks[-1]}
            try:
                for w, mid in ms.items():
                    for vname, yy in (("R", y), ("T", np.concatenate([y, room_tail(y, f"z{split}{k}")]))):
                        lp, lg, vocab = outputs(yy, mid)
                        nfr = int(lg.shape[0])
                        spf = len(yy) / SR / nfr
                        inv = {v: kk for kk, v in vocab.items()}
                        g = greedy(lg, DA.blank_id_for(vocab))
                        fr = [t for x, t in g if inv.get(x) == toks[-1]]
                        spans = DA.align_targets(lp, vocab, toks)
                        row[f"{w}_{vname}"] = {"n_frames": nfr, "spf": spf, "last_frames": fr[-3:],
                                               "final_t0": spans[-1]["start"] * spf}
            except Exception as e:
                row["err"] = f"{type(e).__name__}: {e}"
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
    print("MEASURE_OK zeroth", flush=True)


# ───────── MFA(독립 참조) ─────────
def mfa_text(t):
    if re.search(r"[0-9A-Za-z]", t or ""):
        return None
    s = DA.normalize_syllable_text(t)
    return s or None


def run_mfaprep():
    d = os.path.abspath(a.out)
    os.makedirs(d, exist_ok=True)
    ids = {}
    n = 0
    for j in load_jobs("jobs.jsonl"):
        if j["set"] != "538":
            continue
        own = next(t["target"] for t in j["targets"] if t["kind"] == "same")
        txt = mfa_text(own)
        if not txt:
            continue
        uid = f"c{n:05d}"
        n += 1
        sd = os.path.join(d, "corpus", "s538_" + re.sub(r"[^A-Za-z0-9]", "_", j["spk"]))
        os.makedirs(sd, exist_ok=True)
        sf.write(os.path.join(sd, uid + ".wav"), read_audio(j), SR, subtype="PCM_16")
        open(os.path.join(sd, uid + ".lab"), "w", encoding="utf-8").write(txt + "\n")
        ids[uid] = {"key": f"538:{j['clip']}", "text": own}
    for j in load_jobs("tts_jobs.jsonl"):
        txt = mfa_text(j["target"])
        if not txt:
            continue
        uid = f"t{n:05d}"
        n += 1
        sd = os.path.join(d, "corpus", "tts_" + j["voice"])
        os.makedirs(sd, exist_ok=True)
        sf.write(os.path.join(sd, uid + ".wav"), read_audio(j), SR, subtype="PCM_16")
        open(os.path.join(sd, uid + ".lab"), "w", encoding="utf-8").write(txt + "\n")
        ids[uid] = {"key": f"tts:{j['clip']}", "text": j["target"]}
    json.dump(ids, open(os.path.join(d, "ids.json"), "w"), ensure_ascii=False)
    print("MFAPREP_OK", len(ids), flush=True)


_VOW = set("aeiouɛɯʌøyɐɨəɤæɑɔɪʊ")
SIL = {"", "sil", "sp", "spn", "<eps>", "silence", "noise"}
GLIDES = {"j", "w", "ɥ", "ɰ"}


def is_vowel(ph):
    p = re.sub(r"[ːˑ̃ˈˌ]", "", ph.strip())
    while p[:1] in ("j", "w", "ɰ") and len(p) > 1:
        p = p[1:]
    return p[:1] in _VOW


def parse_textgrid(path):
    """긴 형식 TextGrid의 phones 계층 → [(label, xmin, xmax)]."""
    lines = open(path, encoding="utf-8").read().splitlines()
    tiers, cur, iv = {}, None, None
    for ln in lines:
        s = ln.strip()
        m = re.match(r'name = "(.*)"', s)
        if m:
            cur = m.group(1)
            tiers[cur] = []
            continue
        m = re.match(r"xmin = ([0-9.eE+-]+)", s)
        if m and cur is not None:
            iv = [float(m.group(1)), None, None]
            continue
        m = re.match(r"xmax = ([0-9.eE+-]+)", s)
        if m and iv is not None and iv[1] is None:
            iv[1] = float(m.group(1))
            continue
        m = re.match(r'text = "(.*)"', s)
        if m and iv is not None and cur is not None:
            tiers[cur].append((m.group(1), iv[0], iv[1]))
            iv = None
    for name in tiers:
        if "phone" in name.lower():
            return tiers[name]
    return None


def run_mfaparse():
    d = os.path.abspath(a.out)
    ids = json.load(open(os.path.join(d, "ids.json"), encoding="utf-8"))
    out = open(a.out2, "w")
    ok = 0
    for uid, info in ids.items():
        f = glob.glob(os.path.join(d, "aligned", "*", uid + ".TextGrid")) + glob.glob(os.path.join(d, "aligned", uid + ".TextGrid"))
        row = {"uid": uid, **info, "ok": False}
        if f:
            ph = parse_textgrid(f[0]) or []
            ph = [p for p in ph if p[0].strip().lower() not in SIL]
            # korean_mfa는 활음을 따로 낸다('요' = j o). 우리 중성 토큰(ㅛ)은 활음을 포함하므로, 모음 바로 앞이 활음이면
            # 그 활음 시작을 모음 시작으로 둔다(사후 변경 1, 결과를 보기 전).
            vow = []
            for k, p in enumerate(ph):
                if is_vowel(p[0]):
                    t0 = ph[k - 1][1] if k > 0 and ph[k - 1][0].strip() in GLIDES else p[1]
                    vow.append([p[0], round(t0, 4), round(p[2], 4)])
            if ph and vow:
                row.update(ok=True, vowels=vow, n_vowel=len(vow), final_vowel_t0=vow[-1][1], speech_t1=ph[-1][2],
                           phones=[[p[0], round(p[1], 4), round(p[2], 4)] for p in ph])
                ok += 1
        out.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("MFAPARSE_OK", ok, "/", len(ids), flush=True)


# ───────── 지연 ─────────
def run_latency():
    assert os.environ.get("DGOP_DEVICE") == "cpu"
    jobs = [j for j in load_jobs("jobs.jsonl") if j["set"] == "538"][:6]
    al, sc = PAIRS[a.pair]
    res = {"pair": a.pair, "threads": torch.get_num_threads(),
           "bytes": {k: os.path.getsize(os.path.join(p, "model.int8.safetensors")) for k, p in (("aligner", al), ("scorer", sc))}}
    for tr in ("t", "n"):
        os.environ["DGOP_TAIL_TRIM"] = "1" if tr == "t" else "0"
        times = []
        for rep in range(4):
            for j in jobs:
                y = read_audio(j)
                yT = np.concatenate([y, room_tail(y, f"538:{j['clip']}")])
                toks = JV.text_to_tokens(next(t["target"] for t in j["targets"] if t["kind"] == "same"))
                t0 = time.perf_counter()
                DA.phone_confidences(yT, SR, toks, aligner_id=al, scorer_id=sc)
                if rep > 0:                          # 첫 바퀴는 적재·데우기라 뺀다
                    times.append(time.perf_counter() - t0)
        res[tr] = {"median_s": statistics.median(times), "mean_s": statistics.mean(times), "n": len(times)}
    _, am = DA._load(al, device="cpu")
    _, sm = DA._load(sc, device="cpu")
    res["shared_feature_encoder"] = bool(isinstance(am.wav2vec2.feature_extractor, DA.SharedFeatureEncoder)
                                         and am.wav2vec2.feature_extractor is sm.wav2vec2.feature_extractor)
    try:
        import resource
        res["maxrss_mb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    except Exception:
        pass
    print(res, flush=True)
    json.dump(res, open(a.out, "w"), indent=1)
    print("MEASURE_OK latency", flush=True)


def selftest():
    j = load_jobs("jobs.jsonl")[0]
    y = read_audio(j)
    yT = np.concatenate([y, room_tail(y, "x")])
    toks = JV.text_to_tokens(j["targets"][0]["target"])
    n = 0
    for pair, (al, sc) in PAIRS.items():
        for tr in ("n", "t"):
            os.environ["DGOP_TAIL_TRIM"] = "0" if tr == "n" else "1"
            ref = DA.phone_confidences(yT, SR, toks, aligner_id=al, scorer_id=sc)
            mine, _, _ = phones_for(yT if tr == "n" else trim(yT), toks, al, sc)
            for p, q in zip(mine, ref):
                assert p["token"] == q["token"] and abs(p["t0"] - q["t0"]) < 1e-6 and abs(p["naive"] - q["naive"]) < 1e-6, (pair, tr, p, q)
            n += 1
    os.environ.pop("DGOP_TAIL_TRIM", None)
    print("SELFTEST_OK", n, list(PAIRS), [v[0] for v in variants(y, "x")], flush=True)


{"main": run_main, "tts": run_tts, "hyp": run_hyp, "zeroth": run_zeroth, "mfaprep": run_mfaprep,
 "mfaparse": run_mfaparse, "latency": run_latency, "selftest": selftest}[a.part]()
