"""
독화 지각 자원 — 고도화 축 C의 규칙 기반 부분.

계획서 §3.3: 한국어 독화에는 표준 자원(동구형이음 사전, 독화 난이도 지수, 표준 평가셋)이
거의 없다. 지각공간 임베딩(대조학습)은 데이터·연산이 필요하지만, 그 산출물의 상당 부분은
**비심(viseme) 규칙만으로 결정론적으로 도출**할 수 있다. 이 모듈은 그 규칙 기반 자원을 만든다.

  · 동구형이음 사전: 입모양이 같아 눈으로 구별되지 않는 음소·음절 무리.
  · 독화 난이도 지수: 문장/단어 = 구성 음소의 '안 보이는 정도'와 '혼동 이웃 밀도'로 정의.

음향·영상 데이터 없이 동작하며, 앱 밖 연구·교육에서도 쓸 수 있게 공개 자원으로 내보낸다
(scripts/export_perceptual.py). 지각공간 임베딩이 준비되면 이 규칙값을 데이터로 보정한다.
"""
from collections import Counter
from typing import Dict, List, Optional

import curriculum as _cur
from content_rules import (VISEME_MAP, discover_pairs, viseme_signature,
                           word_visemes, is_hangul_word)

# viseme(1~10) 가시성 — 커리큘럼 레슨에서 가져온다(high 잘 보임 ~ low 거의 안 보임).
_VISIBILITY = {l["viseme_id"]: l["visibility"] for l in _cur.VISEME_LESSONS}
_VIS_WEIGHT = {"high": 0.0, "medium": 0.5, "low": 1.0}  # '안 보이는 정도' 가중


def homophene_dictionary() -> Dict:
    """음소를 입모양(viseme)으로 묶은 동구형이음 사전. 같은 그룹은 눈으로 구별 불가."""
    groups: Dict[int, List[str]] = {}
    for ph, vid in VISEME_MAP.items():
        if 1 <= vid <= 10:  # 학습 대상 음소 그룹만
            groups.setdefault(vid, []).append(ph)
    viseme_groups = {}
    for les in _cur.VISEME_LESSONS:
        vid = les["viseme_id"]
        viseme_groups[vid] = {
            "name": les["name"],
            "phonemes": groups.get(vid, []),
            "visibility": les["visibility"],
        }
    return {
        "viseme_groups": viseme_groups,
        "homophene_clusters": _cur.HOMOPHENE_CLUSTERS,
        "note": "같은 viseme 그룹 또는 같은 혼동 무리의 음소는 입모양이 같아 문맥으로 구별한다.",
    }


def invisibility(word: str) -> Optional[float]:
    """단어의 '안 보이는 정도'(0=전부 뚜렷, 1=전부 안 보임). 저가시성 음소 비중."""
    vis = word_visemes(word)
    if not vis:
        return None
    return round(sum(_VIS_WEIGHT.get(_VISIBILITY.get(v, "medium"), 0.5) for v in vis) / len(vis), 3)


def word_difficulty(word: str, corpus_signatures: Optional[Counter] = None) -> Optional[Dict]:
    """
    단어의 독화 난이도 지수(0 쉬움 ~ 1 어려움).
      · 안 보이는 정도(invisibility): 입 안쪽 자음처럼 눈에 안 드러나는 음소 비중.
      · 혼동 이웃 밀도(neighbor_density): 같은 입모양(동구형이음)으로 보이는 다른 단어 수.
    둘 다 높을수록 문맥 없이는 읽기 어렵다.
    """
    if not is_hangul_word(word):
        return None
    inv = invisibility(word)
    if inv is None:
        return None
    density = 0.0
    if corpus_signatures is not None:
        sig = viseme_signature(word)
        # 같은 입모양을 가진 다른 단어 수(자기 제외), 최대 5로 정규화
        density = round(min(max(corpus_signatures.get(sig, 1) - 1, 0), 5) / 5.0, 3)
    difficulty = round(0.6 * inv + 0.4 * density, 3)
    return {
        "word": word,
        "difficulty": difficulty,
        "invisibility": inv,
        "neighbor_density": density,
        "syllables": sum(1 for c in word if "가" <= c <= "힣"),
        "visemes": word_visemes(word),
    }


def sentence_difficulty(text: str, corpus_signatures: Optional[Counter] = None) -> Dict:
    """문장 난이도 = 구성 단어(어절) 난이도의 평균. 공백으로 어절 분리."""
    words = [w for w in text.split() if is_hangul_word(w)]
    diffs = [d for d in (word_difficulty(w, corpus_signatures) for w in words) if d]
    if not diffs:
        return {"text": text, "difficulty": None, "words": []}
    return {
        "text": text,
        "difficulty": round(sum(d["difficulty"] for d in diffs) / len(diffs), 3),
        "words": diffs,
    }


def build_standard_resources(words: List[str]) -> Dict:
    """동구형이음 사전 + 단어별 난이도 지수 + 최소대립/동구형 쌍을 한 자원으로 조립."""
    valid = [w for w in dict.fromkeys(words) if is_hangul_word(w)]
    sig_count = Counter(viseme_signature(w) for w in valid)
    entries = [word_difficulty(w, sig_count) for w in valid]
    entries = [e for e in entries if e]
    entries.sort(key=lambda e: e["difficulty"])
    try:
        import perceptual_space as _ps
        cons_space = _ps.perceptual_space()
    except Exception:
        cons_space = None  # numpy 미설치 등 → 지각공간은 생략(나머지는 그대로)
    return {
        "meta": {"kind": "korean-speechreading-perceptual-resources", "version": 1,
                 "rules_based": True, "word_count": len(entries)},
        "homophene_dictionary": homophene_dictionary(),
        "consonant_visual_space": cons_space,
        "difficulty_index": entries,
        "lookalike_pairs": discover_pairs(valid),
    }
