"""
D-GOP 음향 백본(강제정렬) 검증 테스트 — 고도화 축 B.

align_targets·span_distribution은 log_probs·vocab에만 의존하는 순수 함수라, 실제 모델
다운로드 없이 합성 CTC 분포로 결정론적 검증이 가능하다. 모델 다운로드가 필요한
ctc_log_probs·phone_confidences는 scripts/check_ml_env.py 및 축 A 통합 시 수동 검증 대상이라
여기서 다루지 않는다.

torch/torchaudio 미설치 환경(HAS_ACOUSTIC=False)에서는 스킵한다.

실행: python3 test_dgop_acoustic.py
"""
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


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n{len(tests)}개 테스트 통과")
