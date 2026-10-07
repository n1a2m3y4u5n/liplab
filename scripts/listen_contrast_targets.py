#!/usr/bin/env python
"""목소리별 대조 측정(docs/listen-voice-contrast-2026-10.md)의 대상 목록을 만든다(맥, 가벼운 계산).

    python scripts/listen_contrast_targets.py OUT.jsonl [--suspect SUMMARY.json ...]

줄마다 클립 하나: {uid, set, voice, text, key, clip, comps: [{text, kind?, dist?}], suspect, hyp?}
  set 'ax'   소리 구별 AX_PAIRS 60쌍의 글(훈련 목소리 m1·f1·m2·f2). 경쟁 글은 그 글이 든 짝의 상대 글 모두.
  set 'word' 낱말 고르기 훈련 풀(word_pool())의 낱말(훈련 목소리). 경쟁 글은 소리 거리 1~6 이웃 가운데 가까운 순 최대 5개.
  set 'gen'  일반화 검사 GEN_WORDS(검사 목소리 m3). 경쟁 글은 include_gen 풀의 이웃에서 검사 낱말을 뺀 것(gen_test_items와 같은
             보기 풀) 가운데 거리 1~6, 가까운 순 최대 5개.
suspect는 소리 품질 점검(docs/sound-qa-2026-10.md 8.5절)의 미해결 목록에 (목소리, 키)가 있는가, hyp는 그때의 Whisper 전사다.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "backend")
sys.path.insert(0, BACKEND)
import listen_curriculum as L  # noqa: E402
import sound_clips as S  # noqa: E402

TRAIN_VOICES = ("m1", "f1", "m2", "f2")
TEST_VOICE = "m3"
MAX_COMPS = 5
MAX_DIST = 6


def nearest(nb, word, exclude=()):
    """이웃 표의 (거리, 낱말) 가까운 순에서 거리 1~6, 최대 5개. 같은 거리는 표의 순서(가나다)를 따른다."""
    out = []
    for d, b in nb.get(word, []):
        if d > MAX_DIST:
            break
        if 1 <= d and b not in exclude:
            out.append({"text": b, "dist": d})
        if len(out) >= MAX_COMPS:
            break
    return out


def build(suspect_paths=()):
    man = json.load(open(os.path.join(BACKEND, "data", "sound", "manifest.json"), encoding="utf-8"))
    sus = {}
    for p in suspect_paths:
        for u in json.load(open(p, encoding="utf-8")).get("unresolved", []):
            sus[(u["voice"], u["key"])] = u.get("hyp")
    rows = []

    def add(set_, voice, text, comps):
        key = S.normalize_text(text)
        clip = (man["clips"].get(voice) or {}).get(key)
        if not clip or not comps:
            return
        rows.append({"uid": f"{set_}:{voice}:{key}", "set": set_, "voice": voice, "text": text, "key": key, "clip": clip["id"],
                     "comps": comps, "suspect": (voice, key) in sus, **({"hyp": sus[(voice, key)]} if (voice, key) in sus else {})})

    # (a) 소리 구별: 글마다 그 글이 든 짝의 상대 글 모두(같은 상대가 두 번이면 한 번)
    by_text = {}
    for p in L.AX_PAIRS:
        for x, y in ((p["a"], p["b"]), (p["b"], p["a"])):
            lst = by_text.setdefault(x, [])
            if all(c["text"] != y for c in lst):
                lst.append({"text": y, "kind": p["kind"], "level": p["level"]})
    for v in TRAIN_VOICES:
        for t in sorted(by_text):
            add("ax", v, t, by_text[t])
    # (b) 낱말 고르기 훈련 풀
    pool = L.word_pool()
    nb = L._neighbors(pool)
    for v in TRAIN_VOICES:
        for w in pool:
            add("word", v, w, nearest(nb, w))
    # (c) 일반화 검사(m3)
    gen = set(L.GEN_WORDS)
    gpool = L.word_pool(include_gen=True)
    train = [w for w in gpool if w not in gen]
    full = L._neighbors(list(train) + [w for w in L.GEN_WORDS if w not in set(train)])
    for w in L.GEN_WORDS:
        add("gen", TEST_VOICE, w, nearest(full, w, exclude=gen))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--suspect", nargs="*", default=[])
    a = ap.parse_args()
    rows = build(a.suspect)
    with open(a.out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    from collections import Counter
    print("TARGETS", len(rows), dict(Counter(r["set"] for r in rows)), "comparisons", sum(len(r["comps"]) for r in rows),
          "suspect", sum(r["suspect"] for r in rows), "clips", len({r["clip"] for r in rows}))


if __name__ == "__main__":
    main()
