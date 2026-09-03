#!/usr/bin/env python
"""
고도화 축 C — 독화 지각 자원(규칙 기반) 공개 export.

동구형이음 사전 + 독화 난이도 지수 + 최소대립/동구형 쌍을 하나의 JSON으로 내보낸다.
한국어 독화에는 이런 표준 자원이 거의 없으므로, 앱 밖 연구·교육에서도 쓸 수 있게
저장소에 공개한다. 지각공간 임베딩(데이터 기반)이 준비되면 이 규칙값을 보정한다.

  python scripts/export_perceptual.py            # 커리큘럼 단어로 자원 생성
  python scripts/export_perceptual.py --out <경로>
"""
import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.join(os.path.dirname(_HERE), "backend")
sys.path.insert(0, _BACKEND)

import perceptual as P  # noqa: E402
import curriculum as C  # noqa: E402

_DEFAULT_OUT = os.path.join(os.path.dirname(_HERE), "docs", "perceptual-resources.json")


def main(args):
    words = [w["word"] for w in C.WORD_BANK]
    res = P.build_standard_resources(words)
    out = args.out or _DEFAULT_OUT
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    c = res["meta"]["word_count"]
    n = len(res["lookalike_pairs"])
    print(f"단어 {c}개 · 동구형이음/최소대립 쌍 {n}개 → {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="LIPLAB 축 C 지각 자원 export")
    ap.add_argument("--out", help="출력 JSON 경로(기본: docs/perceptual-resources.json)")
    main(ap.parse_args())
