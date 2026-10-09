"""맥: 608 새 화자 확인 파드 작업 목록(docs/scoring-608-newspk-2026-10.md 2·3절). 점수는 읽지 않는다(목표 문장·조각 목록·소리만).

  ~/Downloads/liplab/backend/.venv/bin/python scripts/newspk608_pod/build.py STAGE_DATA_DIR
만드는 것(STAGE_DATA_DIR, 저장소 밖):
  jobs.json      클립마다 (목표, 종류) 목록. 종류 same(자기 문장) / diff(다른 문장 2) / cohort(반례 8)
  n608/*.wav     KSC 조각 340개의 APFS 복제(cp -c, 원본은 읽기만)
  c538n/*.wav    538 새 화자 스냅숏 600클립의 복제(10/6 S13 jobs.json과 같은 클립·같은 짝)
  bridge608/*.wav  다리용 옛 608 조각 3개(10/6 세션 FLAC에서 10/6과 같은 방식으로 자름)
"""
import json
import os
import random
import re
import subprocess
import sys

LAB = os.path.expanduser("~/Downloads/liplab-lab")
KSC = os.path.expanduser("~/Downloads/KSC2026/liplab/data/expand")
S13 = f"{LAB}/data/pod_runs/20261006_uoqtuk2pyq0nty/s13/out"
SC = f"{LAB}/data/pod_runs/20261006_35zrgz6wvrqiho/sc/out"
V1_538 = f"{LAB}/data/v1_538/clips"
WAV16 = f"{LAB}/data/hi608/wav16"
K_COHORT = 8
MAX_LEN = 20.0


def hangul(s):
    return re.sub(r"[^가-힣]", "", s or "")


def clip_id(c):
    return f"{c['file'][:-5]}:{c['si']:03d}"


def ok_len(x, n):
    return 0.7 * n <= len(hangul(x)) <= 1.3 * n


def clone(src, dst):
    """APFS 복제. 원본을 옮기거나 덮어쓰지 않는다."""
    if not os.path.exists(dst):
        subprocess.run(["cp", "-c", src, dst], check=True)


def main():
    out = sys.argv[1]
    for d in ("n608", "c538n", "bridge608"):
        os.makedirs(f"{out}/{d}", exist_ok=True)
    # ── 608 새 화자: KSC 정제·화자 상한 뒤 340조각(new_clips.json keep), 목표는 cuts_chosen.json의 대본 문장
    keep = {k: v for k, v in json.load(open(f"{KSC}/new_clips.json", encoding="utf-8")).items() if v["keep"]}
    cuts = {clip_id(c): c for c in json.load(open(f"{KSC}/pod_out/cuts_chosen.json", encoding="utf-8")) if c.get("cut")}
    items608 = []
    for cid in sorted(keep):
        c = cuts[cid]
        assert c["end"] - c["start"] <= MAX_LEN, cid
        src = f"{KSC}/cuts_wav/{cid.replace(':', '_')}.wav"
        dst = f"{out}/n608/{cid.replace(':', '_')}.wav"
        clone(src, dst)
        items608.append({"set": "608", "spk": keep[cid]["spk"], "clip": cid, "path": f"n608/{os.path.basename(dst)}", "own": c["target"]})
    # 다른 문장 2개: 10/6 build_jobs와 같은 규칙(풀 = 자기 문장 목록, 중복 포함, 음절 수 ±30%, random.sample, Random(0))
    # + 한글만 남긴 문자열이 자기 문장과 같은 후보는 뺀다(docs/scoring-analyses-2026-10.md 8.3절과 같은 규칙)
    rng = random.Random(0)
    pool = [it["own"] for it in items608]
    for it in items608:
        t, n = it["own"], len(hangul(it["own"]))
        cand = [x for x in pool if x != t and hangul(x) != hangul(t) and ok_len(x, n)]
        it["targets"] = [[t, "same"]] + [[x, "diff"] for x in rng.sample(cand, min(2, len(cand)))]
    # ── 538 새 화자: 10/6 S13 jobs.json의 538 행 그대로(스냅숏 21명, Random(0)으로 섞은 앞 600, 같은 짝 규칙)
    J = json.load(open(f"{S13}/jobs.json", encoding="utf-8"))
    by538, order538 = {}, []
    for r in J["s18"]:
        if r["set"] != "538":
            continue
        if r["clip"] not in by538:
            by538[r["clip"]] = {"set": "538", "spk": r["spk"], "clip": r["clip"], "path": f"c538n/{r['clip']}.wav", "targets": []}
            order538.append(r["clip"])
            clone(f"{V1_538}/{r['clip']}.wav", f"{out}/c538n/{r['clip']}.wav")
        by538[r["clip"]]["targets"].append([r["target"], r["kind"]])
    items538 = [by538[c] for c in order538]
    for it in items538:
        it["own"] = next(t for t, k in it["targets"] if k == "same")
    # 반례 8개: 10/6 build_jobs 추가 1과 같은 규칙(Random(1) 하나를 608 → 538 순으로, 풀 = 세트 안 문장의 정렬된 집합,
    # 평가 짝과 겹치지 않음, 음절 수 ±30%) + 한글만 남긴 문자열이 자기 문장과 같은 후보는 뺀다(10/7 A2와 같은 뜻)
    rng2 = random.Random(1)
    for items in (items608, items538):
        pool = sorted({it["own"] for it in items})
        for it in items:
            used = {t for t, _ in it["targets"]}
            t, n = it["own"], len(hangul(it["own"]))
            cand = [x for x in pool if x not in used and hangul(x) != hangul(t) and ok_len(x, n)]
            it["targets"] += [[x, "cohort"] for x in rng2.sample(cand, min(K_COHORT, len(cand)))]
    # ── 다리: 옛 608 조각 3개(10/7 다리와 같은 고르기: 20초 이하 조각 이름 순 처음·가운데·끝), 10/6 목표(자기·다른 2)
    import soundfile as sf
    old = [c for c in json.load(open(f"{SC}/cuts608.json", encoding="utf-8")) if c.get("cut")]
    tg = {}
    for l in open(f"{SC}/dgop_full.jsonl", encoding="utf-8"):
        j = json.loads(l)
        if j["set"] == "608" and j["kind"] in ("same", "diff"):
            tg.setdefault(j["clip"], []).append([j["target"], j["kind"]])
    short = sorted(clip_id(c) for c in old if c["end"] - c["start"] <= MAX_LEN)
    byid = {clip_id(c): c for c in old}
    bridge = []
    for k in (0, len(short) // 2, len(short) - 1):
        c = byid[short[k]]
        y, sr = sf.read(f"{WAV16}/{c['file']}")
        assert sr == 16000
        p = f"bridge608/{short[k].replace(':', '_')}.wav"
        sf.write(f"{out}/{p}", y[int(c["start"] * sr):int(c["end"] * sr)], sr)
        bridge.append({"set": "bridge608", "spk": c["file"].split("-")[4], "clip": short[k], "path": p, "targets": tg[short[k]]})
    jobs = items608 + items538 + bridge
    for it in jobs:
        it.pop("own", None)
    json.dump(jobs, open(f"{out}/jobs.json", "w"), ensure_ascii=False, indent=0)
    from collections import Counter
    cnt = Counter((it["set"], k) for it in jobs for _, k in it["targets"])
    short_cohort = sum(1 for it in items608 + items538 if sum(k == "cohort" for _, k in it["targets"]) < K_COHORT)
    print("BUILD_OK", dict(cnt), "spk608", len({it["spk"] for it in items608}), "spk538", len({it["spk"] for it in items538}),
          "clips_cohort_lt8", short_cohort)


if __name__ == "__main__":
    main()
