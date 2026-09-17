#!/usr/bin/env python
"""
고도화 축 G — 콘텐츠 사람 검수 CLI.

계획서의 '규칙 검사 + 사람 검수' 이중 게이트에서 **사람 검수**를 담당한다.
gen_content.py가 만든 candidates_*.json을 훑어 승인분만 approved.json으로 승격한다.
approved.json은 curriculum.py가 앱 기동 시 자동 병합해 서빙한다.

사용:
  python scripts/review_content.py                 # 최신 후보를 대화형으로 검토(항목별 y/N/q)
  python scripts/review_content.py --accept-tier 2 # 단어는 tier<=2만 자동승인, 쌍·문항은 일괄승인
  python scripts/review_content.py --file <경로>   # 특정 후보 파일 지정
"""
import argparse
import glob
import json
import os
import sys
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.join(os.path.dirname(_HERE), "backend")
_OUTDIR = os.path.join(_BACKEND, "data", "curriculum")
_APPROVED = os.path.join(_OUTDIR, "approved.json")


def _latest_candidates():
    files = sorted(glob.glob(os.path.join(_OUTDIR, "candidates_*.json")))
    return files[-1] if files else None


def _load(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _load_approved():
    return _load(_APPROVED, {"meta": {"status": "approved"}, "words": [], "pairs": [], "closures": []})


def _save_approved(appr):
    appr.setdefault("meta", {})["status"] = "approved"
    appr["meta"]["counts"] = {k: len(appr.get(k, [])) for k in ("words", "pairs", "closures")}
    appr["meta"]["reviewed_at"] = datetime.now().isoformat(timespec="seconds")
    os.makedirs(_OUTDIR, exist_ok=True)
    with open(_APPROVED, "w", encoding="utf-8") as f:
        json.dump(appr, f, ensure_ascii=False, indent=2)


def _ask(prompt: str) -> bool:
    ans = input(prompt).strip().lower()
    if ans == "q":
        raise KeyboardInterrupt
    return ans == "y"


def main(args):
    path = args.file or _latest_candidates()
    if not path:
        print("검토할 candidates 파일이 없습니다. 먼저 gen_content.py로 생성하세요.")
        return
    cand = _load(path, {})
    appr = _load_approved()
    seen_w = {w["word"] for w in appr["words"]}
    seen_p = {frozenset((p["a"], p["b"])) for p in appr["pairs"]}
    seen_c = {c["display"] for c in appr["closures"]}
    stats = {"words": 0, "pairs": 0, "closures": 0}
    auto = args.accept_tier is not None
    print(f"검토 대상: {os.path.basename(path)} — {cand.get('meta', {}).get('counts', {})}")
    if auto:
        print(f"자동 모드: 단어 tier<={args.accept_tier} 승인, 쌍·문항 일괄 승인\n")

    try:
        for w in cand.get("words", []):
            if w["word"] in seen_w:
                continue
            ok = (w.get("tier", 1) <= args.accept_tier) if auto \
                else _ask(f"[단어] '{w['word']}' (tier {w.get('tier', 1)}) 승인? [y/N/q] ")
            if ok:
                appr["words"].append(w)
                seen_w.add(w["word"])
                stats["words"] += 1
        for p in cand.get("pairs", []):
            k = frozenset((p["a"], p["b"]))
            if k in seen_p:
                continue
            ok = True if auto else _ask(f"[쌍] {p['a']}/{p['b']} ({p.get('note', '')}) 승인? [y/N/q] ")
            if ok:
                appr["pairs"].append(p)
                seen_p.add(k)
                stats["pairs"] += 1
        for c in cand.get("closures", []):
            if c["display"] in seen_c:
                continue
            ok = True if auto else _ask(f"[문항] {c['display']} (답={c['answer']} 보기={c['options']}) 승인? [y/N/q] ")
            if ok:
                c = dict(c, id=f"g{len(appr['closures']) + 1}")
                appr["closures"].append(c)
                seen_c.add(c["display"])
                stats["closures"] += 1
    except KeyboardInterrupt:
        print("\n검토 중단 — 지금까지 승인분만 저장합니다.")

    _save_approved(appr)
    print("\n승인 병합:", stats)
    print("현재 approved 총계:", appr["meta"]["counts"], "→", _APPROVED)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="LIPLAB 축 G 콘텐츠 검수기")
    ap.add_argument("--file", help="검토할 candidates 파일 경로(기본: 최신)")
    ap.add_argument("--accept-tier", type=int, help="이 tier 이하 단어를 자동 승인(쌍·문항 일괄)")
    main(ap.parse_args())
