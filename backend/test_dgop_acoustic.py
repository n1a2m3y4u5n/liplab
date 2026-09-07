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


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n{len(tests)}개 테스트 통과")
