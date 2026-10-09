"""맥: 608 도메인 적응 파드 묶음 만들기(docs/dgop-608-adapt-2026-10.md 2·3·5절). 점수는 읽지 않는다(목표 문장·조각 시각·화자만).

    ~/Downloads/liplab/backend/.venv/bin/python scripts/dgop_adapt_pod/build.py STAGE_ROOT

만드는 것(STAGE_ROOT 아래):
  audio/sess/*.flac   학습 세션(3.1절 규칙으로 고른 것, cp -c 복제)
  audio/evA/*.wav     E-A: V2 341조각(10/6 cuts608.json + 10/7 recut.json 시각으로 세션에서 자름)
  audio/evB/*.wav     E-B: KSC 조각 340개(cp -c)
  audio/e538/*.wav    E-538(cp -c)
  meta/sessions.json  학습 세션 목록(묶음, 범주, 화자, 자를 길이, 대본 문장)
  meta/excl.json      적합별 평가 문장(한글만)
  meta/eval_*.json    평가 작업(클립, 화자, 절반, 목표, 대치 자리, large-v3 일치율)
  meta/build_summary.json
KSC 폴더와 liplab-lab/data/hi608는 읽기만 한다. 원자료는 저장소에 넣지 않는다.
"""
import csv
import json
import os
import random
import re
import shutil
import subprocess
import sys
import zlib
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(APP, "backend"))
import jamo_vocab  # noqa: E402

LAB = os.path.expanduser("~/Downloads/liplab-lab")
KSC = os.path.expanduser("~/Downloads/KSC2026/liplab/data/expand")
H608 = f"{LAB}/data/hi608"
SC10 = f"{LAB}/data/pod_runs/20261006_35zrgz6wvrqiho/sc/out"
RC10 = f"{LAB}/data/pod_runs/20261007_kcs2amnnqa24d7/rc/out"
V2 = f"{LAB}/data/scores_recut_2026-10-07/V2/dgop_pairs.csv"
V538 = f"{LAB}/data/v1_538"
CAP_S = 90 * 60
MIN_CROP_S = 10 * 60
EXCLUDE_C = {"KJH-M-29"}          # 범주 28 KJH-M-99(나이 미상)와 이니셜·성별이 같다(2.1절)


def hangul(s):
    return re.sub(r"[^가-힣]", "", s or "")


def split_sents(t):
    """대본 → 문장. cut_608의 '.?! 뒤 공백'에 줄바꿈을 더한다(범주 24 대본은 줄로 나뉜다)."""
    return [x.strip() for x in re.split(r"(?<=[.?!])\s+|[\r\n]+", t or "") if hangul(x)]


def cpc(src, dst):
    if os.path.exists(dst):
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    r = subprocess.run(["cp", "-c", src, dst])
    if r.returncode != 0:
        shutil.copy2(src, dst)


def spk_of(stem):
    return stem.split("-")[4]


def key_of(stem):
    p = stem.split("-")
    i = max(k for k, x in enumerate(p) if x in ("M", "F"))
    return f"{p[4]}-{p[i]}-{p[i + 1]}"


# ───────── KSC d1_minimal.candidates 규칙(그대로 옮김, ~/Downloads/KSC2026/liplab/scripts/d1_minimal.py) ─────────
CHO = list("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ")
RULES = {
    "ㅂ": [("ㅍ", "기식"), ("ㅁ", "비음")], "ㅍ": [("ㅂ", "기식")],
    "ㄷ": [("ㅌ", "기식"), ("ㄴ", "비음"), ("ㅅ", "마찰")], "ㅌ": [("ㄷ", "기식")],
    "ㄱ": [("ㅋ", "기식")], "ㅋ": [("ㄱ", "기식")],
    "ㅈ": [("ㅊ", "기식")], "ㅊ": [("ㅈ", "기식")],
    "ㅁ": [("ㅂ", "비음")], "ㄴ": [("ㄷ", "비음")],
    "ㅅ": [("ㄷ", "마찰")],
}
MIN_SEED, MIN_K = 20261007, 2


def _is_syl(ch):
    return 0xAC00 <= ord(ch) <= 0xD7A3


def _onset(ch):
    return CHO[(ord(ch) - 0xAC00) // 588]


def _with_onset(ch, new):
    code = ord(ch) - 0xAC00
    return chr(0xAC00 + CHO.index(new) * 588 + code % 588)


def min_candidates(text):
    base = jamo_vocab.text_to_tokens(text)
    pos = [i for i, ch in enumerate(text) if _is_syl(ch)]
    out = []
    for i in pos[:-1]:
        for new, cat in RULES.get(_onset(text[i]), []):
            t2 = text[:i] + _with_onset(text[i], new) + text[i + 1:]
            tok = jamo_vocab.text_to_tokens(t2)
            diff = [k for k, (a, b) in enumerate(zip(base, tok)) if a != b]
            if len(tok) == len(base) and len(diff) == 1 and tok[diff[0]].startswith("o:"):
                out.append({"char_idx": i, "orig": _onset(text[i]), "new": new, "cat": cat, "target": t2, "tok_idx": diff[0]})
    return out


def pick_min(rng, text):
    cands = min_candidates(text)
    if not cands:
        return []
    first = rng.choice(cands)
    pick = [first]
    rest = [c for c in cands if c["char_idx"] != first["char_idx"]]
    if MIN_K > 1 and rest:
        pick.append(rng.choice(rest))
    return pick


# ───────── 평가 세트 ─────────
def build_eval_A(root):
    """E-A: V2 341조각. 시각은 10/6 cuts608(20초 이하)과 10/7 recut(합격 12개)."""
    import soundfile as sf
    rows = list(csv.DictReader(open(V2)))
    own_rows = [r for r in rows if r["set"] == "608" and r["label"] == "own"]
    clips = sorted({r["clip"] for r in own_rows})
    half = {r["spk"]: int(r["half"]) for r in own_rows}
    cuts = {f"{c['file'][:-5]}:{c['si']:03d}": c for c in json.load(open(f"{SC10}/cuts608.json")) if c.get("cut")}
    recut = {r["clip"]: r for r in json.load(open(f"{RC10}/recut.json")) if r.get("accepted")}
    tg = defaultdict(list)
    for l in open(f"{SC10}/dgop_full.jsonl", encoding="utf-8"):
        j = json.loads(l)
        if j["set"] == "608" and j["kind"] in ("same", "diff"):
            tg[j["clip"]].append((j["target"], j["kind"]))
    rng = random.Random(MIN_SEED)
    jobs, n_other, cache = [], 0, {}
    os.makedirs(f"{root}/audio/evA", exist_ok=True)
    for clip in clips:
        c = cuts[clip]
        st, en, ratio = c["start"], c["end"], c["ratio"]
        if clip in recut:
            st, en, ratio = recut[clip]["start"], recut[clip]["end"], recut[clip]["ratio"]
        else:
            assert en - st <= 20.0, clip
        own = next(t for t, k in tg[clip] if k == "same")
        others = [t for t, k in tg[clip] if k == "diff" and hangul(t) != hangul(own)]
        n_other += len(others)
        f = c["file"]
        dst = f"{root}/audio/evA/{clip.replace(':', '_')}.wav"
        if not os.path.exists(dst):
            if f not in cache:
                cache.clear()
                y, sr = sf.read(f"{H608}/wav16/{f}")
                assert sr == 16000
                cache[f] = y
            y = cache[f]
            sf.write(dst, y[int(st * 16000):int(en * 16000)], 16000)
        mins = pick_min(rng, own)
        spk = spk_of(f[:-5])
        targets = [{"text": own, "kind": "own"}] + [{"text": t, "kind": "other"} for t in others] + \
                  [{"text": m["target"], "kind": "min", "tok_idx": m["tok_idx"], "cat": m["cat"]} for m in mins]
        jobs.append({"set": "A", "spk": spk, "half": half[spk], "clip": clip, "path": f"audio/evA/{clip.replace(':', '_')}.wav",
                     "intel": ratio, "own": own, "targets": targets})
    return jobs, n_other


def build_eval_B(root):
    clips = json.load(open(f"{KSC}/new_clips.json"))
    pod_cuts = {f"{c['file'][:-5]}:{c['si']:03d}": c for c in json.load(open(f"{KSC}/pod_out/cuts608.json")) if c.get("cut")}
    by = defaultdict(list)
    for l in open(f"{KSC}/new_targets.jsonl", encoding="utf-8"):
        j = json.loads(l)
        by[j["clip"]].append(j)
    jobs = []
    for clip in sorted(k for k, v in clips.items() if v["keep"]):
        rs = by[clip]
        own = next(r["target"] for r in rs if r["kind"] == "own")
        targets = [{"text": own, "kind": "own"}]
        targets += [{"text": r["target"], "kind": "other"} for r in rs if r["kind"] == "other"]
        targets += [{"text": r["target"], "kind": "min", "tok_idx": r["tok_idx"], "cat": r["cat"]} for r in rs if r["kind"] == "min"]
        wav = clip.replace(":", "_") + ".wav"
        cpc(f"{KSC}/cuts_wav/{wav}", f"{root}/audio/evB/{wav}")
        jobs.append({"set": "B", "spk": rs[0]["spk"], "half": rs[0]["half"], "clip": clip, "path": f"audio/evB/{wav}",
                     "intel": pod_cuts[clip]["ratio"], "own": own, "targets": targets})
    return jobs


def build_eval_538(root):
    rows = [l.rstrip("\n").split("\t") for l in open(f"{V538}/manifest_clips.tsv", encoding="utf-8") if not l.startswith("#")]
    text = {l.split("\t")[0][:-4]: l.rstrip("\n").split("\t")[2] for l in open(f"{V538}/manifest.tsv", encoding="utf-8")}
    sel = sorted(r[0] for r in rows if int(r[4]) % 4 == 0 and os.path.exists(f"{V538}/clips/{r[0]}.wav") and r[0] in text)
    spk = {r[0]: r[1] for r in rows}
    pool = [text[c] for c in sel]
    rng_o, rng_m = random.Random(0), random.Random(MIN_SEED)
    jobs = []
    for c in sel:
        t = text[c]
        n = len(hangul(t))
        cand = [x for x in pool if hangul(x) != hangul(t) and 0.7 * n <= len(hangul(x)) <= 1.3 * n]
        others = rng_o.sample(cand, min(2, len(cand)))
        mins = pick_min(rng_m, t)
        cpc(f"{V538}/clips/{c}.wav", f"{root}/audio/e538/{c}.wav")
        targets = [{"text": t, "kind": "own"}] + [{"text": x, "kind": "other"} for x in others] + \
                  [{"text": m["target"], "kind": "min", "tok_idx": m["tok_idx"], "cat": m["cat"]} for m in mins]
        jobs.append({"set": "538", "spk": spk[c], "half": zlib.crc32(spk[c].encode()) % 2, "clip": c, "path": f"audio/e538/{c}.wav",
                     "own": t, "degrade": True, "targets": targets})
    return jobs


# ───────── 학습 세션 ─────────
def choose_sessions(items):
    """화자마다 라벨 길이가 짧은 순으로 90분까지(3.1절). 넘치는 세션은 남은 시간이 10분 이상이면 앞부분만."""
    by = defaultdict(list)
    for x in items:
        by[x["key"]].append(x)
    out = []
    for k in sorted(by):
        used = 0.0
        for x in sorted(by[k], key=lambda x: (x["dur"], x["stem"])):
            if used + x["dur"] <= CAP_S:
                out.append(dict(x, crop_s=None))
                used += x["dur"]
                continue
            if CAP_S - used >= MIN_CROP_S:
                out.append(dict(x, crop_s=round(CAP_S - used, 1)))
            break
    return out


def build_sessions(root, A_spk, B_spk):
    man = json.load(open(f"{KSC}/flac16/manifest.json"))
    rt = json.load(open(f"{KSC}/flac16/retest/manifest_retest.json"))
    items = []

    def add(src, stem, cat, label):
        lab = json.load(open(f"{H608}/{label}"))
        spk = spk_of(stem)
        if cat == 28:
            grp = "A" if spk in A_spk else ("B" if spk in B_spk else None)
            assert grp, stem
        else:
            grp = "C"
        items.append({"src": src, "stem": stem, "cat": cat, "spk": spk, "key": key_of(stem), "group": grp,
                      "dur": float(lab["playTime"]), "sents": split_sents(lab["Transcript"])})

    for x in man:
        if not x.get("label"):
            continue
        if x["cat"] in (21, 24) and x["speaker_key"] in EXCLUDE_C:
            continue
        add(f"{KSC}/flac16/{x['path']}", x["stem"], x["cat"], x["label"])
    for x in rt:
        add(f"{KSC}/flac16/{x['path']}", x["stem"], 28, x["label"])
    for f in sorted(os.listdir(f"{H608}/wav16")):
        stem = f[:-5]
        if spk_of(stem) in A_spk:          # A의 평가 세션(F2 학습에만 쓴다)
            add(f"{H608}/wav16/{f}", stem, 28, f"labels/28.감음신경성/{stem}.json")
    stems = Counter(x["stem"] for x in items)
    assert max(stems.values()) == 1, [s for s, n in stems.items() if n > 1]
    chosen = choose_sessions(items)
    out = []
    for x in chosen:
        dst = f"audio/sess/{x['stem']}.flac"
        cpc(x["src"], f"{root}/{dst}")
        out.append({k: x[k] for k in ("stem", "cat", "spk", "key", "group", "dur", "crop_s", "sents")} | {"path": dst})
    return out


def main():
    root = sys.argv[1]
    os.makedirs(f"{root}/meta", exist_ok=True)
    evA, nA_other = build_eval_A(root)
    evB = build_eval_B(root)
    e538 = build_eval_538(root)
    A_spk = {j["spk"] for j in evA}
    B_spk = {j["spk"] for j in evB} | {"YJY"}
    assert len(A_spk) == 15 and len(B_spk) == 19 and not (A_spk & B_spk)
    sess = build_sessions(root, A_spk, B_spk)

    def sents_of(jobs):
        s = set()
        for j in jobs:
            for t in j["targets"]:
                s.add(hangul(t["text"]) if t["kind"] != "min" else hangul(j["own"]))
        return s
    s538 = sents_of(e538)
    excl = {"F1": sorted(sents_of(evA) | s538), "F2": sorted(sents_of(evB) | s538)}
    json.dump(evA, open(f"{root}/meta/eval_A.json", "w"), ensure_ascii=False)
    json.dump(evB, open(f"{root}/meta/eval_B.json", "w"), ensure_ascii=False)
    json.dump(e538, open(f"{root}/meta/eval_538.json", "w"), ensure_ascii=False)
    json.dump(sess, open(f"{root}/meta/sessions.json", "w"), ensure_ascii=False)
    json.dump(excl, open(f"{root}/meta/excl.json", "w"), ensure_ascii=False)
    tk = lambda jobs, k: sum(1 for j in jobs for t in j["targets"] if t["kind"] == k)
    summ = {
        "E-A": {"clips": len(evA), "spk": len(A_spk), "half1_spk": sorted({j["spk"] for j in evA if j["half"] == 1}),
                "other": tk(evA, "other"), "min": tk(evA, "min")},
        "E-B": {"clips": len(evB), "spk": len({j["spk"] for j in evB}), "other": tk(evB, "other"), "min": tk(evB, "min")},
        "E-538": {"clips": len(e538), "spk": len({j["spk"] for j in e538}), "other": tk(e538, "other"), "min": tk(e538, "min")},
        "sessions": {g: {"n": sum(1 for s in sess if s["group"] == g), "spk": len({s["key"] for s in sess if s["group"] == g}),
                         "hours": round(sum(s["crop_s"] or s["dur"] for s in sess if s["group"] == g) / 3600, 2)} for g in "ABC"},
        "excl": {k: len(v) for k, v in excl.items()},
    }
    json.dump(summ, open(f"{root}/meta/build_summary.json", "w"), ensure_ascii=False, indent=1)
    print(json.dumps(summ, ensure_ascii=False, indent=1))
    assert nA_other == 673, nA_other
    print("BUILD_OK")


if __name__ == "__main__":
    main()
