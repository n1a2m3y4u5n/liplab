"""소리 듣기 가상 청취자 실험 V1(docs/listen-virtual-listener-2026-10.md, 계획 docs/listen-advance-plan-2026-10.md 5절).

서버 음성(Supertonic 3, 목소리 m1·f1·m2·f2 훈련, m3 검사)에 듣기 소음 다섯(babble·ssn·talker1_f·talker1_m·talker2)을 앱과 같은
방식으로 섞고(말소리 활성 레벨 ITU-T P.56 대 소음 RMS, 전체 크기 고정, 소음 0.5초 먼저), 세 가지 청취자 모의(정상, 인공와우
잡음 보코더 8채널, 보청기 사용자 고주파 손실)를 거쳐 Whisper(large-v3-turbo, 한국어)로 받아쓴다. 채점은 앱의
listen_curriculum.word_score(소리 나는 대로 낱말 비교)다. 결과는 설계 점검용이며 사람 효과 주장에는 쓰지 않는다.

하위 명령(파드에서 순서대로, 모두 다시 불러도 이어 한다):
  selftest                                   활성 레벨·띄어쓰기 맞춤·모의 처리 점검(GPU 없음)
  prep    --sound DIR --work W               목록 만들기, 클립·소음 풀어 float32 캐시(W/cache.npz), 활성 레벨
  run     --work W [--tiers 1,2,3,4] [--max-minutes M] [--batch 64]
                                             섞기·모의(CPU 프로세스) → 받아쓰기(GPU) → W/asr.jsonl에 덧붙임(이미 한 키는 건너뜀)
  score   --work W                           W/asr.jsonl → W/scored.jsonl(word_score, 띄어쓰기 맞춤판과 그대로판)
  analyze --work W --out RESULT.json         문장별 로지스틱 적합과 사전 기준 판정(문서 8절)
  jfactor --work W --result RESULT.json --out J.json
                                             문장당 독립 요소 수 j 추정(반복 사이 과분산, Boothroyd·Nittrouer j, 모형 맞추기)
  dump    --work W --key KEY --out F.wav     조건 하나의 소리를 파일로(점검용, 재생하지 않는다)

오디오는 파드 작업 폴더에만 두고 저장소에 넣지 않는다.
"""
import argparse
import hashlib
import itertools
import json
import math
import os
import subprocess
import sys
import time

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.environ.get("LIPLAB_BACKEND") or os.path.join(os.path.dirname(_HERE), "backend")
sys.path.insert(0, BACKEND)

SR_MIX = 48000          # 브라우저 AudioContext 표본율(앱은 48 kHz로 풀어 섞는다)
SR_ASR = 16000          # Whisper 입력
VOICES = ["m3", "m1", "f1", "m2", "f2"]       # m3 = 검사용
TRAIN_VOICES = ["m1", "f1", "m2", "f2"]
NOISES = ["babble", "ssn", "talker1_f", "talker1_m", "talker2"]
LISTENERS = ["nh", "ci", "ha"]
SNRS = list(range(-16, 25, 2))                 # −16 ~ +24 dB, 2 dB 간격 21점(문서 6절)
GAIN_DB = -10                                  # 앱 기본 편안한 크기
REF_DBFS = -20
LEAD_S, RAMP_S, HOLD_S = 0.5, 0.15, 0.3        # listenAudio.play: 소음 0.5초 먼저, 0.15초 키움, 말 끝난 뒤 0.3초 + 0.15초 줄임

# 보청기 모의: Bisgaard 외 2010 표준 청력도 S2(완만~가파른 고주파 손실) − 반이득 규칙 증폭 = 남는 손실
BISGAARD_F = [250, 375, 500, 750, 1000, 1500, 2000, 3000, 4000, 6000]
BISGAARD_S2 = [20, 20, 20, 22.5, 25, 35, 55, 75, 95, 95]
HA_FLOOR_DB = -50.0     # 문턱 잡음(백색): 혼합 전체 RMS 대비. 65 dB SPL 제시에서 1 kHz 1/3옥타브 약 0 dB SPL
# 인공와우 모의: 잡음 보코더(Shannon 외 1995; Friesen 외 2001), Greenwood(1990) 간격 8채널
CI_CH, CI_LO, CI_HI, CI_ENV_HZ = 8, 200.0, 7000.0, 160.0


# ───────────────────────────── 앱 계산 옮김 ─────────────────────────────

def amp(db):
    return 10 ** (db / 20)


def mix_levels(gain_db, snr_db):
    """listenMix.mixLevels: 말·소음 목표 RMS. snr_db None이면 말만."""
    total = amp(REF_DBFS + max(-30, min(0, round(gain_db))))
    if snr_db is None:
        return total, 0.0
    r = 10 ** (snr_db / 10)
    return total * math.sqrt(r / (1 + r)), total * math.sqrt(1 / (1 + r))


def active_level(x, sr):
    """listenMix.activeLevel(ITU-T P.56 방법 B)을 그대로 옮긴 것(벡터화). 선형 RMS 등가값."""
    from scipy.signal import lfilter
    x = np.asarray(x, dtype=np.float64)
    n = x.size
    if not n or sr <= 0:
        return 0.0
    g = math.exp(-1 / (sr * 0.03))
    hang = math.ceil(0.2 * sr)
    p = lfilter([1 - g], [1, -g], np.abs(x))
    q = lfilter([1 - g], [1, -g], p)
    x2 = x * x
    total = x2.sum()
    if total == 0:
        return 0.0
    plain = math.sqrt(total / n)
    idx = np.arange(n, dtype=np.float64)
    M = 15.9
    prev = None
    for j in range(15):
        thr = 2.0 ** (j - 15)
        last = np.maximum.accumulate(np.where(q >= thr, idx, -np.inf))
        act = (idx - last) <= hang
        cnt = int(act.sum())
        if cnt < sr * 0.05:
            break
        ss = float(x2[act].sum())
        A = 10 * math.log10(ss / cnt)
        C = 20 * math.log10(thr)
        d = A - C
        if d <= M:
            if prev is None:
                return math.sqrt(ss / cnt)
            t = (prev[1] - M) / (prev[1] - d)
            return 10 ** ((prev[0] + t * (A - prev[0])) / 20)
        prev = (A, d)
    return plain


def rms(x):
    x = np.asarray(x, dtype=np.float64)
    return float(np.sqrt(np.mean(x * x))) if x.size else 0.0


# ───────────────────────────── 문장·키 ─────────────────────────────

def sentences():
    import listen_curriculum as L
    out = []
    for f in ("A", "B"):
        for i, s in enumerate(L.TEST_FORMS[f]):
            out.append({"sid": f"{f}{i + 1:02d}", "set": f, "pos": i, "text": s})
    for i, s in enumerate(L.TRAIN_SENTENCES):
        out.append({"sid": L.sentence_id(i), "set": "T", "pos": i, "text": s})
    return out


def tier_specs(tier, sids):
    """(sid, voice, noise, snr, rep) 목록. snr None = 조용함. 문서 6절의 우선순위."""
    snrs = [None] + SNRS
    if tier == 1:
        return [(s, "m3", "babble", x, 0) for s in sids for x in snrs]
    if tier == 2:
        return [(s, "m3", "babble", x, r) for r in (1, 2) for s in sids for x in SNRS]
    if tier == 3:
        return [(s, v, "babble", x, 0) for v in TRAIN_VOICES for s in sids for x in snrs]
    if tier == 4:
        return [(s, "m3", n, x, 0) for n in NOISES[1:] for s in sids for x in SNRS]
    if tier == 5:   # 넓힌 SNR(문서 6절 규칙으로 필요할 때만): 아래 −22·−20·−18, 위 +26·+28·+30
        ext = [-22, -20, -18, 26, 28, 30]
        return [(s, "m3", "babble", x, r) for r in (0, 1, 2) for s in sids for x in ext]
    raise ValueError(tier)


def mix_key(sid, voice, noise, snr, rep):
    return f"{sid}|{voice}|{noise if snr is not None else '-'}|{'q' if snr is None else snr}|{rep}"


def seed_of(*parts):
    return int(hashlib.sha1("\n".join(map(str, parts)).encode()).hexdigest()[:8], 16)


# ───────────────────────────── 섞기·청취자 모의 ─────────────────────────────

def make_mix(speech, sp_level, noise, nz_rms, snr, seed):
    """앱 listenAudio.play와 같은 시간 배치·크기. 48 kHz float64."""
    s_rms, n_rms = mix_levels(GAIN_DB, snr)
    sp = speech * (s_rms / sp_level)
    if snr is None:
        return sp
    lead, ramp, hold = int(LEAD_S * SR_MIX), int(RAMP_S * SR_MIX), int(HOLD_S * SR_MIX)
    n = lead + sp.size + hold + ramp
    rng = np.random.default_rng(seed)
    off = int(rng.uniform(0, max(0.0, noise.size / SR_MIX - 1)) * SR_MIX)   # Math.random() × (길이 − 1초)
    idx = (off + np.arange(n)) % noise.size                                  # loop = true
    nz = noise[idx] * (n_rms / nz_rms)
    env = np.ones(n)
    env[:ramp] = np.linspace(0, 1, ramp, endpoint=False)
    env[n - ramp:] = np.linspace(1, 0, ramp)
    out = nz * env
    out[lead:lead + sp.size] += sp
    return out


def to_16k(x):
    from scipy.signal import resample_poly
    return resample_poly(x, 1, 3)


def greenwood_edges(lo, hi, n, A=165.4, a=2.1, k=0.88):
    pos = lambda f: math.log10(f / A + k) / a
    frq = lambda x: A * (10 ** (a * x) - k)
    xs = np.linspace(pos(lo), pos(hi), n + 1)
    return [frq(x) for x in xs]


_CI = None


def _ci_filters():
    global _CI
    if _CI is None:
        from scipy.signal import butter
        e = greenwood_edges(CI_LO, CI_HI, CI_CH)
        bands = [butter(4, [e[i], e[i + 1]], btype="band", fs=SR_ASR, output="sos") for i in range(CI_CH)]
        lp = butter(4, CI_ENV_HZ, btype="low", fs=SR_ASR, output="sos")
        _CI = (e, bands, lp)
    return _CI


def sim_ci(x, seed):
    """잡음 보코더: 대역 통과(4차 버터워스, 옆마다 24 dB/옥타브) → 반파 정류 → 160 Hz 저역 통과(4차) → 백색 잡음 변조 →
    같은 대역 통과 → 대역 RMS를 원래 대역 RMS에 맞춤 → 합. 인과 필터(처리기처럼)."""
    from scipy.signal import sosfilt
    _, bands, lp = _ci_filters()
    rng = np.random.default_rng(seed)
    out = np.zeros_like(x)
    for sos in bands:
        b = sosfilt(sos, x)
        env = np.maximum(sosfilt(lp, np.maximum(b, 0.0)), 0.0)
        y = sosfilt(sos, env * rng.standard_normal(x.size))
        rb, ry = rms(b), rms(y)
        if ry > 0:
            out += y * (rb / ry)
    return out


_HA = None


def ha_residual_db(f):
    """주파수 f(Hz)에서 남는 손실(dB): S2 − 반이득 = S2/2. 250 Hz 아래·6 kHz 위는 끝값."""
    lf = np.log2(np.clip(f, BISGAARD_F[0], BISGAARD_F[-1]))
    return 0.5 * np.interp(lf, np.log2(BISGAARD_F), BISGAARD_S2)


def _ha_fir():
    global _HA
    if _HA is None:
        from scipy.signal import firwin2
        fr = np.concatenate([[0], np.geomspace(100, SR_ASR / 2 - 1, 80), [SR_ASR / 2]])
        gain = 10 ** (-ha_residual_db(np.maximum(fr, 1)) / 20)
        _HA = firwin2(1025, fr, gain, fs=SR_ASR)
    return _HA


def sim_ha(x, ref_rms, seed):
    """보청기 사용자 모의: 남는 손실만큼 주파수별 감쇠(선형 위상 FIR) + 문턱 잡음(혼합 전체 RMS의 −50 dB 백색)."""
    from scipy.signal import fftconvolve
    h = _ha_fir()
    y = fftconvolve(x, h, mode="full")[len(h) // 2: len(h) // 2 + x.size]
    rng = np.random.default_rng(seed)
    return y + rng.standard_normal(x.size) * ref_rms * amp(HA_FLOOR_DB)


# ───────────────────────────── 띄어쓰기 맞춤 ─────────────────────────────

def respace(target, answer):
    """답의 띄어쓰기를 정답 낱말 경계에 맞춘다(인식기의 띄어쓰기 버릇을 채점에서 뺀다). 숫자는 앱처럼 한국어 읽기로.
    정답 글자와 맞춰진 답 글자는 그 정답 낱말에 붙이고, 낱말 사이에 끼어든 글자는 따로 낱말로 둔다(끼어든 낱말은 감점 없음).
    낱말 안에 끼어든 글자는 그 낱말에 붙여 그 낱말을 틀리게 한다."""
    import re
    from difflib import SequenceMatcher
    from korean_numbers import normalize_numbers
    keep = re.compile(r"[^\w가-힣]")
    tw = [keep.sub("", w) for w in (target or "").split()]
    tw = [w for w in tw if w]
    ans = keep.sub("", normalize_numbers(answer or "").replace(" ", ""))
    if not tw or not ans:
        return ans
    tch, widx = [], []
    for k, w in enumerate(tw):
        tch += list(w)
        widx += [k] * len(w)
    lab = [None] * len(ans)
    for op, i1, i2, j1, j2 in SequenceMatcher(None, tch, list(ans), autojunk=False).get_opcodes():
        if op in ("equal", "replace"):
            for k in range(j1, j2):
                lab[k] = widx[i1 + min(k - j1, i2 - i1 - 1)]
        elif op == "insert":
            inside = 0 < i1 < len(tch) and widx[i1 - 1] == widx[i1]
            for k in range(j1, j2):
                lab[k] = widx[i1] if inside else ("x", i1)
    toks, cur, curlab = [], "", object()
    for ch, l in zip(ans, lab):
        if l != curlab and cur:
            toks.append(cur)
            cur = ""
        cur += ch
        curlab = l
    if cur:
        toks.append(cur)
    return " ".join(toks)


# ───────────────────────────── prep ─────────────────────────────

def decode(path):
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", str(SR_MIX), "-"],
                       capture_output=True, check=True)
    return np.frombuffer(p.stdout, dtype=np.float32).astype(np.float64)


def cmd_prep(a):
    import sound_clips as SC
    os.makedirs(a.work, exist_ok=True)
    man = json.load(open(os.path.join(a.sound, "manifest.json"), encoding="utf-8"))
    items = sentences()
    clips, meta = {}, {}
    for it in items:
        for v in VOICES:
            c = man["clips"][v][SC.normalize_text(it["text"])]
            x = decode(os.path.join(a.sound, "clips", c["id"] + ".ogg"))
            k = f"{it['sid']}|{v}"
            clips["c:" + k] = x.astype(np.float32)
            meta[k] = {"clip": c["id"], "ms": c["ms"], "active": active_level(x, SR_MIX), "rms": rms(x)}
    for nz in NOISES:
        x = decode(os.path.join(a.sound, "noise", nz + ".ogg"))
        clips["n:" + nz] = x.astype(np.float32)
        meta["noise:" + nz] = {"rms": rms(x), "s": x.size / SR_MIX}
    np.savez(os.path.join(a.work, "cache.npz"), **clips)
    json.dump({"items": items, "meta": meta, "engine": man.get("engine"),
               "voices": man.get("voices")}, open(os.path.join(a.work, "items.json"), "w"), ensure_ascii=False, indent=0)
    act = [m["active"] / m["rms"] for k, m in meta.items() if not k.startswith("noise:")]
    print(f"PREP_OK clips={len(meta) - len(NOISES)} active/rms 중앙 {np.median(act):.2f}", flush=True)


# ───────────────────────────── run ─────────────────────────────

_W = {}


def _winit(work):
    z = np.load(os.path.join(work, "cache.npz"))
    _W["z"] = {k: z[k] for k in z.files}          # float32로 두고 쓸 때 넓힌다(프로세스마다 메모리 절약)
    _W["meta"] = json.load(open(os.path.join(work, "items.json"), encoding="utf-8"))["meta"]
    import os as _os
    for v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        _os.environ[v] = "1"


def render(spec):
    """spec(sid, voice, noise, snr, rep) → [(키, 16 kHz float32)] 청취자 셋."""
    sid, voice, noise, snr, rep = spec
    mk = mix_key(sid, voice, noise, snr, rep)
    m = _W["meta"][f"{sid}|{voice}"]
    sp = _W["z"]["c:" + f"{sid}|{voice}"].astype(np.float64)
    nz = _W["z"]["n:" + noise].astype(np.float64)
    x = make_mix(sp, m["active"], nz, _W["meta"]["noise:" + noise]["rms"], snr, seed_of("mix", mk))
    ref = mix_levels(GAIN_DB, snr)
    ref = math.sqrt(ref[0] ** 2 + ref[1] ** 2)
    y = to_16k(x)
    outs = {"nh": y, "ci": sim_ci(y, seed_of("ci", mk)), "ha": sim_ha(y, ref, seed_of("ha", mk))}
    res = []
    for ln, z in outs.items():
        pk = float(np.max(np.abs(z))) or 1.0
        res.append((f"{mk}|{ln}", (z / max(pk, 1.0)).astype(np.float32)))   # 넘치는 경우만 줄인다(Whisper는 크기 정규화)
    return res


class ASR:
    def __init__(self, name, batch):
        import torch
        from transformers import WhisperForConditionalGeneration, WhisperProcessor
        self.torch = torch
        self.proc = WhisperProcessor.from_pretrained(name)
        try:
            m = WhisperForConditionalGeneration.from_pretrained(name, torch_dtype=torch.float16, attn_implementation="sdpa")
        except ImportError:      # torch 2.1.0 이미지는 transformers의 sdpa 조건(≥2.1.1)에 못 미친다
            m = WhisperForConditionalGeneration.from_pretrained(name, torch_dtype=torch.float16, attn_implementation="eager")
        torch.set_default_dtype(torch.float32)     # 실패한 첫 시도가 기본 dtype을 fp16으로 남길 수 있다
        print("ASR attn", m.config._attn_implementation, flush=True)
        self.model = m.to("cuda").eval()
        fe = self.proc.feature_extractor
        self.n_mels = fe.feature_size
        self.filters = torch.tensor(np.asarray(fe.mel_filters), dtype=torch.float32, device="cuda")   # (201, n_mels)
        self.window = torch.hann_window(400, device="cuda", dtype=torch.float32)
        self.batch = batch

    def feats(self, wavs):
        torch = self.torch
        x = torch.zeros(len(wavs), 480000, device="cuda", dtype=torch.float32)
        for i, w in enumerate(wavs):
            w = torch.from_numpy(np.ascontiguousarray(w[:480000], dtype=np.float32)).to("cuda")
            x[i, : w.numel()] = w
        st = torch.stft(x, 400, 160, window=self.window, return_complex=True)
        mag = st[..., :-1].abs() ** 2
        mel = self.filters.T @ mag
        lg = torch.clamp(mel, min=1e-10).log10()
        mx = lg.amax(dim=(1, 2), keepdim=True)
        lg = torch.maximum(lg, mx - 8.0)
        return ((lg + 4.0) / 4.0).half()

    def __call__(self, wavs):
        with self.torch.inference_mode():
            f = self.feats(wavs)
            ids = self.model.generate(input_features=f, language="ko", task="transcribe", max_new_tokens=64,
                                      num_beams=1, do_sample=False)
        return [t.strip() for t in self.proc.batch_decode(ids, skip_special_tokens=True)]


def cmd_run(a):
    import multiprocessing as mp
    info = json.load(open(os.path.join(a.work, "items.json"), encoding="utf-8"))
    sids = [it["sid"] for it in info["items"]]
    outp = os.path.join(a.work, "asr.jsonl")
    done = set()
    if os.path.exists(outp):
        with open(outp, encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(json.loads(line)["key"])
                except ValueError:
                    pass       # 끊긴 마지막 줄
    specs = []
    for t in [int(x) for x in a.tiers.split(",")]:
        for sp in tier_specs(t, sids):
            mk = mix_key(*sp)
            if not all(f"{mk}|{ln}" in done for ln in LISTENERS):
                specs.append(sp)
    print(f"RUN todo_mixes={len(specs)} done_rows={len(done)}", flush=True)
    if not specs:
        print("RUN_OK nothing", flush=True)
        return
    nproc = a.procs or max(1, (os.cpu_count() or 2) - 1)
    buf = []
    nb = [0]
    # 프로세스 풀을 CUDA 초기화 전에 만든다(CUDA가 켜진 프로세스를 fork하지 않게)
    with open(outp, "a", encoding="utf-8") as fo, mp.get_context("fork").Pool(nproc, _winit, (a.work,)) as pool:
        asr = ASR(a.model, a.batch)
        t0 = time.time()
        n_rows = 0
        deadline = t0 + a.max_minutes * 60 if a.max_minutes else None
        def flush():
            nonlocal n_rows
            keys = [k for k, _ in buf]
            txt = asr([w for _, w in buf])
            for k, t in zip(keys, txt):
                if k in done:
                    continue
                fo.write(json.dumps({"key": k, "asr": t}, ensure_ascii=False) + "\n")
                done.add(k)
                n_rows += 1
            fo.flush()
            buf.clear()
        def results():   # 조각마다 imap(결과가 GPU보다 앞서 메모리에 쌓이지 않게)
            for c0 in range(0, len(specs), 1500):
                yield from pool.imap(render, specs[c0:c0 + 1500], chunksize=4)
        for res in results():
            buf += [r for r in res if r[0] not in done]
            if len(buf) >= asr.batch:
                flush()
                nb[0] += 1
                el = time.time() - t0
                if n_rows and nb[0] % 20 == 0:
                    left = (len(specs) * 3 - n_rows) / (n_rows / el)
                    print(f"PROG rows={n_rows} {n_rows / el:.1f}/s eta={left / 60:.1f}min", flush=True)
                if deadline and time.time() > deadline:
                    print("RUN_STOP max-minutes", flush=True)
                    pool.terminate()
                    break
        if buf:
            flush()
    print(f"RUN_OK rows={n_rows} {n_rows / max(1e-9, time.time() - t0):.1f}/s", flush=True)


# ───────────────────────────── score ─────────────────────────────

def cmd_score(a):
    import listen_curriculum as L
    info = json.load(open(os.path.join(a.work, "items.json"), encoding="utf-8"))
    text = {it["sid"]: it["text"] for it in info["items"]}
    rows = {}
    with open(os.path.join(a.work, "asr.jsonl"), encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            rows[r["key"]] = r["asr"]
    with open(os.path.join(a.work, "scored.jsonl"), "w", encoding="utf-8") as fo:
        for k, t in rows.items():
            sid, voice, noise, snr, rep, ln = k.split("|")
            tgt = text[sid]
            raw = L.word_score(tgt, t)["feedback"]
            rs = respace(tgt, t)
            fit = L.word_score(tgt, rs)["feedback"]
            fo.write(json.dumps({"key": k, "sid": sid, "voice": voice, "noise": noise, "snr": None if snr == "q" else int(snr),
                                 "rep": int(rep), "listener": ln, "n": fit["total_words"], "k": fit["correct_words"],
                                 "k_raw": raw["correct_words"], "asr": t, "respaced": rs}, ensure_ascii=False) + "\n")
    print(f"SCORE_OK rows={len(rows)}", flush=True)


# ───────────────────────────── analyze ─────────────────────────────

def fit_curve(x, k, n):
    """p(x) = u / (1 + exp(−4 s (x − m))), 낱말 수 이항 최대가능도. 반환 dict(m, s, u, srt40, srt50, slope50, ok)."""
    from scipy.optimize import minimize
    x, k, n = (np.asarray(v, dtype=float) for v in (x, k, n))
    if not n.sum():
        return {"ok": False}

    def nll(th):
        m, ls, lu = th
        s = math.exp(min(max(ls, -10.0), 3.0))
        u = 0.2 + 0.8 / (1 + math.exp(-min(max(lu, -50.0), 50.0)))
        p = u / (1 + np.exp(np.clip(-4 * s * (x - m), -50, 50)))
        p = np.clip(p, 1e-6, 1 - 1e-6)
        return -float(np.sum(k * np.log(p) + (n - k) * np.log(1 - p)))
    best = None
    for m0 in (-12, -4, 4, 12, 20):
        for s0 in (0.05, 0.15):
            r = minimize(nll, [m0, math.log(s0), 3.0], method="Nelder-Mead",
                         options={"xatol": 1e-3, "fatol": 1e-4, "maxiter": 2000})
            if best is None or r.fun < best.fun:
                best = r
    m, ls, lu = best.x
    s = min(math.exp(min(ls, 3.0)), 2.0)
    u = 0.2 + 0.8 / (1 + math.exp(-min(max(lu, -50.0), 50.0)))

    def srt(q):
        if u <= q + 1e-6:
            return None
        return m + math.log(q / (u - q)) / (4 * s)
    s50 = srt(0.5)
    slope50 = None if s50 is None else 4 * s * 0.5 * (1 - 0.5 / u)   # dp/dx at p = 0.5
    return {"ok": True, "m": m, "s": s, "u": u, "srt40": srt(0.4), "srt50": s50, "slope50": slope50, "nll": best.fun}


def boot_ci(f, data, B=10000, seed=0):
    rng = np.random.default_rng(seed)
    data = np.asarray(data, dtype=float)
    est = f(data)
    bs = np.array([f(data[rng.integers(0, len(data), len(data))]) for _ in range(B)])
    return est, float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))


def cmd_analyze(a):
    info = json.load(open(os.path.join(a.work, "items.json"), encoding="utf-8"))
    items = {it["sid"]: it for it in info["items"]}
    sids = [it["sid"] for it in info["items"]]
    test_sids = [s for s in sids if items[s]["set"] in "AB"]
    rows = [json.loads(l) for l in open(os.path.join(a.work, "scored.jsonl"), encoding="utf-8")]
    kk = "k_raw" if a.raw else "k"
    by = {}
    quiet = {}
    for r in rows:
        if r["snr"] is None:
            quiet[(r["sid"], r["voice"], r["listener"])] = (r[kk], r["n"])
            continue
        by.setdefault((r["sid"], r["voice"], r["noise"], r["listener"]), []).append((r["rep"], r["snr"], r[kk], r["n"]))

    def fit_of(sid, voice, noise, ln, reps):
        d = [t for t in by.get((sid, voice, noise, ln), []) if t[0] in reps]
        if len({t[1] for t in d}) < 10:
            return None
        return fit_curve([t[1] for t in d], [t[2] for t in d], [t[3] for t in d])

    res = {"config": {"snrs": SNRS, "voices": VOICES, "noises": NOISES, "listeners": LISTENERS, "score": kk,
                      "ci": {"channels": CI_CH, "lo": CI_LO, "hi": CI_HI, "env_hz": CI_ENV_HZ,
                             "edges_hz": [round(e, 1) for e in greenwood_edges(CI_LO, CI_HI, CI_CH)]},
                      "ha": {"audiogram": "Bisgaard 2010 S2", "f": BISGAARD_F, "hl": BISGAARD_S2,
                             "residual_db": [float(ha_residual_db(f)) for f in BISGAARD_F], "floor_db": HA_FLOOR_DB},
                      "engine": info.get("engine"), "n_rows": len(rows)}}
    fits = {}
    reps_all = sorted({t[0] for v in by.values() for t in v})
    for (sid, voice, noise, ln) in sorted(by):
        if voice == "m3" and noise == "babble":
            fits[(sid, voice, noise, ln, "all")] = fit_of(sid, voice, noise, ln, set(reps_all))
            for r in reps_all:
                fits[(sid, voice, noise, ln, r)] = fit_of(sid, voice, noise, ln, {r})
        else:
            fits[(sid, voice, noise, ln, 0)] = fit_of(sid, voice, noise, ln, {0})
    res["fits"] = [{"sid": k[0], "voice": k[1], "noise": k[2], "listener": k[3], "reps": k[4],
                    **{q: (None if v is None else (round(v[q], 3) if isinstance(v.get(q), float) else v.get(q)))
                       for q in ("srt40", "srt50", "slope50", "u", "m", "s")}}
                   for k, v in fits.items() if v and v.get("ok")]

    def val(sid, voice, noise, ln, reps, q="srt40"):
        f = fits.get((sid, voice, noise, ln, reps))
        return None if not f or not f.get("ok") else f.get(q)

    # 조용한 곳 점검
    res["quiet"] = {}
    for ln in LISTENERS:
        for v in VOICES:
            qs = [(sid, *quiet[(sid, v, ln)]) for sid in sids if (sid, v, ln) in quiet]
            if qs:
                res["quiet"][f"{v}|{ln}"] = {"mean_prop": round(float(np.mean([k / n for _, k, n in qs])), 3),
                                              "fail": [s for s, k, n in qs if k < n] if v == "m3" else len([1 for _, k, n in qs if k < n])}
    # 격자 끝 점검(6절 규칙): m3 babble 전체 적합의 SRT50이 [격자 아래 + 4, 위 − 4] 밖인 문장 비율
    res["grid_check"] = {}
    for ln in LISTENERS:
        v = [val(s, "m3", "babble", ln, "all", "srt50") for s in sids]
        out = [x for x in v if x is None or x < SNRS[0] + 4 or x > SNRS[-1] - 4]
        res["grid_check"][ln] = {"n": len(v), "outside": len(out), "frac": round(len(out) / max(1, len(v)), 3),
                                 "low": sum(1 for x in v if x is not None and x < SNRS[0] + 4),
                                 "high_or_none": sum(1 for x in v if x is None or x > SNRS[-1] - 4)}

    # (i) 폼 균형
    def form_delta(ln, reps, q="srt40", swaps=()):
        A = [val(f"A{i + 1:02d}", "m3", "babble", ln, reps, q) for i in range(20)]
        B = [val(f"B{i + 1:02d}", "m3", "babble", ln, reps, q) for i in range(20)]
        for i in swaps:
            A[i], B[i] = B[i], A[i]
        pairs = [(x, y) for x, y in zip(A, B) if x is not None and y is not None]
        return A, B, pairs
    res["forms"] = {}
    for ln in LISTENERS:
        for q in ("srt40", "srt50"):
            A, B, pairs = form_delta(ln, "all", q)
            if len(pairs) < 10:
                continue
            d = np.array([x - y for x, y in pairs])
            est, lo, hi = boot_ci(np.mean, d)
            # 짝 없이(폼 안에서 따로 다시 뽑기)
            rng = np.random.default_rng(1)
            a_, b_ = np.array([x for x, _ in pairs]), np.array([y for _, y in pairs])
            bs = [a_[rng.integers(0, len(a_), len(a_))].mean() - b_[rng.integers(0, len(b_), len(b_))].mean() for _ in range(10000)]
            res["forms"][f"{ln}|{q}"] = {"mean_A": round(float(a_.mean()), 2), "mean_B": round(float(b_.mean()), 2),
                                        "delta": round(est, 2), "ci_paired": [round(lo, 2), round(hi, 2)],
                                        "ci_unpaired": [round(float(np.percentile(bs, 2.5)), 2), round(float(np.percentile(bs, 97.5)), 2)],
                                        "n_pairs": len(pairs), "pair_d": [None if (x is None or y is None) else round(x - y, 2) for x, y in zip(A, B)]}
    exceed = [ln for ln in LISTENERS if f"{ln}|srt40" in res["forms"] and abs(res["forms"][f"{ln}|srt40"]["delta"]) > 0.5]
    signs = {np.sign(res["forms"][f"{ln}|srt40"]["delta"]) for ln in exceed}
    imbalance = len(exceed) >= 2 and len(signs) == 1
    res["form_verdict"] = {"exceed": exceed, "imbalance": bool(imbalance)}
    # 짝 맞바꾸기: rep 0으로 고르고 rep 1·2로 확인
    if imbalance:
        def deltas(reps, swaps):
            out = {}
            for ln in LISTENERS:
                _, _, pairs = form_delta(ln, reps, "srt40", swaps)
                out[ln] = float(np.mean([x - y for x, y in pairs])) if pairs else None
            return out
        verify_reps = [r for r in reps_all if r != 0]
        cand = []
        for size in range(1, 5):
            for sw in itertools.combinations(range(20), size):
                d0 = deltas(0, sw)
                if None in d0.values():
                    continue
                cand.append((max(abs(v) for v in d0.values()), size, sw, d0))
        cand.sort(key=lambda c: (round(c[0], 2), c[1]))
        chosen = cand[0] if cand else None
        vr = None
        if chosen and verify_reps:
            # 확인 반복의 합동 적합(rep 1·2)
            for (sid, voice, noise, ln) in sorted(by):
                if voice == "m3" and noise == "babble" and items[sid]["set"] in "AB":
                    fits[(sid, voice, noise, ln, "ver")] = fit_of(sid, voice, noise, ln, set(verify_reps))
            vr = {"before": deltas("ver", ()), "after": deltas("ver", chosen[2])}
        res["swap"] = None if not chosen else {
            "positions": [i + 1 for i in chosen[2]], "max_abs_delta_rep0": round(chosen[0], 2),
            "delta_rep0": {k: round(v, 2) for k, v in chosen[3].items()},
            "verify": None if vr is None else {k: {ln: (None if x is None else round(x, 2)) for ln, x in v.items()} for k, v in vr.items()}}
        if vr:
            aft, bef = vr["after"], vr["before"]
            ok_all = all(x is not None and abs(x) <= 0.5 for x in aft.values())
            better = sum(1 for ln in LISTENERS if aft[ln] is not None and bef[ln] is not None and abs(aft[ln]) < abs(bef[ln]))
            res["swap"]["accepted"] = bool(ok_all and better >= 2)

    # (ii) 튀는 문장: 140문장 합동(m3 babble 전체 반복), 평균 ± 2 SD 밖
    res["outliers"] = {}
    for ln in LISTENERS:
        v = {s: val(s, "m3", "babble", ln, "all") for s in sids}
        xs = np.array([x for x in v.values() if x is not None])
        mu, sd = float(xs.mean()), float(xs.std(ddof=1))
        res["outliers"][ln] = {"mean": round(mu, 2), "sd": round(sd, 2),
                               "none": [s for s, x in v.items() if x is None],
                               "out": sorted([{"sid": s, "srt40": round(x, 2), "z": round((x - mu) / sd, 2), "text": items[s]["text"]}
                                              for s, x in v.items() if x is not None and abs(x - mu) > 2 * sd], key=lambda e: e["z"])}

    # (iii) 소음 종류: m3, rep 0, 문장 140, 문장마다 짝지은 차이
    res["noise_order"] = {}
    for ln in LISTENERS:
        per = {}
        for nz in NOISES:
            per[nz] = {s: val(s, "m3", nz, ln, 0) for s in sids}
        common = [s for s in sids if all(per[nz][s] is not None for nz in NOISES)]
        if len(common) < 20:
            continue
        means = {nz: float(np.mean([per[nz][s] for s in common])) for nz in NOISES}
        order = sorted(NOISES, key=lambda nz: means[nz])
        adj = []
        for a_, b_ in zip(order, order[1:]):
            d = [per[b_][s] - per[a_][s] for s in common]
            est, lo, hi = boot_ci(np.mean, d, B=4000)
            adj.append({"easier": a_, "harder": b_, "diff": round(est, 2), "ci": [round(lo, 2), round(hi, 2)]})
        res["noise_order"][ln] = {"n": len(common), "mean_srt40": {k: round(v, 2) for k, v in means.items()},
                                  "order_easy_to_hard": order, "adjacent": adj}

    # (iv) 목소리: babble, rep 0
    res["voices"] = {}
    for ln in LISTENERS:
        per = {v: {s: val(s, v, "babble", ln, 0) for s in sids} for v in VOICES}
        common = [s for s in sids if all(per[v][s] is not None for v in VOICES)]
        if len(common) < 20:
            continue
        means = {v: float(np.mean([per[v][s] for s in common])) for v in VOICES}
        d = [per["m3"][s] - np.mean([per[v][s] for v in TRAIN_VOICES]) for s in common]
        est, lo, hi = boot_ci(np.mean, d, B=4000)
        tr = [means[v] for v in TRAIN_VOICES]
        flag = (abs(est) > 1.0 and (lo > 0 or hi < 0)) or means["m3"] < min(tr) - 0.5 or means["m3"] > max(tr) + 0.5
        res["voices"][ln] = {"n": len(common), "mean_srt40": {k: round(v, 2) for k, v in means.items()},
                             "m3_minus_train": round(est, 2), "ci": [round(lo, 2), round(hi, 2)], "unusual": bool(flag)}

    # (v) 문장 난이도 SD(m3 babble): 관측 SD − 추정 오차(반복 사이 분산/반복 수)
    res["difficulty_sd"] = {}
    for ln in LISTENERS:
        for q in ("srt40", "srt50"):
            for pool_name, pool in (("all140", sids), ("test40", test_sids)):
                allv = {s: val(s, "m3", "babble", ln, "all", q) for s in pool}
                xs = np.array([x for x in allv.values() if x is not None])
                if len(xs) < 10:
                    continue
                within = []
                for s in pool:
                    rv = [val(s, "m3", "babble", ln, r, q) for r in reps_all]
                    rv = [x for x in rv if x is not None]
                    if len(rv) >= 2:
                        within.append(np.var(rv, ddof=1))
                err = float(np.mean(within)) / max(1, len(reps_all)) if within else None
                obs = float(xs.std(ddof=1))
                true = None if err is None else math.sqrt(max(0.0, obs ** 2 - err))
                res["difficulty_sd"][f"{ln}|{q}|{pool_name}"] = {
                    "n": len(xs), "sd_obs": round(obs, 2), "err_var": None if err is None else round(err, 3),
                    "sd_true": None if true is None else round(true, 2),
                    "rep_sd_single": None if not within else round(math.sqrt(float(np.mean(within))), 2),
                    "slope50_median": round(float(np.median([val(s, "m3", "babble", ln, "all", "slope50") for s in pool
                                                             if val(s, "m3", "babble", ln, "all", "slope50") is not None])), 3)}
    # 청취자 모의 사이 문장 난이도 상관(스피어만)
    from scipy.stats import spearmanr
    res["listener_corr"] = {}
    for l1, l2 in itertools.combinations(LISTENERS, 2):
        pr = [(val(s, "m3", "babble", l1, "all"), val(s, "m3", "babble", l2, "all")) for s in sids]
        pr = [p for p in pr if None not in p]
        if len(pr) >= 10:
            res["listener_corr"][f"{l1}-{l2}"] = round(float(spearmanr([p[0] for p in pr], [p[1] for p in pr])[0]), 3)
    # 띄어쓰기 맞춤이 바꾼 낱말 비율
    if rows:
        res["respace_effect"] = {"k_mean": round(float(np.mean([r["k"] / r["n"] for r in rows])), 4),
                                 "k_raw_mean": round(float(np.mean([r["k_raw"] / r["n"] for r in rows])), 4)}
    json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"ANALYZE_OK {a.out} fits={len(res['fits'])}", flush=True)


# ───────────────────────────── jfactor ─────────────────────────────
# 문장당 독립 요소 수 j(Boothroyd·Nittrouer 1988, Brand·Kollmeier 2002). 문서 'j 추정' 절.

def _model_cells(s_cond, eps_sd, n, xs_rel, R=3, n_sent=4000, sd_d=0.0, seed=0):
    """시뮬레이션 모형(docs/listen-adaptive-sim-2026-10.md 2.1·2.3): p = 1/(1+exp(−4 s (x − δ − ε))), 낱말 독립.
    문장 n_sent개 × 상대 SNR xs_rel × 제시 R번의 맞힌 낱말 수 k[s, x, r]."""
    rng = np.random.default_rng(seed)
    d = rng.normal(0, sd_d, (n_sent, 1, 1))
    e = rng.normal(0, eps_sd, (n_sent, len(xs_rel), R))
    x = np.asarray(xs_rel, dtype=float)[None, :, None]
    p = 1 / (1 + np.exp(-4 * s_cond * (x - d - e)))
    return rng.binomial(n, p)


def _phi_within(k, n, mask=None):
    """같은 문장·같은 SNR의 반복 사이 분산 ÷ 이항 분산(불편 추정). k[..., r], mask[...]는 쓸 칸."""
    R = k.shape[-1]
    kb = k.mean(-1)
    s2 = k.var(-1, ddof=1)
    N = n * R
    ph = kb / n
    bvar = n * ph * (1 - ph) * N / (N - 1)
    if mask is None:
        mask = np.ones(kb.shape, bool)
    mask = mask & (bvar > 0)
    return float(s2[mask].sum() / bvar[mask].sum()) if mask.any() else float("nan"), int(mask.sum())


def _jbn(k, n, mask):
    """Boothroyd·Nittrouer j = ln P(문장 전부 맞음) / ln P(낱말 맞음), 칸 합동."""
    kk = k[mask]
    pw = kk.sum() / (kk.size * n)
    ps = (kk == n).mean()
    return float(np.log(ps) / np.log(pw)) if 0 < ps < 1 and 0 < pw < 1 else float("nan")


def cmd_jfactor(a):
    res = json.load(open(a.result, encoding="utf-8"))
    fits = {(f["sid"], f["listener"]): f for f in res["fits"]
            if f["voice"] == "m3" and f["noise"] == "babble" and f["reps"] == "all"}
    rows = [json.loads(l) for l in open(os.path.join(a.work, "scored.jsonl"), encoding="utf-8")]
    kk = "k_raw" if a.raw else "k"
    cell = {}
    for r in rows:
        if r["voice"] == "m3" and r["noise"] == "babble" and r["snr"] is not None:
            cell.setdefault((r["sid"], r["listener"], r["snr"]), {})[r["rep"]] = (r[kk], r["n"])
    out = {"score": kk, "listeners": {}}
    xs_rel = np.arange(-6, 6.01, 2.0)
    for ln in LISTENERS:
        L_out = {}
        for n in (3, 4):
            ks, prow, xrel, sl = [], [], [], []
            for (sid, l, x), v in cell.items():
                if l != ln or len(v) < 3 or v[0][1] != n:
                    continue
                f = fits.get((sid, ln))
                if not f or f.get("srt50") is None:
                    continue
                pf = f["u"] / (1 + math.exp(-4 * f["s"] * (x - f["m"])))
                ks.append([v[r][0] for r in (0, 1, 2)])
                prow.append(pf)
                xrel.append(x - f["srt50"])
                sl.append(f["slope50"])
            if len(ks) < 30:
                continue
            ks, prow, xrel = np.array(ks), np.array(prow), np.array(xrel)
            win = (prow >= 0.25) & (prow <= 0.75)
            win2 = np.abs(xrel) <= 2.0
            phi, ncell = _phi_within(ks, n, win)
            phi2, ncell2 = _phi_within(ks, n, win2)
            jbn = _jbn(ks, n, win)
            s_marg = float(np.median([x for x in sl if x is not None]))   # 문장 적합 기울기(50%, 비율/dB)
            # 모형 맞추기: 흔들림 SD마다 조건부 기울기를 골라 주변 기울기를 관측값에 맞춘 뒤 같은 추정량의 φ를 계산
            cal = []
            for eps in np.arange(0.0, 8.01, 0.5):
                lo_s, hi_s = 0.01, 3.0
                for _ in range(30):     # 주변 기울기(제시 흔들림을 섞은 50% 기울기)를 관측값에 맞추는 이분법
                    mid = 0.5 * (lo_s + hi_s)
                    z = np.random.default_rng(1).normal(0, eps, 20000)
                    h = 0.05
                    pm = lambda xx: np.mean(1 / (1 + np.exp(-4 * mid * (xx - z))))
                    sm = (pm(h) - pm(-h)) / (2 * h)
                    if sm < s_marg:
                        lo_s = mid
                    else:
                        hi_s = mid
                s_c = 0.5 * (lo_s + hi_s)
                km = _model_cells(s_c, eps, n, xs_rel, seed=int(eps * 10) + n)
                # 모형 칸의 p(주변)로 같은 창을 쓴다
                pmv = np.array([np.mean(1 / (1 + np.exp(-4 * s_c * (xx - np.random.default_rng(2).normal(0, eps, 20000))))) for xx in xs_rel])
                mwin = np.broadcast_to(((pmv >= 0.25) & (pmv <= 0.75))[None, :], km.shape[:2])
                phm, _ = _phi_within(km, n, mwin)
                cal.append({"eps_sd": float(eps), "s_cond": round(s_c, 3), "phi": round(phm, 3), "jbn": round(_jbn(km, n, mwin), 3)})
            # 관측 φ에 맞는 흔들림(선형 보간)
            phis = np.array([c["phi"] for c in cal])
            epss = np.array([c["eps_sd"] for c in cal])
            order = np.argsort(phis)
            eps_hat = float(np.interp(phi, phis[order], epss[order])) if np.isfinite(phi) else None
            # 그 흔들림을 시뮬레이션 기울기 0.10(조건부)에 넣으면 j는?
            j_sim = None
            if eps_hat is not None:
                kms = _model_cells(0.10, eps_hat, n, xs_rel, seed=99)
                pmv = np.array([np.mean(1 / (1 + np.exp(-4 * 0.10 * (xx - np.random.default_rng(2).normal(0, eps_hat, 20000))))) for xx in xs_rel])
                mwin = np.broadcast_to(((pmv >= 0.25) & (pmv <= 0.75))[None, :], kms.shape[:2])
                j_sim = n / _phi_within(kms, n, mwin)[0]
            # 부트스트랩(문장 단위)
            sids_arr = np.array([sid for (sid, l, x), v in cell.items() if l == ln and len(v) >= 3 and v[0][1] == n
                                 and fits.get((sid, ln)) and fits[(sid, ln)].get("srt50") is not None])
            uniq = np.unique(sids_arr)
            rng = np.random.default_rng(0)
            bs = []
            for _ in range(2000):
                pick = rng.choice(uniq, len(uniq))
                cnt = {u: c for u, c in zip(*np.unique(pick, return_counts=True))}
                w = np.array([cnt.get(s_, 0) for s_ in sids_arr])
                kb = ks.mean(-1)
                s2 = ks.var(-1, ddof=1)
                N = n * 3
                bvar = n * (kb / n) * (1 - kb / n) * N / (N - 1)
                m_ = win & (bvar > 0)
                bs.append((s2 * w)[m_].sum() / (bvar * w)[m_].sum())
            lo, hi = np.percentile(bs, [2.5, 97.5])
            L_out[f"n{n}"] = {"cells": ncell, "phi": round(phi, 3), "phi_ci": [round(float(lo), 3), round(float(hi), 3)],
                              "j_od": round(n / phi, 2), "j_od_ci": [round(n / float(hi), 2), round(n / float(lo), 2)],
                              "phi_win2db": round(phi2, 3), "cells_win2db": ncell2, "j_od_win2db": round(n / phi2, 2),
                              "j_bn": round(jbn, 2), "slope50_marg_median": round(s_marg, 3),
                              "eps_sd_hat": None if eps_hat is None else round(eps_hat, 2),
                              "j_at_sim_slope_0.10": None if j_sim is None else round(j_sim, 2), "calibration": cal}
        out["listeners"][ln] = L_out
    # 참고: 시뮬레이션 조건 C3(흔들림 2 dB)·C5(4 dB), 기울기 0.10, 4어절에서 같은 추정량
    ref = {}
    for nm, eps in (("C0", 0.0), ("C3", 2.0), ("C5", 4.0)):
        km = _model_cells(0.10, eps, 4, xs_rel, seed=7)
        pmv = np.array([np.mean(1 / (1 + np.exp(-4 * 0.10 * (xx - np.random.default_rng(2).normal(0, max(eps, 1e-9), 20000))))) for xx in xs_rel])
        mwin = np.broadcast_to(((pmv >= 0.25) & (pmv <= 0.75))[None, :], km.shape[:2])
        ph = _phi_within(km, 4, mwin)[0]
        ref[nm] = {"eps_sd": eps, "phi": round(ph, 3), "j_od": round(4 / ph, 2), "j_bn": round(_jbn(km, 4, mwin), 2)}
    out["sim_reference_s0.10_n4"] = ref
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("JFACTOR_OK", a.out, flush=True)


# ───────────────────────────── selftest·dump ─────────────────────────────

def cmd_selftest(a):
    sr = SR_MIX
    rng = np.random.default_rng(0)
    t = np.arange(int(2.0 * sr)) / sr
    tone = 0.1 * np.sin(2 * np.pi * 440 * t)
    sig = np.concatenate([np.zeros(sr), tone, np.zeros(sr)])     # 1초 무음 + 2초 + 1초 무음
    al, pr = active_level(sig, sr), rms(sig)
    assert abs(20 * math.log10(al / (0.1 / math.sqrt(2)))) < 1.0, al          # 활성 구간(유지 0.2초 포함) 레벨 ≈ 사인 RMS
    assert al > pr * 1.3
    s, n = mix_levels(-10, 0)
    assert abs(s - n) < 1e-12 and abs(math.hypot(s, n) - amp(-30)) < 1e-12
    assert respace("우리 집은 삼 층이에요.", "우리 집은 3층이에요") == "우리 집은 삼 층이에요"
    assert respace("냉면을 두 그릇 시켰어요.", "냉면을2그릇시켰어요.") == "냉면을 두 그릇 시켰어요"
    assert respace("시계가 오 분 빨라요.", "시계가 오분 아주 빨라요") == "시계가 오 분 아주 빨라요"
    assert respace("책상 위에 열쇠가 있어요.", "책상 위에 열쇄가 있어요") == "책상 위에 열쇄가 있어요"
    y = rng.standard_normal(SR_ASR)
    c = sim_ci(y, 1)
    assert c.shape == y.shape and rms(c) > 0
    from scipy.signal import welch
    h = sim_ha(y, rms(y), 2)
    f, P0 = welch(y, SR_ASR, nperseg=1024)
    _, P1 = welch(h, SR_ASR, nperseg=1024)
    att = 10 * np.log10(P1 / P0)
    a1, a4 = att[np.argmin(abs(f - 1000))], att[np.argmin(abs(f - 4000))]
    assert abs(a1 + 12.5) < 2 and abs(a4 + 47.5) < 4, (a1, a4)
    print("greenwood", [round(e) for e in greenwood_edges(CI_LO, CI_HI, CI_CH)])
    print(f"ha atten 1k {a1:.1f} 4k {a4:.1f}")
    try:
        import listen_curriculum as L
        assert L.word_score("우리 집은 삼 층이에요.", respace("우리 집은 삼 층이에요.", "우리 집은 3층이에요"))["proportion"] == 1.0
    except ImportError:
        print("listen_curriculum 없음(채점 점검 생략)")
    print("SELFTEST_OK", flush=True)


def cmd_dump(a):
    import soundfile as sf
    _winit(a.work)
    sid, voice, noise, snr, rep, ln = a.key.split("|")
    spec = (sid, voice, noise, None if snr == "q" else int(snr), int(rep))
    for k, w in render(spec):
        if k.endswith("|" + ln):
            sf.write(a.out, w, SR_ASR)
            print("DUMP_OK", a.out)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("selftest")
    p = sub.add_parser("prep"); p.add_argument("--sound", required=True); p.add_argument("--work", required=True)
    p = sub.add_parser("run"); p.add_argument("--work", required=True); p.add_argument("--tiers", default="1,2,3,4")
    p.add_argument("--max-minutes", type=float, default=0); p.add_argument("--batch", type=int, default=64)
    p.add_argument("--procs", type=int, default=0); p.add_argument("--model", default="openai/whisper-large-v3-turbo")
    p = sub.add_parser("score"); p.add_argument("--work", required=True)
    p = sub.add_parser("analyze"); p.add_argument("--work", required=True); p.add_argument("--out", required=True)
    p.add_argument("--raw", action="store_true", help="띄어쓰기 맞춤 없이 그대로 채점한 값으로")
    p = sub.add_parser("jfactor"); p.add_argument("--work", required=True); p.add_argument("--result", required=True)
    p.add_argument("--out", required=True); p.add_argument("--raw", action="store_true")
    p = sub.add_parser("dump"); p.add_argument("--work", required=True); p.add_argument("--key", required=True); p.add_argument("--out", required=True)
    a = ap.parse_args()
    {"selftest": cmd_selftest, "prep": cmd_prep, "run": cmd_run, "score": cmd_score, "analyze": cmd_analyze, "jfactor": cmd_jfactor, "dump": cmd_dump}[a.cmd](a)


if __name__ == "__main__":
    main()
