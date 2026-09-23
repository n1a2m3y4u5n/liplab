#!/usr/bin/env python
"""
고도화 축 G(4.4-4) — 두 판본의 승인 콘텐츠(approved.json)를 합치고 규칙 게이트를 다시 건다.

브랜치마다 approved.json이 따로 자라면, 한쪽에서 게이트를 강화한 뒤(예: 문맥 문항 3지 이상) 다른 쪽의 옛 항목이
병합으로 되살아날 수 있다. 이 스크립트는 합집합을 만든 뒤 모든 항목을 content_rules로 다시 검사하고,
떨어진 항목과 사유를 보고한다. 같은 항목(단어·순서 무관 쌍·문항 display|answer)은 첫 번째 파일 쪽을 쓰되,
그쪽이 게이트에서 떨어지고 두 번째 쪽이 통과하면 두 번째 쪽을 쓴다. 검수 기록(meta.review_log)은 둘을 이어 붙인다.

  python scripts/merge_approved.py ours.json theirs.json --out backend/data/curriculum/approved.json
  python scripts/merge_approved.py ours.json theirs.json --dry-run      # 보고만
  (git에서 다른 브랜치 판본 꺼내기: git show origin/<브랜치>:backend/data/curriculum/approved.json > theirs.json)
"""
import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "backend"))

import content_review as CR  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="approved.json 두 판본 병합 + 규칙 게이트 재검사")
    ap.add_argument("first", help="우선 판본(보통 지금 브랜치)")
    ap.add_argument("second", help="합칠 판본")
    ap.add_argument("--out", help="합친 결과 경로(생략하면 --dry-run과 같다)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report", help="보고서 JSON 경로(선택)")
    a = ap.parse_args()
    first = json.load(open(a.first, encoding="utf-8"))
    second = json.load(open(a.second, encoding="utf-8"))
    merged, report = CR.merge(first, second)
    print("유지:", report["kept"], " 중복:", report["duplicates"], " 게이트 탈락:", len(report["dropped"]))
    for d in report["dropped"][:30]:
        print(f"  - [{d['kind']}] {d['key']} ({d['from']}): {d['reason']}")
    if len(report["dropped"]) > 30:
        print(f"  … 외 {len(report['dropped']) - 30}건(--report로 전부 저장)")
    if a.report:
        json.dump(report, open(a.report, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if a.out and not a.dry_run:
        json.dump(merged, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("저장:", a.out, merged["meta"]["counts"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
