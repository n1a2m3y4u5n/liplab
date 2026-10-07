"""목소리별 피할 문항(docs/listen-voice-contrast-2026-10.md 6절) 테스트.

목록 읽기(없으면 빈 목록), 소리 구별·낱말 고르기 문항의 avoid_voices, 연습·복습·단계 API가 같은 목록을 붙이는지, 저장소 목록의 꼴을 본다.
API는 test_listen_practice.py와 같이 임시 DB·임시 목록을 지정한 별도 프로세스에서 돌리고 결과(JSON)만 본다.
"""
import json
import os
import subprocess
import sys
import tempfile

import listen_curriculum as L

HERE = os.path.dirname(os.path.abspath(__file__))
TRAIN = {"m1", "f1", "m2", "f2"}


def _write(d, voices, name="avoid.json"):
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "voices": voices, "test_voice_report": {"m3": {"컵": [{"against": "곱", "margin": -1.0}]}}},
                  f, ensure_ascii=False)
    return p


def test_missing_or_broken_file_is_empty(monkeypatch, tmp_path):
    monkeypatch.setenv("LISTEN_VOICE_AVOID", str(tmp_path / "none.json"))
    assert L.voice_avoid() == {}
    assert L.avoid_voices_ax("바", "파") == [] and L.avoid_voices_word("바다") == []
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("LISTEN_VOICE_AVOID", str(bad))
    assert L.voice_avoid() == {}
    items = L.ax_items(3, "s", n=12, multi_voice=True)
    assert items and all(it["avoid_voices"] == [] for it in items)
    w = L.word_item("바다", 2, L.word_pool(), "s")
    assert w is None or w["avoid_voices"] == []


def test_read_list_and_lookup(monkeypatch, tmp_path):
    p = _write(str(tmp_path), {
        "f2": {"겁": [{"against": "컵", "margin": -2.1, "set": "word"}], "가": [{"against": "카", "margin": -0.4, "set": "ax"}]},
        "m2": {"짜": [{"against": "자", "margin": -1.5, "set": "ax"}]},
        "f1": {"가": [{"against": "기", "margin": -0.2, "set": "ax"}]},
    })
    monkeypatch.setenv("LISTEN_VOICE_AVOID", p)
    # 소리 구별: 짝의 어느 쪽 클립이든 상대 글에 걸리면 피한다(방향 무관), 다른 짝은 영향 없음
    assert L.avoid_voices_ax("가", "카") == ["f2"] and L.avoid_voices_ax("카", "가") == ["f2"]
    assert L.avoid_voices_ax("자", "짜") == ["m2"]
    assert L.avoid_voices_ax("가", "기") == ["f1"]
    assert L.avoid_voices_ax("가", "까") == []
    # 낱말: 정답 글이 어느 경쟁 글에든 걸린 목소리. 검사 목소리 보고 칸(test_voice_report)은 읽지 않는다
    assert L.avoid_voices_word("겁") == ["f2"] and L.avoid_voices_word("가") == ["f1", "f2"]
    assert L.avoid_voices_word("컵") == []
    # 찾기 키로 맞춘다(구두점·공백 차이 무시)
    assert L.avoid_voices_word(" 겁. ") == ["f2"]


def test_items_carry_avoid_voices(monkeypatch, tmp_path):
    # 모든 짝의 두 글을 f1이, 모든 풀 낱말을 f2가 구별하지 못한다고 둔다
    voices = {"f1": {}, "f2": {}}
    for pr in L.AX_PAIRS:
        voices["f1"].setdefault(pr["a"], []).append({"against": pr["b"], "margin": -1.0, "set": "ax"})
    pool = L.word_pool()
    for w in pool:
        voices["f2"][w] = [{"against": "아무", "margin": -1.0, "set": "word"}]
    monkeypatch.setenv("LISTEN_VOICE_AVOID", _write(str(tmp_path), voices))
    for lv in (1, 2, 3, 4):
        items = L.ax_items(lv, f"s{lv}", n=12, multi_voice=True)
        same = [it for it in items if it["first"] == it["second"]]
        assert same and all(it["avoid_voices"] == ["f1"] for it in items)     # 같음 문항도 그 짝 기준
        # 짝 글(바다·사과 등)이 낱말 풀에도 있어 f2 항목이 있지만, 경쟁 글이 짝의 상대가 아니라 소리 구별에는 붙지 않는다
    ax_a = {pr["a"] for pr in L.AX_PAIRS}     # 짝 글이기도 한 낱말(바다·사과 등)은 그 짝에 실패한 f1도 피한다(정답 글 기준)
    want = lambda w: sorted({"f2"} | ({"f1"} if w in ax_a else set()))
    for lv in (1, 2, 3):
        ws = L.word_items(lv, pool, f"w{lv}", n=10)
        assert ws and all(it["avoid_voices"] == want(it["target"]) for it in ws)
    spec = L.parse_contrast("onset:ㅂ:ㅍ")
    mix = L.contrast_practice_items(spec, pool, "p", n=12)
    assert {("first" in it) for it in mix} == {True, False}
    assert all("f1" in it["avoid_voices"] for it in mix if "first" in it)
    assert all(it["avoid_voices"] == want(it["target"]) for it in mix if "first" not in it)
    # 일반화 검사는 검사 목소리 하나라 붙이지 않는다
    assert all("avoid_voices" not in it for it in L.gen_test_items(L.word_pool(include_gen=True)))


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
    r = c.post("/api/auth/register", json={"email": "va@example.com", "username": "va1", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    c.post("/api/listen/ling", json={"results": {k: True for k in L.LING_KEYS}, "false_alarms": 0}, headers=h)
    s1 = c.get("/api/listen/stage/1", headers=h).json()
    out["s1"] = [it.get("avoid_voices") for it in s1["items"]]
    s2 = c.get("/api/listen/stage/2", headers=h).json()
    out["s2"] = [[it["target"], it.get("avoid_voices")] for it in s2["items"]]
    pc = c.get("/api/listen/practice/contrast", params={"contrast": "onset:ㅂ:ㅍ"}, headers=h).json()
    out["pc"] = [["first" in it, it.get("target"), it.get("avoid_voices")] for it in pc["items"]]
    # 복습: 2단계 낱말을 틀리고 하루 앞으로 옮기면 오늘 복습에 나온다
    it = s2["items"][0]
    wrong = next(o for o in it["options"] if o != it["target"])
    c.post("/api/listen/answer", json={"stage": 2, "item_key": it["key"], "answer": wrong, "level": it["level"],
                                       "practice_mode": "contrast"}, headers=h)
    sql("update listen_attempts set created_at = datetime(created_at, '-1 days')")
    rv = c.get("/api/listen/review", headers=h).json()
    out["review"] = [[x["target"], x.get("avoid_voices")] for x in rv["words"]]
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


def test_api_attaches_avoid_voices():
    voices = {"f1": {}, "m2": {}}
    for pr in L.AX_PAIRS:
        voices["f1"].setdefault(pr["a"], []).append({"against": pr["b"], "margin": -1.0, "set": "ax"})
    for w in L.word_pool():
        voices["m2"][w] = [{"against": "아무", "margin": -1.0, "set": "word"}]
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", T_DB=f"{d}/t.db", PYTHONDONTWRITEBYTECODE="1",
                   LIPLAB_UNLOCK_ALL="0", LISTEN_VOICE_AVOID=_write(d, voices))
        for k in ("ANTHROPIC_API_KEY", "LIPLAB_PILOT", "LIPLAB_PILOT_CODES", "LIPLAB_ADMIN_EMAILS"):
            env.pop(k, None)
        p = subprocess.run([sys.executable, "-c", _FLOW], cwd=HERE, env=env, capture_output=True, text=True, timeout=300)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-4000:]}"
    r = json.loads(line[len("RESULT "):])
    assert r["s1"] and all(a == ["f1"] for a in r["s1"])                           # 단계 레슨(오늘의 듣기도 이 응답을 쓴다)
    ax_a = {pr["a"] for pr in L.AX_PAIRS}
    want = lambda w: sorted({"m2"} | ({"f1"} if w in ax_a else set()))
    assert r["s2"] and all(a == want(t) for t, a in r["s2"])
    assert {f for f, _, _ in r["pc"]} == {True, False}                             # 연습(practice:contrast)
    assert all(a == (["f1"] if f else want(t)) for f, t, a in r["pc"])
    assert r["review"] and all(a == want(t) for t, a in r["review"])             # 복습


def test_repo_avoid_list_shape():
    """저장소 목록: 훈련 목소리만, 글은 소리 구별 글이나 낱말 풀, 경쟁 글이 있고 margin < 0(사전 기준 4절의 실패만)."""
    p = L.VOICE_AVOID_PATH
    if not os.path.exists(p):
        return
    raw = json.load(open(p, encoding="utf-8"))
    assert set(raw["voices"]) <= TRAIN
    assert set(raw.get("test_voice_report") or {}) <= {"m3"}
    texts = {x for pr in L.AX_PAIRS for x in (pr["a"], pr["b"])} | set(L.word_pool())
    for v, d in raw["voices"].items():
        for t, ents in d.items():
            assert t in texts, (v, t)
            assert ents and all(e["against"] and e["margin"] < 0 and e["set"] in ("ax", "word") for e in ents), (v, t)
    # 읽은 결과가 파일과 같다
    os.environ.pop("LISTEN_VOICE_AVOID", None)
    got = L.voice_avoid()
    assert {v: set(d) for v, d in got.items()} == {v: set(d) for v, d in raw["voices"].items()}
