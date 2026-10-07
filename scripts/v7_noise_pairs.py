"""V7 0단계(가7): 538에서 같은 인물이 여러 소음 환경을 녹음했는지 센다. 설계는 docs/v7-clear-speech-2026-10.md.

538 파일 이름(lip_<묶음>_<소음환경>_<성별>_<나이대>_<인물>_<시점>_<대본>)에서 인물 번호와 소음 환경을 읽는다. 맥에 남은
manifest·받기 기록(liplab-lab/data 아래의 tsv·log·out·json)만 읽고, 받기 중인 작업 폴더(.work)와 받기 프로세스는 건드리지 않는다.
출력은 집계(인물 수, 소음 환경별 인물 수, 둘 이상의 환경을 가진 인물 수)뿐이다.

  python3 scripts/v7_noise_pairs.py [--root ~/Downloads/liplab-lab/data] [--json out.json]
"""
import argparse
import json
import os
import re

NAME_RE = re.compile(r"lip_([A-Z])_(\d)_([MF])_(\d+)_([CE]\d+)_([A-Z])_(\d+)")
EXTS = (".tsv", ".log", ".out", ".txt", ".json")
SKIP_DIRS = {".work", "clips", "__pycache__", "bs_real", "bs_render", "bs_v13", "renders"}
MIN_PAIRED = 30   # 가7 0단계: 조건 쌍이 있는 화자가 30명 이상일 때만 진행


def scan(root):
    seen = set()
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            if not fn.endswith(EXTS):
                continue
            p = os.path.join(dp, fn)
            try:
                if os.path.getsize(p) > 50_000_000:
                    continue
                with open(p, encoding="utf-8", errors="ignore") as f:
                    for m in NAME_RE.finditer(f.read()):
                        seen.add(m.group(0))
            except OSError:
                continue
    return seen


def summarize(names):
    envs, sex, group = {}, {}, {}
    for n in names:
        g, env, sx, _age, person, _view, _scr = NAME_RE.fullmatch(n).groups()
        envs.setdefault(person, set()).add(int(env))
        sex.setdefault(person, set()).add(sx)
        group.setdefault(person, set()).add(g)
    by_env = {}
    for p, es in envs.items():
        for e in es:
            by_env[e] = by_env.get(e, 0) + 1
    multi = sorted(p for p, es in envs.items() if len(es) > 1)
    env_group = {}
    for p, es in envs.items():
        for e in es:
            for g in group[p]:
                env_group.setdefault(f"{g}_{e}", set()).add(p)
    return {
        "n_files": len(names),
        "n_persons": len(envs),
        "n_persons_C": sum(1 for p in envs if p.startswith("C")),
        "n_persons_E": sum(1 for p in envs if p.startswith("E")),
        "persons_by_env": dict(sorted(by_env.items())),
        "persons_by_group_env": {k: len(v) for k, v in sorted(env_group.items())},
        "n_persons_multi_env": len(multi),
        "n_persons_multi_sex": sum(1 for s in sex.values() if len(s) > 1),
        "min_paired": MIN_PAIRED,
        "step0_pass": len(multi) >= MIN_PAIRED,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.expanduser("~/Downloads/liplab-lab/data"))
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    s = summarize(scan(a.root))
    print(json.dumps(s, ensure_ascii=False, indent=1))
    if a.json:
        json.dump(s, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
