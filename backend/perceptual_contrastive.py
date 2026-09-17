"""
데이터 기반 지각공간 — 고도화 축 C의 학습 가능한 부분.

`perceptual.py`(C.1~C.2)는 비심 규칙만으로 동구형이음 사전·난이도 지수를 결정론적으로
도출한다. 계획서 3.3은 그 위에 실제 시청각 데이터로 학습한 지각공간(대조학습)을 얹어
수작업 계수를 대체하는 것을 목표로 한다: "같은 비심은 가깝게, 다른 비심은 멀게" 배치되도록
음소 구간의 입모양 시퀀스를 인코딩한다.

이 모듈은 그 학습 메커니즘(인코더 + SupCon 대조손실)을 구현한다. 실제 OLKAVS 시청각
특징이 없어도 인코더·손실함수 자체는 '입력 특징 벡터 → 임베딩'이라는 일반 형태라 결정론적
검증이 가능하다: 라벨(비심 그룹)별로 뭉친 합성 특징을 넣었을 때 학습 후 같은 라벨끼리
더 가까워지는지 확인한다(test_perceptual_contrastive.py). 실제 OLKAVS 프레임 특징이
확보되면 `encode_dataset`에 (특징, 비심 라벨) 쌍만 흘려보내면 된다 — 인코더·손실은 그대로.

torch는 requirements-ml.txt 전용 의존성이다(앱 런타임에는 불필요).

정직한 한계. 여기서 학습한 임베딩을 `perceptual.py`의 채점 계수로 실제 대체하는 배선은
하지 않는다 — 합성 데이터로 학습한 모델을 실제 채점에 쓰면 안 되기 때문이다. 실제 OLKAVS로
학습한 뒤에만 연결한다.
"""
from typing import List, Sequence, Tuple

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    HAS_CONTRASTIVE = True
except Exception:  # torch 미설치
    HAS_CONTRASTIVE = False


if HAS_CONTRASTIVE:
    class VisemeEncoder(nn.Module):
        """
        입모양 구간 특징 벡터 → 정규화된 임베딩. 실제 축 A 통합 시 입력은 AV-HuBERT/영상
        인코더가 뽑은 프레임 특징의 요약(예: 평균 풀링)이 되고, 이 인코더는 그 위에 얹는
        가벼운 투영 헤드 역할을 한다(대조학습 실무에서 흔한 구조).
        """
        def __init__(self, input_dim: int, embed_dim: int = 32, hidden_dim: int = 64):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(input_dim, hidden_dim),
                nn.ReLU(),
                nn.Linear(hidden_dim, embed_dim),
            )

        def forward(self, x):
            z = self.net(x)
            return F.normalize(z, dim=-1)


def supervised_contrastive_loss(embeddings, labels, temperature: float = 0.1):
    """
    SupCon(Khosla et al. 2020) 손실 — 같은 라벨(비심 그룹) 임베딩은 가깝게,
    다른 라벨은 멀게 당긴다. embeddings: (N, D) L2정규화됨, labels: (N,) 정수.
    """
    if not HAS_CONTRASTIVE:
        raise RuntimeError("torch 미설치 — backend/requirements-ml.txt 설치 필요")
    device = embeddings.device
    n = embeddings.shape[0]
    sim = embeddings @ embeddings.T / temperature  # (N, N) 코사인 유사도(정규화됨)

    labels = labels.view(-1, 1)
    same_label = (labels == labels.T).float().to(device)
    self_mask = torch.eye(n, device=device)
    positive_mask = same_label - self_mask  # 자기 자신 제외한 같은 라벨

    # 수치 안정화: 행별 최댓값을 빼고 자기 자신은 -inf로 마스킹
    sim = sim - sim.max(dim=1, keepdim=True).values.detach()
    exp_sim = torch.exp(sim) * (1 - self_mask)
    log_prob = sim - torch.log(exp_sim.sum(dim=1, keepdim=True) + 1e-12)

    pos_count = positive_mask.sum(dim=1)
    has_positive = pos_count > 0
    mean_log_prob_pos = (positive_mask * log_prob).sum(dim=1)[has_positive] / pos_count[has_positive]
    return -mean_log_prob_pos.mean()


def train_encoder(features, labels, embed_dim: int = 32, epochs: int = 200,
                   lr: float = 1e-2, temperature: float = 0.1, seed: int = 0):
    """
    (특징, 비심 라벨) 쌍으로 VisemeEncoder를 학습한다. features: (N, input_dim) 텐서/배열,
    labels: (N,) 정수 배열. 반환: 학습된 모델과 손실 이력(감소 추세 확인용).
    """
    if not HAS_CONTRASTIVE:
        raise RuntimeError("torch 미설치 — backend/requirements-ml.txt 설치 필요")
    torch.manual_seed(seed)
    x = torch.as_tensor(features, dtype=torch.float32)
    y = torch.as_tensor(labels, dtype=torch.long)

    model = VisemeEncoder(input_dim=x.shape[1], embed_dim=embed_dim)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)

    history = []
    for _ in range(epochs):
        optimizer.zero_grad()
        z = model(x)
        loss = supervised_contrastive_loss(z, y, temperature=temperature)
        loss.backward()
        optimizer.step()
        history.append(float(loss.item()))
    return model, history


def mean_intra_inter_similarity(embeddings, labels) -> Tuple[float, float]:
    """검증용: 같은 라벨끼리 평균 코사인 유사도 vs 다른 라벨끼리 평균 코사인 유사도."""
    sim = (embeddings @ embeddings.T).detach()
    labels = torch.as_tensor(labels).view(-1, 1)
    same = (labels == labels.T)
    n = sim.shape[0]
    self_mask = torch.eye(n, dtype=torch.bool)
    intra = sim[same & ~self_mask].mean().item()
    inter = sim[~same].mean().item()
    return intra, inter
