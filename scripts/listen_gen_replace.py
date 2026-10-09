#!/usr/bin/env python
"""일반화 검사 낱말 다시 합성·교체 후보(docs/listen-gen-replace-2026-10.md). 맥에서 도는 가벼운 계산이다.

    python scripts/listen_gen_replace.py stage OUTDIR
        OUTDIR/score_targets.jsonl   kresnik 점수 대상(contrast_score.py 꼴). (B) 후보의 m3 클립, 훈련 풀로 돌아갈 네 낱말의 훈련 목소리 클립,
                                     네 낱말의 지금 m3 클립(대조)
        OUTDIR/resynth/targets.jsonl·comps.jsonl   (A) 네 낱말 m3 다시 합성 대상(소리 점검 꼴)과 대조 목록
        OUTDIR/candidates.json       (B) 1~4 조건을 만족한 앞의 12개와 그 판정 과정
    python scripts/listen_gen_replace.py judge OUTDIR SCORE.jsonl [--resynth RESULT_DIR] --report OUT.json
        (A)·(B) 판정(사전 기준 2~4절)과 낱말마다 권하는 길

앱 코드(GEN_WORDS, 소리 목록)는 바꾸지 않는다. 다시 만든 규칙이 지금 GEN_WORDS를 그대로 내지 않으면 (B)는 하지 않는다.
"""
import argparse
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "backend")
sys.path.insert(0, BACKEND)
sys.path.insert(0, HERE)
import curriculum as C  # noqa: E402
import listen_curriculum as L  # noqa: E402
import sound_clips as S  # noqa: E402

FAILED = ("마늘", "바늘", "오빠", "나물")
TRAIN_VOICES = ("m1", "f1", "m2", "f2")
N_SCORE = 12
LAB = os.path.expanduser("~/Downloads/liplab-lab")
SQA_RUNS = ("20261007_mwo4z0qqys996o", "20261007_y0mn97i6mjalnq")
# 검토 문서 3.3절의 '추상어·시간어와 한 음절로 뜻이 여럿인 말'
ABSTRACT = ("사랑·행복·슬픔·겁·시작·맛·날·이틀·공부·수업·시험·사물·형제·목소리·말·배·눈·밤·차·다리·등·병·비·양·파·무·죽·기사·기타·자·살·"
            "이·개·목·폭·남·마을·방·약·강·산·불·풀·돌·피·소·국·콩·곰·선생·답·볼·탑").split("·")


def jl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def vocab():
    out = {}
    for line in open(os.path.join(HERE, "data", "nikl_learner_vocab.tsv"), encoding="utf-8"):
        if line.startswith("#") or line.startswith("word\t"):
            continue
        w, pos, g = line.rstrip("\n").split("\t")
        out.setdefault((w, pos), g)
    return out


def candidates(forms=("A", "B")):
    """원래 규칙의 후보(가나다순). forms는 '검사 문장에 나오지 않음'에서 볼 폼."""
    from assessment import test_only_words
    voc = vocab()
    skip = set(C.STAGE2_EXCLUDED) | set(L.LISTEN_EXCLUDED) | set(test_only_words())
    bank = [w["word"] for w in C.WORD_BANK if w["word"] not in skip]
    ax = {t for p in L.AX_PAIRS for t in (p["a"], p["b"])}
    texts = list(L.TRAIN_SENTENCES) + [s for k in forms for s in L.TEST_FORMS[k]]
    for c in L.CONVO_ITEMS:
        texts += [c["line"], c["paraphrase"], c["question"]] + list(c["options"])
    m = json.load(open(os.path.join(BACKEND, "data", "pilot", "battery_manifest.json"), encoding="utf-8"))
    p3 = {it["word"] for its in m["layers"]["word"]["items"].values() for it in its}
    out = []
    for w in bank:
        if voc.get((w, "명")) not in ("A", "B") or len(w) > 2 or w in ABSTRACT or w in ax or w in p3:
            continue
        if any(w in t for t in texts):
            continue
        out.append(w)
    return sorted(set(out))


def n36(w, pool):
    return sum(1 for b in pool if b != w and 3 <= L.sound_distance(w, b) <= 6)


def greedy(order, full, start=(), limit=20):
    sel = list(start)
    for w in order:
        if len(sel) >= limit:
            break
        trial = sel + [w]
        pool = [b for b in full if b not in set(trial)]
        if all(n36(x, pool) >= 3 for x in trial):
            sel.append(w)
    return sel


class config:
    """GEN_WORDS를 gen(가나다순)으로, retire(물러난 검사 낱말)를 낱말 고르기에서 아예 뺀 상태로 잠깐 바꾼다(모듈 전역, 끝나면 되돌림).
    retire는 사후 변경 1(문서 3절 끝)의 (B′)다. 돌아가는 낱말이 다른 검사 문항의 보기로 들어가지 않게 훈련 풀에도 넣지 않는다."""

    def __init__(self, gen, retire=()):
        self.gen, self.retire = sorted(gen), tuple(retire)

    def __enter__(self):
        self.old = (L.GEN_WORDS, dict(L.LISTEN_EXCLUDED))
        L.GEN_WORDS = self.gen
        for w in self.retire:
            L.LISTEN_EXCLUDED[w] = "일반화 검사에서 물러남(교체 후보 판정용)"
        L._NEIGHBOR_CACHE.clear()
        return self

    def __exit__(self, *exc):
        L.GEN_WORDS = self.old[0]
        L.LISTEN_EXCLUDED.clear()
        L.LISTEN_EXCLUDED.update(self.old[1])
        L._NEIGHBOR_CACHE.clear()
        return False


RETIRE = FAILED   # (B′): 물러난 네 낱말은 훈련 풀로 돌려보내지 않는다


def items_for(gen, retire=RETIRE):
    """GEN_WORDS를 gen으로 바꿨을 때의 gen_test_items."""
    with config(gen, [w for w in retire if w not in gen]):
        its = L.gen_test_items(L.word_pool(include_gen=True))
        return {it["target"]: it["options"] for it in its}


def gen_comps(gen, w):
    """(c) 꼴 경쟁 글(include_gen 풀 이웃에서 검사 낱말을 뺀 것, 거리 1~6 가까운 순 최대 5개)과 그 문항 보기의 합집합."""
    import listen_contrast_targets as T
    with config(gen, [x for x in RETIRE if x not in gen]):
        gp = L.word_pool(include_gen=True)
        g = set(gen)
        train = [x for x in gp if x not in g]
        full = L._neighbors(list(train) + [x for x in L.GEN_WORDS if x not in set(train)])
        comps = T.nearest(full, w, exclude=g)
    opts = items_for(gen).get(w, [])
    have = {c["text"] for c in comps}
    for o in opts:
        if o != w and o not in have:
            comps.append({"text": o, "dist": L.sound_distance(w, o), "option": True})
    for c in comps:
        c.setdefault("option", c["text"] in opts)
    return comps


def unresolved():
    out = set()
    for run in SQA_RUNS:
        p = os.path.join(LAB, "data", "pod_runs", run, "sqa", "summary.json")
        try:
            for u in json.load(open(p, encoding="utf-8"))["unresolved"]:
                out.add((u["voice"], u["key"]))
        except (OSError, ValueError, KeyError):
            print("경고: 소리 점검 요약 없음", p, file=sys.stderr)
    return out


def stage(outdir):
    os.makedirs(os.path.join(outdir, "resynth"), exist_ok=True)
    man = json.load(open(os.path.join(BACKEND, "data", "sound", "manifest.json"), encoding="utf-8"))
    cand = candidates()
    order = list(cand)
    random.Random(20261007).shuffle(order)
    full = L.word_pool(include_gen=True)
    sel = greedy(order, full)
    reproduced = sorted(sel) == sorted(L.GEN_WORDS)
    info = {"n_candidates": len(cand), "reproduced": reproduced, "selected": sel}
    print("후보", len(cand), "다시 만든 20개 = 지금 GEN_WORDS:", reproduced)
    # 지금 GEN_WORDS가 폼 C·D 문장에 글자로 들어 있는가(보고만)
    info["gen_in_forms_cd"] = {w: [s for k in ("C", "D") for s in L.TEST_FORMS[k] if w in s] for w in L.GEN_WORDS
                               if any(w in s for k in ("C", "D") for s in L.TEST_FORMS[k])}
    base16 = [w for w in L.GEN_WORDS if w not in FAILED]
    base_items = items_for(L.GEN_WORDS)
    fullb = [b for b in full if b not in set(RETIRE)]
    cand_all = set(candidates(forms=("A", "B", "C", "D")))
    unres = unresolved()
    rest = order[order.index(sel[-1]) + 1:] if reproduced else []
    log, ok = [], []
    for w in rest:
        why = []
        if w not in cand_all:
            why.append("검사 문장 C·D에 나옴")
        trial = base16 + [w]
        pool = [b for b in fullb if b not in set(trial)]
        if not all(n36(x, pool) >= 3 for x in trial):
            why.append("거리 3~6 이웃 셋 미만")
        if not why:
            its = items_for(trial)
            if any(its.get(x) != base_items.get(x) for x in base16):
                why.append("나머지 16문항 보기가 바뀜")
        if w not in man["clips"].get("m3", {}):
            why.append("m3 클립 없음")
        if ("m3", w) in unres:
            why.append("소리 점검 미해결")
        log.append({"word": w, "ok": not why, "why": why})
        if not why:
            ok.append(w)
        if len(ok) >= N_SCORE:
            break
    info["order_after_20"] = rest[:len(log)]
    info["log"] = log
    info["scored"] = ok
    rows = []

    def add(uid, set_, voice, w, comps):
        clip = man["clips"].get(voice, {}).get(S.normalize_text(w))
        if clip and comps:
            rows.append({"uid": uid, "set": set_, "voice": voice, "text": w, "key": S.normalize_text(w), "clip": clip["id"],
                         "comps": comps})
    for w in ok:
        add(f"genb:m3:{w}", "gen", "m3", w, gen_comps(base16 + [w], w))
    for w in FAILED:
        add(f"gen:m3:{w}", "gen", "m3", w, gen_comps(L.GEN_WORDS, w))
    # 훈련 풀로 돌아간다면(원래 (B), 보고만): (b) 꼴, 네 낱말이 돌아간 훈련 풀에서 가까운 이웃 최대 5개
    import listen_contrast_targets as T
    with config(base16 + ok[:4]):
        nb = L._neighbors(L.word_pool())
        for v in TRAIN_VOICES:
            for w in FAILED:
                add(f"back:{v}:{w}", "word", v, w, T.nearest(nb, w))
    with open(os.path.join(outdir, "score_targets.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    # (A) 다시 합성 대상: 소리 점검 꼴(sound_qa_targets.row)과 대조 목록(uid가 같음)
    import sound_qa_targets as Q
    ev = {v["id"]: v["engine_voice"] for v in man["voices"]}
    qa, comps = [], []
    for w in FAILED:
        key = S.normalize_text(w)
        clip = man["clips"]["m3"][key]
        r = Q.row("m3", ev["m3"], key, clip.get("text") or w, ["listen"], clip)
        qa.append(r)
        comps.append({"uid": r["uid"], "set": "gen", "voice": "m3", "text": w, "key": key, "clip": clip["id"],
                      "comps": gen_comps(L.GEN_WORDS, w)})
    for name, data in (("targets.jsonl", qa), ("comps.jsonl", comps)):
        with open(os.path.join(outdir, "resynth", name), "w", encoding="utf-8") as f:
            for r in data:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    json.dump(info, open(os.path.join(outdir, "candidates.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("(B) 1~4 통과", len(ok), ok)
    print("점수 대상", len(rows), "다시 합성 대상", len(qa))
    return info


def min_margin(rec):
    if not rec or rec.get("err"):
        return None, []
    oks = [c for c in rec.get("comps", []) if c.get("status") == "ok"]
    return (min(c["margin"] for c in oks) if oks else None), [c for c in oks if c["margin"] <= 0]


def judge(outdir, score_path, resynth_dir, report):
    info = json.load(open(os.path.join(outdir, "candidates.json"), encoding="utf-8"))
    sc = {r["uid"]: r for r in jl(score_path)}
    out = {"A": {}, "B": {"picked": [], "rows": []}, "back": {}, "orig": {}}
    for w in FAILED:
        mm, bad = min_margin(sc.get(f"gen:m3:{w}"))
        out["orig"][w] = {"min_margin": mm, "fail": [(c["text"], c["margin"]) for c in bad]}
    # (A)
    if resynth_dir and os.path.exists(os.path.join(resynth_dir, "final.jsonl")):
        fin = {r["uid"]: r for r in jl(os.path.join(resynth_dir, "final.jsonl"))}
        pick = json.load(open(os.path.join(resynth_dir, "pick.json"), encoding="utf-8"))
        tg = {r["uid"]: r for r in jl(os.path.join(resynth_dir, "targets.jsonl"))}
        for uid, t in tg.items():
            p = pick.get(uid, {}) if isinstance(pick, dict) else {}
            out["A"][t["key"]] = {"uid": uid, "adopted": uid in fin, "final": fin.get(uid), "pick": p}
    # (B): 1~4 통과 순서대로, 5(모든 margin > 0)를 만족하고 합쳐도 2·3 조건을 지키는 것 넷
    base16 = [w for w in L.GEN_WORDS if w not in FAILED]
    base_items = items_for(L.GEN_WORDS)
    full = [b for b in L.word_pool(include_gen=True) if b not in set(RETIRE)]
    picked = []
    for w in info["scored"]:
        mm, bad = min_margin(sc.get(f"genb:m3:{w}"))
        row = {"word": w, "min_margin": mm, "fail": [(c["text"], c["margin"]) for c in bad], "ok5": mm is not None and not bad}
        if row["ok5"] and len(picked) < 4:
            trial = base16 + picked + [w]
            pool = [b for b in full if b not in set(trial)]
            its = items_for(trial)
            row["combo_ok"] = all(n36(x, pool) >= 3 for x in trial) and all(its.get(x) == base_items.get(x) for x in base16)
            if row["combo_ok"]:
                picked.append(w)
                row["options"] = its.get(w)
        out["B"]["rows"].append(row)
    out["B"]["picked"] = picked
    for uid, r in sc.items():
        if uid.startswith("back:"):
            _, v, w = uid.split(":")
            mm, bad = min_margin(r)
            out["back"].setdefault(w, {})[v] = {"min_margin": mm, "fail": [(c["text"], c["margin"], c.get("dist")) for c in bad]}
    # 낱말마다 권하는 길(4절)
    rec = {}
    for i, w in enumerate(FAILED):
        a = out["A"].get(w, {})
        if a.get("adopted"):
            rec[w] = "A"
        elif i < len(picked):
            rec[w] = f"B:{picked[i]}"
        else:
            rec[w] = "없음"
    out["recommend"] = rec
    json.dump(out, open(report, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"orig": out["orig"], "A": {k: v["adopted"] for k, v in out["A"].items()}, "B": picked, "recommend": rec},
                     ensure_ascii=False, indent=1))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("stage")
    s.add_argument("outdir")
    j = sub.add_parser("judge")
    j.add_argument("outdir")
    j.add_argument("score")
    j.add_argument("--resynth", default="")
    j.add_argument("--report", required=True)
    a = ap.parse_args()
    if a.cmd == "stage":
        stage(a.outdir)
    else:
        judge(a.outdir, a.score, a.resynth, a.report)


if __name__ == "__main__":
    main()
