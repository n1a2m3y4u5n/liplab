"""Export installed runtime dependency closure for pip-audit, excluding unrelated test/training tools.

Run in the deployment-equivalent environment. Markers are evaluated for this machine;
this is not a substitute for auditing the final Linux image.
"""
import argparse
from importlib.metadata import distribution
from pathlib import Path
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
ROOT = Path(__file__).resolve().parents[1]


def export(requirements, additional=()):
    queue=[]
    for filename in requirements:
        for line in Path(filename).read_text(encoding="utf-8").splitlines():
            line=line.split("#",1)[0].strip()
            if line: queue.append(Requirement(line))
    queue.extend(Requirement(x) for x in additional)
    seen=set(); packages={}
    while queue:
        req=queue.pop()
        if req.marker and not req.marker.evaluate(): continue
        key=(canonicalize_name(req.name),tuple(sorted(req.extras)))
        if key in seen: continue
        seen.add(key)
        dist=distribution(req.name)  # Missing dependency fails closed.
        if req.specifier and not req.specifier.contains(dist.version):
            raise RuntimeError(f"Installed {req.name}=={dist.version} does not satisfy {req.specifier}")
        packages[canonicalize_name(dist.metadata["Name"])]=dist.version
        for dependency in dist.requires or []:
            child=Requirement(dependency)
            if not child.marker or any(child.marker.evaluate({"extra":e}) for e in ["",*req.extras]):
                child.marker=None
                queue.append(child)
    return "".join(f"{name}=={version}\n" for name,version in sorted(packages.items()))

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--output",required=True);p.add_argument("--inference",action="store_true");a=p.parse_args()
    files=[ROOT/"backend/requirements.txt"]
    if a.inference: files.append(ROOT/"backend/requirements-infer.txt")
    additional=[]
    if a.inference:
        # Docker에서 CPU torch는 추론 requirements와 별도로 설치한다.
        import re
        torch_version=re.search(r"torch==([0-9.]+)", (ROOT/"Dockerfile").read_text(encoding="utf-8")).group(1)
        additional.append("torch=="+torch_version)
    Path(a.output).write_text(export(files, additional),encoding="utf-8")
