"""뜻 없는 말 짝 맞추기(nonsense_words.py, C10): 생성 규칙, 얼려 둔 목록 재현, 실제 낱말 빼기, 회차 규칙, API 기록 경로."""
import json
import os
import subprocess
import sys
import tempfile
from itertools import combinations

import pytest

import nonsense_words as nw
from engine import to_pronounced_syllables


DATA = nw.load()
ALL_TRAIN = [w["word"] for s in DATA["sets"] for w in s["words"]]
ALL_HELD = [w for lst in DATA["heldout"] for w in lst]


# ── 생성 규칙 ────────────────────────────────────────────────────────

def test_frozen_lists_regenerate_exactly():
    # 얼려 둔 wordfreq 목록과 저장소 낱말로 다시 만들면 같은 결과(wordfreq가 없는 환경에서도 재현)
    again = nw.generate(nw.repo_real_words() | set(DATA["excluded_by_wordfreq"]), DATA["seed"])
    assert again["sets"] == DATA["sets"] and again["heldout"] == DATA["heldout"]


def test_wordfreq_list_matches_installed_dictionary():
    hits = nw.wordfreq_hits(nw.candidates())
    if hits is None:
        pytest.skip("wordfreq 없음")
    assert hits == DATA["excluded_by_wordfreq"]


def test_sizes_and_unique():
    assert len(DATA["sets"]) == nw.SET_COUNT and all(len(s["words"]) == nw.SET_SIZE for s in DATA["sets"])
    assert len(DATA["heldout"]) == nw.HELDOUT_LISTS and all(len(l) == nw.HELDOUT_SIZE for l in DATA["heldout"])
    assert len(set(ALL_TRAIN + ALL_HELD)) == len(ALL_TRAIN) + len(ALL_HELD)
    assert [s["id"] for s in DATA["sets"]] == [f"ns{i:02d}" for i in range(1, nw.SET_COUNT + 1)]


def test_cvcvc_shape_from_inventory():
    for w in ALL_TRAIN + ALL_HELD:
        assert len(w) == 2 and all("가" <= ch <= "힣" for ch in w)
        c1, v1, c2, v2, c3 = nw.parts(w)
        assert c1 in nw._ONSETS and c2 in nw._ONSETS and c3 in nw._CODAS
        assert v1 in nw._VOWELS and v2 in nw._VOWELS
        assert nw.compose(c1, v1, c2, v2, c3) == w


def test_avatar_says_it_as_written():
    # 첫 음절에 받침이 없어 발음 규칙이 걸리지 않는다: 엔진 발음열 = 철자
    for w in ALL_TRAIN + ALL_HELD:
        c1, v1, c2, v2, c3 = nw.parts(w)
        assert [tuple(s) for s in to_pronounced_syllables(w)] == [(c1, v1, ""), (c2, v2, c3)]


def test_no_real_words():
    real = nw.repo_real_words() | set(DATA["excluded_by_wordfreq"]) | set(nw.MANUAL_EXCLUDED)
    assert not (set(ALL_TRAIN + ALL_HELD) & real)
    # 저장소 단어 은행의 2음절 낱말은 실제로 빠진다(빼기가 동작하는지)
    import curriculum
    bank = {w["word"] for w in curriculum.WORD_BANK}
    assert "바다" in bank and "바다" in nw.repo_real_words()


def test_within_set_constraints():
    for s in DATA["sets"]:
        words = [w["word"] for w in s["words"]]
        ps = [nw.parts(w) for w in words]
        assert len({p[0] for p in ps}) == len(ps) and len({p[2] for p in ps}) == len(ps)   # C1·C2 겹침 없음
        assert {(p[1], p[3]) for p in ps} == {tuple(s["vowels"])}                         # 모음 틀 하나
        for a, b in combinations(words, 2):
            assert nw.group_distance(a, b) >= nw.MIN_GROUP_DISTANCE, (a, b)
        assert len({w["shape"] for w in s["words"]}) == nw.SET_SIZE
        assert all(w["shape"] in nw.SHAPES for w in s["words"])
        assert all(w["skeleton"] == nw.skeleton(w["word"]) for w in s["words"])


def test_skeletons_never_repeat_and_heldout_is_untrained():
    train_sk = [nw.skeleton(w) for w in ALL_TRAIN]
    assert len(set(train_sk)) == len(train_sk)
    assert not ({nw.skeleton(w) for w in ALL_HELD} & set(train_sk))


def test_consonants_spread_over_training():
    from collections import Counter
    cnt = Counter()
    for w in ALL_TRAIN:
        c1, _, c2, _, _ = nw.parts(w)
        cnt[c1] += 1
        cnt[c2] += 1
    assert set(cnt) == set(nw._ONSETS)
    assert max(cnt.values()) - min(cnt.values()) <= 3


def test_skeleton_rule():
    assert nw.skeleton("바록") == "ㅂ_ㄹ_ㄱ"
    assert nw.skeleton("아이") == "__"
    assert nw.skeleton("바다") == "ㅂ_ㄷ_"


def test_generation_is_deterministic_and_seeded():
    ex = nw.repo_real_words() | set(DATA["excluded_by_wordfreq"])
    assert nw.generate(ex, 7) == nw.generate(ex, 7)
    assert nw.generate(ex, 7)["sets"] != nw.generate(ex, 8)["sets"]


# ── 회차 규칙 ────────────────────────────────────────────────────────

S1 = DATA["sets"][0]
W1 = [w["word"] for w in S1["words"]]


def _block(block, wrong=()):
    return [(nw.item_id(S1["id"], block), w, w not in wrong) for w in W1]


def test_item_id_round_trip():
    assert nw.item_id("ns01", 1) == "ns01:b1:h" and nw.item_id("ns01", 2) == "ns01:b2:c"
    assert nw.parse_item_id("ns03:b12:c") == ("ns03", 12)
    assert nw.parse_item_id("x") is None and nw.parse_item_id(None) is None


def test_fresh_set_starts_with_hint_block():
    p = nw.set_progress(S1, [])
    assert p == {"met": False, "next_block": 1, "hint": True, "remaining": W1, "blocks": {}, "n": 0}


def test_partial_block_resumes_with_remaining_words():
    rows = _block(1)[:2]
    p = nw.set_progress(S1, rows)
    assert p["next_block"] == 1 and p["remaining"] == W1[2:]
    # 같은 블록에 같은 낱말이 다시 들어오면 처음 것만 센다
    p2 = nw.set_progress(S1, rows + [rows[0]])
    assert p2["n"] == 2


def test_hint_block_never_meets_criterion():
    p = nw.set_progress(S1, _block(1))
    assert not p["met"] and p["next_block"] == 2 and p["hint"] is False


def test_check_block_criterion():
    # 6개 목록에서 90%는 6개 모두
    p = nw.set_progress(S1, _block(1) + _block(2, wrong={W1[0]}))
    assert not p["met"] and p["next_block"] == 3 and p["hint"] is True
    p = nw.set_progress(S1, _block(1) + _block(2, wrong={W1[0]}) + _block(3) + _block(4))
    assert p["met"] and p["blocks"][4] == [6, 6]


def test_session_moves_to_next_set_and_finishes():
    rows = _block(1) + _block(2)
    st = nw.session_state(DATA["sets"], rows, today_n=12)
    assert st["set_index"] == 1 and st["sets_done"] == 1 and st["progress"]["next_block"] == 1
    assert st["today"] == {"n": 12, "cap": nw.DAILY_TRIAL_CAP, "minutes": nw.DAILY_MINUTES, "done": False}
    all_rows = []
    for s in DATA["sets"]:
        for b in (1, 2):
            all_rows += [(nw.item_id(s["id"], b), w["word"], True) for w in s["words"]]
    fin = nw.session_state(DATA["sets"], all_rows, today_n=nw.DAILY_TRIAL_CAP)
    assert fin["finished"] and fin["sets_done"] == nw.SET_COUNT and fin["today"]["done"]


def test_other_rows_are_ignored():
    rows = [("ns02:b1:h", W1[0], True), ("junk", W1[1], True), (nw.item_id(S1["id"], 1), "없는말", True)]
    assert nw.set_progress(S1, rows)["n"] == 0


def test_daily_budget_fits_ten_minutes():
    # 시행당 약 10초(골격 1.5초 + 아바타 2~3번 반복 + 답 + 피드백)로 잡으면 하루 시행 상한이 10분 안이다
    assert nw.DAILY_TRIAL_CAP * 10 <= nw.DAILY_MINUTES * 60


# ── API(임시 DB, 별도 프로세스) ─────────────────────────────────────────

_FLOW = r'''
import json
from fastapi.testclient import TestClient
import main, nonsense_words as nw
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "ns@example.com", "username": "nsu", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    s0 = c.get("/api/nonsense/session", headers=h).json()
    words = [w["word"] for w in s0["set"]["words"]]
    sid = s0["set"]["id"]
    ans = lambda b, w, ch, **kw: c.post("/api/nonsense/answer", json={"set_id": sid, "block": b, "word": w, "chosen": ch, **kw}, headers=h)
    first = ans(1, words[0], words[1], options=words).json()       # 오답
    dup = ans(1, words[0], words[0]).status_code                    # 같은 블록에 같은 낱말 다시
    skip = ans(2, words[1], words[1]).status_code                   # 블록 건너뛰기
    bad = ans(1, words[1], "바다").status_code                      # 목록 밖 낱말
    for w in words[1:]:
        last1 = ans(1, w, w).json()
    for w in words:
        last2 = ans(2, w, w).json()
    s1 = c.get("/api/nonsense/session", headers=h).json()
    stages = c.get("/api/curriculum/stages", headers=h).json()
    ev = c.get("/api/eval/summary", headers=h).json()
    acts = c.get("/api/calendar/activities", params={"tz_offset_min": -540}, headers=h).json()
    import asyncio
    from database import AsyncSessionLocal, TrialAttempt, ReviewItem, User
    from sqlalchemy import select
    async def rows():
        async with AsyncSessionLocal() as db:
            t = (await db.execute(select(TrialAttempt.item_type, TrialAttempt.stage, TrialAttempt.item_id, TrialAttempt.options,
                                         TrialAttempt.confusions).order_by(TrialAttempt.id))).all()
            rv = (await db.execute(select(ReviewItem))).scalars().all()
            xp = (await db.execute(select(User.total_xp))).scalars().all()
            return [list(x) for x in t], len(rv), xp
    trows, n_review, xp = asyncio.run(rows())
    print("RESULT " + json.dumps({"s0": s0, "first": first, "dup": dup, "skip": skip, "bad": bad, "last1": last1, "last2": last2,
        "s1": s1, "stages": stages, "by_type": ev.get("by_item_type"), "acts": acts, "trows": trows, "n_review": n_review,
        "xp": xp}, ensure_ascii=False))
'''


def test_api_flow_logs_trials_without_touching_mastery():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1")
        env.pop("ANTHROPIC_API_KEY", None)
        p = subprocess.run([sys.executable, "-c", _FLOW], cwd=here, env=env, capture_output=True, text=True, timeout=240)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])
    s0 = r["s0"]
    assert s0["set"]["id"] == "ns01" and s0["block"] == {"index": 1, "hint": True, "remaining": [w["word"] for w in s0["set"]["words"]],
                                                        "started": False, "history": {}}
    assert s0["today"]["n"] == 0 and s0["finished"] is False
    assert r["first"]["correct"] is False and r["first"]["confusions"] and r["first"]["block_done"] is False
    assert r["first"]["block"]["remaining"] == [w["word"] for w in s0["set"]["words"]][1:]
    assert (r["dup"], r["skip"], r["bad"]) == (400, 409, 400)
    assert r["last1"]["block_done"] and r["last1"]["block_correct"] == 5 and r["last1"]["set_done"] is False
    assert r["last1"]["block"]["index"] == 2 and r["last1"]["block"]["hint"] is False
    assert r["last2"]["set_done"] is True and r["last2"]["set"]["id"] == "ns02"
    assert r["s1"]["sets_done"] == 1 and r["s1"]["today"]["n"] == 12
    # 기록: item_type nonsense, stage NULL, item_id에 블록과 골격 여부, 첫 시행만 보기 순서를 보냄
    assert len(r["trows"]) == 12 and all(t[0] == "nonsense" and t[1] is None for t in r["trows"])
    assert r["trows"][0][2] == "ns01:b1:h" and r["trows"][-1][2] == "ns01:b2:c"
    assert r["trows"][0][3] == [w["word"] for w in s0["set"]["words"]] and r["trows"][1][3] is None
    # 단계 숙달·복습·XP는 그대로
    st = {s["key"]: s for s in r["stages"]["stages"]}
    assert st["viseme"].get("attempts", 0) == 0 and st["word"].get("attempts", 0) == 0
    assert st["viseme"]["status"] != "mastered"
    assert r["n_review"] == 0 and not any(r["xp"])
    # 유형별 정확도와 회차 기록에는 보인다
    assert any(b["item_type"] == "nonsense" and b["n"] == 12 for b in r["by_type"])
    rows = [x for day in r["acts"].values() for x in day]
    assert any(x["kind"] == "nonsense" and x["n"] == 12 and x["route"] == "/learn/nonsense" for x in rows)
