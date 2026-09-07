"""
데이터 기반 지각공간(대조학습) 검증 테스트 — 고도화 축 C.

실제 OLKAVS 시청각 특징이 없어도, 라벨(비심 그룹)별로 뭉친 합성 특징으로 학습 메커니즘
자체를 검증할 수 있다: 학습 후 같은 라벨끼리의 임베딩이 다른 라벨끼리보다 뚜렷이 가까워야
한다(대조학습이 실제로 '작동'하는지의 최소 기준). 실제 시각 혼동 구조(양순음이 서로 가깝고
연구개음과는 멀다 등)는 실제 데이터로 학습해야 나오므로 여기서는 다루지 않는다 — 이 테스트는
메커니즘 검증이지 지각공간의 내용 검증이 아니다.

torch 미설치 환경(HAS_CONTRASTIVE=False)에서는 스킵한다.

실행: python3 test_perceptual_contrastive.py
"""
import numpy as np

import perceptual_contrastive as PC


def _ok(cond, msg):
    assert cond, "FAIL: " + msg


def _synthetic_clusters(n_groups=4, per_group=15, input_dim=8, spread=0.3, seed=0):
    """비심 그룹 n_groups개, 그룹마다 뚜렷이 다른 중심 + 가우시안 잡음을 가진 합성 특징."""
    rng = np.random.default_rng(seed)
    centers = rng.uniform(-3, 3, size=(n_groups, input_dim))
    feats, labels = [], []
    for g in range(n_groups):
        feats.append(centers[g] + rng.normal(scale=spread, size=(per_group, input_dim)))
        labels.append(np.full(per_group, g))
    return np.concatenate(feats).astype(np.float32), np.concatenate(labels)


def test_training_reduces_loss():
    if not PC.HAS_CONTRASTIVE:
        print("  (torch 미설치 → 대조학습 테스트 스킵)")
        return
    feats, labels = _synthetic_clusters()
    _, history = PC.train_encoder(feats, labels, epochs=200)
    _ok(history[-1] < history[0], "학습 후 손실이 초기보다 낮아야 함")
    _ok(history[-1] < history[len(history) // 2], "학습 후반부 손실이 중반부보다 낮아야 함(계속 수렴)")


def test_embeddings_separate_by_label():
    if not PC.HAS_CONTRASTIVE:
        print("  (torch 미설치 → 스킵)")
        return
    import torch
    feats, labels = _synthetic_clusters()
    model, _ = PC.train_encoder(feats, labels, epochs=300)
    with torch.no_grad():
        z = model(torch.as_tensor(feats, dtype=torch.float32))
    intra, inter = PC.mean_intra_inter_similarity(z, labels)
    _ok(intra > inter, "학습 후 같은 라벨끼리 유사도가 다른 라벨끼리보다 높아야 함")
    _ok(intra > 0.7, f"같은 라벨끼리는 뚜렷이 뭉쳐야 함(intra={intra:.3f})")
    _ok(inter < intra - 0.3, f"라벨 간 분리가 뚜렷해야 함(intra={intra:.3f}, inter={inter:.3f})")


def test_untrained_encoder_is_worse_than_trained():
    # 학습이 실제로 기여하는지 확인 — 무작위 초기화 상태(학습 전)와 비교.
    if not PC.HAS_CONTRASTIVE:
        print("  (torch 미설치 → 스킵)")
        return
    import torch
    feats, labels = _synthetic_clusters(seed=1)
    torch.manual_seed(0)
    untrained = PC.VisemeEncoder(input_dim=feats.shape[1])
    with torch.no_grad():
        z0 = untrained(torch.as_tensor(feats, dtype=torch.float32))
    intra0, inter0 = PC.mean_intra_inter_similarity(z0, labels)
    gap0 = intra0 - inter0

    model, _ = PC.train_encoder(feats, labels, epochs=300, seed=1)
    with torch.no_grad():
        z1 = model(torch.as_tensor(feats, dtype=torch.float32))
    intra1, inter1 = PC.mean_intra_inter_similarity(z1, labels)
    gap1 = intra1 - inter1

    _ok(gap1 > gap0, f"학습 후 라벨 분리도(intra-inter)가 학습 전보다 커야 함 ({gap0:.3f} → {gap1:.3f})")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n{len(tests)}개 테스트 통과")
