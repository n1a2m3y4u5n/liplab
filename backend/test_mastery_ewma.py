"""1·2단계 숙달 점수: 편향 보정 지수 이동 평균(docs/mastery-ewma.md)의 성질."""
import os

os.environ.setdefault("JWT_SECRET", "test-only-mastery-secret")
import main   # noqa: E402


def run(seq):
    e = 0.0
    for i, c in enumerate(seq):
        e = main._ewma_mastery(e, i, c)
    return e


def test_perfect_start_reaches_threshold_at_minimum():
    # 처음부터 잘하는 학습자는 예전(누적)처럼 최소 시도에서 숙달 문턱에 닿는다
    assert run([True] * main._STAGE1_MIN_ATTEMPTS) >= main._STAGE1_MASTERY
    assert run([True] * main._STAGE2_MIN_ATTEMPTS) >= main._STAGE2_MASTERY


def test_recent_answers_weigh_more_than_early_failures():
    seq = [False] * 10 + [True] * 12
    assert run(seq) > 100 * 12 / 22 + 15   # 누적(54.5)보다 최근 성적(정답 연속)을 더 반영


def test_direction_of_updates():
    base = run([True, False, True, True])
    assert main._ewma_mastery(base, 4, True) > base > main._ewma_mastery(base, 4, False)


def test_bounded():
    assert 0.0 <= run([False] * 30) <= 100.0 and 0.0 <= run([True] * 30) <= 100.0


def test_review_quality_agrees_with_pass_decision():
    # 말하기 합격선 50: 55점 합격이면 복습도 성공(3 이상). 합격선 65: 62점 불합격이면 복습도 실패(3 미만)
    assert main._review_quality(55, True) >= 3
    assert main._review_quality(62, False) < 3
    assert main._review_quality(90, True) >= 4
    assert main._review_quality(None, True) >= 3 and main._review_quality(None, False) < 3


_STAGE3_FLOW = r'''
import asyncio, json
from fastapi.testclient import TestClient
import main, database
out = {}
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "s3@example.com", "username": "s3u", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    uid = c.get("/api/auth/me", headers=h).json()["id"]

    async def run(seq, stage):
        vals = []
        async with database.AsyncSessionLocal() as db:
            for ok in seq:
                sp = await main._bump_stage_progress(uid, stage, ok, main._STAGE3_MIN_ATTEMPTS if stage == 3 else main._STAGE4_MIN_ATTEMPTS,
                                                     main._STAGE3_MASTERY if stage == 3 else main._STAGE4_MASTERY, db)
                vals.append([round(sp.mastery_score, 4), sp.status, sp.mastered_attempts])
            await db.commit()
        return vals
    out["s3"] = asyncio.run(run([False, True, True, True, True, True, True, True], 3))
    out["s4"] = asyncio.run(run([True, False, True, True], 4))
print("RESULT " + json.dumps(out))
'''


def test_stage3_and_stage4_use_bias_corrected_ewma():
    import json, os, subprocess, sys, tempfile
    import main
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1")
        env.pop("ANTHROPIC_API_KEY", None)
        p = subprocess.run([sys.executable, "-c", _STAGE3_FLOW], cwd=here, env=env, capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])
    # 3단계: 같은 순서로 _ewma_mastery를 되풀이한 값과 같고, 5번 이상·80 이상에서 처음 숙달한 시도를 남긴다
    est, n, first = 0.0, 0, None
    for i, ok in enumerate([False, True, True, True, True, True, True, True]):
        est = main._ewma_mastery(est, n, ok)
        n += 1
        assert abs(r["s3"][i][0] - round(est, 4)) < 1e-9
        if first is None and n >= main._STAGE3_MIN_ATTEMPTS and est >= main._STAGE3_MASTERY:
            first = n
    assert main._STAGE3_MASTERY == 80.0 and first is not None
    assert r["s3"][-1][1] == "mastered" and r["s3"][-1][2] == first
    # 4단계도 9/27 밤부터 같은 이동 평균(문턱 75, docs/mastery-ewma.md 6절). 예전 누적 합격률은 100·50·66.7·75였다
    est, n = 0.0, 0
    for i, ok in enumerate([True, False, True, True]):
        est = main._ewma_mastery(est, n, ok)
        n += 1
        assert abs(r["s4"][i][0] - round(est, 4)) < 1e-9
    assert main._STAGE4_MASTERY == 75.0
    assert (r["s4"][-1][1] == "mastered") == (n >= main._STAGE4_MIN_ATTEMPTS and est >= main._STAGE4_MASTERY)


_SPEAK_FLOW = r'''
import asyncio, json
from fastapi.testclient import TestClient
import main, database, speak_curriculum as sc
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "sk@example.com", "username": "sku", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    uid = c.get("/api/auth/me", headers=h).json()["id"]

    async def run(stage, seq):
        stg = sc.get_stage(stage)
        vals = []
        async with database.AsyncSessionLocal() as db:
            for ok in seq:
                sp = await main._bump_speak_progress(uid, stage, ok, stg["min_attempts"], stg["mastery"], db)
                vals.append([round(sp.mastery_score, 4), sp.status])
            await db.commit()
        return vals
    seq = [False, False, True, True, True, True, True, True, True, True, True, True]
    out = {"vals": asyncio.run(run(2, seq)), "min": sc.get_stage(2)["min_attempts"], "thr": sc.get_stage(2)["mastery"],
           "vals0": asyncio.run(run(0, seq)), "min0": sc.get_stage(0)["min_attempts"], "thr0": sc.get_stage(0)["mastery"]}
print("RESULT " + json.dumps(out))
'''


def test_speak_stage_uses_bias_corrected_ewma():
    # 말하기 단계도 9/27 밤부터 같은 이동 평균(모음 단계 문턱 85, docs/mastery-ewma.md 6절). 예전 누적 합격률은 초반 두 번 실패가
    # 끝까지 남아 12번째에도 83%였다
    import json, os, subprocess, sys, tempfile
    import main
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1")
        env.pop("ANTHROPIC_API_KEY", None)
        p = subprocess.run([sys.executable, "-c", _SPEAK_FLOW], cwd=here, env=env, capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])
    assert r["thr"] == 85.0
    est, n, first = 0.0, 0, None
    for i, ok in enumerate([False, False] + [True] * 10):
        est = main._ewma_mastery(est, n, ok)
        n += 1
        assert abs(r["vals"][i][0] - round(est, 4)) < 1e-9
        if first is None and n >= r["min"] and est >= r["thr"]:
            first = n
    # 모음 단계는 이동 평균이 문턱에 닿아도 낱말 속 소리 확인(계획 2-5, test_speak_probe.py) 전에는 숙달하지 않는다
    assert first is not None and all(v[1] == "in_progress" for v in r["vals"])
    # 확인이 없는 발성 단계(문턱 85)는 이동 평균만으로 처음 문턱에 닿은 시도에서 숙달한다
    est, n, first = 0.0, 0, None
    for i, ok in enumerate([False, False] + [True] * 10):
        est = main._ewma_mastery(est, n, ok)
        n += 1
        assert abs(r["vals0"][i][0] - round(est, 4)) < 1e-9
        if first is None and n >= r["min0"] and est >= r["thr0"]:
            first = n
    assert r["thr0"] == 85.0
    assert first is not None and r["vals0"][first - 1][1] == "mastered" and r["vals0"][first - 2][1] == "in_progress"
