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
import math
import os
import random
from collections import Counter
from typing import Dict, List, Optional

import content_rules as _cr
import curriculum as _cur
import perceptual as _perc

# 동형 폼 A/B 판본 동결 파일. 콘텐츠(WORD_BANK)가 바뀌어도 사전·사후가 같은 문항을 쓰게 한다.
# v2(9/27): v1의 정답·문항 id는 그대로 두고, 입모양으로 가를 수 없는 오답(준동구형 포함)과 드문 말 오답을 바꿨다
# (`revise_forms`, docs/assessment-design.md 7절). v1은 B에 가를 수 없는 오답이 6개(A 1개)라 B가 더 어려웠다.
FORMS_VERSION = "v2"
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


def indistinguishable(a: str, b: str) -> bool:
    """입모양만으로 가를 수 없는가. 입 안쪽 무리({6,7,8,10})를 한 기호로 묶은 입모양 열이 같으면 그렇다(동구형이음과,
    입 안쪽 차이만 있는 준동구형). 거리로 재면 안쪽 차이가 두 자리일 때 1.0이 되어 가를 수 있는 것처럼 보였다(닭/갓)."""
    inside = _cr._INSIDE_CLUSTER
    def g(w):
        return tuple("C" if v in inside else v for v in _cr.viseme_signature(w))
    return g(a) == g(b)


def _confusable_options(answer: str, pool: List[str], k: int = 3, closeness: float = 0.5,
                        rng: Optional[random.Random] = None) -> List[str]:
    """오답 보기 k개를 입모양 거리로 고른다.

    입모양이 정답과 완전히 같은 단어(동구형이음, 거리 0)는 입만 보고는 원리적으로 구별할 수 없어
    독화 능력이 아니라 운을 재게 되므로 제외한다. closeness(0~1, 보통 문항 난이도)가 클수록 가까운
    (헷갈리는) 보기, 작을수록 거리 순위 중간쯤의 보기를 쓴다(맨 끝의 무관한 단어는 피한다).
    같은 음절 수 후보가 충분하면 그 안에서 고른다."""
    rng = rng or random
    cands = [(viseme_distance(answer, w), w) for w in pool if w != answer]
    # 동구형이음과 입 안쪽 무리 차이뿐인 준동구형은 입모양으로 가를 수 없어 뺀다(9/27부터 준동구형도 뺌)
    cands = [c for c in cands if c[0] > 0 and not indistinguishable(answer, c[1])]
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


def revise_forms(forms: Dict, words: List[str], excluded) -> Dict:
    """판본 개정(v1 → v2). 정답·문항 id·보기 자리는 그대로 두고, 쓸 수 없는 오답만 바꾼다.
    쓸 수 없는 오답: 정답과 입모양으로 가를 수 없는 단어(indistinguishable)와 드문 말(excluded, curriculum.STAGE2_EXCLUDED).
    바꿀 단어: 같은 음절 수, 쓸 수 있는 단어 가운데 원래 오답과 정답 사이의 입모양 거리에 가장 가까운 것(가를 수 없는 오답이면
    거리 1 이상 중 가장 가까운 것). 거리 차가 같으면 그 폼에서 덜 쓴 단어를 먼저 쓴다. 두 폼의 정답 단어와 이미 있는 보기는
    쓰지 않는다. 결정론적(거리 차, 폼 안 사용 수, 거리, 단어 순).
    반환 {"A", "B", "changes": [{id, answer, old, new, old_dist, new_dist, why}]}."""
    excluded = set(excluded or ())
    words = [w for w in dict.fromkeys(words) if _cr.is_hangul_word(w) and w not in excluded]
    answers = {it["word"] for k in ("A", "B") for it in forms.get(k, [])}
    out = {"A": [], "B": [], "changes": []}
    for key in ("A", "B"):
        used: Counter = Counter(o for it in forms.get(key, []) for o in it["options"])   # 한 폼 안에서 같은 오답이 겹치지 않게
        for it in forms.get(key, []):
            ans = it["word"]
            opts = list(it["options"])
            for i, o in enumerate(opts):
                if o == ans:
                    continue
                d_old = viseme_distance(ans, o)
                near, rare = indistinguishable(ans, o), o in excluded
                if not (near or rare):
                    continue
                target = max(1.0, d_old)
                cands = [(viseme_distance(ans, w), w) for w in words
                         if w not in answers and w not in opts and len(w) == len(ans)]
                cands = [c for c in cands if c[0] > 0 and not indistinguishable(ans, c[1])]
                if not cands:
                    continue
                d_new, w_new = min(cands, key=lambda c: (abs(c[0] - target), used[c[1]], c[0], c[1]))
                opts[i] = w_new
                used[w_new] += 1
                out["changes"].append({"id": it["id"], "answer": ans, "old": o, "new": w_new,
                                       "old_dist": d_old, "new_dist": d_new,
                                       "why": "near" if near else "rare"})
            out[key].append({**it, "options": opts})
    return out


# v2에서 짝(난이도 인접 A_i·B_i)의 폼을 맞바꾼 번호(1부터). 오답 교체 뒤 가상 학습자(시드 1)로 두 폼 정답률 차를 가장 작게
# 하는 교환 조합을 두 잡음 모형(균등·입 안쪽 혼동)의 여섯 조건에서 함께 찾았고(0~4쌍 전수), 판정은 시드 3으로 따로 했다
# (docs/assessment-design.md 7절). 한 모형(균등)만 보고 고른 조합(21, 22)은 다른 모형의 높은 잡음에서 2.2점 차가 남았다.
V2_PAIR_SWAPS = (14, 17, 19, 24)


def swap_pairs(forms: Dict, pairs) -> Dict:
    """짝 번호(1부터)의 A·B 문항을 맞바꾼다. 문항 id는 자리(A21·B21)를 따른다."""
    out = {"A": [dict(it) for it in forms["A"]], "B": [dict(it) for it in forms["B"]]}
    for p in pairs:
        i = p - 1
        a, b = out["A"][i], out["B"][i]
        out["A"][i] = {**b, "id": a["id"]}
        out["B"][i] = {**a, "id": b["id"]}
    return out


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


# 능력 추정(docs/assessment-design.md 10절). 예전 '맞힌 문항 중 최고 난이도'는 4지선다 우연 정답 하나로 수준이 뛰었다(폼에서
# 가상 학습자의 20%가 실제 입모양·단어 수준인데 문장 단계를 추천받음). 이제 우연 정답(1/보기 수)을 반영한 사후 평균(EAP):
# 격자 201점, 사전 N(0.55, 0.25)를 [0, 1]에 자름, 기울기 10. 시드 1 확인에서 시작 단계 일치 폼 50.8 → 80.1%, 적응형 70.5 → 75.1%.
_EAP_GRID = [i / 200 for i in range(201)]
_EAP_SLOPE = 10.0
_EAP_PRIOR = (0.55, 0.25)


def _posterior(answered) -> List[float]:
    """_EAP_GRID 위의 정규화된 사후분포. answered = [(난이도, 정답 여부, 보기 수)]."""
    m, sd = _EAP_PRIOR
    logp = [-(g - m) ** 2 / (2 * sd * sd) for g in _EAP_GRID]
    for d, ok, k in answered:
        c = 1.0 / max(2, int(k or 4))
        for j, g in enumerate(_EAP_GRID):
            p = c + (1 - c) / (1 + math.exp(-_EAP_SLOPE * (g - d)))
            logp[j] += math.log(p if ok else 1 - p)
    top = max(logp)
    w = [math.exp(x - top) for x in logp]
    tot = sum(w)
    return [x / tot for x in w]


def ability_eap(answered) -> float:
    """answered = [(난이도, 정답 여부, 보기 수)]. 답한 문항이 없으면 0."""
    if not answered:
        return 0.0
    return sum(g * w for g, w in zip(_EAP_GRID, _posterior(answered)))


# 적응형 배치검사 길이(docs/assessment-design.md 12절). 예전에는 누구에게나 8문항이었다. 이제 최소 5문항 뒤 한 시작 단계의
# 사후 확률이 0.85 이상이면 끝내고, 아니면 12문항까지 낸다. 시드 1 확인에서 평균 7.78문항으로 시작 단계 일치 77.7 → 80.7%.
ADAPTIVE_MAX_ITEMS = 12
STOP_MIN_ITEMS = 5
STOP_CONFIDENCE = 0.85
_STAGE_CUTS = (0.25, 0.75)   # 수준 1|2, 3|4 = 시작 단계 입모양|단어|문장(level_of·_recommended_stage와 같은 경계)


def stage_probabilities(answered) -> List[float]:
    """세 시작 단계(입모양·단어·문장)의 사후 확률. 답한 문항이 없으면 사전분포 기준."""
    w = _posterior(answered)
    lo, hi = _STAGE_CUTS
    return [sum(x for g, x in zip(_EAP_GRID, w) if g < lo),
            sum(x for g, x in zip(_EAP_GRID, w) if lo <= g < hi),
            sum(x for g, x in zip(_EAP_GRID, w) if g >= hi)]


def level_of(ability: float) -> int:
    return min(5, max(1, int(ability * 4) + 1))


def rescore_log(item_log) -> Optional[Dict]:
    """저장된 문항 기록(item_log: id·word·chosen·correct·difficulty)을 지금 추정기로 다시 채점한다. 사전·사후 비교에서 채점
    방식이 섞이지 않게 한다. 답한 문항이 없거나 난이도가 없으면 None. 보기 수는 기록에 없어 4로 본다(폼·적응형 모두 4지선다)."""
    ans = [(float(it["difficulty"]), bool(it.get("correct")), 4) for it in (item_log or [])
           if isinstance(it, dict) and it.get("chosen") is not None and isinstance(it.get("difficulty"), (int, float))]
    if not ans:
        return None
    a = ability_eap(ans)
    return {"ability": round(a, 3), "level": level_of(a)}


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
    responses={문항ID: 고른 단어}. θ(ability)는 최종 채점과 같은 EAP(ability_eap, 답이 없으면 사전 평균 0.55)이고,
    오답 문항의 안 보이는 자질을 누적해 표적(error_visemes)을 만든다. 적응형 출제(select_next_item)와 진행 중 표시에 쓰인다.
    예전 경계 추정('통과한 최고 난이도와 실패한 최저 난이도의 중간')은 우연 정답에 흔들렸다. EAP로 고르면 시드 1 확인에서
    시작 단계 일치 75.1 → 77.7%, 과소배치 14.2 → 10.8%(docs/assessment-design.md 11절)."""
    by_id = {it["id"]: it for it in asked}
    answered = []
    err = Counter()
    for iid, chosen in responses.items():
        it = by_id.get(iid)
        if not it:
            continue
        ok = chosen == it["word"]
        answered.append((it["difficulty"], ok, len(it.get("options") or []) or 4))
        if not ok:
            for v in it.get("visemes", []):
                err[v] += 1
    theta = ability_eap(answered) if answered else _EAP_PRIOR[0]
    conf = max(stage_probabilities(answered))
    return {"ability": round(theta, 3),
            "error_visemes": [v for v, _ in err.most_common(3)],
            "answered": len(answered),
            "stage_confidence": round(conf, 3),
            "confident": len(answered) >= STOP_MIN_ITEMS and conf >= STOP_CONFIDENCE}


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


def _misread_phonemes(word: str, confs) -> List[str]:
    """틀린 문항에서 오류로 셀 자모. 음소 단위 오류는 실제로 잘못 읽은 자모(대조에서 다른 자리)만 센다(I-5). 예전에는 정답
    단어의 안 보이는 자모를 모두 세어, 맞게 읽은 자모까지 약점으로 잡혔다. 대조가 안 되면 예전 방식(단어의 자모 전부)으로
    대신한다. 소리 없는 초성 ㅇ(viseme None)은 놓친 소리가 아니라 없는 자음을 읽은 것이라 세지 않는다('자주 놓친 소리 ㅇ'이 떴다)."""
    if confs:
        return [c["target"] for c in confs if c["viseme"] is not None]
    return _word_phonemes(word)


def score_placement(items: List[Dict], responses: Dict[str, str]) -> Dict:
    """
    배치검사 채점. responses: {문항ID: 고른 단어}.
    능력 = 우연 정답을 반영한 사후 평균(ability_eap, 예전에는 통과한 문항 중 최고 난이도). 오류 프로파일 = 틀린 문항의 음소.
    """
    from scoring import viseme_confusions
    n = len(items)
    correct = 0
    err = Counter()
    perr = Counter()   # 음소 단위 오류
    conf = Counter()   # 오독 방향: (정답 자모, 읽은 자모, 입모양 이름, 같은 입모양 여부)
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
        else:
            for v in it["visemes"]:
                err[v] += 1
            # 무엇을 무엇으로 읽었는지(오답 보기와 자모 단위 대조)
            confs = viseme_confusions(it["word"], chosen)
            for c in confs:
                conf[(c["target"], c["read"], c["viseme_name_ko"], c["same_viseme"])] += 1
            perr.update(_misread_phonemes(it["word"], confs))
    answered = [(it["difficulty"], responses.get(it.get("id")) == it["word"], len(it.get("options") or []) or 4)
                for it in items if responses.get(it.get("id")) is not None]
    ability = ability_eap(answered)
    level = level_of(ability) if answered else 1
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


def error_counts(item_log) -> Optional[Dict]:
    """문항 기록(item_log: word·chosen)에서 입모양·자모 오류를 자르지 않고 다시 센다. 사전·사후 비교 전용이다.
    저장된 error_visemes(상위 3)·error_phonemes(상위 6)는 화면용으로 잘린 목록이라, 그것끼리 비교하면 순위만 밀린 입모양·
    자모도 '극복'으로 나왔다. 입모양은 score_placement처럼 틀린 문항 단어의 입모양마다 1씩 센다(item_log에 입모양이 없어
    단어에서 다시 구한다. 동결 폼 48문항에서 저장값과 모두 같다). seen_*은 그 입모양·자모가 든 답한 문항 수다.
    답한 문항이 없거나 기록이 없는 옛 검사는 None."""
    from scoring import viseme_confusions
    rows = [it for it in (item_log or [])
            if isinstance(it, dict) and it.get("word") and it.get("chosen") is not None]
    if not rows:
        return None
    vis, seen_v, pho, seen_p = Counter(), Counter(), Counter(), Counter()
    for it in rows:
        word, chosen = it["word"], it["chosen"]
        vids = _cr.word_visemes(word)
        seen_v.update(set(vids))
        seen_p.update(set(_word_phonemes(word)))
        if chosen == word:
            continue
        vis.update(vids)
        pho.update(_misread_phonemes(word, viseme_confusions(word, chosen)))
    return {"visemes": vis, "seen_visemes": seen_v, "phonemes": pho, "seen_phonemes": seen_p}


def phoneme_change(base_log, late_log) -> List[Dict]:
    """사전·사후 자모별 오류 수 변화(전체 개수). 두 검사 모두 그 자모가 든 문항을 풀었을 때만 싣는다. 동결 폼 v2에도 A에만
    있는 자모(ㄸ·ㅃ·ㅋ·ㅐ·ㅝ)가 있어, 이 조건이 없으면 A→B 모의 비교(두 검사 6문항 오답) 보고서의 92.3%에 사후에 묻지 않은
    자모가 'n→0'으로 나왔다. 예전에는 두 검사의 상위 6개끼리 비교해, 'after 0'이 나온 보고서의 93.6%에서 그 자모가 사후에도
    틀렸다(지금 0%). 문항 기록이 없는 검사가 끼면 비운다."""
    ea, eb = error_counts(base_log), error_counts(late_log)
    if not (ea and eb):
        return []
    phonemes = sorted(p for p in set(ea["phonemes"]) | set(eb["phonemes"])
                      if ea["seen_phonemes"][p] and eb["seen_phonemes"][p])
    return [{"phoneme": p, "before": ea["phonemes"][p], "after": eb["phonemes"][p],
             "delta": eb["phonemes"][p] - ea["phonemes"][p]} for p in phonemes]


def improvement_delta(baseline: Dict, latest: Dict, base_log=None, late_log=None) -> Dict:
    """첫 검사(baseline)와 최근 검사(latest)의 향상도 — 각 지표의 증감과 극복/신규 취약 입모양.
    훈련 전/후를 같은 척도로 비교해 '실제로 나아졌는지'를 객관 수치로 준다. 순수 함수.
    극복(resolved)은 첫 검사에서 틀렸고, 최근 검사에서 그 입모양이 든 문항을 1개 이상 풀었으며 오류가 0인 입모양이다.
    신규(new_error)는 거꾸로 첫 검사에서 그 입모양이 든 문항을 풀었고 오류가 0이었는데 최근 검사에서 틀린 입모양이다.
    둘 다 두 검사의 문항 기록(base_log·late_log)을 다시 센 전체 개수로 정하고, 기록이 없는 검사가 끼면 비운다.
    예전에는 저장된 상위 3개끼리의 차집합이라, 폼 A 재검사 모의(두 검사 6문항 오답)에서 극복 목록이 뜬 보고서의 99.2%에
    최근 검사에서도 틀린 입모양이 있었다(지금 0%)."""
    def g(d, k, dflt=0.0):
        return (d or {}).get(k, dflt)
    ea, eb = error_counts(base_log), error_counts(late_log)
    resolved, new = [], []
    if ea and eb:
        resolved = sorted(v for v in ea["visemes"] if eb["seen_visemes"][v] and not eb["visemes"][v])
        new = sorted(v for v in eb["visemes"] if ea["seen_visemes"][v] and not ea["visemes"][v])
    return {
        "accuracy": round(g(latest, "accuracy") - g(baseline, "accuracy"), 3),
        "ability": round(g(latest, "ability") - g(baseline, "ability"), 3),
        "level": int(g(latest, "level", 1)) - int(g(baseline, "level", 1)),
        "resolved_visemes": resolved,     # 예전엔 틀렸는데 이제 안 틀림
        "new_error_visemes": new,         # 새로 약해진 입모양
    }


if __name__ == "__main__":
    # 동형 폼 동결: python assessment.py freeze [--force]
    # 지금 단어 은행으로 A/B를 고정 시드로 만들어 data/assessment/forms_<판본>.json에 저장한다.
    # 이미 있으면 덮어쓰지 않는다(판본을 바꾸려면 FORMS_VERSION을 올린다).
    import sys
    if len(sys.argv) >= 2 and sys.argv[1] == "revise":
        # python assessment.py revise: forms_v1.json → forms_<FORMS_VERSION>.json(쓸 수 없는 오답만 교체)
        src = os.path.join(os.path.dirname(_FORMS_PATH), "forms_v1.json")
        if os.path.exists(_FORMS_PATH) and "--force" not in sys.argv:
            print(f"이미 있음: {_FORMS_PATH} (덮어쓰려면 --force)")
            sys.exit(1)
        with open(src, encoding="utf-8") as f:
            v1 = json.load(f)
        rev = revise_forms(v1, [w["word"] for w in _cur.WORD_BANK], getattr(_cur, "STAGE2_EXCLUDED", {}))
        sw = swap_pairs(rev, V2_PAIR_SWAPS)
        with open(_FORMS_PATH, "w", encoding="utf-8") as f:
            json.dump({"version": FORMS_VERSION, "revised_from": v1.get("version"), "n_bank": len(_cur.WORD_BANK),
                       "pair_swaps": list(V2_PAIR_SWAPS), "A": sw["A"], "B": sw["B"], "changes": rev["changes"]},
                      f, ensure_ascii=False, indent=1)
        print(f"개정 {_FORMS_PATH}: 오답 {len(rev['changes'])}개 교체")
        sys.exit(0)
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
        print("사용법: python assessment.py freeze|revise [--force]")
