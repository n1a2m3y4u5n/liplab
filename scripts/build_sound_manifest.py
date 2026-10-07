#!/usr/bin/env python
"""파드에서 받은 소리·정렬 결과로 소리 목록(backend/data/sound/manifest.json)과 clips/를 만든다(맥, 가벼운 파일 작업).

    python scripts/build_sound_manifest.py RUN_DIR [--out backend/data/sound]

RUN_DIR 구조(파드 final 단계가 만든다)
  texts.json                       sound_inventory.py 결과(합성한 글)
  voices.json                      [{id, label, sex, engine_voice, sources: ['*'] 또는 ['listen']}], 첫째가 기본 목소리
  enc/<목소리>/<id>.ogg|.m4a       인코딩한 소리(Opus 24kbps 48kHz 모노, AAC 32kbps 24kHz 모노)
  synth/<목소리>/synth.jsonl       {id, key, dur(초), ok}
  eval/<목소리>.*.jsonl            {id, key, syl, timing_ok, …}(evaluate.py)
목록에는 인코딩한 두 파일이 모두 있고 합성이 성공한 글만 넣는다. 음절 시각은 정렬 음절 수가 엔진 음절 수와 같을 때만 넣는다.
"""
import argparse
import glob
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))
import sound_clips as S  # noqa: E402


def read_jsonl(paths):
    out = {}
    for p in paths:
        with open(p, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                out[r["id"]] = r
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--out", default=os.path.join(HERE, "..", "backend", "data", "sound"))
    ap.add_argument("--engine", default="Supertonic 3 (supertonic 1.3.1, total_steps 8, speed 1.05)")
    a = ap.parse_args()
    texts = json.load(open(os.path.join(a.run, "texts.json"), encoding="utf-8"))
    voices = json.load(open(os.path.join(a.run, "voices.json"), encoding="utf-8"))
    clips_dir = os.path.join(a.out, "clips")
    os.makedirs(clips_dir, exist_ok=True)
    man = {"version": S.MANIFEST_VERSION, "engine": a.engine, "default_voice": voices[0]["id"],
           "voices": [{k: v[k] for k in ("id", "label", "sex", "engine_voice")} for v in voices], "clips": {}}
    stats = {}
    keep = set()
    for v in voices:
        vid = v["id"]
        want = [e for e in texts if "*" in v["sources"] or set(e["sources"]) & set(v["sources"])]
        syn = read_jsonl(glob.glob(os.path.join(a.run, "synth", vid, "synth.jsonl")))
        ev = read_jsonl(glob.glob(os.path.join(a.run, "eval", f"{vid}.*.jsonl")))
        clips = {}
        n_t = 0
        for e in want:
            i = S.clip_id(e["key"], vid)
            s = syn.get(i) or {}
            r = ev.get(i) or {}
            files = [os.path.join(a.run, "enc", vid, f"{i}.{ext}") for ext in ("ogg", "m4a")]
            # 합성 기록이 없으면(중간에 다시 띄운 경우) 정렬 기록의 길이를 쓴다
            dur = s.get("dur") if s.get("ok") else r.get("dur")
            if dur is None or not all(os.path.exists(f) for f in files):
                continue
            syl = r.get("syl") if r.get("timing_ok") else None
            n_t += syl is not None
            clips[e["key"]] = {"id": i, "ms": int(round(float(dur) * 1000)), "syl": syl, "text": e["text"]}
            for f in files:
                shutil.copyfile(f, os.path.join(clips_dir, os.path.basename(f)))
                keep.add(os.path.basename(f))
        man["clips"][vid] = clips
        stats[vid] = {"wanted": len(want), "clips": len(clips), "with_timing": n_t}
    # 목록에 없는 옛 파일은 지운다(목소리나 글이 바뀐 경우)
    for f in os.listdir(clips_dir):
        if f not in keep:
            os.remove(os.path.join(clips_dir, f))
    with open(os.path.join(a.out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, separators=(",", ":"))
    size = sum(os.path.getsize(os.path.join(clips_dir, f)) for f in os.listdir(clips_dir))
    print(json.dumps({"voices": stats, "files": len(keep), "bytes": size}, ensure_ascii=False))


if __name__ == "__main__":
    main()
