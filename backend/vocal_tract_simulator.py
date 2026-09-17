"""
조음 시뮬레이터 — 고도화 축 E.

계획서 3.5: "학습자가 혀 위치를 직접 조작하면 소리와 입모양이 함께 변하는 인터랙티브 교구."
VocalTractLab(TU Dresden, 오픈소스)은 학습되는 모델이 아니라 **파라미터(혀 위치·입술
원순도·턱 벌림 등 19개 성도 변수)를 넣으면 물리 법칙으로 성도 형상과 소리를 계산해내는
결정론적 시뮬레이터**다. 그래서 조음 역추정(음성→파라미터, 데이터 필요)과 달리 이 절반은
데이터·학습 없이 지금 바로 동작한다.

engine.py의 한국어 viseme 그룹(1~10, VISEME_MAP)을 VTL 성도 형상 프리셋에 매핑하고, 프레임
시퀀스를 만들어 실제 오디오까지 합성한다.

vocaltractlab-cython은 requirements-ml.txt 전용 의존성이다(앱 런타임에는 불필요).

정직한 한계. VTL의 조음 프리셋은 독일어 화자(기본 제공 JD3 성우 파일) 기준이라, 매핑은
조음 위치(양순/치경/연구개/경구개)의 **물리적 유사성에 근거한 근사**다(프론트
`visemeShapes.js`가 ARKit 블렌드셰이프로 근사한 것과 같은 성격 — 실제 렌더링 결과를 보고
보정한 그 접근을 성도 시뮬레이터에도 적용한 것). 자음 프리셋은 모음 문맥별(a/i/u) 변이가
있는데 여기서는 'a' 문맥만 기본으로 쓴다. 실제 한국어 조음 데이터(MNGU0-급 한국어 자료)로
정밀화하는 것은 이 축의 남은 절반(조음 역추정)과 함께 진행할 후속 과제다.
"""
from typing import Dict, Sequence

try:
    import numpy as np
    import vocaltractlab_cython as _vtl
    HAS_VTL = True
except Exception:  # vocaltractlab-cython 미설치
    HAS_VTL = False

# 한국어 viseme(engine.VISEME_MAP 1~10) → VTL 성도 형상 프리셋 이름.
# ll-/tt-/tb- 접두는 각각 아랫입술(labial)·혀끝(tongue tip)·혀몸(tongue body) 주도 조음을 뜻하며,
# VTL 성우 파일이 조음 위치별로 미리 정의해 둔 것을 그대로 재사용한다(직접 파라미터를 손으로
# 지어내지 않음 — 프론트 매핑에서 이미 검증된 "실제 존재하는 것만 쓴다" 원칙과 동일).
VISEME_TO_SHAPE = {
    1: "ll-labial-closure(a)",        # 양순음 ㅂㅍㅁ — 두 입술 폐쇄
    2: "a",                            # 개방모음 ㅏㅐ
    3: "i",                            # 전설모음 ㅣㅔ
    4: "u",                            # 원순모음 ㅗㅜ
    5: "@",                            # 중설모음 ㅓㅡ — 슈와로 근사
    6: "tt-alveolar-closure(a)",      # 치경음 ㄷㄴㄹㅅ
    7: "tb-velar-closure(a)",         # 연구개음 ㄱㅋㅇ
    8: "@",                            # 성문음 ㅎ — 구강 제약이 성문 쪽이라 중립에 가까운 형상으로 근사
    10: "tt-postalveolar-closure(a)", # 경구개음 ㅈㅉㅊ
}
# 9(이중모음)는 별도 처리: 2(개방)·4(원순)의 파라미터 평균으로 보간한다.

_glottis_cache: Dict[str, "np.ndarray"] = {}


def _glottis_shape(name: str = "modal"):
    if name not in _glottis_cache:
        _glottis_cache[name] = _vtl.get_shape(name, "glottis")
    return _glottis_cache[name]


def shape_for_viseme(viseme_id: int):
    """한국어 viseme(1~10)에 대응하는 19차원 성도 파라미터 벡터. 9는 2·4의 평균으로 보간."""
    if not HAS_VTL:
        raise RuntimeError("vocaltractlab-cython 미설치 — backend/requirements-ml.txt 설치 필요")
    if viseme_id == 9:
        a = _vtl.get_shape(VISEME_TO_SHAPE[2], "tract")
        u = _vtl.get_shape(VISEME_TO_SHAPE[4], "tract")
        return (a + u) / 2.0
    name = VISEME_TO_SHAPE.get(viseme_id)
    if name is None:
        raise ValueError(f"조음 시뮬레이터가 다루는 viseme는 1~10 (받은 값: {viseme_id})")
    return _vtl.get_shape(name, "tract")


def synthesize_viseme_sequence(viseme_ids: Sequence[int], frame_duration_s=0.15):
    """
    viseme id 시퀀스를 부드럽게 전환하는 오디오를 합성한다. frame_duration_s는 단일 float
    (전부 동일 길이) 또는 viseme_ids와 같은 길이의 초 단위 리스트(engine.py가 만드는 프레임별
    duration_ms를 그대로 재사용할 때 — /1000 해서 넘기면 됨). VTL 내부 프레임 레이트(약
    400.9Hz, get_constants()['sr_internal'])로 목표 형상 사이를 선형보간해 조음이 순간이동하듯
    뚝뚝 끊기지 않게 한다(실제 조음 운동의 연속성 근사).
    반환: (audio: np.ndarray[float32], sample_rate: int)
    """
    if not HAS_VTL:
        raise RuntimeError("vocaltractlab-cython 미설치")
    if not viseme_ids:
        raise ValueError("viseme_ids가 비어 있음")

    durations = ([frame_duration_s] * len(viseme_ids) if isinstance(frame_duration_s, (int, float))
                 else list(frame_duration_s))
    if len(durations) != len(viseme_ids):
        raise ValueError("frame_duration_s 리스트 길이가 viseme_ids와 달라야 함")

    constants = _vtl.get_constants()
    state_rate = constants["sr_internal"]

    shapes = [shape_for_viseme(v) for v in viseme_ids]
    glottis = _glottis_shape("modal")

    tract_frames = []
    for i, shape in enumerate(shapes):
        nxt = shapes[i + 1] if i + 1 < len(shapes) else shape
        frames_here = max(1, round(durations[i] * state_rate))
        for f in range(frames_here):
            t = f / frames_here
            tract_frames.append(shape * (1 - t) + nxt * t)

    tract_arr = np.stack(tract_frames).astype(np.float64)
    glottis_arr = np.tile(glottis, (len(tract_frames), 1)).astype(np.float64)
    audio = _vtl.synth_block(tract_arr, glottis_arr)
    return audio.astype(np.float32), constants["sr_audio"]


def outline_svg(viseme_id: int, out_path: str) -> str:
    """
    viseme의 성도 단면을 SVG 파일로 렌더하고 그 내용을 문자열로 돌려준다(투명 두상·교구
    시각화용 — 축 F가 재사용할 성도 형상 자산). out_path는 임시 파일 경로로 호출부가 정한다.
    """
    if not HAS_VTL:
        raise RuntimeError("vocaltractlab-cython 미설치")
    shape = shape_for_viseme(viseme_id)
    _vtl.tract_state_to_svg(shape, out_path)
    with open(out_path, "r", encoding="utf-8") as f:
        return f.read()
