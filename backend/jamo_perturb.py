"""
목표 자모열 오염 — 과신(overconfidence)의 존재를 직접 재는 도구.

── 왜 오디오가 아니라 목표열을 건드리는가 ──────────────────────────────
과신이란 **음향은 q인데 모델이 P(p)를 높게 주는 것**이다. 그러니 오디오를 그대로 두고
목표 음소만 틀린 것으로 바꾸면, 저하 발화를 합성하지 않고도 그 조건이 만들어진다.

  깨끗한 발화 + 정답 목표열   → naive 높음 (정상)
  깨끗한 발화 + 오염된 목표열 → naive가 높게 남으면 **과신이 실재**한다
                                naive가 붕괴하면 이 모델은 애초에 과신하지 않는다

`deaf_speech_synthesis`의 신호처리 교란(저역통과·포먼트 이동·잡음)은 분포를 통째로
평평하게 만들어 naive도 함께 떨어뜨린다. 그래서 A-3/A-5에서 과신이 재현되지 않았다.
여기서 만드는 것은 그 교란이 만들지 못한 **체계적 치환** 조건이다.

── 오염 규칙의 근거 ──────────────────────────────────────────────────────
농인 발화의 분절 오류는 생략·왜곡·대치, 특히 **자음 유·무성 오류와 자음 생략, 모음 대치**로
보고된다(Osberger & McGarr 1982). 한국어 실측으로는 청각장애 화자의 **포먼트 공간이 중앙화·
축소되며 F2 감소가 F1보다 뚜렷**하다(서경희·심홍임·고도흥 2002, 언어치료연구 11(1)).
아래 네 규칙은 그 기술을 자모 토큰 수준으로 옮긴 것이다.

CAPT 분야에서 정규 음소를 체계적으로 치환해 오류를 모사하는 것은 확립된 관행이다
(Cao et al., Interspeech 2024 — *"The errors simulated by replacing canonical phonemes
systematically can only mimic substitution errors."*). 그 한계(치환 오류만 모사한다)를
그대로 안고 쓰되, 우리 목적은 발화 합성이 아니라 **과신 조건의 구성**이라 문제되지 않는다.

전부 순수 함수라 모델 없이 결정론적으로 테스트된다(test_jamo_perturb.py).
"""
import random
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import jamo_vocab as V

_ONSET, _NUCLEUS, _CODA = "o:", "n:", "c:"


def _split(token: str) -> Tuple[Optional[str], Optional[str]]:
    """토큰 → (위치 접두, 자모). 특수토큰은 (None, None)."""
    for pre in (_ONSET, _NUCLEUS, _CODA):
        if token.startswith(pre):
            return pre, token[len(pre):]
    return None, None


# ── 규칙 ─────────────────────────────────────────────────────────────────
# 각 규칙은 토큰 하나를 받아 '바꾼 토큰' 또는 None(삭제)을 돌려준다.
# 해당 없으면 원본을 그대로 돌려준다.

def _coda_deletion(token: str) -> Optional[str]:
    """종성 탈락 — 농인 발화에서 가장 흔히 보고되는 자음 생략."""
    pre, _ = _split(token)
    return None if pre == _CODA else token


_STOPPING = {"ㅅ": "ㄷ", "ㅆ": "ㄷ", "ㅈ": "ㄷ", "ㅉ": "ㄷ", "ㅊ": "ㅌ", "ㅎ": "ㄱ"}


def _fricative_stopping(token: str) -> Optional[str]:
    """마찰·파찰음의 파열음화 — 고주파 단서에 의존하는 음소가 먼저 무너진다."""
    pre, j = _split(token)
    if pre == _ONSET and j in _STOPPING:
        return _ONSET + _STOPPING[j]
    return token


_NASALIZATION = {"ㅂ": "ㅁ", "ㅃ": "ㅁ", "ㅍ": "ㅁ", "ㄷ": "ㄴ", "ㄸ": "ㄴ", "ㅌ": "ㄴ"}


def _nasalization(token: str) -> Optional[str]:
    """비음 대치 — 비강 공명 조절 실패로 구강 파열음이 비음으로 흐른다."""
    pre, j = _split(token)
    if pre == _ONSET and j in _NASALIZATION:
        return _ONSET + _NASALIZATION[j]
    return token


# 모음 중앙화 — 전설·고모음일수록 중설(ㅡ/ㅓ)로 끌린다. F2 감소가 F1보다 크다는 실측 반영.
_CENTRALIZATION = {
    "ㅣ": "ㅡ", "ㅔ": "ㅓ", "ㅐ": "ㅓ", "ㅟ": "ㅡ", "ㅚ": "ㅓ",
    "ㅜ": "ㅡ", "ㅗ": "ㅓ", "ㅑ": "ㅏ", "ㅕ": "ㅓ", "ㅛ": "ㅓ", "ㅠ": "ㅡ",
}


def _vowel_centralization(token: str) -> Optional[str]:
    """모음 중앙화 — 청각 피드백 결손의 대표적 음향 지표."""
    pre, j = _split(token)
    if pre == _NUCLEUS and j in _CENTRALIZATION:
        return _NUCLEUS + _CENTRALIZATION[j]
    return token


RULES: Dict[str, Callable[[str], Optional[str]]] = {
    "coda_deletion": _coda_deletion,
    "fricative_stopping": _fricative_stopping,
    "nasalization": _nasalization,
    "vowel_centralization": _vowel_centralization,
}


def perturb(tokens: Sequence[str], rule: str, rate: float = 1.0,
            rng: Optional[random.Random] = None) -> List[str]:
    """
    목표 토큰열에 오염 규칙을 적용한다.

    rule: RULES의 키. rate: 적용 대상 중 실제로 바꿀 비율(0~1).
    rate < 1이면 rng로 표본을 고른다(rng를 주면 결정론적).

    특수토큰(blank·unk·어절경계)은 건드리지 않는다 — 정렬 제약이 깨지면 실험이 오염된다.
    결과가 빈 열이 되거나 원본과 같으면 그대로 돌려준다(호출부가 '오염 실패'를 판정한다).
    """
    if rule not in RULES:
        raise KeyError(f"알 수 없는 규칙: {rule} (가능: {sorted(RULES)})")
    fn = RULES[rule]
    rnd = rng or random.Random(0)

    # 규칙이 실제로 건드리는 위치를 먼저 찾는다 — rate를 '적용 가능한 것 중 비율'로 해석한다.
    hits = [i for i, t in enumerate(tokens)
            if V.is_scorable(t) and fn(t) != t]
    if not hits:
        return list(tokens)
    chosen = set(hits) if rate >= 1.0 else set(
        rnd.sample(hits, max(1, round(len(hits) * rate))))

    out: List[str] = []
    for i, t in enumerate(tokens):
        if i in chosen:
            new = fn(t)
            if new is not None:
                out.append(new)
            # None이면 삭제(종성 탈락)
        else:
            out.append(t)
    return out


def perturbation_report(tokens: Sequence[str], rule: str, rate: float = 1.0,
                        rng: Optional[random.Random] = None) -> Dict:
    """
    오염 결과와 함께 '실제로 몇 개가 바뀌었는가'를 돌려준다.
    바뀐 개수가 0이면 그 문장은 실험 표본에서 빼야 한다 — 정답열과 동일해 비교가 성립하지 않는다.
    """
    perturbed = perturb(tokens, rule, rate=rate, rng=rng)
    changed = sum(1 for a, b in zip(tokens, perturbed) if a != b)
    deleted = len(tokens) - len(perturbed)
    return {
        "rule": rule,
        "original": list(tokens),
        "perturbed": perturbed,
        "changed": changed + deleted,
        "deleted": deleted,
        "usable": (changed + deleted) > 0 and len(perturbed) > 0,
    }
