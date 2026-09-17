#!/usr/bin/env python
"""
문맥 추론(closure) 문항을 3지 이상으로 강화한다.

대량 생성된 closure가 모두 2지선다(정답+오답 1개)라 추측 확률이 50%였다. 문맥으로
판단하는 훈련이 성립하려면 '눈으로 구별 안 되는' 오답이 둘 이상이어야 한다. 규칙 엔진
(lookalike_candidates + 빈도)으로 정답과 시각적으로 혼동되는 실단어 오답을 결정론적으로
추가해, 강화된 check_closure(보기 3+·혼동 오답 2+)를 통과하도록 만든다. LLM 불필요.

  python scripts/upgrade_closures.py            # data/curriculum/approved.json 제자리 갱신
  python scripts/upgrade_closures.py --dry-run  # 미리보기만
"""
import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.join(os.path.dirname(_HERE), "backend")
sys.path.insert(0, _BACKEND)

import content_rules as cr  # noqa: E402

_APPROVED = os.path.join(_BACKEND, "data", "curriculum", "approved.json")


def _is_confusable(answer, other):
    return other != answer and cr._visually_confusable(answer, other)


def upgrade_closure(c, want_distractors=2):
    """정답과 혼동되는 실단어 오답을 채워 (정답 + 혼동오답 want_distractors개)로 만든다."""
    answer = (c.get("answer") or "").strip()
    opts = [str(o).strip() for o in c.get("options", []) if str(o).strip()]
    # 기존 보기 중 혼동 가능한 것 유지(빈도순)
    conf = sorted([o for o in opts if _is_confusable(answer, o)],
                  key=lambda w: -cr.word_zipf(w))
    # 후보 — 정답에서 파생한 혼동 실단어(빈도 높은 순)
    cands = sorted(
        [w for w in cr.lookalike_candidates(answer)
         if w != answer and w not in conf and cr.is_common_word(w)],
        key=lambda w: -cr.word_zipf(w))
    for w in cands:
        if len(conf) >= want_distractors:
            break
        conf.append(w)
    if len(conf) < want_distractors:
        return None  # 혼동 오답을 충분히 못 찾음 → 원본 유지
    new = dict(c)
    new["options"] = [answer] + conf[:want_distractors]
    ok, _, why = cr.check_closure(new["display"], answer, new["options"])
    return new if ok else None


def main(args):
    data = json.load(open(_APPROVED, encoding="utf-8"))
    closures = data.get("closures", [])
    upgraded, kept = 0, 0
    out = []
    for c in closures:
        new = upgrade_closure(c)
        if new:
            upgraded += 1
            out.append(new)
            if args.dry_run:
                print(f"  {c['answer']}: {c['options']} → {new['options']}")
        else:
            kept += 1
            out.append(c)
            if args.dry_run:
                print(f"  [유지] {c['answer']}: {c['options']} (강화 실패)")
    print(f"\n강화 {upgraded}개 · 유지 {kept}개 / 총 {len(closures)}개")
    if not args.dry_run:
        data["closures"] = out
        json.dump(data, open(_APPROVED, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"→ {_APPROVED}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="closure 문항 3지+ 강화")
    ap.add_argument("--dry-run", action="store_true", help="쓰지 않고 미리보기")
    main(ap.parse_args())
