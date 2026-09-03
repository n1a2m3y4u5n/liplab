"""
Advanced Scoring Algorithm with Phonological Similarity Weighting
Evaluates user responses using articulatory feature-based partial credit
"""
import Levenshtein
from typing import Dict, List, Tuple
from engine import decompose_hangul, VISEME_MAP, get_viseme_feature


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


def get_phoneme_similarity(p1: str, p2: str) -> float:
    """
    Calculate similarity score between two phonemes
    Returns 1.0 for identical, 0.0 for completely different
    """
    if p1 == p2:
        return 1.0

    # Check both directions in similarity matrix
    similarity = PHONEME_SIMILARITY.get((p1, p2), PHONEME_SIMILARITY.get((p2, p1)))
    if similarity is not None:
        return similarity

    # 폴백 — 표에 없는 쌍도 '입모양(viseme)'이 같으면 시각적으로 혼동되므로 부분점수를 준다.
    # 손으로 정한 표의 공백을 비심 규칙으로 메워, 채점 근거를 시각 지각과 일관되게 한다.
    v1, v2 = VISEME_MAP.get(p1), VISEME_MAP.get(p2)
    if v1 is not None and v1 == v2:
        return 0.5
    return 0.0


def calculate_jamo_score(correct: List[Tuple], user: List[Tuple]) -> Dict:
    """
    Calculate score based on jamo (초성, 중성, 종성) matching with similarity weights

    Args:
        correct: List of (initial, medial, final) tuples from correct answer
        user: List of (initial, medial, final) tuples from user answer

    Returns:
        Dictionary with total score and detailed breakdown
    """
    # Use dynamic programming for alignment (similar to Levenshtein)
    len_correct = len(correct)
    len_user = len(user)

    # DP matrix: dp[i][j] = (score, alignment)
    dp = [[0.0 for _ in range(len_user + 1)] for _ in range(len_correct + 1)]

    # Initialize
    for i in range(len_correct + 1):
        dp[i][0] = 0.0
    for j in range(len_user + 1):
        dp[0][j] = 0.0

    # Fill DP matrix
    for i in range(1, len_correct + 1):
        for j in range(1, len_user + 1):
            correct_syllable = correct[i - 1]
            user_syllable = user[j - 1]

            # Calculate syllable match score (initial: 30%, medial: 50%, final: 20%)
            initial_score = get_phoneme_similarity(correct_syllable[0], user_syllable[0]) * 0.3
            medial_score = get_phoneme_similarity(correct_syllable[1], user_syllable[1]) * 0.5

            # Final consonant scoring (handle empty finals)
            if correct_syllable[2] and user_syllable[2]:
                final_score = get_phoneme_similarity(correct_syllable[2], user_syllable[2]) * 0.2
            elif not correct_syllable[2] and not user_syllable[2]:
                final_score = 0.2  # Both empty = correct
            elif correct_syllable[2] and not user_syllable[2]:
                final_score = 0.0  # Missing final
            else:
                final_score = 0.0  # Extra final

            syllable_match_score = initial_score + medial_score + final_score

            # Match current syllables
            match_score = dp[i - 1][j - 1] + syllable_match_score

            # Skip in correct (insertion in user answer)
            skip_correct = dp[i - 1][j]

            # Skip in user (deletion in user answer)
            skip_user = dp[i][j - 1]

            dp[i][j] = max(match_score, skip_correct, skip_user)

    # Maximum possible score is len_correct syllables * 1.0
    max_score = len_correct
    achieved_score = dp[len_correct][len_user]

    # Normalize to 0-100 scale
    percentage = (achieved_score / max_score * 100) if max_score > 0 else 0

    # Calculate phoneme-level accuracy
    initial_matches = 0
    medial_matches = 0
    final_matches = 0
    total_initials = len_correct
    total_medials = len_correct
    total_finals = sum(1 for _, _, f in correct if f)

    # Approximate phoneme accuracy using best alignment
    alignment_length = min(len_correct, len_user)
    for i in range(alignment_length):
        if i < len_correct and i < len_user:
            initial_matches += get_phoneme_similarity(correct[i][0], user[i][0])
            medial_matches += get_phoneme_similarity(correct[i][1], user[i][1])
            if correct[i][2] and user[i][2]:
                final_matches += get_phoneme_similarity(correct[i][2], user[i][2])

    return {
        "score": round(percentage, 2),
        "max_score": max_score,
        "achieved_score": round(achieved_score, 2),
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

    return list(set(error_visemes))  # Return unique visemes


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

    # Extract jamo sequences
    correct_jamos = extract_jamo_sequence(correct_clean)
    user_jamos = extract_jamo_sequence(user_clean)

    # Calculate detailed score
    score_result = calculate_jamo_score(correct_jamos, user_jamos)

    # Identify error visemes
    error_visemes = identify_error_visemes(correct_jamos, user_jamos)

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
