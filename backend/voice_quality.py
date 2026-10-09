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


# ── Praat식 CPPS(2026-10-09 재등록, docs/speak-cues-rereg-2026-10.md) ──
# Praat 'To PowerCepstrogram'(음높이 하한 60Hz, 2ms 간격, 최대 5kHz, 50Hz부터 예강조)과
# 'Get CPPS'(추세선을 먼저 빼고 평활, 시간 0.02초·켑스트럼 0.0005초 평활, 60~330Hz 봉우리, 포물선 보간,
# 추세선 켑스트럼 0.001~0.05초, 지수 감쇠(로그 켑스트럼 축 직선), 강건 적합(불완전 Theil))를 numpy로 다시 쓴 것이다.
# Praat 소스의 정의를 따르되 GPL 코드를 옮기지 않고 문서화된 절차만 구현했다.
CPPS_SR = 10000.0


def _resample_fft(y: np.ndarray, sr_in: float, sr_out: float) -> np.ndarray:
    """FFT 절단으로 대역 제한 리샘플(sr_out/2 위는 버린다)."""
    n = len(y)
    m = int(round(n * sr_out / sr_in))
    if m < 2:
        return np.zeros(0)
    Y = np.fft.rfft(y)
    k = m // 2 + 1
    Z = np.zeros(k, dtype=complex)
    kk = min(k, len(Y))
    Z[:kk] = Y[:kk]
    return np.fft.irfft(Z, m) * (m / n)


def _movavg_praat(a: np.ndarray, window: int, axis: int) -> np.ndarray:
    """Praat VECsmoothByMovingAverage: 창 [i − w/2, i + w/2](짝수면 끝 하나 뺌), 가장자리는 있는 만큼 평균."""
    if window <= 1:
        return a
    a = np.moveaxis(a, axis, 0)
    n = a.shape[0]
    cs = np.concatenate([np.zeros((1,) + a.shape[1:]), np.cumsum(a, axis=0)], axis=0)
    i = np.arange(n)
    lo = np.clip(i - window // 2, 0, n - 1)
    hi = np.clip(i + window // 2 - (1 if window % 2 == 0 else 0), 0, n - 1)
    out = (cs[hi + 1] - cs[lo]) / (hi - lo + 1).reshape((-1,) + (1,) * (a.ndim - 1))
    return np.moveaxis(out, 0, axis)


def _theil_rows(x: np.ndarray, Y: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """행마다 불완전 Theil 직선(쌍 i, i + n/2의 기울기 중앙값, 절편 = y − m·x의 중앙값)."""
    n = len(x)
    h = n // 2
    n2 = h + 1 if n % 2 else h
    sl = (Y[:, n2:n2 + h] - Y[:, :h]) / (x[n2:n2 + h] - x[:h])
    m = np.median(sl, axis=1)
    b = np.median(Y - m[:, None] * x[None, :], axis=1)
    return m, b


def cpps_praat(y: np.ndarray, sr: int = SR, pitch_floor: float = 60.0, dt: float = 0.002, pre_hz: float = 50.0,
               t_avg: float = 0.02, q_avg: float = 0.0005, f_lo: float = 60.0, f_hi: float = 330.0,
               q_fit: Tuple[float, float] = (0.001, 0.05), clip_flat: bool = True, speech_only: bool = False
               ) -> Optional[float]:
    """Praat식 CPPS(dB). 소리가 0.1초보다 짧으면 None. speech_only면 창 RMS가 최댓값 −30dB 이상인 창만 평균(보고용)."""
    y = np.asarray(y, dtype=np.float64)
    x = _resample_fft(y, float(sr), CPPS_SR)
    if len(x) < 2:
        return None
    a = np.exp(-2 * np.pi * pre_hz / CPPS_SR)
    x = np.append(x[0], x[1:] - a * x[:-1])
    wdur = 6.0 / pitch_floor                       # 분석 폭 3/하한의 두 배(가우스 창)
    nw = int(round(wdur * CPPS_SR))
    if len(x) < nw:
        return None
    nf = int(np.floor((len(x) / CPPS_SR - wdur) / dt)) + 1
    mid = 0.5 * len(x) / CPPS_SR
    t1 = mid - 0.5 * nf * dt + 0.5 * dt
    starts = np.round((t1 + np.arange(nf) * dt - wdur / 2) * CPPS_SR).astype(int)
    starts = np.clip(starts, 0, len(x) - nw)
    i = np.arange(1, nw + 1)
    imid = 0.5 * (nw + 1)
    edge = np.exp(-12.0)
    win = (np.exp(-48.0 * (i - imid) ** 2 / (nw + 1) ** 2) - edge) / (1 - edge)
    nfft = 8
    while nfft < nw:
        nfft *= 2
    nq = nfft // 2 + 1
    dq = 1.0 / CPPS_SR
    q = np.arange(nq) * dq
    P = np.empty((nf, nq))
    rms = np.empty(nf)
    for c0 in range(0, nf, 512):
        idx = starts[c0:c0 + 512, None] + np.arange(nw)[None, :]
        fr = x[idx]
        rms[c0:c0 + 512] = np.sqrt(np.mean(fr * fr, axis=1))
        fr = (fr - fr.mean(axis=1, keepdims=True)) * win
        X = np.fft.rfft(fr, nfft, axis=1)
        L = np.log(X.real ** 2 + X.imag ** 2 + 1e-300)
        c = np.fft.irfft(L, nfft, axis=1)[:, :nq]
        P[c0:c0 + 512] = c * c
    fit = (q >= q_fit[0] - 1e-12) & (q <= min(q_fit[1], q[-1]) + 1e-12)
    lq = np.log(np.where(q > 0, q, 0.5 * dq))

    def db(Z):
        return 10.0 * np.log10(Z + 1e-300)

    D = db(P)
    m, b = _theil_rows(lq[fit], D[:, fit])
    flat = D - (m[:, None] * lq[None, :] + b[:, None])
    if clip_flat:
        flat = np.clip(flat, 0.0, None)
    flat = np.minimum(flat, 300.0)                 # 디지털 무음 창(값 0)에서 10^(dB/10)이 넘치지 않게
    Z = 10.0 ** (flat / 10.0)
    Z = _movavg_praat(Z, int(np.floor(t_avg / dt + 1e-9)), axis=0)
    Z = _movavg_praat(Z, int(np.floor(q_avg / dq + 1e-9)), axis=1)
    S = db(Z)
    m2, b2 = _theil_rows(lq[fit], S[:, fit])
    lo = int(np.ceil(1.0 / f_hi / dq))
    hi = int(np.floor(1.0 / f_lo / dq))
    seg = S[:, lo:hi + 1]
    j = np.argmax(seg, axis=1)
    jj = lo + j
    ok = (jj > 0) & (jj < nq - 1)
    a0 = S[np.arange(nf), np.clip(jj - 1, 0, nq - 1)]
    a1 = S[np.arange(nf), jj]
    a2 = S[np.arange(nf), np.clip(jj + 1, 0, nq - 1)]
    den = a0 - 2 * a1 + a2
    off = np.where(ok & (den < 0), 0.5 * (a0 - a2) / np.where(den < 0, den, -1.0), 0.0)
    off = np.clip(off, -0.5, 0.5)
    peak = a1 - 0.25 * (a0 - a2) * off
    qp = (jj + off) * dq
    cpp = peak - (m2 * np.log(qp) + b2)
    if speech_only:
        keep = 20 * np.log10(rms + 1e-12) >= 20 * np.log10(rms.max() + 1e-12) + SILENCE_DB
        cpp = cpp[keep]
    return float(np.mean(cpp)) if len(cpp) else None
