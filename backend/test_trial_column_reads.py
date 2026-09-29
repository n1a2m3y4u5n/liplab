"""혼동행렬(/api/curriculum/confusion-matrix)·학습 효과 리포트(/api/eval/summary)가 필요한 열만 읽어도 응답이 같은지.

PERF-3: 두 엔드포인트는 시행(TrialAttempt)·문장(Progress) 전체를 ORM 객체로 읽었다. 이제 전체 수는 count, 정오는
(item_type, correct), confusions는 오답 행에서만, 문장은 (difficulty_level, score)만 읽는다. correct가 NULL인 행은
예전 파이썬 'not a.correct'처럼 오답으로 센다(SQL 'correct is false'만 쓰면 빠진다).

기준은 고치기 전 계산을 ORM 전체 행으로 그대로 옮긴 함수다. 임시 DB를 지정한 별도 프로세스에서 돌린다.
"""
import json
import os
import subprocess
import sys
import tempfile

_SCENARIO = r'''
import json, random
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import select, update
import main, database
from database import TrialAttempt, Progress

def cf(t, r, same):
    return {"position": "initial", "target": t, "read": r, "viseme": 1, "same_viseme": same}

async def seed(uid, other):
    rnd = random.Random(3)
    base = datetime(2026, 9, 1)
    async with database.AsyncSessionLocal() as db:
        for i in range(300):
            correct = rnd.choice([True, True, False, None])     # NULL 행 포함
            wrong = not correct
            conf = [cf(rnd.choice("ㄱㄴㅁ"), rnd.choice("ㅂㅍㄷ"), rnd.random() < 0.4)
                    for _ in range(rnd.randint(1, 2))] if wrong else []
            # 시각을 id 순서와 다르게 섞어 created_at 정렬이 지켜지는지 본다
            db.add(TrialAttempt(user_id=uid, stage=1, item_type=rnd.choice(["viseme", "word", "closure"]),
                                target="null" if correct is None else "x", chosen="y", correct=correct, confusions=conf,
                                created_at=base + timedelta(minutes=rnd.randint(0, 5000))))
        db.add(TrialAttempt(user_id=other, stage=1, item_type="word", target="x", chosen="y", correct=False,
                            confusions=[cf("ㅅ", "ㅈ", True)]))
        for i in range(40):
            db.add(Progress(user_id=uid, scenario_id="s", sentence="문장", user_answer="답", score=rnd.randint(0, 100),
                            difficulty_level=rnd.choice([1, 2, 3, None]) or 1, situation="카페",
                            created_at=base + timedelta(minutes=rnd.randint(0, 5000))))
        await db.commit()
        # ORM은 None을 넣으면 열 기본값(False)을 쓰므로 NULL은 따로 넣는다
        await db.execute(update(TrialAttempt).where(TrialAttempt.target == "null").values(correct=None))
        await db.commit()

async def reference(uid):
    """고치기 전 두 엔드포인트의 계산(ORM 전체 행)."""
    import eval_metrics as _em
    async with database.AsyncSessionLocal() as db:
        # 예전 쿼리는 ORDER BY가 없어 (user_id, created_at) 인덱스 순서로 읽혔다. 같은 횟수의 혼동 순서가 이 순서를 따른다
        rows = (await db.execute(select(TrialAttempt).where(TrialAttempt.user_id == uid)
                                 .order_by(TrialAttempt.created_at.asc(), TrialAttempt.id.asc()))).scalars().all()
        jamo = {}; same_cnt = tot_cf = 0
        n_wrong = sum(1 for a in rows if not a.correct)
        for a in rows:
            for c in (a.confusions or []):
                e = jamo.setdefault((c.get("target"), c.get("read")), {"count": 0, "same_viseme": 0})
                e["count"] += 1; tot_cf += 1
                if c.get("same_viseme"):
                    e["same_viseme"] += 1; same_cnt += 1
        cm = {"trials": len(rows), "wrong": n_wrong, "confusion_count": tot_cf,
              "same_viseme_ratio": round(same_cnt / tot_cf, 3) if tot_cf else 0.0,
              "jamo_confusions": sorted([{"target": t, "read": rd, "count": v["count"], "same_viseme": v["same_viseme"]}
                                         for (t, rd), v in jamo.items()], key=lambda x: -x["count"])[:30]}
        tr = (await db.execute(select(TrialAttempt).where(TrialAttempt.user_id == uid)
                               .order_by(TrialAttempt.created_at.asc(), TrialAttempt.id.asc()))).scalars().all()
        seq = [(a.item_type, bool(a.correct)) for a in tr]
        by = []
        for it in ("viseme", "word", "closure"):
            seg = [a for a in tr if a.item_type == it]
            if seg:
                by.append({"item_type": it, "n": len(seg), "accuracy": round(sum(1 for a in seg if a.correct) / len(seg) * 100, 1)})
        s2 = t2 = 0
        for a in tr:
            for c in (a.confusions or []):
                t2 += 1; s2 += 1 if c.get("same_viseme") else 0
        prog = (await db.execute(select(Progress).where(Progress.user_id == uid)
                                 .order_by(Progress.created_at.asc(), Progress.id.asc()))).scalars().all()
        ev = {"overview": {"total_trials": len(tr),
                           "trial_accuracy": round(sum(1 for a in tr if a.correct) / len(tr) * 100, 1) if tr else None,
                           "total_sentences": len(prog),
                           "sentence_avg_score": round(sum(p.score or 0 for p in prog) / len(prog), 1) if prog else None},
              "learning_curve": _em.type_adjusted_curve(seq), "baseline_vs_recent": _em.within_type_change(seq),
              "by_item_type": by, "same_viseme_ratio": round(s2 / t2, 3) if t2 else None,
              "sentence_trend": _em.group_adjusted_curve([(p.difficulty_level or 0, p.score or 0.0) for p in prog],
                                                         lo=0.0, hi=100.0, ndigits=1)}
        n_null = sum(1 for a in rows if a.correct is None)
        # 속도 기록·짝 탐색 문항이 없는 자료라 걸러지는 시행이 없다(9/29 필터, docs/eval-metrics.md 7절)
        if ev["baseline_vs_recent"] is not None:
            ev["baseline_vs_recent"]["excluded"] = {"speed": 0, "probe": 0}
    return cm, ev, n_null

out = {}
with TestClient(main.app) as c:
    tok = []
    for i in range(2):
        r = c.post("/api/auth/register", json={"email": f"cm{i}@example.com", "username": f"혼동{i}", "password": "pw-123456",
                                               "agree_terms": True, "age_confirmed": True})
        tok.append(r.json()["access_token"])
    h = {"Authorization": "Bearer " + tok[0]}
    uid = c.get("/api/auth/me", headers=h).json()["id"]
    other = c.get("/api/auth/me", headers={"Authorization": "Bearer " + tok[1]}).json()["id"]
    c.portal.call(seed, uid, other)
    cm = c.get("/api/curriculum/confusion-matrix", headers=h).json()
    ev = c.get("/api/eval/summary", headers=h).json()
    ref_cm, ref_ev, n_null = c.portal.call(reference, uid)
    for b in ev["by_item_type"]:
        b.pop("label", None)
    out = {"cm": cm, "ref_cm": ref_cm, "ev": {k: ev[k] for k in ref_ev if k != "overview"},
           "ev_overview": ev["overview"], "ref_ev": ref_ev, "n_null": n_null}
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


def test_column_reads_give_same_confusion_matrix_and_summary():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1")
        env.pop("ANTHROPIC_API_KEY", None)
        p = subprocess.run([sys.executable, "-c", _SCENARIO], cwd=here, env=env,
                           capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])
    assert r["n_null"] > 0                                  # correct가 NULL인 행이 실제로 있다
    assert r["cm"] == r["ref_cm"]                           # NULL 행도 오답 수·혼동에 들어간다
    assert r["cm"]["trials"] == 300                         # 다른 사용자의 시행은 세지 않는다
    ref = r["ref_ev"]
    assert r["ev_overview"] == ref["overview"]
    for k in ("learning_curve", "baseline_vs_recent", "by_item_type", "same_viseme_ratio", "sentence_trend"):
        assert r["ev"][k] == ref[k], k
