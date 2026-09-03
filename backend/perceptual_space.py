"""
자음 시각 지각공간 — 고도화 축 C 예비 실증(계획서 그림3).

한국어 자음을 '시각적으로 드러나는 자질'(조음 위치=입모양)만으로 벡터화해, 자음 쌍의 시각
유사도 행렬과 지각공간(고전 MDS 2D 좌표)을 만든다. 유성성·기식·긴장처럼 입 밖으로 드러나지
않는 자질은 시각 벡터에 거의 기여하지 않으므로, 같은 입모양 자음이 한 군으로 뭉친다(동구형이음).

지각공간 임베딩(대조학습, 데이터 기반)의 규칙판 예비 결과다. 데이터로 학습하기 전 단계에서
"시각 자질만으로도 알려진 혼동 군이 복원된다"는 축 C의 방향을 자체 실행으로 확인한다.
numpy만 사용(torch 불필요).
"""
import numpy as np

from content_rules import VISEME_MAP
from engine import get_phoneme_type

# 초성 자음(무음 ㅇ 제외 목적상 포함하되 조음 위치로만 다룸)
CONSONANTS = ["ㅂ", "ㅃ", "ㅍ", "ㅁ", "ㄷ", "ㄸ", "ㅌ", "ㄴ", "ㄹ", "ㅅ", "ㅆ",
              "ㄱ", "ㄲ", "ㅋ", "ㅇ", "ㅈ", "ㅉ", "ㅊ", "ㅎ"]
# 자음 viseme(조음 위치) → 시각 벡터의 위치 차원
_VPOS = {1: 0, 6: 1, 7: 2, 8: 3, 10: 4}


def visual_feature(ph: str) -> np.ndarray:
    """자음의 '시각적으로 드러나는 자질' 벡터. 조음 위치(입모양)가 주 신호, 방식은 미세 보조."""
    vec = np.zeros(6)
    v = VISEME_MAP.get(ph)
    if v in _VPOS:
        vec[_VPOS[v]] = 1.0  # 조음 위치(입모양) — 시각적으로 가장 뚜렷
    t = get_phoneme_type(ph, "initial")
    # 방식은 입 밖으로 거의 안 드러나므로 아주 작은 가중만(비음>유음>기식 순 약한 시각 흔적)
    vec[5] = 0.15 if "nasal" in t else 0.10 if "liquid" in t else 0.08 if "aspirated" in t else 0.0
    return vec


def similarity_matrix(cons=None):
    """자음 쌍 시각 유사도(코사인) 행렬. 1.0에 가까울수록 눈으로 구별 불가."""
    cons = cons or CONSONANTS
    F = np.array([visual_feature(c) for c in cons])
    norm = np.linalg.norm(F, axis=1, keepdims=True)
    norm[norm == 0] = 1.0
    Fn = F / norm
    return cons, Fn @ Fn.T


def classical_mds(cons=None, dim: int = 2):
    """코사인 거리 행렬에 고전 MDS를 적용해 자음 지각공간 2D 좌표를 얻는다."""
    cons, S = similarity_matrix(cons)
    D2 = 1.0 - S  # 코사인 거리(제곱 근사)
    n = len(cons)
    J = np.eye(n) - np.ones((n, n)) / n
    B = -0.5 * J @ D2 @ J
    w, V = np.linalg.eigh(B)
    idx = np.argsort(w)[::-1][:dim]
    coords = V[:, idx] * np.sqrt(np.maximum(w[idx], 0.0))
    return cons, coords


def perceptual_space() -> dict:
    """공개 자원용 — 자음 시각 유사도 행렬 + 지각공간 좌표."""
    cons, S = similarity_matrix()
    _, coords = classical_mds()
    return {
        "consonants": cons,
        "similarity": np.round(S, 3).tolist(),
        "mds_2d": [{"phoneme": c, "x": round(float(coords[i][0]), 3), "y": round(float(coords[i][1]), 3)}
                   for i, c in enumerate(cons)],
        "note": "시각 자질(조음 위치=입모양)만으로 벡터화. 같은 입모양 자음이 한 군으로 뭉친다(동구형이음).",
    }
