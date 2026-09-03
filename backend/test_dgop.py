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


def test_dgop_vs_naive_overconfidence():
    # 뭉갠 발화: 목표 확률이 낮지 않은데(0.4) 분포가 평평 → 실은 불확실
    blurry = D.dgop_phone(0.4, [0.4, 0.35, 0.15, 0.1])
    # 명료 발화: 목표 확률 높고 분포 뾰족
    clear = D.dgop_phone(0.85, [0.85, 0.1, 0.03, 0.02])
    _ok(clear["dgop"] > blurry["dgop"], "명료 발음 D-GOP > 뭉갠 발음")
    _ok(blurry["naive"] > blurry["dgop"], "뭉갠 발화는 naive보다 D-GOP가 낮음(과신 보정)")
    _ok(blurry["uncertainty"] > clear["uncertainty"], "뭉갠 발화의 불확실성이 더 큼")


def test_sentence_and_fuse():
    phones = [D.dgop_phone(0.8, [0.8, 0.1, 0.1]), D.dgop_phone(0.5, [0.5, 0.3, 0.2])]
    s = D.sentence_dgop(phones)
    _ok(0 <= s["score"] <= 100 and 0 <= s["uncertainty"] <= 1, "문장 집계 범위")

    low = D.fuse_audio_visual(80, 0.1, 60)
    high = D.fuse_audio_visual(80, 0.8, 60)
    _ok(high["visual_weight"] > low["visual_weight"], "음향 불확실할수록 영상 가중↑")
    _ok(D.fuse_audio_visual(80, 0.5, None)["score"] == 80, "영상 없으면 오디오 점수 그대로")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n{len(tests)}개 테스트 통과")
