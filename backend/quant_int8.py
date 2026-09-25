"""
가중치 전용 int8 양자화(2026-09-25, liplab-dev를 4GB 머신에 올리기 위한 것).

nn.Linear 가중치를 출력 채널별 대칭 int8(scale = max|w| / 127)로 저장하고, 순전파 때 fp32로 곱한다:
    y = (x · Qᵀ) ⊙ s + b
가중치 메모리는 약 1/4이 되고 활성값은 fp32 그대로라, 활성까지 int8로 바꾸는 동적 양자화보다 오차가 작다.
층마다 가중치를 잠깐 fp32로 풀기 때문에 속도 이득은 없다(목적은 메모리).

torch.ao.quantization(2.10부터 폐기 예정 경고, 맥 ARM 휠에는 양자화 엔진이 없음)과 torchao(추가 의존성)에 기대지
않으려고 직접 구현했다. backbone_service가 BACKBONE_QUANT=int8일 때 CPU의 CTC 모델(D-GOP 정렬기·채점기)에만 쓴다.
"""
from typing import Dict, Iterable

import torch
import torch.nn.functional as F
from torch import nn


class Int8Linear(nn.Module):
    """nn.Linear의 가중치를 채널별 int8로 바꾼 대체 모듈. 편향은 fp32로 둔다."""

    def __init__(self, lin: nn.Linear):
        super().__init__()
        w = lin.weight.detach().float()
        scale = w.abs().amax(dim=1).clamp(min=1e-12) / 127.0
        self.in_features = lin.in_features
        self.out_features = lin.out_features
        self.register_buffer("qweight", torch.round(w / scale[:, None]).clamp_(-127, 127).to(torch.int8))
        self.register_buffer("scale", scale)
        self.register_buffer("bias", None if lin.bias is None else lin.bias.detach().float().clone())

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        y = F.linear(x, self.qweight.to(x.dtype)) * self.scale.to(x.dtype)
        if self.bias is not None:
            y = y + self.bias.to(x.dtype)
        return y

    def extra_repr(self) -> str:
        return f"in_features={self.in_features}, out_features={self.out_features}, int8"


def _tensor_bytes(model: nn.Module) -> int:
    seen, total = set(), 0
    for t in list(model.parameters()) + list(model.buffers()):
        if t is None or id(t) in seen:
            continue
        seen.add(id(t))
        total += t.numel() * t.element_size()
    return total


def quantize_linears(model: nn.Module, skip: Iterable[str] = ("lm_head",), detach_rest: bool = True) -> Dict:
    """model 안의 nn.Linear를 Int8Linear로 바꾼다(제자리). skip은 건너뛸 모듈 이름(전체 경로 또는 마지막 이름).
    CTC 출력층(lm_head)은 기본으로 건너뛴다 — 크기가 작고, 점수가 바로 그 로짓의 softmax라서다.

    detach_rest: 남은 파라미터·버퍼(합성곱·정규화·lm_head, 모델당 약 60MB)를 복사해 체크포인트 파일 매핑과 끊는다.
    transformers는 safetensors를 mmap으로 올려 가중치가 파일 페이지로 남는데, 변환하면서 fp32 가중치를 한 번 다 읽으므로
    남은 텐서 하나라도 그 매핑을 잡고 있으면 읽은 페이지(모델당 약 1.2GB)가 프로세스 메모리에 계속 잡힌다(9/25 호스팅 점검
    int8 최대 6.2GB). 전부 복사하면 매핑이 풀린다.
    반환: {"replaced": 개수, "bytes_before": …, "bytes_after": …}"""
    skip = set(skip or ())
    before = _tensor_bytes(model)
    replaced = 0
    for parent_name, parent in list(model.named_modules()):
        for child_name, child in list(parent.named_children()):
            full = f"{parent_name}.{child_name}" if parent_name else child_name
            if type(child) is nn.Linear and child_name not in skip and full not in skip:
                setattr(parent, child_name, Int8Linear(child))
                replaced += 1
    if detach_rest:
        with torch.no_grad():
            for p in model.parameters():
                p.data = p.data.clone()
            for m in model.modules():
                for name, b in list(m._buffers.items()):
                    if b is not None and b.dtype != torch.int8:
                        m._buffers[name] = b.clone()
    model.liplab_quant = "int8"
    return {"replaced": replaced, "bytes_before": before, "bytes_after": _tensor_bytes(model)}
