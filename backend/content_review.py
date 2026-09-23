"""
콘텐츠 사람검수(축 G '이중 게이트'의 사람 단계) — 인앱 운영자 검수용 순수 로직.

파이프라인: LLM 대량생성 → 규칙 게이트(content_rules) → **사람 검수** → approved.json → 커리큘럼.
지금까지 사람 검수는 CLI(scripts/review_content.py)뿐이었다. 이 모듈은 후보(candidates_*.json)
중 아직 승인/반려되지 않은 '대기' 항목을 뽑고, 운영자의 승인/반려를 approved.json·rejected.json에
반영한다(중복 없이). DB 비의존 순수 파일 연산 → 결정론적 테스트 가능.

항목 종류(kind): word {word,tier} · pair {a,b,...} · closure {display,answer,options,...}

결정마다 meta.review_log에 누가(운영자 가명 태그)·언제·무엇을 승인/반려했는지 남긴다(계획서 4.4-4).
두 판본(브랜치별 approved.json)을 합칠 때는 merge()가 합집합을 만든 뒤 규칙 게이트를 다시 건다.
"""
import glob
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

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


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def closure_id(item: Dict) -> str:
    """문맥 문항의 안정 id(content_pipeline.closure_id와 같은 식): 'g' + sha1(display|answer) 앞 8자리.
    후보 배치마다 g1, g2…가 다시 쓰이므로 승인할 때 내용 기반 id로 바꿔 저장한다."""
    raw = f"{item.get('display', '')}|{item.get('answer', '')}"
    return "g" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]


def review(kind: str, item: Dict, decision: str, reviewer: str = "unknown", now: Optional[str] = None) -> Dict:
    """운영자 결정 반영. approve→approved.json, reject→rejected.json (중복 없이 추가).
    reviewer는 이메일이 아닌 가명 태그다(저장소에 들어가는 파일이라 개인정보를 남기지 않는다)."""
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
        if kind == "closures":
            item = dict(item, id=closure_id(item))
        store.setdefault(kind, []).append(item)
        meta = store.setdefault("meta", {})
        meta["reviewed"] = True
        meta.setdefault("review_log", []).append(
            {"kind": kind, "key": k, "decision": decision, "by": reviewer, "at": now or _utcnow()})
        json.dump(store, open(target_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        added = True
    return {"ok": True, "kind": kind, "key": k, "decision": decision, "added": added}


def _gate(kind: str, item: Dict) -> Tuple[bool, str]:
    """규칙 게이트 재검사(content_rules). 항목 모양은 그대로 두고 통과 여부와 사유만 본다."""
    import content_rules as R
    if kind == "words":
        ok, _, why = R.check_word(str(item.get("word", "")))
    elif kind == "pairs":
        ok, _, why = R.check_lookalike_pair(str(item.get("a", "")), str(item.get("b", "")))
    else:
        ok, _, why = R.check_closure(item.get("display", ""), item.get("answer", ""), item.get("options") or [])
    return ok, why


def merge(first: Dict, second: Dict, now: Optional[str] = None) -> Tuple[Dict, Dict]:
    """두 판본의 approved를 합친다(4.4-4). 같은 키는 first 쪽을 쓰고, 합친 뒤 모든 항목에 규칙 게이트를
    다시 건다 — 한쪽 판본에서 게이트가 강화된 뒤(예: 문맥 문항 3지 이상) 다른 판본의 옛 항목이 그대로
    섞여 들어오지 않게 한다. 문맥 문항 id는 내용 기반으로 맞춘다. 반환: (합친 판본, 보고서)."""
    out = {"meta": {}, "words": [], "pairs": [], "closures": []}
    report = {"kept": {}, "dropped": [], "duplicates": {}}
    for kind in ("words", "pairs", "closures"):
        kept, dropped, dup = set(), {}, 0
        for src, store in (("first", first), ("second", second)):
            for it in store.get(kind, []) or []:
                k = _key(kind, it)
                if not k:
                    continue
                if k in kept:
                    dup += 1
                    continue
                ok, why = _gate(kind, it)
                if not ok:
                    dropped.setdefault(k, {"kind": kind, "key": k, "from": src, "reason": why})
                    continue
                dropped.pop(k, None)   # 다른 판본의 같은 항목(예: 3지로 고친 문항)이 통과하면 그쪽을 쓴다
                kept.add(k)
                if kind == "closures":
                    it = dict(it, id=closure_id(it))
                out[kind].append(it)
        report["dropped"].extend(dropped.values())
        report["kept"][kind] = len(out[kind])
        report["duplicates"][kind] = dup
    log = list((first.get("meta") or {}).get("review_log", [])) + list((second.get("meta") or {}).get("review_log", []))
    log.append({"kind": "*", "key": "*", "decision": "merge", "by": "merge_approved",
                "at": now or _utcnow(), "dropped": len(report["dropped"])})
    out["meta"] = {"status": "approved", "rules_version": max((first.get("meta") or {}).get("rules_version", 1),
                                                              (second.get("meta") or {}).get("rules_version", 1)),
                   "counts": {k: len(out[k]) for k in ("words", "pairs", "closures")},
                   "reviewed": True, "review_log": log}
    return out, report
