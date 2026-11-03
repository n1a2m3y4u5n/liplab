"""배포 관문: 전시앱 설정(fly.toml)과 Dockerfile ARG 기본값이 기준 판과 같은지 git으로 대조한다(11/03 검토 O19).
기본 기준은 origin/main이다. 의도해서 바꿀 때는 관문을 -AllowConfigChange로 돌린다.
또 관문이 본 커밋·트리·작업트리 변경 여부를 gate-meta.json에 남긴다(deploy_dev.ps1이 배포 직전에 대조한다, O18).

  python scripts/check_config.py [--root 저장소] [--base origin/main] [--meta gate-meta.json]
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def _git(root, *args):
    r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout


def dockerfile_arg_defaults(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        m = re.match(r"^\s*ARG\s+([A-Za-z_][A-Za-z0-9_]*)(?:=(.*))?\s*$", line)
        if m:
            out[m.group(1)] = m.group(2).strip() if m.group(2) is not None else None
    return out


def check(root: Path, base: str) -> list:
    errors = []
    rc, _ = _git(root, "rev-parse", "--verify", "--quiet", base + "^{commit}")
    if rc != 0:
        return [f"기준 판 {base}을(를) 찾을 수 없다"]
    rc, old_fly = _git(root, "show", f"{base}:fly.toml")
    new_fly = (root / "fly.toml").read_text(encoding="utf-8") if (root / "fly.toml").is_file() else None
    if rc == 0 and new_fly is not None and old_fly.replace("\r\n", "\n") != new_fly.replace("\r\n", "\n"):
        errors.append(f"fly.toml(전시앱)이 {base}와 다르다")
    rc, old_df = _git(root, "show", f"{base}:Dockerfile")
    if rc == 0:
        old = dockerfile_arg_defaults(old_df)
        new = dockerfile_arg_defaults((root / "Dockerfile").read_text(encoding="utf-8"))
        for k in sorted(set(old) | set(new)):
            if old.get(k, "<없음>") != new.get(k, "<없음>"):
                errors.append(f"Dockerfile ARG {k} 기본값이 바뀌었다: {old.get(k, '<없음>')} → {new.get(k, '<없음>')}")
    return errors


def meta(root: Path) -> dict:
    _, head = _git(root, "rev-parse", "HEAD")
    _, tree = _git(root, "rev-parse", "HEAD^{tree}")
    _, status = _git(root, "status", "--porcelain", "--untracked-files=no")
    return {"commit": head.strip(), "tree": tree.strip(), "tracked_changes": [l for l in status.splitlines() if l.strip()]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--meta", default=None)
    ap.add_argument("--allow-change", action="store_true")
    a = ap.parse_args(argv)
    root = Path(a.root)
    errors = [] if a.allow_change else check(root, a.base)
    m = meta(root)
    m["base"] = a.base
    m["config_errors"] = errors
    if a.meta:
        Path(a.meta).write_text(json.dumps(m, indent=2), encoding="utf-8")
    print(f"commit {m['commit'][:10]} tree {m['tree'][:10]} tracked_changes={len(m['tracked_changes'])}")
    if errors:
        print("CONFIG_CHECK_FAILED")
        for e in errors:
            print("  - " + e)
        return 1
    print("fly.toml and Dockerfile ARG defaults unchanged vs " + a.base)
    return 0


if __name__ == "__main__":
    sys.exit(main())
