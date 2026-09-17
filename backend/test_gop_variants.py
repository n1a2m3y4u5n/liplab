"""
GOP 채점식 변형 검증 — 축 B 재설계.

전부 순수 함수라 합성 분포로 결정론적으로 검증된다. 이 파일이 통과해야 GPU에서 덤프를
뜰 가치가 있다 — 채점식이 틀린 채로 특징을 덤프하면 그 GPU 시간을 통째로 버린다.

실행: PYTHONPATH=. python test_gop_variants.py
"""
import math

import gop_variants as G


def _ok(cond, msg):
    assert cond, "FAIL: " + msg


C = 6
BLANK = 0


def _dist(peak_idx, mass):
    """peak_idx에 mass를 몰아준 확률분포."""
    rest = (1.0 - mass) / (C - 1)
    p = [rest] * C
    p[peak_idx] = mass
    return p


def _span(target_id, peak_idx, mass, logit_scale=1.0):
    """세 집계(확률·로그확률·로짓)를 갖춘 구간 통계."""
    p = _dist(peak_idx, mass)
    return {
        "target_id": target_id,
        "mean_prob": p,
        "mean_logprob": [math.log(max(v, 1e-12)) for v in p],
        "mean_logit": [logit_scale * math.log(max(v, 1e-12)) for v in p],
    }


def test_all_scorers_run_and_are_finite():
    """등록된 채점식이 전부 실행되고 유한한 값을 내야 스윕이 성립한다."""
    span = _span(target_id=1, peak_idx=1, mass=0.8)
    prior = [1.0 / C] * C
    for name in G.SCORERS:
        v = G.score_span(name, span, prior=prior)
        _ok(v is not None, f"{name}이 None을 냈다")
        _ok(math.isfinite(v), f"{name}이 유한하지 않다: {v}")


def test_scorers_reward_correct_pronunciation():
    """목표에 확신 > 목표가 애매 > 다른 음소에 확신. 채점식이면 이 순서를 지켜야 한다."""
    good = _span(1, 1, 0.90)          # 목표에 확신
    vague = _span(1, 1, 0.30)         # 목표가 1등이지만 약함
    wrong = _span(1, 2, 0.90)         # 다른 음소에 확신
    prior = [1.0 / C] * C
    for name in G.SCORERS:
        # confidence: 진단용이라 목표를 보지 않는다.
        # dgop: **구 식**이라 이 순서를 지키지 못한다(그래서 제품에서 내렸다).
        #       test_production_scorer_no_longer_inverts_ranking이 그 성질을 따로 고정한다.
        if name in ("confidence", "dgop"):
            continue
        g = G.score_span(name, good, prior=prior)
        v = G.score_span(name, vague, prior=prior)
        w = G.score_span(name, wrong, prior=prior)
        _ok(g > v, f"{name}: 확신({g:.3f}) > 애매({v:.3f}) 여야 함")
        _ok(v > w, f"{name}: 애매({v:.3f}) > 오답확신({w:.3f}) 여야 함")


def test_production_scorer_no_longer_inverts_ranking():
    """
    2026-09-09에 발견한 순위 역전이 **해결됐음을 확인**한다(2026-09-15 교체).

    문제는 이랬다 — '또렷하게 다른 음소를 발음함'이 '머뭇거리지만 목표가 1등'보다 **높은
    점수**를 받았다. confidence가 분포의 뾰족함만 보고 그 봉우리가 목표 위에 있는지는 보지
    않기 때문이다. 발음 교정 앱에서 이는 치명적이다 — 확신에 차서 틀릴수록 점수가 오른다.

    제품 채점식(`dgop.dgop_phone`)은 이제 naive라 순서를 맞게 매긴다. 아래에서 그것을 확인하고,
    **구 식이 여전히 뒤집는다는 것도 함께 고정**한다 — 그게 교체의 근거였고, A-6 스윕의 비교
    기준이라 앞으로도 그 모습 그대로 남아 있어야 한다.
    """
    import dgop as D

    vague = _span(target_id=1, peak_idx=1, mass=0.30)   # 목표가 1등이지만 약함
    wrong = _span(target_id=1, peak_idx=2, mass=0.90)   # 다른 음소에 확신

    nv_v, nv_w = G.score_span("naive", vague), G.score_span("naive", wrong)
    _ok(nv_v > nv_w, f"naive는 순서를 맞게 매긴다 ({nv_v:.3f} > {nv_w:.3f})")

    # 해결 확인 — 제품이 실제로 부르는 함수로 잰다.
    pr_v = D.dgop_phone(vague["mean_prob"][1], vague["mean_prob"])["dgop"]
    pr_w = D.dgop_phone(wrong["mean_prob"][1], wrong["mean_prob"])["dgop"]
    _ok(pr_v > pr_w,
        f"제품 채점식은 더 이상 뒤집지 않는다 — 해결 확인 ({pr_v:.4f} > {pr_w:.4f})")
    # dgop_phone은 4자리로 반올림해 돌려주므로 정확히 같지는 않다(0.02 vs 0.020000000000000004).
    _ok(abs(pr_v - nv_v) < 1e-4 and abs(pr_w - nv_w) < 1e-4,
        f"제품 채점식은 naive와 같은 값을 낸다 (반올림 오차까지: {pr_v:.4f}/{nv_v:.4f}, {pr_w:.4f}/{nv_w:.4f})")

    # 교체의 근거 — 구 식은 여전히 뒤집는다(스윕 비교 기준이라 그대로 둔다).
    lg_v, lg_w = G.score_span("dgop", vague), G.score_span("dgop", wrong)
    _ok(lg_v < lg_w, f"구 식은 여전히 뒤집는다 — 교체 근거 ({lg_v:.4f} < {lg_w:.4f})")


def test_confidence_ignores_the_target():
    """
    confidence는 목표가 무엇이든 같은 값을 낸다 — 이것이 곱셈이 정보를 못 더하는 이유다.
    (scripts/analyze_dgop_redundancy.py가 재현하는 성질을 단위 수준에서 고정한다.)
    """
    a = _span(target_id=1, peak_idx=1, mass=0.9)
    b = _span(target_id=3, peak_idx=1, mass=0.9)   # 목표만 바꿈
    _ok(G.score_span("confidence", a) == G.score_span("confidence", b),
        "confidence가 목표에 의존하면 안 된다(분포만 본다)")
    # 반면 naive는 목표에 따라 달라져야 한다.
    _ok(G.score_span("naive", a) != G.score_span("naive", b), "naive는 목표에 의존해야 한다")


def test_maxlogit_survives_uniform_scaling_softmax_does_not():
    """
    로짓 기반 변형의 존재 이유 — softmax는 로짓을 통째로 낮춰도 분포가 같으면 구별하지 못한다.
    OOD(병리 발화)에서 '모든 로짓이 낮다'는 신호가 바로 과신을 드러내는 단서다.
    """
    confident = _span(1, 1, 0.9, logit_scale=1.0)
    # 같은 확률분포인데 로짓 크기만 절반 — softmax를 거치면 구별 불가
    ood = dict(confident)
    ood["mean_logit"] = [v * 0.5 for v in confident["mean_logit"]]

    _ok(G.score_span("naive", confident) == G.score_span("naive", ood),
        "softmax 기반(naive)은 로짓 크기 차이를 못 본다")
    _ok(G.score_span("dgop", confident) == G.score_span("dgop", ood),
        "구 D-GOP도 못 본다 — 세 항이 전부 softmax 안에 있다")
    _ok(G.score_span("maxlogit", confident) != G.score_span("maxlogit", ood),
        "MaxLogit은 로짓 크기 차이를 본다(이 변형을 넣는 이유)")


def test_prior_normalization_penalizes_frequent_tokens():
    """prior 정규화는 빈도가 높은 음소가 거저 점수를 받는 편향을 걷는다."""
    span = _span(1, 1, 0.8)
    flat = [1.0 / C] * C
    skewed = [0.5] + [0.5 / (C - 1)] * (C - 1)   # id 0이 흔함
    span_common = dict(span, target_id=0)
    a = G.score_span("prior_maxlogit", span_common, prior=flat)
    b = G.score_span("prior_maxlogit", span_common, prior=skewed)
    _ok(b < a, f"흔한 음소는 prior 정규화로 점수가 깎여야 함 ({b:.3f} < {a:.3f})")


def test_missing_aggregate_is_skipped_not_crashed():
    """덤프에 로짓이 없으면 로짓 기반 변형만 조용히 빠져야 한다(스윕이 죽으면 안 된다)."""
    span = {"target_id": 1, "mean_prob": _dist(1, 0.8)}
    _ok(G.score_span("naive", span) is not None, "확률 기반은 계산돼야 함")
    _ok(G.score_span("maxlogit", span) is None, "로짓이 없으면 None")
    _ok(G.score_span("gmm_gop", span) is None, "로그확률이 없으면 None")


def test_dnn_gop_without_prior_preserves_naive_ranking():
    """prior가 없으면 dnn_gop은 naive의 단조 변환이라 순위가 같아야 한다."""
    spans = [_span(1, 1, m) for m in (0.2, 0.5, 0.9)]
    nv = [G.score_span("naive", s) for s in spans]
    dn = [G.score_span("dnn_gop", s) for s in spans]
    _ok(all(a < b for a, b in zip(nv, nv[1:])), "naive가 증가")
    _ok(all(a < b for a, b in zip(dn, dn[1:])), "dnn_gop도 같은 순서")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n{len(tests)}개 테스트 통과")
