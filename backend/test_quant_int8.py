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


def _tiny_ctc_dir(root):
    """작은 wav2vec2 CTC 체크포인트(fp32)와 전처리 파일을 root에 만든다(내려받지 않음)."""
    import json
    transformers = pytest.importorskip("transformers")
    torch.manual_seed(0)
    cfg = transformers.Wav2Vec2Config(
        vocab_size=8, hidden_size=32, num_hidden_layers=2, num_attention_heads=2, intermediate_size=64,
        conv_dim=(16, 16), conv_stride=(5, 2), conv_kernel=(10, 3), num_conv_pos_embeddings=8,
        num_conv_pos_embedding_groups=2, do_stable_layer_norm=True, feat_extract_norm="layer")
    model = transformers.Wav2Vec2ForCTC(cfg).eval()
    src = os.path.join(root, "src")
    model.save_pretrained(src)
    vocab = os.path.join(root, "vocab.json")
    with open(vocab, "w", encoding="utf-8") as f:
        json.dump({"<pad>": 0, "<unk>": 1, "|": 2, "ㄱ": 3, "ㅏ": 4, "ㄴ": 5, "ㅣ": 6, "ㅁ": 7}, f)
    tok = transformers.Wav2Vec2CTCTokenizer(vocab, unk_token="<unk>", pad_token="<pad>", word_delimiter_token="|")
    fe = transformers.Wav2Vec2FeatureExtractor(feature_size=1, sampling_rate=16000, padding_value=0.0,
                                               do_normalize=True, return_attention_mask=True)
    transformers.Wav2Vec2Processor(feature_extractor=fe, tokenizer=tok).save_pretrained(src)
    return src


def test_export_then_load_is_bit_identical_to_runtime_quantization(tmp_path):
    """미리 변환한 파일(export_ctc → load_ctc)이 실행 중 변환(quantize_linears)과 텐서·출력 모두 비트 단위로 같아야 한다."""
    from transformers import AutoModelForCTC
    src = _tiny_ctc_dir(str(tmp_path))
    out = os.path.join(str(tmp_path), "int8")
    info = Q.export_ctc(src, out)
    assert Q.has_int8(out) and not Q.has_fp32(out) and Q.has_fp32(src)
    assert os.path.isfile(os.path.join(out, "config.json")) and os.path.isfile(os.path.join(out, "vocab.json"))
    assert info["replaced"] > 0 and info["file_bytes"] < os.path.getsize(os.path.join(src, "model.safetensors"))

    ref = AutoModelForCTC.from_pretrained(src).eval()
    Q.quantize_linears(ref)
    got = Q.load_ctc(out)
    assert got.liplab_quant == "int8" and got.liplab_quant_from == "file"
    assert type(got.lm_head) is nn.Linear and isinstance(got.wav2vec2.encoder.layers[0].attention.q_proj, Q.Int8Linear)
    a, b = ref.state_dict(), got.state_dict()
    assert a.keys() == b.keys()
    for k in a:
        assert a[k].dtype == b[k].dtype and torch.equal(a[k], b[k]), k
    x = torch.randn(1, 4000)
    with torch.no_grad():
        assert torch.equal(ref(x).logits, got(x).logits)


def test_backbone_loads_int8_file_without_fp32(tmp_path, monkeypatch):
    """int8 파일만 있는 폴더는 BACKBONE_QUANT와 상관없이 그 파일로 올리고, 상태에 quant·quant_from을 남긴다."""
    src = _tiny_ctc_dir(str(tmp_path))
    out = os.path.join(str(tmp_path), "int8")
    Q.export_ctc(src, out)
    monkeypatch.delenv("BACKBONE_QUANT", raising=False)
    bb.clear()
    try:
        proc, model = bb.load(out, "ctc", "cpu")
        assert proc is not None and model.liplab_quant_from == "file"
        row = bb.status()["loaded"][0]
        assert row["quant"] == "int8" and row["quant_from"] == "file"
        # fp32가 함께 있으면 BACKBONE_QUANT가 int8일 때만 파일을 쓴다
        _, m2 = bb._load_ctc(src, "cpu")
        assert getattr(m2, "liplab_quant", None) is None
    finally:
        bb.clear()


def test_dev_config_auto_stop_value_is_valid():
    """fly.dev.toml의 auto_stop_machines는 fly가 받는 값이어야 한다(9/26부터 "suspend")."""
    import tomllib
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fly.dev.toml")
    if not os.path.exists(p):
        pytest.skip("fly.dev.toml 없음")
    with open(p, "rb") as f:
        svc = tomllib.load(f).get("http_service", {})
    assert svc.get("auto_stop_machines") in ("off", "stop", "suspend", True, False)
