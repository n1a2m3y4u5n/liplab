"""538 새 화자 고르기 등록 전 점검(docs/scoring-subst-2026-10.md 3.5절). 점수는 읽지 않고 'spk숫자' 문자열만 센다(읽기만, 줄 단위).

  python spk_scan.py scan OUT_SCAN.json            데스크탑 두 자료 뿌리를 훑어 폴더별 538 화자 ID
  python spk_scan.py exclude OUT_SCAN.json OUT.json  v1_538r·roi538을 뺀 모든 폴더의 화자 합집합 → {"exclude": [...]}
"""
import collections
import gzip
import json
import os
import re
import sys

PAT = re.compile(r"spk(\d{3})")
ROOTS = [r"D:\liplab\mac_archive\liplab-lab\data", r"D:\liplab\lab\data"]
SKIP_EXT = {".wav", ".flac", ".mp4", ".npy", ".npz", ".pt", ".png", ".jpg", ".onnx", ".safetensors", ".bin", ".tar", ".zip", ".mp3", ".webm"}
KEEP = ("v1_538r", "roi538")   # 후보 클립이 있는 폴더(독화 전용)


def scan(out):
    by = collections.defaultdict(set)
    for root in ROOTS:
        tag = "archive" if "mac_archive" in root else "lab"
        for dp, _dn, fn in os.walk(root):
            rel = os.path.relpath(dp, root).split(os.sep)
            top = rel[0] if rel[0] != "." else "_"
            key = f"{tag}:{top}" if top != "pod_runs" or len(rel) < 2 else f"{tag}:pod_runs/{rel[1]}"
            for f in fn:
                for m in PAT.finditer(f):
                    by[key].add(m.group(1))
                if os.path.splitext(f)[1].lower() in SKIP_EXT:
                    continue
                p = os.path.join(dp, f)
                try:
                    if os.path.getsize(p) > 300 * 2 ** 20:
                        continue
                    op = gzip.open if f.endswith(".gz") else open
                    with op(p, "rt", encoding="utf-8", errors="ignore") as fh:
                        for line in fh:
                            for m in PAT.finditer(line):
                                by[key].add(m.group(1))
                except Exception:
                    pass
    res = {k: sorted(v) for k, v in by.items() if v}
    json.dump(res, open(out, "w"), indent=0)
    for k in sorted(res):
        print(k, len(res[k]))


def exclude(scan_path, out):
    res = json.load(open(scan_path))
    ex = set()
    for k, v in res.items():
        top = k.split(":", 1)[-1].split("/")[0]
        if top not in KEEP:
            ex |= {"spk" + x for x in v}
    json.dump({"exclude": sorted(ex), "rule": "v1_538r·roi538 밖 모든 폴더에 나온 538 화자"}, open(out, "w"), indent=0)
    print("EXCLUDE", len(ex))


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "scan":
        scan(a[1])
    elif a and a[0] == "exclude":
        exclude(a[1], a[2])
    else:
        print(__doc__)
        sys.exit(2)
