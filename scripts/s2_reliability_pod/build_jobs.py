"""S2 음소 피드백 신뢰도 지도의 작업 목록(맥, 모델 없음). docs/phoneme-feedback-reliability-2026-10.md 4절.

    python build_jobs.py OUT_DIR        →  OUT_DIR/jobs.jsonl, OUT_DIR/jobs_summary.json

클립마다 원래 목표 토큰열(앱 jamo_vocab.text_to_tokens)과, 한 자리만 바꾼 대치 목록(가까운 대치 24, 아무 소리 6, 끝 모음 1)을 만든다.
A0 = 10/6 D-GOP 평가 538 클립 600개(58명, 탐색), A1 = 10/6 밤 고정 21명 클립 630개(확인). 문장·소리 원자료는 lab 묶음에만 둔다.
"""
import json
import os
import random
import sys
import zlib
from collections import Counter

APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(APP, "backend"))
os.environ.setdefault("LIPLAB_CONTENT_WARMUP", "0")
import jamo_vocab as JV  # noqa: E402

LAB = os.environ.get("LAB", os.path.expanduser("~/Downloads/liplab-lab"))
DGOP_1006 = f"{LAB}/data/pod_runs/20261006_35zrgz6wvrqiho/sc/out/dgop_full.jsonl"
FROZEN = f"{LAB}/data/scores_newspk_2026-10-06/v1_snapshot_spk_frozen.txt"
V1_MAN = f"{LAB}/data/v1_538/manifest.tsv"
K_NEAR, K_ANY, K_FINAL = 24, 6, 1


def _pairs(spec):
    out = {}
    for a, b in (p.split("-") for p in spec.split()):
        out.setdefault(a, set()).add(b)
        out.setdefault(b, set()).add(a)
    return out


NEAR = {
    "o:": _pairs("ㄱ-ㅋ ㄱ-ㄲ ㅋ-ㄲ ㄷ-ㅌ ㄷ-ㄸ ㅌ-ㄸ ㅂ-ㅍ ㅂ-ㅃ ㅍ-ㅃ ㅈ-ㅊ ㅈ-ㅉ ㅊ-ㅉ ㅅ-ㅆ "
                 "ㄴ-ㄷ ㅁ-ㅂ ㄱ-ㄷ ㄷ-ㅂ ㅅ-ㄷ ㅈ-ㄷ ㅅ-ㅈ ㄹ-ㄴ ㄹ-ㄷ ㅎ-ㅅ ㅎ-ㅋ"),
    "n:": _pairs("ㅏ-ㅓ ㅓ-ㅗ ㅗ-ㅜ ㅜ-ㅡ ㅡ-ㅓ ㅡ-ㅣ ㅐ-ㅏ ㅐ-ㅣ ㅔ-ㅏ ㅔ-ㅣ "
                 "ㅑ-ㅏ ㅕ-ㅓ ㅛ-ㅗ ㅠ-ㅜ ㅒ-ㅐ ㅘ-ㅏ ㅝ-ㅓ ㅙ-ㅐ ㅞ-ㅔ ㅚ-ㅗ ㅚ-ㅔ ㅟ-ㅣ ㅟ-ㅜ ㅢ-ㅡ "
                 "ㅑ-ㅕ ㅕ-ㅛ ㅛ-ㅠ ㅘ-ㅝ"),
    "c:": _pairs("ㄴ-ㅇ ㄴ-ㅁ ㅁ-ㅇ ㄱ-ㄷ ㄷ-ㅂ ㄱ-ㅂ ㄴ-ㄷ ㅁ-ㅂ ㅇ-ㄱ ㄹ-ㄴ"),
}
INVENTORY = {"o:": JV.ONSETS, "n:": JV.NUCLEI, "c:": JV.CODAS}
# 발음상 같거나 표준 발음이 허용하는 대치(4절). 가까운·아무 소리 대치 모두에서 뺀다.
EXCLUDE = {frozenset(p.split("-")) for p in "ㅐ-ㅔ ㅒ-ㅖ ㅖ-ㅔ ㅙ-ㅚ ㅙ-ㅞ ㅚ-ㅞ ㅢ-ㅣ ㅢ-ㅔ".split()}
# 초성 ㅈ·ㅉ·ㅊ 뒤에서는 y계 반모음 있음·없음이 발음상 같다(져[저], 표준 발음법 5항 다만 1).
Y_GLIDE = {frozenset(p.split("-")) for p in "ㅑ-ㅏ ㅕ-ㅓ ㅛ-ㅗ ㅠ-ㅜ ㅒ-ㅐ".split()}
PALATAL = {"o:ㅈ", "o:ㅉ", "o:ㅊ"}
VELAR_ONSET, LABIAL_ONSET = set("ㄱㄲㅋ"), set("ㅂㅃㅍㅁ")


def final_syllable_start(toks):
    """마지막 음절(발음형 자모열의 마지막 중성 + 바로 앞 초성 + 뒤 종성)의 시작 위치. build_scores_csv와 같은 정의."""
    idx = [i for i, t in enumerate(toks) if t.startswith("n:")]
    if not idx:
        return len(toks)
    i = idx[-1]
    return i - 1 if i > 0 and toks[i - 1].startswith("o:") else i


def next_onset(toks, i):
    for t in toks[i + 1:]:
        if t == "|":
            continue
        return t[2:] if t.startswith("o:") else None
    return None


def allowed(toks, i, y):
    tok = toks[i]
    pos, x = tok[:2], tok[2:]
    if y == x or frozenset((x, y)) in EXCLUDE:
        return False
    if pos == "n:" and i > 0 and toks[i - 1] in PALATAL and frozenset((x, y)) in Y_GLIDE:
        return False
    if pos == "c:":
        nx = next_onset(toks, i)
        if nx in VELAR_ONSET and y in ("ㅇ", "ㄱ"):
            return False
        if nx in LABIAL_ONSET and y in ("ㅁ", "ㅂ"):
            return False
    return True


def candidates(toks, silent, kind):
    fs = final_syllable_start(toks)
    nuc = [i for i, t in enumerate(toks) if t.startswith("n:")]
    last_n = nuc[-1] if nuc else None
    out = []
    for i, tok in enumerate(toks):
        if tok == "|" or i in silent:
            continue
        pos, x = tok[:2], tok[2:]
        if kind == "final":
            if i != last_n:
                continue
            ys = NEAR[pos].get(x, ())
        else:
            if i >= fs:
                continue
            ys = NEAR[pos].get(x, ()) if kind == "near" else [j for j in INVENTORY[pos] if j != x]
        for y in sorted(ys):
            if allowed(toks, i, y):
                out.append((i, x, pos + y))
    return out


def weighted_pick(cands, k, counts, seed):
    """가중 비복원 추출(Efraimidis–Spirakis): 키 u^(1/w), w = 1 / (자료 안 그 소리의 후보 수)."""
    rng = random.Random(seed)
    keyed = sorted(((rng.random() ** counts[c[2]], c) for c in cands), key=lambda z: -z[0])
    return sorted(c for _, c in keyed[:k])


def load_sets():
    a0 = []
    seen = set()
    for l in open(DGOP_1006, encoding="utf-8"):
        r = json.loads(l)
        if r["set"] == "538" and r["kind"] == "same" and r["clip"] not in seen:
            seen.add(r["clip"])
            a0.append({"set": "A0", "clip": r["clip"], "spk": r["spk"], "target": r["target"]})
    frozen = set(open(FROZEN).read().split())
    a1 = []
    for l in open(V1_MAN, encoding="utf-8"):
        c, s, t = l.rstrip("\n").split("\t")
        if s in frozen:
            a1.append({"set": "A1", "clip": c.replace(".mp4", ""), "spk": s, "target": t})
    return a0, a1


def build(items):
    rows = []
    for it in items:
        toks = JV.text_to_tokens(it["target"])
        silent = set(JV.silent_linking_h(it["target"]))
        rows.append({**it, "tokens": toks, "silent_h": sorted(silent), "fs": final_syllable_start(toks),
                     "_c": {k: candidates(toks, silent, k) for k in ("near", "any", "final")}})
    for kind, k in (("near", K_NEAR), ("any", K_ANY), ("final", K_FINAL)):
        counts = Counter(c[2] for r in rows for c in r["_c"][kind])
        for r in rows:
            r.setdefault("subs", [])
            for i, x, y in weighted_pick(r["_c"][kind], k, counts, zlib.crc32(f"{kind}|{r['clip']}".encode())):
                r["subs"].append({"kind": kind, "i": i, "x": r["tokens"][i], "y": y})
    for r in rows:
        del r["_c"]
    return rows


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    a0, a1 = load_sets()
    assert len(a0) == 600 and len({r["spk"] for r in a0}) == 58, (len(a0), len({r["spk"] for r in a0}))
    assert len(a1) == 630 and len({r["spk"] for r in a1}) == 21, (len(a1), len({r["spk"] for r in a1}))
    assert not ({r["spk"] for r in a0} & {r["spk"] for r in a1})
    rows = build(a0) + build(a1)
    with open(f"{out}/jobs.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    summ = {}
    for st in ("A0", "A1"):
        rs = [r for r in rows if r["set"] == st]
        summ[st] = {"clips": len(rs), "speakers": len({r["spk"] for r in rs}),
                    "subs": dict(Counter(s["kind"] for r in rs for s in r["subs"])),
                    "near_by_y": dict(sorted(Counter(s["y"] for r in rs for s in r["subs"] if s["kind"] == "near").items()))}
    json.dump(summ, open(f"{out}/jobs_summary.json", "w"), ensure_ascii=False, indent=1)
    print("JOBS_OK", {k: (v["clips"], v["subs"]) for k, v in summ.items()})


if __name__ == "__main__":
    main()
