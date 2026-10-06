"""FSRS 그림자 모드(fsrs_shadow.py, C11): 식의 성질, 앱 답 → 등급, 관측 확률, 분석(log loss·보정표·시간순 분할)."""
import math
import random

import fsrs_shadow as fs


def test_forgetting_curve_hits_90_percent_at_stability():
    assert math.isclose(fs.retrievability(5.0, 5.0), 0.9, rel_tol=1e-9)
    assert fs.retrievability(0, 3.0) == 1.0
    assert fs.retrievability(10, 3.0) < fs.retrievability(2, 3.0)


def test_initial_state_uses_fsrs5_defaults():
    st = fs.step(None, fs.GOOD, None)
    assert st["r"] is None
    assert st["stability"] == fs.DEFAULT_W[2]
    assert math.isclose(st["difficulty"], 7.1949 - math.exp(0.5345 * 2) + 1, rel_tol=1e-9)
    assert fs.step(None, fs.AGAIN, None)["stability"] == fs.DEFAULT_W[0]


def test_recall_grows_and_lapse_shrinks_stability():
    s0 = {"stability": 5.0, "difficulty": 5.0}
    good = fs.step(s0, fs.GOOD, 5)
    hard = fs.step(s0, fs.HARD, 5)
    again = fs.step(s0, fs.AGAIN, 5)
    assert math.isclose(good["r"], 0.9, rel_tol=1e-9)
    assert good["stability"] > hard["stability"] > 5.0 > again["stability"]
    assert again["difficulty"] > s0["difficulty"] > good["difficulty"] - 1e-9
    # 망각 뒤 안정도는 S / e^(w17·w18) 이하(FSRS-5)
    assert again["stability"] <= 5.0 / math.exp(fs.DEFAULT_W[17] * fs.DEFAULT_W[18]) + 1e-12


def test_same_day_review_uses_short_term_formula():
    s0 = {"stability": 2.0, "difficulty": 5.0}
    st = fs.step(s0, fs.GOOD, 0)
    assert math.isclose(st["stability"], 2.0 * math.exp(fs.DEFAULT_W[17] * fs.DEFAULT_W[18]), rel_tol=1e-9)
    assert st["r"] == 1.0


def test_difficulty_stays_in_range():
    st = {"stability": 1.0, "difficulty": 9.9}
    for _ in range(30):
        st = fs.step(st, fs.AGAIN, 1)
        assert fs.D_MIN <= st["difficulty"] <= fs.D_MAX
    for _ in range(30):
        st = fs.step(st, fs.EASY, 1)
        assert fs.D_MIN <= st["difficulty"] <= fs.D_MAX


def test_grade_mapping_follows_app_rules():
    assert fs.grade_for(1, "choice", 1.0) == fs.AGAIN
    assert fs.grade_for(3, "choice", 0.8) == fs.HARD          # 감속 정답 → Hard
    assert fs.grade_for(3, "choice", 1.0) == fs.GOOD          # 보기 고른 정답: 찍기는 관측 확률에서
    assert fs.grade_for(4, "typed", 1.0) == fs.GOOD
    assert fs.grade_for(3) == fs.HARD and fs.grade_for(4) == fs.GOOD and fs.grade_for(5) == fs.EASY   # 점수 등급


def test_observed_probability_for_four_choice():
    assert fs.observed_probability(0.0, fs.guess_rate("choice")) == 0.25
    assert math.isclose(fs.observed_probability(0.8, fs.guess_rate("choice")), 0.25 + 0.75 * 0.8)
    assert fs.observed_probability(0.8, fs.guess_rate("typed")) == 0.8
    assert fs.observed_probability(None, 0.25) is None


def test_sm2_proxy():
    assert fs.sm2_proxy(6, 6) == 0.9
    assert fs.sm2_proxy(None, 6) is None and fs.sm2_proxy(3, 0) is None
    assert fs.sm2_proxy(12, 6) < fs.sm2_proxy(6, 6)


def test_time_split_is_per_learner_and_ordered():
    rows = [{"user_id": u, "t": f"2026-10-{d:02d}", "id": d} for u in (1, 2) for d in range(1, 11)]
    train, test = fs.time_split(rows, 0.7)
    assert len(train) == 14 and len(test) == 6
    for u in (1, 2):
        last_train = max(r["t"] for r in train if r["user_id"] == u)
        first_test = min(r["t"] for r in test if r["user_id"] == u)
        assert last_train < first_test


def _synthetic(n, seed=0):
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        r = rng.uniform(0.3, 1.0)
        guess = 0.25 if i % 2 else 0.0
        p = fs.observed_probability(r, guess)
        rows.append({"id": i, "user_id": i % 10, "t": f"{i:06d}", "guess": guess, "passed": rng.random() < p,
                     "p_fsrs": p, "p_sm2": fs.observed_probability(0.9, guess)})
    return rows


def test_compare_reports_and_only_judges_with_enough_reviews():
    small = fs.compare(_synthetic(100))
    assert small["enough"] is False and small["criterion_met"] is None
    assert set(small["log_loss"]) == {"fsrs", "constant", "sm2_proxy"}
    big = fs.compare(_synthetic(4000, seed=1))
    assert big["enough"] is True
    # 결과가 FSRS 예측에서 뽑혔으므로 FSRS가 상수·SM-2 대리보다 낮고 보정 차이도 작다
    assert big["log_loss"]["fsrs"] < big["log_loss"]["constant"]
    assert big["log_loss"]["fsrs"] < big["log_loss"]["sm2_proxy"]
    assert big["calibration"]["fsrs"]["gap_mean"] < 0.05
    assert big["criterion_met"] is True


def test_compare_skips_rows_without_predictions():
    rows = _synthetic(20)
    rows[0]["p_fsrs"] = None
    out = fs.compare(rows)
    assert out["n_rows"] == 20 and out["n_usable"] == 19


def test_calibration_table_bins():
    t = fs.calibration_table([0.05, 0.15, 0.95, 1.0], [0, 0, 1, 1], bins=10)
    assert [b["n"] for b in t["bins"]] == [1, 1, 2]
    assert t["gap_mean"] is not None
