"""서버 1의 소리 캐시 → 10/7 품질 점검 대상 목록(docs/listen-convo-tts-2026-10.md 5.5절).

    python qa_targets.py CACHE_DIR WORK_SERVED WORK_REJECTED

서비스에 쓴 클립(index.json)은 WORK_SERVED/targets.jsonl(orig_id = 캐시 파일, orig_syl = 서버가 준 음절 시각),
게이트에서 떨어진 클립(rejected/index.jsonl, LIPLAB_SOUND_KEEP_REJECTED=1)은 WORK_REJECTED/targets.jsonl. 필드는 scripts/sound_qa_targets.py와 같다."""
import json
import os
import sys

sys.path.insert(0, os.environ.get("LIPLAB_BACKEND", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend")))
import sound_clips as S  # noqa: E402
from korean_numbers import normalize_numbers  # noqa: E402

cache, ws, wr = sys.argv[1:4]
for d in (ws, wr):
    os.makedirs(d, exist_ok=True)
idx = json.load(open(os.path.join(cache, "index.json"), encoding="utf-8"))
n = 0
with open(os.path.join(ws, "targets.jsonl"), "w", encoding="utf-8") as f:
    for voice, clips in idx.items():
        if voice.startswith("_"):
            continue
        for key, c in clips.items():
            text = c.get("text") or key
            f.write(json.dumps({"uid": f"{voice}_{c['id']}", "voice": voice, "key": key, "text": text, "tts_text": normalize_numbers(text),
                                "n_syl": len(S.syllable_positions(text)), "orig_id": c["id"], "orig_ms": c.get("ms"),
                                "orig_syl": c.get("syl"), "gate": c.get("q"), "tries": c.get("tries")}, ensure_ascii=False) + "\n")
            n += 1
m = 0
rp = os.path.join(cache, "rejected", "index.jsonl")
with open(os.path.join(wr, "targets.jsonl"), "w", encoding="utf-8") as f:
    if os.path.exists(rp):
        seen = set()
        for line in open(rp, encoding="utf-8"):
            r = json.loads(line)
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            f.write(json.dumps({"uid": f"{r['voice']}_{r['id']}", "voice": r["voice"], "key": r["key"], "text": r["text"],
                                "tts_text": normalize_numbers(r["text"]), "n_syl": len(S.syllable_positions(r["text"])),
                                "orig_id": r["id"], "orig_ms": r.get("ms"), "orig_syl": None, "gate": r.get("q"),
                                "tries": r.get("tries")}, ensure_ascii=False) + "\n")
            m += 1
print("QA_TARGETS_OK served", n, "rejected", m)
