"""배포 관문 보조 스크립트(scripts/check_assets.py, check_config.py)의 단위 시험. 관문의 pytest가 함께 돌린다."""
import json
import os
import subprocess
import sys

import pytest

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
sys.path.insert(0, SCRIPTS)
import check_assets  # noqa: E402
import check_config  # noqa: E402


def _fake_root(tmp_path):
    for rel in check_assets.ASSETS:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(json.dumps({"name": rel}).encode() if rel.endswith(".json") else b"model-" + rel.encode())
    return tmp_path


def test_assets_update_then_verify_then_one_byte_fails(tmp_path):
    root = _fake_root(tmp_path)
    manifest = root / "m.json"
    assert check_assets.main(["--root", str(root), "--manifest", str(manifest), "--update"]) == 0
    assert check_assets.main(["--root", str(root), "--manifest", str(manifest)]) == 0
    target = root / check_assets.ASSETS[2]
    data = bytearray(target.read_bytes())
    data[0] ^= 1                                   # 1바이트만 바꾼다
    target.write_bytes(bytes(data))
    errors, _ = check_assets.verify(root, manifest)
    assert any("해시가 다르다" in e and check_assets.ASSETS[2] in e for e in errors)
    assert check_assets.main(["--root", str(root), "--manifest", str(manifest)]) == 1


def test_assets_missing_file_and_missing_manifest(tmp_path):
    root = _fake_root(tmp_path)
    errors, _ = check_assets.verify(root, root / "none.json")
    assert any("기대 해시 파일이 없다" in e for e in errors)
    (root / check_assets.ASSETS[0]).unlink()
    errors, _ = check_assets.verify(root, root / "none.json")
    assert any("파일이 없거나 비어 있다" in e for e in errors)


def test_roi_meta_sha_must_match_onnx(tmp_path):
    root = _fake_root(tmp_path)
    (root / check_assets.ROI_META).write_text(json.dumps({"sha256": "0" * 64}), encoding="utf-8")
    manifest = root / "m.json"
    check_assets.main(["--root", str(root), "--manifest", str(manifest), "--update"])
    errors, _ = check_assets.verify(root, manifest)
    assert any("ROI meta" in e for e in errors)


def test_config_dockerfile_arg_defaults_parse():
    text = "FROM x\nARG WITH_ML=0\nARG DGOP_MODEL=kresnik\nARG DGOP_STREAM=0\nARG NODEFAULT\n"
    assert check_config.dockerfile_arg_defaults(text) == {"WITH_ML": "0", "DGOP_MODEL": "kresnik", "DGOP_STREAM": "0", "NODEFAULT": None}


def _git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=cwd, check=True, capture_output=True)


def test_config_invariants_detect_flytoml_and_arg_changes(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "fly.toml").write_text('app = "liplab"\n', encoding="utf-8", newline="\n")
    (tmp_path / "Dockerfile").write_text("ARG WITH_ML=0\n", encoding="utf-8", newline="\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    assert check_config.check(tmp_path, "HEAD") == []
    (tmp_path / "Dockerfile").write_text("ARG WITH_ML=1\n", encoding="utf-8", newline="\n")
    errs = check_config.check(tmp_path, "HEAD")
    assert any("WITH_ML" in e for e in errs)
    (tmp_path / "Dockerfile").write_text("ARG WITH_ML=0\nRUN echo hi\n", encoding="utf-8", newline="\n")
    assert check_config.check(tmp_path, "HEAD") == []                      # ARG 기본값이 같으면 다른 줄은 허용
    (tmp_path / "fly.toml").write_text('app = "liplab"\n[x]\n', encoding="utf-8", newline="\n")
    assert any("fly.toml" in e for e in check_config.check(tmp_path, "HEAD"))
