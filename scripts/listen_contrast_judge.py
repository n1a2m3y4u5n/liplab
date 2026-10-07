#!/usr/bin/env python
"""목소리별 대조 측정 판정(docs/listen-voice-contrast-2026-10.md 4절, 사전 등록 기준). 맥, 가벼운 집계.

    python scripts/listen_contrast_judge.py TARGETS.jsonl SCORE.jsonl --report OUT.json [--avoid backend/data/listen_voice_avoid.json]
        [--verdict verdict.json] [--resynth-out DIR] [--replaced FINAL.jsonl]

--resynth-out: 반영 대상 실패(훈련 목소리)의 다시 합성 대상(소리 점검 꼴 targets.jsonl)과 대조 목록(comps.jsonl)을 DIR에 쓴다.
--replaced: 다시 합성해 바꾼 클립(contrast_pick final의 final.jsonl). 그 (목소리, 글)은 avoid 목록에서 빼고 보고에 '바꿈'으로 적는다.
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))
sys.path.insert(0, HERE)
import sound_clips as S  # noqa: E402

TRAIN = ("m1", "f1", "m2", "f2")
TEST = "m3"
GATE_N = 20
GATE_AGREE = 0.80
CAUTION_PCT = 5


def jl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def group_of(set_, comp):
    """관문 묶음: 소리 구별은 짝 종류, 낱말은 경쟁 낱말의 소리 거리(1, 2, 3~6)."""
    if set_ == "ax":
        return "ax:" + comp["kind"]
    d = int(comp["dist"])
    return "word:d" + ("1" if d == 1 else "2" if d == 2 else "3-6")


def pctl(xs, p):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def hangul(s):
    return "".join(ch for ch in (s or "") if "가" <= ch <= "힣" or ch == " ").strip()


def judge(targets, scores, verdict=None, replaced=()):
    sc = {r["uid"]: r for r in scores if r.get("cand", "orig") == "orig"}
    rows = []
    for t in targets:
        s = sc.get(t["uid"])
        comps = []
        for c in t["comps"]:
            m = next((x for x in (s or {}).get("comps", []) if x["text"] == c["text"]), None) if s and not s.get("err") else None
            st = m["status"] if m else "missing"
            comps.append({**c, "status": st, "margin": m.get("margin") if m else None, "group": group_of(t["set"], c)})
        rows.append({**t, "comps": comps, "greedy": (s or {}).get("greedy"), "err": (s or {}).get("err")})
    # 판정자 타당성 관문(기준 클립, 판정 가능한 비교)
    gate = defaultdict(lambda: [0, 0])
    for r in rows:
        if r["suspect"]:
            continue
        for c in r["comps"]:
            if c["status"] == "ok":
                g = gate[c["group"]]
                g[0] += 1
                g[1] += c["margin"] > 0
    gate_tab = {g: {"n": n, "agree": round(k / n, 4) if n else None, "pass": n >= GATE_N and k / n >= GATE_AGREE}
                for g, (n, k) in sorted(gate.items())}
    # 주의 경계: 대상((a)·(b))별 기준 클립 문항의 가장 작은 margin 5백분위. (c)는 (b)의 값을 쓴다
    ref_min = defaultdict(list)
    for r in rows:
        ms = [c["margin"] for c in r["comps"] if c["status"] == "ok"]
        if ms and not r["suspect"] and r["set"] in ("ax", "word"):
            ref_min[r["set"]].append(min(ms))
    caution_thr = {k: round(pctl(v, CAUTION_PCT), 4) for k, v in ref_min.items()}
    caution_thr["gen"] = caution_thr.get("word")
    rep = set(replaced)
    for r in rows:
        ok = [c for c in r["comps"] if c["status"] == "ok"]
        r["scorable"] = bool(ok)
        r["min_margin"] = min(c["margin"] for c in ok) if ok else None
        fails = [c for c in ok if c["margin"] < 0]
        r["fail"] = bool(fails)
        r["fail_applied"] = [c for c in fails if gate_tab.get(c["group"], {}).get("pass")]
        r["fail_weak"] = [c for c in fails if not gate_tab.get(c["group"], {}).get("pass")]
        thr = caution_thr.get(r["set"])
        r["caution"] = (not r["fail"]) and r["min_margin"] is not None and thr is not None and r["min_margin"] < thr
        r["replaced"] = (r["voice"], r["key"]) in rep
    return rows, gate_tab, caution_thr


def agreement(rows, verdict):
    """보고만: Whisper(의심 목록)·음향 분류와의 일치."""
    out = {}
    tab = Counter()
    hyp_comp = Counter()
    for r in rows:
        if not r["scorable"]:
            continue
        tab[(r["suspect"], r["fail"])] += 1
        if r["suspect"]:
            h = hangul(r.get("hyp")).replace(" ", "")
            m = next((c for c in r["comps"] if c["status"] == "ok" and c["text"].replace(" ", "") == h), None)
            if m:
                hyp_comp["judge_agrees" if m["margin"] < 0 else "judge_disagrees"] += 1
            else:
                hyp_comp["hyp_not_a_competitor"] += 1
    out["whisper_2x2"] = {"suspect_and_fail": tab[(True, True)], "suspect_not_fail": tab[(True, False)],
                          "clean_and_fail": tab[(False, True)], "clean_not_fail": tab[(False, False)]}
    out["whisper_hyp_is_competitor"] = dict(hyp_comp)
    if verdict:
        av = Counter()
        lst = []
        seen = set()
        for r in rows:
            v = verdict.get(f"{r['voice']}:{r['key']}")
            # 같은 (목소리, 글)이 소리 구별과 낱말 양쪽에 있으면 앞의 것(소리 구별)만 센다
            if not v or not r["scorable"] or (r["voice"], r["key"]) in seen:
                continue
            seen.add((r["voice"], r["key"]))
            ac_fail = v["acoustic"] != v["intended"]
            av[(ac_fail, r["fail"])] += 1
            lst.append({"voice": r["voice"], "key": r["key"], "intended": v["intended"], "acoustic": v["acoustic"],
                        "asr": v.get("asr"), "judge_fail": r["fail"], "min_margin": r["min_margin"]})
        out["acoustic_2x2"] = {"acoustic_diff_and_fail": av[(True, True)], "acoustic_diff_not_fail": av[(True, False)],
                               "acoustic_same_and_fail": av[(False, True)], "acoustic_same_not_fail": av[(False, False)]}
        out["acoustic_rows"] = lst
    return out


def avoid_json(rows):
    voices, test = defaultdict(dict), defaultdict(dict)
    for r in rows:
        if r["replaced"]:
            continue
        if r["voice"] in TRAIN:
            fails, dest = r["fail_applied"], voices
        elif r["voice"] == TEST:
            fails, dest = [c for c in r["comps"] if c["status"] == "ok" and c["margin"] < 0], test
        else:
            continue
        for c in fails:
            ent = {"against": c["text"], "margin": round(c["margin"], 3), "set": r["set"], "group": c["group"]}
            lst = dest[r["voice"]].setdefault(r["text"], [])
            if all(e["against"] != c["text"] for e in lst):
                lst.append(ent)
    srt = lambda d: {v: {t: sorted(es, key=lambda e: e["margin"]) for t, es in sorted(d[v].items())} for v in sorted(d)}
    return {"version": 1, "doc": "docs/listen-voice-contrast-2026-10.md",
            "judge": "kresnik/wav2vec2-large-xlsr-korean CTC 로그우도 차 margin = ll(의도) - ll(경쟁), margin < 0이면 실패",
            "rule": "소리 구별: 짝의 두 글 중 하나라도 그 짝의 상대 글에 실패한 목소리를 피함. 낱말 고르기: 정답 글이 실패한 목소리를 피함.",
            "voices": srt(voices), "test_voice_report": srt(test)}


def resynth_targets(rows, man):
    """반영 대상 실패(훈련 목소리, 바꾸지 않은 것) → 소리 점검 꼴 대상과 대조 목록(경쟁 글은 (a)·(b) 합집합)."""
    from sound_qa_targets import row as qa_row
    ev = {v["id"]: v.get("engine_voice") for v in man["voices"]}
    want = {(r["voice"], r["key"]) for r in rows if r["voice"] in TRAIN and r["fail_applied"]}
    by = defaultdict(list)
    for r in rows:
        if (r["voice"], r["key"]) in want:
            by[(r["voice"], r["key"])].append(r)
    qa, comps = [], []
    for (v, k), rs in sorted(by.items()):
        clip = man["clips"][v][k]
        t = qa_row(v, ev[v], k, rs[0]["text"], ["listen"], clip)
        qa.append(t)
        cs = []
        for r in rs:
            for c in r["comps"]:
                if all(x["text"] != c["text"] for x in cs):
                    cs.append({k2: c[k2] for k2 in ("text", "kind", "dist") if k2 in c})
        comps.append({"uid": t["uid"], "set": "+".join(sorted({r["set"] for r in rs})), "voice": v, "text": rs[0]["text"], "key": k,
                      "clip": clip["id"], "comps": cs})
    return qa, comps


def table(rows):
    """목소리 × 대상별 문항 수(판정 가능), 실패, 반영, 판정자 약함, 주의, 판정 불가."""
    t = defaultdict(Counter)
    for r in rows:
        k = (r["voice"], r["set"])
        t[k]["items"] += 1
        if not r["scorable"]:
            t[k]["unscorable"] += 1
            continue
        t[k]["scorable"] += 1
        t[k]["fail"] += r["fail"]
        t[k]["applied"] += bool(r["fail_applied"])
        t[k]["weak_only"] += bool(r["fail_weak"]) and not r["fail_applied"]
        t[k]["caution"] += r["caution"]
        t[k]["replaced"] += r["replaced"] and bool(r["fail_applied"])
    return {f"{v}|{s}": dict(c) for (v, s), c in sorted(t.items())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("targets"); ap.add_argument("score")
    ap.add_argument("--report", required=True)
    ap.add_argument("--avoid", default="")
    ap.add_argument("--verdict", default="")
    ap.add_argument("--resynth-out", default="")
    ap.add_argument("--replaced", default="")
    a = ap.parse_args()
    targets, scores = jl(a.targets), jl(a.score)
    verdict = json.load(open(a.verdict, encoding="utf-8")) if a.verdict else None
    replaced = [(r["voice"], r["key"]) for r in jl(a.replaced)] if a.replaced else []
    rows, gate_tab, thr = judge(targets, scores, verdict, replaced)
    man = json.load(open(os.path.join(HERE, "..", "backend", "data", "sound", "manifest.json"), encoding="utf-8"))
    fails = []
    for r in rows:
        if r["fail"] or r["caution"]:
            fails.append({"voice": r["voice"], "set": r["set"], "text": r["text"], "suspect": r["suspect"], "hyp": r.get("hyp"),
                          "greedy": r["greedy"], "min_margin": r["min_margin"], "caution": r["caution"], "replaced": r["replaced"],
                          "fail": [{"against": c["text"], "margin": c["margin"], "group": c["group"],
                                    "applied": c in r["fail_applied"]} for c in r["comps"] if c["status"] == "ok" and c["margin"] < 0]})
    unsc = Counter()
    for r in rows:
        for c in r["comps"]:
            unsc[c["status"]] += 1
    all_fail_train = defaultdict(set)
    for r in rows:
        if r["voice"] in TRAIN and r["fail_applied"] and not r["replaced"]:
            all_fail_train[(r["set"], r["text"])].add(r["voice"])
    report = {"gate": gate_tab, "caution_threshold": thr, "table": table(rows), "comparison_status": dict(unsc),
              "agreement": agreement(rows, verdict),
              "all_train_voices_fail": sorted(f"{s}:{t}" for (s, t), vs in all_fail_train.items() if len(vs) == len(TRAIN)),
              "m3_gen_fail": [f for f in fails if f["set"] == "gen" and f["fail"]],
              "items": fails}
    json.dump(report, open(a.report, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if a.avoid:
        av = avoid_json(rows)
        json.dump(av, open(a.avoid, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("AVOID", {v: len(d) for v, d in av["voices"].items()}, "entries",
              sum(len(es) for d in av["voices"].values() for es in d.values()), "m3_report", sum(len(d) for d in av["test_voice_report"].values()))
    if a.resynth_out:
        os.makedirs(a.resynth_out, exist_ok=True)
        qa, comps = resynth_targets(rows, man)
        for name, data in (("targets.jsonl", qa), ("comps.jsonl", comps)):
            with open(os.path.join(a.resynth_out, name), "w", encoding="utf-8") as f:
                for x in data:
                    f.write(json.dumps(x, ensure_ascii=False) + "\n")
        print("RESYNTH_TARGETS", len(qa))
    print("GATE", json.dumps(gate_tab, ensure_ascii=False))
    print("CAUTION_THR", thr)
    print("STATUS", dict(unsc))
    for k, v in report["table"].items():
        print("TABLE", k, v)
    print("AGREE", json.dumps({k: v for k, v in report["agreement"].items() if k != "acoustic_rows"}, ensure_ascii=False))
    print("ALL4", report["all_train_voices_fail"])


if __name__ == "__main__":
    main()
