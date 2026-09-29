"""학습 효과 리포트·재검사 비교의 통계 타당성(9/29, docs/eval-metrics.md 6~9절).

- 개인 전후 차이의 색: Newcombe 95% 구간이 0을 벗어날 때만 칠한다. 학습 효과가 없을 때 색이 붙는 비율 ≤ 5%.
- 사전(A 24문항)·사후(B 기본 얼굴 12문항) 비교: 학습 효과가 없을 때 |평균 편향| ≤ 2%p. 새 가상 화자 문항이 더 어려워도 그렇다.
- /api/assessment/history는 같은 종류끼리만 비교한다(동형 폼끼리, 자가진단끼리).
- 문장 점수 추이는 복습 행을 빼고, 초기 대비 최근·학습곡선은 1.0배 보통 문항만 쓴다.
- 검사 결과에 검사 전 연습 시행 수(trials_before)를 남긴다.
"""
import json
import math
import os
import random
import statistics
import subprocess
import sys
import tempfile
from types import SimpleNamespace

import assessment as A
import eval_metrics as E


def test_newcombe_matches_published_example():
    # Newcombe(1998) 표 II 예: 56/70 대 48/80, 차이 0.2000, 방법 10 구간 0.0524~0.3339 (여기서는 p2 − p1이라 부호가 반대)
    r = E.newcombe_diff(56, 70, 48, 80)
    assert r["diff"] == -0.2 and r["clear"] is True
    assert abs(r["ci95"][0] + 0.3339) < 1e-3 and abs(r["ci95"][1] + 0.0524) < 1e-3
    lo, hi = E.wilson_interval(0, 12)
    assert abs(lo) < 1e-12 and abs(hi - 0.2425) < 1e-3
    assert E.newcombe_diff(5, 0, 1, 2) is None
    assert E.newcombe_diff(12, 24, 6, 12)["clear"] is False


def _p_ok(theta, d, c=0.25):
    return c + (1 - c) / (1 + math.exp(-A._EAP_SLOPE * (theta - d)))


def test_prepost_null_false_color_and_bias():
    """학습 효과 없음(θ 고정)에서 사전 A(24문항)와 사후 B 기본 얼굴 절반(12문항) 비교. 새 가상 화자 문항은 정답률을 10%p 낮춘다."""
    F = A.frozen_forms(build_if_missing=False)
    fa, fb = F["A"], F["B"]
    rng = random.Random(1)
    n = 1500
    for theta in (0.3, 0.45, 0.6, 0.75, 0.9):
        colored = red_old = 0
        new_d, old_d = [], []
        for u in range(n):
            xa = sum(rng.random() < _p_ok(theta, it["difficulty"]) for it in fa)
            post = [(it["talker"], rng.random() < _p_ok(theta, it["difficulty"]) - (0.10 if it["talker"] != "default" else 0))
                    for it in A.assign_talker_conditions(fb, u)]
            face = [c for t, c in post if t == "default"]
            r = E.newcombe_diff(xa, 24, sum(face), len(face))
            colored += r["clear"]
            red_old += r["diff"] < 0
            new_d.append(r["diff"] * 100)
            old_d.append((sum(c for _, c in post) - xa) / 24 * 100)   # 예전 파일럿 분석: 사후 24문항을 모두 셈
        assert colored / n <= 0.05, (theta, colored / n)
        assert abs(statistics.fmean(new_d)) <= 2.0, (theta, statistics.fmean(new_d))
        assert statistics.fmean(old_d) < -4.0            # 예전 방식은 새 화자 문항 난이도만큼 떨어져 보였다
        if theta < 0.9:
            assert red_old / n > 0.3                     # 예전 색(부호만)은 효과가 없어도 3분의 1 넘게 빨강


def test_within_type_null_false_color():
    rng = random.Random(2)
    n = 4000
    colored = 0
    for _ in range(n):
        tr = [("viseme", rng.random() < .8) for _ in range(rng.randint(12, 30))] + \
             [("word", rng.random() < .6) for _ in range(rng.randint(15, 45))]
        colored += E.within_type_change(tr)["clear"]
    assert colored / n <= 0.05, colored / n


def test_natural_speed_filter_removes_fast_speech_bias():
    assert E.is_natural_trial(None, False) and E.is_natural_trial(1.0, False) and E.is_natural_trial(1.005, None)
    assert not E.is_natural_trial(1.25, False) and not E.is_natural_trial(0.75, False) and not E.is_natural_trial(1.0, True)
    rng = random.Random(4)
    raw, nat = [], []
    for _ in range(3000):
        tr = [("word", rng.random() < .6, 1.0) for _ in range(33)] + \
             [("word", rng.random() < .45, rng.choice([1.25, 1.6, 2.0])) for _ in range(12)]
        raw.append(E.within_type_change([(t, c) for t, c, _ in tr])["delta_pp"])
        nat.append(E.within_type_change([(t, c) for t, c, s in tr if E.is_natural_trial(s, False)])["delta_pp"])
    assert statistics.fmean(raw) < -8 and abs(statistics.fmean(nat)) <= 2.0


def _r(form, version="v2"):
    return SimpleNamespace(form=form, form_version=version)


def test_comparable_pair_only_like_with_like():
    assert A.comparable_pair([_r("placement")]) is None
    assert A.comparable_pair([_r("placement"), _r("B")]) is None               # 적응형 뒤 동형 폼: 비교하지 않는다
    p = A.comparable_pair([_r("placement"), _r("A"), _r("placement"), _r("B")])
    assert p["kind"] == "fixed_forms" and p["base"].form == "A" and "A→B" in p["label"]
    p = A.comparable_pair([_r("A"), _r("B"), _r("placement")])
    assert p is None                                                           # 자가진단 짝이 없다
    p = A.comparable_pair([_r("placement"), _r("A"), _r("placement")])
    assert p["kind"] == "adaptive" and p["base"] is not p["latest"]
    p = A.comparable_pair([_r("A"), _r("A")])
    assert p["kind"] == "same_form"
    assert A.comparable_pair([_r("A", "v1"), _r("B", "v2")]) is None             # 판본이 다르면 동형이 아니다
    assert A.pretest_after_training(None) is None
    assert A.pretest_after_training(A.PRETEST_TRIALS_FLAG - 1) is False and A.pretest_after_training(A.PRETEST_TRIALS_FLAG)


_FLOW = r'''
import asyncio, json, random
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
import main, database
import eval_metrics as E
from database import TrialAttempt, Progress

def reg(c, name):
    r = c.post("/api/auth/register", json={"email": f"{name}@example.com", "username": name, "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    return h, c.get("/api/auth/me", headers=h).json()["id"]

def take(c, h, form, k_right):
    items = c.get("/api/assessment/placement", params={"form": form}, headers=h).json()["items"]
    resp = {it["id"]: (it["word"] if i < k_right else next(o for o in it["options"] if o != it["word"]))
            for i, it in enumerate(items)}
    return c.post("/api/assessment/score", json={"items": items, "responses": resp, "form": form}, headers=h).json()

def placement(c, h):
    items = c.get("/api/assessment/placement", params={"n": 8}, headers=h).json()["items"]
    return c.post("/api/assessment/score", json={"items": items, "responses": {it["id"]: it["word"] for it in items},
                                                "form": "placement"}, headers=h).json()

out = {}
with TestClient(main.app) as c:
    # 자가진단 → 사후 B: 종류가 달라 비교하지 않는다. 사전 검사 권유용 pretest_taken은 B를 본 뒤 True
    h, uid = reg(c, "hist1")
    placement(c, h)
    out["after_placement"] = c.get("/api/assessment/history", headers=h).json()
    take(c, h, "B", 12)
    out["placement_then_b"] = c.get("/api/assessment/history", headers=h).json()
    placement(c, h)
    out["adaptive_pair"] = c.get("/api/assessment/history", headers=h).json()

    # 연습 25회 뒤 사전 A, 그 뒤 사후 B: 동형 폼 비교, 사전은 '연습 뒤'로 표시
    h2, uid2 = reg(c, "hist2")
    async def seed_trials():
        base = datetime.utcnow() - timedelta(days=1)
        async with database.AsyncSessionLocal() as db:
            for i in range(25):
                db.add(TrialAttempt(user_id=uid2, stage=1, item_type="viseme", target="1", chosen="1", correct=True,
                                    confusions=[], created_at=base + timedelta(seconds=i)))
            await db.commit()
    asyncio.run(seed_trials())
    a = take(c, h2, "A", 12)
    out["b_has_pretest"] = "pretest" in take(c, h2, "B", 12)
    out["a_result"] = {"trials_before": a.get("trials_before"), "pretest": a.get("pretest")}
    out["fixed_pair"] = c.get("/api/assessment/history", headers=h2).json()
    out["progression"] = c.get("/api/assessment/progression", headers=h2).json()
    out["report_notes"] = c.get("/api/assessment/report", headers=h2).json()["notes"]

    # 리포트: 복습 행은 문장 추이에서 빠지고, 빠른 말·짝 탐색 문항은 초기 대비 최근에서 빠진다
    h3, uid3 = reg(c, "ev1")
    rnd = random.Random(5)
    fresh, trials = [], []
    async def seed_eval():
        base = datetime.utcnow() - timedelta(days=2)
        async with database.AsyncSessionLocal() as db:
            for i in range(40):
                sid = "srs_review_3" if i % 4 == 3 else ("mistake_review_x" if i % 7 == 0 else "cafe")
                sc = 100.0 if sid != "cafe" else float(rnd.randint(20, 80))
                lvl = rnd.choice([1, 2])
                db.add(Progress(user_id=uid3, scenario_id=sid, sentence="문장", user_answer="답", score=sc,
                                difficulty_level=lvl, situation="카페", created_at=base + timedelta(minutes=i)))
                if sid == "cafe":
                    fresh.append((lvl, sc))
            for i in range(36):
                spd = 1.6 if i >= 30 else (None if i % 2 else 1.0)
                probe = {"position": "initial"} if i in (5, 6) else None
                ok = rnd.random() < 0.6
                db.add(TrialAttempt(user_id=uid3, stage=2, item_type="word", target="x", chosen="y", correct=ok,
                                    confusions=[], speed=spd, probe=probe, created_at=base + timedelta(minutes=i)))
                if spd != 1.6 and probe is None:
                    trials.append(("word", ok))
            await db.commit()
    asyncio.run(seed_eval())
    ev = c.get("/api/eval/summary", headers=h3).json()
    out["ev"] = {"trend": ev["sentence_trend"], "bvr": ev["baseline_vs_recent"], "curve": ev["learning_curve"],
                 "total_sentences": ev["overview"]["total_sentences"],
                 "expect_trend": E.group_adjusted_curve(fresh, lo=0.0, hi=100.0, ndigits=1),
                 "expect_bvr": E.within_type_change(trials), "expect_curve": E.type_adjusted_curve(trials),
                 "by_mode_n": sum(m["n"] for m in ev["sentence_by_mode"]), "n_fresh": len(fresh)}
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


def test_history_pairs_progression_ci_and_summary_filters():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1")
        env.pop("ANTHROPIC_API_KEY", None)
        p = subprocess.run([sys.executable, "-c", _FLOW], cwd=here, env=env, capture_output=True, text=True, timeout=240)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])

    assert r["after_placement"]["pretest_taken"] is False and r["after_placement"]["delta"] is None
    pb = r["placement_then_b"]
    assert pb["delta"] is None and pb["comparison"] is None and pb["baseline"] is None and pb["pretest_taken"] is True
    ad = r["adaptive_pair"]
    assert ad["comparison"]["kind"] == "adaptive" and ad["comparison"]["baseline_form"] == "placement"
    assert ad["delta"]["accuracy"] == 0 and ad["delta"]["accuracy_clear"] is False

    assert r["a_result"]["trials_before"] == 25
    assert r["a_result"]["pretest"] == {"trials_before": 25, "after_training": True, "flag_threshold": 20}
    assert r["b_has_pretest"] is False                         # 사전을 본 뒤의 B는 사후라 표시하지 않는다
    fp = r["fixed_pair"]
    assert fp["comparison"]["kind"] == "fixed_forms" and fp["comparison"]["label"] == "동형 폼 A→B 비교"
    # 사전 12/24, 사후 기본 얼굴 절반의 정답률은 앞 12문항 중 기본 얼굴 몫에 따라 다르지만 구간은 늘 있다
    lo, hi = fp["delta"]["accuracy_ci95"]
    assert lo < fp["delta"]["accuracy"] < hi
    pr = r["progression"]
    assert pr["pre"]["trials_before"] == 25 and pr["pre"]["after_training"] is True and pr["pre"]["flag_threshold"] == 20
    assert isinstance(pr["accuracy_delta_clear"], bool) and len(pr["accuracy_delta_ci95"]) == 2
    assert any("연습 25회 뒤" in n for n in r["report_notes"])

    ev = r["ev"]
    assert ev["total_sentences"] == 40                        # 개요는 전체 문장
    assert ev["trend"] == ev["expect_trend"] and ev["by_mode_n"] == ev["n_fresh"]
    assert ev["curve"] == ev["expect_curve"]
    bvr, exp = ev["bvr"], ev["expect_bvr"]
    assert bvr["excluded"] == {"speed": 6, "probe": 2}
    assert {k: bvr[k] for k in exp} == exp and isinstance(bvr["clear"], bool)
