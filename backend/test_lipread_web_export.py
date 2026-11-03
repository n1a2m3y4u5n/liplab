"""묶음 D: 후보 내보내기 스크립트의 가드와 정규화, 결합 4지 채점 함수의 입력 계약(합성 입력). 무거운 모듈이 없으면 건너뛴다."""
import os
import sys

import numpy as np
import pytest

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, os.path.join(SCRIPTS, "lipread_roi"))
import lipread_web_export as X  # noqa: E402


def test_normalize64_is_zero_mean_unit_rms():
    roi = np.random.default_rng(0).integers(0, 256, (75, 80, 80)).astype(np.float32)
    z = X.normalize64(roi)
    assert z.dtype == np.float32 and abs(float(z.mean())) < 1e-4 and abs(float(np.sqrt((z.astype(np.float64) ** 2).mean())) - 1) < 1e-3


def test_normalize64_clamps_flat_input():
    z = X.normalize64(np.full((10, 80, 80), 128, np.float32))
    assert np.isfinite(z).all() and float(np.abs(z).max()) == 0.0


def test_greedy_ctc_collapse():
    logits = np.eye(5)[[1, 1, 0, 1, 2, 2, 0, 3]]
    assert X.greedy(logits) == [1, 1, 2, 3]


@pytest.mark.skipif(not X.CANDIDATES["C65"]["onnx"].is_file(), reason="등록 ONNX가 이 PC에 없다")
def test_export_aborts_when_pt_is_not_the_registered_one(tmp_path, capsys):
    fake = tmp_path / "model.pt"
    fake.write_bytes(b"not the registered checkpoint")
    assert X.main(["--pt", str(fake), "--out", str(tmp_path / "o")]) == 1
    assert "EXPORT_ABORT" in capsys.readouterr().out


def test_score4_onnx_fusion_requires_both_inputs(tmp_path):
    onnx = pytest.importorskip("onnx")
    ort = pytest.importorskip("onnxruntime")
    torch = pytest.importorskip("torch")
    import roi_train as R
    from onnx import helper, TensorProto
    # roi_z만 받는 그래프는 결합 채점을 거부한다
    node = helper.make_node("ReduceMean", ["roi_z"], ["logits"], axes=[2, 3], keepdims=0)
    g = helper.make_graph([node], "g", [helper.make_tensor_value_info("roi_z", TensorProto.FLOAT, ["B", "T", 80, 80])],
                          [helper.make_tensor_value_info("logits", TensorProto.FLOAT, ["B", "T"])])
    m = helper.make_model(g, opset_imports=[helper.make_opsetid("", 13)])
    m.ir_version = 8
    p = tmp_path / "single.onnx"
    onnx.save(m, str(p))
    with pytest.raises(AssertionError):
        R.score4_onnx_fusion(str(p), [None], [{"spk": "a"}], None, None)
