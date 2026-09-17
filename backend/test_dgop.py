"""
전사 비의존 발음정확도(D-GOP) 검증 테스트 — 고도화 축 B.

핵심 논지: 뭉갠 발화에서 표준 GOP(naive)는 과신하지만, D-GOP는 예측 분포의 불확실성으로
점수를 보정해 과신을 막는다. 순수 함수라 결정론적. 외부 의존성 없음.

실행: python3 test_dgop.py
"""
import dgop as D


def _ok(cond, msg):
    assert cond, "FAIL: " + msg


def test_entropy_margin():
    _ok(D.normalized_entropy([1, 0, 0, 0]) < 0.01, "one-hot 엔트로피 ≈ 0")
    _ok(D.normalized_entropy([0.25, 0.25, 0.25, 0.25]) > 0.99, "균등분포 엔트로피 ≈ 1")
    _ok(D.top_margin([0.9, 0.05, 0.05]) > 0.8, "뾰족 분포 margin 큼")
    _ok(D.top_margin([0.25, 0.25, 0.25, 0.25]) < 0.01, "균등 분포 margin ≈ 0")


def test_confidence():
    _ok(D.phone_confidence([0.9, 0.05, 0.03, 0.02]) > 0.5, "확신 분포 신뢰도 높음")
    _ok(D.phone_confidence([0.3, 0.28, 0.22, 0.2]) < 0.15, "평평 분포 신뢰도 낮음")
    # 확신 분포가 평평 분포보다 신뢰도가 훨씬 높아야 한다(상대 비교가 핵심)
    _ok(D.phone_confidence([0.9, 0.05, 0.03, 0.02]) > 5 * D.phone_confidence([0.3, 0.28, 0.22, 0.2]),
        "확신 분포 신뢰도가 평평 분포보다 크게 높음")


def test_score_is_naive_and_confidence_is_no_longer_multiplied():
    """2026-09-15 교체 확인 — 점수는 naive 그대로이고 confidence를 곱하지 않는다(A-6)."""
    # 뭉갠 발화: 목표 확률이 낮지 않은데(0.4) 분포가 평평 → 실은 불확실
    blurry = D.dgop_phone(0.4, [0.4, 0.35, 0.15, 0.1])
    # 명료 발화: 목표 확률 높고 분포 뾰족
    clear = D.dgop_phone(0.85, [0.85, 0.1, 0.03, 0.02])
    _ok(clear["dgop"] > blurry["dgop"], "명료 발음 > 뭉갠 발음")
    _ok(blurry["dgop"] == blurry["naive"] and clear["dgop"] == clear["naive"],
        "점수는 naive 그대로 — 곱셈 항을 버렸다")
    # confidence·uncertainty는 남아 있다. 점수엔 안 쓰이고 fuse_audio_visual의 영상 가중에만 쓰인다.
    _ok(blurry["uncertainty"] > clear["uncertainty"], "뭉갠 발화의 불확실성이 더 큼")


def test_sentence_and_fuse():
    phones = [D.dgop_phone(0.8, [0.8, 0.1, 0.1]), D.dgop_phone(0.5, [0.5, 0.3, 0.2])]
    s = D.sentence_dgop(phones)
    _ok(0 <= s["score"] <= 100 and 0 <= s["uncertainty"] <= 1, "문장 집계 범위")

    low = D.fuse_audio_visual(80, 0.1, 60)
    high = D.fuse_audio_visual(80, 0.8, 60)
    _ok(high["visual_weight"] > low["visual_weight"], "음향 불확실할수록 영상 가중↑")
    _ok(D.fuse_audio_visual(80, 0.5, None)["score"] == 80, "영상 없으면 오디오 점수 그대로")


def test_calibration_hits_anchor_targets():
    """앵커로 삼은 severity 대표 원점수는 정확히 목표 점수로 나와야 한다."""
    for raw, target in zip(D.AXIS_A_SEVERITY_SCORES, D.DISPLAY_TARGETS_BY_SEVERITY):
        got = D.calibrate_score(raw)
        _ok(abs(got - target) < 0.05, f"원점수 {raw} → {target}점 (실제 {got})")


def test_calibration_range_and_edges():
    _ok(D.calibrate_score(0.0) == 0.0, "원점수 0 → 0점")
    _ok(D.calibrate_score(None) is None, "채점 불가(None)는 0점으로 둔갑하지 않음")
    _ok(all(0 <= D.calibrate_score(r) <= 100 for r in (0, 0.01, 1, 9.51, 50, 100, 1000)),
        "보정 점수는 항상 0~100")

    # 최상위 앵커에서 100점에 닿고, 그 위로는 넘지 않는다(상한 고정).
    top_raw = D.DEFAULT_CALIBRATION["anchors"][-1][0]
    _ok(D.calibrate_score(top_raw) == 100.0, "최상위 앵커 → 100점")
    _ok(D.calibrate_score(top_raw * 3) == 100.0, "앵커 초과분은 100점에서 멈춘다")

    # ⚠️ 기록해 두는 사실(2026-09-09): 100점은 **실제로는 도달 불가**하다.
    # sentence_dgop의 원점수 상한이 100인데(dgop ≤ 1 → ×100), 버그 수정으로 원점수가
    # 올라간 뒤 최상위 앵커가 raw 129로 외삽됐다. 따라서 달성 가능한 최고 표시점수는 94.9다.
    # fit_calibration의 외삽 규칙을 그대로 둔 결과다. 2026-09-09 **그대로 두기로 결정**했다 —
    # 발음 교정 앱에서 만점을 주지 않는 편이 낫다는 판단(계획서 A-5). 이 단정문이 그 결정을
    # 고정한다: 앵커가 바뀌어 100점이 도달 가능해지면 여기서 깨진다.
    _ok(top_raw > 100, f"최상위 앵커가 원점수 상한을 넘어섰다 (raw {top_raw})")
    _ok(D.calibrate_score(100.0) < 100.0,
        f"원점수 만점으로도 100점이 안 나온다 (실제 {D.calibrate_score(100.0)})")


def test_calibration_preserves_ranking():
    """보정은 단조 변환이다 — 순위가 바뀌면 변별력을 사후에 조작하는 셈이 된다."""
    raws = [0.0, 0.05, 0.1, 0.3, 0.61, 1.0, 1.49, 2.74, 5.0, 9.51, 14.0]
    scores = [D.calibrate_score(r) for r in raws]
    _ok(all(a <= b for a, b in zip(scores, scores[1:])), "원점수가 오르면 보정 점수도 오른다")
    _ok(scores[0] < scores[-1], "양끝이 실제로 벌어져 있다(상수 함수가 아님)")


def test_calibration_opens_the_scale():
    """
    A-3 한계 ②의 해결 여부 — 깨끗한 발화가 합격선을 넘고 중증 저하는 미달해야 한다.

    원점수를 하드코딩하지 않고 현재 앵커(AXIS_A_SEVERITY_SCORES)를 따라간다. 이전에는
    9.51/0.61을 박아 두었는데, 그건 구간 뭉갬 버그 시절의 severity 실측이라 버그를
    고치자 9.51이 '중등도와 중증 사이'를 뜻하게 되어 테스트가 거짓으로 깨졌다.
    """
    clean = D.calibrate_score(D.AXIS_A_SEVERITY_SCORES[0])    # severity 0
    severe = D.calibrate_score(D.AXIS_A_SEVERITY_SCORES[3])   # severity 3
    _ok(clean >= 65, f"정상 발화가 단어·문장 합격선(65) 이상 (실제 {clean})")
    _ok(severe < 50, f"중증 저하는 음소 합격선(50)에도 못 미침 (실제 {severe})")


def test_fit_drops_non_monotone_severity():
    """A-3 베이스라인처럼 severity 3→4가 역전되면 그 앵커는 버려야 한다."""
    cal = D.fit_calibration([6.65, 3.58, 2.07, 1.15, 1.25])   # 베이스라인 실측
    _ok(cal["dropped_severities"] == [4], f"역전된 severity 4가 버려짐 (실제 {cal['dropped_severities']})")
    raws = [a[0] for a in cal["anchors"]]
    disp = [a[1] for a in cal["anchors"]]
    _ok(all(a < b for a, b in zip(raws, raws[1:])), "앵커 원점수가 엄격히 증가")
    _ok(all(a < b for a, b in zip(disp, disp[1:])), "앵커 표시점수가 엄격히 증가")
    _ok(disp[-1] == 100.0 and disp[0] == 0.0, "양끝이 0점·100점")


def test_fit_rejects_unusable_input():
    for bad, why in (([9.51], "대표값이 하나뿐"), ([5.0, 5.0, 5.0], "전부 동점이라 단조가 없음")):
        try:
            D.fit_calibration(bad)
            _ok(False, f"{why}면 예외를 내야 한다")
        except ValueError:
            pass


def test_fuse_per_phone():
    # 확신 구간 + 뭉갠 구간. 뭉갠 구간이 영상(90)에 더 끌려가야(구간별 가중) 한다.
    clear = D.dgop_phone(0.9, [0.9, 0.05, 0.05])
    blurry = D.dgop_phone(0.4, [0.4, 0.33, 0.27])
    res = D.fuse_audio_visual_per_phone([clear, blurry], 90.0)
    _ok(res is not None and 0 <= res["score"] <= 100, "구간별 융합 점수 범위")
    _ok(res["per_phone"] is True and res["n_phones"] == 2, "구간별 융합 메타")
    _ok(D.fuse_audio_visual_per_phone([], 90.0) is None, "음소 없으면 None")
    _ok(D.fuse_audio_visual_per_phone([clear], None) is None, "영상 없으면 None(스칼라 경로로)")
    # 전부 확신(불확실 낮음)일 때보다 전부 뭉갤 때 영상 평균 가중이 커야 한다
    all_clear = D.fuse_audio_visual_per_phone([clear, clear], 90.0)
    all_blur = D.fuse_audio_visual_per_phone([blurry, blurry], 90.0)
    _ok(all_blur["visual_weight"] > all_clear["visual_weight"], "뭉갠 구간일수록 영상 가중↑(구간별)")


def test_fuse_per_phone_units_and_assess_text_shape():
    """
    병합 함정 고정(STATUS.md '축 B 병합 충돌 정리') — 구간별 융합은 음소 dgop(0~1)를 ×100 해서
    앵커 보정(calibrate_score, 0~100 입력)에 넣는다. 0~1을 그대로 넣으면 깨끗한 발화가 19.5점이
    되고 예외도 없다. 로지스틱 보정이 살아 있으면 severity 0·1·2가 98.0으로 포화한다.
    """
    clean_raw = D.AXIS_A_SEVERITY_SCORES[0]                     # 깨끗한 발화 원점수(0~100)
    clean = {**D.dgop_phone(clean_raw / 100.0, [0.97, 0.02, 0.01]), "uncertainty": 0.0}
    res = D.fuse_audio_visual_per_phone([clean], 90.0)
    _ok(abs(res["audio_score"] - D.DISPLAY_TARGETS_BY_SEVERITY[0]) < 0.5,
        f"깨끗한 음소의 오디오 점수는 앵커 목표(90) 근처 — 19.5나 98이면 단위/보정이 틀렸다 (실제 {res['audio_score']})")
    mild = {**D.dgop_phone(D.AXIS_A_SEVERITY_SCORES[1] / 100.0, [0.5, 0.3, 0.2]), "uncertainty": 0.0}
    res_mild = D.fuse_audio_visual_per_phone([mild], 90.0)
    _ok(res_mild["audio_score"] < res["audio_score"] - 10, "severity 0과 1이 포화 없이 구별된다")
    # 문장 단위 융합과 같은 키를 돌려준다(프론트가 audio_score·visual_score를 그대로 읽는다).
    _ok({"score", "visual_weight", "audio_score", "visual_score"} <= set(res), "fuse_audio_visual과 같은 키")

    # dgop_acoustic.assess_text의 phones 모양을 그대로 받는다 — 정렬 실패·어절 경계는 융합에서 빠진다.
    phones = [
        {"token": "o:ㄱ", "label": "ㄱ", "aligned": True, "scorable": True, **D.dgop_phone(0.8, [0.8, 0.1, 0.1])},
        {"token": "|", "label": "", "aligned": True, "scorable": False, **D.dgop_phone(0.1, [0.4, 0.3, 0.3])},
        {"token": "n:ㅏ", "label": "ㅏ", "aligned": False, "scorable": True},
    ]
    got = D.fuse_audio_visual_per_phone(phones, 60.0)
    _ok(got["n_phones"] == 1, f"채점 대상이면서 정렬된 음소만 융합 (실제 {got['n_phones']})")
    _ok(D.fuse_audio_visual_per_phone(phones[1:], 60.0) is None, "융합할 음소가 없으면 None(문장 단위 경로로)")

    # 보정 앵커를 넘기면 그 앵커로 보정한다(앱은 load_calibration()을 넘긴다).
    cal = D.fit_calibration([20.0, 8.0, 4.0, 2.0, 1.0])
    p = {**D.dgop_phone(0.20, [0.5, 0.3, 0.2]), "uncertainty": 0.0}
    _ok(abs(D.fuse_audio_visual_per_phone([p], 50.0, calibration=cal)["audio_score"] - 90.0) < 0.05,
        "calibration 인자가 반영된다")


def test_single_calibrate_score_and_raw_sentence_score():
    """calibrate_score 정의는 하나(앵커+log, 0~100 입력)이고 sentence_dgop은 원점수만 낸다."""
    import inspect
    src = inspect.getsource(D)
    _ok(src.count("def calibrate_score(") == 1, "calibrate_score가 중복 정의되지 않았다")
    _ok(list(inspect.signature(D.calibrate_score).parameters) == ["raw_score", "calibration"],
        "살아남은 정의는 앵커 보정(raw_score 0~100, calibration)")
    s = D.sentence_dgop([D.dgop_phone(0.8, [0.8, 0.1, 0.1])])
    _ok(s["score"] == 80.0 and "score_calibrated" not in s,
        "sentence_dgop.score는 원점수(0~100) — 보정은 assess_text가 calibrate_score로 한다")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n{len(tests)}개 테스트 통과")
