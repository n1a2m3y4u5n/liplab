"""
농인 발화 근사 합성 — 고도화 축 A.

계획서 3.1: 농인·난청 화자의 한국어 발화 공개 코퍼스가 없어, 정상 발화(OLKAVS 등)에
조음 교란(포먼트 이동, 말속도 신축, 명료도 저하)을 적용해 그 분포를 근사한 합성 코퍼스를
만든다. 이 모듈은 그 교란 자체를 구현한다 — 원본 오디오 파일 없이도 numpy 배열 입력이면
바로 동작하고 결정론적으로 테스트할 수 있다. 실제 OLKAVS 원천 데이터는 축 A 착수 시
이 함수들에 배치로 흘려보내면 된다.

의존성은 requirements-ml.txt 전용(librosa·scipy·numpy) — 앱 런타임/배포에는 불필요.

정직한 한계. formant_shift는 순수 포먼트 전용 워프가 아니라 리샘플+시간복원 방식의
근사(피치와 포먼트가 함께 움직인다 — VTLP류 augmentation에서 흔히 쓰는 값싼 근사)다.
정밀한 포먼트 전용 조작은 LPC 기반 성도 워핑이 필요하며 이번 범위 밖이다.
"""
import numpy as np

try:
    import librosa
    from scipy.signal import butter, sosfiltfilt
    HAS_SYNTHESIS = True
except Exception:  # librosa/scipy 미설치
    HAS_SYNTHESIS = False


def time_stretch(y: np.ndarray, rate: float) -> np.ndarray:
    """말속도 신축. rate>1이면 빨라지고(짧아지고) rate<1이면 느려진다(길어진다)."""
    if not HAS_SYNTHESIS:
        raise RuntimeError("librosa 미설치 — backend/requirements-ml.txt 설치 필요")
    return librosa.effects.time_stretch(y.astype(np.float32), rate=rate)


def formant_shift(y: np.ndarray, sr: int, semitones: float) -> np.ndarray:
    """
    포먼트(+피치) 이동 근사. 리샘플로 스펙트럼을 주파수축에서 늘리거나 줄인 뒤
    time_stretch로 원래 길이로 되돌린다(리샘플이 바꾼 재생속도만 상쇄, 스펙트럼
    워프는 유지). semitones<0이면 저음(농인 발화에서 흔한 조음 뭉갬 방향)으로 이동.
    """
    if not HAS_SYNTHESIS:
        raise RuntimeError("librosa 미설치 — backend/requirements-ml.txt 설치 필요")
    ratio = 2.0 ** (semitones / 12.0)
    resampled = librosa.resample(y.astype(np.float32), orig_sr=sr, target_sr=int(sr * ratio))
    return librosa.effects.time_stretch(resampled, rate=ratio)


def lowpass(y: np.ndarray, sr: int, cutoff_hz: float, order: int = 4) -> np.ndarray:
    """명료도 저하(고주파 성분 제거) — 버터워스 저역통과, 위상 왜곡 없는 zero-phase 필터."""
    if not HAS_SYNTHESIS:
        raise RuntimeError("scipy 미설치 — backend/requirements-ml.txt 설치 필요")
    nyquist = sr / 2.0
    cutoff_hz = min(cutoff_hz, nyquist * 0.99)
    sos = butter(order, cutoff_hz / nyquist, btype="low", output="sos")
    return sosfiltfilt(sos, y).astype(np.float32)


def add_noise(y: np.ndarray, snr_db: float, rng: np.random.Generator = None) -> np.ndarray:
    """목표 SNR(dB)에 맞춘 백색잡음 추가. rng를 고정하면 결정론적."""
    rng = rng or np.random.default_rng(0)
    noise = rng.standard_normal(len(y)).astype(np.float32)
    signal_power = float(np.mean(y.astype(np.float64) ** 2)) or 1e-12
    noise_power = float(np.mean(noise.astype(np.float64) ** 2)) or 1e-12
    target_noise_power = signal_power / (10.0 ** (snr_db / 10.0))
    scale = (target_noise_power / noise_power) ** 0.5
    return (y.astype(np.float32) + noise * scale).astype(np.float32)


# 5단계 저하 강도 — 계획서 그림7·그림8의 예비 실증(다섯 단계 강도 스윕)과 같은 구조.
# 강도가 오를수록 저역통과 컷오프는 낮아지고(고주파 손실↑), SNR은 낮아지며(잡음↑),
# 포먼트는 저음 쪽으로 더 크게 이동한다.
SEVERITY_LEVELS = {
    0: {"cutoff_hz": 8000, "snr_db": 40, "formant_semitones": 0.0},   # 명료
    1: {"cutoff_hz": 6000, "snr_db": 25, "formant_semitones": -0.5},
    2: {"cutoff_hz": 4000, "snr_db": 15, "formant_semitones": -1.0},
    3: {"cutoff_hz": 2500, "snr_db": 8,  "formant_semitones": -1.5},
    4: {"cutoff_hz": 1500, "snr_db": 3,  "formant_semitones": -2.0},  # 심함
}


def simulate_deaf_speech(y: np.ndarray, sr: int, severity: int,
                          rng: np.random.Generator = None) -> np.ndarray:
    """
    저하 강도(0=명료 ~ 4=심함)에 따라 포먼트 이동 → 저역통과 → 잡음 추가를 순서대로 적용해
    농인 발화를 근사한다. severity·파라미터 매핑은 SEVERITY_LEVELS에서 조정한다.
    """
    if severity not in SEVERITY_LEVELS:
        raise ValueError(f"severity는 0~4 (받은 값: {severity})")
    cfg = SEVERITY_LEVELS[severity]
    out = y
    if cfg["formant_semitones"] != 0.0:
        out = formant_shift(out, sr, cfg["formant_semitones"])
        # formant_shift는 float32 정밀도 상 길이가 원본과 한두 샘플 어긋날 수 있어 맞춰준다.
        out = librosa.util.fix_length(out, size=len(y))
    out = lowpass(out, sr, cfg["cutoff_hz"])
    out = add_noise(out, cfg["snr_db"], rng=rng)
    return out
