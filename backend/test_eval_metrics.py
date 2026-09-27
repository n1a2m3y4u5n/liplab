"""학습 효과 리포트 지표(eval_metrics, GET /api/eval/summary). 근거는 docs/eval-metrics.md."""
import json
import os
import subprocess
import sys
import tempfile

from eval_metrics import (criterion_progress, group_adjusted_curve, pooled_change, type_adjusted_curve,
                          within_type_change)

# 실력 변화 없이 유형만 바뀌는 학습자: 입모양 12회(10/12 정답) 뒤 단어 12회(6/12 정답), 유형 안에서는 고르게 섞임
_V = [True, True, True, False, True, True, True, True, True, True, True, False]
_W = [True, False, True, False, True, False, False, True, False, True, True, False]
NO_LEARNING = [("viseme", c) for c in _V] + [("word", c) for c in _W]


def test_pooled_split_confounds_type_mix_but_within_type_does_not():
    old = pooled_change(NO_LEARNING)
    assert old["delta"] < -0.3                 # 예전 방식: 유형이 바뀐 것만으로 크게 떨어져 보인다
    new = within_type_change(NO_LEARNING)
    assert new["method"] == "within_type" and abs(new["delta_pp"]) <= 10
    assert [t["item_type"] for t in new["by_type"]] == ["viseme", "word"]
    assert new["n_each"] == 4 + 4               # 유형별 k = 12 // 3


def test_within_type_needs_nine_trials_in_a_type_and_weights_by_k():
    assert within_type_change([("viseme", True)] * 8 + [("word", False)] * 8) is None
    trials = [("viseme", False)] * 3 + [("viseme", True)] * 6 + [("word", False)] * 18
    r = within_type_change(trials)
    # 입모양 k=3: 0% → 100%, 단어 k=6: 0% → 0%. 가중 평균 = (3·100 + 6·0) / 9
    assert r["baseline_acc"] == 0.0 and r["recent_acc"] == round(300 / 9, 1)
    assert {t["item_type"]: t["delta_pp"] for t in r["by_type"]} == {"viseme": 100.0, "word": 0.0}


def test_type_adjusted_curve_is_flat_without_learning():
    curve = type_adjusted_curve(NO_LEARNING, n_bins=4)
    assert [b["n"] for b in curve] == [6, 6, 6, 6]
    assert curve[0]["raw"] > curve[-1]["raw"] + 0.2           # 보정 전: 계단처럼 떨어진다
    assert max(b["value"] for b in curve) - min(b["value"] for b in curve) <= 0.17   # 보정 뒤: 표집 잡음만
    assert type_adjusted_curve([]) == []


def test_group_adjusted_curve_clips_and_rounds():
    items = [(1, 100.0), (1, 100.0), (2, 0.0), (2, 100.0)]
    c = group_adjusted_curve(items, n_bins=4, lo=0.0, hi=100.0, ndigits=1)
    assert all(0.0 <= b["value"] <= 100.0 for b in c)
    assert [b["raw"] for b in c] == [100.0, 100.0, 0.0, 100.0]


def test_criterion_progress_uses_the_binding_condition():
    assert criterion_progress(True, 3, 10.0, 85.0, 8) == 1.0
    assert criterion_progress(False, 3, 100.0, 85.0, 8) == 0.375         # 시도 수가 모자람
    assert criterion_progress(False, 52, 65.6, 85.0, 6) == round(65.6 / 85, 3)   # 점수가 모자람
    assert criterion_progress(False, 0, 0.0, None, None) == 0.0


_FLOW = r'''
import json
from fastapi.testclient import TestClient
import main
out = {}
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "ev@example.com", "username": "ev1", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    marks = []
    for i in range(11):
        j = c.post("/api/curriculum/recognition", json={"viseme_id": 1, "chosen_id": 1}, headers=h).json()
        marks.append(j["mastered"])
    s = c.get("/api/eval/summary", headers=h).json()
    out["first_mastered_at"] = marks.index(True) + 1
    out["stage1"] = next(x for x in s["trials_to_criterion"] if x["stage"] == 1)
    out["curve"] = s["learning_curve"]
    out["bvr"] = s["baseline_vs_recent"]
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


def test_summary_reports_the_attempt_where_mastery_was_first_reached():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1")
        env.pop("ANTHROPIC_API_KEY", None)
        p = subprocess.run([sys.executable, "-c", _FLOW], cwd=here, env=env, capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])
    st1 = r["stage1"]
    assert r["first_mastered_at"] == 8                       # 최소 시도 8회에서 숙달
    assert st1["mastered"] and st1["attempts"] == 11
    assert st1["trials_to_mastery"] == 8, "숙달 뒤 시도가 늘어도 처음 숙달한 시도 수를 보여야 한다"
    assert st1["progress"] == 1.0 and st1["mastery_threshold"] == 85.0
    assert r["curve"] and all("raw" in b for b in r["curve"])
    assert r["bvr"]["method"] == "within_type" and r["bvr"]["by_type"][0]["item_type"] == "viseme"
