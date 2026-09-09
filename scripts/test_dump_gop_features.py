"""
GOP 특징 덤프 배관 검증 — GPU·체크포인트 없이.

이 스크립트의 GPU 실행은 12분·$1이다. 배관 오류를 Pod에서 처음 만나면 그 값을 버린다.
특히 **perturb 모드는 자모 vocab 체크포인트가 있어야만 동작**해서 로컬 스모크로는
검증되지 않는다(공개 체크포인트는 음절 vocab이다). 그래서 모델 순전파를 가짜로 바꿔
collect()를 그대로 통과시킨다.

실행: python scripts/test_dump_gop_features.py
"""
import importlib.util
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "backend"))
sys.path.insert(0, _HERE)

import jamo_vocab as JV  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "dump_gop_features", os.path.join(_HERE, "dump_gop_features.py"))
D = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(D)


def _ok(cond, msg):
    assert cond, "FAIL: " + msg


SENT = "학교에서 국물을 먹었습니다"
_TOKENS = JV.text_to_tokens(SENT)


def _fake_outputs(waveform, sample_rate, model_id=None):
    """자모 vocab 모델을 흉내 낸다 — 목표열이 또렷하게 나오도록 로짓을 구성."""
    import torch
    T = max(len(_TOKENS) * 4, 64)
    torch.manual_seed(0)
    logits = torch.randn(T, JV.VOCAB_SIZE) * 0.5
    # 토큰을 순서대로 배치해 강제정렬이 자연스럽게 풀리도록 한다.
    seg = T // len(_TOKENS)
    for k, tok in enumerate(_TOKENS):
        s, e = k * seg, min(T, (k + 1) * seg)
        logits[s:e, JV.VOCAB[tok]] += 8.0
    return torch.log_softmax(logits, dim=-1), logits, dict(JV.VOCAB)


def _patched(fn_tokens):
    import dgop_acoustic as DA
    DA.ctc_outputs = _fake_outputs
    DA.tokens_for_text = fn_tokens


def test_severity_mode_collects_all_conditions():
    _patched(lambda text, model_id=None: list(_TOKENS))
    rows = D._smoke_rows(n=2)
    recs, meta = D.collect(rows, "fake", "fake", "severity", [], 1.0, 0, verbose=False)
    _ok(recs, "레코드가 비어 있으면 안 됨")
    conds = {r["cond"] for r in recs}
    _ok(conds == {f"sev{s}" for s in D.SEVERITIES},
        f"severity 5개 조건이 전부 있어야 함 — 받음 {sorted(conds)}")
    _ok(meta["mode"] == "severity", "meta에 모드가 기록돼야 함")


def test_perturb_mode_produces_perturbed_conditions():
    """이 프로젝트에서 로컬로 검증 불가능했던 경로 — 자모 vocab을 가짜로 만들어 통과시킨다."""
    _patched(lambda text, model_id=None: list(_TOKENS))
    rows = D._smoke_rows(n=2)
    rules = ["coda_deletion", "vowel_centralization"]
    recs, _ = D.collect(rows, "fake", "fake", "perturb", rules, 1.0, 0, verbose=False)
    conds = {r["cond"] for r in recs}
    _ok("clean" in conds, "정답 목표열 조건이 있어야 비교가 성립")
    for r in rules:
        _ok(r in conds, f"오염 조건 {r}이 수집돼야 함 — 받음 {sorted(conds)}")
    # 오염 조건에서도 구간이 실제로 잡혀야 한다.
    for r in rules:
        _ok(sum(1 for x in recs if x["cond"] == r) > 0, f"{r}의 구간이 0개")


def test_perturb_rejects_non_jamo_vocab():
    """음절 vocab으로 perturb를 돌리면 12분 뒤가 아니라 즉시 실패해야 한다."""
    _patched(lambda text, model_id=None: ["학", "교", "|", "에"])
    rows = D._smoke_rows(n=1)
    try:
        D.collect(rows, "fake", "fake", "perturb", ["coda_deletion"], 1.0, 0, verbose=False)
        _ok(False, "자모가 아니면 ValueError여야 함")
    except ValueError as e:
        _ok("자모" in str(e), f"원인을 알려줘야 함 — 받음 {e}")


def test_spans_contain_no_blank_frames():
    """
    불변: 구간 안에 blank 프레임이 없다(ctc_align.token_spans가 run만 잡으므로).
    이게 깨지면 Cao et al. 2024의 blank 제외 논점이 그때부터 유효해진다.
    """
    _patched(lambda text, model_id=None: list(_TOKENS))
    rows = D._smoke_rows(n=2)
    recs, _ = D.collect(rows, "fake", "fake", "severity", [], 1.0, 0, verbose=False)
    bad = [r for r in recs if r["nb_frames"] != r["frames"]]
    _ok(not bad, f"구간 {len(bad)}개에 blank가 섞였다 — 정렬 방식이 바뀌었는지 확인")


def test_npz_roundtrip_keeps_what_sweep_needs():
    """저장→로드 후 스윕이 쓰는 키가 전부 살아 있어야 한다."""
    import tempfile
    import numpy as np
    _patched(lambda text, model_id=None: list(_TOKENS))
    rows = D._smoke_rows(n=2)
    recs, meta = D.collect(rows, "fake", "fake", "severity", [], 1.0, 0, verbose=False)
    path = os.path.join(tempfile.mkdtemp(), "f.npz")
    D.save_npz(recs, meta, path)
    d = np.load(path, allow_pickle=True)
    for k in ("mean_prob", "mean_logprob", "mean_logit", "target_id",
              "utt", "cond", "frames", "nb_frames", "meta_mode"):
        _ok(k in d, f"npz에 {k}가 없다 — 스윕이 읽지 못한다")
    _ok(d["mean_prob"].shape[1] == JV.VOCAB_SIZE, "vocab 차원이 보존돼야 함")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n{len(tests)}개 테스트 통과")
