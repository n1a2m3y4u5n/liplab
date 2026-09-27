"""3단계 문장 4지선다 오답 보기(sentence_options.py): 레슨 밖 문장, 음절 수가 가까운 것, 문맥 추론 문장 제외.

예전 보기(같은 레슨의 다른 문장)는 뒤에 주관식으로 나올 문장을 먼저 보여 줬다(그런 문항의 40~56%).
"""
import json
import os
import random
import subprocess
import sys
import tempfile

import curriculum as C
import sentence_options as S


def test_options_exclude_the_lesson_and_match_length():
    lesson = ["아메리카노 한 잔 주세요.", "따뜻한 걸로 할게요.", "여기서 마실게요.", "설탕은 빼주세요.", "영수증 주세요."]
    pool = S.static_pool()
    for target in lesson:
        opts = S.pick_options(target, pool, lesson, rng=random.Random(1))
        assert len(opts) == 3 and not set(opts) & set(lesson), opts
        # 가장 가까운 네 문장 안에서 고른다
        gaps = sorted(abs(S.syllables(p) - S.syllables(target)) for p in pool if p not in lesson)
        assert max(abs(S.syllables(o) - S.syllables(target)) for o in opts) <= gaps[3]


def test_same_sentence_with_other_punctuation_is_not_an_option():
    # '밥 먹었어요.'와 '밥 먹었어요?'는 입모양이 같다
    opts = S.pick_options("밥 먹었어요?", ["밥 먹었어요.", "밥 먹었어요 ?", "물 좀 주세요.", "잘 지냈어요.", "내일 만나요."], [],
                          rng=random.Random(0))
    assert all(S._key(o) != S._key("밥 먹었어요") for o in opts)


def test_pool_has_no_closure_sentences():
    # 문맥 추론 문장이 보기로 먼저 보이면 그쪽 빈칸 답이 샌다
    filled = {S._key(it["display"].replace("___", it["answer"])) for it in C.CLOSURE_ITEMS if "___" in (it.get("display") or "")}
    assert not {S._key(p) for p in S.static_pool()} & filled


_FLOW = r'''
import json
from fastapi.testclient import TestClient
import main
lesson = ["메뉴판 좀 주세요.", "이거 맵나요?", "두 명이에요.", "물 좀 주세요.", "계산해 주세요."]
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "so@example.com", "username": "so1", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    d = c.post("/api/curriculum/sentence-options", headers=h, json={"sentence": lesson[0], "exclude": lesson}).json()
print("RESULT " + json.dumps({"options": d.get("options"), "lesson": lesson}, ensure_ascii=False))
'''


def test_sentence_options_api():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1")
        p = subprocess.run([sys.executable, "-c", _FLOW], cwd=here, env=env, capture_output=True, text=True, timeout=240)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])
    assert len(r["options"]) == 3 and not set(r["options"]) & set(r["lesson"]), r
