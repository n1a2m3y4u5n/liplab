"""대화 듣기 생성 문항(listen_convo_gen, docs/listen-convo-tts-2026-10.md) 시험. 유료 API·합성기 없이 돈다.
순수 함수는 바로 보고, 생성·서빙·채점 흐름은 합성(sound_service.generate)을 가짜로 바꾼 별도 프로세스에서 본다."""
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from contextlib import asynccontextmanager
from functools import lru_cache

import pytest

import listen_convo_gen as G
import listen_curriculum as L
import sound_clips as S

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(HERE, "..", "scripts", "convo_tts", "fixture_items.json")


def _fixture():
    return json.load(open(FIXTURE, encoding="utf-8"))["items"]


@pytest.fixture(autouse=True)
def _pre_expand_convo(monkeypatch):
    """대리 문항 파일은 10/15 측정 때 그대로 둔다. 그 가운데 일부를 검수해 미리 합성 대화(c35~c58)로 넣었으므로, 이 시험들은 확대 전
    대화 목록(c01~c34)을 기준으로 본다(넣은 대사는 '이미 있는 글'이라 생성 점검이 버린다. 그것은 test_known_text_after_expand가 본다)."""
    monkeypatch.setattr(L, "CONVO_ITEMS", [c for c in L.CONVO_ITEMS if int(c["id"][1:]) <= 34])
    monkeypatch.setattr(G, "_FORBIDDEN_KEYS", None)


def test_known_text_after_expand(monkeypatch):
    """확대 뒤 목록에서는 미리 합성 대화로 넣은 대사를 생성 문항으로 다시 만들지 않는다."""
    monkeypatch.undo()
    G._FORBIDDEN_KEYS = None
    it = next(x for x in _fixture() if x["line"].startswith("비가 오면 공원"))     # c56과 같은 대사
    assert G.validate_item(it, it["scene"])[1] == "known_text"
    G._FORBIDDEN_KEYS = None


def test_fixture_items_pass_rules():
    """대리 문항 24개는 모두 점검을 통과하고(측정 전제), 장면마다 3개다."""
    items = _fixture()
    assert len(items) == 24
    for it in items:
        ok, why = G.validate_item(it, it["scene"])
        assert ok is not None, (it["line"], why)
        assert ok["answer"] == it["answer"] and ok["place"] == it["place"]
    by = {}
    for it in items:
        by[it["scene"]] = by.get(it["scene"], 0) + 1
    assert by == {k: 3 for k in G.scene_keys()}


def test_validate_rejects():
    base = dict(_fixture()[0])
    sc = base["scene"]

    def bad(**kw):
        return G.validate_item({**base, **kw}, sc)[1]

    assert bad(line="오늘은 예약이 다 차서 내일 10시에 오셔야 해요.") == "non_hangul"       # 숫자
    assert bad(line="OK 내일 오전 열 시에 오세요.") == "non_hangul"
    assert bad(options=["오늘 오후", "내일 오전 열 시", "내일 오전 열 시", "모레 오전"]) == "dup_options"
    assert bad(answer=3) == "answer_not_heard"                     # '모레 오전'은 들은 말에 없다
    assert bad(answer=7) == "bad_answer" and bad(answer="x") == "bad_answer"
    assert bad(options=["a"]) == "missing_fields"
    assert bad(paraphrase=base["line"]) == "same_paraphrase"
    assert bad(line="네 시요.") == "length"
    assert bad(line="귀가 아파서 내일 오전 열 시에 오셔야 해요.") == "gen_word"            # 일반화 검사 낱말
    t = L.TEST_FORMS["A"][0]
    assert G.validate_item({**base, "line": t, "options": base["options"]}, sc)[1] in ("known_text", "answer_not_heard")
    c = L.CONVO_ITEMS[0]
    assert G.validate_item({"line": c["line"], "paraphrase": c["paraphrase"] + " 네.", "question": c["question"],
                            "options": c["options"], "answer": c["answer"]}, "clinic")[1] == "known_text"
    assert G.validate_item(base, "nowhere")[1] == "bad_input"
    # 장소가 장면에 없으면 장면의 첫 장소로 둔다
    assert G.validate_item({**base, "place": "우주"}, sc)[0]["place"] == L.SCENES[0]["places"][0]


def test_mix_and_ids():
    st = [{"key": f"c:{i}"} for i in range(6)]
    gen = [{"key": "g:a"}, {"key": "g:b"}]
    assert [x["key"] for x in G.mix(st, gen)] == ["c:0", "g:a", "c:1", "g:b", "c:2", "c:3", "c:4", "c:5"]
    assert [x["key"] for x in G.mix(st, gen, keep_len=True)] == ["c:0", "g:a", "c:1", "g:b", "c:2", "c:3"]
    assert G.mix(st, []) == st
    assert G.item_id("내일 오전 열 시에 오세요.") == G.item_id("내일 오전 열 시에 오세요") and G.item_id("가").startswith("g")
    assert G.scene_for("병원") == "clinic" and G.scene_for("clinic") == "clinic" and G.scene_for("우주") is None


def test_avoid_from_list_heard_texts_only(tmp_path, monkeypatch):
    """피하기 목록은 소리로 들려주는 글(대사·바꾼 말)에만 쓴다. 글로만 보이는 보기 낱말이 목록에 있어도 목소리를 피하지 않는다."""
    it = _fixture()[2]                                  # 보기에 신분증·통장
    p = tmp_path / "avoid.json"
    p.write_text(json.dumps({"voices": {
        "f2": {"신분증": [{"against": "신문증"}]},                 # 보기 낱말(글로만 보임)
        "m1": {o: [{"against": "x"}] for o in it["options"]},    # 보기 넷 모두
        "m2": {it["paraphrase"]: [{"against": "x"}]},             # 들려주는 바꾼 말
        "f1": {"통장": []}}}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("LISTEN_VOICE_AVOID", str(p))
    assert G.avoid_from_list(it, ["m1", "f1", "m2", "f2"]) == ["m2"]
    assert G.HEARD_FIELDS == ("line", "paraphrase")
    # 10/15 측정에서 버려졌던 문항(보기 '서랍'이 네 목소리 목록에 있음)도 지금 규칙으로는 피할 목소리가 없다
    monkeypatch.delenv("LISTEN_VOICE_AVOID")
    laundry = next(x for x in _fixture() if x["line"].startswith("빨래는"))
    assert G.avoid_from_list(laundry, ["m1", "f1", "m2", "f2"]) == []


def test_repo_avoid_list_has_no_sentence_keys():
    """저장소 목록의 키는 낱말·음절뿐이라 대화 대사에는 걸리지 않는다(바뀌면 이 시험이 알린다)."""
    av = L.voice_avoid()
    assert av and all(" " not in k and len(k) <= 4 for d in av.values() for k in d)
    heard = {S.normalize_text(c[f]) for c in L.CONVO_ITEMS for f in G.HEARD_FIELDS}
    assert not heard & {k for d in av.values() for k in d}


def _fake_env(tmp, monkeypatch, reject=()):
    """합성을 가짜로: 캐시에 빈 파일과 목록 항목을 남긴다. reject의 (목소리, 글)은 게이트 탈락으로 None."""
    import sound_service
    monkeypatch.setenv("LIPLAB_LISTEN_GEN", "1")
    monkeypatch.setenv("LIPLAB_SOUND_DYNAMIC", "1")
    monkeypatch.setenv("LIPLAB_SOUND_CACHE_DIR", str(tmp))
    monkeypatch.setenv("LIPLAB_LISTEN_GEN_FIXTURE", FIXTURE)
    monkeypatch.setattr(sound_service, "dynamic_enabled", lambda: True)
    monkeypatch.setattr(sound_service, "_index", None, raising=False)
    # 고정 목록의 클립은 비운다(목소리만 남김). 대리 문항 일부가 10/15 장면 확대로 미리 합성돼 있어, 비우지 않으면 합성 없이 '있음'이 된다
    real = sound_service.manifest()
    empty = {**real, "clips": {}}
    monkeypatch.setattr(sound_service, "manifest", lambda: empty)
    calls = []

    def gen(text, voice):
        calls.append((voice, text))
        if (voice, text) in reject:
            return None
        key = S.normalize_text(text)
        clip = {"id": S.clip_id(key, voice), "ms": 1000, "syl": None, "text": text}
        sound_service.cache_store(key, voice, clip, {"ogg": b"x", "m4a": b"y"})
        return {"key": key, **clip}

    monkeypatch.setattr(sound_service, "generate", gen)
    G.reset_cache()
    return calls


@asynccontextmanager
async def _slot():
    yield


def test_produce_ready_and_avoid(tmp_path, monkeypatch):
    it = _fixture()[3]                                  # food 첫 문항
    calls = _fake_env(tmp_path, monkeypatch, reject={("m2", it["paraphrase"])})
    rec = asyncio.run(G.produce("food", _slot))
    assert rec["status"] == "ready" and rec["avoid_voices"] == ["m2"] and rec["line"] == it["line"]
    # 검사 목소리(m3)는 합성하지 않는다. m2는 대사 뒤 바꾼 말에서 떨어져 거기서 멈춘다
    assert {v for v, _ in calls} == {"m1", "f1", "m2", "f2"} and len(calls) == 8
    gid = G.item_id(it["line"])
    assert G.lookup(gid)["answer"] == it["answer"]
    got = G.ready_items("food")
    assert [g["key"] for g in got] == [f"g:{gid}"] and got[0]["avoid_voices"] == ["m2"] and "answer" not in got[0]
    assert got[0]["generated"] is True
    # 같은 대사는 다시 합성하지 않는다(다음 대리 문항으로 넘어간다)
    rec2 = asyncio.run(G.produce("food", _slot))
    assert rec2["line"] == _fixture()[4]["line"]
    # 저장소는 파일에 남아 다시 읽힌다
    G.reset_cache()
    assert G.lookup(gid)["line"] == it["line"]
    st = G.status()
    assert st["scenes"]["food"]["ready"] == 2 and st["attempts_today"]["food"] == 2


def test_produce_rejects_when_few_voices(tmp_path, monkeypatch):
    it = _fixture()[0]
    _fake_env(tmp_path, monkeypatch, reject={("m1", it["line"]), ("f1", it["line"]), ("m2", it["line"])})
    rec = asyncio.run(G.produce("clinic", _slot))
    assert rec["status"] == "rejected" and rec["reason"] == "voices"
    assert G.lookup(G.item_id(it["line"])) is None and G.ready_items("clinic") == []


def test_need_respects_pool_and_cap(tmp_path, monkeypatch):
    _fake_env(tmp_path, monkeypatch)
    monkeypatch.setenv("LIPLAB_LISTEN_GEN_POOL", "1")
    assert G._need("transit")
    asyncio.run(G.produce("transit", _slot))
    assert not G._need("transit")                       # 목표 1개 채움
    monkeypatch.setenv("LIPLAB_LISTEN_GEN_POOL", "6")
    monkeypatch.setenv("LIPLAB_LISTEN_GEN_DAILY", "1")
    assert not G._need("transit")                       # 오늘 시도 상한
    monkeypatch.setenv("LIPLAB_LISTEN_GEN", "0")
    assert not G._need("home") and G.ready_items("transit") == []


def test_ready_items_drop_missing_sound(tmp_path, monkeypatch):
    """캐시에서 소리가 지워져 쓸 목소리가 둘 미만이 되면 내지 않는다."""
    import sound_service
    _fake_env(tmp_path, monkeypatch)
    rec = asyncio.run(G.produce("home", _slot))
    assert rec["status"] == "ready"
    for v in ("m1", "f1", "m2"):
        clip = sound_service.find(rec["line"], v)[0]
        os.remove(os.path.join(str(tmp_path), clip["id"] + ".ogg"))
    assert G.ready_items("home") == []


# ── API 흐름(가짜 합성) ───────────────────────────────────────────────

_FLOW = r'''
import json, os, time
from fastapi.testclient import TestClient
import sound_clips as S, sound_service, listen_curriculum as L

def gen(text, voice):
    key = S.normalize_text(text)
    clip = {"id": S.clip_id(key, voice), "ms": 1000, "syl": None, "text": text}
    sound_service.cache_store(key, voice, clip, {"ogg": b"x", "m4a": b"y"})
    return {"key": key, **clip}

sound_service.dynamic_enabled = lambda: True
sound_service.generate = gen
import main
out = {}
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "cg@example.com", "username": "cg1", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    c.post("/api/listen/ling", json={"results": {k: True for k in L.LING_KEYS}, "false_alarms": 0}, headers=h)
    s0 = c.get("/api/listen/practice/scenario", params={"place": "shop"}, headers=h).json()
    out["first"] = [len(s0["items"]), sum(1 for i in s0["items"] if i.get("generated"))]
    for _ in range(100):
        st = c.get("/api/listen/convo-gen/status", headers=h).json()
        if (st["scenes"].get("shop") or {}).get("ready") == 3 and not st["running"]:
            break
        time.sleep(0.05)
    out["status"] = [st["enabled"], st["scenes"].get("shop"), st["attempts_today"].get("shop")]
    s1 = c.get("/api/listen/practice/scenario", params={"place": "shop"}, headers=h).json()
    s1b = c.get("/api/listen/practice/scenario", params={"place": "마트"}, headers=h).json()
    out["by_place"] = [len(s1b["items"]), sum(1 for i in s1b["items"] if i.get("generated"))]
    gens = [i for i in s1["items"] if i.get("generated")]
    out["mixed"] = [len(s1["items"]), len(gens), [i["key"][:2] for i in s1["items"][:4]], all("answer" not in i for i in gens)]
    g = gens[0]
    a = c.post("/api/listen/answer", json={"stage": 5, "item_key": g["key"], "choice": 0, "practice_mode": "scenario"},
               headers=h).json()
    out["ans_practice"] = [a["correct"], a["generated"], a["line"] == g["line"], a["counted"]]
    # 5단계: 생성 문항은 8개 중 2개까지, 답은 숙달에 넣지 않는다
    s5 = c.get("/api/listen/stage/5", headers=h).json()
    g5 = [i for i in s5["items"] if i.get("generated")]
    out["stage5"] = [len(s5["items"]), len(g5)]
    a5 = c.post("/api/listen/answer", json={"stage": 5, "item_key": g5[0]["key"], "choice": 0}, headers=h).json()
    st5 = next(i for i in s5["items"] if not i.get("generated"))
    a6 = c.post("/api/listen/answer", json={"stage": 5, "item_key": st5["key"], "choice": 0}, headers=h).json()
    out["stage5_ans"] = [a5["counted"], a5.get("generated"), a6["counted"]]
    out["bad_key"] = c.post("/api/listen/answer", json={"stage": 5, "item_key": "g:nope", "choice": 0}, headers=h).status_code
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


@lru_cache(maxsize=1)
def _run():
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1", LIPLAB_UNLOCK_ALL="1",
                   LIPLAB_LISTEN_GEN="1", LIPLAB_SOUND_DYNAMIC="1", LIPLAB_SOUND_CACHE_DIR=f"{d}/cache",
                   LIPLAB_LISTEN_GEN_FIXTURE=FIXTURE)
        env.pop("ANTHROPIC_API_KEY", None)
        p = subprocess.run([sys.executable, "-c", _FLOW], cwd=HERE, env=env, capture_output=True, text=True, timeout=300)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-4000:]}"
    return json.loads(line[len("RESULT "):])


def test_api_flow_generated_items():
    r = _run()
    full = json.loads(subprocess.run([sys.executable, "-c", "import json, listen_curriculum as L; print(json.dumps([c['place'] for c in L.CONVO_ITEMS], ensure_ascii=False))"],
                                     cwd=HERE, capture_output=True, text=True).stdout)   # 확대 뒤 목록(서버와 같은 것)
    # 대리 문항 가운데 가게·은행·우체국 셋은 확대 문항(c44~c46)과 대사·바꾼 말이 달라 생성 점검을 통과한다(다른 장면은 일부가 확대 문항과 같다)
    food = sum(1 for p in full if p in ("은행", "마트", "미용실", "가게", "우체국"))
    n_sik = sum(1 for p in full if p == "마트")
    assert r["first"] == [food, 0]                               # 처음에는 준비된 생성 문항이 없다(응답은 기다리지 않는다)
    assert r["status"] == [True, {"ready": 3, "rejected": 0, "pending": 0}, 3]   # 대리 문항이 다 떨어지면 멈춘다
    assert r["mixed"][0] == food + 3 and r["mixed"][1] == 3 and r["mixed"][2] == ["c:", "g:", "c:", "g:"] and r["mixed"][3]
    assert r["by_place"] == [n_sik + 3, 3]                            # 장소 이름(마트)도 그 장면의 생성 문항을 받는다
    assert r["ans_practice"] == [True, True, True, False]
    assert r["stage5"] == [8, 2]
    assert r["stage5_ans"] == [False, True, True]
    assert r["bad_key"] == 400


def test_off_by_default(tmp_path, monkeypatch):
    """켜지 않으면(기본) 생성 문항을 내지도 만들지도 않는다. 합성만 켜고 생성을 안 켜도 같다."""
    _fake_env(tmp_path, monkeypatch)
    asyncio.run(G.produce("work", _slot))
    monkeypatch.delenv("LIPLAB_LISTEN_GEN")
    assert not G.enabled() and G.ready_items("work") == [] and not G._need("work")
    assert G.status()["enabled"] is False
