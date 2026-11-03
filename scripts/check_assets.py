"""배포 관문: git 밖 모델 파일의 sha256을 기록하고 기대값과 대조한다(11/03 검토 O18, M18).

- 기대값은 scripts/dev_assets.sha256.json(저장소에 둔 작은 파일)이다. 모델을 일부러 바꿀 때만 `--update`로 다시 쓴다.
- ROI 웹 모델의 meta.json이 적은 sha256이 실제 파일과 같은지도 확인한다(meta에 적기만 하고 아무도 대조하지 않았다).
- 1바이트만 달라도 실패한다. 파일 내용은 읽기만 하고 출력하지 않는다.

  python scripts/check_assets.py [--root 저장소] [--manifest 파일] [--report 결과.json] [--update]
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ASSETS = [
    "backend/models/dgop_ours/aligner/model.int8.safetensors",
    "backend/models/dgop_ours/scorer/model.int8.safetensors",
    "backend/models/dgop_stream/student_w8.onnx",
    "backend/models/dgop_stream/calibration.json",
    "backend/models/kr_a4_wavlm.pt",
    "frontend/public/models/roi/kr_lipread_roi.web.onnx",
    "frontend/public/models/roi/kr_lipread_roi.web.meta.json",
]
ROI_ONNX = "frontend/public/models/roi/kr_lipread_roi.web.onnx"
ROI_META = "frontend/public/models/roi/kr_lipread_roi.web.meta.json"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def collect(root: Path, assets=ASSETS) -> dict:
    out = {}
    for rel in assets:
        p = root / rel
        out[rel] = {"sha256": sha256_of(p), "bytes": p.stat().st_size} if p.is_file() and p.stat().st_size > 0 else None
    return out


def verify(root: Path, manifest_path: Path, assets=ASSETS) -> tuple:
    """(오류 목록, 현재 해시 표)."""
    current = collect(root, assets)
    errors = []
    for rel, info in current.items():
        if info is None:
            errors.append(f"파일이 없거나 비어 있다: {rel}")
    expected = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else None
    if expected is None:
        errors.append(f"기대 해시 파일이 없다: {manifest_path.name} (모델을 확인한 뒤 --update)")
    else:
        for rel, info in current.items():
            if info is None:
                continue
            want = expected.get(rel)
            if not want:
                errors.append(f"기대 해시에 없는 파일: {rel}")
            elif want["sha256"] != info["sha256"]:
                errors.append(f"해시가 다르다: {rel} (기대 {want['sha256'][:12]}…, 실제 {info['sha256'][:12]}…)")
    # meta가 적은 sha256과 실제 ONNX
    meta_p, onnx_p = root / ROI_META, root / ROI_ONNX
    if meta_p.is_file() and onnx_p.is_file():
        try:
            claimed = json.loads(meta_p.read_text(encoding="utf-8")).get("sha256")
        except ValueError:
            errors.append("ROI meta를 읽을 수 없다")
            claimed = None
        if claimed and current.get(ROI_ONNX) and claimed != current[ROI_ONNX]["sha256"]:
            errors.append("ROI meta의 sha256이 실제 ONNX와 다르다")
    return errors, current


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--report", default=None)
    ap.add_argument("--update", action="store_true")
    a = ap.parse_args(argv)
    root = Path(a.root)
    manifest = Path(a.manifest) if a.manifest else root / "scripts" / "dev_assets.sha256.json"
    if a.update:
        current = collect(root)
        missing = [k for k, v in current.items() if v is None]
        if missing:
            print("없는 파일이 있어 갱신하지 않는다: " + ", ".join(missing))
            return 1
        manifest.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"{manifest} 갱신: {len(current)}개")
        return 0
    errors, current = verify(root, manifest)
    if a.report:
        Path(a.report).write_text(json.dumps({"assets": current, "errors": errors}, indent=2, sort_keys=True), encoding="utf-8")
    for rel, info in current.items():
        print(f"{rel}: {info['sha256'][:16] if info else 'MISSING'}")
    if errors:
        print("ASSET_CHECK_FAILED")
        for e in errors:
            print("  - " + e)
        return 1
    print("assets match expected sha256")
    return 0


if __name__ == "__main__":
    sys.exit(main())
