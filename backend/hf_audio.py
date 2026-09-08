"""
Hugging Face `datasets`의 오디오 컬럼 → 1D numpy 파형.

datasets 5.x부터 Audio 컬럼 디코딩이 soundfile에서 **torchcodec**으로 바뀌면서,
행을 읽으면 `{"array": ..., "sampling_rate": ...}` 딕셔너리가 아니라 `AudioDecoder`
객체가 나온다(2026-09-08 RunPod에서 실기 확인). 축 A 스크립트 네 개가 모두 오디오를
읽으므로 변환을 여기 한곳에 모은다.

두 형식을 모두 받는다 — datasets 버전을 올리거나 내려도 스크립트는 그대로 동작한다.

torchcodec 주의: 버전이 torch와 묶여 있다(0.6.x ↔ torch 2.8). 최신판을 깔면 CUDA 13
런타임(libnvrtc.so.13)을 요구해 CUDA 12 환경에서 import부터 실패한다.
"""
from typing import Any

import numpy as np


def to_waveform(audio: Any) -> np.ndarray:
    """오디오 컬럼 값 → float32 1D numpy 배열(모노)."""
    # datasets 5.x — torchcodec AudioDecoder
    if hasattr(audio, "get_all_samples"):
        data = audio.get_all_samples().data          # (채널, 샘플)
        arr = data.numpy()
        return (arr.mean(axis=0) if arr.ndim > 1 else arr).astype(np.float32)

    # datasets 4.x 이하 — {"array", "sampling_rate"}
    if isinstance(audio, dict) and "array" in audio:
        arr = np.asarray(audio["array"])
        return (arr.mean(axis=0) if arr.ndim > 1 else arr).astype(np.float32)

    # 이미 배열인 경우
    arr = np.asarray(audio)
    return (arr.mean(axis=0) if arr.ndim > 1 else arr).astype(np.float32)


def sampling_rate_of(audio: Any, default: int = 16000) -> int:
    """오디오 컬럼 값에서 샘플레이트를 꺼낸다. 알 수 없으면 default."""
    if hasattr(audio, "get_all_samples"):
        return int(audio.get_all_samples().sample_rate)
    if isinstance(audio, dict):
        return int(audio.get("sampling_rate", default))
    return default
