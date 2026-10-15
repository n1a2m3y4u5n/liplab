"""동적 문장 합성기(C17, 기본 끔). 고정 소리와 같은 엔진(Supertonic 3, ONNX)으로 서버 CPU에서 합성한다.

`supertonic` 패키지가 설치돼 있고 LIPLAB_SOUND_DYNAMIC=1일 때만 쓴다. 이미지에는 Dockerfile의 WITH_SOUND_TTS=1 빌드에서만 들어간다.
메모리·지연·품질 측정과 판정은 docs/listen-convo-tts-2026-10.md.
합성한 소리는 미리 합성한 클립과 같게 정리하고(앞뒤 무음 150 ms, 활성 레벨 −24 dBFS, sound_gate.postprocess), 실행 중 품질 게이트
(sound_gate.judge)를 거친다. 인코딩은 faster-whisper가 이미 쓰는 PyAV로 한다(ogg/opus 24kbps, m4a/aac 24kbps, 모노). 음절 시각과 D-GOP는
이미 올라와 있는 정렬기·채점기로 얻는다.
"""
import io
import os
import threading
import time
from typing import Dict, List, Optional, Tuple

import numpy as np

_tts = None
_styles: Dict[str, object] = {}
_lock = threading.Lock()
THREADS = int(os.getenv("LIPLAB_SOUND_THREADS", "2") or 2)
LOAD_SECONDS: Optional[float] = None


def available() -> bool:
    try:
        import supertonic  # noqa: F401
        import av  # noqa: F401
        return True
    except Exception:
        return False


def loaded() -> bool:
    return _tts is not None


def _load():
    global _tts, LOAD_SECONDS
    if _tts is None:
        with _lock:
            if _tts is None:
                t0 = time.time()
                os.environ.setdefault("OMP_NUM_THREADS", str(THREADS))
                from supertonic import TTS
                # ONNX Runtime 스레드를 정한다. 정하지 않으면 보이는 코어 수만큼 띄워, 할당이 그보다 적은 기계에서 수십 배 느려진다(파드 실측)
                _tts = TTS(auto_download=os.getenv("HF_HUB_OFFLINE") != "1", intra_op_num_threads=THREADS, inter_op_num_threads=1)
                LOAD_SECONDS = round(time.time() - t0, 2)
    return _tts


def warm() -> None:
    """예열(LIPLAB_WARMUP=1이고 합성이 켜졌을 때): 엔진을 올리고 짧은 글을 한 번 합성해 ONNX 첫 실행 비용을 미리 치른다."""
    tts = _load()
    with _lock:
        st = tts.get_voice_style(voice_name="M1")
        tts.synthesize("안녕하세요.", voice_style=st, lang="ko")


def _resample(x: np.ndarray, sr: int, to: int) -> np.ndarray:
    """PyAV 리샘플러. 정렬기는 16kHz를 받는다."""
    import av
    frame = av.AudioFrame.from_ndarray(x.astype(np.float32)[None, :], format="flt", layout="mono")
    frame.sample_rate = sr
    rs = av.AudioResampler(format="flt", layout="mono", rate=to)
    out = [f.to_ndarray().reshape(-1) for f in rs.resample(frame)]
    out += [f.to_ndarray().reshape(-1) for f in rs.resample(None)]
    return np.concatenate(out) if out else np.zeros(0, np.float32)


def to16k(x: np.ndarray, sr: int) -> np.ndarray:
    return _resample(x, sr, 16000) if sr != 16000 else np.asarray(x, np.float32)


def encode(x: np.ndarray, sr: int) -> Dict[str, bytes]:
    """모노 float32 → {'ogg': opus 24kbps 48kHz, 'm4a': aac 24kbps 24kHz}. 고정 소리(파드의 ffmpeg 인코딩)와 같은 설정이다."""
    import av
    out = {}
    for ext, fmt, codec, rate, br in (("ogg", "ogg", "libopus", 48000, 24000), ("m4a", "mp4", "aac", 24000, 24000)):
        y = _resample(x, sr, rate) if sr != rate else x
        buf = io.BytesIO()
        with av.open(buf, "w", format=fmt) as c:
            st = c.add_stream(codec, rate=rate)
            st.bit_rate = br
            st.layout = "mono"
            fr = av.AudioFrame.from_ndarray(np.clip(y, -1, 1).astype(np.float32)[None, :], format="flt", layout="mono")
            fr.sample_rate = rate
            for pkt in st.encode(fr):
                c.mux(pkt)
            for pkt in st.encode(None):
                c.mux(pkt)
        out[ext] = buf.getvalue()
    return out


def trim_silence(x: np.ndarray, sr: int, margin_ms: int = 100, rel_db: float = -45.0) -> np.ndarray:
    """앞뒤 무음 자르기(10ms 창 RMS가 최대보다 45dB 낮은 구간, 앞뒤 100ms 남김). 10/7 첫 합성(scripts/sound_pod/synth.py)의 규칙.
    지금 합성 경로는 sound_gate.postprocess를 쓴다(품질 점검 뒤 고정 소리와 같은 정리)."""
    w = max(1, int(sr * 0.01))
    n = len(x) // w
    if n < 3:
        return x
    rms = np.sqrt(np.mean(x[:n * w].reshape(n, w) ** 2, axis=1) + 1e-12)
    on = np.where(rms > rms.max() * (10 ** (rel_db / 20)))[0]
    if not on.size:
        return x
    m = int(sr * margin_ms / 1000)
    return x[max(0, on[0] * w - m):min(len(x), (on[-1] + 1) * w + m)]


def synthesize_raw(text: str, voice: str, steps: int = 8, speed: float = 1.05, seed: int = 0) -> Tuple[np.ndarray, int]:
    """글 → (합성 원본 float32, 엔진 표본율). 시드는 엔진이 쓰는 numpy 전역 난수(10/7 점검과 같은 방식, 잠금 안에서 정한다)."""
    tts = _load()
    with _lock:
        style = _styles.get(voice)
        if style is None:
            style = _styles[voice] = tts.get_voice_style(voice_name=voice)
        np.random.seed(int(seed))
        wav, _dur = tts.synthesize(text, voice_style=style, lang="ko", total_steps=int(steps), speed=float(speed))
        sr = int(getattr(tts, "sample_rate", None) or 44100)
    return np.asarray(wav, dtype=np.float32).reshape(-1), sr


def phones_for(wav16: np.ndarray, text: str) -> Tuple[Optional[List[Dict]], Optional[List[str]], Optional[float]]:
    """정렬기(DGOP_ALIGNER_ID)·채점기(DGOP_SCORER_ID)로 (자모 구간, 토큰, D-GOP 표시 점수). 정렬기가 없거나 실패하면 (None, 토큰, None)."""
    aligner = os.getenv("DGOP_ALIGNER_ID") or os.getenv("DGOP_MODEL_ID")
    try:
        import jamo_vocab
        toks = jamo_vocab.text_to_tokens(text)
    except Exception:
        return None, None, None
    if not aligner:
        return None, toks, None
    try:
        import dgop
        import dgop_acoustic as DA
        if not DA.HAS_ACOUSTIC:
            return None, toks, None
        scorer = os.getenv("DGOP_SCORER_ID") or aligner
        if DA.tokens_for_text(text, model_id=aligner) != toks:
            return None, toks, None
        phones = DA.phone_confidences(wav16, 16000, toks, aligner_id=aligner, scorer_id=scorer)
        scored = [p for p in phones if p.get("aligned") and p.get("scorable")]
        S = None
        if scored:
            raw = dgop.sentence_dgop(scored)["score"]
            S = dgop.calibrate_score(raw, DA.load_calibration(DA.calibration_path_for(scorer)))
        return phones, toks, S
    except Exception as e:
        print(f"[WARN] 소리 정렬 실패: {type(e).__name__}: {e}")
        return None, toks, None


def make_clip(text: str, tts_text: str, engine_voice: str, voice_id: str, keep_rejected: bool = False) -> Dict:
    """글 하나를 두 후보까지 합성·정리·게이트한다(docs/listen-convo-tts-2026-10.md 4절).
    돌려주는 값: {ok, files(통과일 때 인코딩), ms, syl, q{tier,flags,dgop,cand,…}, tries[...], rejected_files(측정용)}."""
    import sound_gate as G
    tries = []
    best = None
    for ci, (steps, speed, seed) in enumerate(G.CANDIDATES):
        t0 = time.time()
        raw, sr = synthesize_raw(tts_text, engine_voice, steps, speed, seed)
        y, info = G.postprocess(raw, sr)
        if info.get("empty"):
            tries.append({"cand": f"c{ci}", "tier": "fail", "flags": ["fail:empty"], "sec": round(time.time() - t0, 3)})
            continue
        wav16 = to16k(y, sr)
        phones, toks, S = phones_for(wav16, text)
        q = G.judge(text, voice_id, y, sr, info.get("raw_level_db"), phones, toks or [], S)
        q.update({"cand": f"c{ci}", "raw_level_db": info.get("raw_level_db"), "sec": round(time.time() - t0, 3)})
        tries.append({k: q[k] for k in ("cand", "tier", "flags", "dgop", "sec")})
        rec = {"q": q, "y": y, "sr": sr}
        if q["tier"] == "pass":
            best = rec
            break
        if best is None or (G.RANK[q["tier"]], len(q["flags"])) < (G.RANK[best["q"]["tier"]], len(best["q"]["flags"])):
            best = rec
    out = {"ok": False, "tries": tries}
    if best is None:
        return out
    q = best["q"]
    ms = len(best["y"]) / best["sr"] * 1000.0
    if q["tier"] == "pass":
        out.update(ok=True, files=encode(best["y"], best["sr"]), ms=ms, syl=q.pop("syl"), q=q)
    else:
        q.pop("syl", None)
        out.update(q=q, ms=ms)
        if keep_rejected:
            out["rejected_files"] = encode(best["y"], best["sr"])
    return out


def synthesize(text: str, voice: str) -> Optional[Tuple[np.ndarray, float, Dict[str, bytes]]]:
    """(옛 경로, 게이트 없음) 글 → (16kHz 파형, 길이 ms, 인코딩한 파일들). 실패하면 None."""
    import sound_gate as G
    raw, sr = synthesize_raw(text, voice)
    y, info = G.postprocess(raw, sr)
    if info.get("empty") or not y.size:
        return None
    return to16k(y, sr), len(y) / sr * 1000.0, encode(y, sr)


def align_syllables(wav16: np.ndarray, text: str, ms: float) -> Optional[List[List[int]]]:
    """D-GOP 정렬기로 음절 시각. 정렬기가 없거나 실패하면 None."""
    import sound_clips as S
    phones, toks, _ = phones_for(wav16, text)
    if not phones:
        return None
    try:
        return S.syllable_times(phones, toks, duration_ms=ms)
    except Exception:
        return None
