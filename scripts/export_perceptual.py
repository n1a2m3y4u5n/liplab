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
import assessment as A  # noqa: E402

_DEFAULT_OUT = os.path.join(os.path.dirname(_HERE), "docs", "perceptual-resources.json")

# 표준 평가셋 — seed 고정으로 완전히 재현되는 배치검사 벤치마크(축 C의 공개 3종 중 하나).
_EVAL_SEED = 20260903
_EVAL_N = 20


def build_eval_set(words):
    """난이도 스펙트럼에서 균등 표집한 고정 배치검사 문항(동구형 오답 포함).
    한국어 독화에는 공개 표준 평가셋이 없으므로, 재현 가능한 벤치마크로 함께 배포한다."""
    items = A.build_placement_items(words, n=_EVAL_N, seed=_EVAL_SEED)
    return {
        "description": ("난이도 오름차순으로 균등 표집한 배치검사 문항. 각 문항은 정답 단어와 "
                        "'같아 보이는' 오답(동구형/최소대립)을 함께 담는다. seed 고정으로 재현 가능."),
        "seed": _EVAL_SEED,
        "count": len(items),
        "items": items,
    }


def main(args):
    words = [w["word"] for w in C.WORD_BANK]
    res = P.build_standard_resources(words)
    # 표준 평가셋을 마지막에 추가(build_placement_items가 seed를 고정하므로 다른 자원 생성 뒤에)
    res["standard_eval_set"] = build_eval_set(words)
    out = args.out or _DEFAULT_OUT
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    c = res["meta"]["word_count"]
    n = len(res["lookalike_pairs"])
    ev = res["standard_eval_set"]["count"]
    print(f"단어 {c}개 · 동구형이음/최소대립 쌍 {n}개 · 표준 평가셋 {ev}문항 → {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="LIPLAB 축 C 지각 자원 export")
    ap.add_argument("--out", help="출력 JSON 경로(기본: docs/perceptual-resources.json)")
    main(ap.parse_args())
