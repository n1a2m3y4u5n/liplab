"""동적 문장 합성기(C17, 기본 끔). 고정 소리와 같은 엔진(Supertonic 3, ONNX)으로 서버 CPU에서 합성한다.

`supertonic` 패키지가 설치돼 있고 LIPLAB_SOUND_DYNAMIC=1일 때만 쓴다. 배포 이미지에는 넣지 않았다. 4GB 기계의 기존 최대 사용량
3.15GB(fly.dev.toml)에 합성기 상주 메모리를 더한 값과 2코어 지연은 docs/sound-condition.md 6절에 적었다.
인코딩은 faster-whisper가 이미 쓰는 PyAV로 한다(ogg/opus 24kbps, m4a/aac 24kbps, 모노). 음절 시각은 D-GOP 정렬기가 올라와 있으면
그것으로 얻고, 없으면 시각 없이 소리만 준다(화면이 길이 비례로 맞춘다).
"""
import io
import os
import threading
from typing import Dict, List, Optional, Tuple

import numpy as np

_tts = None
_styles: Dict[str, object] = {}
_lock = threading.Lock()
THREADS = int(os.getenv("LIPLAB_SOUND_THREADS", "2") or 2)


def available() -> bool:
    try:
        import supertonic  # noqa: F401
        import av  # noqa: F401
        return True
    except Exception:
        return False


def _load():
    global _tts
    if _tts is None:
        os.environ.setdefault("OMP_NUM_THREADS", str(THREADS))
        from supertonic import TTS
        # ONNX Runtime 스레드를 정한다. 정하지 않으면 보이는 코어 수만큼 띄워, 할당이 그보다 적은 기계에서 수십 배 느려진다(파드 실측)
        _tts = TTS(auto_download=os.getenv("HF_HUB_OFFLINE") != "1", intra_op_num_threads=THREADS, inter_op_num_threads=1)
    return _tts


def _resample(x: np.ndarray, sr: int, to: int) -> np.ndarray:
    """정수 비 리샘플(PyAV 리샘플러). 정렬기는 16kHz를 받는다."""
    import av
    frame = av.AudioFrame.from_ndarray(x.astype(np.float32)[None, :], format="flt", layout="mono")
    frame.sample_rate = sr
    rs = av.AudioResampler(format="flt", layout="mono", rate=to)
    out = [f.to_ndarray().reshape(-1) for f in rs.resample(frame)]
    out += [f.to_ndarray().reshape(-1) for f in rs.resample(None)]
    return np.concatenate(out) if out else np.zeros(0, np.float32)


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
    """앞뒤 무음 자르기(10ms 창 RMS가 최대보다 45dB 낮은 구간, 앞뒤 100ms 남김). 고정 소리(scripts/sound_pod/synth.py)와 같은 규칙."""
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


def synthesize(text: str, voice: str) -> Optional[Tuple[np.ndarray, float, Dict[str, bytes]]]:
    """글 → (16kHz 파형, 길이 ms, 인코딩한 파일들). 실패하면 None."""
    with _lock:
        tts = _load()
        style = _styles.get(voice)
        if style is None:
            style = _styles[voice] = tts.get_voice_style(voice_name=voice)
        wav, _dur = tts.synthesize(text, voice_style=style, lang="ko")
        sr = int(getattr(tts, "sample_rate", None) or 44100)
    x = trim_silence(np.asarray(wav, dtype=np.float32).reshape(-1), sr)
    if not x.size:
        return None
    peak = float(np.max(np.abs(x)))
    if peak > 1.0:
        x = x / peak
    return _resample(x, sr, 16000), len(x) / sr * 1000.0, encode(x, sr)


def align_syllables(wav16: np.ndarray, text: str, ms: float) -> Optional[List[List[int]]]:
    """D-GOP 정렬기(DGOP_ALIGNER_ID)로 음절 시각. 정렬기가 없거나 실패하면 None."""
    aligner = os.getenv("DGOP_ALIGNER_ID") or os.getenv("DGOP_MODEL_ID")
    if not aligner:
        return None
    try:
        import dgop_acoustic as DA
        import jamo_vocab
        import sound_clips as S
        if not DA.HAS_ACOUSTIC:
            return None
        toks = DA.tokens_for_text(text, model_id=aligner)
        if toks != jamo_vocab.text_to_tokens(text):
            return None
        phones = DA.phone_confidences(wav16, 16000, toks, aligner_id=aligner, scorer_id=aligner)
        return S.syllable_times(phones, toks, duration_ms=ms)
    except Exception as e:
        print(f"[WARN] 소리 정렬 실패: {type(e).__name__}: {e}")
        return None
