"""말하기 녹음 루프의 파이썬 이식(S10, docs/speak-loudness-intonation-2026-10.md).

프론트 SpeakingPractice.jsx 녹음 루프(화면마다 2,048표본 버퍼의 RMS, 네 화면마다 음높이와 trace 한 점)와
lib/pitch.js autoCorrelate, lib/voicing.longestVoicedRun을 16kHz에서 같은 시간 길이로 옮긴다
(버퍼 42.67ms = 683표본, 화면 간격 16.67ms, trace 간격 66.67ms).

- 지금 규칙(cur): 크기 = (RMS > 0.01인 화면 RMS 평균 − 0.01) / 0.13 × 100, 이어 낸 길이 = longestVoicedRun(trace, 0.01).
  0단계 합격 = 크기 ≥ 22이고 길이 ≥ 1.2초, '크게' = 크기 ≥ 60, '작게' = 12 ≤ 크기 ≤ 45.
- 설계 R(docs/speak-loudness-baseline.md): 잡음 바닥 F, 유성 표본(RMS ≥ k·F, 최댓값 0.5로 맞춘 버퍼의 음높이 70~500Hz,
  그 주기의 정규화 상호상관 ≥ θ), Dv, L, SNR, 기준선 B. k·F의 k와 바닥 백분위는 탐색 후보(사전 등록 문서 2.3절).
"""
import math
from typing import Dict, List, Optional, Sequence

import numpy as np

SR = 16000
BUF = int(round(2048 / 48000 * SR))        # 683
FRAME_HOP = SR / 60.0                       # 266.67표본(화면 하나)
TRACE_EVERY = 4                             # 네 화면마다 trace
MIN_HZ, MAX_HZ = 70, 500


def autocorrelate(buf: np.ndarray, sr: int = SR) -> float:
    """lib/pitch.js autoCorrelate 그대로(ACF2+, 지연은 sr/70+2까지). 범위 밖이면 -1."""
    SIZE = len(buf)
    rms = math.sqrt(float(np.mean(buf * buf)))
    if rms < 0.006:
        return -1
    thres = 0.2
    r1, r2 = 0, SIZE - 1
    for i in range(SIZE // 2):
        if abs(buf[i]) < thres:
            r1 = i
            break
    for i in range(1, SIZE // 2):
        if abs(buf[SIZE - i]) < thres:
            r2 = SIZE - i
            break
    b = buf[r1:r2]
    n = len(b)
    if n < 8:
        return -1
    max_lag = min(n - 1, math.ceil(sr / MIN_HZ) + 2)
    full = np.correlate(b, b, mode="full")[n - 1:]
    c = full[: max_lag + 1]
    d = 0
    while d < max_lag and c[d] > c[d + 1]:
        d += 1
    maxpos = d + int(np.argmax(c[d:]))
    T0 = float(maxpos)
    if T0 <= 0:
        return -1
    x1 = c[maxpos - 1] if maxpos - 1 >= 0 else 0.0
    x2 = c[maxpos]
    x3 = c[maxpos + 1] if maxpos + 1 <= max_lag else 0.0
    a = (x1 + x3 - 2 * x2) / 2
    bb = (x3 - x1) / 2
    if a:
        T0 = T0 - bb / (2 * a)
    return sr / T0


def voiced_pitch(buf: np.ndarray, sr: int = SR) -> Dict[str, float]:
    """설계 R의 음높이: 버퍼를 최댓값 0.5로 맞춘 뒤 autocorrelate, 그 주기에서 정규화 상호상관(선명도).
    {hz(범위 밖이면 0), clarity(0~1)}. 프론트 lib/pitch.voicedPitch와 같은 계산."""
    pk = float(np.max(np.abs(buf))) if len(buf) else 0.0
    if pk <= 0:
        return {"hz": 0.0, "clarity": 0.0}
    b = buf * (0.5 / pk)
    hz = autocorrelate(b, sr)
    if not (MIN_HZ < hz < MAX_HZ):
        return {"hz": 0.0, "clarity": 0.0}
    T = int(round(sr / hz))
    if T <= 0 or T >= len(b) - 8:
        return {"hz": 0.0, "clarity": 0.0}
    u, v = b[:-T], b[T:]
    den = math.sqrt(float(np.dot(u, u)) * float(np.dot(v, v)))
    cl = float(np.dot(u, v)) / den if den > 0 else 0.0
    return {"hz": float(hz), "clarity": max(0.0, cl)}


def loop(x: np.ndarray, sr: int = SR) -> Dict[str, list]:
    """녹음 루프 흉내. rms_frames: 화면마다 RMS. trace: 네 화면마다 {t, rms, hz, clarity}(설계 R 음높이)."""
    x = np.asarray(x, dtype=np.float64)
    rms_frames, trace = [], []
    k = 0
    while True:
        end = int(round(BUF + k * FRAME_HOP))
        if end > len(x):
            break
        buf = x[end - BUF:end]
        r = math.sqrt(float(np.mean(buf * buf)))
        rms_frames.append(r)
        if k % TRACE_EVERY == 0:
            vp = voiced_pitch(buf, sr)
            trace.append({"t": round((end / sr) - BUF / sr, 4), "rms": r, "hz": round(vp["hz"], 2), "clarity": round(vp["clarity"], 4)})
        k += 1
    return {"rms_frames": rms_frames, "trace": trace}


def longest_run(ts: Sequence[float], flags: Sequence[bool], max_gap: float = 0.15) -> float:
    """lib/voicing.longestVoicedRun과 같은 규칙(표본 간격 중앙값 step, 끊김 허용 max(maxGap + step, 2·step))."""
    pts = list(zip(ts, flags))
    if len(pts) < 2:
        return 0.0
    gaps = sorted(pts[i + 1][0] - pts[i][0] for i in range(len(pts) - 1))
    step = gaps[len(gaps) // 2] or 0.07
    gap_ok = max(max_gap + step, step * 2)
    best, start, last = 0.0, None, None
    for t, f in pts:
        if not f:
            continue
        if start is None or t - last > gap_ok:
            start = t
        last = t
        best = max(best, last - start + step)
    return round(best * 10) / 10


# ── 지금 규칙 ──
def current_rule(lp: Dict[str, list]) -> Dict[str, float]:
    raw = lp["rms_frames"]
    voiced = [v for v in raw if v > 0.01]
    avg = sum(voiced) / len(voiced) if voiced else 0.0
    loud = max(0, min(100, round((avg - 0.01) / 0.13 * 100)))
    tr = lp["trace"]
    dv = longest_run([p["t"] for p in tr], [p["rms"] > 0.01 for p in tr])
    return {"loudness": loud, "dv": dv,
            "stage0": loud >= 22 and dv >= 1.2, "loud": loud >= 60, "soft": 12 <= loud <= 45, "long": dv >= 2.0}


# ── 설계 R ──
def floor_rms(tr: List[dict], pct: float = 10.0) -> float:
    rs = [p["rms"] for p in tr]
    if not rs:
        return 0.0005
    head = [p["rms"] for p in tr if p["t"] < 0.3] or rs[:1]
    return max(0.0005, min(float(np.median(head)), float(np.percentile(rs, pct))))


def voiced_flags(tr: List[dict], k: float = 2.0, theta: float = 0.3, pct: float = 10.0) -> List[bool]:
    F = floor_rms(tr, pct)
    return [p["rms"] >= k * F and p["hz"] > 0 and p["clarity"] >= theta for p in tr]


def design_r(lp: Dict[str, list], k: float = 2.0, theta: float = 0.3, pct: float = 10.0) -> Dict[str, Optional[float]]:
    tr = lp["trace"]
    F = floor_rms(tr, pct)
    fl = voiced_flags(tr, k, theta, pct)
    dv = longest_run([p["t"] for p in tr], fl)
    vr = [p["rms"] for p, f in zip(tr, fl) if f]
    L = 20 * math.log10(float(np.median(vr))) if vr else None
    snr = (L - 20 * math.log10(F)) if L is not None else None
    return {"F_db": 20 * math.log10(F), "L": L, "snr": snr, "dv": dv,
            "stage0": bool(dv >= 1.2 and snr is not None and snr >= 12.0), "long": dv >= 2.0}


def judge_with_baseline(r: Dict, B: Optional[float]) -> Dict[str, bool]:
    """'크게'·'작게'(기준선 B가 있을 때). 둘 다 Dv ≥ 0.3초."""
    L, dv = r["L"], r["dv"]
    if B is None or L is None:
        return {"loud": False, "soft": False}
    return {"loud": bool(dv >= 0.3 and L >= B + 6.0), "soft": bool(dv >= 0.3 and B - 18.0 <= L <= B - 6.0)}


def nucleus_flags(tr: List[dict]) -> List[bool]:
    """모음 구간(음절 핵): ±2표본 안 최댓값의 −6dB 이내이면서 클립 최댓값의 −20dB 이상."""
    rs = np.array([p["rms"] for p in tr])
    if not len(rs):
        return []
    mx = rs.max()
    out = []
    for i, r in enumerate(rs):
        loc = rs[max(0, i - 2):i + 3].max()
        out.append(bool(r > 0 and r >= loc * 10 ** (-6 / 20) and r >= mx * 10 ** (-20 / 20)))
    return out
