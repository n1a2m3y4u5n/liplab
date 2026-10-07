"""소리 듣기 연습 모드·듣기 복습·소리 교실·과제·분석 연동 테스트(docs/listen-integration-api-2026-10.md).

test_listen_curriculum.py와 같은 방식: 순수 함수는 바로, API는 임시 DB를 지정한 별도 프로세스에서 시나리오를 돌리고 결과(JSON)만 본다.
연습 모드 답(session 'practice:<모드>')이 어디에 들어가고 어디에 안 들어가는지를 여기서 고정한다.
  단계 숙달·수준·4단계 계단·단계 상태: 안 들어감
  혼동 집계·간격 복습·소리 구별 정답률·연습량(요약 days, 과제, 분석): 들어감
  내보내기 trials_by_stage: 안 들어감(practice_by_mode에 따로)
"""
import json
import os
import subprocess
import sys
import tempfile
from functools import lru_cache

import listen_curriculum as L


# ── 순수 함수 ─────────────────────────────────────────────────────────

def test_parse_contrast():
    assert L.parse_contrast("onset:ㅂ:ㅍ")["label"] == "첫소리 ㅂ·ㅍ"
    assert L.parse_contrast("coda:ㄴ:-")["label"] == "받침 ㄴ·없음"
    assert L.parse_contrast("kind:fricative") == {"key": "kind:fricative", "type": "kind", "kind": "fricative", "label": "마찰음"}
    for bad in ("", "onset:ㅂ:ㅂ", "vowel:ㅐ:ㅔ", "kind:nope", "onset:ㅏ:ㅂ", "tone:ㅂ:ㅍ", "onset:ㅂ"):
        assert L.parse_contrast(bad) is None, bad


def test_contrast_kind_matches_ax_pairs():
    """낱말 대조의 종류 나눔이 소리 구별 짝(AX_PAIRS)의 종류와 같다(한 소리만 다른 짝 모두)."""
    for p in L.AX_PAIRS:
        cs = L.contrast_of(p["a"], p["b"])
        if len(cs) == 1:
            assert L.contrast_kind(cs[0]) == p["kind"], p


def test_contrast_practice_items():
    pool = L.word_pool()
    spec = L.parse_contrast("onset:ㅂ:ㅍ")
    its = L.contrast_practice_items(spec, pool, "s1", n=12)
    assert len(its) == 12
    ax = [i for i in its if i["type"] == "ax"]
    words = [i for i in its if i["type"] == "word"]
    assert ax and words and all(i["stage"] == 1 for i in ax) and all(i["stage"] == 2 for i in words)
    assert sum(i["first"] == i["second"] for i in ax) in (len(ax) // 2, (len(ax) + 1) // 2)
    for i in ax:
        assert L.ax_parse(i["key"]) and {i["first"], i["second"]} <= {"바", "파"}
    for i in words:
        assert i["target"] in i["options"] and len(set(i["options"])) == len(i["options"]) == 4
        assert {i["focus"]["target"], i["focus"]["heard"]} == {"ㅂ", "ㅍ"}
        # 그 대조 하나로만 갈리는 보기가 들어 있다
        assert any(L.contrast_of(i["target"], o) and len(L.contrast_of(i["target"], o)) == 1 and
                   {L.contrast_of(i["target"], o)[0]["target"], L.contrast_of(i["target"], o)[0]["heard"]} == {"ㅂ", "ㅍ"}
                   for o in i["options"] if o != i["target"])
    assert its == L.contrast_practice_items(spec, pool, "s1", n=12) and its != L.contrast_practice_items(spec, pool, "s2", n=12)
    # 낱말이 없는 종류(길이)는 같다·다르다만
    ln = L.contrast_practice_items(L.parse_contrast("kind:length"), pool, "s", n=12)
    assert len(ln) == 12 and all(i["type"] == "ax" for i in ln)
    # 종류 대조의 낱말 문항은 그 종류로 갈리는 보기를 갖는다
    fr = [i for i in L.contrast_practice_items(L.parse_contrast("kind:fricative"), pool, "s", n=12) if i["type"] == "word"]
    assert fr and all(L.contrast_kind(i["focus"]) == "fricative" for i in fr)


def test_contrast_catalog():
    cat = L.contrast_catalog(L.word_pool())
    assert [k["kind"] for k in cat] == list(L.AX_KIND_LABEL)
    by = {k["kind"]: k for k in cat}
    assert all(k["desc"] and k["pairs"] for k in cat)
    assert by["intonation"]["lip"] == "same" and by["length"]["lip"] == "differs"
    assert by["laryngeal"]["lip"] == "same" and by["place"]["lip"] == "differs"     # ㅂ·ㅍ는 같은 입, 자리가 다르면 다른 입
    assert "소리로 가려야" in by["laryngeal"]["desc"]
    for k in cat:
        seen = set()
        for w in k["words"]:
            assert w["distance"] <= 2 and L.sound_distance(w["target"], w["partner"]) == w["distance"]
            cs = L.contrast_of(w["target"], w["partner"])
            assert len(cs) == 1 and L.contrast_kind(cs[0]) == k["kind"]
            assert L.parse_contrast(w["contrast"]) is not None
            assert not {w["target"], w["partner"]} & seen
            seen |= {w["target"], w["partner"]}
    # 가까운 순이고(거리 1부터, 모자라면 2), 마찰음 종류만 거리 1인 짝이 없다
    for k in cat:
        ds = [w["distance"] for w in k["words"]]
        assert ds == sorted(ds) and (not ds or ds[0] == (2 if k["kind"] == "fricative" else 1)), k["kind"]
    assert not by["length"]["words"] and by["place"]["words"]
    # 소리 없는 글은 넣지 않는다
    none = L.contrast_catalog(L.word_pool(), has_sound=lambda t: False)
    assert all(not k["pairs"] and not k["words"] for k in none)
    only = L.contrast_catalog(L.word_pool(), has_sound=lambda t: t in {"바", "파"})
    assert [p for k in only for p in k["pairs"]] == [{"a": "바", "b": "파", "level": 3, "lip_same": True}]


def test_scenes_cover_places():
    places = {c["place"] for c in L.CONVO_ITEMS}
    member = [p for s in L.SCENES for p in s["places"]]
    assert places <= set(member) and len(member) == len(set(member))      # 장소마다 정확히 한 묶음
    sp = L.scene_places()
    assert [s["key"] for s in sp] == [s["key"] for s in L.SCENES]
    assert all(s["n"] >= 4 for s in sp) and sum(s["n"] for s in sp) == len(L.CONVO_ITEMS)
    its = L.scene_items("home", "x")
    assert len(its) == 4 and all("answer" not in i and L.CONVO_BY_ID[i["id"]]["place"] in ("아파트", "집", "관리실 안내") for i in its)
    assert L.scene_items("home", "x", recent=[its[0]["id"]])[-1]["id"] == its[0]["id"]
    assert [i["id"] for i in L.scene_items("병원", "x")] and all(i["place"] == "병원" for i in L.scene_items("병원", "x"))
    assert L.scene_items("nope", "x") is None


def test_new_convo_items_content_rules():
    """10/7 연습 모드에 맞춰 더한 대화 문항(c31~c34): 대사·바꾼 말이 P3 파일럿·검사·훈련 문장·다른 대화와 유사도 점검에 걸리지 않고,
    일반화 검사 낱말이 글자로 들어 있지 않다(docs/review/listen-content-review-2026-10.md 1·3.3절)."""
    import importlib.util
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "build_pilot_manifest.py")
    spec = importlib.util.spec_from_file_location("build_pilot_manifest", path)
    B = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(B)
    new = [c for c in L.CONVO_ITEMS if c["id"] in ("c31", "c32", "c33", "c34")]
    assert len(new) == 4
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "pilot", "battery_manifest.json"),
              encoding="utf-8") as f:
        man = json.load(f)
    pilot = []

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k == "text" and isinstance(v, str) and sum("가" <= ch <= "힣" for ch in v) >= 4:
                    pilot.append(v)
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(man)
    others = list(L.TRAIN_SENTENCES) + [s for f in L.TEST_FORMS.values() for s in f] + pilot
    for c in L.CONVO_ITEMS:
        if c not in new:
            others += [c["line"], c["paraphrase"]]
    for c in new:
        mine = [c["line"], c["paraphrase"]]
        rest = others + [t for o in new if o is not c for t in (o["line"], o["paraphrase"])]
        for t in mine:
            for o in rest:
                assert not B.similarity_reasons(t, o, both_ways=True), (c["id"], t, o)
        blob = " ".join(mine + [c["question"]] + c["options"])
        assert not [g for g in L.GEN_WORDS if g in blob], c["id"]
    assert set(t for c in new for t in (c["line"], c["paraphrase"])) <= set(L.inventory_texts())


def test_condition_items():
    r = L.condition_items("room", "s", n=6)
    assert [i["rt60"] for i in r] == list(L.ROOM_RT60) * 2 and all(i["cond"] == "room" for i in r)
    nz = L.condition_items("noise", "s", n=8, snr_db=12.0)
    assert {i["noise"] for i in nz} == set(L.TRAIN_NOISES) and all(i["snr_db"] == 12.0 for i in nz)
    assert {i["noise"] for i in L.condition_items("noise", "s", n=4, noise="ssn")} == {"ssn"}
    assert {i["noise"] for i in L.condition_items("noise", "s", n=4, noise=L.HELDOUT_NOISE)} != {L.HELDOUT_NOISE}
    assert all("rt60" not in i and "noise" not in i for i in L.condition_items("phone", "s", n=3))


def test_practice_session_names():
    assert L.practice_session("contrast") == "practice:contrast"
    assert L.is_practice_session("practice:review") and not L.is_practice_session("practice")
    assert not L.is_practice_session(None) and not L.is_practice_session("test:abc")
    assert set(L.PRACTICE_KEYS) == {"contrast", "dictation", "noise_endless", "scenario", "conditions"}


def test_daily_tasks_listen():
    from datetime import date
    import daily_tasks as D
    t = date(2030, 1, 9)
    st = D.stats([], t, 0, listen_minutes=15.2)
    keys = [r["key"] for r in D.board(st, t, [])]
    assert "listen_15" not in keys
    rows = {r["key"]: r for r in D.board(st, t, [], listen=True)}
    assert rows["listen_15"]["cur"] == 15 and rows["listen_15"]["done"] and rows["listen_15"]["period_key"] == t.isoformat()
    assert not {r["key"]: r for r in D.board(D.stats([], t, 0, listen_minutes=14.9), t, [], listen=True)}["listen_15"]["done"]
    assert [t_["key"] for t_ in D.tasks_for(True)][-1] == "week_5days"


# ── API 흐름 ──────────────────────────────────────────────────────────

_FLOW = r'''
import json, os, sqlite3
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
import main, listen_curriculum as L

def sql(q, *a):
    db = sqlite3.connect(os.environ["T_DB"])
    rows = db.execute(q, a).fetchall()
    db.commit(); db.close()
    return rows

def shift(days):
    # 모든 듣기 시행을 days일 앞으로 옮긴다(간격 복습 흉내)
    sql("update listen_attempts set created_at = datetime(created_at, ?)", f"-{days} days")

out = {}
with TestClient(main.app) as c:
    def reg(email, name):
        r = c.post("/api/auth/register", json={"email": email, "username": name, "password": "pw-123456",
                                               "agree_terms": True, "age_confirmed": True})
        return {"Authorization": "Bearer " + r.json()["access_token"]}
    h = reg("lp@example.com", "lp1")
    op = reg("op@example.com", "operator")
    out["tasks_before"] = [t["key"] for t in c.get("/api/tasks", headers=h).json()["daily"]]
    out["overview_before"] = c.get("/api/analysis/overview", headers=h).json()["listen"]
    m0 = c.get("/api/listen/practice/modes", headers=h).json()["modes"]
    out["modes0"] = [[m["key"], m["available"], bool(m.get("reason"))] for m in m0]
    out["locked_get"] = c.get("/api/listen/practice/contrast", headers=h).status_code
    c.post("/api/listen/ling", json={"results": {k: True for k in L.LING_KEYS}, "false_alarms": 0}, headers=h)
    out["modes1"] = [m["available"] for m in c.get("/api/listen/practice/modes", headers=h).json()["modes"]]
    out["unknown_mode"] = c.get("/api/listen/practice/bogus", headers=h).status_code
    out["bad_contrast"] = c.get("/api/listen/practice/contrast", params={"contrast": "onset:ㅂ:ㅂ"}, headers=h).status_code

    # 소리 짝 집중 연습: 묻지 않으면(혼동 기록 없음) 기본 대조
    d0 = c.get("/api/listen/practice/contrast", headers=h).json()
    out["contrast_default"] = [d0["source"], d0["contrast"]["key"], len(d0["items"])]
    pc = c.get("/api/listen/practice/contrast", params={"contrast": "onset:ㅂ:ㅍ"}, headers=h).json()
    out["contrast"] = [pc["source"], pc["contrast"]["label"], len(pc["items"]), sorted({i["type"] for i in pc["items"]}),
                       pc["n_done"]]
    ax = next(i for i in pc["items"] if i["type"] == "ax")
    a1 = c.post("/api/listen/answer", json={"stage": 1, "item_key": ax["key"], "same": ax["first"] == ax["second"],
                                            "practice_mode": "contrast"}, headers=h).json()
    out["ax_ans"] = [a1["correct"], a1["counted"], a1["practice_mode"], "kind_label" in a1, "level" in a1, "mastery_score" in a1]
    w = next(i for i in pc["items"] if i["type"] == "word")
    # 그 대조(ㅂ·ㅍ) 하나로만 갈리는 보기를 고른다(혼동 집계가 그 대조가 되게)
    wrong = next(o for o in w["options"] if o != w["target"] and len(L.contrast_of(w["target"], o)) == 1)
    a2 = c.post("/api/listen/answer", json={"stage": 2, "item_key": w["key"], "answer": wrong, "level": w["level"],
                                            "practice_mode": "contrast"}, headers=h)
    out["word_ans"] = [a2.status_code, a2.json()["correct"], a2.json()["counted"], isinstance(a2.json()["contrast"], list)]
    out["n_done_after"] = c.get("/api/listen/practice/contrast", params={"contrast": "onset:ㅂ:ㅍ"}, headers=h).json()["n_done"]
    # 단계 숙달·수준·상태에는 안 들어간다(1단계 행 없음, 2단계는 잠긴 채)
    st = {s["stage"]: s for s in c.get("/api/listen/curriculum", headers=h).json()["stages"]}
    out["stage_after"] = [st[1]["status"], st[1].get("attempts"), st[2]["status"]]
    out["s1_level"] = c.get("/api/listen/stage/1", headers=h).json()["level"]
    # 혼동 기록이 생기면 기본 대조는 그 혼동
    d1 = c.get("/api/listen/practice/contrast", headers=h).json()
    out["contrast_conf"] = d1["source"]
    # 잘못된 조합
    out["bad_pm"] = [
        c.post("/api/listen/answer", json={"stage": 2, "item_key": w["key"], "answer": w["target"], "practice_mode": "dictation"},
               headers=h).status_code,
        c.post("/api/listen/answer", json={"stage": 2, "item_key": w["key"], "answer": w["target"], "practice_mode": "bogus"},
               headers=h).status_code]

    # 받아쓰기
    dc = c.get("/api/listen/practice/dictation", headers=h).json()
    it = dc["items"][0]
    a3 = c.post("/api/listen/answer", json={"stage": 3, "item_key": it["key"], "answer": "", "practice_mode": "dictation"},
                headers=h).json()
    out["dict"] = [len(dc["items"]), all(i["stage"] == 3 for i in dc["items"]), a3["correct"], a3["counted"], "word_feedback" in a3]
    dc2 = c.get("/api/listen/practice/dictation", headers=h).json()
    out["dict_recent_last"] = it["id"] not in [i["id"] for i in dc2["items"][:5]]

    # 소음 속 문장 이어 듣기: 연습 전용 계단
    ne = c.get("/api/listen/practice/noise_endless", headers=h).json()
    s4 = ne["items"][0]
    out["ne_nosnr"] = c.post("/api/listen/answer", json={"stage": 4, "item_key": s4["key"], "answer": s4["text"],
                                                         "practice_mode": "noise_endless"}, headers=h).status_code
    a4 = c.post("/api/listen/answer", json={"stage": 4, "item_key": s4["key"], "answer": s4["text"], "snr_db": ne["next_db"],
                                            "condition": "ao", "practice_mode": "noise_endless"}, headers=h).json()
    ne2 = c.get("/api/listen/practice/noise_endless", headers=h).json()
    st4 = c.get("/api/listen/stage/4", headers=h).json()
    out["ne"] = [ne["next_db"], a4["correct"], a4["stair"]["practice_ao"]["next_db"], a4["next_condition"],
                 ne2["stair"]["practice_ao"]["n_trials"], ne2["next_db"], st4["stair"]["ao"]["n_trials"], st4["n_done"]]

    # 상황별 대화 듣기
    pl = c.get("/api/listen/practice/scenario/places", headers=h).json()["places"]
    out["places"] = [len(pl), min(p["n"] for p in pl)]
    out["sc_noplace"] = c.get("/api/listen/practice/scenario", headers=h).status_code
    out["sc_unknown"] = c.get("/api/listen/practice/scenario", params={"place": "우주"}, headers=h).status_code
    sc = c.get("/api/listen/practice/scenario", params={"place": "home"}, headers=h).json()
    ci = sc["items"][0]
    a5 = c.post("/api/listen/answer", json={"stage": 5, "item_key": ci["key"], "choice": 0, "condition": "quiet",
                                            "practice_mode": "scenario"}, headers=h).json()
    out["sc"] = [len(sc["items"]), all("answer" not in i for i in sc["items"]), all(i["stage"] == 5 for i in sc["items"]),
                 a5["counted"], a5["answer"] == L.CONVO_BY_ID[ci["id"]]["answer"], sc["noise_snr_db"]]

    # 듣기 조건 고르기
    cp = c.get("/api/listen/practice/conditions", params={"cond": "phone"}, headers=h).json()
    cn = c.get("/api/listen/practice/conditions", params={"cond": "noise", "noise": "ssn"}, headers=h).json()
    out["cond"] = [cp["cond"], len(cp["items"]), {i["cond"] for i in cp["items"]} == {"phone"},
                   sorted({i["noise"] for i in cn["items"]}), cn["snr_db"],
                   c.get("/api/listen/practice/conditions", params={"cond": "space"}, headers=h).status_code,
                   c.get("/api/listen/practice/conditions", params={"cond": "noise", "noise": "talker2"}, headers=h).status_code,
                   c.get("/api/listen/practice/conditions", headers=h).json()["cond"]]
    ni = cn["items"][0]
    a6 = c.post("/api/listen/answer", json={"stage": 3, "item_key": ni["key"], "answer": ni["text"], "condition": "noise",
                                            "noise": "ssn", "snr_db": cn["snr_db"], "practice_mode": "conditions"}, headers=h).json()
    out["cond_ans"] = [a6["correct"], a6["counted"],
                       c.post("/api/listen/answer", json={"stage": 3, "item_key": ni["key"], "answer": "",
                                                          "practice_mode": "conditions"}, headers=h).status_code,
                       c.post("/api/listen/answer", json={"stage": 3, "item_key": ni["key"], "answer": "", "condition": "noise",
                                                          "practice_mode": "conditions"}, headers=h).status_code]
    row = sql("select condition, noise, snr_db, session from listen_attempts where item_key = ? and session = 'practice:conditions'",
              ni["key"])[0]
    out["cond_row"] = list(row)

    # 요약: 혼동·소리 구별·연습량에 들어가고 훈련 역치에는 안 들어간다
    sm = c.get("/api/listen/summary", headers=h).json()
    out["summary"] = [len(sm["confusions"]) >= 1, sum(k["n"] for k in sm["ax_kinds"]), sm["training"]["n_ao"],
                      sm["practice"]["by_mode"], sm["practice"]["n_noise"], sm["days"][-1]["n"]]

    # 듣기 복습: 어제 틀린 낱말·문장이 오늘 나온다
    out["review_today"] = c.get("/api/listen/review", headers=h).json()["n"]
    shift(1)
    rv = c.get("/api/listen/review", headers=h).json()
    out["review"] = [[x["target"] for x in rv["words"]], [x["id"] for x in rv["sentences"]], rv["n"],
                     all(len(x["options"]) == 4 and x["target"] in x["options"] for x in rv["words"]),
                     [x["stage"] for x in rv["words"]] + [x["stage"] for x in rv["sentences"]]]
    due = c.get("/api/review/due", headers=h).json()
    out["review_due"] = [due["total"], due["listen_count"], due["listen_words"], due["listen_sentences"], due["total_with_listen"]]
    out["today_review_due"] = c.get("/api/listen/today", headers=h).json()["review_due"]
    # 2단계 안의 간격 복습과 같은 기록을 본다
    s2 = c.get("/api/listen/stage/2", headers=h).json()
    out["s2_review_before"] = [i["target"] for i in s2["items"] if i.get("review")]
    rw = rv["words"][0]
    r1 = c.post("/api/listen/answer", json={"stage": 2, "item_key": rw["key"], "answer": rw["target"], "level": rw["level"],
                                            "practice_mode": "review"}, headers=h).json()
    rs = rv["sentences"][0]
    c.post("/api/listen/answer", json={"stage": 3, "item_key": rs["key"], "answer": rs["text"], "practice_mode": "review"}, headers=h)
    out["review_ans"] = [r1["correct"], r1["counted"], r1["practice_mode"]]
    out["review_after1"] = c.get("/api/listen/review", headers=h).json()["n"]
    out["s2_review_after"] = [i["target"] for i in c.get("/api/listen/stage/2", headers=h).json()["items"] if i.get("review")]
    shift(3)
    rv2 = c.get("/api/listen/review", headers=h).json()
    out["review_after3d"] = [[x["target"] for x in rv2["words"]], [x["id"] for x in rv2["sentences"]]]
    c.post("/api/listen/answer", json={"stage": 2, "item_key": rw["key"], "answer": rw["target"], "level": 2,
                                       "practice_mode": "review"}, headers=h)
    c.post("/api/listen/answer", json={"stage": 3, "item_key": rs["key"], "answer": rs["text"], "practice_mode": "review"}, headers=h)
    shift(5)
    out["review_after_two"] = c.get("/api/listen/review", headers=h).json()["n"]

    # 과제: 듣기를 시작한 사용자에게 '소리 듣기 15분'. 오늘 2분 간격 시행 9개(16분)를 넣으면 달성
    uid = sql("select id from users where email = 'lp@example.com'")[0][0]
    t0 = datetime.combine(main._kst_today(), datetime.min.time()) + timedelta(hours=12) - timedelta(hours=9)
    for k in range(9):
        sql("insert into listen_attempts (user_id, stage, mode, item_key, target, correct, session, created_at) "
            "values (?, 3, 'sentence', 's:t001', '창문 좀 열어 주세요.', 1, 'practice:dictation', ?)",
            uid, (t0 + timedelta(minutes=2 * k)).strftime("%Y-%m-%d %H:%M:%S.000000"))
    g = c.get("/api/tasks", headers=h).json()
    lt = next(t for t in g["daily"] if t["key"] == "listen_15")
    out["task"] = [lt["total"], lt["cur"], lt["done"], lt["claimed"], lt["xp"]]
    cl = c.post("/api/tasks/claim", headers=h).json()
    out["claim"] = [k["key"] for k in cl["claimed"]]
    out["tasks_other"] = [t["key"] for t in c.get("/api/tasks", headers=op).json()["daily"]]

    # 분석 탭 요약
    ov = c.get("/api/analysis/overview", headers=h).json()
    out["overview"] = [ov["listen"]["week_minutes"] >= 16, ov["listen"]["ax_n"], ov["listen"]["ax_accuracy"],
                       ov["listen"]["test_srt_db"], ov["listen"]["n_tests"], "has_data" in ov and "weekly" in ov,
                       ov["listen"]["week_days"] >= 1]

    # 소리 교실
    ct = c.get("/api/listen/contrasts", headers=h).json()["kinds"]
    out["contrasts"] = [[k["kind"] for k in ct], all(k["pairs"] for k in ct), sum(len(k["words"]) for k in ct) > 10,
                        all(k["desc"] for k in ct)]

    # 내보내기: 연습 답은 단계 훈련 수에 없고 practice_by_mode에 따로
    os.environ["LIPLAB_PILOT"] = "1"
    os.environ["LIPLAB_PILOT_CODES"] = "ALPHA:train,BETA:control"
    c.post("/api/pilot/join", json={"code": "ALPHA"}, headers=h)
    os.environ["LIPLAB_ADMIN_EMAILS"] = "op@example.com"
    ex = c.get("/api/pilot/export", headers=op).json()
    li = next(p for p in ex["participants"] if p.get("listen"))["listen"]
    out["export"] = [sorted(f"{d['stage']}:{d['mode']}" for d in li["trials_by_stage"]),
                     sorted(f"{d['practice']}:{d['stage']}:{d['mode']}" for d in li["practice_by_mode"]),
                     sum(d["n"] for d in li["practice_by_mode"])]
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


@lru_cache(maxsize=1)
def _run():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", T_DB=f"{d}/t.db", PYTHONDONTWRITEBYTECODE="1",
                   LIPLAB_UNLOCK_ALL="0")
        for k in ("ANTHROPIC_API_KEY", "LIPLAB_PILOT", "LIPLAB_PILOT_CODES", "LIPLAB_ADMIN_EMAILS"):
            env.pop(k, None)
        p = subprocess.run([sys.executable, "-c", _FLOW], cwd=here, env=env, capture_output=True, text=True, timeout=300)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-4000:]}"
    return json.loads(line[len("RESULT "):])


def test_practice_modes_gate():
    r = _run()
    assert r["tasks_before"] == ["review_clear", "read_once", "two_sessions"]      # 듣기를 시작하기 전에는 과제가 없다
    assert r["overview_before"] is None
    assert [m[0] for m in r["modes0"]] == list(L.PRACTICE_KEYS)
    assert all(m[1] is False and m[2] for m in r["modes0"]) and r["locked_get"] == 409
    assert all(r["modes1"]) and r["unknown_mode"] == 404 and r["bad_contrast"] == 400


def test_contrast_mode_records_without_mastery():
    r = _run()
    assert r["contrast_default"] == ["default", "kind:place", 12]
    assert r["contrast"] == ["query", "첫소리 ㅂ·ㅍ", 12, ["ax", "word"], 0]
    assert r["ax_ans"] == [True, False, "contrast", True, False, False]           # 수준·숙달 칸 없음
    assert r["word_ans"] == [200, False, False, True]                              # 잠긴 2단계 문항도 연습으로 받는다
    assert r["n_done_after"] == 2
    assert r["stage_after"] == ["unlocked", None, "locked"] and r["s1_level"] == 1
    assert r["contrast_conf"] == "confusions"
    assert r["bad_pm"] == [400, 400]


def test_dictation_noise_scenario_conditions():
    r = _run()
    assert r["dict"] == [10, True, False, False, True] and r["dict_recent_last"]
    # 연습 계단: +10 dB에서 맞히면 6 dB. 4단계 계단은 그대로(시행 0)
    assert r["ne_nosnr"] == 400
    assert r["ne"] == [10.0, True, 6.0, "practice_ao", 1, 6.0, 0, 0]
    assert r["places"][0] == len(L.SCENES) and r["places"][1] >= 4
    assert r["sc_noplace"] == 400 and r["sc_unknown"] == 404
    assert r["sc"] == [4, True, True, False, True, 10.0]
    assert r["cond"][:3] == ["phone", 10, True] and r["cond"][3] == ["ssn"] and r["cond"][4] == 10.0
    assert r["cond"][5:] == [400, 400, "phone"]
    assert r["cond_ans"] == [True, False, 400, 400]
    assert r["cond_row"] == ["noise", "ssn", 10.0, "practice:conditions"]


def test_summary_counts_practice():
    r = _run()
    conf, ax_n, n_ao, by_mode, n_noise, today_n = r["summary"]
    assert conf and ax_n == 1 and n_ao == 0 and n_noise == 1
    assert by_mode == {"contrast": 2, "dictation": 1, "noise_endless": 1, "scenario": 1, "conditions": 1}
    assert today_n >= 6 + 1                                                       # 점검 7행 + 연습 답


def test_listen_review_flow():
    r = _run()
    assert r["review_today"] == 0                                                 # 오늘 틀린 것은 내일부터
    words, sents, n, opts_ok, stages = r["review"]
    assert len(words) == 1 and len(sents) == 1 and n == 2 and opts_ok and stages == [2, 3]
    assert r["review_due"] == [0, 2, 1, 1, 2] and r["today_review_due"] == 2
    assert r["s2_review_before"] == words                                         # 2단계 안의 복습과 같은 기록
    assert r["review_ans"] == [True, False, "review"]
    assert r["review_after1"] == 0 and r["s2_review_after"] == []                 # 맞히면 사흘 뒤
    assert r["review_after3d"] == [words, sents]
    assert r["review_after_two"] == 0                                             # 두 번 맞히면 빠진다


def test_tasks_overview_contrasts_export():
    r = _run()
    assert r["task"][0] == 15 and r["task"][1] >= 15 and r["task"][2] is True and r["task"][4] == 15
    assert "listen_15" in r["claim"]
    assert "listen_15" not in r["tasks_other"]
    assert r["overview"][0] and r["overview"][1] == 1 and r["overview"][2] == 1.0
    assert r["overview"][3] is None and r["overview"][4] == 0 and r["overview"][5] and r["overview"][6]
    assert r["contrasts"] == [list(L.AX_KIND_LABEL), True, True, True]
    stage_keys, prac_keys, n_prac = r["export"]
    assert stage_keys == ["0:ling"]                                               # 단계 훈련 수에는 점검만(연습 답 없음)
    assert "contrast:1:ax" in prac_keys and "review:2:word_id" in prac_keys and "noise_endless:4:noise" in prac_keys
    assert n_prac >= 6 + 4 + 9


# ── 날짜 경계·처음 사용자·다른 사용자·다시 쓴 답(10/7 검토, docs/review/listen-integration-review-2026-10.md) ──────────

_FLOW2 = r'''
import json, os, sqlite3
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
import main, listen_curriculum as L

def sql(q, *a):
    db = sqlite3.connect(os.environ["T_DB"])
    rows = db.execute(q, a).fetchall()
    db.commit(); db.close()
    return rows

def ts(t):
    return t.strftime("%Y-%m-%d %H:%M:%S.%f")

out = {}
with TestClient(main.app) as c:
    def reg(email, name):
        r = c.post("/api/auth/register", json={"email": email, "username": name, "password": "pw-123456",
                                               "agree_terms": True, "age_confirmed": True})
        return {"Authorization": "Bearer " + r.json()["access_token"]}
    ha, hb = reg("pa@example.com", "pa1"), reg("pb@example.com", "pb1")
    ua = sql("select id from users where email = 'pa@example.com'")[0][0]
    ub = sql("select id from users where email = 'pb@example.com'")[0][0]

    # 처음 사용자(B): 오늘의 듣기는 소리 확인 한 블록, 연습 문항은 409, 복습·과제·분석에는 듣기가 없다
    tb = c.get("/api/listen/today", headers=hb).json()
    out["first_today"] = [[b["mode"] for b in tb["blocks"]], tb["done_today"], tb["review_due"], tb["target_min"]]
    out["first_other"] = [c.get("/api/listen/practice/dictation", headers=hb).status_code,
                          c.get("/api/listen/review", headers=hb).json()["n"],
                          [t["key"] for t in c.get("/api/tasks", headers=hb).json()["daily"]],
                          c.get("/api/analysis/overview", headers=hb).json()["listen"]]

    # A: 소리 확인 뒤 연습. 단서를 본 뒤 다시 쓴 답(practice: true)은 연습 모드를 붙여도 복습·혼동·연습 계단에 넣지 않는다
    c.post("/api/listen/ling", json={"results": {k: True for k in L.LING_KEYS}, "false_alarms": 0}, headers=ha)
    pc = c.get("/api/listen/practice/contrast", params={"contrast": "onset:ㅂ:ㅍ"}, headers=ha).json()
    w = next(i for i in pc["items"] if i["type"] == "word")
    wrong = next(o for o in w["options"] if o != w["target"])
    r1 = c.post("/api/listen/answer", json={"stage": 2, "item_key": w["key"], "answer": wrong, "level": w["level"],
                                            "practice_mode": "contrast", "practice": True}, headers=ha).json()
    ne = c.get("/api/listen/practice/noise_endless", headers=ha).json()
    s4 = ne["items"][0]
    r2 = c.post("/api/listen/answer", json={"stage": 4, "item_key": s4["key"], "answer": "", "snr_db": ne["next_db"],
                                            "practice_mode": "noise_endless", "practice": True}, headers=ha).json()
    dc = c.get("/api/listen/practice/dictation", headers=ha).json()
    c.post("/api/listen/answer", json={"stage": 3, "item_key": dc["items"][0]["key"], "answer": "", "practice_mode": "dictation"},
           headers=ha)
    sm = c.get("/api/listen/summary", headers=ha).json()
    out["retry"] = [r1["counted"], r2["stair"]["practice_ao"]["n_trials"], sm["confusions"], sm["practice"]["by_mode"],
                    c.get("/api/listen/practice/noise_endless", headers=ha).json()["stair"]["practice_ao"]["n_trials"],
                    sorted({s for (s,) in sql("select session from listen_attempts where user_id = ? and stage in (2, 4)", ua)})]
    sql("update listen_attempts set created_at = datetime(created_at, '-1 days') where user_id = ?", ua)
    rv = c.get("/api/listen/review", headers=ha).json()
    out["retry_review"] = [[x["target"] for x in rv["words"]], len(rv["sentences"])]

    # 다른 사용자(B)에게는 A의 연습이 보이지 않는다
    sb = c.get("/api/listen/summary", headers=hb).json()
    out["isolation"] = [sb["practice"]["by_mode"], sb["confusions"], sum(d["n"] for d in sb["days"]),
                        c.get("/api/listen/review", headers=hb).json()["n"]]

    # 날짜 경계(KST): B의 시행을 어제 23시 59분(KST)에 하나, 오늘 0시 1분부터 2분 간격으로 여덟 개 넣는다(모두 반응 시간 30초).
    # 자정을 가로지르는 2분 간격은 어제·오늘 어느 쪽에도 더하지 않는다. 오늘 = 30초 + 2분 × 7 = 14.5분 → 과제 14 / 15(미달)
    today = main._kst_today()
    start = datetime.combine(today, datetime.min.time()) - timedelta(hours=9)      # 오늘 0시(KST)의 UTC
    def put(t):
        sql("insert into listen_attempts (user_id, stage, mode, item_key, target, correct, rt_ms, session, created_at) "
            "values (?, 3, 'sentence', 's:t001', '창문 좀 열어 주세요.', 1, 30000, 'practice:dictation', ?)", ub, ts(t))
    put(start - timedelta(minutes=1))
    for k in range(8):
        put(start + timedelta(minutes=1 + 2 * k))
    def view():
        s = c.get("/api/listen/summary", headers=hb).json()["days"]
        t = c.get("/api/listen/today", headers=hb).json()["done_today"]
        g = next(x for x in c.get("/api/tasks", headers=hb).json()["daily"] if x["key"] == "listen_15")
        ov = c.get("/api/analysis/overview", headers=hb).json()["listen"]
        return [s[-2]["date"], s[-2]["n"], s[-2]["minutes"], s[-1]["date"], s[-1]["n"], s[-1]["minutes"], t["n"], t["minutes"],
                g["cur"], g["done"], ov["week_minutes"], ov["week_days"]]
    out["boundary"] = view()
    out["boundary_dates"] = [(today - timedelta(days=1)).isoformat(), today.isoformat()]
    # 2분 뒤 한 시행 더 → 16.5분, 과제 달성(세 곳이 같은 분)
    put(start + timedelta(minutes=17))
    out["boundary2"] = view()
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


@lru_cache(maxsize=1)
def _run2():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", T_DB=f"{d}/t.db", PYTHONDONTWRITEBYTECODE="1",
                   LIPLAB_UNLOCK_ALL="0")
        for k in ("ANTHROPIC_API_KEY", "LIPLAB_PILOT", "LIPLAB_PILOT_CODES", "LIPLAB_ADMIN_EMAILS"):
            env.pop(k, None)
        p = subprocess.run([sys.executable, "-c", _FLOW2], cwd=here, env=env, capture_output=True, text=True, timeout=300)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-4000:]}"
    return json.loads(line[len("RESULT "):])


def test_first_user_today_and_gates():
    r = _run2()
    assert r["first_today"] == [["ling"], {"n": 0, "minutes": 0.0}, 0, 15]
    assert r["first_other"] == [409, 0, ["review_clear", "read_once", "two_sessions"], None]


def test_practice_retry_excluded_everywhere():
    """정답 단서를 본 뒤 다시 쓴 답은 practice_mode를 붙여도 session 'practice'로 남아 혼동·복습·연습 계단·모드별 수에 들어가지 않는다."""
    r = _run2()
    counted, stair_n, conf, by_mode, stair_n2, sessions = r["retry"]
    assert counted is False and stair_n == 0 and stair_n2 == 0 and conf == []
    assert by_mode == {"dictation": 1} and sessions == ["practice"]
    assert r["retry_review"] == [[], 1]                                           # 다시 쓴 낱말은 복습에 없고, 받아쓰기 문장만


def test_other_user_isolated():
    r = _run2()
    assert r["isolation"] == [{}, [], 0, 0]


def test_kst_day_boundary_same_minutes_everywhere():
    """요약 days·오늘의 듣기·과제 listen_15·분석 week_minutes가 같은 KST 날짜와 같은 분을 쓴다. 자정을 가로지르는 간격은 어느 날에도 넣지 않는다."""
    r = _run2()
    yday, today = r["boundary_dates"]
    assert r["boundary"] == [yday, 1, 0.5, today, 8, 14.5, 8, 14.5, 14, False, 15.0, 2]
    assert r["boundary2"] == [yday, 1, 0.5, today, 9, 16.5, 9, 16.5, 15, True, 17.0, 2]
