#!/usr/bin/env python
"""소리 품질 점검·재합성 결과를 저장소 목록(backend/data/sound/manifest.json)과 clips/에 넣는다(맥, 가벼운 파일 작업).

    python scripts/sound_qa_apply.py RUN_DIR --targets TARGETS.jsonl [--prune INVENTORY.json] [--out backend/data/sound] [--dry-run]
--prune: 인벤토리(sound_inventory.py 결과, 모든 화면의 출처)가 더는 쓰지 않는 글의 항목을 목록에서 지운다.

RUN_DIR(qa_session.sh fetch가 푼 폴더): final.jsonl({uid, voice, key, cand, ms, syl, …}), enc/<후보>_<uid>.{ogg,m4a}.
바뀐 클립은 rev(새 Ogg sha1 앞 12자)로 새 이름 clip_id(키, 목소리, rev)를 받고(docs/sound-qa-2026-10.md 6절), 목록 항목에
rev와 고른 후보 q를 적는다. 목록에 없던 글(목록에 없는 글만 합성)은 새 항목으로 넣는다. 어떤 항목도 가리키지 않는 옛 파일은 지운다.
끝에 소리 자료 전체 크기(목록 + 클립 + 소음)를 찍고 50MB를 넘으면 실패 코드로 끝난다.
"""
import argparse
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))
sys.path.insert(0, HERE)
import sound_clips as S  # noqa: E402

LIMIT = 50_000_000


def dir_bytes(d):
    return sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(d) for f in fs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--targets", required=True)
    ap.add_argument("--out", default=os.path.join(HERE, "..", "backend", "data", "sound"))
    ap.add_argument("--engine", default="Supertonic 3 (supertonic 1.3.1). 기본 total_steps 8, speed 1.05; "
                                         "다시 합성한 클립은 q 후보 설정(docs/sound-qa-2026-10.md 3절)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--prune", default="")
    ap.add_argument("--sylfix", default="", help="그대로 둔 기존 클립의 음절 시각 고침(qa_judge final의 orig_sylfix.jsonl)")
    a = ap.parse_args()
    mpath = os.path.join(a.out, "manifest.json")
    clips_dir = os.path.join(a.out, "clips")
    man = json.load(open(mpath, encoding="utf-8"))
    targets = {}
    for l in open(a.targets, encoding="utf-8"):
        if l.strip():
            t = json.loads(l)
            targets[t["uid"]] = t
    n_rep = n_new = 0
    for l in open(os.path.join(a.run, "final.jsonl"), encoding="utf-8"):
        if not l.strip():
            continue
        r = json.loads(l)
        t = targets[r["uid"]]
        src = {ext: os.path.join(a.run, "enc", f"{r['cand']}_{r['uid']}.{ext}") for ext in ("ogg", "m4a")}
        if not all(os.path.exists(p) and os.path.getsize(p) > 0 for p in src.values()):
            sys.exit(f"인코딩 파일 없음: {src}")
        ok, why = True, ""
        syl = r.get("syl")
        if not syl or len(syl) != len(S.syllable_positions(t["text"])):
            ok, why = False, "syl"
        if not ok:
            sys.exit(f"음절 시각 이상 {r['uid']} {why}")
        rev = S.audio_rev(open(src["ogg"], "rb").read())
        cid = S.clip_id(r["key"], r["voice"], rev)
        clips = man["clips"].setdefault(r["voice"], {})
        old = clips.get(r["key"])
        entry = {"id": cid, "ms": int(r["ms"]), "syl": syl, "text": (old or {}).get("text") or t["text"], "rev": rev, "q": r["cand"]}
        clips[r["key"]] = entry
        n_rep += old is not None
        n_new += old is None
        if not a.dry_run:
            for ext, p in src.items():
                shutil.copyfile(p, os.path.join(clips_dir, f"{cid}.{ext}"))
    n_fix = 0
    if a.sylfix:
        for l in open(a.sylfix, encoding="utf-8"):
            if not l.strip():
                continue
            r = json.loads(l)
            c = man["clips"].get(r["voice"], {}).get(r["key"])
            t = targets.get(r["uid"])
            if c and t and c["id"] == t.get("orig_id"):      # 이번에 바뀌지 않은 클립만(바뀐 클립은 final.jsonl의 고친 시각)
                c["syl"] = r["syl"]
                n_fix += 1
    pruned = 0
    if a.prune:
        from sound_qa_targets import wanted_keys
        want = wanted_keys(a.prune)
        for v, clips in man["clips"].items():
            for k in [k for k in clips if k not in want.get(v, set())]:
                del clips[k]
                pruned += 1
    man["engine"] = a.engine
    keep = {f"{c['id']}.{ext}" for clips in man["clips"].values() for c in clips.values() for ext in ("ogg", "m4a")}
    removed = 0
    if not a.dry_run:
        missing = [f for f in keep if not os.path.exists(os.path.join(clips_dir, f))]
        if missing:
            sys.exit(f"목록이 가리키는 파일 없음 {len(missing)}개: {missing[:3]}")
        for f in os.listdir(clips_dir):
            if f not in keep:
                os.remove(os.path.join(clips_dir, f))
                removed += 1
        with open(mpath + ".tmp", "w", encoding="utf-8") as f:
            json.dump(man, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(mpath + ".tmp", mpath)
    size = dir_bytes(a.out)
    print(json.dumps({"replaced": n_rep, "added": n_new, "pruned": pruned, "sylfix": n_fix, "removed_files": removed, "files": len(keep),
                      "sound_bytes": size, "limit": LIMIT, "dry_run": a.dry_run}, ensure_ascii=False))
    if size > LIMIT:
        sys.exit("SOUND_SIZE_OVER_LIMIT")


if __name__ == "__main__":
    main()
