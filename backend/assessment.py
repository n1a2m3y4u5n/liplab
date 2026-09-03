"""
디지털 독화 표준검사 — 고도화 축 I.

계획서 §3.9: 독화 실력을 재는 표준 검사가 국내에 없어, 학습자의 현재 수준과 향상도를
객관적으로 판단할 근거가 없다. 이 모듈은 지각 난이도 지수(perceptual, 축 C)로 난이도를
통제한 문항을 구성해 **배치검사(초기 수준 진단)**와 **음소별 오류 프로파일**을 제공한다.

개발용 공개 자원(C)과 사용자 대상 검사(I)는 역할이 다르다: C는 앱 밖 공개 계수, I는 개인 진단.
문항은 '입모양을 보고 단어 맞추기'(4지선다)이며, 오답 보기는 정답과 시각적으로 혼동되는
(동구형이음·최소대립) 단어를 우선 배치해 실제 독화 변별력을 잰다.

지각공간 임베딩(데이터 기반)이 준비되면 난이도 통제를 정교화한다(Phase 2).
"""
import random
from collections import Counter
from typing import Dict, List, Optional

import content_rules as _cr
import curriculum as _cur
import perceptual as _perc


def _confusable_options(answer: str, pool: List[str], k: int = 3) -> List[str]:
    """정답과 시각적으로 혼동되는 오답 보기 k개(동구형이음·최소대립 우선, 부족하면 임의)."""
    sig = _cr.viseme_signature(answer)
    same = [w for w in pool if w != answer and _cr.viseme_signature(w) == sig]
    mp = [w for w in pool if w != answer and _cr.minimal_pair_diff(answer, w) is not None]
    cand = list(dict.fromkeys(same + mp))
    random.shuffle(cand)
    opts = cand[:k]
    if len(opts) < k:
        rest = [w for w in pool if w != answer and w not in opts]
        random.shuffle(rest)
        opts += rest[:k - len(opts)]
    return opts


def build_placement_items(words: List[str], n: int = 8, seed: Optional[int] = None) -> List[Dict]:
    """난이도 스펙트럼에서 균등 표집한 배치검사 문항 n개(쉬움→어려움)."""
    if seed is not None:
        random.seed(seed)
    words = [w for w in dict.fromkeys(words) if _cr.is_hangul_word(w)]
    sig = Counter(_cr.viseme_signature(w) for w in words)
    entries = [e for e in (_perc.word_difficulty(w, sig) for w in words) if e]
    entries.sort(key=lambda e: e["difficulty"])
    if not entries:
        return []
    n = min(n, len(entries))
    step = len(entries) / n
    items = []
    for i in range(n):
        e = entries[int(i * step)]
        opts = _confusable_options(e["word"], words) + [e["word"]]
        random.shuffle(opts)
        items.append({"id": f"q{i + 1}", "word": e["word"], "options": opts,
                      "difficulty": e["difficulty"], "visemes": e["visemes"]})
    return items


def _recommended_stage(level: int) -> Dict:
    """추정 수준(1~5)으로 시작 학습 단계 추천(커리큘럼 STAGES)."""
    if level <= 1:
        key = "viseme"
    elif level <= 3:
        key = "word"
    else:
        key = "sentence"
    stg = next((s for s in _cur.STAGES if s["key"] == key), None)
    return {"stage": stg["stage"], "key": key, "title": stg["title"]} if stg else {"key": key}


def score_placement(items: List[Dict], responses: Dict[str, str]) -> Dict:
    """
    배치검사 채점. responses: {문항ID: 고른 단어}.
    능력 = 통과한 문항 중 최고 난이도(어려운 걸 맞출수록 높다). 오류 프로파일 = 틀린 문항의 음소.
    """
    by_id = {it["id"]: it for it in items}
    n = len(items)
    correct = 0
    err = Counter()
    solved_diff = []
    for iid, chosen in responses.items():
        it = by_id.get(iid)
        if not it:
            continue
        if chosen == it["word"]:
            correct += 1
            solved_diff.append(it["difficulty"])
        else:
            for v in it["visemes"]:
                err[v] += 1
    ability = max(solved_diff) if solved_diff else 0.0
    level = min(5, max(1, int(ability * 4) + 1)) if solved_diff else 1
    return {
        "total": n,
        "correct": correct,
        "accuracy": round(correct / n, 3) if n else 0.0,
        "ability": round(ability, 3),
        "level": level,
        "error_visemes": [v for v, _ in err.most_common(3)],
        "recommended_start": _recommended_stage(level),
    }
