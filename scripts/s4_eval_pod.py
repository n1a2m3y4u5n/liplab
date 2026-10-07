"""S4 채점 모델 증류 평가(docs/scorer-distill-2026-10.md 6절), 파드 쪽.

채점은 앱 커밋 b675975의 backend(`dgop_acoustic.assess_text`·`phone_confidences`)를 그대로 부르고, 음향 출력(`ctc_outputs`)만 바꿔 끼운다.
  python s4_eval_pod.py prep                              608 컷 다시 자르기, E1·E2 작업 목록
  python s4_eval_pod.py e1  BACKEND WORKERS OUT.jsonl     10/6 짝(608·538 same·diff)
  python s4_eval_pod.py e2  BACKEND WORKERS OUT.json      사·자·차·하 앱 방향 대치(자음 부분만, speak_app_direction_pod_eval.py 규칙)
  python s4_eval_pod.py dev BACKEND WORKERS OUT.jsonl     Zeroth 시험 × 4조건 × 목표 3개(학생 고르기)
  python s4_eval_pod.py latency BACKEND OUT.json          문장당 끝에서 끝 시간(한 번에 한 문장, 스레드 LAT_THREADS=2)
BACKEND: teacher(GPU int8) | teacher_cpu(앱 경로 그대로, CPU int8) | onnx:경로 | torch:H|X(학생 fp32, GPU)
"""
import hashlib
import io
import json
import os
import random
import re
import sys
import time
import zlib
from concurrent.futures import ProcessPoolExecutor

import numpy as np

W = os.environ.get("S4_W", "/workspace")
BK = f"{W}/backend"
AL_DIR = f"{BK}/models/dgop_ours/aligner"
SC_DIR = f"{BK}/models/dgop_ours/scorer"
CAL = f"{BK}/data/dgop_calibration_ours.json"
EV = f"{W}/eval"
SR = 16000


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def hangul(s):
    return re.sub(r"[^가-힣]", "", s or "")


# ───────────────────────── prep ─────────────────────────
def cmd_prep():
    """608 컷: cuts608.json의 시작·끝 초로 세션 FLAC을 speak_asr_pod_run.cut_608과 같은 방식(sf.write)으로 다시 자른다."""
    import soundfile as sf
    os.makedirs(f"{EV}/cuts", exist_ok=True)
    cuts = [c for c in json.load(open(f"{EV}/cuts608.json")) if c.get("cut")]
    cache = {}
    for c in cuts:
        dst = f"{EV}/cuts/{c['file'][:-5]}_{c['si']:03d}.wav"
        c["wav"] = dst
        if os.path.exists(dst):
            continue
        if c["file"] not in cache:
            cache.clear()
            audio, sr = sf.read(f"{EV}/s608/{c['file']}")
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            assert sr == SR, sr
            cache[c["file"]] = audio
        audio = cache[c["file"]]
        sf.write(dst, audio[int(c["start"] * SR):int(c["end"] * SR)], SR)
    by_clip = {f"{c['file'][:-5]}:{c['si']:03d}": c for c in cuts}
    # E1: 10/6 행(same·diff)과 클립 경로
    rows = [json.loads(l) for l in open(f"{EV}/e1_rows.jsonl", encoding="utf-8")]
    jobs = {}
    for r in rows:
        if r["set"] == "608":
            path = by_clip[r["clip"]]["wav"]
        else:
            path = f"{EV}/c538wav/{r['clip']}.wav"
        assert os.path.exists(path), path
        jobs.setdefault(r["clip"], {"path": path, "set": r["set"], "spk": r["spk"], "clip": r["clip"], "targets": []})
        jobs[r["clip"]]["targets"].append([r["target"], r["kind"]])
    json.dump(list(jobs.values()), open(f"{EV}/e1_jobs.json", "w"), ensure_ascii=False)
    # E2: 538 manifest 전부 + 608 컷 363
    e2 = []
    for l in open(f"{EV}/c538wav/manifest.tsv", encoding="utf-8"):
        clip, spk, text = l.rstrip("\n").split("\t")
        p = f"{EV}/c538wav/{clip.replace('.mp4', '')}.wav"
        if os.path.exists(p):
            e2.append({"path": p, "text": text, "spk": spk, "group": "538"})
    e2 += [{"path": c["wav"], "text": c["target"], "spk": c["file"].split("-")[4], "group": "608"} for c in cuts]
    json.dump(e2, open(f"{EV}/e2_jobs.json", "w"), ensure_ascii=False)
    # 개발: Zeroth 시험 × 4조건, 목표 = 자기 문장 + 음절 수 ±30%인 다른 시험 문장 2개(Random(0), 발화 이름 순)
    dev = json.load(open(f"{W}/data/devwav/dev.json", encoding="utf-8"))
    texts = {}
    for d in dev:
        texts[d["src"]] = d["text"]
    srcs = sorted(texts)
    pool = [texts[s] for s in srcs]
    rng = random.Random(0)
    tg = {}
    for s in srcs:
        t = texts[s]
        n = len(hangul(t))
        cand = [x for x in pool if hangul(x) != hangul(t) and 0.7 * n <= len(hangul(x)) <= 1.3 * n]
        tg[s] = [[t, "same"]] + [[x, "diff"] for x in rng.sample(cand, min(2, len(cand)))]
    dj = [{"path": d["path"], "set": "dev", "spk": d["spk"], "clip": d["name"], "cond": d["cond"], "targets": tg[d["src"]]}
          for d in dev]
    json.dump(dj, open(f"{EV}/dev_jobs.json", "w"), ensure_ascii=False)
    log("PREP_OK e1_clips", len(jobs), "e1_rows", len(rows), "e2", len(e2), "dev", len(dj))


# ───────────────────────── backends ─────────────────────────
_STATE = {}


class Teacher:
    """교사 int8(quant_int8.load_ctc)을 GPU에서. 전처리는 앱과 같은 프로세서."""

    def __init__(self, device="cuda"):
        import torch
        sys.path.insert(0, BK)
        import quant_int8 as Q
        from transformers import AutoProcessor
        torch.backends.cuda.matmul.allow_tf32 = False      # TF32는 교사 로짓을 최대 0.4까지 바꾼다(10/7 점검), fp32로 계산
        torch.backends.cudnn.allow_tf32 = False
        self.torch = torch
        self.device = device
        self.proc = AutoProcessor.from_pretrained(AL_DIR)
        self.al = Q.load_ctc(AL_DIR).to(device).eval()
        self.sc = Q.load_ctc(SC_DIR).to(device).eval()
        self.vocab = self.proc.tokenizer.get_vocab()

    def run(self, wave):
        t = self.torch
        x = self.proc(wave, sampling_rate=SR, return_tensors="pt").input_values.to(self.device)
        with t.no_grad():
            a = self.al(x).logits[0].float().cpu()
            s = self.sc(x).logits[0].float().cpu()
        return {"al": a, "sc": s}


class Onnx:
    def __init__(self, path, threads=2):
        import onnxruntime as ort
        import torch
        from transformers import AutoProcessor
        self.torch = torch
        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        so.inter_op_num_threads = 1
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.sess = ort.InferenceSession(path, so, providers=["CPUExecutionProvider"])
        self.vocab = AutoProcessor.from_pretrained(AL_DIR).tokenizer.get_vocab()
        self.fwd = []

    def run(self, wave):
        t0 = time.perf_counter()
        a, s = self.sess.run(None, {"wav": np.ascontiguousarray(wave, dtype=np.float32)[None]})
        self.fwd.append(time.perf_counter() - t0)
        return {"al": self.torch.from_numpy(a[0]).float(), "sc": self.torch.from_numpy(s[0]).float()}


class TorchStudent:
    def __init__(self, init, device="cuda"):
        import torch
        sys.path.insert(0, f"{W}/scripts")
        import s4_distill_pod as S
        from transformers import AutoProcessor
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        self.torch = torch
        self.device = device
        st = S.build_student(init, "cpu")
        st.load_state_dict(torch.load(f"{W}/runs/{init}/final.pt", map_location="cpu")["model"])
        self.st = st.to(device).eval()
        self.vocab = AutoProcessor.from_pretrained(AL_DIR).tokenizer.get_vocab()

    def run(self, wave):
        t = self.torch
        with t.no_grad():
            a, s = self.st(t.from_numpy(np.ascontiguousarray(wave, dtype=np.float32))[None].to(self.device))
        return {"al": a[0].float().cpu(), "sc": s[0].float().cpu()}


def make_backend(spec, threads=2):
    if spec == "teacher":
        return Teacher("cuda")
    if spec.startswith("onnx:"):
        return Onnx(spec[5:], threads)
    if spec.startswith("torch:"):
        return TorchStudent(spec[6:], "cuda")
    raise ValueError(spec)


def setup(spec, threads=2):
    """작업자 초기화: 앱 backend를 올리고 ctc_outputs를 BACKEND 출력으로 바꾼다(teacher_cpu는 바꾸지 않는다)."""
    if "D" in _STATE:
        return _STATE["D"]
    os.environ.update(DGOP_CALIBRATION=CAL, HF_HUB_OFFLINE="1", LIPLAB_CONTENT_WARMUP="0")
    if spec == "teacher_cpu":
        os.environ.update(BACKBONE_QUANT="int8", DGOP_DEVICE="cpu", DGOP_ALIGNER_ID=AL_DIR, DGOP_SCORER_ID=SC_DIR)
    sys.path.insert(0, BK)
    import torch
    torch.set_num_threads(threads)
    import dgop_acoustic as D
    import jamo_vocab
    if spec == "teacher_cpu":
        _STATE.update(D=D, ids=(AL_DIR, SC_DIR), be=None)
        return D
    be = make_backend(spec, threads)
    cache = {}

    def ctc_outputs(waveform, sample_rate, model_id=D.DEFAULT_MODEL_ID):
        key = hashlib.sha1(np.ascontiguousarray(waveform, dtype=np.float32).tobytes()).hexdigest()
        if key not in cache:
            cache.clear()
            cache[key] = be.run(waveform)
        lg = cache[key][model_id]
        return torch.log_softmax(lg, dim=-1), lg, be.vocab

    D.ctc_outputs = ctc_outputs
    D._share_once = lambda a, b: None
    D.tokens_for_text = lambda text, model_id=None: jamo_vocab.text_to_tokens(text)
    _STATE.update(D=D, ids=("al", "sc"), be=be)
    return D


def _init_worker(spec, threads):
    if spec == "teacher" or spec.startswith("torch:"):
        os.environ.pop("CUDA_VISIBLE_DEVICES", None)
    setup(spec, threads)


# ───────────────────────── E1·dev ─────────────────────────
def pair_job(job):
    D = _STATE["D"]
    al, sc = _STATE["ids"]
    data = open(job["path"], "rb").read()
    out = []
    t0 = time.time()
    for target, kind in job["targets"]:
        try:
            r = D.assess_text(data, target, aligner_id=al, scorer_id=sc)
            out.append({k: job.get(k) for k in ("set", "spk", "clip", "cond")} | {"target": target, "kind": kind, "score": r.get("score"),
                       "raw": r.get("raw_score"), "n_ph": sum(1 for p in r.get("phones") or [] if p.get("aligned") and p.get("scorable"))})
        except Exception as e:
            out.append({k: job.get(k) for k in ("set", "spk", "clip", "cond")} | {"target": target, "kind": kind,
                       "error": f"{type(e).__name__}: {e}"})
    return out, time.time() - t0


def run_pairs(jobs_file, spec, workers, out_path, threads=2):
    jobs = json.load(open(jobs_file, encoding="utf-8"))
    log("jobs", len(jobs), "backend", spec, "workers", workers)
    n, err, t0 = 0, 0, time.time()
    with open(out_path + ".tmp", "w", encoding="utf-8") as f, \
            ProcessPoolExecutor(workers, initializer=_init_worker, initargs=(spec, threads)) as ex:
        for i, (rows, dt) in enumerate(ex.map(pair_job, jobs, chunksize=2)):
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                n += 1
                err += "error" in r
            if i % 200 == 0:
                log(i, len(jobs), "rows", n, "errors", err, round(time.time() - t0), "s")
    os.replace(out_path + ".tmp", out_path)
    log("PAIRS_OK", os.path.basename(out_path), "rows", n, "errors", err, round(time.time() - t0), "s")


# ───────────────────────── E2 ─────────────────────────
def cons_job(job):
    """speak_app_direction_pod_eval.job과 같은 자음 부분(포먼트는 뺌)."""
    import speak_app_direction_pod_eval as A
    from faster_whisper.audio import decode_audio
    D = _STATE["D"]
    al, sc = _STATE["ids"]
    path, text, spk, group = job["path"], job["text"], job["spk"], job["group"]
    try:
        data = open(path, "rb").read()
        wave = decode_audio(io.BytesIO(data), sampling_rate=SR)[:SR * 30]
        base_toks = D.tokens_for_text(text, model_id=al)
        base = D.phone_confidences(wave, SR, base_toks, aligner_id=al, scorer_id=sc)
        # 9/29와 같은 씨앗 문자열(그때 경로: 538 /workspace/c538/<클립>.flac, 608 /workspace/cuts/<컷>.wav)
        b = os.path.basename(path)
        seed_path = f"/workspace/c538/{b[:-4]}.flac" if group == "538" else f"/workspace/cuts/{b}"
        rng = random.Random(zlib.crc32(seed_path.encode()))
        cons = []

        def dg(ph, k):
            p = ph[k] if k < len(ph) else {}
            return p.get("dgop") if p.get("aligned") else None

        for c in A.TRUE_CONS:
            sp = A.spots(text, c)
            for i in rng.sample(sp, min(A.MAX_SPOTS, len(sp))):
                probe = "ㄱ" if c != "ㄱ" else "ㄷ"
                k = A.locate(base_toks, D.tokens_for_text(A.with_onset(text, i, probe), model_id=al), c, probe)
                if k is None:
                    continue
                cons.append({"kind": "true", "cons": c, "k": k, "i": i, "wi": A.word_initial(text, i), "dgop": dg(base, k)})
        for y, x in A.PAIRS:
            sp = A.spots(text, y)
            for i in rng.sample(sp, min(A.MAX_SPOTS, len(sp))):
                alt_toks = D.tokens_for_text(A.with_onset(text, i, x), model_id=al)
                k = A.locate(base_toks, alt_toks, y, x)
                if k is None:
                    continue
                alt = D.phone_confidences(wave, SR, alt_toks, aligner_id=al, scorer_id=sc)
                cons.append({"kind": "pair", "y": y, "x": x, "k": k, "i": i, "wi": A.word_initial(text, i),
                             "same": dg(base, k) if y != "ㅇ" else None, "alt": dg(alt, k)})
        return {"path": os.path.basename(path), "spk": spk, "group": group, "n_tok": len(base_toks), "cons": cons}
    except Exception as e:
        return {"path": os.path.basename(path), "spk": spk, "group": group, "error": f"{type(e).__name__}: {e}"}


def run_e2(spec, workers, out_path, threads=2):
    jobs = json.load(open(f"{EV}/e2_jobs.json", encoding="utf-8"))
    jobs.sort(key=lambda j: j["group"] != "608")
    log("e2 jobs", len(jobs), spec)
    out, t0 = [], time.time()
    with ProcessPoolExecutor(workers, initializer=_init_worker, initargs=(spec, threads)) as ex:
        for i, r in enumerate(ex.map(cons_job, jobs, chunksize=2)):
            out.append(r)
            if i % 200 == 0:
                log(i, len(jobs), sum(len(x.get("cons", [])) for x in out), "errors", sum("error" in x for x in out),
                    round(time.time() - t0), "s")
    json.dump(out, open(out_path, "w"), ensure_ascii=False)
    log("E2_OK", os.path.basename(out_path), len(out), "errors", sum("error" in x for x in out), round(time.time() - t0), "s")


# ───────────────────────── latency ─────────────────────────
def latency_sentences():
    jobs = json.load(open(f"{EV}/e1_jobs.json", encoding="utf-8"))
    sel = []
    for st in ("538", "608"):
        js = sorted([j for j in jobs if j["set"] == st], key=lambda j: j["clip"])
        step = len(js) / 50.0
        for k in range(50):
            j = js[int(k * step)]
            own = next(t for t, kind in j["targets"] if kind == "same")
            sel.append((j["path"], own, st, j["clip"]))
    return sel


def cmd_latency(spec, out_path):
    threads = int(os.environ.get("LAT_THREADS", "2"))
    os.environ["OMP_NUM_THREADS"] = str(threads)
    if spec == "teacher_cpu":
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
    D = setup(spec, threads)
    al, sc = _STATE["ids"]
    sel = latency_sentences()
    warm = sel[:3]
    for p, t, _, _ in warm:
        D.assess_text(open(p, "rb").read(), t, aligner_id=al, scorer_id=sc)
    be = _STATE.get("be")
    if be is not None and hasattr(be, "fwd"):
        be.fwd.clear()
    rows = []
    for p, t, st, clip in sel:
        data = open(p, "rb").read()
        t0 = time.perf_counter()
        r = D.assess_text(data, t, aligner_id=al, scorer_id=sc)
        dt = time.perf_counter() - t0
        import soundfile as sf
        info = sf.info(p)
        rows.append({"set": st, "clip": clip, "sec": round(dt, 4), "audio_s": round(info.frames / info.samplerate, 3), "raw": r.get("raw_score")})
    secs = np.array([r["sec"] for r in rows])
    cpu = ""
    try:
        cpu = next(l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name"))
    except Exception:
        pass
    res = {"backend": spec, "threads": threads, "cpu": cpu, "n": len(rows), "median": float(np.median(secs)),
           "p95": float(np.percentile(secs, 95)), "max": float(secs.max()), "mean_audio_s": float(np.mean([r["audio_s"] for r in rows])),
           "fwd_median": float(np.median(be.fwd)) if be is not None and getattr(be, "fwd", None) else None, "rows": rows}
    json.dump(res, open(out_path, "w"), indent=1)
    log("LATENCY_OK", spec, threads, "median", round(res["median"], 3), "p95", round(res["p95"], 3), cpu)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "prep":
        cmd_prep()
    elif cmd in ("e1", "dev"):
        spec, workers, out = sys.argv[2], int(sys.argv[3]), sys.argv[4]
        run_pairs(f"{EV}/{cmd}_jobs.json", spec, workers, out, int(os.environ.get("EVAL_THREADS", "2")))
    elif cmd == "e2":
        spec, workers, out = sys.argv[2], int(sys.argv[3]), sys.argv[4]
        sys.path.insert(0, f"{W}/scripts")
        run_e2(spec, workers, out, int(os.environ.get("EVAL_THREADS", "2")))
    elif cmd == "latency":
        cmd_latency(sys.argv[2], sys.argv[3])
    else:
        sys.exit(f"알 수 없는 명령 {cmd}")
