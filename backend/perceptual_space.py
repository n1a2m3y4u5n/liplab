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


# ── 모음 시각 지각공간 ────────────────────────────────────────────────────
# 자음이 조음 위치로 뭉치듯, 모음은 '눈에 보이는' 자질(개구도·원순성)이 주 신호다.
# viseme 그룹(개방/전설/원순/중설/이중모음)을 주 차원으로, 개구도·원순성을 보조 차원으로 둔다.
VOWELS = ["ㅏ", "ㅐ", "ㅑ", "ㅒ", "ㅓ", "ㅔ", "ㅕ", "ㅖ", "ㅗ", "ㅘ",
          "ㅙ", "ㅚ", "ㅛ", "ㅜ", "ㅝ", "ㅞ", "ㅟ", "ㅠ", "ㅡ", "ㅢ", "ㅣ"]
_VVIS = {2: 0, 3: 1, 4: 2, 5: 3, 9: 4}   # 개방/전설/원순/중설/이중모음 → 위치 차원
# 개구도(턱 벌림, 0=거의 닫힘 ~ 1=크게 벌림) — 입모양으로 뚜렷이 드러난다.
_OPEN = {
    "ㅏ": 1.0, "ㅑ": 1.0, "ㅐ": 0.75, "ㅒ": 0.75, "ㅓ": 0.6, "ㅕ": 0.6, "ㅔ": 0.55, "ㅖ": 0.55,
    "ㅗ": 0.45, "ㅛ": 0.45, "ㅜ": 0.25, "ㅠ": 0.25, "ㅡ": 0.25, "ㅣ": 0.2,
    "ㅘ": 0.7, "ㅙ": 0.6, "ㅚ": 0.45, "ㅝ": 0.55, "ㅞ": 0.5, "ㅟ": 0.3, "ㅢ": 0.25,
}
# 원순성(입술 둥긂, 0~1) — 역시 눈에 보인다.
_ROUND = {
    "ㅗ": 1.0, "ㅛ": 1.0, "ㅜ": 1.0, "ㅠ": 1.0, "ㅚ": 1.0, "ㅟ": 1.0,
    "ㅘ": 0.7, "ㅙ": 0.7, "ㅝ": 0.7, "ㅞ": 0.7,
}


def vowel_visual_feature(ph: str) -> np.ndarray:
    """모음의 '시각적으로 드러나는 자질' 벡터. viseme 위치(주) + 개구도·원순성(보조)."""
    vec = np.zeros(7)
    v = VISEME_MAP.get(ph)
    if v in _VVIS:
        vec[_VVIS[v]] = 1.0                 # 입모양 군 — 가장 뚜렷
    vec[5] = 0.4 * _OPEN.get(ph, 0.4)       # 개구도(잘 보임)
    vec[6] = 0.4 * _ROUND.get(ph, 0.0)      # 원순성(잘 보임)
    return vec


def vowel_similarity_matrix(vows=None):
    """모음 쌍 시각 유사도(코사인) 행렬."""
    vows = vows or VOWELS
    F = np.array([vowel_visual_feature(v) for v in vows])
    norm = np.linalg.norm(F, axis=1, keepdims=True)
    norm[norm == 0] = 1.0
    Fn = F / norm
    return vows, Fn @ Fn.T


def vowel_classical_mds(vows=None, dim: int = 2):
    """모음 코사인 거리에 고전 MDS를 적용해 모음 지각공간 2D 좌표를 얻는다."""
    vows, S = vowel_similarity_matrix(vows)
    D2 = 1.0 - S
    n = len(vows)
    J = np.eye(n) - np.ones((n, n)) / n
    B = -0.5 * J @ D2 @ J
    w, V = np.linalg.eigh(B)
    idx = np.argsort(w)[::-1][:dim]
    coords = V[:, idx] * np.sqrt(np.maximum(w[idx], 0.0))
    return vows, coords


def _confusion_block(symbols, coords):
    """MDS 좌표 → '지각공간 내 거리로 도출한' 음소 쌍 혼동도(1=구별 불가). 대각=1.0."""
    n = len(symbols)
    dmax = max((float(np.linalg.norm(coords[i] - coords[j]))
                for i in range(n) for j in range(n)), default=0.0) or 1.0
    rows = {}
    for i, a in enumerate(symbols):
        rows[a] = {b: round(1.0 - float(np.linalg.norm(coords[i] - coords[j])) / dmax, 3)
                   for j, b in enumerate(symbols)}
    return rows


def phoneme_confusion_matrix() -> dict:
    """한국어 음소 혼동 행렬 — 자음·모음 각각의 지각공간(고전 MDS) 거리에서 도출.

    LIPLAB의 채점은 원래 '사람이 손으로 0~1로 매긴' 유사도 표에 의존했다. 이 함수는 그 표를,
    조음 자질에서 만든 지각공간의 기하 거리로 대체한 '규칙판 혼동 행렬'을 준다. 데이터로 학습한
    임베딩 거리(대조학습)로 나아가기 전의 결정론적 baseline이다.
    """
    cons, ccoords = classical_mds()
    vows, vcoords = vowel_classical_mds()
    return {
        "consonants": {"symbols": cons, "confusion": _confusion_block(cons, ccoords)},
        "vowels": {"symbols": vows, "confusion": _confusion_block(vows, vcoords)},
        "note": ("조음 자질로 만든 시각 지각공간(고전 MDS)의 거리에서 도출한 규칙판 음소 혼동 행렬. "
                 "손으로 매긴 유사도 표를 대체하는 결정론적 baseline이며, 학습된 임베딩 거리로 보정될 자리."),
    }
