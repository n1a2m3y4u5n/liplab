"""
콘텐츠 사람검수(축 G '이중 게이트'의 사람 단계) — 인앱 운영자 검수용 순수 로직.

파이프라인: LLM 대량생성 → 규칙 게이트(content_rules) → **사람 검수** → approved.json → 커리큘럼.
지금까지 사람 검수는 CLI(scripts/review_content.py)뿐이었다. 이 모듈은 후보(candidates_*.json)
중 아직 승인/반려되지 않은 '대기' 항목을 뽑고, 운영자의 승인/반려를 approved.json·rejected.json에
반영한다(중복 없이). DB 비의존 순수 파일 연산 → 결정론적 테스트 가능.

항목 종류(kind): word {word,tier} · pair {a,b,...} · closure {display,answer,options,...}
"""
import glob
import json
import os
from typing import Dict, List, Tuple

_DIR = os.path.join(os.path.dirname(__file__), "data", "curriculum")
_APPROVED = os.path.join(_DIR, "approved.json")
_REJECTED = os.path.join(_DIR, "rejected.json")
_EMPTY = {"words": [], "pairs": [], "closures": []}


def _load(path: str) -> Dict:
    try:
        d = json.load(open(path, encoding="utf-8"))
        for k in ("words", "pairs", "closures"):
            d.setdefault(k, [])
        return d
    except Exception:
        return {"meta": {}, **{k: [] for k in _EMPTY}}


def _latest_candidates() -> Dict:
    files = sorted(glob.glob(os.path.join(_DIR, "candidates_*.json")))
    return _load(files[-1]) if files else {"meta": {}, **{k: [] for k in _EMPTY}}


def _key(kind: str, item: Dict) -> str:
    """중복·매칭용 안정 키. pair는 순서 무관, closure는 내용(display|answer).

    closure를 id로 매칭하면 배치마다 재사용된 id(g1…) 때문에 새 문항이 이미 승인된
    것으로 오인되어 검수 대기 목록에 나타나지 않는다.
    """
    if kind == "words":
        return str(item.get("word", "")).strip()
    if kind == "pairs":
        return "|".join(sorted([str(item.get("a", "")).strip(), str(item.get("b", "")).strip()]))
    if kind == "closures":
        return f"{str(item.get('display', '')).strip()}|{str(item.get('answer', '')).strip()}"
    return json.dumps(item, ensure_ascii=False, sort_keys=True)


def _keyset(items: List[Dict], kind: str) -> set:
    return {_key(kind, it) for it in items}


def pending() -> Dict:
    """승인·반려되지 않은 대기 후보 + 요약. 종류별 목록·건수."""
    cand = _latest_candidates()
    appr = _load(_APPROVED)
    rej = _load(_REJECTED)
    out: Dict[str, List[Dict]] = {}
    counts = {}
    for kind in ("words", "pairs", "closures"):
        done = _keyset(appr.get(kind, []), kind) | _keyset(rej.get(kind, []), kind)
        p = [it for it in cand.get(kind, []) if _key(kind, it) not in done]
        out[kind] = p
        counts[kind] = {"pending": len(p), "approved": len(appr.get(kind, [])),
                        "rejected": len(rej.get(kind, [])), "candidates": len(cand.get(kind, []))}
    return {"pending": out, "counts": counts}


def review(kind: str, item: Dict, decision: str) -> Dict:
    """운영자 결정 반영. approve→approved.json, reject→rejected.json (중복 없이 추가)."""
    if kind not in ("words", "pairs", "closures"):
        raise ValueError("unknown kind")
    if decision not in ("approve", "reject"):
        raise ValueError("decision must be approve|reject")
    target_path = _APPROVED if decision == "approve" else _REJECTED
    store = _load(target_path)
    existing = _keyset(store.get(kind, []), kind)
    k = _key(kind, item)
    added = False
    if k and k not in existing:
        store.setdefault(kind, []).append(item)
        store.setdefault("meta", {})["reviewed"] = True
        json.dump(store, open(target_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        added = True
    return {"ok": True, "kind": kind, "key": k, "decision": decision, "added": added}
