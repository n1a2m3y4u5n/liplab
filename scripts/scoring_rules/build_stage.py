"""맥: 문장 점수 규칙 후보 파드 묶음(docs/scoring-rules-2026-10.md 3절). 점수는 읽지 않는다(목표 문장·조각 시각·화자·절반만).
다리(유효성) 점검에 쓸 지난 점수는 파드가 계산한 뒤 맥에서 비교하므로 여기서는 열지 않는다.

    python scripts/scoring_rules/build_stage.py explore STAGE_ROOT   # 538 절반 0, 범주 28 절반 0, 범주 27 첫 묶음 전부
    python scripts/scoring_rules/build_stage.py confirm STAGE_ROOT   # 538 절반 1, 범주 28 절반 1, 범주 27 두 번째 묶음(세션 FLAC, 파드에서 자름)

만드는 것: STAGE_ROOT/audio/<묶음>/*.wav(또는 c27b2/*.flac + labels), STAGE_ROOT/jobs.json, STAGE_ROOT/stage_summary.json
"""
import json
import os
import random
import shutil
import sys
import zlib
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(APP, "backend"))
sys.path.insert(0, HERE)
import jamo_vocab as JV  # noqa: E402
import targets as TG  # noqa: E402

LAB = os.path.expanduser("~/Downloads/LIPLAB_ALL/liplab-lab")
D = f"{LAB}/data"
NS = f"{D}/ns_stage/root/data"                      # 10/9 ns 묶음: 538 새 21명 600클립(c538n)
AD = f"{D}/adapt_stage/root"                        # 10/9 적응 묶음: E-538(697), E-A(341), E-B(340)
C27R = f"{D}/pod_runs/20261009_0b7hmamwk96ebn/c27"  # 10/9 범주 27 첫 묶음 결과(jobs.json, cuts608.json)
C27F = f"{D}/hi608/c27/flac16"
B2F = f"{D}/hi608/c27/b2/flac16"
LABELS = f"{D}/hi608/labels"


def half538(spk):
    return zlib.crc32(spk.encode()) % 2


def half608(ini):
    return zlib.crc32(ini.encode()) % 2


def cpc(src, dst):
    if not os.path.exists(dst):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)


def jobs538(root, half):
    """c538n 600클립(10/9 ns 짝: 자기·다른 2) ∪ E-538에만 있는 클립(10/9 적응 짝: 자기·다른 2·min 2). min은 E-538 것을 쓰고,
    E-538에 없는 c538n 클립은 클립 이름 순으로 Random(20261007) 한 생성기에서 새로 만든다. 모든 클립에 min2를 더한다."""
    ns = [j for j in json.load(open(f"{NS}/jobs.json", encoding="utf-8")) if j["set"] == "538"]
    e = json.load(open(f"{AD}/meta/eval_538.json", encoding="utf-8"))
    emap = {x["clip"]: x for x in e}
    rows = {}
    for j in ns:
        own = next(t for t, k in j["targets"] if k == "same")
        oth = [t for t, k in j["targets"] if k == "diff"]
        rows[j["clip"]] = {"spk": j["spk"], "src": f"{NS}/{j['path']}", "own": own, "others": oth, "mins": None}
    for x in e:
        own = next(t["text"] for t in x["targets"] if t["kind"] == "own")
        mins = [t for t in x["targets"] if t["kind"] == "min"]
        if x["clip"] in rows:
            assert rows[x["clip"]]["own"] == own, x["clip"]
            rows[x["clip"]]["mins"] = mins
        else:
            rows[x["clip"]] = {"spk": x["spk"], "src": f"{AD}/{x['path']}", "own": own,
                               "others": [t["text"] for t in x["targets"] if t["kind"] == "other"], "mins": mins}
    rng = random.Random(TG.MIN_SEED)
    jobs = []
    for clip in sorted(rows):
        r = rows[clip]
        if r["mins"] is None:
            ms = TG.pick_min(rng, r["own"], JV)
            r["mins"] = [{"text": m["target"], "kind": "min", "tok_idx": m["tok_idx"], "cat": m["cat"], "char_idx": m["char_idx"],
                          "new": m["new"]} for m in ms]
        if half538(r["spk"]) != half:
            continue
        tg = [{"text": r["own"], "kind": "own"}] + [{"text": t, "kind": "other"} for t in r["others"]] + \
             [{k: m[k] for k in ("text", "kind", "tok_idx", "cat")} for m in r["mins"]]
        m2 = min2_from(r["own"], r["mins"])
        if m2:
            tg.append(m2)
        dst = f"audio/538/{clip}.wav"
        cpc(r["src"], f"{root}/{dst}")
        jobs.append({"set": "538", "spk": r["spk"], "clip": clip, "path": dst, "targets": tg})
    return jobs


def min2_from(own, mins):
    """min 목표 문장 두 개에서 바꾼 음절을 되찾아 함께 적용한다(E-538·E-A·E-B의 min에는 char_idx가 없다)."""
    ms = []
    for m in mins[:2]:
        diff = [i for i, (a, b) in enumerate(zip(own, m["text"])) if a != b]
        if len(diff) != 1 or len(own) != len(m["text"]):
            return None
        ms.append({"char_idx": diff[0], "new": TG._onset(m["text"][diff[0]]), "tok_idx": m["tok_idx"], "cat": m["cat"]})
    return TG.min2_of(own, ms, JV)


def jobs608(root, half):
    """범주 28: E-A(10/7 정제본 15명 341) + E-B(10/9 새 18명 340), 10/9 적응 짝 그대로(자기·다른 2·min 2) + min2."""
    jobs = []
    for name, sub in (("eval_A", "evA"), ("eval_B", "evB")):
        for x in json.load(open(f"{AD}/meta/{name}.json", encoding="utf-8")):
            if half608(x["spk"]) != half:
                continue
            assert x["half"] == half
            own = next(t["text"] for t in x["targets"] if t["kind"] == "own")
            tg = [dict(t) for t in x["targets"]]
            m2 = min2_from(own, [t for t in x["targets"] if t["kind"] == "min"])
            if m2:
                tg.append(m2)
            dst = f"audio/c28/{os.path.basename(x['path'])}"
            cpc(f"{AD}/{x['path']}", f"{root}/{dst}")
            jobs.append({"set": "c28", "spk": "28-" + x["spk"], "clip": x["clip"], "path": dst, "targets": tg})
    return jobs


def jobs_c27b1(root):
    """범주 27 첫 묶음 758조각: 10/9 cuts608.json 시각으로 세션 FLAC에서 다시 자른다(cut_608과 같은 표본 경계).
    자기·다른 2는 10/9 jobs.json 그대로, min·min2는 새로 만든다(조각 순서, Random(20261007))."""
    import soundfile as sf
    cuts = json.load(open(f"{C27R}/n608/out/cuts608.json", encoding="utf-8"))
    kept, info = TG.select_c27(cuts)
    J = json.load(open(f"{C27R}/out/jobs.json", encoding="utf-8"))
    pairs = {}
    for r in J["s18"]:
        pairs.setdefault(r["clip"], []).append((r["target"], r["kind"]))
    assert len(pairs) == len(kept) == 758, (len(pairs), len(kept))
    rng = random.Random(TG.MIN_SEED)
    jobs, cache = [], {}
    for c in kept:
        cid = TG.clip_id(c)
        own = [t for t, k in pairs[cid] if k == "same"]
        assert own == [c["target"]], cid
        dst = f"audio/c27b1/{cid.replace(':', '_')}.wav"
        if not os.path.exists(f"{root}/{dst}"):
            if c["file"] not in cache:
                cache.clear()
                y, sr = sf.read(f"{C27F}/{c['file']}")
                assert sr == 16000 and y.ndim == 1
                cache[c["file"]] = y
            y = cache[c["file"]]
            os.makedirs(f"{root}/audio/c27b1", exist_ok=True)
            sf.write(f"{root}/{dst}", y[int(c["start"] * 16000):int(c["end"] * 16000)], 16000)
        tg = [{"text": c["target"], "kind": "own"}] + [{"text": t, "kind": "other"} for t, k in pairs[cid] if k == "diff"] + \
             TG.min_targets(rng, c["target"], JV)
        jobs.append({"set": "c27b1", "spk": TG.spk608(c["file"][:-5]), "clip": cid, "path": dst, "targets": tg})
    return jobs, info


def stage_c27b2(root):
    """범주 27 두 번째 묶음: 세션 FLAC과 라벨만 올린다. 자르기·고르기·짝은 파드(feat_pod.py b2jobs)가 같은 규칙으로 한다."""
    os.makedirs(f"{root}/c27b2/s608", exist_ok=True)
    os.makedirs(f"{root}/c27b2/labels", exist_ok=True)
    n = 0
    import glob
    for f in sorted(glob.glob(f"{B2F}/*.flac")):
        b = os.path.basename(f)[:-5]
        src = glob.glob(f"{LABELS}/*/{b}.json")
        assert src, b
        cpc(f, f"{root}/c27b2/s608/{b}.flac")
        cpc(src[0], f"{root}/c27b2/labels/{b}.json")
        n += 1
    return n


def main():
    phase, root = sys.argv[1], os.path.abspath(sys.argv[2])
    os.makedirs(root, exist_ok=True)
    if phase == "explore":
        j538 = jobs538(root, 0)
        j608 = jobs608(root, 0)
        j27, info = jobs_c27b1(root)
        jobs = j538 + j608 + j27
        summ = {"phase": phase, "c27b1_select": info}
    elif phase == "confirm":
        jobs = jobs538(root, 1) + jobs608(root, 1)
        summ = {"phase": phase, "c27b2_sessions": stage_c27b2(root)}
    else:
        sys.exit("explore|confirm")
    for j in jobs:
        assert os.path.exists(f"{root}/{j['path']}"), j["path"]
    json.dump(jobs, open(f"{root}/jobs.json", "w"), ensure_ascii=False)
    summ["clips"] = dict(Counter(j["set"] for j in jobs))
    summ["speakers"] = {s: len({j["spk"] for j in jobs if j["set"] == s}) for s in summ["clips"]}
    summ["targets"] = {s: dict(Counter(t["kind"] for j in jobs if j["set"] == s for t in j["targets"])) for s in summ["clips"]}
    json.dump(summ, open(f"{root}/stage_summary.json", "w"), ensure_ascii=False, indent=1)
    print("STAGE_OK", json.dumps(summ, ensure_ascii=False))


if __name__ == "__main__":
    main()
