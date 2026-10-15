"""A2(새 538 화자 재확인) 작업 목록(맥, 모델 없음). docs/phone-tail-2026-10.md 8절.

    python build_a2.py OUT_DIR      →  OUT_DIR/jobs.jsonl, OUT_DIR/jobs_summary.json, OUT_DIR/wav_list.tsv

자료: 맥에 이미 있는 V7b 538 전문가 화자 클립(liplab-lab/data/v18/v7b_dl*/clips) 가운데 S2(A0·A1)에 나온 인물 번호(E007·E009·E192 등)를 빼고,
V7b 계획 파일이 낭독으로 정한 대본(read)의 클립만 쓴다. 화자 = 인물 번호. 대치·생략 고르기는 S2 build_jobs와 같은 규칙과 시드다.
"""
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "s2_reliability_pod"))
import build_jobs as BJ  # noqa: E402

LAB = BJ.LAB
V18 = f"{LAB}/data/v18"


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    s2 = [json.loads(l) for l in open(f"{LAB}/data/s2stage/data/jobs.jsonl", encoding="utf-8")]
    used = {j["clip"].split("_")[6] for j in s2}
    plan = {}
    for f in ("v7b_plan2.json", "v7b_plan.json"):
        for v in json.load(open(f"{V18}/{f}", encoding="utf-8")).values():
            plan.setdefault(v["person"], v)
    items, wav, seen = [], [], set()
    for d in ("v7b_dl", "v7b_dl2"):
        for l in open(f"{V18}/{d}/manifest.tsv", encoding="utf-8"):
            c, _s, t = l.rstrip("\n").split("\t")
            c = c[:-4]
            p, scr = c.split("_")[6], c.split("_")[8]
            path = f"{V18}/{d}/clips/{c}.wav"
            if c in seen or p in used or p not in plan or scr not in plan[p]["read"] or not os.path.exists(path):
                continue
            if not BJ.JV.text_to_tokens(t):
                continue
            seen.add(c)
            items.append({"set": "A2", "clip": c, "spk": p, "target": t})
            wav.append(f"{c}\t{path}\n")
    rows = BJ.build(items)
    with open(f"{out}/jobs.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    open(f"{out}/wav_list.tsv", "w").writelines(wav)
    summ = {"clips": len(rows), "speakers": len({r["spk"] for r in rows}), "excluded_persons_seen_in_s2": sorted(used & set(plan)),
            "subs": dict(Counter(s["kind"] for r in rows for s in r["subs"])),
            "near_for_R": {y: sum(1 for r in rows for s in r["subs"] if s["kind"] == "near" and s["y"] == y) for y in ("n:ㅏ", "o:ㄴ", "o:ㄹ")}}
    json.dump(summ, open(f"{out}/jobs_summary.json", "w"), ensure_ascii=False, indent=1)
    print("A2_JOBS_OK", json.dumps(summ, ensure_ascii=False))


if __name__ == "__main__":
    main()
