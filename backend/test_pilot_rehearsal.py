"""파일럿 리허설 자동화(scripts/pilot_rehearsal.py)와 주분석(scripts/pilot_analyze.py) 테스트.

리허설은 test_pilot.py처럼 임시 DB를 쓰는 별도 프로세스에서 돈다(스크립트가 임시 폴더에 DB·매체를 만들고 지운다). 가상 참여자 5명이
등록부터 유지 검사 예약까지 API로 돌고, 가명 내보내기(판 7, trials=true)에서 분석에 필요한 필드의 null 비율과 배정·순서 규칙,
'영상 준비 전'(missing) 기록을 검사한 뒤 같은 내보내기로 주분석을 끝까지 돌린다. 분석 함수는 합성 자료로 따로 확인한다.
"""
import functools
import importlib.util
import json
import math
import os
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")


def _load(name):
    sys.path.insert(0, SCRIPTS)
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@functools.lru_cache(maxsize=1)
def _rehearsal():
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "out")
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        for k in ("LIPLAB_PILOT", "LIPLAB_PILOT_CODES", "LIPLAB_ADMIN_EMAILS", "LIPLAB_PILOT_NOCUE_COHORTS", "LIPLAB_PILOT_SECRET",
                  "LIPLAB_PILOT_MANIFEST", "LIPLAB_PILOT_MEDIA_DIR", "ANTHROPIC_API_KEY", "DATABASE_URL"):
            env.pop(k, None)
        p = subprocess.run([sys.executable, os.path.join(SCRIPTS, "pilot_rehearsal.py"), "--participants", "5", "--out", out],
                           cwd=HERE, env=env, capture_output=True, text=True, timeout=600)
        line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
        assert line, f"리허설 실패:\n{p.stdout[-3000:]}\n{p.stderr[-4000:]}"
        with open(os.path.join(out, "rehearsal_report.json"), encoding="utf-8") as f:
            rep = json.load(f)
        with open(os.path.join(out, "export.json"), encoding="utf-8") as f:
            ex = json.load(f)
        with open(os.path.join(out, "analysis", "pilot_analyze.json"), encoding="utf-8") as f:
            ana = json.load(f)
        md = open(os.path.join(out, "analysis", "pilot_analyze.md"), encoding="utf-8").read()
    return {"code": p.returncode, "result": json.loads(line[len("RESULT "):]), "rep": rep, "ex": ex, "ana": ana, "md": md,
            "stdout": p.stdout[-3000:]}


def test_rehearsal_all_checks_and_fields_pass():
    r = _rehearsal()
    failed = [c for c in r["rep"]["checks"] if not c["ok"]] + [f for f in r["rep"]["fields"] if not f["ok"]]
    assert r["code"] == 0 and r["result"]["ok"] and not failed, (failed, r["stdout"])
    names = {c["check"] for c in r["rep"]["checks"]}
    for must in ("폼 순서가 순번대로 ABC·BCA·CAB", "실제 얼굴 낱말 층에 '영상 준비 전'(missing.media)이 남는다",
                 "이메일·사용자명·학습 입력 문장이 없다", "학습 초기화 뒤에도 P3 회차·표준검사·소리 듣기 검사가 남는다",
                 "소리 듣기 사전·사후 폼이 다르다", "분석 스크립트가 P3 주지표를 계산했다"):
        assert must in names
    # 필드 검사는 분석에 쓰는 열을 빠짐없이 본다(값이 하나라도 비면 실패)
    fields = {f["field"]: f for f in r["rep"]["fields"]}
    for k in ("battery[].open[].n_matched_phonemes", "battery[].open[].rt_from_onset_ms", "battery[].closed[].plays",
              "battery[snr].snr_estimate_kind", "battery[completed].render_log.mean_late_ms", "listen.tests[].srt_db",
              "listen.days[].minutes", "reading_days[].minutes", "participants[].b_completed_seq", "trial_log[].talker"):
        assert fields[k]["n"] > 0 and fields[k]["null_ratio"] == 0, fields[k]


def test_rehearsal_missing_media_path_and_battery_rows():
    ex = _rehearsal()["ex"]
    assert ex["version"] == 7 and ex["n"] == 5
    rows = [b for p in ex["participants"] for b in p["battery"]]
    word = [b for b in rows if b["layer"] == "word"]
    # 낱말 영상은 한 문항 건너 하나만 있다: 준비 12, 영상 준비 전 12. 응답은 준비된 문항에만
    assert word and all(b["n_items"] == 24 and b["n_ready"] == 12 and b["missing"] == {"media": 12} and len(b["closed"]) == 12
                        for b in word)
    av = [b for b in rows if b["layer"] == "av"]
    assert av and all(b["missing"] == {"media": 10} and {r["modality"] for r in b["open"]} == {"A", "AV"} for b in av)
    snr = [b for b in rows if b["layer"] == "snr"]
    assert len(snr) == 5 and all(b["snr_estimate_kind"] in ("reversals", "last_levels", "posterior40") and b["snr_calibrated_db"] is not None
                                 for b in snr)
    # 한 사람만 유지 검사(R)를 봤고 나머지는 예정일을 기다린다
    states = sorted(p["battery_schedule"]["state"] for p in ex["participants"])
    assert states == ["done", "waiting", "waiting", "waiting", "waiting"]


def test_rehearsal_analysis_runs_to_the_end():
    r = _rehearsal()
    a = r["ana"]
    pr = a["p3"]["primary"]
    assert pr["n"] == 5 and pr["estimate"] is not None and pr["lo"] < pr["estimate"] < pr["hi"]
    assert pr["verdict"] in ("support", "undecided", "refute") and sorted(pr["n_by_order"]) == ["ABC", "BCA", "CAB"]
    seq = a["p3"]["sequential"]
    assert [lk["n"] for lk in seq["looks"]] == [5] and seq["looks"][0]["bf_plus0"] > 0
    assert seq["looks"][0]["stop"] is None and seq["state"] == "continue"   # 10명 전에는 멈추지 않는다
    assert a["p3"]["retention"]["n"] == 1 and a["p3"]["retention"]["persons"][0]["days_after_b"] == 0
    assert a["p3"]["rci"] is not None and a["p3"]["av_gain"]
    lp = a["listen"]["primary"]
    assert lp["n_train"] == 3 and lp["n_control"] == 2 and lp["diff"] is not None and lp["ci"]
    assert a["listen"]["sequential"]["reached"] is False
    assert any("아바타" in w for w in a["warnings"])
    assert "순차 멈춤 규칙" in r["md"] and "소리 듣기" in r["md"]


# ── 분석 함수(합성 자료) ─────────────────────────────────
def test_order_adjusted_matches_design_simulation():
    import numpy as np
    PA, DS = _load("pilot_analyze"), _load("pilot_design_sim")
    rng = np.random.default_rng(3)
    D = rng.normal(4, 10, size=(1, 13))
    orders = [("ABC", "BCA", "CAB")[i % 3] for i in range(13)]   # 설계 모의실험과 같은 배정(i % 3)
    est, se, df, neff, _ = DS.order_adjusted(D)
    oa = PA.order_adjusted(list(D[0]), orders)
    assert math.isclose(oa["estimate"], float(est[0]), rel_tol=1e-9) and math.isclose(oa["se"], float(se[0]), rel_tol=1e-9)
    assert oa["df"] == df and math.isclose(oa["n_eff"], neff)
    # 순서가 하나뿐이거나 자유도가 없으면 계산하지 않는다
    assert PA.order_adjusted([1.0, 2.0, 3.0], ["ABC", "BCA", "CAB"])["estimate"] is None


def test_bf_plus0_matches_selfcheck_values():
    PA = _load("pilot_analyze")
    sc = json.load(open(os.path.join(HERE, "..", "docs", "pilot", "design-simulation.json"), encoding="utf-8")).get("bf_selfcheck")
    rows = [r for r in (sc or []) if r["t"] in (2.0, 3.0)]
    assert rows
    for r in rows:   # 일표본(유효 인원 n, 자유도 n − 1)에서 설계 문서의 격자 값과 같다
        assert math.isclose(PA.bf_plus0(r["t"], r["n"], r["n"] - 1), r["bfplus0_grid"], rel_tol=2e-3), r


def test_sequential_rule_stops_only_after_n_min():
    PA = _load("pilot_analyze")
    # 큰 효과: 5명에서 BF가 6을 넘어도 10명 전에는 멈추지 않고, 10명에서 지지 쪽으로 멈춘다
    rows = [{"D": 20.0 + (i % 5), "order": ("ABC", "BCA", "CAB")[i % 3], "b_seq": i + 1} for i in range(15)]
    s = PA.sequential(rows)
    assert s["looks"][0]["n"] == 5 and s["looks"][0]["stop"] is None and s["looks"][0]["bf_plus0"] > 6
    assert s["stopped"]["n"] == 10 and s["stopped"]["side"] == "support" and s["state"] == "stopped"
    assert s["stopped"]["verdict"] == "support"
    # 효과 0: 영가설 쪽 멈춤(BF ≤ 1/6) 또는 계속. 지지 쪽으로는 멈추지 않는다
    rows0 = [{"D": (-1) ** i * (3.0 + i % 4) - 1.0, "order": ("ABC", "BCA", "CAB")[i % 3], "b_seq": i + 1} for i in range(40)]
    s0 = PA.sequential(rows0)
    assert (s0["stopped"] or {}).get("side") != "support"
    # B 완료 순번 순서로 줄 세운다(순번이 없으면 빠진다)
    shuffled = list(reversed(rows)) + [{"D": 99.0, "order": "ABC", "b_seq": None}]
    assert PA.sequential(shuffled)["looks"] == s["looks"]


def test_three_way_and_listen_verdicts():
    PA = _load("pilot_analyze")
    assert PA.verdict(0.5, 9.0, 5) == "support" and PA.verdict(-1.0, 4.9, 5) == "refute" and PA.verdict(-1.0, 5.0, 5) == "undecided"
    ok = PA.listen_decision([3.0, 3.5, 4.0, 3.2], [0.5, 1.0, 0.2, 0.8])
    assert ok["verdict"] == "success" and ok["diff"] >= 2
    small = PA.listen_decision([0.2, 0.4, 0.3, 0.1], [0.3, 0.2, 0.4, 0.3])
    assert small["verdict"] == "fail"
    wide = PA.listen_decision([5.0, -2.0, 4.0], [0.0, 1.0, -1.0])
    assert wide["verdict"] == "undecided"
    assert PA.listen_decision([1.0], [])["verdict"] is None


def test_layer_score_uses_phoneme_sums_not_mean_of_ratios():
    PA = _load("pilot_analyze")
    row = {"layer": "sentence", "open": [{"n_matched_phonemes": 1, "n_target_phonemes": 10},
                                         {"n_matched_phonemes": 9, "n_target_phonemes": 10},
                                         {"n_matched_phonemes": 0, "n_target_phonemes": 20}]}
    assert PA.layer_score(row) == pytest.approx(25.0)   # (1 + 9 + 0) / 40, 문장 비율 평균(33.3)이 아니다
    assert PA.layer_score({"layer": "nonsense", "closed": [{"consonant_hits": 3}, {"consonant_hits": 0}]}) == pytest.approx(50.0)
