"""전이 조건 사후 검사(커리큘럼 계획 2-3, docs/talker-variation.md 6절).

사후 검사 문항의 절반은 기본 얼굴, 절반은 검사 전용 가상 화자(h1·h2)로 낸다. 배정은 난이도가 이웃한 두 문항을 짝지어
한쪽씩 나누고 사용자 번호로 역균형한다. 학습 효과 리포트는 기본 얼굴 향상도와 새 화자 조건 점수를 따로 준다.
엔드포인트 흐름은 임시 DB를 지정한 별도 프로세스에서 돌린다(test_assessment_compare.py와 같은 방식).
"""
import json
import os
import subprocess
import sys
import tempfile

import assessment as A


def _form(name="B"):
    return A.frozen_forms(build_if_missing=False)[name]


def test_assignment_splits_half_and_counterbalances():
    items = _form("B")
    a1 = A.assign_talker_conditions(items, 1)
    a2 = A.assign_talker_conditions(items, 2)
    assert [it["id"] for it in a1] == [it["id"] for it in items], "문항 순서는 그대로"
    assert all("talker" not in it for it in items), "동결 폼을 고치지 않는다"
    assert a1 == A.assign_talker_conditions(items, 1), "결정론적"
    for a in (a1, a2):
        held = [it for it in a if it["talker"] != A.DEFAULT_TALKER]
        assert len(held) == 12 and {it["talker"] for it in held} == set(A.HELD_OUT_TALKERS)
        assert sum(it["talker"] == "h1" for it in held) == 6
        d = [it["difficulty"] for it in a if it["talker"] == A.DEFAULT_TALKER]
        h = [it["difficulty"] for it in held]
        assert abs(sum(d) / 12 - sum(h) / 12) < 0.01, "두 절반의 평균 난이도가 맞는다"
    # 홀짝이 다른 사용자는 새 화자 문항이 정확히 뒤집힌다(역균형)
    for x, y in zip(a1, a2):
        assert (x["talker"] == A.DEFAULT_TALKER) != (y["talker"] == A.DEFAULT_TALKER)


def test_scoring_records_condition_and_transfer():
    items = A.assign_talker_conditions(_form("B"), 1)
    resp = {it["id"]: (it["word"] if it["talker"] == A.DEFAULT_TALKER else next(o for o in it["options"] if o != it["word"]))
            for it in items}
    r = A.score_placement(items, resp)
    assert all(e["talker"] in ("default", "h1", "h2") for e in r["item_log"])
    t = r["talker_transfer"]
    assert t["default"] == {"n": 12, "correct": 12, "accuracy": 1.0}
    assert t["new_talker"] == {"n": 12, "correct": 0, "accuracy": 0.0}
    assert t["gap"] == -1.0 and t["talkers"] == ["h1", "h2"]
    face = A.default_face_log(r["item_log"])
    assert len(face) == 12 and A.log_accuracy(face) == 1.0
    assert A.rescore_log(face)["ability"] > A.rescore_log(r["item_log"])["ability"]


def test_old_logs_unchanged():
    items = _form("A")
    r = A.score_placement(items, {it["id"]: it["word"] for it in items})
    assert all("talker" not in e for e in r["item_log"]), "조건 없는 검사 기록은 예전 형식"
    assert r["talker_transfer"] is None
    assert A.default_face_log(r["item_log"]) is r["item_log"]
    assert A.talker_transfer(None) is None and A.default_face_log(None) is None


_FLOW = r'''
import json
from fastapi.testclient import TestClient
import main

def wrong(it):
    return next(o for o in it["options"] if o != it["word"])

out = {}
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "tr@example.com", "username": "tr1", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    ga = c.get("/api/assessment/placement", params={"form": "A"}, headers=h).json()
    out["pre_post_flag"] = ga["post"]
    out["pre_has_talker"] = any("talker" in it for it in ga["items"])
    fa = ga["items"]
    # 사전 A: 24문항 중 12문항 정답(0.5)
    ra = {it["id"]: (it["word"] if i % 2 == 0 else wrong(it)) for i, it in enumerate(fa)}
    c.post("/api/assessment/score", json={"items": fa, "responses": ra, "form": "A"}, headers=h)
    gb = c.get("/api/assessment/placement", params={"form": "B"}, headers=h).json()
    out["post_flag"] = gb["post"]
    fb = gb["items"]
    out["held"] = sum(it["talker"] != "default" for it in fb)
    # 사후 B: 기본 얼굴 12문항은 모두 정답, 새 화자 12문항은 9개 정답
    k = 0
    rb = {}
    for it in fb:
        if it["talker"] == "default":
            rb[it["id"]] = it["word"]
        else:
            rb[it["id"]] = it["word"] if k < 9 else wrong(it)
            k += 1
    sb = c.post("/api/assessment/score", json={"items": fb, "responses": rb, "form": "B"}, headers=h).json()
    out["score_transfer"] = sb["talker_transfer"]
    out["prog"] = c.get("/api/assessment/progression", headers=h).json()
    out["hist"] = c.get("/api/assessment/history", headers=h).json()
    out["report_transfer"] = c.get("/api/assessment/report", headers=h).json()["progression"]["talker_transfer"]
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


def test_post_test_conditions_end_to_end():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1")
        env.pop("ANTHROPIC_API_KEY", None)
        p = subprocess.run([sys.executable, "-c", _FLOW], cwd=here, env=env, capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])
    assert r["pre_post_flag"] is False and r["pre_has_talker"] is False, "사전 검사는 모두 기본 얼굴"
    assert r["post_flag"] is True and r["held"] == 12
    assert r["score_transfer"]["new_talker"]["accuracy"] == 0.75 and r["score_transfer"]["default"]["accuracy"] == 1.0
    prog = r["prog"]
    # 기본 얼굴 향상도: 사후는 기본 얼굴 절반(1.0), 전체 24문항 정확도(21/24)는 따로
    assert prog["pre"]["accuracy"] == 0.5 and prog["post"]["accuracy"] == 1.0
    assert prog["post"]["accuracy_all"] == 0.875 and prog["post"]["n_default"] == 12
    assert prog["accuracy_delta"] == 0.5
    t = prog["talker_transfer"]
    assert t["new_talker"] == {"n": 12, "correct": 9, "accuracy": 0.75} and t["gap"] == -0.25
    assert r["report_transfer"] == t
    assert r["hist"]["latest"]["accuracy"] == 1.0, "첫 검사 대비 향상도도 기본 얼굴로 비교"
