"""끝 구간 다시 나누기 확인 측정(파드, docs/dgop-final-vowel-fix2-2026-10.md 4~5절). 모델은 배포와 같은 int8 파일.

    python measure.py main    ROOT OUT.jsonl [--shard i/n] [--limit N]   538n·608n: 끝 자르기(n·t) × 소리(R·T) × 시각(K0·N1a·N1l)
    python measure.py tts     ROOT OUT.jsonl [--shard i/n]               서버 음성 문장 클립(같은 변형)
    python measure.py deg     ROOT OUT.jsonl [--shard i/n]               538n 자기 문장, 합성 저하 clean·mild·mod·sev × 끝 자르기(n·t)
    python measure.py mfaprep ROOT DIR                                   MFA 말뭉치(538n 자기 문장, 서버 음성)
    python measure.py mfaparse ROOT DIR OUT.jsonl                        MFA TextGrid → 끝 모음 시작
    python measure.py cpu     ROOT OUT.json GPU_MAIN_GLOB                CPU 2스레드 지연과 CPU·GPU 경로 일치(앱 phone_confidences 그대로)
    python measure.py selftest ROOT                                      앱 phone_confidences(환경변수 설정별)를 그대로 부르는지 확인

모든 채점·시각은 앱 함수 dgop_acoustic.phone_confidences를 환경변수(DGOP_TAIL_TRIM, DGOP_TAIL_RESEG)와 TAIL_RESEG_GATE만 바꿔 부른다.
순전파는 같은 입력이면 다시 쓰도록 ctc_outputs만 메모한다(결과는 같다). N1 변형은 자기 문장만 계산한다(다른 문장의 점수는 시각과
무관해 K0와 같다). ROOT: backend/(이 브랜치 코드, models/dgop_ours = 지금 int8), data/jobs.jsonl·tts_jobs.jsonl·wav·tts, tools/make_deaf_corpus.py.
"""
import argparse
import glob
import hashlib
import json
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
ap.add_argument("--threads", type=int, default=2)
a = ap.parse_args()

ROOT = os.path.abspath(a.root)
BK = os.path.join(ROOT, "backend")
sys.path.insert(0, BK)
sys.path.insert(0, os.path.join(ROOT, "tools"))
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
TAIL_S = 1.0
MAX_S = 30
TIMING = {"K0": None, "N1a": "all", "N1l": "late"}
SEVS = ("clean", "mild", "mod", "sev")

# ───────── 순전파 메모(같은 입력이면 같은 결과) ─────────
_orig_outputs = DA.ctc_outputs
_memo = {}


def _memo_outputs(waveform, sample_rate, model_id=DA.DEFAULT_MODEL_ID):
    key = (model_id, sample_rate, hashlib.sha1(np.ascontiguousarray(waveform, dtype=np.float32).tobytes()).hexdigest())
    if key not in _memo:
        if len(_memo) > 64:
            _memo.clear()
        _memo[key] = _orig_outputs(waveform, sample_rate, model_id)
    return _memo[key]


DA.ctc_outputs = _memo_outputs


def win_db(y, win=0.01):
    n = int(SR * win)
    m = len(y) // n
    if m < 1:
        return np.zeros(0)
    r = np.sqrt(np.mean(np.asarray(y[:m * n], dtype=np.float64).reshape(m, n) ** 2, 1) + 1e-12)
    return 20 * np.log10(r)


def room_tail(y, key, secs=TAIL_S):
    """10/7과 같은 T 조건: 그 클립 10 ms 창 RMS 10백분위 수준의 가우스 잡음(시드는 클립 이름)."""
    db = win_db(y)
    rms = max(10 ** (np.percentile(db, 10) / 20.0), 1e-4) if len(db) else 1e-4
    rng = np.random.default_rng(zlib.crc32(key.encode()))
    return (rng.standard_normal(int(SR * secs)) * rms).astype(np.float32)


def app_phones(y, tokens, trim, timing):
    """앱 그대로: 환경변수만 바꿔 dgop_acoustic.phone_confidences를 부른다."""
    os.environ["DGOP_TAIL_TRIM"] = "1" if trim == "t" else "0"
    gate = TIMING[timing]
    os.environ["DGOP_TAIL_RESEG"] = "0" if gate is None else "1"
    DA.TAIL_RESEG_GATE = gate or "late"
    return DA.phone_confidences(np.asarray(y, dtype=np.float32), SR, tokens, aligner_id=AL, scorer_id=SC)


def sentence(phones, target):
    for i in JV.silent_linking_h(target):
        if i < len(phones):
            phones[i]["silent_h"] = True
    sc = [p for p in phones if p.get("aligned") and p.get("scorable")]
    raw = G.sentence_dgop(sc)["score"]
    return raw, G.calibrate_score(raw, CAL)


def slim(ph):
    return [[p["token"], p.get("t0"), p.get("t1"), p.get("naive"), 1 if p.get("silent_h") else 0] for p in ph]


def read_audio(job):
    if job["set"] == "tts":
        f = os.path.join(ROOT, "data", "tts", job["file"])
        from faster_whisper.audio import decode_audio      # 앱 assess_text·sound_tts와 같은 디코드
        return decode_audio(f, sampling_rate=SR).astype(np.float32)[:SR * MAX_S]
    y, sr = sf.read(os.path.join(ROOT, "data", "wav", job["file"]), dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    assert sr == SR, (job["file"], sr)
    return y.astype(np.float32)[:SR * MAX_S]


def shard(items):
    i, n = map(int, a.shard.split("/"))
    items = items[i::n]
    return items[:a.limit] if a.limit else items


def load_jobs(name):
    return [json.loads(l) for l in open(os.path.join(ROOT, "data", name), encoding="utf-8") if l.strip()]


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


def measure_clip(j, y, key, out, done, targets):
    yT = np.concatenate([y, room_tail(y, key)])[:SR * MAX_S]
    for cond, yy in (("R", y), ("T", yT)):
        for tr in ("n", "t"):
            rows = {}
            for tm in TIMING:
                v = f"{tm}_{tr}_{cond}"
                if (j["clip"], v) in done:
                    continue
                rows[tm] = {"set": j["set"], "clip": j["clip"], "spk": j.get("spk", j.get("voice")), "half": j.get("half"),
                            "variant": v, "dur": round(len(yy) / SR, 3), "dur_raw": round(len(y) / SR, 3),
                            "speech_end": DA.speech_end_seconds(yy, SR), "speech_end_raw": DA.speech_end_seconds(y, SR),
                            "targets": []}
            if not rows:
                continue
            try:
                base = {}
                for k, t in enumerate(targets):
                    toks = JV.text_to_tokens(t["target"])
                    for tm in rows:
                        if tm != "K0" and t["kind"] != "same":
                            if k not in base:
                                bp = app_phones(yy, toks, tr, "K0")
                                base[k] = (bp, *sentence(bp, t["target"]))
                            ph, raw, sc = base[k]          # 다른 문장은 시각과 무관(점수 같음)
                        else:
                            ph = app_phones(yy, toks, tr, tm)
                            raw, sc = sentence(ph, t["target"])
                            if tm == "K0":
                                base[k] = (ph, raw, sc)
                        rows[tm]["targets"].append({"kind": t["kind"], "target": t["target"], "raw": raw, "score": sc,
                                                    "rate": speak_cues.rate_pause(yy, ph, SR), "phones": slim(ph),
                                                    "retimed": any(p.get("retimed") for p in ph)})
            except Exception as e:
                for r in rows.values():
                    r["err"] = f"{type(e).__name__}: {e}"
            for r in rows.values():
                out.write(json.dumps(r, ensure_ascii=False) + "\n")
            out.flush()


def run_main():
    jobs = shard(load_jobs("jobs.jsonl"))
    done = done_keys(a.out)
    out = open(a.out, "a")
    for j in jobs:
        measure_clip(j, read_audio(j), f"{j['set']}:{j['clip']}", out, done, j["targets"])
    print("MEASURE_OK main", len(jobs), flush=True)


def run_tts():
    jobs = shard(load_jobs("tts_jobs.jsonl"))
    done = done_keys(a.out)
    out = open(a.out, "a")
    for j in jobs:
        measure_clip(j, read_audio(j), f"tts:{j['clip']}", out, done, [{"kind": "same", "target": j["target"]}])
    print("MEASURE_OK tts", len(jobs), flush=True)


def run_deg():
    import make_deaf_corpus as MD
    jobs = shard([j for j in load_jobs("jobs.jsonl") if j["set"] == "538n"])
    done = done_keys(a.out)
    out = open(a.out, "a")
    for j in jobs:
        y = read_audio(j)
        own = j["targets"][0]
        toks = JV.text_to_tokens(own["target"])
        seed = zlib.crc32(j["clip"].encode()) % (2 ** 31)
        for sev in SEVS:
            ys = y if sev == "clean" else np.asarray(MD.perturb_safe(y, SR, seed=seed, **dict(MD.PRESETS[sev])), dtype=np.float32)
            for tr in ("n", "t"):
                v = f"K0_{tr}_{sev}"
                if (j["clip"], v) in done:
                    continue
                row = {"set": "538n", "clip": j["clip"], "spk": j["spk"], "half": j["half"], "variant": v}
                try:
                    ph = app_phones(ys, toks, tr, "K0")
                    row["raw"], row["score"] = sentence(ph, own["target"])
                except Exception as e:
                    row["err"] = f"{type(e).__name__}: {e}"
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                out.flush()
    print("MEASURE_OK deg", len(jobs), flush=True)


# ───────── MFA(독립 참조, tailaug와 같은 방식) ─────────
def mfa_text(t):
    if re.search(r"[0-9A-Za-z]", t or ""):
        return None
    s = DA.normalize_syllable_text(t)
    return s or None


def run_mfaprep():
    d = os.path.abspath(a.out)
    os.makedirs(d, exist_ok=True)
    ids, n = {}, 0
    for j in load_jobs("jobs.jsonl"):
        if j["set"] != "538n":
            continue
        own = j["targets"][0]["target"]
        txt = mfa_text(own)
        if not txt:
            continue
        uid = f"c{n:05d}"
        n += 1
        sd = os.path.join(d, "corpus", "s538_" + re.sub(r"[^A-Za-z0-9]", "_", j["spk"]))
        os.makedirs(sd, exist_ok=True)
        sf.write(os.path.join(sd, uid + ".wav"), read_audio(j), SR, subtype="PCM_16")
        open(os.path.join(sd, uid + ".lab"), "w", encoding="utf-8").write(txt + "\n")
        ids[uid] = {"key": f"538n:{j['clip']}", "text": own}
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
            ph = [p for p in (parse_textgrid(f[0]) or []) if p[0].strip().lower() not in SIL]
            vow = []
            for k, p in enumerate(ph):          # 모음 바로 앞이 활음이면 그 활음 시작을 모음 시작으로(tailaug 사후 변경 1과 같다)
                if is_vowel(p[0]):
                    t0 = ph[k - 1][1] if k > 0 and ph[k - 1][0].strip() in GLIDES else p[1]
                    vow.append([p[0], round(t0, 4), round(p[2], 4)])
            if ph and vow:
                row.update(ok=True, vowels=vow, n_vowel=len(vow), final_vowel_t0=vow[-1][1], speech_t1=ph[-1][2],
                           phones=[[p[0], round(p[1], 4), round(p[2], 4)] for p in ph])
                ok += 1
        out.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("MFAPARSE_OK", ok, "/", len(ids), flush=True)


# ───────── CPU 지연·경로 일치(C5) ─────────
def run_cpu():
    assert os.environ.get("DGOP_DEVICE") == "cpu"
    gpu = {}
    for f in glob.glob(a.out2):
        for l in open(f):
            r = json.loads(l)
            if r["set"] == "538n" and r["variant"].endswith("_T") and not r.get("err"):
                gpu[(r["clip"], r["variant"])] = r["targets"][0]
    jobs = [j for j in load_jobs("jobs.jsonl") if j["set"] == "538n"][:6]
    res = {"threads": torch.get_num_threads(), "configs": {}}
    for tm, tr in (("K0", "t"), ("K0", "n"), ("N1l", "t"), ("N1l", "n"), ("N1a", "t"), ("N1a", "n")):
        times, dt, ds, n = [], [], [], 0
        for rep in range(4):
            for j in jobs:
                y = read_audio(j)
                yT = np.concatenate([y, room_tail(y, f"{j['set']}:{j['clip']}")])[:SR * MAX_S]
                toks = JV.text_to_tokens(j["targets"][0]["target"])
                _memo.clear()                          # 지연은 순전파까지 다시 잰다
                t0 = time.perf_counter()
                ph = app_phones(yT, toks, tr, tm)
                el = time.perf_counter() - t0
                if rep == 0:                           # 첫 바퀴(적재·데우기)는 지연에서 빼고 GPU 값과 비교만
                    g = gpu.get((j["clip"], f"{tm}_{tr}_T"))
                    if g is not None:
                        raw, sc = sentence(ph, j["targets"][0]["target"])
                        ds.append(abs(sc - g["score"]))
                        dt += [max(abs(p.get("t0", 0) - q[1]), abs(p.get("t1", 0) - q[2])) for p, q in zip(ph, g["phones"])]
                        n += 1
                else:
                    times.append(el)
        res["configs"][f"{tm}_{tr}"] = {"median_s": statistics.median(times), "mean_s": statistics.mean(times), "n": len(times),
                                        "gpu_n": n, "score_diff_max": max(ds) if ds else None,
                                        "time_diff_max": max(dt) if dt else None,
                                        "time_diff_gt_frame": (sum(1 for x in dt if x > 0.021) / len(dt)) if dt else None}
    _, am = DA._load(AL, device="cpu")
    _, sm = DA._load(SC, device="cpu")
    res["shared_feature_encoder"] = bool(isinstance(am.wav2vec2.feature_extractor, DA.SharedFeatureEncoder)
                                         and am.wav2vec2.feature_extractor is sm.wav2vec2.feature_extractor)
    res["bytes"] = {k: os.path.getsize(os.path.join(p, "model.int8.safetensors")) for k, p in (("aligner", AL), ("scorer", SC))}
    print(res, flush=True)
    json.dump(res, open(a.out, "w"), indent=1)
    print("MEASURE_OK cpu", flush=True)


def selftest():
    """메모한 순전파와 환경변수 전환이 앱 함수의 결과를 바꾸지 않는지(메모 없이 새로 부른 값과 같은지)."""
    j = load_jobs("jobs.jsonl")[0]
    y = read_audio(j)
    yT = np.concatenate([y, room_tail(y, "x")])
    toks = JV.text_to_tokens(j["targets"][0]["target"])
    n = 0
    for tm in TIMING:
        for tr in ("n", "t"):
            mine = app_phones(yT, toks, tr, tm)
            _memo.clear()
            DA.ctc_outputs = _orig_outputs
            ref = app_phones(yT, toks, tr, tm)
            DA.ctc_outputs = _memo_outputs
            for p, q in zip(mine, ref):
                assert p["token"] == q["token"] and p.get("t0") == q.get("t0") and p.get("t1") == q.get("t1") \
                    and abs(p["naive"] - q["naive"]) < 1e-6, (tm, tr, p, q)
            n += 1
    print("SELFTEST_OK", n, flush=True)


{"main": run_main, "tts": run_tts, "deg": run_deg, "mfaprep": run_mfaprep, "mfaparse": run_mfaparse,
 "cpu": run_cpu, "selftest": selftest}[a.part]()
