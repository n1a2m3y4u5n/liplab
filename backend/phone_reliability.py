"""
소리별 음소 피드백 신뢰도 표(S2, docs/phoneme-feedback-reliability-2026-10.md).

말하기 결과의 음소 칩과 약한 소리 코칭은 소리(초성·중성·종성 × 자모)마다 믿을 수 있는 정도가 다르다. 538 인위 치환으로 측정한
소리별 탐지 AUC·거짓 빨강과 608 짝 세션의 재검사 일치를 사전 기준으로 판정해, 통과한 소리만 `data/phone_reliability.json`의
reliable 목록에 둔다. 이 모듈은 그 표를 읽어 D-GOP 음소마다 `reliable`을 붙인다.

- 표가 없거나 깨졌으면 아무것도 붙이지 않는다(None). 화면과 코칭은 예전처럼 모든 소리를 같은 '참고' 칩으로 다룬다.
- 문장 끝 음절(발음형 자모열의 마지막 중성과 바로 앞 초성·뒤 종성)은 표와 상관없이 늘 False다. 정렬기가 문장 끝 모음을 말소리
  안에 내지 않는 결함(docs/dgop-final-vowel-2026-10.md)이 고쳐지기 전에는 그 자리 점수를 판정하지 않는다. 수정이 들어오면
  측정을 다시 하고 표를 바꾼다.
- 표에는 소리별 집계값만 있다(538·608 원자료 없음).
"""
import json
import os
from functools import lru_cache
from typing import Dict, List, Optional, Sequence

TABLE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "phone_reliability.json")


@lru_cache(maxsize=4)
def load_table(path: str = TABLE_PATH) -> Optional[Dict]:
    """신뢰도 표. 없거나 reliable 목록이 없으면 None."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            t = json.load(f)
    except Exception as e:
        print(f"[WARN] 음소 신뢰도 표를 읽지 못했습니다({path}): {e}")
        return None
    if not isinstance(t.get("reliable"), list):
        return None
    return t


def reliable_tokens(path: str = TABLE_PATH) -> Optional[frozenset]:
    t = load_table(path)
    return None if t is None else frozenset(t["reliable"])


def final_syllable_start(tokens: Sequence[str]) -> int:
    """문장 끝 음절의 시작 위치: 마지막 중성, 바로 앞이 초성이면 그 초성부터. 중성이 없으면 len(tokens)."""
    idx = [i for i, t in enumerate(tokens) if (t or "").startswith("n:")]
    if not idx:
        return len(tokens)
    i = idx[-1]
    return i - 1 if i > 0 and (tokens[i - 1] or "").startswith("o:") else i


def annotate(phones: List[Dict], path: str = TABLE_PATH) -> bool:
    """D-GOP phones(assess_text 결과, 자리 순서 그대로)에 reliable(True/False)을 붙인다. 표가 없으면 아무것도 하지 않고 False를 돌려준다.
    끝 음절은 phones 전체(어절 경계 포함)의 토큰열로 정한다. 정렬·채점 대상이 아닌 토큰은 False."""
    rel = reliable_tokens(path)
    if rel is None or not phones:
        return False
    cut = final_syllable_start([p.get("token") or "" for p in phones])
    for i, p in enumerate(phones):
        p["reliable"] = bool(i < cut and p.get("aligned") and p.get("scorable") and not p.get("silent_h")
                             and (p.get("token") or "") in rel)
    return True
