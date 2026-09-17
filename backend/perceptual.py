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
import os
from collections import Counter
from typing import Dict, List, Optional

import curriculum as _cur
from content_rules import (VISEME_MAP, discover_pairs, viseme_signature,
                           word_visemes, is_hangul_word, minimal_pair_diff)

# viseme(1~10) 가시성 — 커리큘럼 레슨에서 가져온다(high 잘 보임 ~ low 거의 안 보임).
_VISIBILITY = {l["viseme_id"]: l["visibility"] for l in _cur.VISEME_LESSONS}
_VIS_WEIGHT = {"high": 0.0, "medium": 0.5, "low": 1.0}  # '안 보이는 정도' 가중

# 공개 표준 자원 판본(§3.3 "판본과 함께 공개"). 재현성을 위해 빌드 타임스탬프가 아닌 고정 판을 쓴다.
# 스키마·값이 바뀌면 semver를 올리고 edition(판)을 갱신한다.
RESOURCE_SEMVER = "1.0.0"
RESOURCE_EDITION = "2026-09"
RESOURCE_LICENSE = "CC BY 4.0"
RESOURCE_SOURCE = "LIPLAB (CNSAi)"


def viseme_invisibility(viseme_id: int) -> float:
    """비심의 '안 보이는 정도'(0 뚜렷 ~ 1 안 보임). 난이도 지수(C)의 음소 단위 성분.
    시각 증강(축 J)이 기호 표시 우선순위를 매길 때 재사용한다(안 보이는 비심일수록 우선)."""
    return _VIS_WEIGHT.get(_VISIBILITY.get(viseme_id, "medium"), 0.5)


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


# 비심(1~10)별 소속 음소 수 — 그룹에 음소가 여럿이면 그 입모양은 '동구형이음'(눈으로 구별 불가).
_VIS_GROUP_SIZE = Counter(v for v in VISEME_MAP.values() if 1 <= v <= 10)


def homophene_ratio(word: str) -> Optional[float]:
    """단어 음소 중 '입모양이 같은 다른 음소가 있는'(동구형이음) 비율(0~1).
    난이도 지수(계획서 §3.3 '동구형이음 비율')의 corpus 비의존 성분 — 코퍼스 없이 라이브 계산."""
    vis = word_visemes(word)
    if not vis:
        return None
    amb = sum(1 for v in vis if _VIS_GROUP_SIZE.get(v, 1) >= 2)
    return round(amb / len(vis), 3)


def word_difficulty(word: str, corpus_signatures: Optional[Counter] = None) -> Optional[Dict]:
    """
    단어의 독화 난이도 지수(0 쉬움 ~ 1 어려움).
      · 안 보이는 정도(invisibility): 입 안쪽 자음처럼 눈에 안 드러나는 음소 비중.
      · 동구형이음 비율(homophene_ratio): 입모양이 같은 다른 음소가 있는 음소 비중(corpus 비의존).
      · 혼동 이웃 밀도(neighbor_density): 같은 입모양으로 보이는 '다른 단어' 수(corpus 있을 때만).
    셋 다 높을수록 문맥 없이는 읽기 어렵다. corpus가 없으면 이웃밀도는 0이지만, 동구형이음
    비율이 시각 혼동을 잡아 라이브에서도 난이도가 유효하다.
    """
    if not is_hangul_word(word):
        return None
    inv = invisibility(word)
    if inv is None:
        return None
    homo = homophene_ratio(word) or 0.0
    density = 0.0
    if corpus_signatures is not None:
        sig = viseme_signature(word)
        # 같은 입모양을 가진 다른 단어 수(자기 제외), 최대 5로 정규화
        density = round(min(max(corpus_signatures.get(sig, 1) - 1, 0), 5) / 5.0, 3)
    difficulty = round(0.5 * inv + 0.3 * homo + 0.2 * density, 3)
    return {
        "word": word,
        "difficulty": difficulty,
        "invisibility": inv,
        "homophene_ratio": homo,
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


def build_benchmark(words: List[str], n_per_tier: int = 12, seed: int = 20260916) -> Dict:
    """한국어 독화 능력 **표준 평가셋**(계획서 C). 난이도 3구간(쉬움·보통·어려움)으로 층화해
    각 구간에서 균등 표집한 고정 문항. 문항마다 정답·시각혼동 오답보기·난이도·표적 비심을 담아,
    앱 밖 연구·교육에서도 재현 가능한 벤치마크로 쓴다(결정론적: seed 고정)."""
    import random
    rng = random.Random(seed)
    valid = [w for w in dict.fromkeys(words) if is_hangul_word(w)]
    sig_count = Counter(viseme_signature(w) for w in valid)
    entries = [e for e in (word_difficulty(w, sig_count) for w in valid) if e]
    if not entries:
        return {"tiers": [], "items": []}
    entries.sort(key=lambda e: e["difficulty"])
    N = len(entries)
    tiers = [("easy", 0, N // 3), ("medium", N // 3, 2 * N // 3), ("hard", 2 * N // 3, N)]
    items = []
    for tier, lo, hi in tiers:
        pool = entries[lo:hi] or entries
        k = min(n_per_tier, len(pool))
        step = max(1, len(pool) // k)
        picked = [pool[i * step] for i in range(k)]
        for e in picked:
            ans = e["word"]
            sig = viseme_signature(ans)
            same = [w for w in valid if w != ans and viseme_signature(w) == sig]
            mp = [w for w in valid if w != ans and minimal_pair_diff(ans, w) is not None]
            cand = list(dict.fromkeys(same + mp))
            rng.shuffle(cand)
            opts = cand[:3]
            if len(opts) < 3:
                rest = [w for w in valid if w != ans and w not in opts]; rng.shuffle(rest)
                opts += rest[:3 - len(opts)]
            options = opts + [ans]; rng.shuffle(options)
            items.append({"id": f"bm_{tier}_{len(items)}", "answer": ans, "options": options,
                          "tier": tier, "difficulty": e["difficulty"], "visemes": e["visemes"],
                          "n_homophenes": len(same)})
    return {"n_items": len(items), "tiers": [t[0] for t in tiers], "seed": seed, "items": items}


def load_data_similarity() -> Optional[Dict]:
    """C 실화자 데이터로 산출한 자모 시각유사도(있으면). 규칙판과 별개로 공개 리소스에 포함."""
    import json
    for p in ("data/c_jamo_similarity.json",
              os.path.expanduser("~/Downloads/liplab-lab/data/c_out/c_jamo_similarity.json")):
        if os.path.exists(p):
            try:
                return json.load(open(p, encoding="utf-8"))
            except Exception:
                pass
    return None


def build_standard_resources(words: List[str]) -> Dict:
    """동구형이음 사전 + 단어별 난이도 지수 + 최소대립/동구형 쌍 + 표준 평가셋을 한 자원으로 조립."""
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
    data_sim = load_data_similarity()
    return {
        "meta": {"kind": "korean-speechreading-perceptual-resources", "version": 2,
                 "semver": RESOURCE_SEMVER, "edition": RESOURCE_EDITION,
                 "license": RESOURCE_LICENSE, "source": RESOURCE_SOURCE,
                 "rules_based": True, "word_count": len(entries),
                 "note": "난이도지수·동구형이음사전·시각공간·평가셋은 규칙기반. jamo_visual_similarity_data는 "
                         "실화자 데이터 유래(별도 검증)."},
        "homophene_dictionary": homophene_dictionary(),
        "consonant_visual_space": cons_space,
        "difficulty_index": entries,
        "lookalike_pairs": discover_pairs(valid),
        "standard_benchmark": build_benchmark(valid),
        "jamo_visual_similarity_data": data_sim,
    }
