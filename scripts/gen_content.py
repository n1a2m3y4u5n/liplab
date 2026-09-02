#!/usr/bin/env python
"""
고도화 축 G — 콘텐츠 대량 생성 CLI.

Claude로 단어를 생성하고, 동구형이음 파트너로 확장한 뒤, 규칙으로 쌍을 발굴하고
문맥 문항을 만들어 backend/data/curriculum/ 아래에 저장한다.

사용:
  python scripts/gen_content.py --words 60 --closures 30
      → candidates_<시각>.json 생성(사람 검수 대기 상태 status="candidate").
  python scripts/gen_content.py --words 60 --auto-approve
      → 검수를 생략하고 approved.json에도 병합(데모/개발용). 실제 배포용은 검수 후 승인.

approved.json이 있으면 curriculum.py가 앱 기동 시 자동으로 병합해 서빙한다(비파괴).
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.join(os.path.dirname(_HERE), "backend")
sys.path.insert(0, _BACKEND)

import content_pipeline as P  # noqa: E402
import curriculum as C  # noqa: E402

_OUTDIR = os.path.join(_BACKEND, "data", "curriculum")


def _merge_approved(existing: dict, new: dict) -> dict:
    """생성물을 기존 approved에 중복 없이 누적한다(단어·쌍·문항)."""
    out = {"meta": {"status": "approved", "rules_version": new["meta"].get("rules_version", 1)},
           "words": list(existing.get("words", [])),
           "pairs": list(existing.get("pairs", [])),
           "closures": list(existing.get("closures", []))}
    seen_w = {w["word"] for w in out["words"]}
    for w in new.get("words", []):
        if w["word"] not in seen_w:
            out["words"].append(w)
            seen_w.add(w["word"])
    seen_p = {frozenset((p["a"], p["b"])) for p in out["pairs"]}
    for p in new.get("pairs", []):
        k = frozenset((p["a"], p["b"]))
        if k not in seen_p:
            out["pairs"].append(p)
            seen_p.add(k)
    base = len(out["closures"])
    seen_disp = {c["display"] for c in out["closures"]}
    for c in new.get("closures", []):
        if c["display"] not in seen_disp:
            c = dict(c, id=f"g{base + 1}")
            out["closures"].append(c)
            seen_disp.add(c["display"])
            base += 1
    out["meta"]["counts"] = {k: len(out[k]) for k in ("words", "pairs", "closures")}
    return out


async def run(args) -> None:
    os.makedirs(_OUTDIR, exist_ok=True)
    seeds = None if args.no_seed else [w["word"] for w in C.WORD_BANK]
    res = await P.generate_all(word_target=args.words, closure_max=args.closures, seed_words=seeds)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    cand_path = os.path.join(_OUTDIR, f"candidates_{ts}.json")
    with open(cand_path, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print("생성 완료:", res["meta"]["counts"])
    print("후보 저장:", cand_path)

    if args.auto_approve:
        appr_path = os.path.join(_OUTDIR, "approved.json")
        try:
            with open(appr_path, encoding="utf-8") as f:
                existing = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            existing = {}
        merged = _merge_approved(existing, res)
        with open(appr_path, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        print("승인 병합(검수 생략):", appr_path, merged["meta"]["counts"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="LIPLAB 축 G 콘텐츠 생성기")
    ap.add_argument("--words", type=int, default=60, help="생성 목표 단어 수")
    ap.add_argument("--closures", type=int, default=30, help="생성할 문맥 문항 수")
    ap.add_argument("--no-seed", action="store_true", help="기존 큐레이션 단어를 씨앗으로 쓰지 않음")
    ap.add_argument("--auto-approve", action="store_true", help="검수 생략하고 approved.json에 병합(개발용)")
    asyncio.run(run(ap.parse_args()))
