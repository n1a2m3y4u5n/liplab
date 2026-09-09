"""
D-GOP 음향 백본(강제정렬) 검증 테스트 — 고도화 축 B.

align_targets·span_distribution은 log_probs·vocab에만 의존하는 순수 함수라, 실제 모델
다운로드 없이 합성 CTC 분포로 결정론적 검증이 가능하다. 모델 다운로드가 필요한
ctc_log_probs·phone_confidences는 scripts/check_ml_env.py 및 축 A 통합 시 수동 검증 대상이라
여기서 다루지 않는다.

torch/torchaudio 미설치 환경(HAS_ACOUSTIC=False)에서는 스킵한다.

실행: python3 test_dgop_acoustic.py
"""
import json
import os
import tempfile

import dgop as D
import dgop_acoustic as DA


def _ok(cond, msg):
    assert cond, "FAIL: " + msg


# 합성 CTC 예시: vocab={blank,A,B,C}, 6프레임이 "blank A A B C blank"를 확신 있게 가리키도록 구성.
_VOCAB = {"<pad>": 0, "A": 1, "B": 2, "C": 3}
_SEQ = [0, 1, 1, 2, 3, 0]  # 프레임별 정답 라벨


def _synthetic_log_probs():
    import torch
    logits = torch.full((len(_SEQ), len(_VOCAB)), -10.0)
    for i, tid in enumerate(_SEQ):
        logits[i, tid] = 10.0
    return torch.log_softmax(logits, dim=-1)


def test_align_targets_recovers_spans():
    if not DA.HAS_ACOUSTIC:
        print("  (torch/torchaudio 미설치 → 강제정렬 테스트 스킵)")
        return
    log_probs = _synthetic_log_probs()
    spans = DA.align_targets(log_probs, _VOCAB, ["A", "B", "C"])
    by_token = {s["token"]: s for s in spans}
    _ok(by_token["A"]["start"] == 1 and by_token["A"]["end"] == 2, "A는 프레임 1~2에 정렬")
    _ok(by_token["B"]["start"] == 3 and by_token["B"]["end"] == 3, "B는 프레임 3에 정렬")
    _ok(by_token["C"]["start"] == 4 and by_token["C"]["end"] == 4, "C는 프레임 4에 정렬")


def test_align_targets_separates_repeated_tokens():
    """
    같은 토큰이 문장에 여러 번 나오면 **출현별로** 구간이 잡혀야 한다.

    2026-09-09 회귀 방지. 이전 구현은 정렬 경로를 토큰 id로 필터링해 min/max를 취했고,
    그 결과 중복 토큰의 모든 출현이 '첫 출현 시작 ~ 마지막 출현 끝'이라는 하나의 거대한
    구간으로 뭉개졌다. 자모 vocab(49토큰)에 라벨 중앙값이 103토큰이라 실제 문장에서는
    거의 항상 밟는 경로이고, 뭉개진 구간의 평균 분포는 평평해져 D-GOP가 통째로 깎인다.
    """
    if not DA.HAS_ACOUSTIC:
        print("  (torch 미설치 → 스킵)")
        return
    import torch
    # "A blank B blank A" — A가 두 번 나온다.
    seq = [1, 0, 2, 0, 1]
    logits = torch.full((len(seq), len(_VOCAB)), -10.0)
    for i, tid in enumerate(seq):
        logits[i, tid] = 10.0
    log_probs = torch.log_softmax(logits, dim=-1)

    spans = DA.align_targets(log_probs, _VOCAB, ["A", "B", "A"])
    _ok([s["token"] for s in spans] == ["A", "B", "A"], "목표 순서가 유지돼야 함")
    _ok((spans[0]["start"], spans[0]["end"]) == (0, 0),
        f"첫 A는 프레임 0 — 받음 {spans[0]}")
    _ok((spans[1]["start"], spans[1]["end"]) == (2, 2),
        f"B는 프레임 2 — 받음 {spans[1]}")
    _ok((spans[2]["start"], spans[2]["end"]) == (4, 4),
        f"둘째 A는 프레임 4 — 받음 {spans[2]}")
    # 옛 방식(id 필터 min/max)이었다면 두 A가 모두 (0, 4)로 뭉개져 B 구간까지 삼킨다.
    _ok(spans[0]["end"] < spans[1]["start"], "첫 A가 B 구간을 삼키면 안 됨")

    # 뭉개진 구간이 실제로 점수를 깎는다는 것까지 확인한다.
    smeared = DA.span_distribution(log_probs, 0, 4)      # 옛 방식이 잡던 구간
    exact = DA.span_distribution(log_probs, 0, 0)        # 자체 구현이 잡는 구간
    a_id = _VOCAB["A"]
    _ok(D.dgop_phone(exact[a_id], exact)["dgop"] > 0.9, "정확한 구간이면 D-GOP가 높다")
    _ok(D.dgop_phone(smeared[a_id], smeared)["dgop"] < 0.1,
        "뭉갠 구간은 분포가 평평해져 D-GOP가 무너진다(옛 구현의 실제 손해)")


def test_align_targets_missing_token_raises():
    if not DA.HAS_ACOUSTIC:
        print("  (torch/torchaudio 미설치 → 스킵)")
        return
    log_probs = _synthetic_log_probs()
    try:
        DA.align_targets(log_probs, _VOCAB, ["A", "Z"])
        _ok(False, "vocab에 없는 토큰은 KeyError여야 함")
    except KeyError:
        pass


def test_span_distribution_confident():
    if not DA.HAS_ACOUSTIC:
        print("  (torch/torchaudio 미설치 → 스킵)")
        return
    log_probs = _synthetic_log_probs()
    dist = DA.span_distribution(log_probs, 1, 2)  # A 구간
    _ok(dist[_VOCAB["A"]] > 0.99, "확신 분포에서 목표 토큰 확률이 거의 1")
    _ok(DA.span_distribution(log_probs, None, None) == [], "start=None이면 빈 리스트")


def test_phone_confidences_end_to_end_on_synthetic_distribution():
    if not DA.HAS_ACOUSTIC:
        print("  (torch/torchaudio 미설치 → 스킵)")
        return
    import dgop as D
    log_probs = _synthetic_log_probs()
    spans = DA.align_targets(log_probs, _VOCAB, ["A", "B", "C"])
    for span in spans:
        dist = DA.span_distribution(log_probs, span["start"], span["end"])
        target_prob = dist[_VOCAB[span["token"]]]
        result = D.dgop_phone(target_prob, dist)
        _ok(result["dgop"] > 0.9, f"확신 정렬 구간({span['token']})의 D-GOP는 높아야 함")


def _patched_ctc(mapping):
    """model_id → log_probs를 돌려주는 가짜 ctc_log_probs. 실제 모델 다운로드를 피한다."""
    def _fake(waveform, sample_rate, model_id=DA.DEFAULT_MODEL_ID):
        return mapping[model_id], _VOCAB
    return _fake


def _flat_log_probs():
    """모든 프레임이 균등분포 — 채점기가 '전혀 확신 못 하는' 상태."""
    import torch
    return torch.log_softmax(torch.zeros((len(_SEQ), len(_VOCAB))), dim=-1)


def test_scorer_distribution_wins_over_aligner():
    """구간은 정렬기가 찾고 점수는 채점기가 낸다 — 축 A 2모델 분리의 핵심 계약."""
    if not DA.HAS_ACOUSTIC:
        print("  (torch/torchaudio 미설치 → 스킵)")
        return
    orig = DA.ctc_log_probs
    try:
        DA.ctc_log_probs = _patched_ctc({"aligner": _synthetic_log_probs(),
                                         "scorer": _flat_log_probs()})
        res = DA.phone_confidences(None, 16000, ["A", "B", "C"],
                                   aligner_id="aligner", scorer_id="scorer")
        _ok(all(r["aligned"] for r in res), "정렬기가 확신 분포라 구간은 모두 잡힘")
        # 점수는 평평한 채점기 분포에서 나와야 한다 — 정렬기 분포를 썼다면 confidence가 1에 가깝다.
        _ok(all(r["confidence"] < 0.05 for r in res),
            f"채점기(균등분포)의 낮은 신뢰도가 반영돼야 함: {[r['confidence'] for r in res]}")

        # 같은 모델을 쓰면 기존 단일 모델 동작 그대로
        DA.ctc_log_probs = _patched_ctc({"solo": _synthetic_log_probs()})
        solo = DA.phone_confidences(None, 16000, ["A", "B", "C"], aligner_id="solo")
        _ok(all(r["confidence"] > 0.9 for r in solo), "단일 모델이면 확신 분포가 그대로 반영")
    finally:
        DA.ctc_log_probs = orig


def test_frame_mismatch_raises():
    """정렬기·채점기의 프레임 수가 다르면 구간을 옮길 수 없다 — 조용히 틀리지 말고 즉시 실패."""
    if not DA.HAS_ACOUSTIC:
        print("  (torch/torchaudio 미설치 → 스킵)")
        return
    import torch
    orig = DA.ctc_log_probs
    try:
        short = torch.log_softmax(torch.zeros((3, len(_VOCAB))), dim=-1)  # 6프레임이 아닌 3프레임
        DA.ctc_log_probs = _patched_ctc({"aligner": _synthetic_log_probs(), "scorer": short})
        try:
            DA.phone_confidences(None, 16000, ["A", "B", "C"],
                                 aligner_id="aligner", scorer_id="scorer")
            _ok(False, "프레임 수 불일치는 예외를 내야 함")
        except ValueError as e:
            _ok("프레임 수" in str(e), f"명확한 오류 메시지여야 함: {e}")
    finally:
        DA.ctc_log_probs = orig


def _load_calibration_fresh(path):
    """캐시를 비우고 읽는다 — 테스트끼리 앵커가 새어나가지 않도록."""
    DA._calibration_cache.clear()
    try:
        return DA.load_calibration(path)
    finally:
        DA._calibration_cache.clear()


def test_calibration_file_overrides_default():
    """체크포인트를 바꾸면 앵커도 바뀐다 — 파일이 내장 기본값을 이겨야 한다."""
    cal = D.fit_calibration([20.0, 8.0, 4.0, 2.0, 1.0], source="테스트")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(cal, f)
        path = f.name
    try:
        loaded = _load_calibration_fresh(path)
        _ok(loaded["source"] == "테스트", "파일의 앵커를 읽어야 함")
        _ok(abs(D.calibrate_score(20.0, loaded) - 90.0) < 0.05, "파일 앵커로 보정됨")
    finally:
        os.unlink(path)


def test_calibration_falls_back_when_unusable():
    """보정 파일 하나 때문에 채점이 죽으면 안 된다 — 조용히 내장 기본값으로."""
    missing = _load_calibration_fresh("/nonexistent/dgop_calibration.json")
    _ok(missing is D.DEFAULT_CALIBRATION, "없는 파일 → 내장 기본값")

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        f.write("{ 깨진 JSON")
        path = f.name
    try:
        _ok(_load_calibration_fresh(path) is D.DEFAULT_CALIBRATION, "깨진 파일 → 내장 기본값")
    finally:
        os.unlink(path)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n{len(tests)}개 테스트 통과")
