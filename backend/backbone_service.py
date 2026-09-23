"""
공용 음성 백본 서비스(계획서 §3.1 A-9, §4.1 '임베딩 서비스로 상주').

자기지도 음성 모델(WavLM·wav2vec2)을 프로세스 안에서 한 번만 올려 여러 축이 함께 쓴다. 지금 쓰는 곳:
  · A4 음성구동 아바타(audio2face.py): 동결 WavLM-large 은닉 표현(kind="base")
  · B D-GOP(dgop_acoustic.py): 한국어 wav2vec2 CTC 사후확률(kind="ctc")

계획서는 B~E가 한 백본을 공유하는 구조를 그렸지만, 실측에서 축마다 맞는 백본이 달랐다. A4는 WavLM이
wav2vec2보다 3개 홀드아웃 모두에서 높았고(9/18), D-GOP 채점은 한국어 CTC 헤드가 필요하다. 그래서 '모델
하나'가 아니라 '적재·캐시·장치 관리 지점 하나'로 구현한다. 같은 모델 id와 장치를 쓰는 축은 가중치 한 벌을
나눠 쓰고, 상태는 GET /api/backbone/status로 본다. torch·transformers가 없으면 available()이 False이고,
각 축은 기존 폴백(전사 채점, 규칙 비심 립싱크)으로 간다.
"""
import os
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

_LOCK = threading.Lock()
_CACHE: Dict[Tuple[str, str, str], tuple] = {}     # (model_id, kind, device) → (processor 또는 None, model)
_STATS: Dict[Tuple[str, str, str], Dict] = {}

CONSUMERS = {
    "a4_audio2face": "음성 → 입모양 52계수(동결 은닉 표현, kind=base)",
    "b_dgop": "전사 비의존 발음채점(CTC 사후확률, kind=ctc)",
}


def available() -> bool:
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        return True
    except Exception:
        return False


def resolve_device() -> str:
    """BACKBONE_DEVICE(없으면 예전 이름 DGOP_DEVICE)로 강제할 수 있다. 기본은 GPU가 있으면 cuda."""
    forced = os.getenv("BACKBONE_DEVICE") or os.getenv("DGOP_DEVICE")
    if forced:
        return forced
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def _load_base(model_id: str, device: str) -> tuple:
    from transformers import AutoModel
    model = AutoModel.from_pretrained(model_id).eval().to(device)
    for p in model.parameters():
        p.requires_grad_(False)
    return None, model


def _load_ctc(model_id: str, device: str) -> tuple:
    from transformers import AutoModelForCTC, AutoProcessor
    processor = AutoProcessor.from_pretrained(model_id)
    model = AutoModelForCTC.from_pretrained(model_id).eval().to(device)
    return processor, model


# 종류별 적재 함수. 테스트는 이 표를 바꿔 모델을 받지 않고 캐시·통계만 확인한다.
_LOADERS = {"base": _load_base, "ctc": _load_ctc}
_DEFAULT_LOADERS = dict(_LOADERS)


def _param_count(model) -> Optional[int]:
    try:
        return int(sum(p.numel() for p in model.parameters()))
    except Exception:
        return None


def load(model_id: str, kind: str = "base", device: Optional[str] = None) -> tuple:
    """(processor, model)을 돌려준다. 처음 부를 때만 적재하고, 그 뒤로는 같은 객체를 나눠 쓴다."""
    if kind not in _LOADERS:
        raise ValueError(f"알 수 없는 백본 종류: {kind}")
    if _LOADERS[kind] is _DEFAULT_LOADERS[kind] and not available():
        raise RuntimeError("torch/transformers 미설치 — backend/requirements-ml.txt 설치 필요")
    device = device or resolve_device()
    key = (model_id, kind, device)
    with _LOCK:
        if key not in _CACHE:
            t0 = time.time()
            _CACHE[key] = _LOADERS[kind](model_id, device)
            _STATS[key] = {"model_id": model_id, "kind": kind, "device": device,
                           "load_seconds": round(time.time() - t0, 2),
                           "params": _param_count(_CACHE[key][1]),
                           "loaded_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                           "uses": 0}
        _STATS[key]["uses"] += 1
        return _CACHE[key]


def embed(wave16k, model_id: str, device: Optional[str] = None, layer: Optional[int] = None):
    """16kHz 모노 파형 → (T, D) 은닉 표현(약 50Hz, torch 텐서). layer를 주면 그 층, 없으면 마지막 층."""
    import torch
    _, model = load(model_id, "base", device)
    dev = next(model.parameters()).device
    x = torch.as_tensor(wave16k, dtype=torch.float32, device=dev)[None]
    with torch.no_grad():
        if layer is None:
            h = model(x).last_hidden_state
        else:
            h = model(x, output_hidden_states=True).hidden_states[layer]
    return h[0]


def status() -> Dict:
    """올라간 모델·장치·사용 횟수. 이 함수는 모델을 새로 올리지 않는다."""
    ok = available()
    with _LOCK:
        loaded = [dict(v) for v in _STATS.values()]
    return {"available": ok, "device": resolve_device() if ok else None, "loaded": loaded,
            "consumers": CONSUMERS}


def clear() -> None:
    """캐시를 비운다(테스트용)."""
    with _LOCK:
        _CACHE.clear()
        _STATS.clear()
