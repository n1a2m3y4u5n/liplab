"""
LIPLAB 콘텐츠 대량화 파이프라인 — 고도화 축 G.

설계 원칙: **생성은 LLM, 관계는 규칙.**
  1) 단어는 Claude가 대량 생성하고, content_rules.check_word 게이트로 거른다.
  2) '눈으로 헷갈리는 쌍'(동구형이음·최소대립)은 LLM에게 맡기지 않고
     content_rules.discover_pairs가 비심 규칙으로 결정론적으로 발굴한다.
  3) 문맥 추론(closure) 문장만 Claude가 만들되, 오답 보기는 이미 규칙으로 확정한
     혼동 파트너를 넣고 check_closure 게이트로 재검증한다.

생성물은 status="candidate"로 저장된다. 앱에 반영하려면 사람 검수를 거쳐
status="approved"가 되어야 한다(계획서의 '규칙 검사 + 사람 검수' 이중 게이트).
"""
import asyncio
import json
import random
from typing import Dict, List, Optional

import content_rules as R
from content_gen import generate_words
from llm_service import anthropic_client

_MODEL = "claude-sonnet-4-6"


async def build_word_bank(target: int = 60, max_syllable: int = 3,
                          avoid: Optional[List[str]] = None, max_rounds: int = 8,
                          concurrency: int = 5) -> List[Dict]:
    """Claude로 단어를 병렬 생성해 규칙 게이트를 통과한 target개를 모은다.

    한 라운드에서 concurrency개 배치를 동시에 호출한다(각 15단어). 동시 배치가
    같은 avoid를 보므로 일부 겹치지만 dict로 중복 제거되어 무해하다."""
    avoid = list(avoid or [])
    out: Dict[str, Dict] = {}
    for _ in range(max_rounds):
        if len(out) >= target:
            break
        tasks = [generate_words(n=15, max_syllable=max_syllable, avoid=avoid + list(out.keys()))
                 for _ in range(concurrency)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for cands in results:
            if isinstance(cands, Exception):
                continue  # LLM/파싱 실패는 스킵(호출부 폴백 철학)
            for w in cands:
                ok, item, _ = R.check_word(w, max_syllable=max_syllable)
                if ok and item["word"] not in out:
                    out[item["word"]] = item
    return list(out.values())[:target]


async def _filter_real_batch(cands: List[str]) -> List[str]:
    """후보 한 배치에서 실제 표준 한국어 단어만 남긴다(자모 치환 후보의 실재성 판정)."""
    listing = ", ".join(cands)
    system = (
        "너는 한국어 어휘 판정기다. 아래 후보 중 **실제로 존재하는 표준 한국어 단어**만 고른다.\n"
        "- 일반 명사·기본 어휘 위주. 사전에 없는 조합, 비표준어, 고유명사, 비속어는 버린다.\n"
        "- 후보에 있는 글자 그대로만 채택하고 변형하지 않는다. 하나도 없으면 빈 배열.\n"
        f"후보: {listing}\n"
        '반드시 JSON만 출력: {"items": ["실제단어", ...]}'
    )
    try:
        resp = await anthropic_client.messages.create(
            model=_MODEL, max_tokens=1024, temperature=0.0, system=system,
            messages=[{"role": "user", "content": "판정"}],
        )
        content = resp.content[0].text.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        got = {str(x).strip() for x in json.loads(content).get("items", [])}
        return [c for c in cands if c in got]  # LLM 환각 방지: 후보에 있던 것만
    except Exception:
        return []


async def filter_real_words(cands: List[str], batch: int = 40, concurrency: int = 6) -> List[str]:
    """자모 치환 후보들을 배치·병렬로 LLM에 물어 실재 단어만 반환한다."""
    cands = [c for c in dict.fromkeys(cands) if c]
    batches = [cands[i:i + batch] for i in range(0, len(cands), batch)]
    sem = asyncio.Semaphore(concurrency)

    async def run(b: List[str]) -> List[str]:
        async with sem:
            return await _filter_real_batch(b)

    results = await asyncio.gather(*[run(b) for b in batches])
    real: List[str] = []
    for r in results:
        real.extend(r)
    return list(dict.fromkeys(real))


async def _closure_sentence(answer: str, distractor: str) -> Optional[str]:
    """answer가 유일하게 자연스럽고 distractor를 넣으면 어색한 짧은 문장(___ 포함)."""
    system = (
        "너는 청각장애인 독화 훈련용 '문맥 추론' 문항 출제기다.\n"
        f"- 두 단어 '{answer}'와 '{distractor}'는 입모양이 비슷해 눈으로는 구별이 어렵다.\n"
        f"- 빈칸 자리에 '{answer}'를 넣으면 자연스럽고, '{distractor}'를 넣으면 "
        "말이 안 되는 짧은 한국어 문장을 만들어라. 즉 문맥만으로 답이 하나로 정해져야 한다.\n"
        f"- 빈칸은 정확히 '___'(밑줄 3개)로 표시하고, 그 자리에 '{answer}'가 들어간다.\n"
        "- 6~14자 내외 일상 구어체 한 문장. 너무 쉽거나 뻔하지 않게.\n"
        f'반드시 JSON만 출력: {{"display": "___를 ...", "hint": "짧은 힌트"}}'
    )
    try:
        resp = await anthropic_client.messages.create(
            model=_MODEL, max_tokens=200, temperature=0.9, system=system,
            messages=[{"role": "user", "content": f"시드 {random.randint(1000, 9999)}"}],
        )
        content = resp.content[0].text.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        data = json.loads(content)
        display = str(data.get("display", "")).strip()
        hint = str(data.get("hint", "")).strip()
        return display, hint
    except Exception:
        return None


async def build_closures(pairs: List[Dict], max_items: int = 40,
                         concurrency: int = 8) -> List[Dict]:
    """혼동쌍(same_looking=True)마다 문맥 문항을 병렬 생성하고 게이트로 재검증한다."""
    confusable = [p for p in pairs if p.get("same_looking")]
    random.shuffle(confusable)
    confusable = confusable[:max_items * 2]  # 게이트 탈락분 여유
    sem = asyncio.Semaphore(concurrency)

    async def one(p: Dict) -> Optional[Dict]:
        async with sem:
            made = await _closure_sentence(p["a"], p["b"])
        if not made:
            return None
        display, hint = made
        ok, item, _ = R.check_closure(display, p["a"], [p["a"], p["b"]])
        if not ok:
            return None
        item["hint"] = hint or "문맥에 어울리는 쪽을 고르세요."
        return item

    results = await asyncio.gather(*[one(p) for p in confusable])
    items = [r for r in results if r][:max_items]
    for i, it in enumerate(items, 1):
        it["id"] = f"g{i}"
    return items


async def generate_all(word_target: int = 60, closure_max: int = 30,
                       avoid: Optional[List[str]] = None,
                       seed_words: Optional[List[str]] = None) -> Dict:
    """
    단어 생성 → 동구형이음 파트너 확장 → 쌍 발굴 → 문맥 문항까지 한 번에.

    파트너 확장이 핵심이다. 무작위 단어끼리는 '같아 보이는 쌍'이 잘 안 생기므로,
    각 단어의 초성·종성을 같은 입모양 자음으로 치환한 후보를 만들고 LLM으로 실재
    단어만 걸러 풀에 더한다. 그 뒤 규칙으로 쌍을 발굴한다(관계는 규칙이 보증).
    """
    words = await build_word_bank(target=word_target, avoid=avoid)
    generated = [w["word"] for w in words]

    # seed = 갓 생성한 단어 + (있으면)기존 큐레이션 단어. 파트너 후보의 씨앗.
    seeds = list(dict.fromkeys(generated + list(seed_words or [])))
    cand_set = set()
    for w in seeds:
        cand_set.update(R.lookalike_candidates(w))
    cand_set.difference_update(seeds)
    partners = await filter_real_words(sorted(cand_set))

    pool = list(dict.fromkeys(seeds + partners))
    pairs = R.discover_pairs(pool)

    # 저장할 단어 목록: 생성 단어 + 신규 파트너(seed에 없던 것). 파트너는 대립상대가
    # 있으므로 tier 2(시각적으로 헷갈리는 단어)로 표시한다.
    known = {w["word"] for w in words}
    for p in partners:
        if p not in known and p not in (seed_words or []):
            words.append({"word": p, "tier": 2})
            known.add(p)

    closures = await build_closures(pairs, max_items=closure_max)
    return {
        "meta": {
            "status": "candidate",
            "rules_version": 1,
            "counts": {"words": len(words), "pairs": len(pairs), "closures": len(closures)},
        },
        "words": words,
        "pairs": pairs,
        "closures": closures,
    }
