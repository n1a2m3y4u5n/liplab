"""발음 바꿈(대치) 잡기 작업 파일 만들기(docs/scoring-subst-2026-10.md 3절). 점수를 보지 않는다.

  python build_jobs.py explore SRULES_EXPLORE_ROOT OUT.json
      10/15 탐색 자료(538 절반 0·범주 28 절반 0·범주 27 첫 묶음)의 작업을 경로만 절대 경로로 바꿔 옮긴다(목표는 그대로, 'other'는 뺀다).
  python build_jobs.py confirm SR_CONFIRM_DIR OUT.json
      10/17 확인 자료: 538 절반 1 → 538h1(보고만), 범주 28 절반 1 → c28h1, 범주 27 두 번째 묶음(jobs_b2.json) → c27b2.
  python build_jobs.py fresh538 V1_538R_DIR EXCLUDE.json OUT.json
      538 새 화자: V1 재받기 클립(v1_538r) 가운데 EXCLUDE.json(어느 채점 자료에든 나온 538 화자)에 없는 화자. 화자마다 클립 ID 순 정렬 뒤
      random.Random(20261019)로 최대 15개, 목표는 자기 문장 + 대치(min ≤ 2, min2)로 10/15와 같은 규칙(scripts/scoring_rules/targets.py).
"""
import csv
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scoring_rules"))
BK = os.environ.get("SUB_BACKEND") or os.path.join(HERE, "..", "..", "backend")
SEED = 20261019
PER_SPK = 15


def _abs(root, jobs, rename=None, drop_other=True):
    out = []
    for j in jobs:
        j = dict(j)
        j["path"] = os.path.normpath(os.path.join(root, j["path"])) if not os.path.isabs(j["path"]) else j["path"]
        if rename:
            j["set"] = rename.get(j["set"], j["set"])
        if drop_other:
            j["targets"] = [t for t in j["targets"] if t["kind"] != "other"]
        out.append(j)
    return out


def cmd_explore(root, out):
    jobs = json.load(open(os.path.join(root, "jobs.json"), encoding="utf-8"))
    res = _abs(root, jobs)
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    print("EXPLORE_JOBS", len(res), {s: sum(1 for j in res if j["set"] == s) for s in sorted({j["set"] for j in res})})


def cmd_confirm(d, out):
    a = _abs(d, json.load(open(os.path.join(d, "jobs.json"), encoding="utf-8")), {"538": "538h1", "c28": "c28h1"})
    b = _abs(d, json.load(open(os.path.join(d, "jobs_b2.json"), encoding="utf-8")), {"c27b2": "c27b2"})
    res = a + b
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    print("CONFIRM_JOBS", len(res), {s: sum(1 for j in res if j["set"] == s) for s in sorted({j["set"] for j in res})})


def cmd_fresh538(d, exclude_path, out):
    sys.path.insert(0, BK)
    import jamo_vocab as JV
    import targets as TG
    excl = set(json.load(open(exclude_path, encoding="utf-8"))["exclude"])
    text = {}
    with open(os.path.join(d, "manifest.tsv"), encoding="utf-8") as f:
        for row in csv.reader(f, delimiter="\t"):
            if len(row) >= 3 and row[0].endswith(".mp4"):
                text[row[0][:-4]] = row[2].strip()
    clips = {}
    with open(os.path.join(d, "manifest_clips.tsv"), encoding="utf-8") as f:
        for row in csv.DictReader((l for l in f if not l.startswith("#") or l.startswith("#clip")), delimiter="\t"):
            cid = row.get("#clip") or row.get("clip")
            if cid and row["spk"] not in excl and cid in text and os.path.exists(os.path.join(d, "clips", cid + ".wav")):
                clips.setdefault(row["spk"], []).append(cid)
    rng_m = random.Random(TG.MIN_SEED)
    jobs = []
    for spk in sorted(clips):
        ids = sorted(clips[spk])
        if len(ids) > PER_SPK:
            ids = sorted(random.Random(SEED).sample(ids, PER_SPK))
        for cid in ids:
            own = text[cid]
            tg = [{"text": own, "kind": "own"}] + TG.min_targets(rng_m, own, JV)
            jobs.append({"set": "f538", "spk": spk, "clip": cid, "path": os.path.join(d, "clips", cid + ".wav"), "targets": tg})
    json.dump(jobs, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    print("FRESH538_JOBS", len(jobs), "speakers", len({j["spk"] for j in jobs}),
          "min", sum(1 for j in jobs for t in j["targets"] if t["kind"] == "min"),
          "min2", sum(1 for j in jobs for t in j["targets"] if t["kind"] == "min2"))


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "explore":
        cmd_explore(a[1], a[2])
    elif a and a[0] == "confirm":
        cmd_confirm(a[1], a[2])
    elif a and a[0] == "fresh538":
        cmd_fresh538(a[1], a[2], a[3])
    else:
        print(__doc__)
        sys.exit(2)
