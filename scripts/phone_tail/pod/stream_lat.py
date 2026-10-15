"""S4 긴 녹음 지연: 입력 분할·스트리밍 시험(파드). docs/scorer-stream-latency-2026-10.md 2절.

    python stream_lat.py export      구조가 같은 학생(H 구성, 사전학습 인코더 + 무작위 출력층) → 가중치 전용 int8 ONNX
    python stream_lat.py fidelity    교사(GPU int8)·사전학습 인코더로 창 나누기 대 전체 순전파의 칩·은닉 상태 차(보고만)
    python stream_lat.py latency     파드 CPU 2스레드: 전체 순전파(F)와 스트리밍(S)의 녹음 뒤 지연, 10/7 표본 길이의 F(다리 2)

S4_W=/workspace/pt(backend/, scripts/의 s4_distill_pod.py·s4_eval_pod.py, data/wav, data/jobs.jsonl, data/lat100.json). 결과 out/stream_*.json.
"""
import hashlib
import io
import json
import os
import sys
import time
import zlib

import numpy as np

W = os.environ.get("S4_W", "/workspace/pt")
sys.path.insert(0, f"{W}/scripts")
sys.path.insert(0, f"{W}/backend")
os.environ.setdefault("LIPLAB_CONTENT_WARMUP", "0")
import s4_distill_pod as S  # noqa: E402
import s4_eval_pod as E  # noqa: E402

SR = 16000
HOP = 320
C_S, LC_S, RC_S = (float(os.environ.get(k, d)) for k, d in (("STREAM_C", 4.0), ("STREAM_LC", 2.0), ("STREAM_RC", 1.0)))
SUF = os.environ.get("STREAM_SUFFIX", "")   # 사후 관찰(창 문맥을 바꾼 판, 보고만)
CF, LF, RF = int(C_S * SR / HOP), int(LC_S * SR / HOP), int(RC_S * SR / HOP)
LENGTHS = (3, 5, 8, 10, 15, 20, 25, 30)
OUT = f"{W}/out"
W8 = f"{W}/runs/Hs/student_w8.onnx"
os.makedirs(OUT, exist_ok=True)


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ───────────── 자료: A1 클립을 이어 붙인 소리와 목표 ─────────────
def clips():
    js = [json.loads(l) for l in open(f"{W}/data/jobs.jsonl", encoding="utf-8")]
    import soundfile as sf
    out = []
    for j in js:
        y, sr = sf.read(f"{W}/data/wav/{j['clip']}.wav", dtype="float32")
        out.append((y if y.ndim == 1 else y.mean(1), j["target"]))
    return out


def concat(pool, seconds, seed, exact=False):
    """pool에서 난수 순서로 이어 붙여 seconds 이상이 되게 한다(exact면 정확히 그 길이로 자름). 목표는 이어 붙인 대본."""
    rng = np.random.default_rng(seed)
    ys, ts, n = [], [], 0
    while n < seconds * SR:
        y, t = pool[int(rng.integers(len(pool)))]
        ys.append(y)
        ts.append(t)
        n += len(y)
    y = np.concatenate(ys)
    if exact:
        y = y[:int(seconds * SR)]
    return y.astype(np.float32), " ".join(ts)


# ───────────── 창 나누기 ─────────────
def windows(n_samples):
    """청크 k: 남길 전역 프레임 [b_k, b_k+1), 넣을 표본 [s0, s1). 마지막 청크는 오른쪽 문맥이 없다."""
    G = S.conv_len(n_samples)
    out = []
    b = 0
    while b < G:
        e = min(b + CF, G)
        f0 = max(0, b - LF)
        s0 = f0 * HOP
        s1 = n_samples if e >= G else min(n_samples, (e + RF - 1) * HOP + 400)
        out.append((b, e, f0, s0, s1))
        b = e
    return G, out


def stitch(run, y):
    """run(wave) → (al, sc) numpy [프레임, 49]. 창마다 넣고 가운데 프레임을 이어 붙인다."""
    G, ws = windows(len(y))
    al, sc = [], []
    for b, e, f0, s0, s1 in ws:
        a, s = run(y[s0:s1])
        assert a.shape[0] >= e - f0, (a.shape, b, e, f0)
        al.append(a[b - f0:e - f0])
        sc.append(s[b - f0:e - f0])
    al, sc = np.concatenate(al), np.concatenate(sc)
    assert al.shape[0] == G
    return al, sc


# ───────────── 칩 값 ─────────────
def chips(al, sc, toks):
    import torch
    import dgop_acoustic as DA
    import dgop as G
    vocab = json.load(open(f"{W}/backend/models/dgop_ours/aligner/vocab.json", encoding="utf-8"))
    spans = DA.align_targets(torch.from_numpy(al.astype(np.float32)), vocab, toks)
    p = np.exp(sc - sc.max(1, keepdims=True))
    p /= p.sum(1, keepdims=True)
    vals = []
    for t, sp in zip(toks, spans):
        if DA._is_scorable(t):
            vals.append(float(p[sp["start"]:sp["end"] + 1].mean(0)[vocab[t]]))
    raw = G.sentence_dgop([{"naive": v, "confidence": 1.0, "dgop": v, "uncertainty": 0.0} for v in vals])["score"]
    return vals, raw


def color(v):
    d = int(np.floor(100 * v + 0.5))
    return "bad" if d < 45 else ("warn" if d < 70 else "good")


def cmd_fidelity():
    import torch
    import jamo_vocab as JV
    pool = clips()
    T = E.Teacher("cuda")
    run_t = lambda w: tuple(x.numpy() for x in (lambda o: (o["al"], o["sc"]))(T.run(w)))
    gnorm = os.environ.get("STREAM_GLOBALNORM") == "1"
    if gnorm:
        # 사후 관찰: 입력 정규화(평균 0·분산 1)를 창마다가 아니라 소리 전체로 한 번(스트리밍에서는 그때까지의 누적 통계로 바꿀 수 있다)
        def run_t(w):
            x = torch.from_numpy(np.ascontiguousarray(w, dtype=np.float32))[None].cuda()
            with torch.no_grad():
                return T.al(x).logits[0].float().cpu().numpy(), T.sc(x).logits[0].float().cpu().numpy()
    res = {"teacher": [], "hubert_cos": []}
    from transformers import HubertModel
    hub = HubertModel.from_pretrained(S.H_ID).cuda().eval()
    torch.backends.cuda.matmul.allow_tf32 = False

    def run_h(w):
        with torch.no_grad():
            h = hub(torch.from_numpy(w)[None].cuda()).last_hidden_state[0].float().cpu().numpy()
        return h, h
    agree = n = 0
    for L in (15, 20, 25, 30):
        for r in range(10):
            y, txt = concat(pool, L, zlib.crc32(f"fid|{L}|{r}".encode()), exact=True)
            if gnorm:
                y = ((y - y.mean()) / np.sqrt(y.var() + 1e-7)).astype(np.float32)
            toks = JV.text_to_tokens(txt)
            fa, fs = run_t(y)
            ca, cs = stitch(run_t, y)
            vf, rf = chips(fa, fs, toks)
            vc, rc = chips(ca, cs, toks)
            ag = sum(color(a) == color(b) for a, b in zip(vf, vc))
            agree += ag
            n += len(vf)
            res["teacher"].append({"L": L, "r": r, "n_tok": len(vf), "agree": ag, "raw_full": rf, "raw_chunk": rc,
                                   "naive_absdiff_p95": float(np.percentile(np.abs(np.array(vf) - np.array(vc)), 95)),
                                   "logit_absdiff_max": float(max(np.abs(fa - ca).max(), np.abs(fs - cs).max()))})
            hf, _ = run_h(y)
            hc, _ = stitch(run_h, y)
            m = min(len(hf), len(hc))
            cos = (hf[:m] * hc[:m]).sum(1) / (np.linalg.norm(hf[:m], axis=1) * np.linalg.norm(hc[:m], axis=1) + 1e-9)
            res["hubert_cos"].append({"L": L, "r": r, "median": float(np.median(cos)), "p01": float(np.percentile(cos, 1)), "min": float(cos.min())})
        log("FID", L)
    raw = np.array([abs(x["raw_full"] - x["raw_chunk"]) for x in res["teacher"]])
    res["summary"] = {"chip_agree": agree / n, "tokens": n, "raw_absdiff_median": float(np.median(raw)), "raw_absdiff_p95": float(np.percentile(raw, 95)),
                      "raw_absdiff_max": float(raw.max()), "hubert_cos_median": float(np.median([x["median"] for x in res["hubert_cos"]])),
                      "hubert_cos_p01_min": float(min(x["p01"] for x in res["hubert_cos"]))}
    # 창 나누기 자체 점검: 창이 전체를 덮으면 전체와 같아야 한다
    y, txt = concat(pool, 3, 1, exact=True)
    G, ws = windows(len(y))
    assert len(ws) == 1 and ws[0][3] == 0 and ws[0][4] == len(y)
    json.dump(res, open(f"{OUT}/stream_fidelity{SUF}.json", "w"), indent=1)
    log("FIDELITY_OK", json.dumps(res["summary"]))


def cmd_export():
    import torch
    torch.manual_seed(0)
    st = S.build_student("H", "cpu").eval()
    nfold = S.fold_weight_norm(st)
    os.makedirs(os.path.dirname(W8), exist_ok=True)
    fp32 = W8.replace("_w8", "_fp32")
    dummy = torch.zeros(1, 4 * SR).normal_(0, 0.05)
    torch.onnx.export(st, (dummy,), fp32, input_names=["wav"], output_names=["al", "sc"], opset_version=17,
                      dynamic_axes={"wav": {1: "samples"}, "al": {1: "frames"}, "sc": {1: "frames"}}, dynamo=False, do_constant_folding=True)
    stats = S.quantize_weights_int8(fp32, W8)
    info = {"size_w8": os.path.getsize(W8), "size_fp32": os.path.getsize(fp32), "stats": stats, "params": S.n_params(st), "folded": nfold,
            "size_ratio_vs_1007_H": os.path.getsize(W8) / 104.6e6}
    json.dump(info, open(f"{OUT}/stream_export.json", "w"), indent=1)
    log("EXPORT_OK", json.dumps(info))


def wav_bytes(y):
    import soundfile as sf
    b = io.BytesIO()
    sf.write(b, y, SR, format="WAV", subtype="PCM_16")
    return b.getvalue()


def cmd_latency():
    threads = 2
    os.environ["OMP_NUM_THREADS"] = str(threads)
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    D = E.setup("onnx:" + W8, threads)
    be = E._STATE["be"]
    import dgop_acoustic as DA
    from faster_whisper.audio import decode_audio
    patched = D.ctc_outputs
    pool = clips()
    import torch

    def onnx_run(w):
        a, s = be.sess.run(None, {"wav": np.ascontiguousarray(w, dtype=np.float32)[None]})
        return a[0], s[0]

    def full(y, txt):
        data = wav_bytes(y)
        t0 = time.perf_counter()
        r = D.assess_text(data, txt, aligner_id="al", scorer_id="sc")
        return time.perf_counter() - t0, r.get("raw_score")

    def stream(y, txt):
        """녹음 중 청크(창 끝까지 소리가 왔을 때) 순전파 시간들, 녹음 뒤 지연(디코드·자르기 + 마지막 창 + 정렬·채점)."""
        data = wav_bytes(y)
        y = decode_audio(io.BytesIO(data), sampling_rate=SR)[:SR * 30]     # 녹음 중 기기에 있는 소리(16비트로 저장한 뒤와 같게)
        N = len(y)
        G, ws = windows(N)
        committed, during = {}, []
        for b, e, f0, s0, s1 in ws:
            if e >= G:
                break               # 마지막 청크는 녹음이 끝난 뒤
            t0 = time.perf_counter()
            committed[b] = (e, f0, s1, onnx_run(y[s0:s1]))
            during.append(time.perf_counter() - t0)
        t0 = time.perf_counter()
        yy = decode_audio(io.BytesIO(data), sampling_rate=SR)[:SR * 30]
        yt = DA.trim_trailing_silence(yy, SR)
        Nt = len(yt)
        Gt = S.conv_len(Nt)
        al, sc, b = [], [], 0
        for bb in sorted(committed):
            e, f0, s1, (a, s) = committed[bb]
            if bb != b or s1 > Nt or e > Gt:
                break
            al.append(a[bb - f0:e - f0])
            sc.append(s[bb - f0:e - f0])
            b = e
        if b < Gt:
            f0 = max(0, b - LF)
            a, s = onnx_run(yt[f0 * HOP:Nt])
            al.append(a[b - f0:Gt - f0])
            sc.append(s[b - f0:Gt - f0])
        al, sc = np.concatenate(al), np.concatenate(sc)
        assert al.shape[0] == Gt, (al.shape, Gt)
        key = hashlib.sha1(np.ascontiguousarray(yt, dtype=np.float32).tobytes()).hexdigest()
        st = {"al": torch.from_numpy(al).float(), "sc": torch.from_numpy(sc).float()}

        def ctc_outputs(waveform, sample_rate, model_id=DA.DEFAULT_MODEL_ID):
            k = hashlib.sha1(np.ascontiguousarray(waveform, dtype=np.float32).tobytes()).hexdigest()
            assert k == key, "자른 파형이 다르다"
            lg = st[model_id]
            return torch.log_softmax(lg, dim=-1), lg, be.vocab
        D.ctc_outputs = ctc_outputs
        try:
            r = D.assess_text(data, txt, aligner_id="al", scorer_id="sc")
        finally:
            D.ctc_outputs = patched
        return time.perf_counter() - t0, during, r.get("raw_score")

    # 데우기
    y, t = concat(pool, 10, 7, exact=True)
    for _ in range(2):
        full(y, t)
        stream(y, t)
    rows = []
    for rep in range(int(os.environ.get("STREAM_REPS", "3"))):
        for L in LENGTHS:
            for r in range(5):
                y, t = concat(pool, L, zlib.crc32(f"lat|{L}|{r}".encode()), exact=True)
                tf, raw_f = full(y, t)
                ts, during, raw_s = stream(y, t)
                rows.append({"rep": rep, "L": L, "r": r, "full": tf, "stream_post": ts, "during": during, "raw_full": raw_f, "raw_stream": raw_s})
        log("LAT rep", rep)
    summ = {}
    for L in LENGTHS:
        f = np.array([x["full"] for x in rows if x["L"] == L])
        s = np.array([x["stream_post"] for x in rows if x["L"] == L])
        d = np.array([v for x in rows if x["L"] == L for v in x["during"]])
        summ[L] = {"full_median": float(np.median(f)), "full_p95": float(np.percentile(f, 95)), "stream_median": float(np.median(s)),
                   "stream_p95": float(np.percentile(s, 95)), "during_p95": float(np.percentile(d, 95)) if len(d) else None, "n": len(f)}
    # 다리 2: 10/7 표본 100문장의 길이·목표로 F
    lat = [] if SUF else json.load(open(f"{W}/data/lat100.json", encoding="utf-8"))
    bridge = []
    for k, x in enumerate(lat):
        y, _ = concat(pool, x["audio_s"], zlib.crc32(f"br|{k}".encode()), exact=True)
        tf, _ = full(y, x["target"])
        bridge.append({"audio_s": x["audio_s"], "sec": tf, "sec_1007": x["sec"]})
    b = np.array([x["sec"] for x in bridge] or [np.nan])
    b7 = np.array([x["sec_1007"] for x in bridge] or [np.nan])
    cpu = ""
    try:
        cpu = next(l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name"))
    except Exception:
        pass
    res = {"cpu": cpu, "threads": threads, "chunk": [C_S, LC_S, RC_S], "by_length": summ, "rows": rows,
           "bridge": {"median": float(np.median(b)), "p95": float(np.percentile(b, 95)), "median_1007": float(np.median(b7)),
                      "p95_1007": float(np.percentile(b7, 95)), "ratio_median": float(np.median(b / b7)), "rows": bridge}}
    json.dump(res, open(f"{OUT}/stream_latency{SUF}.json", "w"), indent=1)
    log("LATENCY_OK", cpu, json.dumps(summ), json.dumps({k: v for k, v in res["bridge"].items() if k != "rows"}))


if __name__ == "__main__":
    {"export": cmd_export, "fidelity": cmd_fidelity, "latency": cmd_latency}[sys.argv[1]]()
