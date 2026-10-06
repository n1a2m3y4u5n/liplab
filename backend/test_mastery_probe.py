"""숙달 지연 탐침(mastery_probe.py, C16): 일정 창, 비율 상한, 문항 고르기, 분석."""
import random
from datetime import date

import curriculum as cur
import mastery_probe as mp


def test_due_waves_windows():
    m = date(2026, 10, 1)
    assert mp.due_waves(m, date(2026, 10, 1)) == []                      # 숙달한 날은 없다
    assert [w["wave"] for w in mp.due_waves(m, date(2026, 10, 2))] == [1]
    assert mp.due_waves(m, date(2026, 10, 2))[0]["due_on"] == "2026-10-02"
    assert [w["wave"] for w in mp.due_waves(m, date(2026, 10, 7))] == [1]   # 1일 회차는 6일 뒤까지
    assert [w["wave"] for w in mp.due_waves(m, date(2026, 10, 8))] == [7]
    assert mp.due_waves(m, date(2026, 10, 14))[0]["delay_days"] == 13
    assert mp.due_waves(m, date(2026, 10, 15)) == []                     # 창이 지나면 없다(예전 숙달자)
    assert mp.due_waves(None, date(2026, 10, 2)) == []


def test_lesson_quota_keeps_share_at_or_below_cap():
    assert mp.lesson_quota(12) == 3                    # 3 / (12 + 3) = 20%
    assert mp.lesson_quota(12, used=2) == 1            # 실제 얼굴 탐침과 상한을 함께 쓴다
    assert mp.lesson_quota(12, used=5) == 0
    assert mp.lesson_quota(0) == 0
    for n in range(1, 40):
        q = mp.lesson_quota(n)
        assert q / (n + q) <= mp.PROBE_SHARE_CAP + 1e-9 if q else True


def test_compose():
    assert mp.compose("ㅂ", "ㅏ") == "바" and mp.compose("ㅇ", "ㅐ") == "애"
    assert mp.compose("받침 ㅇ", "ㅏ") is None


def test_stage1_items_are_unseen_and_unambiguous():
    seen = set(cur.DEMO_SYLLABLE.values())
    items = mp.stage1_items(cur.VISEME_LESSONS, seen, random.Random(1))
    assert len(items) == mp.PROBE_ITEMS
    groups = mp._phoneme_groups(cur.VISEME_LESSONS)
    quiz = {l["viseme_id"] for l in cur.VISEME_LESSONS if l["visibility"] != "low"}
    stimuli = [it["stimulus"] for it in items]
    assert len(set(stimuli)) == len(stimuli)
    assert not (set(stimuli) & (seen | mp.LABEL_SYLLABLES))
    assert len({it["target"] for it in items}) == mp.PROBE_ITEMS      # 퀴즈 무리 여섯이 한 번씩
    for it in items:
        vals = [o["value"] for o in it["options"]]
        assert len(vals) == 4 and len(set(vals)) == 4 and it["target"] in vals
        assert {int(v) for v in vals} <= quiz
        # 음절 안의 다른 무리(자음 무리 음절의 모음 등)는 보기에 없다
        code = ord(it["stimulus"]) - 0xAC00
        cho, jung = mp._CHO[code // 588], mp._JUNG[(code // 28) % 21]
        inside = {groups.get(cho), groups.get(jung)} - {None, int(it["target"])}
        assert not ({str(g) for g in inside} & set(vals))


def test_text_items_skip_seen_and_need_three_wrong_options():
    pool = [f"단어{i}" for i in range(20)]
    seen = set(pool[:10])
    opts = lambda w, used: [x for x in pool if x != w and x not in used][:3]   # noqa: E731
    items = mp.text_items("word", pool, seen, random.Random(0), opts)
    assert len(items) == mp.PROBE_ITEMS
    assert all(it["target"] not in seen for it in items)
    assert all(len(it["options"]) == 4 for it in items)
    none = mp.text_items("word", pool, seen, random.Random(0), lambda w, used: ["a"])
    assert none == []


def test_seed_is_stable():
    assert mp.seed_for(3, 2, 7) == mp.seed_for(3, 2, 7) != mp.seed_for(3, 2, 1)


def test_estimate_p_respects_guess_floor():
    assert mp.estimate_p(0, 6) > 0.25
    assert mp.estimate_p(6, 6) > 0.85
    assert mp.estimate_p(3, 6) < mp.estimate_p(4, 6) < mp.estimate_p(5, 6)
    assert mp.estimate_p(0, 0) is None


def _rows(user, stage, wave, k, n=6):
    return [{"user_id": user, "stage": stage, "wave": wave, "correct": i < k} for i in range(n)]


def test_probe_report_compares_with_simulation():
    rows = []
    for u in range(10):                     # 1·2단계 7일: 10명 중 1명만 선 아래
        rows += _rows(u, 1, 7, 2 if u == 0 else 6)
        rows += _rows(u, 1, 1, 6)
    for u in range(10):                     # 3단계 7일: 10명 중 5명이 선 아래
        rows += _rows(100 + u, 3, 7, 1 if u < 5 else 6)
    rows += [{"user_id": 999, "stage": 2, "wave": 7, "correct": None}] * 6   # 안 푼 탐침은 뺀다
    rows += _rows(998, 2, 7, 3, n=3)        # 답이 너무 적으면 뺀다
    rep = mp.probe_report(rows)
    g12, g3 = rep["groups"]["1-2"], rep["groups"]["3"]
    assert g12["waves"][7]["learners"] == 10
    assert g12["waves"][7]["share_below"] == 0.1 and g12["waves"][7]["within_margin"] is True
    assert g12["decision"] == "유지"
    assert g12["forgetting"]["learners"] == 10 and g12["forgetting"]["mean_drop"] > 0
    assert g3["waves"][7]["share_below"] == 0.5 and g3["waves"][7]["within_margin"] is False
    assert g3["decision"].startswith("숙달 규칙 재검토")
    assert g3["waves"][1]["learners"] == 0 and g3["waves"][1]["share_below"] is None
    assert g12["sim_prediction"] == 0.065 and g3["sim_prediction"] == 0.109



_FLOW_WAVES = r'''
import asyncio, json
import database, main
async def run():
    await database.init_db()
    async with database.AsyncSessionLocal() as db:
        w1 = await main._probe_items(7, 1, 1, db)
        for i, it in enumerate(w1):
            db.add(database.MasteryProbe(user_id=7, stage=1, wave=1, seq=i, item_kind="viseme", stimulus=it["stimulus"],
                                         target=str(it["target"]), options=[], due_on="2026-10-01"))
        db.add(database.TrialAttempt(user_id=7, stage=1, item_type="viseme_ax", target="파/피", chosen="same", correct=True))
        await db.commit()
        w7 = await main._probe_items(7, 1, 7, db)
        return [x["stimulus"] for x in w1], [x["stimulus"] for x in w7]
a, b = asyncio.run(run())
print("RESULT " + json.dumps({"w1": a, "w7": b}, ensure_ascii=False))
'''


def test_probe_items_skip_earlier_wave_and_ax_syllables():
    # 검토 결함 5: 7일 회차는 1일 회차에 낸 자극과 같은지 다른지(AX)에서 본 음절을 다시 내지 않는다
    import json, os, subprocess, sys, tempfile
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1")
        env.pop("ANTHROPIC_API_KEY", None)
        p = subprocess.run([sys.executable, "-c", _FLOW_WAVES], cwd=here, env=env, capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])
    assert r["w7"] and not (set(r["w1"]) & set(r["w7"]))
    assert "파" not in r["w7"] and "피" not in r["w7"]
