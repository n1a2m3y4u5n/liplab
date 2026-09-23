#!/usr/bin/env python
"""
파일럿 자료 보관·파기(계획서 §4.7) — 보관 기한이 지난 참여자 자료를 파기하고 파기 대장에 남긴다.

보관 기간은 연구 계획(윤리 심의)에서 정한다. 스크립트에 기본값은 없다: 연구 종료일(--study-end)과 보관 일수
(--retain-days)를 매번 준다. 기본은 보고만 하고, --apply를 줘야 실제로 지운다. 기한 전에는 --apply를 거부한다.
동의를 철회한 참여자는 기한과 무관하게 --withdraw <가명>으로 바로 처리한다(가명은 /api/pilot/export의 pid).

처리 방식(--mode):
  unlink  파일럿에서만 뺀다(참여 코드·집단 삭제). 계정과 학습 기록은 일반 서비스 약관대로 남는다.
          연구용 가명 내보내기에 더는 나오지 않는다.
  delete  계정과 학습 기록 전부를 지운다(계정 삭제와 같은 범위). 연구 참여만을 위해 만든 계정에 쓴다.

  cd backend    # 앱과 같은 DATABASE_URL·LIPLAB_PILOT_SECRET(없으면 JWT_SECRET) 환경에서 실행한다(가명이 같아야 한다)
  python ../scripts/pilot_retention.py --study-end 2026-12-31 --retain-days 365                 # 대상과 행 수만 본다
  python ../scripts/pilot_retention.py --study-end 2026-12-31 --retain-days 365 --apply --mode delete
  python ../scripts/pilot_retention.py --withdraw 1a2b3c4d5e6f --apply --mode delete           # 동의 철회

배포 서버(Docker 이미지)에도 /app/scripts/pilot_retention.py로 들어간다. 서버에서는
  fly ssh console -C "python /app/scripts/pilot_retention.py --study-end … --retain-days …"
처럼 실행한다. 이미지 안에는 backend 폴더가 따로 없고 /app이 곧 backend라, 아래에서 둘 다 찾는다.
파기 대장: --ledger에 한 줄씩 덧붙인다. 기본은 /data가 있으면(배포 볼륨) /data/pilot_destruction_ledger.jsonl,
없으면 ./pilot_destruction_ledger.jsonl이다. 컨테이너의 다른 경로는 재시작 때 사라진다. 대장은 연구 기록과 함께 보관한다.
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import date, datetime, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
# 저장소에서는 <루트>/backend, 배포 이미지에서는 /app(= backend 내용) 자체가 모듈 위치다
sys.path.insert(0, os.path.join(_ROOT, "backend") if os.path.isdir(os.path.join(_ROOT, "backend")) else _ROOT)
_DEFAULT_LEDGER = ("/data/pilot_destruction_ledger.jsonl" if os.path.isdir("/data") and os.access("/data", os.W_OK)
                   else "pilot_destruction_ledger.jsonl")


def _parse(argv):
    ap = argparse.ArgumentParser(description="파일럿 자료 보관·파기(§4.7)")
    ap.add_argument("--study-end", type=date.fromisoformat, help="연구 종료일 YYYY-MM-DD")
    ap.add_argument("--retain-days", type=int, help="연구 종료 뒤 보관 일수(연구 계획에서 정한 값)")
    ap.add_argument("--withdraw", action="append", default=[], help="동의 철회한 참여자의 가명(pid), 여러 번 줄 수 있다")
    ap.add_argument("--cohort", default=None, help="이 집단만")
    ap.add_argument("--mode", choices=("unlink", "delete"), default=None)
    ap.add_argument("--apply", action="store_true", help="실제로 처리한다(없으면 보고만)")
    ap.add_argument("--ledger", default=_DEFAULT_LEDGER)
    ap.add_argument("--today", type=date.fromisoformat, default=None, help="오늘 날짜(시험용)")
    a = ap.parse_args(argv)
    if not a.withdraw and (a.study_end is None or a.retain_days is None):
        ap.error("--study-end와 --retain-days가 필요하다(동의 철회 처리는 --withdraw)")
    if a.apply and not a.mode:
        ap.error("--apply에는 --mode unlink|delete가 필요하다")
    return a


async def run(argv) -> dict:
    import pilot_data as PD
    from database import AsyncSessionLocal
    a = _parse(argv)
    today = a.today or date.today()
    reason = "withdrawal" if a.withdraw else "retention"
    due = None if a.withdraw else PD.due_date(a.study_end, a.retain_days)
    async with AsyncSessionLocal() as db:
        profs = await PD.participants(db, a.cohort)
        if a.withdraw:
            want = set(a.withdraw)
            profs = [p for p in profs if PD.pseudonym(p.user_id) in want]
            missing = sorted(want - {PD.pseudonym(p.user_id) for p in profs})
        else:
            missing = []
        rows = []
        for p in profs:
            rows.append({"pid": PD.pseudonym(p.user_id), "cohort": p.cohort, "rows": await PD.count_rows(db, p.user_id)})
        out = {"reason": reason, "today": today.isoformat(), "due": due.isoformat() if due else None,
               "cohort": a.cohort, "participants": rows, "missing_pids": missing, "applied": False}
        if not a.apply:
            return out
        if due and today < due:
            out["refused"] = f"보관 기한 전입니다(기한 {due.isoformat()}, {(due - today).days}일 남음)"
            return out
        removed = {}
        for p in profs:
            if a.mode == "delete":
                for t, n in (await PD.purge(db, p.user_id)).items():
                    removed[t] = removed.get(t, 0) + n
            else:
                PD.unlink(p)
                db.add(p)
        await db.commit()
    out.update(applied=True, mode=a.mode, removed=removed)
    entry = {"at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
             "reason": reason, "mode": a.mode, "study_end": a.study_end.isoformat() if a.study_end else None,
             "retain_days": a.retain_days, "due": out["due"], "cohort": a.cohort,
             "pids": [r["pid"] for r in rows], "rows_removed": removed}
    with open(a.ledger, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    out["ledger"] = os.path.abspath(a.ledger)
    return out


def main() -> int:
    out = asyncio.run(run(sys.argv[1:]))
    print(f"사유: {out['reason']}  기한: {out['due'] or '-'}  대상: {len(out['participants'])}명"
          + (f"  집단: {out['cohort']}" if out["cohort"] else ""))
    for r in out["participants"]:
        print(f"  {r['pid']}  {r['cohort'] or '-':<10} {sum(r['rows'].values())}행 {r['rows']}")
    if out["missing_pids"]:
        print("  찾지 못한 가명:", ", ".join(out["missing_pids"]))
    if out.get("refused"):
        print("처리하지 않음:", out["refused"])
        return 2
    if out["applied"]:
        print(f"처리 완료({out['mode']}): {out['removed'] or '파일럿 표시만 삭제'} → 대장 {out['ledger']}")
    else:
        print("보고만 했다. 처리하려면 --apply --mode unlink|delete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
