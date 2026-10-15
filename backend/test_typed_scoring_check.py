"""P20 표본·채점표·분석 도구(scripts/typed_scoring_check.py): 표본 규칙(층·한 사람 몫·빈 답), 채점표에 자동 점수가 없음,
ICC 식, 채점표 오류 검사, 끝까지 도는지. 기준 문서는 docs/pilot/typed-scoring-check.md 5·6·10절이다."""
import csv
import importlib.util
import json
import os
import random
from collections import Counter

import numpy as np
import pytest

_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "typed_scoring_check.py")
_spec = importlib.util.spec_from_file_location("typed_scoring_check", _SCRIPT)
tsc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tsc)


def _read(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _export(n_people=8, n_items=40, seed=1):
    return tsc.fake_export(seed=seed, n_people=n_people, n_items=n_items)


def _write_export(tmp_path, ex):
    p = tmp_path / "export.json"
    p.write_text(json.dumps(ex, ensure_ascii=False), encoding="utf-8")
    return str(p)


# ── 대상 모으기 ─────────────────────────────────────

def test_collect_filters_layer_modality_and_dedups():
    ex = _export(n_people=2, n_items=5)
    ex["participants"][0]["battery"].append({"session_label": "A1", "layer": "snr", "modality": "A", "open": [
        {"seq": 0, "item_id": "n0", "modality": "A", "target": "물 주세요", "answer_text": "물 주세요"}]})
    ex["participants"][0]["battery"].append(dict(ex["participants"][0]["battery"][0]))   # 같은 회차·층을 한 번 더(이어서 하기)
    rows = tsc.collect(ex)
    assert len(rows) == 10 and all(r["layer"] == "sentence" and r["modality"] == "real" for r in rows)
    assert len(tsc.collect(ex, layers=("sentence", "snr"), modality="any")) == 11
    assert tsc.collect(ex, modality="avatar") == []


def test_blank_detection():
    assert tsc.is_blank("") and tsc.is_blank("  ,. ") and tsc.is_blank(None)
    assert not tsc.is_blank("모름") and not tsc.is_blank("ㅂ")


# ── 표본 규칙(문서 5절 2항) ─────────────────────────

def test_sample_rules_strata_cap_blank():
    rows = tsc.collect(_export(n_people=8, n_items=40))
    chosen, cuts, warnings, shortfall = tsc.draw_sample(rows, n=200, seed=3)
    assert len(chosen) == 200 and len(set(chosen)) == 200
    assert Counter(rows[i]["stratum"] for i in chosen) == {1: 40, 2: 40, 3: 40, 4: 40, 5: 40}
    assert max(Counter(rows[i]["pid"] for i in chosen).values()) <= 60
    assert sum(rows[i]["blank"] for i in chosen) <= 10
    assert not shortfall and not warnings
    # 층은 점수 순서를 지킨다(낮은 층의 최댓값 ≤ 높은 층의 최솟값)
    for a, b in zip(cuts, cuts[1:]):
        assert a["max"] <= b["min"]
    # 같은 시드는 같은 표본
    rows2 = tsc.collect(_export(n_people=8, n_items=40))
    assert tsc.draw_sample(rows2, n=200, seed=3)[0] == chosen


def test_person_cap_binds_and_fills_from_neighbours():
    # 한 사람이 답의 대부분을 낸 경우: 30% 상한(60개)을 지키고 다른 사람 답으로 채운다
    ex = _export(n_people=1, n_items=300, seed=5)
    other = _export(n_people=6, n_items=30, seed=6)
    for j, p in enumerate(other["participants"]):
        p["pid"] = f"q{j}"
    ex["participants"] += other["participants"]
    rows = tsc.collect(ex)
    chosen, _cuts, warnings, _short = tsc.draw_sample(rows, n=200, seed=1)
    by = Counter(rows[i]["pid"] for i in chosen)
    assert by["p00"] <= 60 and len(chosen) == 200


def test_blank_cap():
    ex = _export(n_people=8, n_items=40)
    for p in ex["participants"]:
        for r in p["battery"][0]["open"][:6]:
            r["answer_text"] = ""          # 빈 답 48개
    rows = tsc.collect(ex)
    chosen, *_ = tsc.draw_sample(rows, n=200, seed=2)
    assert sum(rows[i]["blank"] for i in chosen) <= 10


def test_small_pool_takes_all_with_warning():
    rows = tsc.collect(_export(n_people=3, n_items=20))
    chosen, _c, warnings, _s = tsc.draw_sample(rows, n=200)
    assert len(chosen) == 60 and any("모두 쓴다" in w for w in warnings)


# ── 채점표 ─────────────────────────────────────────

def test_sheets_hide_auto_scores_and_participants(tmp_path):
    ex = _export()
    m = tsc.sample(_write_export(tmp_path, ex), str(tmp_path / "out"), seed=11)
    out = tmp_path / "out"
    a, b = _read(out / "rater_sheet_A.csv"), _read(out / "rater_sheet_B.csv")
    assert list(a[0].keys()) == tsc.RATER_COLS
    assert len(a) == len(b) == 200 and {r["표본id"] for r in a} == {r["표본id"] for r in b}
    assert [r["표본id"] for r in a] != [r["표본id"] for r in b]          # 행 순서가 다르다
    assert all(not r[tsc.C_MATCH] and not r[tsc.C_NT] for r in a)       # 채점 칸은 비어 있다
    text = (out / "rater_sheet_A.csv").read_text(encoding="utf-8-sig")
    assert "p0" not in text and "auto" not in text and "stratum" not in text
    op = _read(out / "operator_key.csv")
    assert {r["sample_id"] for r in op if r["sample_id"].startswith("T")} == {r["표본id"] for r in a}
    assert len([r for r in op if r["sample_id"].startswith("P")]) == 20
    practice = {(r["정답 문장"], r["친 답"]) for r in _read(out / "practice_sheet.csv")}
    assert len(practice) >= 1
    assert len(_read(out / "boundary_sheet.csv")) == 30
    keys = _read(out / "key_sheet.csv")
    assert keys and "발음 열쇠(표준 발음)" in keys[0] and all(not r["발음 열쇠(표준 발음)"] for r in keys)
    assert m["n_sample"] == 200 and m["scorer_version"] == "strict-v2" and m["export_sha256"]


def test_boundary_cases_cover_doc_list():
    cases = {c for c, _t, _a in tsc.BOUNDARY_CASES}
    for need in ("띄어쓰기", "전각 공백", "쉼표", "낱자", "숫자", "영문", "순서 바뀜", "덧붙임", "발음대로 쓴 답", "오타", "빈 답", "'모름'"):
        assert need in cases
    assert len(tsc.BOUNDARY_CASES) == 30
    auto = {(t, a): tsc.score(t, a) for _c, t, a in tsc.BOUNDARY_CASES}
    assert auto[("오늘 날씨가 좋아요", "모름")]["n_matched_phonemes"] == 0          # R9
    assert auto[("옷 입어요", "옷　입어요")]["phoneme_accuracy"] == 1.0          # R1
    assert auto[("세 시에 만나요", "3시에 만나요")]["phoneme_accuracy"] == 1.0       # R5 숫자


# ── ICC와 분석 ─────────────────────────────────────

def _icc_numpy(x):
    x = np.asarray(x, float)
    n, k = x.shape
    gm = x.mean()
    msr = k * ((x.mean(1) - gm) ** 2).sum() / (n - 1)
    msc = n * ((x.mean(0) - gm) ** 2).sum() / (k - 1)
    sse = ((x - x.mean(1, keepdims=True) - x.mean(0, keepdims=True) + gm) ** 2).sum()
    mse = sse / ((n - 1) * (k - 1))
    return (msr - mse) / (msr + (k - 1) * mse + k * (msc - mse) / n)


def test_icc_formula():
    rng = random.Random(0)
    for _ in range(20):
        x = [[v, v + rng.gauss(0.02, 0.05)] for v in (rng.random() for _ in range(30))]
        assert tsc.icc_a1(x) == pytest.approx(_icc_numpy(x), abs=1e-12)
    assert tsc.icc_a1([[0.1, 0.1], [0.5, 0.5], [0.9, 0.9]]) == pytest.approx(1.0)
    # 절대 일치: 한쪽이 일정하게 높으면 1보다 작다(일관성 ICC라면 1)
    assert tsc.icc_a1([[0.1, 0.3], [0.5, 0.7], [0.6, 0.8]]) < 0.9
    assert tsc.icc_a1([[1.0, 1.0]]) is None


def test_analyze_end_to_end(tmp_path):
    out = str(tmp_path / "demo")
    tsc.sample(_write_export(tmp_path, _export()), out)
    tsc.fake_raters(out)
    r = tsc.analyze(out, os.path.join(out, "rater_sheet_A.csv"), os.path.join(out, "rater_sheet_B.csv"), B=200)
    assert not r.get("errors")
    m = r["response_level"]
    assert m["n"] == 200 and 0.9 < m["icc_auto_vs_mean"] <= 1.0 and m["ci95"][0] <= m["icc_auto_vs_mean"] <= m["ci95"][1]
    assert r["verdict"].startswith("통과") and r["session_level"]["n"] == 8
    assert os.path.exists(os.path.join(out, "analysis.json")) and os.path.exists(os.path.join(out, "disagreements.csv"))


def test_analyze_reports_sheet_errors(tmp_path):
    out = str(tmp_path / "demo")
    tsc.sample(_write_export(tmp_path, _export()), out)
    tsc.fake_raters(out)
    p = os.path.join(out, "rater_sheet_B.csv")
    rows = _read(p)
    rows[0][tsc.C_MATCH] = ""                                   # 빈 칸
    rows[1][tsc.C_MATCH] = str(int(rows[1][tsc.C_NT]) + 1)       # 맞은 수 > 정답 수
    rows[2][tsc.C_NT] = "다섯"                                   # 숫자가 아님
    del rows[3]                                                  # 빠진 표본
    tsc.write_csv(p, tsc.RATER_COLS, rows)
    r = tsc.analyze(out, os.path.join(out, "rater_sheet_A.csv"), p, B=50)
    errs = " ".join(r["errors"])
    assert "비어 있다" in errs and "> 정답 음소 수" in errs and "숫자가 아니다" in errs and "없는 표본 1개" in errs


def test_judge_holds_when_raters_disagree():
    block = {"icc_auto_vs_mean": 0.95, "ci95": [0.92, 0.97], "icc_raters": 0.80, "bland_altman": {"mean_diff": 0.0}}
    assert tsc.judge(block)[0] == "보류"
    block["icc_raters"] = 0.95
    assert tsc.judge(block)[0] == "통과"
    block["bland_altman"] = {"mean_diff": 0.05}
    assert tsc.judge(block)[0].startswith("통과(주지표만")
    block["icc_auto_vs_mean"] = 0.85
    assert tsc.judge(block)[0] == "미달"


def test_key_mismatch(tmp_path):
    p = tmp_path / "key_sheet.csv"
    tsc.write_csv(str(p), tsc.KEY_COLS, [
        {"문장id": "S001", tsc.C_TARGET: "옷 입어", "발음 열쇠(표준 발음)": "오디버", "정답 음소 수": "5"},
        {"문장id": "S002", tsc.C_TARGET: "닭 앞에", "발음 열쇠(표준 발음)": "다가페", "정답 음소 수": "7"},   # 자동은 표준 발음 쪽 6
    ])
    mm = tsc.key_mismatch(str(p))
    assert [r["sentence_id"] for r in mm] == ["S002"] and mm[0]["auto_n"] == 6


def test_tool_does_not_import_app_scoring_paths():
    src = open(_SCRIPT, encoding="utf-8").read()
    assert "calculate_score" not in src.replace("scoring.calculate_score", "") and "sentence_feedback" not in src.split('"""', 2)[2]
