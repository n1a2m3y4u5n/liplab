#!/usr/bin/env python
"""
측정 기록 보고(10/6): FSRS 그림자 모드(C11), 숙달 지연 탐침(C16), 지연 유지 검사(C7), 레슨별 정신적 노력(C14)을 한 번에 요약한다.
보고만 한다. 간격 교체·숙달 규칙 재검토·노력 상한 규칙은 결과를 보고 사람이 결정한다(docs/master-plan-2026-10.md 트랙 C).

  cd backend    # 앱과 같은 DATABASE_URL 환경에서 실행한다
  python ../scripts/measurement_report.py                 # 모든 학습자
  python ../scripts/measurement_report.py --cohort A      # 이 파일럿 집단만
  python ../scripts/measurement_report.py --out 결과.json

공용 데모 계정은 여러 방문자의 기록이 섞여 있어 뺀다.
"""
import argparse
import asyncio
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "backend") if os.path.isdir(os.path.join(_ROOT, "backend")) else _ROOT)


async def collect(cohort=None) -> dict:
    from sqlalchemy import select
    import database as D
    import fsrs_shadow as fs
    import mastery_probe as mp
    import mental_effort as me
    import retention as ret

    await D.init_db()
    async with D.AsyncSessionLocal() as db:
        demo = "demo@liplab.app"   # main._DEMO_EMAIL과 같다(main을 불러오지 않으려고 값을 옮겨 적음)
        users = (await db.execute(select(D.User.id, D.User.email))).all()
        keep = {u for u, e in users if (e or "").lower() != demo}
        if cohort:
            keep &= set((await db.execute(select(D.LearningProfile.user_id).where(
                D.LearningProfile.cohort == cohort))).scalars().all())

        logs = (await db.execute(select(D.ReviewLog))).scalars().all()
        review_rows = [{"id": r.id, "user_id": r.user_id, "t": r.created_at.isoformat() if r.created_at else "",
                        "passed": r.passed, "p_fsrs": r.p_fsrs, "p_sm2": r.p_sm2, "guess": r.guess}
                       for r in logs if r.user_id in keep]
        probes = (await db.execute(select(D.MasteryProbe))).scalars().all()
        probe_rows = [{"user_id": p.user_id, "stage": p.stage, "wave": p.wave, "correct": p.correct}
                      for p in probes if p.user_id in keep]
        efforts = (await db.execute(select(D.LessonEffort))).scalars().all()
        effort_rows = [{"stage": e.stage, "lesson_kind": e.lesson_kind, "response": e.response, "rating": e.rating}
                       for e in efforts if e.user_id in keep]
        rets = (await db.execute(select(D.RetentionResult))).scalars().all()
        posts = {p.id: p for p in (await db.execute(select(D.PlacementResult).where(
            D.PlacementResult.id.in_([r.post_result_id for r in rets if r.post_result_id])))).scalars().all()}
        pairs = [{"post_accuracy": posts[r.post_result_id].accuracy if r.post_result_id in posts else None,
                  "retention_accuracy": r.accuracy, "days_after_post": r.days_after_post}
                 for r in rets if r.user_id in keep]
    await D.close_db()
    return {"learners": len(keep), "fsrs_shadow": fs.compare(review_rows), "mastery_probes": mp.probe_report(probe_rows),
            "mental_effort": me.report(effort_rows), "retention": ret.summary(pairs)}


def main(argv=None):
    ap = argparse.ArgumentParser(description="측정 기록 보고(C7·C11·C14·C16)")
    ap.add_argument("--cohort", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    rep = asyncio.run(collect(a.cohort))
    text = json.dumps(rep, ensure_ascii=False, indent=2, default=str)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text)
    print(text)


if __name__ == "__main__":
    main()
