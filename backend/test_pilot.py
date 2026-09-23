"""파일럿 계측(§4.7) API 테스트 — 참여 코드 검증·집단 배정, 운영자 전용 가명 내보내기(개인정보 미포함).

test_account_security.py와 같은 방식: 임시 DB를 지정한 별도 프로세스에서 시나리오를 돌리고 결과(JSON)만 검사한다.
"""
import functools
import json
import os
import subprocess
import sys
import tempfile

_SCENARIO = r'''
import json, os
from fastapi.testclient import TestClient
import main
out = {}
with TestClient(main.app) as c:
    def reg(email, name):
        r = c.post("/api/auth/register", json={"email": email, "username": name, "password": "pw-123456",
                                               "agree_terms": True, "age_confirmed": True})
        return {"Authorization": "Bearer " + r.json()["access_token"]}
    p1 = reg("p1@example.com", "pilot1")
    op = reg("op@example.com", "operator")
    out["off"] = c.post("/api/pilot/join", json={"code": "ALPHA"}, headers=p1).status_code
    os.environ["LIPLAB_PILOT"] = "1"
    os.environ["LIPLAB_PILOT_CODES"] = "ALPHA:train,BETA:control"
    out["bad_code"] = c.post("/api/pilot/join", json={"code": "nope"}, headers=p1).status_code
    j = c.post("/api/pilot/join", json={"code": "alpha"}, headers=p1)
    out["join"], out["cohort"] = j.status_code, j.json().get("cohort")
    item = main._training_closures()[0]
    c.post("/api/curriculum/closure-answer", json={"item_id": item["id"], "chosen": item["answer"]}, headers=p1)
    out["export_no_admin"] = c.get("/api/pilot/export", headers=op).status_code
    os.environ["LIPLAB_ADMIN_EMAILS"] = "op@example.com"
    ex = c.get("/api/pilot/export", headers=op)
    out["export"] = ex.status_code
    body = ex.json()
    out["n"] = body["n"]
    out["text"] = json.dumps(body, ensure_ascii=False)
    out["row"] = body["participants"][0] if body["participants"] else None
    # 운영자 가명 찾기(철회·파기 요청 처리) — 본문으로 이메일을 받는다
    out["lookup"] = c.post("/api/pilot/lookup", json={"email": "P1@example.com"}, headers=op).json()
    out["lookup_missing"] = c.post("/api/pilot/lookup", json={"email": "none@example.com"}, headers=op).status_code
    out["lookup_no_admin"] = c.post("/api/pilot/lookup", json={"email": "p1@example.com"}, headers=p1).status_code

    # 동형 폼을 역균형 순서(B 먼저, A 나중)로 본다 + 참여 전 배치검사 1회
    def take(form):
        items = c.get("/api/assessment/placement", params={"form": form}, headers=p1).json()["items"]
        resp = {it["id"]: (it["word"] if i % 2 == 0 else (it.get("options") or [it["word"]])[-1])
                for i, it in enumerate(items)}
        return c.post("/api/assessment/score", json={"items": items, "responses": resp, "form": form}, headers=p1)
    take("B"); take("A")
    out["progression"] = c.get("/api/assessment/progression", headers=p1).json()
    ex2 = c.get("/api/pilot/export", headers=op).json()
    out["export_v2"] = {"version": ex2.get("version"), "row": ex2["participants"][0]}

    # 학습 초기화 뒤에도 파일럿 참여와 사전·사후(A·B) 결과는 남는다
    rr = c.post("/api/account/learning-reset", params={"confirm": True}, headers=p1)
    out["reset"] = rr.status_code
    out["reset_kept"] = rr.json().get("kept")
    out["after_reset_joined"] = c.get("/api/pilot/status", headers=p1).json()["joined"]
    after = c.get("/api/pilot/export", headers=op).json()
    out["after_reset_n"] = after["n"]
    out["after_reset_forms"] = [t["form"] for t in after["participants"][0]["tests"]]

    # 파일럿이 아닌 사람은 초기화하면 검사 기록도 지워진다(원래 범위)
    p2 = reg("p2@example.com", "notpilot")
    items = c.get("/api/assessment/placement", params={"form": "A"}, headers=p2).json()["items"]
    c.post("/api/assessment/score", json={"items": items, "responses": {}, "form": "A"}, headers=p2)
    r2 = c.post("/api/account/learning-reset", params={"confirm": True}, headers=p2).json()
    out["nonpilot_removed_tests"] = r2["removed"].get("placement_results")

    # 배치검사(적응형 포함)는 사전·사후 문항 단어를 내지 않는다
    import assessment as _asmt
    tw = _asmt.test_only_words()
    seen = set()
    for _ in range(5):
        for it in c.get("/api/assessment/placement", params={"n": 8}, headers=p2).json()["items"]:
            seen.add(it["word"]); seen.update(it.get("options") or [])
    asked, responses = [], {}
    for _ in range(8):
        nx = c.post("/api/assessment/placement/next", json={"asked": asked, "responses": responses, "n": 8},
                    headers=p2).json()
        if nx.get("done") or not nx.get("item"):
            break
        it = nx["item"]
        seen.add(it["word"]); seen.update(it.get("options") or [])
        asked.append(it); responses[it["id"]] = it["word"]
    out["placement_test_word_leak"] = sorted(seen & tw)
    out["placement_seen"] = len(seen)

    # 기호 켬·끔(J-12): 기호 없는 집단(control)은 기호 목록이 비고, 학습 집단(train)은 그대로다
    os.environ["LIPLAB_PILOT_NOCUE_COHORTS"] = "control"
    p3 = reg("p3@example.com", "nocue")
    c.post("/api/pilot/join", json={"code": "BETA"}, headers=p3)
    off = c.get("/api/cues", params={"text": "밥 먹어요"}, headers=p3).json()
    on = c.get("/api/cues", params={"text": "빵 먹어요", "personalize": False}, headers=p1).json()
    out["cues_off"] = {"n": len(off["cues"]), "suppressed": off.get("suppressed"),
                       "status": c.get("/api/pilot/status", headers=p3).json()["cues"]}
    out["cues_on"] = {"n": len(on["cues"]), "status": c.get("/api/pilot/status", headers=p1).json()["cues"]}
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


@functools.lru_cache(maxsize=1)
def _run():
    """시나리오는 한 번만 돌리고 여러 테스트가 결과를 나눠 본다."""
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1")
        for k in ("LIPLAB_PILOT", "LIPLAB_PILOT_CODES", "LIPLAB_ADMIN_EMAILS", "LIPLAB_PILOT_NOCUE_COHORTS",
                  "LIPLAB_PILOT_SECRET"):
            env.pop(k, None)
        p = subprocess.run([sys.executable, "-c", _SCENARIO], cwd=here, env=env,
                           capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    return json.loads(line[len("RESULT "):])


def test_pilot_join_and_pseudonymized_export():
    r = _run()
    assert r["off"] == 403 and r["bad_code"] == 400
    assert r["join"] == 200 and r["cohort"] == "train"
    assert r["export_no_admin"] == 403 and r["export"] == 200 and r["n"] == 1
    row = r["row"]
    assert len(row["pid"]) == 12 and row["cohort"] == "train"
    assert row["trials_by_stage"]["3"] == {"n": 1, "correct": 1}
    # 이메일·사용자명은 내보내기에 없어야 한다
    assert "p1@example.com" not in r["text"] and "pilot1" not in r["text"]
    assert r["lookup"]["pid"] == row["pid"] and r["lookup"]["cohort"] == "train"
    assert r["lookup_missing"] == 404 and r["lookup_no_admin"] == 403


def test_counterbalanced_order_and_export_v2():
    r = _run()
    prog = r["progression"]
    assert prog["available"] and prog["homogeneous"] and prog["order"] == "B→A", prog
    ex = r["export_v2"]
    assert ex["version"] == 2
    row = ex["row"]
    assert row["joined_on"] and len(row["joined_on"]) == 10
    forms = [t["form"] for t in row["tests"]]
    assert forms == ["B", "A"]
    for t in row["tests"]:
        assert t["after_join"] is True
        assert t["items"] and all(set(i) == {"id", "correct", "chosen"} for i in t["items"])
    assert row["since_join"] is not None and row["since_join"]["trials_by_stage"]["3"] == {"n": 1, "correct": 1}


def test_reset_keeps_pilot_tests_and_placement_hides_test_words():
    r = _run()
    assert r["reset"] == 200 and r["after_reset_joined"] is True and r["after_reset_n"] == 1
    assert r["reset_kept"] == {"placement_results_ab": 2} and r["after_reset_forms"] == ["B", "A"]
    assert r["nonpilot_removed_tests"] == 1
    assert r["placement_seen"] > 20 and r["placement_test_word_leak"] == []


def test_nocue_cohort_gets_no_symbols():
    r = _run()
    assert r["cues_off"] == {"n": 0, "suppressed": "pilot_cohort", "status": False}
    assert r["cues_on"]["n"] > 0 and r["cues_on"]["status"] is True
