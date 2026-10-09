"""S20 묶음 만들기(맥, docs/speak-intelligibility-index-2026-10.md 2절). 소리를 자르고 복사하기만 한다(모델 없음).

  python scripts/s20_pod/build.py <묶음 root>

O(기존 정제본 V2, 15명 341조각): 10/6 cuts608.json의 시작·끝, 다시 자른 12조각은 10/7 recut.json의 시작·끝으로 원본 세션 FLAC에서 자른다
(10/6·10/7과 같은 y[int(a*sr):int(b*sr)] → sf.write). N(새 화자 18명 340조각): KSC cuts_wav를 cp -c로 복사한다(원본은 읽기만).
조각 목록 root/data/clips.json(조각 ID·묶음·화자·절반·성별·대본·경로). 이 목록과 소리는 lab 묶음 폴더와 파드에만 둔다.
"""
import csv
import json
import os
import re
import subprocess
import sys
import zlib

import numpy as np
import soundfile as sf

LAB = os.path.expanduser(os.environ.get("LAB", "~/Downloads/liplab-lab"))
KSC = os.path.expanduser("~/Downloads/KSC2026/liplab/data/expand")
V2 = f"{LAB}/data/scores_recut_2026-10-07/V2/dgop_pairs.csv"
CUTS_1006 = f"{LAB}/data/pod_runs/20261006_35zrgz6wvrqiho/sc/out/cuts608.json"
RECUT = f"{LAB}/data/pod_runs/20261007_kcs2amnnqa24d7/rc/out/recut.json"
WAV16 = f"{LAB}/data/hi608/wav16"
SR = 16000
MIN_CLIPS = 5


def half(spk):
    return zlib.crc32(spk.encode()) % 2


def sex_of(stem):
    m = re.search(r"-(M|F)-\d+-", stem)
    return m.group(1) if m else None


def main(root):
    d = f"{root}/data"
    os.makedirs(f"{d}/clips/O", exist_ok=True)
    os.makedirs(f"{d}/clips/N", exist_ok=True)
    clips = []
    # ── O ──
    own = [r for r in csv.DictReader(open(V2)) if r["set"] == "608" and r["label"] == "own"]
    c608 = {}
    for c in json.load(open(CUTS_1006)):
        if c.get("cut"):
            c608[f"{c['file'][:-5]}:{c['si']:03d}"] = c
    rec = {r["clip"]: r for r in json.load(open(RECUT)) if r.get("accepted")}
    by_file = {}
    for r in own:
        cid = r["clip"]
        base = c608[cid]
        st, en = (rec[cid]["start"], rec[cid]["end"]) if cid in rec else (base["start"], base["end"])
        assert int(r["half"]) == half(r["spk"]), cid
        by_file.setdefault(base["file"], []).append((cid, r["spk"], base["target"], st, en, cid in rec))
    for f, items in sorted(by_file.items()):
        y, sr = sf.read(f"{WAV16}/{f}", dtype="float32")
        if y.ndim > 1:
            y = y.mean(axis=1)
        assert sr == SR, (f, sr)
        for cid, spk, tgt, st, en, rc in items:
            rel = f"clips/O/{cid.replace(':', '_')}.wav"
            sf.write(f"{d}/{rel}", y[int(st * SR):int(en * SR)], SR)
            clips.append({"clip": cid, "set": "O", "spk": spk, "half": half(spk), "sex": sex_of(f[:-5]), "target": tgt,
                          "path": rel, "dur": round(en - st, 3), "recut": rc})
    # ── N ──
    meta = json.load(open(f"{KSC}/new_clips.json"))
    tg = {}
    for line in open(f"{KSC}/new_targets.jsonl"):
        t = json.loads(line)
        if t["kind"] == "own":
            tg[t["clip"]] = t
    for cid, m in sorted(meta.items()):
        if not m["keep"]:
            continue
        stem, idx = cid.rsplit(":", 1)
        src = f"{KSC}/cuts_wav/{stem}_{idx}.wav"
        rel = f"clips/N/{stem}_{idx}.wav"
        dst = f"{d}/{rel}"
        if not os.path.exists(dst):
            subprocess.run(["cp", "-c", src, dst], check=True)
        info = sf.info(dst)
        assert info.samplerate == SR and info.channels == 1, (src, info.samplerate, info.channels)
        t = tg[cid]
        assert t["spk"] == m["spk"] and int(t["half"]) == half(m["spk"]), cid
        clips.append({"clip": cid, "set": "N", "spk": m["spk"], "half": half(m["spk"]), "sex": sex_of(stem), "target": t["target"],
                      "path": rel, "dur": round(info.frames / SR, 3), "recut": False})
    # 포함 조건(조각 5개 이상)
    n_by = {}
    for c in clips:
        n_by[c["spk"]] = n_by.get(c["spk"], 0) + 1
    drop = sorted(s for s, n in n_by.items() if n < MIN_CLIPS)
    clips = [c for c in clips if c["spk"] not in drop]
    json.dump(clips, open(f"{d}/clips.json", "w"), ensure_ascii=False, indent=0)
    summ = {}
    for c in clips:
        k = f"{c['set']}{c['half']}"
        summ.setdefault(k, set()).add(c["spk"])
    print("BUILD clips", len(clips), "O", sum(c["set"] == "O" for c in clips), "N", sum(c["set"] == "N" for c in clips),
          "recut", sum(c["recut"] for c in clips), "drop", drop, {k: len(v) for k, v in sorted(summ.items())},
          "sex_missing", sum(c["sex"] is None for c in clips))


if __name__ == "__main__":
    main(sys.argv[1])
