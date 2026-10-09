"""608 새 화자(KSC 10/8~9 받기, 범주 28 18명)로 말하기 채점 결정 확인(docs/scoring-608-newspk-2026-10.md). 맥에서 점수 파일만 읽는다.

    python3 scripts/scoring_608_newspk.py frozen              옛 자료(10/7 정제본 V2·538 10/6)만으로 고정값을 낸다(새 화자 점수를 읽지 않음)
    python3 scripts/scoring_608_newspk.py build RUN_DIR       파드 결과 → 문장별 CSV(저장소 밖, liplab-lab/data/scores_newspk608_2026-10-09/)
    python3 scripts/scoring_608_newspk.py report [OUT.json]   다리·판정(N1~N7)·합친 값

RUN_DIR: liplab-lab/data/pod_runs/<날짜>_<파드>/ns(out/dgop_old.jsonl, dgop_new.jsonl, tscore.jsonl). 저장소에는 집계만 적는다.
"""
import collections
import csv
import hashlib
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import scoring_608_recut as RC  # noqa: E402

SA = RC.SA
auc, ff, wp, jl, hangul, sid_of = SA.auc, SA.ff, SA.wp, RC.jl, RC.hangul, RC.sid_of
LAB = RC.LAB
NEWROOT = f"{LAB}/data/scores_newspk608_2026-10-09"
V2 = f"{RC.OUTROOT}/V2"
RC_RUN = f"{LAB}/data/pod_runs/20261007_kcs2amnnqa24d7/rc"
KSC = os.path.expanduser("~/Downloads/KSC2026/liplab/data/expand")
S13 = f"{LAB}/data/pod_runs/20261006_uoqtuk2pyq0nty/s13/out"
PASS = 65.0
B = 2000
GRID01 = np.round(np.arange(0, 100.0001, 0.1), 1)


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def boot(rows, stat, seed=0):
    """화자 부트스트랩 95% 구간(세트 안에서 화자 복원 추출, 뽑힌 화자의 모든 행). 10/7 RC.boot과 같다."""
    return RC.boot(rows, stat, seed)


def metric(rs, fn):
    return [round(float(fn(rs)), 4)] + boot(rs, fn)


# ───────────────────────── 옛 자료(고정값의 출처) ─────────────────────────
def old_rows(ver):
    """ver='old': 10/7 V2 CSV(b675975, own·other·cohort·noise). ver='trim': 끝 자르기 판 own·other(538 10/6 600클립 R_trim50,
    608 V2 = 10/7 D11 trim_report와 같은 행 고르기)."""
    if ver == "old":
        SA.D = V2
        return [r for r in SA.joined()]
    rows = []
    for j in jl(f"{RC.FV}/merged/main.jsonl"):
        if j["set"] == "538" and j["variant"] == "R_trim50":
            for t in j["targets"]:
                rows.append({"set": "538", "spk": j["spk"], "half": j["half"], "clip": j["clip"],
                             "label": "own" if t["kind"] == "same" else "other", "dg": t["score"] if t["score"] is not None else 0.0})
    cs = RC.cut_sets(RC_RUN)
    rec = {}
    for f in (f"{RC.FV}/merged/main.jsonl", f"{RC.FV}/mainfix.jsonl"):
        for j in jl(f):
            if j["set"] == "608" and j["variant"] == "R_trim50":
                rec[j["clip"]] = j
    drop, acc = cs["drop"]["V2"], cs["acc"]
    for clip, j in rec.items():
        if clip in drop or clip in acc:
            continue
        own = hangul([t for t in j["targets"] if t["kind"] == "same"][0]["target"])
        for t in j["targets"]:
            if t["kind"] == "diff" and hangul(t["target"]) == own:
                continue
            rows.append({"set": "608", "spk": j["spk"], "half": j["half"], "clip": clip, "label": "own" if t["kind"] == "same" else "other",
                         "dg": t["score"] if t["score"] is not None else 0.0})
    own = {j["clip"]: hangul(j["target"]) for j in jl(f"{RC_RUN}/out/dgop_full_recut.jsonl")
           if j["set"] == "608" and j["clip"] in acc and j["kind"] == "same"}
    for j in jl(f"{RC_RUN}/out/trim_recut.jsonl"):
        if j["set"] != "608" or j["clip"] not in acc or j["kind"] not in ("same", "diff"):
            continue
        if j["kind"] == "diff" and hangul(j["target"]) == own[j["clip"]]:
            continue
        rows.append({"set": "608", "spk": j["spk"], "half": RC.half_of(j["spk"]), "clip": j["clip"],
                     "label": "own" if j["kind"] == "same" else "other", "dg": j.get("score") if j.get("score") is not None else 0.0})
    return rows


def cmd_frozen():
    os.makedirs(NEWROOT, exist_ok=True)
    out = {}
    for ver in ("old", "trim"):
        rows = [r for r in old_rows(ver) if r["label"] in ("own", "other")]
        h0 = [r for r in rows if r["half"] == 0]
        o538 = [r["dg"] for r in h0 if r["set"] == "538" and r["label"] == "other"]
        t21 = next(float(g) for g in GRID01 if wp(o538, g) <= 0.05)
        tb = SA.lowest_threshold(GRID01, lambda x: x["dg"], h0)
        all538 = [r["dg"] for r in rows if r["set"] == "538" and r["label"] == "other"]
        t_same = next(t for t in range(0, 101) if wp(all538, t) <= 0.05)
        out[ver] = {"t21_h0_538": t21, "t_both_h0": tb, "t_same_strictness_538all": t_same,
                    "n": {"538_own": sum(r["set"] == "538" and r["label"] == "own" for r in rows),
                          "608_own": sum(r["set"] == "608" and r["label"] == "own" for r in rows),
                          "608_spk": len({r["spk"] for r in rows if r["set"] == "608"})}}
    out["s1_params"] = json.load(open(f"{V2}/s1_params.json"))
    p15 = json.load(open(f"{V2}/s15_params.json"))
    out["s15_params"] = {k: v for k, v in p15.items() if not k.startswith("ecdf")}
    out["s15_noise_pass_V2"] = json.load(open(f"{V2}/s15_confirm.json"))["F1_noise_pass"]
    out["sha256"] = {"s1_params.json": sha(f"{V2}/s1_params.json"), "s15_params.json": sha(f"{V2}/s15_params.json")}
    json.dump(out, open(f"{NEWROOT}/frozen.json", "w"), ensure_ascii=False, indent=1, default=SA._np)
    print(json.dumps(out, ensure_ascii=False, indent=1, default=SA._np))


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "frozen":
        cmd_frozen()
    else:
        sys.exit(f"알 수 없는 명령 {cmd}")
