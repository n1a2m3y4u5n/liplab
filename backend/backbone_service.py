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

_LOCK = threading.Lock()        # _CACHE·_STATS·_LOADING을 읽고 쓸 때만 잠깐 잡는다
_LOAD_LOCK = threading.Lock()   # 적재는 한 번에 하나(호스팅 기계는 디스크 읽기가 병목이라 동시에 올려도 빨라지지 않는다)
_CACHE: Dict[Tuple[str, str, str], tuple] = {}     # (model_id, kind, device) → (processor 또는 None, model)
_STATS: Dict[Tuple[str, str, str], Dict] = {}
_LOADING: Dict[Tuple[str, str, str], float] = {}   # 지금 올리는 모델 → 시작 시각

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


QUANT_MODES = ("", "none", "fp32", "int8")


def quant_mode() -> str:
    """BACKBONE_QUANT. int8이면 CPU에 올리는 CTC 모델(D-GOP 정렬기·채점기)의 선형층 가중치를 int8로 둔다(quant_int8.py,
    모델당 약 1.2GB → 0.4GB). A4 아바타 백본(kind=base)은 int8 품질을 따로 재지 않았으므로 fp32 그대로다."""
    mode = (os.getenv("BACKBONE_QUANT") or "").strip().lower()
    if mode not in QUANT_MODES:
        raise ValueError(f"알 수 없는 BACKBONE_QUANT: {mode} (가능: int8, none)")
    return mode


def _load_ctc(model_id: str, device: str) -> tuple:
    """폴더에 미리 변환한 int8 파일(quant_int8.INT8_FILE)이 있으면 그것을 바로 올린다. fp32 가중치가 함께 있으면
    BACKBONE_QUANT=int8일 때만 파일을 쓰고, int8 파일만 있으면(배포 이미지) 설정과 상관없이 쓴다."""
    from transformers import AutoModelForCTC, AutoProcessor
    mode = quant_mode()
    processor = AutoProcessor.from_pretrained(model_id)
    if os.path.isdir(model_id):
        import quant_int8
        if quant_int8.has_int8(model_id) and (mode == "int8" or not quant_int8.has_fp32(model_id)):
            return processor, quant_int8.load_ctc(model_id).to(device)
    model = AutoModelForCTC.from_pretrained(model_id).eval().to(device)
    if mode == "int8" and device == "cpu":
        import gc
        import quant_int8
        quant_int8.quantize_linears(model, skip=("lm_head",))
        model.liplab_quant_from = "runtime"
        gc.collect()
        _malloc_trim()
    return processor, model


def _malloc_trim() -> None:
    """glibc가 해제된 힙을 OS에 돌려주게 한다(리눅스만, 실패해도 무시)."""
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


# 종류별 적재 함수. 테스트는 이 표를 바꿔 모델을 받지 않고 캐시·통계만 확인한다.
_LOADERS = {"base": _load_base, "ctc": _load_ctc}
_DEFAULT_LOADERS = dict(_LOADERS)


def _param_count(model) -> Optional[int]:
    try:
        n = sum(p.numel() for p in model.parameters())
        for m in getattr(model, "modules", lambda: [])():   # int8 선형층(quant_int8.Int8Linear) 가중치는 버퍼라 따로 센다
            if type(m).__name__ == "Int8Linear":
                n += m.qweight.numel() + (m.bias.numel() if m.bias is not None else 0)
        return int(n)
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
        if key in _CACHE:
            _STATS[key]["uses"] += 1
            return _CACHE[key]
    with _LOAD_LOCK:
        with _LOCK:
            if key in _CACHE:                      # 기다리는 사이 다른 스레드가 올렸다
                _STATS[key]["uses"] += 1
                return _CACHE[key]
            _LOADING[key] = time.time()
        t0 = time.time()
        try:
            obj = _LOADERS[kind](model_id, device)
        finally:
            with _LOCK:
                _LOADING.pop(key, None)
        stats = {"model_id": model_id, "kind": kind, "device": device,
                 "load_seconds": round(time.time() - t0, 2),
                 "params": _param_count(obj[1]),
                 "quant": getattr(obj[1], "liplab_quant", None),
                 "quant_from": getattr(obj[1], "liplab_quant_from", None),
                 "loaded_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                 "uses": 1}
        with _LOCK:
            _CACHE[key] = obj
            _STATS[key] = stats
        return obj


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
    """올라간 모델·장치·사용 횟수와 지금 올리는 모델. 이 함수는 모델을 새로 올리지 않고, 적재가 끝나기를 기다리지도 않는다
    (예전에는 적재 내내 잡힌 잠금을 기다려, 비동기 엔드포인트에서 부르면 적재가 끝날 때까지 서버 전체가 멈췄다)."""
    ok = available()
    now = time.time()
    with _LOCK:
        loaded = [dict(v) for v in _STATS.values()]
        loading = [{"model_id": k[0], "kind": k[1], "device": k[2], "seconds": round(now - t, 1)}
                   for k, t in _LOADING.items()]
    return {"available": ok, "device": resolve_device() if ok else None, "loaded": loaded, "loading": loading,
            "consumers": CONSUMERS}


def clear() -> None:
    """캐시를 비운다(테스트용)."""
    with _LOCK:
        _CACHE.clear()
        _STATS.clear()
        _LOADING.clear()
