"""축 E — 모음 포먼트로 혀 위치 교정 방향 만들기(numpy만 사용).

웹캠은 입술·턱만 보인다. 혀의 높낮이·앞뒤는 소리의 공명(포먼트)에 드러난다: F1이 높을수록 혀가 낮고
(입이 크게 벌어짐), F2가 높을수록 혀가 앞에 있다. 모음을 말한 녹음에서 F1·F2를 LPC로 추정해 목표
모음(VocalTractSimulator의 VOWELS와 같은 값)과 비교하고 "혀를 조금 더 앞으로"처럼 방향을 말해 준다.

화자 정규화: 목표값은 성인 남성 대략치다. 성도가 짧은 여성·아동은 같은 모음도 포먼트가 높으므로,
목소리 높이(F0) 구간으로 배율을 정해 목표를 맞춘다(160Hz 미만 1.0, 250Hz 미만 1.12, 그 이상 1.25).
F3로 성도 길이를 추정하는 방법은 짧은 녹음에서 극점이 흔들려 쓰지 않았다(합성 모음 시험에서 25% 오차).
판정 폭: F1 ±35%, F2 ±15%(로그 비율). 고모음 F1은 F0 배음 때문에 LPC가 20~30% 높게 잡는 경향이 있어
F1 폭을 넓게 둔다. 정직: 짧은 녹음 한 개로 추정한 포먼트는 흔들린다. 이 교정은 방향 안내이고 진단이 아니다.
"""
import io
from typing import Dict, List, Optional

import numpy as np

SR = 16000
# 한국어 단모음 목표(F1, F2 Hz, 성인 남성 대략치) — frontend VocalTractSimulator.jsx VOWELS와 같은 값.
VOWEL_TARGETS: Dict[str, Dict] = {
    "ㅣ": {"f1": 300, "f2": 2300, "round": 0}, "ㅔ": {"f1": 450, "f2": 2000, "round": 0},
    "ㅐ": {"f1": 620, "f2": 1760, "round": 0}, "ㅏ": {"f1": 780, "f2": 1300, "round": 0},
    "ㅓ": {"f1": 600, "f2": 1150, "round": 0}, "ㅗ": {"f1": 460, "f2": 880, "round": 1},
    "ㅜ": {"f1": 330, "f2": 830, "round": 1}, "ㅡ": {"f1": 350, "f2": 1500, "round": 0},
}
_F1_TOL, _F2_TOL = 1.35, 1.15
_JUNG = list("ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ")


def target_vowel(text: str) -> Optional[str]:
    """'아'·'이'처럼 초성 ㅇ·받침 없는 단모음 음절 하나면 그 모음, 아니면 None."""
    t = (text or "").strip()
    if len(t) != 1 or not (0xAC00 <= ord(t) <= 0xD7A3):
        return None
    s = ord(t) - 0xAC00
    cho, jung, jong = s // 588, (s % 588) // 28, s % 28
    if cho != 11 or jong != 0:          # 초성 ㅇ(11), 받침 없음
        return None
    v = _JUNG[jung]
    return v if v in VOWEL_TARGETS else None


def decode_mono16k(audio_bytes: bytes) -> Optional[np.ndarray]:
    """업로드 음성(webm·wav 등) → 16kHz 모노 float32. 배포는 faster-whisper의 디코더(PyAV)를,
    로컬 개발은 librosa를 쓴다. 둘 다 실패하면 None."""
    try:
        from faster_whisper.audio import decode_audio
        return np.asarray(decode_audio(io.BytesIO(audio_bytes), sampling_rate=SR), dtype=np.float32)
    except Exception:
        pass
    try:
        import librosa
        y, _ = librosa.load(io.BytesIO(audio_bytes), sr=SR, mono=True)
        return y.astype(np.float32)
    except Exception:
        return None


def _lpc(frame: np.ndarray, order: int) -> Optional[np.ndarray]:
    """자기상관 + 레빈슨-더빈으로 LPC 계수 [1, a1..ap]."""
    r = np.correlate(frame, frame, mode="full")[len(frame) - 1:len(frame) + order]
    if r[0] <= 0:
        return None
    a = np.zeros(order + 1)
    a[0] = 1.0
    e = r[0]
    for i in range(1, order + 1):
        acc = r[i] + np.dot(a[1:i], r[i - 1:0:-1])
        k = -acc / e
        a[1:i] = a[1:i] + k * a[i - 1:0:-1]
        a[i] = k
        e *= (1 - k * k)
        if e <= 0:
            return None
    return a


def _frame_formants(frame: np.ndarray, sr: int, order: int) -> List[float]:
    x = np.append(frame[0], frame[1:] - 0.97 * frame[:-1]) * np.hamming(len(frame))
    a = _lpc(x, order)
    if a is None:
        return []
    roots = [z for z in np.roots(a) if np.imag(z) >= 0.01]
    out = []
    for z in roots:
        f = np.angle(z) * sr / (2 * np.pi)
        bw = -0.5 * (sr / (2 * np.pi)) * np.log(np.abs(z))
        if 90 < f < _MAX_FORMANT and bw < 400:
            out.append(float(f))
    return sorted(out)


_MAX_FORMANT = 5500.0     # Praat 관례: 이 주파수까지 포먼트 5개를 찾는다
_N_FORMANTS = 5


def _resample(y: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    """FFT 절단·영채움 리샘플링(scipy 없이). 짧은 녹음 한 개용."""
    n_out = int(round(len(y) * sr_out / sr_in))
    spec = np.fft.rfft(y)
    bins = n_out // 2 + 1
    out = np.zeros(bins, dtype=complex)
    m = min(len(spec), bins)
    out[:m] = spec[:m]
    return np.fft.irfft(out, n_out) * (n_out / len(y))


def estimate_formants(y: np.ndarray, sr: int = SR) -> Optional[Dict[str, float]]:
    """에너지가 큰(유성 모음) 프레임들의 F1·F2·F3 중앙값. 모음 구간이 짧거나 추정이 불안정하면 None.
    최대 포먼트 5.5kHz 기준으로 11kHz로 낮춘 뒤 10차 LPC(포먼트 5개)로 찾는다. 16kHz 그대로 18차를 쓰면
    남는 극점이 공명 사이에 가짜 포먼트를 만든다."""
    if y is None or len(y) < int(0.12 * sr):
        return None
    y = y.astype(np.float64)
    target_sr = int(2 * _MAX_FORMANT)
    if sr != target_sr:
        y = _resample(y, sr, target_sr)
        sr = target_sr
    y = y / (np.max(np.abs(y)) + 1e-9)
    win, hop = int(0.025 * sr), int(0.010 * sr)
    frames = [y[i:i + win] for i in range(0, len(y) - win, hop)]
    if not frames:
        return None
    energy = np.array([float(np.sum(f * f)) for f in frames])
    keep = energy >= np.percentile(energy, 40)          # 조용한 앞뒤 구간 제외
    order = 2 * _N_FORMANTS
    f1s, f2s, f3s = [], [], []
    for f, k in zip(frames, keep):
        if not k:
            continue
        fs = _frame_formants(f, sr, order)
        if len(fs) >= 3:
            f1s.append(fs[0]); f2s.append(fs[1]); f3s.append(fs[2])
    if len(f1s) < 5:
        return None
    f0s = [v for v in (_frame_f0(f, sr) for f, k in zip(frames, keep) if k) if v]
    return {"f1": float(np.median(f1s)), "f2": float(np.median(f2s)), "f3": float(np.median(f3s)),
            "f0": float(np.median(f0s)) if f0s else None, "frames": len(f1s)}


def _frame_f0(frame: np.ndarray, sr: int) -> Optional[float]:
    """자기상관 최대 지연으로 F0(60~400Hz). 주기성이 약하면 None."""
    x = frame - frame.mean()
    ac = np.correlate(x, x, mode="full")[len(x) - 1:]
    if ac[0] <= 0:
        return None
    lo, hi = int(sr / 400), int(sr / 60)
    if hi >= len(ac):
        return None
    lag = lo + int(np.argmax(ac[lo:hi]))
    return float(sr / lag) if ac[lag] / ac[0] > 0.3 else None


def speaker_scale(f0: Optional[float]) -> float:
    """목소리 높이 구간 → 목표 포먼트 배율(성인 남성 1.0, 성인 여성 1.12, 아동 1.25)."""
    if not f0:
        return 1.0
    return 1.0 if f0 < 160 else (1.12 if f0 < 250 else 1.25)


def vowel_feedback(y: np.ndarray, vowel: str, sr: int = SR) -> Optional[Dict]:
    """목표 모음 대비 혀 높낮이(F1)·앞뒤(F2) 교정 방향. 추정이 안 되면 None."""
    tgt = VOWEL_TARGETS.get(vowel)
    est = estimate_formants(y, sr)
    if not tgt or not est:
        return None
    scale = speaker_scale(est.get("f0"))
    t1, t2 = tgt["f1"] * scale, tgt["f2"] * scale
    r1, r2 = est["f1"] / t1, est["f2"] / t2
    height = "raise" if r1 > _F1_TOL else ("lower" if r1 < 1 / _F1_TOL else "ok")   # F1 높음 = 혀가 낮음
    front = "back" if r2 > _F2_TOL else ("forward" if r2 < 1 / _F2_TOL else "ok")   # F2 높음 = 혀가 앞
    msg = []
    if height == "raise":
        msg.append("혀가 조금 낮아요. 혀를 올리고 입을 덜 벌려 보세요.")
    elif height == "lower":
        msg.append("혀가 조금 높아요. 혀를 내리고 입을 더 벌려 보세요.")
    if front == "forward":
        msg.append("혀를 조금 더 앞으로 내밀어 보세요.")
    elif front == "back":
        msg.append("혀가 앞에 있어요. 혀를 조금 뒤로 당겨 보세요.")
    if tgt["round"] and front != "ok":
        msg.append("입술도 동그랗게 모아 주세요.")
    if not msg:
        msg.append("혀 위치가 목표 모음에 가까워요.")
    return {"vowel": vowel, "f1": round(est["f1"]), "f2": round(est["f2"]), "f3": round(est["f3"]),
            "f0": round(est["f0"]) if est.get("f0") else None,
            "target_f1": round(t1), "target_f2": round(t2), "speaker_scale": round(scale, 2),
            "height": height, "front": front, "messages": msg}
