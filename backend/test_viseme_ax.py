"""1단계 '같은지 다른지'(AX) 문항(docs/mastery-ewma.md 11절, A0(2)): 짝 정답·제외 규칙(curriculum.ax_pair)과 채점 기록
(/api/curriculum/recognition-ax). AX 답은 시행 기록(item_type 'viseme_ax', 보기 포함)에만 남고 1단계 숙달에는 들어가지 않는다.
기록 흐름은 임시 DB를 쓰는 별도 프로세스에서 돈다.
"""
import asyncio
import json
import math
import os
import re
import subprocess
import sys
import tempfile

import curriculum as cur
import engine

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def test_answer_key_from_group_membership():
    key = lambda a, b: (cur.ax_pair(a, b) or {}).get("same")
    assert key("바", "마") is True        # 입술 닫힘끼리
    assert key("바", "아") is False       # 입술 닫힘 대 첫소리 없음
    assert key("다", "가") is True        # 입 안쪽끼리(치경·연구개)
    assert key("하", "카") is True        # 성문·연구개, 둘 다 150ms
    assert key("다", "바") is False       # 입 안쪽 대 입술
    assert key("오", "우") is True and key("아", "이") is False
    assert cur.ax_pair("다", "가")["inside"] is True and cur.ax_pair("바", "마")["inside"] is False
    assert cur.ax_pair("마", "바")["groups"] == [1, 1]


def test_ambiguous_and_invalid_pairs_are_rejected():
    for a, b in [("다", "자"), ("가", "차"), ("다", "아"), ("하", "아"), ("아", "어"), ("바", "버"),   # 거리로 애매
                 ("자", "차"), ("아", "애"), ("바", "파"),                                          # 길이로 갈리는 같음
                 ("다", "고"), ("밥", "맙"), ("와", "오"), ("다", "다"), ("라", "다"), ("A", "다"), ("다가", "다")]:
        assert cur.ax_pair(a, b) is None, (a, b)


def test_excluded_list_matches_frontend():
    """AX_EXCLUDED_GROUP_PAIRS는 화면(visemeAx.js)이 화자 7명 거리로 다시 계산해 확인하는 목록과 같아야 한다."""
    src = open(os.path.join(ROOT, "frontend/src/lib/visemeAx.js"), encoding="utf-8").read()
    body = re.search(r"AX_EXCLUDED_GROUP_PAIRS = \[(.*)\]\n", src).group(1)
    js = {frozenset(None if x.strip() == "null" else int(x) for x in m.split(","))
          for m in re.findall(r"\[([^\[\]]+)\]", body)}
    assert js == set(cur.AX_EXCLUDED_GROUP_PAIRS)


def test_kept_pairs_are_clear_on_default_avatar():
    """기본 화자 입모양 표(scripts/viseme_shapes.json, 화면 visemeShapes.js에서 내보냄)에서 낼 수 있는 짝은 같음이면 0.2 미만,
    다름이면 0.3 이상이다(가상 화자 6명까지 넣은 확인은 visemeAx.test.mjs)."""
    shapes = json.load(open(os.path.join(ROOT, "scripts/viseme_shapes.json"), encoding="utf-8"))["blendshapes"]

    def dist(ga, gb):
        A, B = shapes[str(ga or 15)], shapes[str(gb or 15)]
        return math.sqrt(sum((A.get(k, 0) - B.get(k, 0)) ** 2 for k in set(A) | set(B)))

    kept = [cur.ax_pair(a, b) for a, b in cur.ax_candidates()]
    kept = [p for p in kept if p]
    assert len(cur.ax_candidates()) == 290 and len(kept) == 166
    for p in kept:
        d = dist(*p["groups"])
        assert (d < 0.2) if p["same"] else (d >= 0.3), (p, d)
    cells = {(p["inside"], p["same"]) for p in kept}
    assert cells == {(True, True), (True, False), (False, True), (False, False)}


def test_duration_table_matches_engine():
    """AX_ONSETS·AX_VOWELS의 길이는 엔진이 실제로 내는 프레임 길이와 같다('같음' 짝을 길이로 가르지 못하게 쓰는 값)."""
    for a, b in cur.ax_candidates():
        for syl in (a, b):
            cho, jung = cur._ax_split(syl)
            frames = asyncio.run(engine.text_to_visemes(syl))
            if cho == "ㅇ":
                assert [f["duration_ms"] for f in frames] == [cur.AX_VOWELS[jung][1]], syl
            else:
                assert [f["viseme"] for f in frames] == [cur.AX_ONSETS[cho][0], cur.AX_VOWELS[jung][0]], syl
                assert [f["duration_ms"] for f in frames] == [cur.AX_ONSETS[cho][1], cur.AX_VOWELS[jung][1]], syl


_FLOW = r'''
import json, asyncio, datetime as dt
from fastapi.testclient import TestClient
import main
from database import AsyncSessionLocal, TrialAttempt, StageProgress
from sqlalchemy import select
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "ax@example.com", "username": "axu", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    post = lambda body: c.post("/api/curriculum/recognition-ax", json=body, headers=h)
    res = {
        "same_ok": post({"a": "다", "b": "가", "chosen": "same", "options": ["same", "different"]}).json(),
        "diff_wrong": post({"a": "바", "b": "아", "chosen": "same", "options": ["different", "same"]}).json(),
        "no_opts": post({"a": "오", "b": "우", "chosen": "same", "options": ["same", "x"]}).json(),
        "ambiguous": post({"a": "다", "b": "아", "chosen": "same"}).status_code,
        "bad_choice": post({"a": "다", "b": "가", "chosen": "maybe"}).status_code,
        "rec": c.post("/api/curriculum/recognition", json={"viseme_id": 1, "chosen_id": 1}, headers=h).json(),
    }
    async def rows():
        async with AsyncSessionLocal() as db:
            tr = (await db.execute(select(TrialAttempt).order_by(TrialAttempt.id))).scalars().all()
            sp = (await db.execute(select(StageProgress).where(StageProgress.stage == 1))).scalars().all()
            return ([{"stage": t.stage, "type": t.item_type, "target": t.target, "chosen": t.chosen, "correct": t.correct,
                      "options": t.options} for t in tr], [{"attempts": s.attempts, "correct": s.correct} for s in sp])
    res["trials"], res["sp"] = asyncio.run(rows())
    today = (dt.datetime.utcnow() + dt.timedelta(hours=9)).date().isoformat()
    res["acts"] = c.get("/api/calendar/activities", params={"tz_offset_min": -540}, headers=h).json().get(today)
    res["eval"] = c.get("/api/eval/summary", headers=h).json().get("by_item_type")
    print("RESULT " + json.dumps(res, ensure_ascii=False))
'''


def test_ax_answers_are_recorded_but_not_counted_toward_mastery():
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1",
                   LIPLAB_UNLOCK_ALL="1")
        env.pop("ANTHROPIC_API_KEY", None)
        p = subprocess.run([sys.executable, "-c", _FLOW], cwd=HERE, env=env, capture_output=True, text=True, timeout=240)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])
    assert r["same_ok"]["correct"] is True and r["same_ok"]["answer"] == "same" and r["same_ok"]["inside"] is True
    assert r["same_ok"]["xp_gained"] > 0
    assert r["diff_wrong"]["correct"] is False and r["diff_wrong"]["answer"] == "different"
    assert r["no_opts"]["correct"] is True
    assert r["ambiguous"] == 400 and r["bad_choice"] == 400
    assert "same_cluster" not in r["rec"]   # 나올 수 없던 '같아 보이는 무리' 필드는 뺐다
    ax = [t for t in r["trials"] if t["type"] == "viseme_ax"]
    assert [(t["stage"], t["target"], t["chosen"], t["correct"]) for t in ax] == [
        (1, "다/가", "same", True), (1, "바/아", "same", False), (1, "오/우", "same", True)]
    assert [t["options"] for t in ax] == [["same", "different"], ["different", "same"], None]
    # 1단계 숙달에는 인지퀴즈 1번만 들어간다(AX 3번은 빠짐)
    assert r["sp"] == [{"attempts": 1, "correct": 1}]
    rows = {x["kind"]: x for x in r["acts"]}
    assert rows["viseme_ax"]["n"] == 3 and rows["viseme_ax"]["label"] == "독화 · 입모양 같은지 다른지"
    assert rows["viseme_ax"]["route"] == "/learn/viseme"
    by = {x["item_type"]: x for x in r["eval"]}
    assert by["viseme_ax"]["n"] == 3 and by["viseme_ax"]["label"] == "입모양 같은지 다른지"
