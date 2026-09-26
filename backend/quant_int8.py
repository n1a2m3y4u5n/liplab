"""
가중치 전용 int8 양자화(2026-09-25, liplab-dev를 4GB 머신에 올리기 위한 것).

nn.Linear 가중치를 출력 채널별 대칭 int8(scale = max|w| / 127)로 저장하고, 순전파 때 fp32로 곱한다:
    y = (x · Qᵀ) ⊙ s + b
가중치 메모리는 약 1/4이 되고 활성값은 fp32 그대로라, 활성까지 int8로 바꾸는 동적 양자화보다 오차가 작다.
층마다 가중치를 잠깐 fp32로 풀기 때문에 속도 이득은 없다(목적은 메모리).

torch.ao.quantization(2.10부터 폐기 예정 경고, 맥 ARM 휠에는 양자화 엔진이 없음)과 torchao(추가 의존성)에 기대지
않으려고 직접 구현했다. backbone_service가 BACKBONE_QUANT=int8일 때 CPU의 CTC 모델(D-GOP 정렬기·채점기)에만 쓴다.

미리 변환한 파일(9/26): export_ctc()가 변환 결과를 model.int8.safetensors로 저장하고 load_ctc()가 그 파일을 바로 올린다.
fp32 가중치(모델당 1.26GB)를 읽지 않으므로 읽는 양이 약 0.36GB로 준다. 호스팅 기계의 루트 파일시스템은 초당 약 17MB라
(9/26 liplab-dev 실측) 켜질 때마다 모델당 76초를 fp32 읽기에 썼다. 저장하는 텐서는 quantize_linears() 결과 그대로라
실행 중 변환과 값이 비트 단위로 같다(test_quant_int8.py, scripts/export_int8.py가 확인).
"""
import os
import shutil
from typing import Dict, Iterable, Iterator, Tuple

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

    @classmethod
    def empty(cls, in_features: int, out_features: int, bias: bool, device="meta") -> "Int8Linear":
        """값 없이 모양만 있는 틀. load_ctc()가 저장된 텐서를 이 자리에 그대로 넣는다."""
        self = cls.__new__(cls)
        nn.Module.__init__(self)
        self.in_features = in_features
        self.out_features = out_features
        self.register_buffer("qweight", torch.empty(out_features, in_features, dtype=torch.int8, device=device))
        self.register_buffer("scale", torch.empty(out_features, dtype=torch.float32, device=device))
        self.register_buffer("bias", torch.empty(out_features, dtype=torch.float32, device=device) if bias else None)
        return self

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


def _linear_targets(model: nn.Module, skip: Iterable[str]) -> Iterator[Tuple[nn.Module, str, nn.Linear]]:
    """int8로 바꿀 nn.Linear(부모, 이름, 모듈). quantize_linears()와 load_ctc()가 같은 규칙을 쓰게 한 곳에 둔다."""
    skip = set(skip or ())
    for parent_name, parent in list(model.named_modules()):
        for child_name, child in list(parent.named_children()):
            full = f"{parent_name}.{child_name}" if parent_name else child_name
            if type(child) is nn.Linear and child_name not in skip and full not in skip:
                yield parent, child_name, child


def quantize_linears(model: nn.Module, skip: Iterable[str] = ("lm_head",), detach_rest: bool = True) -> Dict:
    """model 안의 nn.Linear를 Int8Linear로 바꾼다(제자리). skip은 건너뛸 모듈 이름(전체 경로 또는 마지막 이름).
    CTC 출력층(lm_head)은 기본으로 건너뛴다 — 크기가 작고, 점수가 바로 그 로짓의 softmax라서다.

    detach_rest: 남은 파라미터·버퍼(합성곱·정규화·lm_head, 모델당 약 60MB)를 복사해 체크포인트 파일 매핑과 끊는다.
    transformers는 safetensors를 mmap으로 올려 가중치가 파일 페이지로 남는데, 변환하면서 fp32 가중치를 한 번 다 읽으므로
    남은 텐서 하나라도 그 매핑을 잡고 있으면 읽은 페이지(모델당 약 1.2GB)가 프로세스 메모리에 계속 잡힌다(9/25 호스팅 점검
    int8 최대 6.2GB). 전부 복사하면 매핑이 풀린다.
    반환: {"replaced": 개수, "bytes_before": …, "bytes_after": …}"""
    before = _tensor_bytes(model)
    replaced = 0
    for parent, child_name, child in list(_linear_targets(model, skip)):
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


INT8_FILE = "model.int8.safetensors"
_FP32_FILES = ("model.safetensors", "model.safetensors.index.json", "pytorch_model.bin", "pytorch_model.bin.index.json")
_SKIP_COPY = _FP32_FILES + ("training_args.bin", "optimizer.pt", "scheduler.pt", "rng_state.pth", "trainer_state.json")


def has_int8(model_dir: str) -> bool:
    return os.path.isfile(os.path.join(model_dir, INT8_FILE))


def has_fp32(model_dir: str) -> bool:
    return any(os.path.isfile(os.path.join(model_dir, n)) for n in _FP32_FILES)


def export_ctc(src_dir: str, out_dir: str, skip: Iterable[str] = ("lm_head",)) -> Dict:
    """fp32 CTC 체크포인트 폴더 → int8 폴더(model.int8.safetensors + config·전처리 파일). 반환: quantize_linears() 결과 + 파일 크기."""
    from safetensors.torch import save_file
    from transformers import AutoModelForCTC
    skip = tuple(skip or ())
    model = AutoModelForCTC.from_pretrained(src_dir).eval()
    info = quantize_linears(model, skip=skip)
    os.makedirs(out_dir, exist_ok=True)
    for name in sorted(os.listdir(src_dir)):
        src = os.path.join(src_dir, name)
        if os.path.isfile(src) and name not in _SKIP_COPY and not name.startswith("."):
            shutil.copy2(src, os.path.join(out_dir, name))
    sd = {k: v.detach().contiguous() for k, v in model.state_dict().items()}
    path = os.path.join(out_dir, INT8_FILE)
    save_file(sd, path, metadata={"liplab_quant": "int8", "format": "1", "skip": ",".join(skip)})
    os.chmod(path, 0o644)   # save_file은 600으로 만든다. 이미지 안에서 다른 사용자로 돌아도 읽히게
    info["file_bytes"] = os.path.getsize(path)
    return info


def load_ctc(model_dir: str) -> nn.Module:
    """export_ctc()로 만든 폴더를 fp32 가중치 없이 올린다. 모델 틀은 meta 장치에 만들고(메모리·시간 0), 선형층을 Int8Linear
    틀로 바꾼 뒤 저장된 텐서를 그대로 넣는다. 파일은 한 번에 끝까지 읽어 일반 메모리에 둔다(파일 매핑이 남으면 첫 추론 때
    느린 디스크에서 다시 읽는다)."""
    from safetensors.torch import load as st_load
    from transformers import AutoConfig, AutoModelForCTC
    path = os.path.join(model_dir, INT8_FILE)
    with open(path, "rb") as f:
        raw = f.read()
    meta = _read_metadata(raw)
    if meta.get("liplab_quant") != "int8":
        raise ValueError(f"{path}: liplab int8 파일이 아니다(metadata={meta})")
    skip = tuple(x for x in meta.get("skip", "").split(",") if x)
    config = AutoConfig.from_pretrained(model_dir)
    with torch.device("meta"):
        model = AutoModelForCTC.from_config(config)
    for parent, child_name, child in list(_linear_targets(model, skip)):
        setattr(parent, child_name, Int8Linear.empty(child.in_features, child.out_features, child.bias is not None))
    sd = st_load(raw)
    del raw
    model.load_state_dict(sd, strict=True, assign=True)
    left = [n for n, t in list(model.named_parameters()) + list(model.named_buffers()) if t is not None and t.is_meta]
    if left:
        raise RuntimeError(f"{path}: 값이 안 채워진 텐서 {len(left)}개(예: {left[:3]})")
    model.eval()
    for p in model.parameters():
        p.requires_grad_(False)
    model.liplab_quant = "int8"
    model.liplab_quant_from = "file"
    return model


def _read_metadata(raw: bytes) -> Dict:
    """safetensors 머리(8바이트 길이 + JSON)의 __metadata__만 읽는다."""
    import json
    import struct
    n = struct.unpack("<Q", raw[:8])[0]
    return json.loads(raw[8:8 + n].decode("utf-8")).get("__metadata__") or {}

