"""측정 작업 목록과 소리 묶음(맥, 모델 없음). docs/dgop-final-vowel-fix2-2026-10.md 4절.

    python build_jobs.py NS_ROOT SOUND_DIR STAGE_DATA

NS_ROOT: 10/9 새 화자 묶음(liplab-lab/data/ns_stage/root, data/jobs.json·c538n·n608). SOUND_DIR: backend/data/sound.
STAGE_DATA/jobs.jsonl: 538 새 21명 600클립(set 538n)과 608 새 18명 340조각(set 608n), 자기 문장(same)과 다른 문장 2개(diff).
STAGE_DATA/tts_jobs.jsonl: 서버 음성 m1·f2의 문장 클립(한글 5음절 이상, 10/7과 같은 규칙). 소리는 STAGE_DATA/wav·tts로 복제한다(cp -c).
절반은 crc32(화자) % 2(보고용, 판정은 전체). 원자료는 앱 저장소에 넣지 않는다.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import zlib

ns, sound_dir, stage = sys.argv[1:4]
os.makedirs(os.path.join(stage, "wav"), exist_ok=True)
os.makedirs(os.path.join(stage, "tts"), exist_ok=True)


def clone(src, dst):
    if os.path.exists(dst):
        return
    if subprocess.call(["cp", "-c", src, dst]) != 0:
        shutil.copy(src, dst)


n = {"538n": 0, "608n": 0}
with open(os.path.join(stage, "jobs.jsonl"), "w", encoding="utf-8") as f:
    for j in json.load(open(os.path.join(ns, "data", "jobs.json"), encoding="utf-8")):
        if j["set"] not in ("538", "608"):
            continue
        st = j["set"] + "n"
        tg = [{"kind": k, "target": t} for t, k in j["targets"] if k in ("same", "diff")]
        tg.sort(key=lambda t: t["kind"] != "same")
        if not tg or tg[0]["kind"] != "same":
            continue
        name = os.path.basename(j["path"])
        clone(os.path.join(ns, "data", j["path"]), os.path.join(stage, "wav", name))
        f.write(json.dumps({"set": st, "clip": j["clip"], "spk": j["spk"], "half": zlib.crc32(j["spk"].encode()) % 2,
                            "file": name, "targets": tg}, ensure_ascii=False) + "\n")
        n[st] += 1
man = json.load(open(os.path.join(sound_dir, "manifest.json"), encoding="utf-8"))
tts = []
for voice in ("m1", "f2"):
    for key, c in sorted(man["clips"][voice].items()):
        if len(re.sub(r"[^가-힣]", "", key)) >= 5:
            fn = c["id"] + ".ogg"
            clone(os.path.join(sound_dir, "clips", fn), os.path.join(stage, "tts", fn))
            tts.append({"set": "tts", "clip": f"{voice}:{key}", "voice": voice, "target": key, "file": fn})
with open(os.path.join(stage, "tts_jobs.jsonl"), "w", encoding="utf-8") as f:
    for t in tts:
        f.write(json.dumps(t, ensure_ascii=False) + "\n")
print("JOBS", n, "TTS", len(tts))
