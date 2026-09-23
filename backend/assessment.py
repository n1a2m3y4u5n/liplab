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
import json
import os
import random
from collections import Counter
from typing import Dict, List, Optional

import content_rules as _cr
import curriculum as _cur
import perceptual as _perc

# 동형 폼 A/B 판본 동결 파일. 콘텐츠(WORD_BANK)가 바뀌어도 사전·사후가 같은 문항을 쓰게 한다.
FORMS_VERSION = "v1"
# 사전·사후 폼 길이. 합성 응답 시뮬레이션(scripts/assessment_reliability_sim.py)에서 8문항은 KR-20≈0.52,
# 24문항은 ≈0.76이라 집단 비교 기준(0.7)을 넘기려고 24로 둔다(docs/assessment-design.md). 배치검사는 8문항.
FORM_LENGTH = 24
_FORMS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "assessment",
                           f"forms_{FORMS_VERSION}.json")


def viseme_distance(a: str, b: str) -> float:
    """두 단어 입모양 순열 사이의 거리(가중 편집거리). 치환 비용: 같은 비심 0, 둘 다 입 안쪽
    무리({6,7,8,10}, 눈으로 거의 못 가름) 0.5, 그 외 1. 삽입·삭제 1. 0이면 입모양이 완전히 같다."""
    sa, sb = _cr.viseme_signature(a), _cr.viseme_signature(b)
    inside = _cr._INSIDE_CLUSTER
    prev = [float(j) for j in range(len(sb) + 1)]
    for i in range(1, len(sa) + 1):
        cur = [float(i)] + [0.0] * len(sb)
        for j in range(1, len(sb) + 1):
            x, y = sa[i - 1], sb[j - 1]
            sub = 0.0 if x == y else (0.5 if (x in inside and y in inside) else 1.0)
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + sub)
        prev = cur
    return prev[-1]


def _confusable_options(answer: str, pool: List[str], k: int = 3, closeness: float = 0.5,
                        rng: Optional[random.Random] = None) -> List[str]:
    """오답 보기 k개를 입모양 거리로 고른다.

    입모양이 정답과 완전히 같은 단어(동구형이음, 거리 0)는 입만 보고는 원리적으로 구별할 수 없어
    독화 능력이 아니라 운을 재게 되므로 제외한다. closeness(0~1, 보통 문항 난이도)가 클수록 가까운
    (헷갈리는) 보기, 작을수록 거리 순위 중간쯤의 보기를 쓴다(맨 끝의 무관한 단어는 피한다).
    같은 음절 수 후보가 충분하면 그 안에서 고른다."""
    rng = rng or random
    cands = [(viseme_distance(answer, w), w) for w in pool if w != answer]
    cands = [c for c in cands if c[0] > 0]
    same_len = [c for c in cands if len(c[1]) == len(answer)]
    base = same_len if len(same_len) >= k * 3 else cands
    if not base:
        return []
    base.sort(key=lambda c: (c[0], c[1]))
    win = max(k, min(len(base), k * 4))
    # 헷갈릴 만한 구간(거리 순 상위 1/4) 안에서만 고른다. 어려운 문항은 그 앞쪽(가까운 쪽), 쉬운 문항은 뒤쪽.
    region = base[:max(win, len(base) // 4)]
    start = int((1.0 - max(0.0, min(1.0, closeness))) * max(0, len(region) - win))
    window = region[start:start + win]
    return [w for _, w in rng.sample(window, min(k, len(window)))]


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
        opts = _confusable_options(e["word"], words, closeness=e["difficulty"]) + [e["word"]]
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
            opts = _confusable_options(e["word"], words, closeness=e["difficulty"]) + [e["word"]]
            random.shuffle(opts)
            forms[key].append({"id": f"{key}{i + 1}", "word": e["word"], "options": opts,
                               "difficulty": e["difficulty"], "visemes": e["visemes"]})
    return forms


def frozen_forms(words: Optional[List[str]] = None, build_if_missing: bool = True) -> Optional[Dict]:
    """동결된 동형 폼 {"version", "A", "B"}. 파일이 있으면 그것을, 없으면 지금 단어 은행으로 만든다
    (만든 결과를 저장하지는 않는다 — 동결은 `python assessment.py freeze`로 명시적으로 한다)."""
    if os.path.exists(_FORMS_PATH):
        with open(_FORMS_PATH, encoding="utf-8") as f:
            return json.load(f)
    if not build_if_missing:
        return None
    words = words if words is not None else [w["word"] for w in _cur.WORD_BANK]
    forms = build_progression_forms(words, n=FORM_LENGTH)
    return {"version": f"{FORMS_VERSION}-unfrozen", "A": forms["A"], "B": forms["B"]}


def test_only_words() -> set:
    """동결 폼 A/B의 정답 단어 — 훈련 콘텐츠에서 빼서 사전·사후가 문항 암기를 재지 않게 한다."""
    f = frozen_forms(build_if_missing=False) or {}
    return {it["word"] for k in ("A", "B") for it in f.get(k, [])}


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
    opts = _confusable_options(best["word"], words, closeness=best["difficulty"], rng=rng) + [best["word"]]
    rng.shuffle(opts)
    return {"id": f"q{len(asked) + 1}", "word": best["word"], "options": opts,
            "difficulty": best["difficulty"], "visemes": best["visemes"]}


def score_placement(items: List[Dict], responses: Dict[str, str]) -> Dict:
    """
    배치검사 채점. responses: {문항ID: 고른 단어}.
    능력 = 통과한 문항 중 최고 난이도(어려운 걸 맞출수록 높다). 오류 프로파일 = 틀린 문항의 음소.
    """
    from scoring import viseme_confusions
    n = len(items)
    correct = 0
    err = Counter()
    perr = Counter()   # 음소 단위 오류
    conf = Counter()   # 오독 방향: (정답 자모, 읽은 자모, 입모양 이름, 같은 입모양 여부)
    solved_diff = []
    item_log = []      # 문항 단위 기록 — 신뢰도(KR-20)·문항 분석의 원자료
    for it in items:
        chosen = responses.get(it.get("id"))
        ok = chosen == it["word"]
        item_log.append({"id": it.get("id"), "word": it["word"], "chosen": chosen,
                         "correct": bool(ok), "difficulty": it.get("difficulty")})
        if chosen is None:
            continue
        if ok:
            correct += 1
            solved_diff.append(it["difficulty"])
        else:
            for v in it["visemes"]:
                err[v] += 1
            # 음소 단위: 정답 단어의 자모 중 시각적으로 안 드러나는 것을 카운트
            for ph in _word_phonemes(it["word"]):
                perr[ph] += 1
            # 무엇을 무엇으로 읽었는지(오답 보기와 자모 단위 대조)
            for c in viseme_confusions(it["word"], chosen):
                conf[(c["target"], c["read"], c["viseme_name_ko"], c["same_viseme"])] += 1
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
        "error_confusions": [{"target": t, "read": r, "viseme": vn, "same_viseme": sv, "count": c}
                             for (t, r, vn, sv), c in conf.most_common(6)],
        "item_log": item_log,
        "recommended_start": _recommended_stage(level),
    }


def improvement_delta(baseline: Dict, latest: Dict) -> Dict:
    """첫 검사(baseline)와 최근 검사(latest)의 향상도 — 각 지표의 증감과 극복/신규 취약 입모양.
    훈련 전/후를 같은 척도로 비교해 '실제로 나아졌는지'를 객관 수치로 준다. 순수 함수."""
    def g(d, k, dflt=0.0):
        return (d or {}).get(k, dflt)
    base_err = set(g(baseline, "error_visemes", []) or [])
    late_err = set(g(latest, "error_visemes", []) or [])
    return {
        "accuracy": round(g(latest, "accuracy") - g(baseline, "accuracy"), 3),
        "ability": round(g(latest, "ability") - g(baseline, "ability"), 3),
        "level": int(g(latest, "level", 1)) - int(g(baseline, "level", 1)),
        "resolved_visemes": sorted(base_err - late_err),   # 예전엔 틀렸는데 이제 안 틀림
        "new_error_visemes": sorted(late_err - base_err),  # 새로 약해진 입모양
    }


if __name__ == "__main__":
    # 동형 폼 동결: python assessment.py freeze [--force]
    # 지금 단어 은행으로 A/B를 고정 시드로 만들어 data/assessment/forms_<판본>.json에 저장한다.
    # 이미 있으면 덮어쓰지 않는다(판본을 바꾸려면 FORMS_VERSION을 올린다).
    import sys
    if len(sys.argv) >= 2 and sys.argv[1] == "freeze":
        if os.path.exists(_FORMS_PATH) and "--force" not in sys.argv:
            print(f"이미 동결됨: {_FORMS_PATH} (덮어쓰려면 --force)")
            sys.exit(1)
        words = [w["word"] for w in _cur.WORD_BANK]
        forms = build_progression_forms(words, n=FORM_LENGTH)
        os.makedirs(os.path.dirname(_FORMS_PATH), exist_ok=True)
        with open(_FORMS_PATH, "w", encoding="utf-8") as f:
            json.dump({"version": FORMS_VERSION, "n_bank": len(words), "A": forms["A"], "B": forms["B"]},
                      f, ensure_ascii=False, indent=1)
        print(f"동결 {_FORMS_PATH}: A {len(forms['A'])}문항, B {len(forms['B'])}문항")
    else:
        print("사용법: python assessment.py freeze [--force]")
