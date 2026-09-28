"""감속 재생에서 얻은 정답을 숙달에 0.5로 넣기(docs/mastery-ewma.md 7절, 커리큘럼 개선 계획 1-1)."""
import json
import os
import subprocess
import sys
import tempfile

os.environ.setdefault("JWT_SECRET", "test-only-speed-secret")
import main   # noqa: E402


def test_ewma_accepts_fraction_and_keeps_bool():
    # bool은 예전과 같고, 0.5는 정답과 오답 사이 값이다
    assert main._ewma_mastery(0.0, 0, True) == main._ewma_mastery(0.0, 0, 1.0) == 100.0
    assert main._ewma_mastery(0.0, 0, False) == main._ewma_mastery(0.0, 0, 0.0) == 0.0
    base = main._ewma_mastery(main._ewma_mastery(0.0, 0, True), 1, False)
    half = main._ewma_mastery(base, 2, 0.5)
    assert main._ewma_mastery(base, 2, False) < half < main._ewma_mastery(base, 2, True)
    assert main._ewma_mastery(0.0, 0, 1.7) == 100.0 and main._ewma_mastery(0.0, 0, -1) == 0.0   # 범위 밖은 자른다


def test_speed_credit():
    assert main._speed_credit(1.0, None) == 1.0          # 속도를 보내지 않은 예전 화면·1단계
    assert main._speed_credit(1.0, 1.0) == 1.0
    assert main._speed_credit(1.0, 1.25) == 1.0          # 빠른 말은 그대로 정답 1
    assert main._speed_credit(1.0, 0.85) == 0.5          # 적응 감속으로 늘어난 재생
    assert main._speed_credit(0.0, 0.5) == 0.0
    assert main._speed_credit(1.0, "x") == 1.0


def test_slow_only_learner_cannot_master_by_slow_answers():
    # 감속 정답만 계속 내면 추정값이 50에 머물러 숙달 문턱 85에 닿지 않는다
    e = 0.0
    for i in range(60):
        e = main._ewma_mastery(e, i, main._speed_credit(1.0, 0.8))
    assert 49.0 < e <= 50.0 < main._STAGE2_MASTERY
    assert main._NATURAL_SPEED_GATE < main._STAGE2_MASTERY


_FLOW = r'''
import json, sqlite3, os
from fastapi.testclient import TestClient
import main
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "sp@example.com", "username": "spu", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    w0 = c.get("/api/curriculum/words", headers=h).json()
    scores = []
    for sp in (0.8, 0.8, None, 1.25):
        rr = c.post("/api/curriculum/word-answer", json={"word": "바다", "correct": True, "chosen": "바다", "speed": sp},
                    headers=h).json()
        scores.append(rr["mastery_score"])
    rec = c.post("/api/curriculum/recognition", json={"viseme_id": 1, "chosen_id": 1, "speed": 0.5}, headers=h).json()
    bad = c.post("/api/curriculum/word-answer", json={"word": "바다", "correct": True, "chosen": "바다", "speed": 9},
                 headers=h).status_code
    w1 = c.get("/api/curriculum/words", headers=h).json()
db = sqlite3.connect(os.environ["T_DB"])
speeds = [x[0] for x in db.execute("select speed from trial_attempts order by id")]
print("RESULT " + json.dumps({"w0": {k: w0.get(k) for k in ("mastered", "mastery_score", "natural_speed_gate")},
                              "scores": scores, "rec": rec["mastery_score"], "bad": bad,
                              "w1": w1.get("mastery_score"), "speeds": speeds}))
'''


def test_word_and_recognition_record_speed():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", T_DB=f"{d}/t.db",
                   PYTHONDONTWRITEBYTECODE="1", LIPLAB_UNLOCK_ALL="1")
        env.pop("ANTHROPIC_API_KEY", None)
        p = subprocess.run([sys.executable, "-c", _FLOW], cwd=here, env=env, capture_output=True, text=True, timeout=240)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])
    assert r["w0"] == {"mastered": False, "mastery_score": 0.0, "natural_speed_gate": main._NATURAL_SPEED_GATE}
    # 감속 정답 두 번(0.5씩), 속도 없음(1), 빠른 말(1) 순서를 _ewma_mastery로 되풀이한 값과 같다
    est = 0.0
    for i, credit in enumerate([0.5, 0.5, 1.0, 1.0]):
        est = main._ewma_mastery(est, i, credit)
        assert abs(r["scores"][i] - round(est, 1)) < 1e-9
    assert r["scores"][0] == 50.0
    assert r["rec"] == 50.0                     # 1단계 첫 답도 감속이면 0.5
    assert r["bad"] == 422                      # 말이 안 되는 속도는 받지 않는다
    assert r["w1"] == r["scores"][-1]
    assert r["speeds"] == [0.8, 0.8, None, 1.25, 0.5]
