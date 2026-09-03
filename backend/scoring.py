"""
Advanced Scoring Algorithm with Phonological Similarity Weighting
Evaluates user responses using articulatory feature-based partial credit
"""
import Levenshtein
from typing import Dict, List, Optional, Tuple
from engine import decompose_hangul, VISEME_MAP, get_viseme_feature, to_pronounced_syllables


# Phonological similarity matrix (0.0 = completely different, 1.0 = identical)
# Based on articulatory features (place, manner, voicing)
PHONEME_SIMILARITY = {
    # Bilabial consonants (place similarity)
    ('ㅂ', 'ㅍ'): 0.7, ('ㅂ', 'ㅃ'): 0.7, ('ㅍ', 'ㅃ'): 0.7,
    ('ㅂ', 'ㅁ'): 0.6, ('ㅍ', 'ㅁ'): 0.6, ('ㅃ', 'ㅁ'): 0.6,

    # Alveolar consonants
    ('ㄷ', 'ㅌ'): 0.7, ('ㄷ', 'ㄸ'): 0.7, ('ㅌ', 'ㄸ'): 0.7,
    ('ㄷ', 'ㄴ'): 0.6, ('ㅌ', 'ㄴ'): 0.6, ('ㄸ', 'ㄴ'): 0.6,
    ('ㄷ', 'ㄹ'): 0.5, ('ㅌ', 'ㄹ'): 0.5, ('ㄴ', 'ㄹ'): 0.6,
    ('ㅅ', 'ㅆ'): 0.8, ('ㅅ', 'ㄷ'): 0.5, ('ㅆ', 'ㄸ'): 0.5,

    # Velar consonants
    ('ㄱ', 'ㅋ'): 0.7, ('ㄱ', 'ㄲ'): 0.7, ('ㅋ', 'ㄲ'): 0.7,
    ('ㄱ', 'ㅇ'): 0.5, ('ㅋ', 'ㅇ'): 0.5, ('ㄲ', 'ㅇ'): 0.5,

    # Palatal consonants
    ('ㅈ', 'ㅊ'): 0.7, ('ㅈ', 'ㅉ'): 0.7, ('ㅊ', 'ㅉ'): 0.7,

    # Open vowels (jaw opening similarity)
    ('ㅏ', 'ㅐ'): 0.8, ('ㅑ', 'ㅒ'): 0.8, ('ㅏ', 'ㅑ'): 0.7,
    ('ㅐ', 'ㅒ'): 0.7, ('ㅏ', 'ㅓ'): 0.6, ('ㅐ', 'ㅔ'): 0.8,

    # Front vowels
    ('ㅣ', 'ㅔ'): 0.7, ('ㅣ', 'ㅖ'): 0.7, ('ㅔ', 'ㅖ'): 0.8,
    ('ㅣ', 'ㅐ'): 0.6, ('ㅔ', 'ㅐ'): 0.8,

    # Rounded vowels
    ('ㅗ', 'ㅜ'): 0.7, ('ㅛ', 'ㅠ'): 0.7, ('ㅗ', 'ㅛ'): 0.8,
    ('ㅜ', 'ㅠ'): 0.8, ('ㅗ', 'ㅚ'): 0.7, ('ㅜ', 'ㅟ'): 0.7,

    # Central vowels
    ('ㅓ', 'ㅕ'): 0.8, ('ㅓ', 'ㅡ'): 0.6, ('ㅕ', 'ㅡ'): 0.6,

    # Diphthongs with similar starting points
    ('ㅘ', 'ㅙ'): 0.8, ('ㅘ', 'ㅚ'): 0.7, ('ㅝ', 'ㅞ'): 0.8,
    ('ㅝ', 'ㅟ'): 0.7, ('ㅢ', 'ㅣ'): 0.7, ('ㅢ', 'ㅡ'): 0.7,
}


# ── 자음 시각 유사도(지각공간에서 도출) ──────────────────────────────────
# 손으로 짠 PHONEME_SIMILARITY 표에 없는 자음 쌍의 부분점수를, 앱의 지각공간 모델
# (perceptual_space의 고전 MDS 2D 좌표)에서 도출한다. 표의 공백을 원리적으로 메우고,
# 채점 근거를 앱 전체의 '시각 혼동' 정의와 한 출처로 맞춘다. 같은 입모양 자음은 서로
# 가깝고(높은 부분점수), 눈으로도 어느 정도 닮은 다른 위치(예: 치경 ㄷ ↔ 경구개 ㅈ)는
# 중간값, 명백히 다른 입모양(양순 ㅂ ↔ 연구개 ㄱ)은 0에 가깝게 나온다.
# numpy·perceptual_space를 못 불러오면 조용히 비활성화하고 기존 비심 폴백을 쓴다.
_CONS_FALLBACK_CAP = 0.6   # 폴백 부분점수 상한(표의 near-identical 값과 정합; 큐레이션 표 ≥ 자동 폴백)


def _sim_from_coords(symbols, coords) -> Dict[Tuple[str, str], float]:
    """지각공간 좌표 → 쌍별 (거리 기반) 시각 유사도. 상한 _CONS_FALLBACK_CAP로 스케일."""
    import numpy as np
    n = len(symbols)
    dmax = max((float(np.linalg.norm(coords[i] - coords[j]))
                for i in range(n) for j in range(n)), default=0.0)
    if dmax <= 0:
        return {}
    out: Dict[Tuple[str, str], float] = {}
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            sim = 1.0 - float(np.linalg.norm(coords[i] - coords[j])) / dmax
            out[(symbols[i], symbols[j])] = round(sim * _CONS_FALLBACK_CAP, 3)
    return out


def _build_perceptual_similarity(kind: str) -> Dict[Tuple[str, str], float]:
    """자음/모음 시각 유사도를 지각공간(고전 MDS)에서 도출. numpy 없으면 {} 반환."""
    try:
        import perceptual_space as ps
        if kind == "consonant":
            syms, coords = ps.classical_mds()
        else:
            syms, coords = ps.vowel_classical_mds()
        return _sim_from_coords(syms, coords)
    except Exception:
        return {}


# 자음·모음 각각의 지각공간에서 도출한 시각 유사도(손으로 매긴 표를 기하 거리로 대체)
_CONS_SIM: Dict[Tuple[str, str], float] = _build_perceptual_similarity("consonant")
_VOWEL_SIM: Dict[Tuple[str, str], float] = _build_perceptual_similarity("vowel")


def get_phoneme_similarity(p1: str, p2: str) -> float:
    """
    Calculate similarity score between two phonemes
    Returns 1.0 for identical, 0.0 for completely different
    """
    if p1 == p2:
        return 1.0

    # Check both directions in similarity matrix (큐레이션 표가 우선)
    similarity = PHONEME_SIMILARITY.get((p1, p2), PHONEME_SIMILARITY.get((p2, p1)))
    if similarity is not None:
        return similarity

    # 표에 없는 자음·모음 쌍은 지각공간(MDS)에서 도출한 시각 유사도로 채운다
    if (p1, p2) in _CONS_SIM:
        return _CONS_SIM[(p1, p2)]
    if (p1, p2) in _VOWEL_SIM:
        return _VOWEL_SIM[(p1, p2)]

    # 최후 폴백(지각공간 비활성 등) — 같은 입모양(viseme)이면 부분점수를 준다
    v1, v2 = VISEME_MAP.get(p1), VISEME_MAP.get(p2)
    if v1 is not None and v1 == v2:
        return 0.5
    return 0.0


def _syllable_match_score(cs: Tuple, us: Tuple) -> float:
    """두 음절의 부분 일치 점수 (초성 30% · 중성 50% · 종성 20%)."""
    initial_score = get_phoneme_similarity(cs[0], us[0]) * 0.3
    medial_score = get_phoneme_similarity(cs[1], us[1]) * 0.5
    if cs[2] and us[2]:
        final_score = get_phoneme_similarity(cs[2], us[2]) * 0.2
    elif not cs[2] and not us[2]:
        final_score = 0.2  # 둘 다 받침 없음 = 일치
    else:
        final_score = 0.0  # 한쪽만 받침 (누락/추가)
    return initial_score + medial_score + final_score


def align_jamos(correct: List[Tuple], user: List[Tuple]) -> List[Tuple[Optional[Tuple], Optional[Tuple]]]:
    """
    DP(삽입/삭제 허용)로 정답·사용자 음절을 정렬하고 backtrace로 정렬쌍을 복원한다.
    반환: [(정답음절|None, 사용자음절|None), ...] — None은 삽입/삭제 지점.
    음소별 정확도·오류비심·혼동 모두 이 '같은 정렬'을 근거로 삼아야 앞음절이 하나
    밀렸을 때 이후가 통째로 오정렬되는 버그를 막는다.
    """
    n, m = len(correct), len(user)
    dp = [[0.0] * (m + 1) for _ in range(n + 1)]
    # 이동 기록: 'M'=매칭(대각), 'C'=정답만 소비(삭제), 'U'=사용자만 소비(삽입)
    bt = [[None] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        bt[i][0] = 'C'
    for j in range(1, m + 1):
        bt[0][j] = 'U'

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            match_score = dp[i - 1][j - 1] + _syllable_match_score(correct[i - 1], user[j - 1])
            skip_correct = dp[i - 1][j]
            skip_user = dp[i][j - 1]
            best = max(match_score, skip_correct, skip_user)
            dp[i][j] = best
            # 동점 시 매칭 우선(정렬을 최대한 붙임) → 결정론적
            if best == match_score:
                bt[i][j] = 'M'
            elif best == skip_correct:
                bt[i][j] = 'C'
            else:
                bt[i][j] = 'U'

    pairs: List[Tuple[Optional[Tuple], Optional[Tuple]]] = []
    i, j = n, m
    while i > 0 or j > 0:
        move = bt[i][j]
        if move == 'M':
            pairs.append((correct[i - 1], user[j - 1])); i -= 1; j -= 1
        elif move == 'C':
            pairs.append((correct[i - 1], None)); i -= 1
        else:
            pairs.append((None, user[j - 1])); j -= 1
    pairs.reverse()
    return pairs


def calculate_jamo_score(correct: List[Tuple], user: List[Tuple]) -> Dict:
    """
    자모(초성·중성·종성) 정렬 채점. 총점과 음소별 정확도를 '동일한 DP 정렬'로 산출한다.

    Args:
        correct: 정답의 (초성, 중성, 종성) 튜플 리스트
        user: 사용자 답의 (초성, 중성, 종성) 튜플 리스트

    Returns:
        score(0~100), phoneme_accuracy(초/중/종 %), alignment(정렬쌍) 등
    """
    len_correct = len(correct)
    alignment = align_jamos(correct, user)

    achieved_score = sum(_syllable_match_score(cs, us) for cs, us in alignment if cs and us)
    max_score = len_correct
    percentage = (achieved_score / max_score * 100) if max_score > 0 else 0

    # 음소별 정확도 — 정렬쌍 기준. 정답에만 있는(사용자가 놓친) 음절은 0점으로 반영.
    initial_matches = 0.0
    medial_matches = 0.0
    final_matches = 0.0
    total_initials = len_correct
    total_medials = len_correct
    total_finals = sum(1 for _, _, f in correct if f)

    for cs, us in alignment:
        if cs is None:
            continue  # 사용자가 더 넣은 음절 — 정답 쪽 분모에 없음
        if us is None:
            continue  # 사용자가 놓친 음절 — 0점(분모에는 이미 포함)
        initial_matches += get_phoneme_similarity(cs[0], us[0])
        medial_matches += get_phoneme_similarity(cs[1], us[1])
        if cs[2] and us[2]:
            final_matches += get_phoneme_similarity(cs[2], us[2])

    return {
        "score": round(percentage, 2),
        "max_score": max_score,
        "achieved_score": round(achieved_score, 2),
        "alignment": alignment,
        "phoneme_accuracy": {
            "initial": round(initial_matches / total_initials * 100, 1) if total_initials > 0 else 0,
            "medial": round(medial_matches / total_medials * 100, 1) if total_medials > 0 else 0,
            "final": round(final_matches / total_finals * 100, 1) if total_finals > 0 else 0,
        }
    }


def extract_jamo_sequence(text: str) -> List[Tuple]:
    """
    Extract jamo sequence from Korean text
    Returns list of (initial, medial, final) tuples
    """
    jamo_sequence = []

    for char in text:
        if '가' <= char <= '힣':
            initial, medial, final = decompose_hangul(char)
            if initial:
                jamo_sequence.append((initial, medial, final))

    return jamo_sequence


def to_pronounced_jamos(text: str) -> List[Tuple]:
    """
    텍스트를 '소리 나는 대로'(연음·구개음화·격음화·겹받침·ㅎ탈락) 변환한 뒤
    [초, 중, 종] 튜플 열로 반환한다. 무음 초성 ㅇ은 ''로 남는다.

    독화 앱은 철자가 아니라 '실제 발화 입모양'을 채점해야 한다. 아바타가 '굳이'를
    '구지'로 보여주므로, 입모양을 완벽히 읽어 '구지'라 적어도 '굳이'로 적어도 정답이어야
    한다. 정답·사용자 답 양쪽을 이 함수로 정규화해 두 표기가 같은 점수를 받게 한다.
    """
    out: List[Tuple] = []
    for syl in to_pronounced_syllables(text):
        if isinstance(syl, (list, tuple)) and len(syl) == 3:
            out.append(tuple(syl))
    return out


def identify_error_visemes(correct_jamos: List[Tuple], user_jamos: List[Tuple]) -> List[int]:
    """
    Identify which visemes the user struggled with
    Returns list of viseme IDs where errors occurred
    """
    error_visemes = []

    alignment_length = min(len(correct_jamos), len(user_jamos))

    for i in range(alignment_length):
        correct_syl = correct_jamos[i]
        user_syl = user_jamos[i]

        # Check initial consonant
        if correct_syl[0] != user_syl[0]:
            viseme = VISEME_MAP.get(correct_syl[0], 15)
            error_visemes.append(viseme)

        # Check medial vowel
        if correct_syl[1] != user_syl[1]:
            viseme = VISEME_MAP.get(correct_syl[1], 15)
            error_visemes.append(viseme)

        # Check final consonant
        if correct_syl[2] != user_syl[2]:
            if correct_syl[2]:
                viseme = VISEME_MAP.get(correct_syl[2], 15)
                error_visemes.append(viseme)

    # Handle length differences
    if len(correct_jamos) > len(user_jamos):
        # User missed syllables
        for i in range(len(user_jamos), len(correct_jamos)):
            for phoneme in correct_jamos[i]:
                if phoneme:
                    viseme = VISEME_MAP.get(phoneme, 15)
                    error_visemes.append(viseme)

    return sorted(set(error_visemes))  # 고유 비심 (결정론적 순서)


def error_visemes_from_alignment(alignment: List[Tuple]) -> List[int]:
    """
    DP 정렬쌍으로부터 '정답 쪽' 오류 비심을 뽑는다. calculate_jamo_score의 정렬을 그대로
    재사용하므로 음절이 밀렸을 때 생기는 허위 오류가 없다. 무음 초성 ㅇ('')은 비교에서 제외해
    실제 자음과의 가짜 불일치(예: 초성 ㅇ↔ㅈ)를 만들지 않는다.
    """
    errors: List[int] = []
    for cs, us in alignment:
        if cs is None:
            continue  # 사용자가 더 넣은 음절 — 정답에 귀속할 비심 없음
        if us is None:
            for ph in cs:  # 놓친 음절의 모든 음소가 오류
                if ph:
                    errors.append(VISEME_MAP.get(ph, 15))
            continue
        if cs[0] and cs[0] != us[0]:
            errors.append(VISEME_MAP.get(cs[0], 15))
        if cs[1] != us[1]:
            errors.append(VISEME_MAP.get(cs[1], 15))
        if cs[2] and cs[2] != us[2]:
            errors.append(VISEME_MAP.get(cs[2], 15))
    # 등장 순서 유지하며 중복 제거 (결정론적)
    seen: List[int] = []
    for v in errors:
        if v is not None and v not in seen:
            seen.append(v)
    return seen


async def calculate_score(correct: str, user_answer: str, db=None) -> Dict:
    """
    Main scoring function with phonological similarity weighting

    Args:
        correct: Correct sentence
        user_answer: User's answer
        db: Database session (optional, for additional context)

    Returns:
        Dictionary containing:
        - score: Overall score (0-100)
        - phoneme_accuracy: Breakdown by initial/medial/final
        - viseme_errors: List of problematic viseme IDs
        - feedback: Human-readable feedback
        - features: Mapping of viseme IDs to phonological features
    """
    # Normalize inputs
    correct_clean = correct.strip().replace(" ", "")
    user_clean = user_answer.strip().replace(" ", "")

    # Handle empty answers
    if not user_clean:
        return {
            "score": 0.0,
            "phoneme_accuracy": {"initial": 0, "medial": 0, "final": 0},
            "viseme_errors": [],
            "feedback": {"message": "답변을 입력해주세요."},
            "features": {}
        }

    # '소리 나는 대로'로 정규화한 자모열로 채점 (철자가 아니라 실제 발화 입모양 기준).
    # 굳이/구지처럼 표기가 달라도 발음이 같으면 동일 채점 → 완벽히 읽은 답을 감점하지 않는다.
    correct_jamos = to_pronounced_jamos(correct_clean)
    user_jamos = to_pronounced_jamos(user_clean)

    # Calculate detailed score
    score_result = calculate_jamo_score(correct_jamos, user_jamos)

    # Identify error visemes — 채점과 '같은 정렬'을 재사용해 오정렬 허위 오류 방지
    error_visemes = error_visemes_from_alignment(score_result["alignment"])

    # Calculate basic Levenshtein distance for additional context
    levenshtein_distance = Levenshtein.distance(correct_clean, user_clean)
    levenshtein_ratio = (1 - levenshtein_distance / max(len(correct_clean), len(user_clean))) * 100

    # Generate feedback
    feedback = generate_feedback(score_result["score"], score_result["phoneme_accuracy"])

    # Map error visemes to features
    viseme_features = {str(v): get_viseme_feature(v) for v in error_visemes}

    return {
        "score": score_result["score"],
        "phoneme_accuracy": score_result["phoneme_accuracy"],
        "viseme_errors": error_visemes,
        "feedback": feedback,
        "features": viseme_features,
        "levenshtein_ratio": round(levenshtein_ratio, 2)
    }


def generate_feedback(score: float, phoneme_accuracy: Dict) -> Dict:
    """Generate human-readable feedback based on score"""
    if score >= 90:
        message = "완벽해요! 입모양을 정확히 읽어내셨습니다."
        level = "excellent"
    elif score >= 75:
        message = "잘하셨어요! 대부분의 입모양을 정확히 파악했습니다."
        level = "good"
    elif score >= 60:
        message = "괜찮아요. 조금만 더 집중하면 더 좋은 결과를 얻을 수 있어요."
        level = "fair"
    elif score >= 40:
        message = "아쉬워요. 입모양에 더 집중해서 다시 시도해보세요."
        level = "needs_improvement"
    else:
        message = "다시 한번 천천히 입모양을 관찰하며 연습해보세요."
        level = "retry"

    # Add specific phoneme feedback
    weak_phonemes = []
    if phoneme_accuracy["initial"] < 70:
        weak_phonemes.append("자음 (초성)")
    if phoneme_accuracy["medial"] < 70:
        weak_phonemes.append("모음 (중성)")
    if phoneme_accuracy["final"] < 70:
        weak_phonemes.append("받침 (종성)")

    specific_tip = ""
    if weak_phonemes:
        specific_tip = f"{', '.join(weak_phonemes)} 발음을 더 집중해서 연습해보세요."

    return {
        "message": message,
        "level": level,
        "specific_tip": specific_tip,
        "phoneme_breakdown": phoneme_accuracy
    }
