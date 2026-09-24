"""
Audio2Face 백본 — 고도화 축 A4(음성 → 얼굴 블렌드셰이프).

한국어 wav2vec2(동결) hidden states → BiGRU 헤드 → 52 ARKit 블렌드셰이프 회귀.
로그멜(화자 종속) 대신 동결 음성 백본 특징을 써서 '화자 불변' 매핑을 학습한 모델의 추론부.
제품 기본은 WavLM-large 백본·20화자(미학습 화자 교차검증 jawOpen 상관 r≈0.66,
kr_a4_wavlm.pt). 옛 kresnik wav2vec2 체크포인트도 backbone 필드 없이 로드되어 하위호환.
실제 음성으로 아바타가 립싱크하게 하는 계획서 축 A4의 제품 편입.

**추론만 하므로 GPU 없이 CPU에서 동작**(느릴 뿐). torch·torchaudio·transformers·librosa가
없으면 is_available()=False로, 앱은 텍스트→비심 경로로 폴백한다(배포 무영향).
"""
import io
import os
from typing import Dict, List, Optional

SR = 16000
FPS = 30
_W2V = "kresnik/wav2vec2-large-xlsr-korean"

# 모델 탐색 경로 — 앱 내부(backend/models) 우선, 없으면 랩 산출물.
# kr_a4_wavlm.pt(WavLM 백본, 20화자)가 최우선: 동일 데이터 CV에서 kresnik를 상회하는
# 오디오 표현이라 미학습 화자 립싱크가 더 정확하다(체크포인트의 backbone 필드로 자동 로드).
_CKPT_CANDIDATES = [
    os.path.join(os.path.dirname(__file__), "models", "kr_a4_wavlm.pt"),
    os.path.join(os.path.dirname(__file__), "models", "kr_a4_w2v.pt"),
    os.path.join(os.path.dirname(__file__), "models", "kr_a4_w2v_8spk.pt"),
    os.path.join(os.path.dirname(__file__), "models", "kr_a4_w2v_4spk.pt"),
    os.path.expanduser("~/Downloads/liplab-lab/models/kr_a4_w2v_4spk.pt"),
]

_w2v = None
_head = None
_names: Optional[List[str]] = None
_backbone: Optional[str] = None


def is_available() -> bool:
    """추론에 필요한 라이브러리와 체크포인트가 모두 있으면 True."""
    try:
        import torch  # noqa: F401
        import torchaudio  # noqa: F401
        import transformers  # noqa: F401
        import librosa  # noqa: F401
    except Exception:
        return False
    return _find_ckpt() is not None


def _find_ckpt() -> Optional[str]:
    env = os.environ.get("LIPLAB_A4_CKPT")
    if env and os.path.exists(env):
        return env
    for p in _CKPT_CANDIDATES:
        if p and os.path.exists(p):
            return p
    return None


def _build_head(n_bs: int):
    """train_a4_w2v.py의 Head와 동일 구조(체크포인트 호환)."""
    import torch.nn as nn
    import torch.nn.functional as F

    class Head(nn.Module):
        def __init__(self):
            super().__init__()
            self.norm = nn.LayerNorm(1024)
            self.proj = nn.Linear(1024, 256)
            self.gru = nn.GRU(256, 256, num_layers=2, batch_first=True,
                              bidirectional=True, dropout=0.1)
            self.out = nn.Sequential(nn.Linear(512, 256), nn.SiLU(), nn.Linear(256, n_bs))

        def forward(self, x):
            h = F.silu(self.proj(self.norm(x)))
            h, _ = self.gru(h)
            return self.out(h)

    return Head()


def _load():
    """동결 음성 백본과 학습된 헤드를 1회 로드.

    백본은 체크포인트의 'backbone' 필드를 따른다(WavLM-large 등). 옛 체크포인트엔 이 필드가
    없으므로 기존 kresnik wav2vec2로 폴백해 하위호환을 유지한다. WavLM-large·wav2vec2-large
    모두 hidden 1024라 헤드 구조는 동일하고, AutoModel이 두 계열을 모두 로드한다."""
    global _w2v, _head, _names, _backbone
    if _head is not None:
        return
    import torch
    import backbone_service as _bb
    ckpt_path = _find_ckpt()
    ck = torch.load(ckpt_path, map_location="cpu")
    _names = ck["names"]
    _backbone = ck.get("backbone", _W2V)
    _head = _build_head(len(_names))
    _head.load_state_dict(ck["state"])
    _head.eval()
    # 동결 백본은 공용 백본 서비스(A-9)가 올려 둔다 — 같은 모델을 쓰는 다른 축과 가중치를 나눠 쓴다.
    _, _w2v = _bb.load(_backbone, "base", "cpu")


def _to_mono16k(audio_bytes: bytes):
    """오디오 바이트 → 16k mono float32 numpy.
    브라우저 녹음은 webm/opus라 soundfile로는 못 읽는 경우가 많아, 실패 시 ffmpeg로 폴백한다."""
    import numpy as np
    y = None
    try:
        # 배포 이미지에는 librosa·ffmpeg가 없어 faster-whisper의 디코더(PyAV)를 먼저 쓴다(D-GOP와 같은 경로)
        from faster_whisper.audio import decode_audio
        y = np.asarray(decode_audio(io.BytesIO(audio_bytes), sampling_rate=SR), dtype=np.float32)
    except Exception:
        y = None
    if y is None or getattr(y, "size", 0) == 0:
        try:
            import librosa
            y, _ = librosa.load(io.BytesIO(audio_bytes), sr=SR, mono=True)
        except Exception:
            y = None
    if y is None or getattr(y, "size", 0) == 0:
        # ffmpeg 폴백 — stdin(webm/opus 등) → 16k mono f32le stdout
        import subprocess
        try:
            proc = subprocess.run(
                ["ffmpeg", "-v", "error", "-i", "pipe:0", "-ac", "1",
                 "-ar", str(SR), "-f", "f32le", "pipe:1"],
                input=audio_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            y = np.frombuffer(proc.stdout, dtype=np.float32).copy()
        except Exception:
            return np.zeros(0, dtype=np.float32)
    if y.size == 0:
        return y
    return (y - y.mean()) / (y.std() + 1e-6)


def _w2v_features(y, dev):
    """16k mono → wav2vec2 hidden states → 30fps 리샘플 (T,1024)."""
    import torch
    import torch.nn.functional as F
    import backbone_service as _bb
    h = _bb.embed(y, _backbone, device=dev)[None]   # (1, T_w2v, 1024) ~49Hz
    n_frames = max(1, int(round(len(y) / SR * FPS)))
    h = F.interpolate(h.transpose(1, 2), size=n_frames, mode="linear", align_corners=False)
    return h.transpose(1, 2)[0]                 # (n_frames, 1024)


def _smooth(frames, alpha: float = 0.5):
    """경미한 인과 EMA로 프레임 지터 완화(모델이 이미 속도손실로 부드럽지만 안전망)."""
    if not frames:
        return frames
    out = [frames[0]]
    for f in frames[1:]:
        prev = out[-1]
        out.append([alpha * v + (1 - alpha) * p for v, p in zip(f, prev)])
    return out


def blendshapes_from_audio(audio_bytes: bytes) -> Dict:
    """
    음성 → 52 ARKit 블렌드셰이프 시퀀스(30fps). 아바타가 그대로 재생 가능한 형태.
    반환: {fps, names:[52], frames:[[52]..], n} — 모델/오디오 문제 시 audio_available=False.
    """
    import torch
    _load()
    y = _to_mono16k(audio_bytes)
    if y.size < SR // 10:  # 0.1초 미만이면 무의미
        return {"fps": FPS, "names": _names or [], "frames": [], "n": 0,
                "audio_available": True, "note": "too_short"}
    dev = "cpu"
    feat = _w2v_features(y, dev)
    with torch.no_grad():
        out = _head(feat[None].to(dev)).clamp(0, 1)[0].cpu().numpy()
    frames = _smooth([[round(float(v), 4) for v in row] for row in out])
    return {"fps": FPS, "names": _names, "frames": frames, "n": len(frames),
            "audio_available": True}
