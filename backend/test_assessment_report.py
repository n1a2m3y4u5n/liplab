"""교사·언어재활사용 결과지 API(I-9) 테스트 — 검사 이력·사전·사후·오류 프로파일·학습량·해석 주의가 한 번에 오는가.

test_pilot.py와 같은 방식: 임시 DB를 지정한 별도 프로세스에서 시나리오를 돌리고 결과(JSON)만 검사한다.
"""
import json
import os
import subprocess
import sys
import tempfile

_SCENARIO = r'''
import asyncio, json
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
import main
out = {}
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "t1@example.com", "username": "학생한명", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    out["empty"] = c.get("/api/assessment/report", headers=h).json()
    uid = c.get("/api/auth/me", headers=h).json()["id"]

    # 사전 검사를 UTC 20시에 둔다 — 한국(−540분) 날짜로는 다음 날이어야 한다
    t0 = (datetime.utcnow() - timedelta(days=14)).replace(hour=20, minute=0, second=0, microsecond=0)
    out["t0_utc_day"] = t0.date().isoformat()
    out["t0_kst_day"] = (t0 + timedelta(hours=9)).date().isoformat()

    async def seed():
        from database import AsyncSessionLocal, PlacementResult
        async with AsyncSessionLocal() as db:
            db.add(PlacementResult(user_id=uid, form="A", form_version="v1", total=24, correct=12, accuracy=0.5,
                                   ability=-0.2, level=2, error_visemes=[1, 7],
                                   error_phonemes=[{"phoneme": "ㅁ", "count": 3}, {"phoneme": "ㄱ", "count": 1}],
                                   created_at=t0))
            db.add(PlacementResult(user_id=uid, form="B", form_version="v1", total=24, correct=18, accuracy=0.75,
                                   ability=0.6, level=3, error_visemes=[7],
                                   error_phonemes=[{"phoneme": "ㄱ", "count": 2}, {"phoneme": "ㅁ", "count": 1}],
                                   created_at=t0 + timedelta(days=13)))
            await db.commit()
    asyncio.run(seed())
    item = main._training_closures()[0]
    c.post("/api/curriculum/closure-answer", json={"item_id": item["id"], "chosen": item["answer"]}, headers=h)
    out["report"] = c.get("/api/assessment/report", headers=h).json()
    out["report_utc"] = c.get("/api/assessment/report", params={"tz_offset_min": 0}, headers=h).json()
    out["noauth"] = c.get("/api/assessment/report").status_code
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


def _run():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1")
        p = subprocess.run([sys.executable, "-c", _SCENARIO], cwd=here, env=env,
                           capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    return json.loads(line[len("RESULT "):])


def test_assessment_report_for_teacher():
    r = _run()
    empty = r["empty"]
    assert empty["tests"] == [] and empty["progression"]["available"] is False
    rep = r["report"]
    assert rep["learner"]["name"] == "학생한명"
    assert [t["form"] for t in rep["tests"]] == ["A", "B"]
    assert rep["progression"]["available"] is True and rep["progression"]["homogeneous"] is True
    assert abs(rep["progression"]["accuracy_delta"] - 0.25) < 1e-9
    # 최근 검사(B)의 오류 프로파일 — 입모양 이름과 자모가 많은 순으로
    assert [v["viseme_id"] for v in rep["error_profile"]["visemes"]] == [7]
    assert rep["error_profile"]["visemes"][0]["name"]
    assert rep["error_profile"]["phonemes"][0] == {"phoneme": "ㄱ", "count": 2}
    stage3 = [s for s in rep["activity"]["trials_by_stage"] if s["stage"] == 3]
    assert stage3 and stage3[0]["n"] == 1 and stage3[0]["correct"] == 1
    assert rep["activity"]["active_days"] >= 2
    assert any("규준" in n for n in rep["notes"]) and any("모의실험" in n for n in rep["notes"])
    # 날짜는 현지 기준(기본 한국) — UTC 20시 검사는 한국 날짜로 다음 날
    assert rep["tests"][0]["date"] == r["t0_kst_day"]
    assert r["report_utc"]["tests"][0]["date"] == r["t0_utc_day"]
    assert rep["issued_on"] and len(rep["issued_on"]) == 10
    assert r["noauth"] == 401
