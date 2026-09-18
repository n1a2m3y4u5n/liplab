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


def build_progression_forms(words: List[str], n: int = 8, seed: int = 7) -> Dict[str, List[Dict]]:
    """향상도검사용 동형 폼 A(사전)·B(사후). 난이도 스펙트럼을 짝/홀로 이등분해 두 폼의
    난이도 분포를 맞춘다(동형). 사전에 A, 사후에 B를 풀면 통제된 사전·사후 비교가 된다."""
    random.seed(seed)
    words = [w for w in dict.fromkeys(words) if _cr.is_hangul_word(w)]
    sig = Counter(_cr.viseme_signature(w) for w in words)
    entries = [e for e in (_perc.word_difficulty(w, sig) for w in words) if e]
    entries.sort(key=lambda e: e["difficulty"])
    if not entries:
        return {"A": [], "B": []}
    # 난이도 정렬을 인접쌍으로 묶어 한쪽은 A, 다른 쪽은 B로 → 두 폼 난이도 매칭
    forms = {"A": [], "B": []}
    per = min(n, len(entries) // 2) if len(entries) >= 2 else len(entries)
    step = max(1, len(entries) // max(1, per))
    for i in range(per):
        base = i * step
        for key, off in (("A", 0), ("B", 1)):
            idx = min(base + off, len(entries) - 1)
            e = entries[idx]
            opts = _confusable_options(e["word"], words) + [e["word"]]
            random.shuffle(opts)
            forms[key].append({"id": f"{key}{i + 1}", "word": e["word"], "options": opts,
                               "difficulty": e["difficulty"], "visemes": e["visemes"]})
    return forms


def _word_phonemes(word: str) -> List[str]:
    """한글 단어 → 자모(초·중·종) 리스트. 음소 단위 오류 프로파일용."""
    out = []
    for ch in word:
        o = ord(ch)
        if 0xAC00 <= o <= 0xD7A3:
            s = o - 0xAC00
            cho, jung, jong = s // 588, (s % 588) // 28, s % 28
            CHO = list('ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ')
            JUNG = list('ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ')
            JONG = list('ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ')
            out.append(CHO[cho]); out.append(JUNG[jung])
            if jong:
                out.append(JONG[jong - 1])
    return out


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


def estimate_ability(asked: List[Dict], responses: Dict[str, str]) -> Dict:
    """검사 진행 중 러닝 능력추정. asked=이미 낸 문항들(difficulty·visemes 포함),
    responses={문항ID: 고른 단어}. θ(ability)는 '통과한 최고 난이도와 실패한 최저 난이도의
    경계'로 추정하고, 오답 문항의 안 보이는 자질을 누적해 표적(error_visemes)을 만든다.
    적응형 출제(select_next_item)와 진행 중 표시에 쓰인다(최종 채점은 score_placement가 담당)."""
    by_id = {it["id"]: it for it in asked}
    solved, failed = [], []
    err = Counter()
    for iid, chosen in responses.items():
        it = by_id.get(iid)
        if not it:
            continue
        if chosen == it["word"]:
            solved.append(it["difficulty"])
        else:
            failed.append(it["difficulty"])
            for v in it.get("visemes", []):
                err[v] += 1
    if solved and failed:
        theta = (max(solved) + min(failed)) / 2.0
    elif solved:
        theta = min(1.0, max(solved) + 0.12)   # 다 맞음 → 더 어렵게
    elif failed:
        theta = max(0.0, min(failed) - 0.12)    # 다 틀림 → 더 쉽게
    else:
        theta = 0.5                              # 시작: 중간 난이도
    return {"ability": round(theta, 3),
            "error_visemes": [v for v, _ in err.most_common(3)],
            "answered": len(solved) + len(failed)}


def select_next_item(asked: List[Dict], responses: Dict[str, str],
                     words: List[str], seed: Optional[int] = None) -> Optional[Dict]:
    """적응형 다음 문항 1개. 추정 능력 θ에 난이도가 가장 가까운 단어를 고르되(난이도지수 C 기반),
    누적 오답 자질(표적)을 포함하는 단어를 우선한다. 이미 낸 단어는 제외. 후보 없으면 None.
    build_placement_items/build_progression_forms(동형폼)는 손대지 않는 별도 경로다."""
    rng = random.Random(seed)
    words = [w for w in dict.fromkeys(words) if _cr.is_hangul_word(w)]
    used = {it["word"] for it in asked}
    sig = Counter(_cr.viseme_signature(w) for w in words)
    entries = [e for e in (_perc.word_difficulty(w, sig) for w in words)
               if e and e["word"] not in used]
    if not entries:
        return None
    est = estimate_ability(asked, responses)
    theta = est["ability"]
    targets = set(est["error_visemes"])

    def key(e):
        close = -abs(e["difficulty"] - theta)          # 1순위: θ 근접
        hit = 1 if (targets and set(e["visemes"]) & targets) else 0  # 2순위: 약점 자질 겨냥
        return (round(close, 3), hit, rng.random())
    best = max(entries, key=key)
    opts = _confusable_options(best["word"], words) + [best["word"]]
    rng.shuffle(opts)
    return {"id": f"q{len(asked) + 1}", "word": best["word"], "options": opts,
            "difficulty": best["difficulty"], "visemes": best["visemes"]}


def score_placement(items: List[Dict], responses: Dict[str, str]) -> Dict:
    """
    배치검사 채점. responses: {문항ID: 고른 단어}.
    능력 = 통과한 문항 중 최고 난이도(어려운 걸 맞출수록 높다). 오류 프로파일 = 틀린 문항의 음소.
    """
    by_id = {it["id"]: it for it in items}
    n = len(items)
    correct = 0
    err = Counter()
    perr = Counter()   # 음소 단위 오류
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
            # 음소 단위: 정답 단어의 자모 중 시각적으로 안 드러나는 것을 카운트
            for ph in _word_phonemes(it["word"]):
                perr[ph] += 1
    ability = max(solved_diff) if solved_diff else 0.0
    level = min(5, max(1, int(ability * 4) + 1)) if solved_diff else 1
    return {
        "total": n,
        "correct": correct,
        "accuracy": round(correct / n, 3) if n else 0.0,
        "ability": round(ability, 3),
        "level": level,
        "error_visemes": [v for v, _ in err.most_common(3)],
        "error_phonemes": [{"phoneme": p, "count": c} for p, c in perr.most_common(6)],
        "recommended_start": _recommended_stage(level),
    }
