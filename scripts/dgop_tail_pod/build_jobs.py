"""측정 작업 목록 만들기(맥, 네트워크 없음). docs/dgop-final-vowel-2026-10.md 3절.

    python build_jobs.py SC_OUT SCORES_CSV SOUND_DIR STAGE_DATA

SC_OUT: 10/6 파드 결과(liplab-lab/data/pod_runs/20261006_35zrgz6wvrqiho/sc/out, dgop_full.jsonl·cuts608.json),
SCORES_CSV: liplab-lab/data/scores_2026-10-06/dgop_pairs.csv(608 화자 절반), SOUND_DIR: backend/data/sound.
STAGE_DATA/jobs.jsonl: 538·608 클립마다 자기 문장(same)과 10/6과 같은 다른 문장 2개(diff). 538 절반은 crc32(화자) % 2.
STAGE_DATA/tts_jobs.jsonl: 서버 음성 m1·f2의 문장 클립(한글 5음절 이상). 원자료는 앱 저장소에 넣지 않는다.
"""
import csv
import json
import os
import re
import sys
import zlib

sc_out, scores_csv, sound_dir, stage = sys.argv[1:5]
os.makedirs(stage, exist_ok=True)
half608 = {}
for r in csv.DictReader(open(scores_csv)):
    if r["set"] == "608" and r["half"] != "":
        half608[r["spk"]] = int(r["half"])
cuts = {f"{c['file'][:-5]}:{c['si']:03d}": c for c in json.load(open(os.path.join(sc_out, "cuts608.json"))) if c["cut"]}
jobs = {}
for line in open(os.path.join(sc_out, "dgop_full.jsonl")):
    r = json.loads(line)
    if r["set"] not in ("538", "608") or r["kind"] not in ("same", "diff"):
        continue
    j = jobs.setdefault(r["clip"], {"set": r["set"], "clip": r["clip"], "spk": r["spk"], "targets": []})
    j["targets"].append({"kind": r["kind"], "target": r["target"]})
n = {"538": 0, "608": 0}
with open(os.path.join(stage, "jobs.jsonl"), "w", encoding="utf-8") as f:
    for clip in sorted(jobs):
        j = jobs[clip]
        if j["set"] == "538":
            j["half"] = zlib.crc32(j["spk"].encode()) % 2
        else:
            c = cuts[clip]
            j.update(file=c["file"], start=c["start"], end=c["end"], half=half608[j["spk"]])
        j["targets"].sort(key=lambda t: t["kind"] != "same")
        assert j["targets"][0]["kind"] == "same"
        n[j["set"]] += 1
        f.write(json.dumps(j, ensure_ascii=False) + "\n")
man = json.load(open(os.path.join(sound_dir, "manifest.json")))
tts = []
for voice in ("m1", "f2"):
    for key, c in sorted(man["clips"][voice].items()):
        if len(re.sub(r"[^가-힣]", "", key)) >= 5:
            tts.append({"set": "tts", "clip": f"{voice}:{key}", "voice": voice, "target": key, "file": c["id"] + ".ogg"})
with open(os.path.join(stage, "tts_jobs.jsonl"), "w", encoding="utf-8") as f:
    for t in tts:
        f.write(json.dumps(t, ensure_ascii=False) + "\n")
print("JOBS", n, "TTS", len(tts))
