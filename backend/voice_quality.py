"""발성 지표(S24): 음높이 수준·안정도·목소리 질을 numpy만으로 낸다.

docs/speak-voice-quality-2026-10.md의 사전 등록 측정에 쓴 구현이다. 2026-10-07 확인에서 일곱 지표 모두 기준(608 안 CER과 |ρ| ≥ 0.30)에
못 미쳐 앱에는 연결하지 않았다. 측정 재현용으로 남긴다. 정의는 Praat의 표준 지표를 따르되
(Boersma 1993 자기상관 음높이·HNR, Praat 매뉴얼의 jitter (local)·shimmer (local), Hillenbrand·Houde 1996의 CPPS) 계산은 단순화했다.
Praat(parselmouth)는 GPL이라 앱에 넣지 않고, 측정에서만 이 구현과의 순위상관을 확인한다.

- 음높이: 40ms 한 창(최저 75Hz의 세 주기), 10ms 간격, Hann 창. 창의 자기상관으로 나눈 정규화 자기상관(Boersma 1993)에서
  75~500Hz 지연의 국소 최댓값 가운데 강도 R − 0.01·log2(75/F)(Praat 옥타브 비용)가 가장 큰 것. R ≥ 0.45이고 창 RMS가
  가장 큰 창의 −30dB 이상이면 유성.
- 옥타브 튐 보정: 이어진 유성 구간마다 구간 중앙값에서 7반음 넘게 벗어난 창은 두 배·절반으로 3반음 안에 들면 고치고, 아니면 무성.
- 주기 표시: 유성 구간 안에서 국소 주기 T의 0.8~1.2배 범위의 양의 최댓값을 차례로 잡는다(Praat 'peaks' 방식과 같은 생각,
  위치·크기는 포물선 보간). jitter·shimmer는 Praat 기본 제약(주기 0.0001~0.02초, 이웃 주기 비 ≤ 1.3, 이웃 진폭 비 ≤ 1.6)을 따른다.
- CPPS: 40ms 창·10ms 간격, 1차 예강조(0.97), 파워 스펙트럼 dB의 켑스트럼(20·log10|c|), 시간 3창·켑스트럼 0.5ms 평활,
  60~330Hz 봉우리에서 1~25ms 회귀선까지의 높이. 창 RMS가 최댓값 −30dB 이상인 창의 평균.
"""
from typing import Dict, List, Optional, Tuple

import numpy as np

SR = 16000
F0_MIN, F0_MAX = 75.0, 500.0
WIN_S, HOP_S = 0.040, 0.010
VOICING_THR = 0.45
SILENCE_DB = -30.0
OCTAVE_COST = 0.01
MIN_VOICED_FRAMES = 20          # 유성 0.2초 미만이면 음높이 지표 없음
MIN_PERIODS = 20                # 주기 20개 미만이면 jitter·shimmer 없음
FEATURES = ("f0_med_hz", "f0_sd_st", "f0_step_st", "jitter_local", "shimmer_local", "hnr_db", "cpps_db")


def _frame_starts(n: int, win: int, hop: int) -> np.ndarray:
    if n < win:
        return np.zeros(0, dtype=int)
    return np.arange(0, n - win + 1, hop)


def _rms_db(x: np.ndarray) -> float:
    return 20.0 * np.log10(np.sqrt(np.mean(x * x)) + 1e-12)


def f0_track(y: np.ndarray, sr: int = SR) -> Dict[str, np.ndarray]:
    """창마다 음높이(Hz, 무성 0)·정규화 자기상관 R·RMS(dB)·시각(초, 창 가운데)."""
    y = np.asarray(y, dtype=np.float64)
    win, hop = int(round(WIN_S * sr)), int(round(HOP_S * sr))
    starts = _frame_starts(len(y), win, hop)
    w = np.hanning(win)
    nfft = 1 << int(np.ceil(np.log2(2 * win)))
    wac = np.fft.irfft(np.abs(np.fft.rfft(w, nfft)) ** 2, nfft)[:win]
    wac = wac / wac[0]
    lag_lo, lag_hi = int(np.floor(sr / F0_MAX)), int(np.ceil(sr / F0_MIN))
    f0 = np.zeros(len(starts))
    rr = np.zeros(len(starts))
    db = np.full(len(starts), -240.0)
    for k, s in enumerate(starts):
        x = y[s:s + win]
        db[k] = _rms_db(x)
        xw = (x - x.mean()) * w
        ac = np.fft.irfft(np.abs(np.fft.rfft(xw, nfft)) ** 2, nfft)[:win]
        if ac[0] <= 0:
            continue
        r = ac / ac[0] / np.maximum(wac, 1e-6)
        seg = r[lag_lo - 1:lag_hi + 2]
        best, best_lag, best_r = -np.inf, 0.0, 0.0
        for i in range(1, len(seg) - 1):
            if seg[i] >= seg[i - 1] and seg[i] >= seg[i + 1] and seg[i] > 0:
                a, b, c = seg[i - 1], seg[i], seg[i + 1]
                den = a - 2 * b + c
                off = 0.5 * (a - c) / den if den < 0 else 0.0
                lag = lag_lo - 1 + i + off
                rv = min(1.0, b - 0.25 * (a - c) * off)
                strength = rv - OCTAVE_COST * np.log2(F0_MIN * lag / sr)
                if strength > best:
                    best, best_lag, best_r = strength, lag, rv
        if best_lag > 0:
            f0[k], rr[k] = sr / best_lag, best_r
    thr = (db.max() if len(db) else 0.0) + SILENCE_DB
    voiced = (rr >= VOICING_THR) & (db >= thr) & (f0 >= F0_MIN) & (f0 <= F0_MAX)
    f0 = np.where(voiced, f0, 0.0)
    f0 = _fix_octaves(f0)
    times = (starts + win / 2) / sr
    return {"t": times, "f0": f0, "r": np.where(f0 > 0, rr, 0.0), "db": db, "thr_db": thr}


def _runs(mask: np.ndarray) -> List[Tuple[int, int]]:
    """True가 이어진 구간 [i0, i1)."""
    out, i, n = [], 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            out.append((i, j))
            i = j
        else:
            i += 1
    return out


def _fix_octaves(f0: np.ndarray) -> np.ndarray:
    f0 = f0.copy()
    for i0, i1 in _runs(f0 > 0):
        seg = f0[i0:i1]
        med = np.median(seg)
        for k in range(len(seg)):
            d = 12 * np.log2(seg[k] / med)
            if abs(d) <= 7:
                continue
            for m in (2.0, 0.5):
                if abs(12 * np.log2(seg[k] * m / med)) <= 3:
                    seg[k] = seg[k] * m
                    break
            else:
                seg[k] = 0.0
        f0[i0:i1] = seg
    return f0


def _peak(y: np.ndarray, i: int) -> Tuple[float, float]:
    """표본 i 둘레 포물선 보간 → (위치, 크기)."""
    if 0 < i < len(y) - 1:
        a, b, c = y[i - 1], y[i], y[i + 1]
        den = a - 2 * b + c
        if den < 0:
            off = 0.5 * (a - c) / den
            return i + off, b - 0.25 * (a - c) * off
    return float(i), float(y[i])


def pulses(y: np.ndarray, tr: Dict[str, np.ndarray], sr: int = SR) -> List[List[Tuple[float, float]]]:
    """유성 구간마다 [(위치 표본, 진폭)]."""
    y = np.asarray(y, dtype=np.float64)
    f0, t = tr["f0"], tr["t"]
    out = []
    half = WIN_S / 2
    for i0, i1 in _runs(f0 > 0):
        if i1 - i0 < 3:
            continue
        a = max(0, int((t[i0] - half) * sr))
        b = min(len(y), int((t[i1 - 1] + half) * sr))
        tt, ff = t[i0:i1], f0[i0:i1]

        def period_at(p):
            return sr / float(np.interp(p / sr, tt, ff))

        T0 = period_at(a)
        if a + int(T0) + 1 >= b:
            continue
        p = a + int(np.argmax(y[a:a + int(T0) + 1]))
        seq = [_peak(y, p)]
        while True:
            T = period_at(p)
            lo, hi = p + int(0.8 * T), p + int(np.ceil(1.2 * T)) + 1
            if hi > b or lo <= p:
                break
            q = lo + int(np.argmax(y[lo:hi]))
            seq.append(_peak(y, q))
            p = q
        if len(seq) >= 3:
            out.append(seq)
    return out


def jitter_shimmer(runs: List[List[Tuple[float, float]]], sr: int = SR) -> Tuple[Optional[float], Optional[float], int]:
    """jitter (local, %), shimmer (local, %), 쓴 주기 수. Praat 기본 제약(주기 0.0001~0.02초, 주기 비 ≤ 1.3, 진폭 비 ≤ 1.6)."""
    dps, pers, das, amps = [], [], [], []
    for seq in runs:
        pos = np.array([s[0] for s in seq]) / sr
        amp = np.array([s[1] for s in seq])
        per = np.diff(pos)
        ok = (per >= 0.0001) & (per <= 0.02)
        a_per = amp[1:]          # 주기마다 그 주기를 닫는 봉우리 진폭
        for k in range(len(per)):
            if ok[k]:
                pers.append(per[k])
                amps.append(a_per[k])
            if k == 0 or not (ok[k] and ok[k - 1]):
                continue
            r = per[k] / per[k - 1]
            if 1 / 1.3 <= r <= 1.3:
                dps.append(abs(per[k] - per[k - 1]))
            if a_per[k] > 0 and a_per[k - 1] > 0:
                ra = a_per[k] / a_per[k - 1]
                if 1 / 1.6 <= ra <= 1.6:
                    das.append(abs(a_per[k] - a_per[k - 1]))
    n = len(pers)
    if n < MIN_PERIODS or len(dps) < MIN_PERIODS - 1:
        return None, None, n
    jit = 100.0 * float(np.mean(dps)) / float(np.mean(pers))
    pos_amps = [a for a in amps if a > 0]
    shim = (100.0 * float(np.mean(das)) / float(np.mean(pos_amps))) if len(das) >= MIN_PERIODS - 1 and pos_amps else None
    return jit, shim, n


def cpps(y: np.ndarray, sr: int = SR) -> Optional[float]:
    y = np.asarray(y, dtype=np.float64)
    if len(y) < 2:
        return None
    y = np.append(y[0], y[1:] - 0.97 * y[:-1])
    win, hop = int(round(WIN_S * sr)), int(round(HOP_S * sr))
    starts = _frame_starts(len(y), win, hop)
    if len(starts) < 3:
        return None
    nfft = 1 << int(np.ceil(np.log2(win)))
    w = np.hanning(win)
    frames = np.stack([y[s:s + win] * w for s in starts])
    db = np.array([_rms_db(y[s:s + win]) for s in starts])
    spec = 10 * np.log10(np.abs(np.fft.rfft(frames, nfft, axis=1)) ** 2 + 1e-12)
    cep = np.fft.irfft(spec, nfft, axis=1)[:, : nfft // 2]
    cdb = 20 * np.log10(np.abs(cep) + 1e-12)
    # 평활: 시간 3창, 켑스트럼 0.5ms(8표본 at 16k)
    k = max(1, int(round(0.0005 * sr)))
    ker = np.ones(k) / k
    cdb = np.apply_along_axis(lambda v: np.convolve(v, ker, mode="same"), 1, cdb)
    cdb = np.stack([cdb[max(0, i - 1):i + 2].mean(axis=0) for i in range(len(cdb))])
    q = np.arange(nfft // 2) / sr
    lo, hi = int(np.floor(sr / 330.0)), int(np.ceil(sr / 60.0))
    fit = (q >= 0.001) & (q <= 0.025)
    keep = db >= db.max() + SILENCE_DB
    vals = []
    for i in np.where(keep)[0]:
        c = cdb[i]
        j = lo + int(np.argmax(c[lo:hi + 1]))
        A = np.vstack([q[fit], np.ones(fit.sum())]).T
        m, b0 = np.linalg.lstsq(A, c[fit], rcond=None)[0]
        vals.append(c[j] - (m * q[j] + b0))
    return float(np.mean(vals)) if vals else None


def features(y: np.ndarray, sr: int = SR) -> Dict[str, Optional[float]]:
    """한 녹음의 발성 지표. 값을 낼 수 없으면 None."""
    y = np.asarray(y, dtype=np.float64)
    out: Dict[str, Optional[float]] = {k: None for k in FEATURES}
    tr = f0_track(y, sr)
    f0 = tr["f0"]
    v = f0[f0 > 0]
    out["voiced_s"] = round(len(v) * HOP_S, 3)
    if len(v) >= MIN_VOICED_FRAMES:
        med = float(np.median(v))
        st = 12 * np.log2(v / med)
        out["f0_med_hz"] = med
        out["f0_sd_st"] = float(np.std(st))
        steps = []
        for i0, i1 in _runs(f0 > 0):
            if i1 - i0 >= 2:
                steps.extend(np.abs(np.diff(12 * np.log2(f0[i0:i1]))).tolist())
        out["f0_step_st"] = float(np.median(steps)) if len(steps) >= MIN_VOICED_FRAMES - 1 else None
        r = np.clip(tr["r"][f0 > 0], 1e-3, 0.999)
        out["hnr_db"] = float(np.mean(10 * np.log10(r / (1 - r))))
        jit, shim, n = jitter_shimmer(pulses(y, tr, sr), sr)
        out["jitter_local"], out["shimmer_local"], out["n_periods"] = jit, shim, n
    out["cpps_db"] = cpps(y, sr)
    db = tr["db"]
    out["floor_db"] = float(np.percentile(db, 10) - db.max()) if len(db) else None   # 보고용: 잡음 바닥(최댓값 기준)
    return out
