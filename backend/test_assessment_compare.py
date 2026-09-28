"""배치검사 재검사 비교(/api/assessment/history의 극복 입모양, /api/assessment/progression의 자모별 오류 변화).

예전에는 저장된 상위 3개(입모양)·6개(자모)끼리 비교해, 순위만 밀리고 여전히 틀리는 입모양·자모가 '이제 안 틀리는
입모양'·'n→0'으로 나왔다. 이제 두 검사의 문항 기록(item_log)을 전부 다시 세어 비교한다. 화면용 상위 목록은 그대로다.
문항 기록이 없는 옛 검사가 끼면 극복·자모 변화를 비운다.

database 모듈이 import 시점에 DATABASE_URL을 읽으므로 임시 DB를 지정한 별도 프로세스에서 시나리오를 돌리고
결과(JSON)만 검사한다(test_form_version_pairing.py와 같은 방식).
"""
import json
import os
import subprocess
import sys
import tempfile

_FLOW = r'''
import asyncio, json, random
from collections import Counter
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
import main, database
import assessment as A
from scoring import viseme_confusions
from database import PlacementResult

def resp(items, wrong):
    return {it["id"]: (next(o for o in it["options"] if o != it["word"]) if it["id"] in wrong else it["word"])
            for it in items}

def full_vis(items, wrong):
    c = Counter()
    for it in items:
        if it["id"] in wrong:
            c.update(it["visemes"])
    return c

def full_pho(items, wrong):
    c = Counter()
    for it in items:
        if it["id"] in wrong:
            ch = next(o for o in it["options"] if o != it["word"])
            c.update(x["target"] for x in viseme_confusions(it["word"], ch) if x["viseme"] is not None)
    return c

out = {}
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "cmp@example.com", "username": "cmp1", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    fa = c.get("/api/assessment/placement", params={"form": "A"}, headers=h).json()["items"]
    fb = c.get("/api/assessment/placement", params={"form": "B"}, headers=h).json()["items"]
    ids = [it["id"] for it in fa]
    # 상위 3개끼리 비교하면 여전히 틀리는 입모양이 극복으로 나오는 두 검사를 고른다(감사 재현과 같은 설정)
    rng = random.Random(0)
    while True:
        w0, w1 = set(rng.sample(ids, 6)), set(rng.sample(ids, 6))
        s0, s1 = A.score_placement(fa, resp(fa, w0)), A.score_placement(fa, resp(fa, w1))
        stale = [v for v in set(s0["error_visemes"]) - set(s1["error_visemes"]) if full_vis(fa, w1)[v]]
        if stale:
            break
    for w in (w0, w1):
        c.post("/api/assessment/score", json={"items": fa, "responses": resp(fa, w), "form": "A"}, headers=h)
    hist = c.get("/api/assessment/history", headers=h).json()
    f0, f1 = full_vis(fa, w0), full_vis(fa, w1)
    out["history"] = {"stale_top3": sorted(stale), "resolved": hist["delta"]["resolved_visemes"],
                      "new": hist["delta"]["new_error_visemes"],
                      "expect_resolved": sorted(v for v in f0 if not f1[v]),
                      "expect_new": sorted(v for v in f1 if not f0[v]),
                      "latest_top3": hist["latest"]["error_visemes"], "stored_top3": s1["error_visemes"]}
    # 사후 B: 자모 변화는 첫 A와 B의 전체 개수, 두 폼 모두 묻는 자모만
    w2 = set(rng.sample([it["id"] for it in fb], 6))
    c.post("/api/assessment/score", json={"items": fb, "responses": resp(fb, w2), "form": "B"}, headers=h)
    prog = c.get("/api/assessment/progression", headers=h).json()
    pa, pb = full_pho(fa, w0), full_pho(fb, w2)
    in_a = {p for it in fa for p in A._word_phonemes(it["word"])}
    in_b = {p for it in fb for p in A._word_phonemes(it["word"])}
    out["progression"] = {"rows": prog["error_phoneme_change"], "order": prog["order"],
                          "expect": [{"phoneme": p, "before": pa[p], "after": pb[p], "delta": pb[p] - pa[p]}
                                     for p in sorted(set(pa) | set(pb)) if p in in_a and p in in_b]}

    # 문항 기록이 없는 옛 검사가 첫 검사면 극복·자모 변화를 비운다
    r = c.post("/api/auth/register", json={"email": "old@example.com", "username": "old1", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h2 = {"Authorization": f"Bearer {r.json()['access_token']}"}
    uid2 = c.get("/api/auth/me", headers=h2).json()["id"]

    async def add_old():
        async with database.AsyncSessionLocal() as db:
            db.add(PlacementResult(user_id=uid2, form="A", form_version="v2", total=24, correct=12, accuracy=0.5,
                                   ability=0.5, level=2, error_visemes=[6, 4, 7],
                                   error_phonemes=[{"phoneme": "ㄱ", "count": 3}], item_log=None,
                                   created_at=datetime.utcnow() - timedelta(days=5)))
            await db.commit()
    asyncio.run(add_old())
    c.post("/api/assessment/score", json={"items": fb, "responses": resp(fb, set()), "form": "B"}, headers=h2)
    out["old"] = {"delta": c.get("/api/assessment/history", headers=h2).json()["delta"],
                  "rows": c.get("/api/assessment/progression", headers=h2).json()["error_phoneme_change"]}
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


def test_retest_comparison_uses_full_item_log_counts():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1")
        env.pop("ANTHROPIC_API_KEY", None)
        p = subprocess.run([sys.executable, "-c", _FLOW], cwd=here, env=env, capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])
    h = r["history"]
    assert h["stale_top3"] and not set(h["stale_top3"]) & set(h["resolved"]), h
    assert h["resolved"] == h["expect_resolved"] and h["new"] == h["expect_new"], h
    assert h["latest_top3"] == h["stored_top3"], "화면용 상위 3개 저장값은 그대로다"
    pr = r["progression"]
    assert pr["order"] == "A→B" and pr["rows"] == pr["expect"], pr
    assert r["old"]["delta"]["resolved_visemes"] == [] and r["old"]["delta"]["new_error_visemes"] == [], r["old"]
    assert r["old"]["rows"] == [], r["old"]
