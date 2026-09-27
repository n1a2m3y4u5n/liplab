"""3단계 문장 4지선다의 오답 보기.

예전 보기는 같은 레슨의 다른 문장 3개였고, 세 갈래로 답이 샜다(scripts/sentence_options_sim.py).
1) 뒤에 주관식·서술형으로 나올 문장이 보기로 먼저 보였다(그런 문항의 40~56%, 레슨 문장 5~10개).
2) 앞에서 이미 푼 문장은 정답이 공개된 뒤라 답이 아님을 알고 지울 수 있었다.
3) 보기끼리 길이가 달라 아바타 재생 길이만으로 고를 수 있었다(음절 수를 15% 잡음으로 어림하는 관찰자 정답률 45%, 우연 25%).
이제 레슨 밖 문장 가운데 음절 수가 가까운 것을 고른다. 1)·2)는 없어진다. 3)은 풀 밀도에 달려 있어 코드의 문장(60개)만으로는
41%이고(목표와 2~5음절, 5단계는 13음절까지 차이), 캐시된 LLM 문장이 쌓일수록 준다. 풀은 단계별 대체 문장, 상황 기본 문장, 말하기 문장, 캐시된 LLM
시나리오 문장이다. 모두 다른 레슨에서 정답으로도 나오는 문장이라, 오답으로만 쓰는 전용 문장 은행과 달리 '본 적 있는
문장 = 오답'으로 지울 수 없다. 문맥 추론 문장은 뺀다(빈칸 답이 보기로 먼저 보이면 그쪽 문항이 샌다, 문맥 추론도 3단계 숙달에 든다).
"""
import random
import re
from typing import Iterable, List, Optional


def syllables(text: str) -> int:
    return sum(1 for ch in text or "" if "가" <= ch <= "힣")


def _key(text: str) -> str:
    """구두점·공백을 뺀 비교 키('밥 먹었어요.'와 '밥 먹었어요?'는 입모양이 같아 같은 문장으로 본다)."""
    return re.sub(r"[^가-힣A-Za-z0-9]", "", text or "")


def static_pool() -> List[str]:
    """코드에 든 문장(대체 문장·상황 기본 문장·말하기 문장·억양 문장). 캐시된 LLM 문장은 main이 더한다."""
    import llm_service as _L
    import speak_curriculum as _SC
    out = [s for bank in _L.FALLBACK_BY_LEVEL.values() for s in bank]
    out += [s for v in _L._SITUATION_DEFAULTS.values() for s in v]
    for st in _SC.SPEAK_STAGES:
        if st.get("mode") == "sentence":
            out += [it["target"] for it in st["items"]]
    return list(dict.fromkeys(out))


def pick_options(target: str, pool: Iterable[str], exclude: Iterable[str] = (), k: int = 3, spare: int = 1,
                 rng: Optional[random.Random] = None) -> List[str]:
    """음절 수가 target에 가장 가까운 문장 k+spare개 가운데 무작위 k개. exclude(이번 레슨 문장)와 target은 뺀다.
    spare는 매번 같은 보기만 나오지 않게 두는 여유다(늘리면 길이 맞춤이 느슨해진다)."""
    rng = rng or random
    t = syllables(target)
    banned = {_key(x) for x in exclude} | {_key(target)}
    cands, seen = [], set()
    for p in pool:
        kp = _key(p)
        if p and kp and kp not in banned and kp not in seen:
            seen.add(kp)
            cands.append(p)
    rng.shuffle(cands)
    cands.sort(key=lambda c: abs(syllables(c) - t))
    near = cands[:k + spare]
    return rng.sample(near, k) if len(near) >= k else near
