"""소리 듣기 배치검사 후보 D(backend/listen_placement.py, docs/listen-placement3-2026-10.md 11절) 테스트.

1. 일치 시험: scripts/listen_placement3_sim.py의 시뮬레이터(run_chunk_d)를 고정 시드로 직접 돌려 사람마다 낸 문항과 답을 기록하고,
   같은 답을 이 모듈에 차례로 넣어 (가) 문항마다 고른 종류·SNR, (나) 멈춘 문항 수, (다) 위 단계·두 시작 수준이 모두 같은지 본다.
2. 문항 풀 규칙(1차 4.2절), 다시 채점·답 열 확인, next_level의 시작 수준 인자.
3. API: 플래그 LISTEN_PLACEMENT가 꺼져 있으면 404이고 화면 응답이 그대로, 켜면 검사 → 적용 → 단계 상태·시작 수준.
"""
import json
import os
import subprocess
import sys
import tempfile
from functools import lru_cache

import numpy as np
import pytest

import listen_curriculum as L
import listen_placement as P

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS = os.path.join(_ROOT, "scripts")

PARITY_SEED = 999          # 3차 문서 3절의 코드 점검 시드(판정 시드 0·101·102와 겹치지 않음)
PARITY_N = 60


def _sim_d():
    sys.path.insert(0, _SCRIPTS)
    import listen_placement3_sim as P3
    return P3


@lru_cache(maxsize=1)
def _parity_run():
    """조건 아홉 개 × PARITY_N명을 시뮬레이터로 돌리고, 사람마다 (사건 열, 시뮬레이터 결정)을 모은다."""
    P3 = _sim_d()
    orig = P3.BatchD
    made = []

    class LogBatch(orig):
        def __init__(self, b):
            super().__init__(b)
            self.log = [[] for _ in range(b)]
            made.append(self)

        def add_ax(self, idx, ok):
            for i, o in zip(np.atleast_1d(idx), np.atleast_1d(ok)):
                self.log[i].append({"kind": "pa", "ok": bool(o)})
            super().add_ax(idx, ok)

        def add_word(self, idx, ok):
            for i, o in zip(np.atleast_1d(idx), np.atleast_1d(ok)):
                self.log[i].append({"kind": "pw", "ok": bool(o)})
            super().add_word(idx, ok)

        def add_quiet(self, idx, k, n):
            for i, kk in zip(np.atleast_1d(idx), np.atleast_1d(k)):
                self.log[i].append({"kind": "pq", "k": int(kk)})
            super().add_quiet(idx, k, n)

        def add_noise(self, idx, x_eff, k, n):
            for i, x, kk in zip(np.atleast_1d(idx), np.atleast_1d(x_eff), np.atleast_1d(k)):
                self.log[i].append({"kind": "pn", "xe": float(x), "k": int(kk)})
            super().add_noise(idx, x_eff, k, n)

    cfgname = P.VERSION
    _, g, m, s, tg, ur, lr = next(c for c in P3.combos_d() if c[0] == cfgname)
    people = []
    P3.BatchD = LogBatch
    try:
        for cname in P3.CONDS:
            made.clear()
            _, Lst, traj, _ = P3.job(("D", g, cname, PARITY_SEED, PARITY_N, PARITY_N))
            logs = [row for b in made if any(b.log) for row in b.log]
            assert len(logs) == PARITY_N
            pu, p1, p2, last = traj["pu"], traj["p1"], traj["p2"], traj["last"]
            ok = pu.max(-1) >= s
            stop = P3.P2._stop(ok, last, m)
            ar = np.arange(len(last))
            up = P3.decide_n(pu[ar, stop], ur) + 2
            l1 = P3.decide_n(p1[ar, stop], lr)
            l2 = P3.decide_n(p2[ar, stop], lr)
            for i in range(PARITY_N):
                people.append({"cond": cname, "events": logs[i], "stop": int(stop[i]), "up": int(up[i]), "l1": int(l1[i]),
                               "l2": int(l2[i]), "pu": pu[i, stop[i]], "p1": p1[i, stop[i]], "p2": p2[i, stop[i]]})
    finally:
        P3.BatchD = orig
    assert (g, m, s, tg, ur, lr) == (1, 4, 0.95, "upper", "mode", "q0.8")
    return people


def test_parity_with_simulator():
    """모듈이 시뮬레이터와 같은 문항을 고르고, 같은 곳에서 멈추고, 같은 결정을 낸다(조건 9 × 60명, 시드 999)."""
    people = _parity_run()
    mism = []
    max_dp = 0.0
    for pi, p in enumerate(people):
        answers = []
        for t in range(p["stop"]):
            s = P.step(answers)
            ev = p["events"][t]
            if s["done"] or s["kind"] != ev["kind"]:
                mism.append((pi, t, "kind", s.get("kind"), ev["kind"]))
                break
            if ev["kind"] == "pn":
                voice = P.SENT_VOICES[sum(1 for a in answers if a["kind"] in ("pq", "pn")) % 2]
                if s["snr"] - P.VOFF[voice] != ev["xe"]:
                    mism.append((pi, t, "snr", s["snr"], ev["xe"]))
                    break
                answers.append({"kind": "pn", "snr": s["snr"], "k": ev["k"]})
            else:
                answers.append({k: v for k, v in ev.items()})
        else:
            s = P.step(answers)
            if not s["done"]:
                mism.append((pi, p["stop"], "not_stopped"))
                continue
            r = s["result"]
            if (r["upper"], r["level1"], r["level2"]) != (p["up"], p["l1"], p["l2"]):
                mism.append((pi, p["stop"], "decision", (r["upper"], r["level1"], r["level2"]), (p["up"], p["l1"], p["l2"])))
            pr = P.probabilities(answers)
            max_dp = max(max_dp, float(np.max(np.abs(np.array(pr["upper"]) - p["pu"]))),
                         float(np.max(np.abs(np.array(pr["level1"]) - p["p1"]))),
                         float(np.max(np.abs(np.array(pr["level2"]) - p["p2"]))))
    assert not mism, f"{len(mism)}명 불일치: {mism[:5]}"
    assert max_dp < 1e-9, max_dp
    # 시험이 비어 있지 않다: 여러 갈래의 결과와 문항 종류가 나온다
    assert {p["up"] for p in people} == {3, 4, 5}
    assert len({p["l1"] for p in people}) >= 3 and len({p["l2"] for p in people}) >= 2
    assert {e["kind"] for p in people for e in p["events"][:p["stop"]]} == {"pa", "pw", "pq", "pn"}


def test_parity_summary_printed(capsys):
    """문서 11절에 적은 일치 결과 요약(사람 수, 평균 문항 수)이 다시 계산된다."""
    people = _parity_run()
    n = len(people)
    items = np.mean([p["stop"] for p in people])
    assert n == 9 * PARITY_N and 4 <= items <= 16
    print(f"PARITY n={n} mean_items={items:.2f}")


# ── 문항 풀·채점 ──────────────────────────────────────────────────────

def test_pools_follow_placement_rules():
    pl = P.pools()
    sents = pl["sentences"]
    assert [sid for sid, _ in sents] == list(P.SENTENCE_POOL)
    forms = {s for f in L.TEST_FORMS.values() for s in f} if isinstance(L.TEST_FORMS, dict) else set()
    for sid, text in sents:
        assert text == L.TRAIN_BY_ID[sid] and not L.gen_words_in(text) and text not in forms
        assert len(text.split()) == P.N_WORDS
    pairs = {(p["a"], p["b"]) for p in pl["pairs"]}
    assert len(pairs) == 17 and not pairs & {("바", "다"), ("바", "가"), ("파", "타")}
    assert all(p["level"] == 4 for p in pl["pairs"])
    banned = set(L.GEN_WORDS) | set(L.GEN_REPLACE_CANDIDATES)
    assert not banned & set(pl["word_pool"])
    assert len(pl["word_targets"]) >= P.MAX_ITEMS and all(not L.avoid_voices_word(w) for w in pl["word_targets"])


def test_items_unique_voices_and_scoring():
    seed = "u1:abc"
    counts = {"pa": 0, "pw": 0, "sent": 0}
    seen = {"pa": set(), "pw": set(), "sent": set()}
    sames = []
    for j in range(13):
        for kind, ck in (("pa", "pa"), ("pw", "pw"), ("pq" if j % 2 else "pn", "sent")):
            it = P.make_item(seed, kind, 6.0, counts)
            assert it["voice"] in P.TRAIN_VOICES and it["voice"] != "m3"
            if kind == "pa":
                pair = frozenset((it["first"], it["second"]))
                sames.append(it["first"] == it["second"])
                assert it["voice"] not in L.avoid_voices_ax(*sorted(next(
                    (p["a"], p["b"]) for p in P.pools()["pairs"] if {it["first"], it["second"]} <= {p["a"], p["b"]})))
                seen["pa"].add((pair, j))
            elif kind == "pw":
                assert it["target"] in it["options"] and len(set(it["options"])) == 4
                assert not (set(it["options"]) & (set(L.GEN_WORDS) | set(L.GEN_REPLACE_CANDIDATES)))
                assert it["target"] not in seen["pw"]
                seen["pw"].add(it["target"])
            else:
                assert it["id"] not in seen["sent"] and it["voice"] == P.SENT_VOICES[j % 2]
                seen["sent"].add(it["id"])
            counts[ck] += 1
    assert 4 <= sum(sames) <= 9
    # 같은 seed면 같은 문항
    assert P.make_item(seed, "pw", None, {"pw": 3}) == P.make_item(seed, "pw", None, {"pw": 3})
    # 다시 채점
    s_item = P.make_item(seed, "pn", 10.0, {"sent": 0})
    core, rec = P.score_raw(s_item, {"answer": s_item["text"]})
    assert core == {"kind": "pn", "k": 4, "snr": 10.0} and rec["k"] == 4
    assert P.score_raw(s_item, {"answer": ""})[0]["k"] == 0
    a_item = P.make_item(seed, "pa", None, {"pa": 0})
    assert P.score_raw(a_item, {"same": a_item["first"] == a_item["second"]})[0]["ok"] is True
    with pytest.raises(ValueError):
        P.score_raw(a_item, {})


def test_replay_checks_item_keys():
    seed = "u2:s"
    r0 = P.replay(seed, [])
    assert not r0["done"] and r0["n"] == 0
    it = r0["item"]
    raw = {"item_key": it["key"], "answer": it.get("text", ""), "same": True}
    r1 = P.replay(seed, [raw])
    assert r1["n"] == 1 and r1["log"][0]["key"] == it["key"]
    with pytest.raises(ValueError):
        P.replay(seed, [{"item_key": "pl:pq:t999", "answer": "x"}])
    with pytest.raises(ValueError):
        P.state_of([{"kind": "pn", "snr": 7.0, "k": 2}])     # 후보에 없는 SNR
    # 끝까지: 모두 맞히는 사람은 위 단계 5, 두 수준 맨 위(문장 받아쓰기 정답, 같다·다르다 정답, 낱말 정답)
    answers = []
    for _ in range(P.MAX_ITEMS + 1):
        r = P.replay(seed, answers)
        if r["done"]:
            break
        it = r["item"]
        answers.append({"item_key": it["key"], "answer": it.get("text") or it.get("target"), "same": it.get("first") == it.get("second")})
    assert r["done"] and r["result"]["upper"] == 5 and r["result"]["level1"] == 4 and r["result"]["level2"] == 3
    assert r["result"]["items"] <= P.MAX_ITEMS and r["result"]["seconds"] <= P.MAX_SECONDS
    with pytest.raises(ValueError):
        P.replay(seed, answers + [answers[-1]])                 # 끝난 뒤의 답
    # 모두 틀리는 사람은 위 단계 3, 두 수준 1
    answers = []
    for _ in range(P.MAX_ITEMS + 1):
        r = P.replay(seed, answers)
        if r["done"]:
            break
        it = r["item"]
        answers.append({"item_key": it["key"], "answer": "", "same": it.get("first") != it.get("second")})
    assert (r["result"]["upper"], r["result"]["level1"], r["result"]["level2"]) == (3, 1, 1)


def test_next_level_start_argument():
    """기록이 없으면 start(기본 1)에서 시작하고, 기록이 있으면 start는 쓰이지 않는다(지금 규칙 그대로)."""
    assert L.next_level([], 1) == 1 and L.next_level([], 2) == 1
    assert L.next_level([], 1, start=3) == 3 and L.next_level([], 2, start=3) == 3
    assert L.next_level([], 2, start=9) == 3 and L.next_level([], 1, start=0) == 1   # 범위 밖은 자른다
    hist = [(2, True)] * 10
    assert L.next_level(hist, 1, start=4) == L.next_level(hist, 1) == 3
    assert L.next_level([(1, False)] * 6, 2, start=3) == 1


def test_today_plan_both_leveled():
    """배치검사를 적용한 학습자만 1·2단계 묶음을 함께 받는다(기본값은 예전과 같다)."""
    st = {0: "mastered", 1: "in_progress", 2: "in_progress", 3: "unlocked", 4: "locked", 5: "locked"}
    base = L.today_plan(st, True)
    assert [b["stage"] for b in base] == [1, 3] and base == L.today_plan(st, True, both_leveled=False)
    both = L.today_plan(st, True, both_leveled=True)
    assert [b["stage"] for b in both] == [1, 2, 3]
    st2 = {**st, 1: "mastered"}
    assert L.today_plan(st2, True, both_leveled=True) == L.today_plan(st2, True)


# ── API ──────────────────────────────────────────────────────────────

_FLOW = r'''
import json, os, sqlite3
from fastapi.testclient import TestClient
import main, listen_curriculum as L

def sql(q, *a):
    db = sqlite3.connect(os.environ["T_DB"])
    rows = db.execute(q, a).fetchall()
    db.commit(); db.close()
    return rows

out = {}
with TestClient(main.app) as c:
    def reg(email, name):
        r = c.post("/api/auth/register", json={"email": email, "username": name, "password": "pw-123456",
                                               "agree_terms": True, "age_confirmed": True})
        return {"Authorization": "Bearer " + r.json()["access_token"]}
    h = reg("pl@example.com", "pl1")
    cur0 = c.get("/api/listen/curriculum", headers=h).json()
    out["cur_keys"] = sorted(cur0.keys())
    out["placement0"] = cur0.get("placement")
    out["next0"] = c.post("/api/listen/placement/next", json={"answers": []}, headers=h).status_code
    out["apply0"] = c.post("/api/listen/placement/apply", json={"session": "x", "answers": []}, headers=h).status_code
    if os.environ.get("LISTEN_PLACEMENT") == "D":
        c.post("/api/listen/ling", json={"results": {k: True for k in L.LING_KEYS}, "false_alarms": 0}, headers=h)
        cur1 = c.get("/api/listen/curriculum", headers=h).json()
        out["placement1"] = cur1.get("placement")
        r = c.post("/api/listen/placement/next", json={"answers": []}, headers=h).json()
        sess = r["session"]
        answers = []
        kinds = []
        while not r["done"]:
            it = r["item"]
            kinds.append(it["kind"])
            # 소리 구별·문장은 맞히고, 낱말은 틀린다(2단계 시작 수준이 낮게 나오게)
            if it["kind"] == "pa":
                a = {"item_key": it["key"], "same": it["first"] == it["second"]}
            elif it["kind"] == "pw":
                a = {"item_key": it["key"], "answer": next(o for o in it["options"] if o != it["target"])}
            else:
                a = {"item_key": it["key"], "answer": it["text"]}
            answers.append(a)
            r = c.post("/api/listen/placement/next", json={"session": sess, "answers": answers}, headers=h).json()
        out["result"] = r["result"]
        out["kinds"] = kinds
        out["bad_key"] = c.post("/api/listen/placement/next", json={"session": sess, "answers": [{"item_key": "pl:pq:t999", "answer": ""}]},
                                headers=h).status_code
        out["attempts_before"] = sql("select count(*) from listen_attempts where stage > 0")[0][0]
        ap = c.post("/api/listen/placement/apply", json={"session": sess, "answers": answers}, headers=h)
        out["apply"] = [ap.status_code, ap.json()]
        out["apply_again"] = c.post("/api/listen/placement/apply", json={"session": sess, "answers": answers}, headers=h).status_code
        out["attempts_after"] = sql("select count(*) from listen_attempts where stage > 0")[0][0]
        out["runs"] = sql("select session, version, applied from listen_placement_runs")
        path = c.get("/api/listen/curriculum", headers=h).json()
        out["recommended"] = path["recommended"]
        st = {s["stage"]: s for s in path["stages"]}
        out["status"] = {n: [st[n]["status"], st[n].get("level")] for n in range(6)}
        s1 = c.get("/api/listen/stage/1", headers=h).json()
        s2 = c.get("/api/listen/stage/2", headers=h).json()
        out["stage_levels"] = [s1["level"], s2["level"], sorted({i["level"] for i in s2["items"]})]
        w = s2["items"][0]
        a = c.post("/api/listen/answer", json={"stage": 2, "item_key": w["key"], "answer": w["target"], "level": w["level"]}, headers=h).json()
        out["word_answer_level"] = [a["counted"], a["level"], sql("select level from listen_attempts where stage = 2")[0][0]]
        out["placement2"] = c.get("/api/listen/curriculum", headers=h).json().get("placement")
        today = c.get("/api/listen/today", headers=h).json()
        out["today_stages"] = sorted({b.get("stage") for b in today["blocks"]})
        # 0단계를 마치지 않은 사람은 검사를 받을 수 없다
        h2 = reg("pl2@example.com", "pl2")
        out["not_ready"] = c.post("/api/listen/placement/next", json={"answers": []}, headers=h2).status_code
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


def _run(flag):
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", T_DB=f"{d}/t.db", PYTHONDONTWRITEBYTECODE="1",
                   LIPLAB_UNLOCK_ALL="0")
        for k in ("ANTHROPIC_API_KEY", "LIPLAB_PILOT", "LIPLAB_PILOT_CODES", "LIPLAB_ADMIN_EMAILS", "LISTEN_PLACEMENT"):
            env.pop(k, None)
        if flag is not None:
            env["LISTEN_PLACEMENT"] = flag
        p = subprocess.run([sys.executable, "-c", _FLOW], cwd=here, env=env, capture_output=True, text=True, timeout=300)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-4000:]}"
    return json.loads(line[len("RESULT "):])


@pytest.mark.parametrize("flag", [None, "off", "C", "0"])
def test_api_flag_off_is_unchanged(flag):
    r = _run(flag)
    assert "stages" in r["cur_keys"] and "placement" not in r["cur_keys"] and r["placement0"] is None
    assert r["next0"] == 404 and r["apply0"] == 404


@lru_cache(maxsize=1)
def _run_on():
    return _run("D")


def test_api_flag_on_flow():
    r = _run_on()
    assert {"placement", "stages", "recommended", "ling_today", "next_node"} <= set(r["cur_keys"]) and r["placement0"] == {"available": False, "reason": "ling_first", "version": P.VERSION}
    assert r["next0"] == 409 and r["apply0"] == 409 and r["not_ready"] == 409
    assert r["placement1"] == {"available": True, "reason": None, "version": P.VERSION}
    res = r["result"]
    assert r["recommended"] == res["upper"]
    assert 4 <= res["items"] <= 16 and res["version"] == P.VERSION
    assert res["level2"] in (1, 2, 3) and res["level1"] in (1, 2, 3, 4) and res["upper"] in (3, 4, 5) and len(r["kinds"]) == res["items"]
    assert r["bad_key"] == 400
    assert r["attempts_before"] == 0 and r["attempts_after"] == 0          # 검사 답은 시행 기록에 넣지 않는다
    code, body = r["apply"]
    assert code == 200 and body["upper"] == res["upper"] and body["level1"] == res["level1"]
    assert r["apply_again"] == 409
    assert r["runs"] and r["runs"][0][1] == P.VERSION and r["runs"][0][2] == 1
    st = {int(k): v for k, v in r["status"].items()}
    assert st[0][0] == "mastered"
    assert st[1] == ["in_progress", res["level1"]] and st[2] == ["in_progress", res["level2"]]
    for n in range(3, 6):
        assert st[n][0] == ("unlocked" if n <= res["upper"] else "locked")
    assert r["stage_levels"][0] == res["level1"] and r["stage_levels"][1] == res["level2"]
    assert r["stage_levels"][2] == [res["level2"]]
    assert r["word_answer_level"] == [True, res["level2"], res["level2"]]
    assert r["placement2"]["available"] is False and r["placement2"]["reason"] == "already"
    assert {1, 2, 4 if res["upper"] >= 4 else 3} <= set(r["today_stages"])
