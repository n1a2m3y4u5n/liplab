"""
Audio2Face 백본 — 고도화 축 A4(음성 → 얼굴 블렌드셰이프).

한국어 wav2vec2(동결) hidden states → BiGRU 헤드 → 52 ARKit 블렌드셰이프 회귀.
로그멜(화자 종속) 대신 wav2vec2 특징을 써서 '화자 불변' 매핑을 학습했고, 미학습 화자
교차검증 jawOpen 상관 r≈0.68(8화자)을 얻은 모델(kr_a4_w2v)의 추론부. 실제 음성으로 아바타가
립싱크하게 하는 계획서 축 A4의 제품 편입.

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
_CKPT_CANDIDATES = [
    os.path.join(os.path.dirname(__file__), "models", "kr_a4_w2v.pt"),
    os.path.join(os.path.dirname(__file__), "models", "kr_a4_w2v_8spk.pt"),
    os.path.join(os.path.dirname(__file__), "models", "kr_a4_w2v_4spk.pt"),
    os.path.expanduser("~/Downloads/liplab-lab/models/kr_a4_w2v_4spk.pt"),
]

_w2v = None
_head = None
_names: Optional[List[str]] = None


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
    """wav2vec2(동결)와 학습된 헤드를 1회 로드."""
    global _w2v, _head, _names
    if _head is not None:
        return
    import torch
    from transformers import Wav2Vec2Model
    ckpt_path = _find_ckpt()
    ck = torch.load(ckpt_path, map_location="cpu")
    _names = ck["names"]
    _head = _build_head(len(_names))
    _head.load_state_dict(ck["state"])
    _head.eval()
    _w2v = Wav2Vec2Model.from_pretrained(_W2V).eval()
    for p in _w2v.parameters():
        p.requires_grad_(False)


def _to_mono16k(audio_bytes: bytes):
    """오디오 바이트 → 16k mono float32 numpy.
    브라우저 녹음은 webm/opus라 soundfile로는 못 읽는 경우가 많아, 실패 시 ffmpeg로 폴백한다."""
    import numpy as np
    y = None
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
    x = torch.tensor(y, dtype=torch.float32, device=dev)[None]
    with torch.no_grad():
        h = _w2v(x).last_hidden_state           # (1, T_w2v, 1024) ~49Hz
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
