#!/usr/bin/env python
"""소리 품질 점검·재합성(docs/sound-qa-2026-10.md)의 대상 목록을 만든다(맥, 가벼운 계산).

    python scripts/sound_qa_targets.py all OUT.jsonl [--inventory TEXTS]
        목록(manifest)의 모든 클립(기존 점검 + 전체 재합성 대상). --inventory를 주면 지금 인벤토리가 쓰지 않는 글은 뺀다
    python scripts/sound_qa_targets.py missing TEXTS OUT.jsonl [--voices m1,f1] [--listen]
        목록에 없는 (목소리, 글)만. TEXTS는 sound_inventory.py 결과(JSON, sources 포함), 글 문자열의 JSON 배열,
        또는 한 줄에 글 하나인 텍스트 파일. 출처가 있으면 목소리는 VOICE_SOURCES 규칙(듣기 글은 다섯 목소리, 나머지는
        기본 두 목소리)을 따르고, 출처 없는 글은 --voices(기본 m1,f1), --listen이면 다섯 목소리 모두.

줄마다 {uid, voice, engine_voice, key, text, tts_text, n_syl, sources, orig_id?, orig_ms?, orig_syl?}. uid = 목소리_clip_id(키, 목소리).
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))
import sound_clips as S  # noqa: E402
from korean_numbers import normalize_numbers  # noqa: E402

SOUND = os.path.join(HERE, "..", "backend", "data", "sound")
# 목소리마다 합성하는 글의 출처(docs/sound-condition.md 3.4절). '*'는 모든 출처
VOICE_SOURCES = {"m1": ["*"], "f1": ["*"], "m2": ["listen"], "f2": ["listen"], "m3": ["listen"]}


def row(voice, engine_voice, key, text, sources, clip=None):
    r = {"uid": f"{voice}_{S.clip_id(key, voice)}", "voice": voice, "engine_voice": engine_voice, "key": key, "text": text,
         "tts_text": normalize_numbers(text), "n_syl": len(S.syllable_positions(text)), "sources": sources}
    if clip:
        r.update(orig_id=clip["id"], orig_ms=clip.get("ms"), orig_syl=clip.get("syl"))
    return r


def wanted_keys(inv_path):
    """인벤토리(sound_inventory.py 결과) → {목소리: 그 목소리가 가져야 할 키 집합}(VOICE_SOURCES 규칙)."""
    out = {v: set() for v in VOICE_SOURCES}
    for e in read_texts(inv_path):
        key = S.normalize_text(e["text"])
        for v, ss in VOICE_SOURCES.items():
            if key and ("*" in ss or set(ss) & set(e["sources"] or [])):
                out[v].add(key)
    return out


def read_texts(path):
    raw = open(path, encoding="utf-8").read()
    try:
        data = json.loads(raw)
    except ValueError:
        data = [l.strip() for l in raw.splitlines() if l.strip()]
    out = []
    for e in data:
        if isinstance(e, str):
            out.append({"text": e, "sources": None})
        elif isinstance(e, dict) and e.get("text"):
            out.append({"text": e["text"], "sources": e.get("sources")})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["all", "missing"])
    ap.add_argument("args", nargs="+")
    ap.add_argument("--voices", default="m1,f1")
    ap.add_argument("--listen", action="store_true")
    ap.add_argument("--inventory", default="")
    a = ap.parse_args()
    man = S.load_manifest(os.path.join(SOUND, "manifest.json"))
    ev = {v["id"]: v["engine_voice"] for v in man["voices"]}
    rows = []
    if a.mode == "all":
        out = a.args[0]
        want = wanted_keys(a.inventory) if a.inventory else None
        for v, clips in man["clips"].items():
            for k, c in clips.items():
                if want is not None and k not in want.get(v, set()):
                    continue
                rows.append(row(v, ev[v], k, c.get("text") or k, None, c))
    else:
        src, out = a.args[0], a.args[1]
        seen = set()
        for e in read_texts(src):
            key = S.normalize_text(e["text"])
            if not key:
                continue
            if e["sources"]:
                voices = [v for v, ss in VOICE_SOURCES.items() if "*" in ss or set(ss) & set(e["sources"])]
            else:
                voices = list(VOICE_SOURCES) if a.listen else [v for v in a.voices.split(",") if v]
            for v in voices:
                if v not in ev:
                    sys.exit(f"모르는 목소리 {v}")
                if key in man["clips"].get(v, {}) or (v, key) in seen:
                    continue
                seen.add((v, key))
                rows.append(row(v, ev[v], key, e["text"], e["sources"]))
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    by = {}
    for r in rows:
        by[r["voice"]] = by.get(r["voice"], 0) + 1
    print(json.dumps({"targets": len(rows), "by_voice": by}, ensure_ascii=False))


if __name__ == "__main__":
    main()
