"""가중치 전용 int8(quant_int8, 9/25) 테스트 — 작은 모델로 교체 범위·오차·메모리와 BACKBONE_QUANT 해석을 본다."""
import os

import pytest

torch = pytest.importorskip("torch")
from torch import nn  # noqa: E402

import backbone_service as bb  # noqa: E402
import quant_int8 as Q  # noqa: E402


class _Tiny(nn.Module):
    def __init__(self):
        super().__init__()
        self.enc = nn.Sequential(nn.Linear(64, 256), nn.GELU(), nn.Linear(256, 64))
        self.proj = nn.Linear(64, 64, bias=False)
        self.lm_head = nn.Linear(64, 12)

    def forward(self, x):
        return self.lm_head(self.proj(self.enc(x)))


def test_replaces_linears_except_lm_head_and_stays_close():
    torch.manual_seed(0)
    m = _Tiny().eval()
    x = torch.randn(5, 7, 64)
    with torch.no_grad():
        ref = m(x)
    info = Q.quantize_linears(m)
    assert info["replaced"] == 3
    assert type(m.lm_head) is nn.Linear and isinstance(m.enc[0], Q.Int8Linear) and isinstance(m.proj, Q.Int8Linear)
    assert m.proj.bias is None and m.liplab_quant == "int8"
    with torch.no_grad():
        out = m(x)
    rel = (out - ref).abs().max() / ref.abs().max()
    assert rel < 0.02
    assert info["bytes_after"] < 0.45 * info["bytes_before"]


def test_param_count_includes_int8_weights():
    m = _Tiny()
    n0 = bb._param_count(m)
    Q.quantize_linears(m)
    assert bb._param_count(m) == n0


def test_quant_mode_env(monkeypatch):
    monkeypatch.delenv("BACKBONE_QUANT", raising=False)
    assert bb.quant_mode() == ""
    monkeypatch.setenv("BACKBONE_QUANT", "INT8")
    assert bb.quant_mode() == "int8"
    monkeypatch.setenv("BACKBONE_QUANT", "int4")
    with pytest.raises(ValueError):
        bb.quant_mode()


def test_dev_config_quant_value_is_valid():
    """fly.dev.toml의 BACKBONE_QUANT가 백엔드가 받는 값이어야 한다(오타면 모델 적재에서 ValueError)."""
    import tomllib
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fly.dev.toml")
    if not os.path.exists(p):
        pytest.skip("fly.dev.toml 없음")
    with open(p, "rb") as f:
        env = tomllib.load(f).get("env", {})
    assert str(env.get("BACKBONE_QUANT", "")).strip().lower() in bb.QUANT_MODES
