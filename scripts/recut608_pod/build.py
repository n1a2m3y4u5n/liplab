"""맥: 다시 자르기 파드 작업 목록(docs/scoring-608-recut-2026-10.md 2.5·3·4.3절). 점수는 읽지 않는다(목표 문장·조각 시각·지연 표본 이름만).

  python3 scripts/recut608_pod/build.py OUT_DATA_DIR
만드는 것: jobs.json(다시 자를 25조각과 10/6 목표 목록), bridge.json(다리 608 3·538 3), lat.json(지연 표본 정의)
입력: 10/6 파드 원자료(cuts608.json, dgop_full.jsonl), S4 지연 결과(표본 이름만), S4 E1 행(자기 문장)
"""
import json
import os
import sys

LAB = os.path.expanduser("~/Downloads/liplab-lab")
SC = f"{LAB}/data/pod_runs/20261006_35zrgz6wvrqiho/sc/out"
S4 = f"{LAB}/data/pod_runs/20261007_ubn4h922kfnx03/s4/out"
E1 = f"{LAB}/data/s16stage/root/" + "ev" + "al/e1_rows.jsonl"
MAX_LEN = 20.0


def clip_id(c):
    return f"{c['file'][:-5]}:{c['si']:03d}"


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    cuts = [c for c in json.load(open(f"{SC}/cuts608.json", encoding="utf-8")) if c.get("cut")]
    assert len(cuts) == 363
    targets = {}
    for l in open(f"{SC}/dgop_full.jsonl", encoding="utf-8"):
        j = json.loads(l)
        if j["set"] in ("608", "538") and j["kind"] in ("same", "diff", "cohort"):
            targets.setdefault((j["set"], j["clip"]), []).append([j["target"], j["kind"]])
    long_ = [c for c in cuts if c["end"] - c["start"] > MAX_LEN]
    word = [c for c in long_ if "-01-01-" in c["file"]]
    recut = [c for c in long_ if "-01-01-" not in c["file"]]
    assert len(long_) == 34 and len(word) == 9 and len(recut) == 25, (len(long_), len(word), len(recut))
    jobs = [{"clip": clip_id(c), "file": c["file"], "si": c["si"], "spk": c["file"].split("-")[4], "start": c["start"], "end": c["end"],
             "ratio": c["ratio"], "target": c["target"], "targets": targets[("608", clip_id(c))]} for c in recut]
    json.dump(jobs, open(f"{out}/jobs.json", "w"), ensure_ascii=False, indent=1)
    # 다리: 다시 자르지 않는 608 조각 3개(이름 순 등간격)와 538 지연 표본의 앞 3개. 목표는 자기 문장·다른 문장 2개
    lat = json.load(open(f"{S4}/lat_H_w8_t2.json"))
    short = sorted(clip_id(c) for c in cuts if c["end"] - c["start"] <= MAX_LEN)
    by = {clip_id(c): c for c in cuts}
    br = []
    for k in (0, len(short) // 2, len(short) - 1):
        c = by[short[k]]
        br.append({"set": "608", "clip": short[k], "file": c["file"], "spk": c["file"].split("-")[4], "start": c["start"], "end": c["end"],
                   "targets": [t for t in targets[("608", short[k])] if t[1] in ("same", "diff")]})
    own = {}
    for l in open(E1, encoding="utf-8"):
        r = json.loads(l)
        if r["kind"] == "same":
            own[(r["set"], r["clip"])] = (r["target"], r["spk"])
    s538 = [r["clip"] for r in lat["rows"] if r["set"] == "538"]
    for clip in s538[:3]:
        br.append({"set": "538", "clip": clip, "spk": own[("538", clip)][1],
                   "targets": [t for t in targets[("538", clip)] if t[1] in ("same", "diff")]})
    json.dump(br, open(f"{out}/bridge.json", "w"), ensure_ascii=False, indent=1)
    L = {"s538": [{"clip": c, "own": own[("538", c)][0]} for c in s538],
         "e1_608": [{"clip": clip_id(c), "file": c["file"], "start": c["start"], "end": c["end"], "own": own[("608", clip_id(c))][0]} for c in cuts],
         "wordlist": [clip_id(c) for c in word], "recut25": [clip_id(c) for c in recut],
         "orig100_608": [r["clip"] for r in lat["rows"] if r["set"] == "608"]}
    assert len(L["s538"]) == 50 and len(L["orig100_608"]) == 50
    json.dump(L, open(f"{out}/lat.json", "w"), ensure_ascii=False, indent=1)
    need538 = sorted(set(s538))
    json.dump({"c538": need538, "sessions": sorted({c["file"] for c in cuts})}, open(f"{out}/need.json", "w"))
    print("BUILD_OK jobs", len(jobs), "bridge", len(br), "lat538", len(s538), "sessions", len({c['file'] for c in cuts}))


if __name__ == "__main__":
    main()
