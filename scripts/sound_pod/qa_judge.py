"""품질 점검 판정·선택(docs/sound-qa-2026-10.md 2~5절). 가벼운 계산(어느 가상환경이든 numpy·scipy와 백엔드 모듈만).

    python qa_judge.py judge  WORK --cands orig|c0,c1…   → WORK/judged.<후보>.jsonl
    python qa_judge.py ref    WORK                       → WORK/ref.json(기존 클립 판정에서 빠르기·레벨 기준)
    python qa_judge.py decide WORK [--force-normalize 0|1] → WORK/plan.json, WORK/stage1.uids
    python qa_judge.py escalate WORK                     → WORK/stage2.uids(1단계 c0·c1에 통과 후보가 없는 것)
    python qa_judge.py final  WORK                       → WORK/final.jsonl, WORK/summary.json

WORK 안: targets.jsonl, asr/*.jsonl, eval/*.jsonl, cand/<후보>/synth.*.jsonl.
기준(ref.json)은 기존 클립 점검 결과로 만든다. 목록에 없는 글만 합성할 때(기존 클립 없음)는 --ref로 저장소의
scripts/sound_pod/qa_ref.json(이번 점검의 기준)을 넘긴다.
"""
import argparse
import glob
import json
import os
import sys
from collections import Counter, defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qa_rules as Q  # noqa: E402

STAGE1 = ["c0", "c1"]
STAGE2 = ["c2", "c3", "c4", "c5", "c6", "c7"]
STAGE3 = ["c8", "c9", "c10", "c11", "c12", "c13", "c14", "c15"]   # 사후 추가: 2단계 뒤 통과 후보가 없는 새 글만


def P(work, *a):
    return os.path.join(work, *a)


def load_ref(work, ref_path=None):
    p = ref_path or P(work, "ref.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def load_eval(work):
    """(uid, 후보) → D-GOP·신호 기록. 같은 것이 여러 번 있으면 오류 없는 줄을 쓴다."""
    ev = {}
    for r in Q.read_jsonl(sorted(glob.glob(P(work, "eval", "*.jsonl")))):
        k = (r["uid"], r["cand"])
        if k not in ev or (ev[k].get("err") and not r.get("err")):
            ev[k] = r
    return ev


def pron_group(t):
    return Q.length_group(int(t.get("n_syl") or 0), t["key"])


def judge(work, cands, ref_path=None):
    targets = {t["uid"]: t for t in Q.load_targets(P(work, "targets.jsonl"))}
    asr = {(r["uid"], r["cand"]): r for r in Q.read_jsonl(glob.glob(P(work, "asr", "*.jsonl")))}
    ev = load_eval(work)
    syn = {(r["uid"], r["cand"]): r for r in Q.read_jsonl(glob.glob(P(work, "cand", "*", "synth.*.jsonl"))) if r.get("ok")}
    ref = load_ref(work, ref_path)
    for c in cands:
        n = 0
        with open(P(work, f"judged.{c}.jsonl"), "w", encoding="utf-8") as out:
            for uid, t in targets.items():
                e, s = ev.get((uid, c)), asr.get((uid, c))
                if e is None or s is None:
                    continue
                g = pron_group(t)
                m = dict(e.get("metrics") or {})
                # 사후 변경 1: 문장 끝 '요'가 파일 끝에 정렬된 클립은 그 음절을 빼고 모음 끊김·쉼을 다시 센다
                stuck = ""
                try:
                    import jamo_vocab
                    groups = Q.syllable_groups_ms(e.get("phones") or [], jamo_vocab.text_to_tokens(t["text"]))
                    se = (m["dur_ms"] - m["tail_ms"]) if m.get("tail_ms") is not None else None
                    stuck = Q.tail_stuck(groups, se)
                    if stuck:
                        m["vowel_drop_n"] = max(0, int(m.get("vowel_drop_n") or 0) - 1)
                    if stuck == "syl":
                        m["gap_in_word_ms"], m["gap_between_ms"] = Q.max_gaps(groups[:-1])
                except Exception:
                    pass
                per_v = Q.per(t["text"], s["hyp"])
                pron = Q.judge_pron(g, per_v, e.get("dgop"), s["hyp"])
                rv = Q.rate_value(m, g)
                rz = None
                lvl = None
                if ref:
                    rr = (ref.get("rate") or {}).get(f"{t['voice']}|{g}")
                    rz = Q.robust_z(rv, tuple(rr) if rr else None)
                    med = (ref.get("level") or {}).get(t["voice"])
                    if med is not None:
                        raw = m.get("level_db") if c == "orig" else (syn.get((uid, c)) or {}).get("raw_level_db")
                        lvl = None if raw is None else raw - med
                sig = Q.judge_signal(m, g, rz, lvl, check_pad=(c == "orig"))
                if c == "orig":
                    syl, dur = t.get("orig_syl"), float(t.get("orig_ms") or m.get("dur_ms") or 0)
                else:
                    syl, dur = e.get("syl"), float(m.get("dur_ms") or 0)
                sv = Q.syl_valid(syl, int(t.get("n_syl") or 0), dur)
                res = Q.combine(pron, sig, sv)
                try:   # 참고 기록(판정에 안 씀): 낱말 단위 소리 나는 대로 정답 비율
                    from listen_curriculum import word_score
                    wp = word_score(t["text"], s["hyp"])["proportion"]
                except Exception:
                    wp = None
                rec = {"uid": uid, "cand": c, "voice": t["voice"], "key": t["key"], "group": g, "hyp": s["hyp"], "word_prop": wp,
                       "per": None if per_v is None else round(per_v, 4), "dgop": e.get("dgop"), "rate": rv,
                       "rate_z": None if rz is None else round(rz, 3), "level_dev": None if lvl is None else round(lvl, 2),
                       **res, "tail_stuck": stuck, "metrics": m}
                if c == "orig" and e.get("syl") and t.get("orig_syl") and len(e["syl"]) == len(t["orig_syl"]):
                    rec["resync_start_diff_ms"] = [abs(x[0] - y[0]) for x, y in zip(e["syl"], t["orig_syl"])]
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n += 1
        print(f"JUDGE_OK {c} n={n}", flush=True)


def make_ref(work):
    rows = Q.read_jsonl([P(work, "judged.orig.jsonl")])
    if not rows:   # judge가 기준 없이 한 번 돈 결과로 만든다(빠르기·레벨 항목만 기준이 필요하다)
        sys.exit("judged.orig.jsonl 없음")
    rate, level = defaultdict(list), defaultdict(list)
    for r in rows:
        rate[f"{r['voice']}|{r['group']}"].append(r.get("rate"))
        level[r["voice"]].append((r.get("metrics") or {}).get("level_db"))
    out = {"rate": {k: Q.robust_ref(v) for k, v in rate.items()},
           "level": {k: float(np.median([x for x in v if x is not None])) for k, v in level.items()}}
    json.dump(out, open(P(work, "ref.json"), "w"), ensure_ascii=False, indent=1)
    print("REF_OK", json.dumps(out, ensure_ascii=False))


def pct(v, ps=(10, 50, 90)):
    v = [x for x in v if x is not None]
    return {f"p{p}": round(float(np.percentile(v, p)), 2) for p in ps} if v else {}


def decide(work, force=None):
    rows = Q.read_jsonl([P(work, "judged.orig.jsonl")])
    lead = [(r["metrics"] or {}).get("lead_ms") for r in rows]
    tail = [(r["metrics"] or {}).get("tail_ms") for r in rows]
    lvl = [(r["metrics"] or {}).get("level_db") for r in rows]
    st = {"lead_ms": pct(lead), "tail_ms": pct(tail), "level_db": pct(lvl)}
    w = lambda d: d["p90"] - d["p10"]
    rule = {"lead_width": w(st["lead_ms"]), "tail_width": w(st["tail_ms"]), "level_width": w(st["level_db"])}
    norm = rule["lead_width"] > 40 or rule["tail_width"] > 60 or rule["level_width"] > 3
    if force is not None:
        norm = bool(force)
    tiers = Counter(r["tier"] for r in rows)
    plan = {"normalize": norm, "stats": st, "rule": rule, "orig_tiers": dict(tiers), "n": len(rows)}
    json.dump(plan, open(P(work, "plan.json"), "w"), ensure_ascii=False, indent=1)
    allt = Q.load_targets(P(work, "targets.jsonl"))
    if norm:
        uids = [t["uid"] for t in allt]
    else:
        uids = [r["uid"] for r in rows if r["tier"] != "pass"]
    # 목록에 없던 글(orig_id 없음)은 언제나 합성한다
    have = set(uids)
    uids += [t["uid"] for t in allt if not t.get("orig_id") and t["uid"] not in have]
    plan["new_texts"] = sum(1 for t in allt if not t.get("orig_id"))
    json.dump(plan, open(P(work, "plan.json"), "w"), ensure_ascii=False, indent=1)
    open(P(work, "stage1.uids"), "w").write("\n".join(uids) + "\n")
    print("DECIDE_OK", json.dumps(plan, ensure_ascii=False), "stage1", len(uids))


def best(rows):
    return min(rows, key=Q.select_key) if rows else None


def escalate(work):
    by = defaultdict(list)
    for c in STAGE1:
        for r in Q.read_jsonl([P(work, f"judged.{c}.jsonl")]):
            by[r["uid"]].append(r)
    want = set(open(P(work, "stage1.uids")).read().split())
    out = [u for u in sorted(want) if not any(r["tier"] == "pass" for r in by.get(u, []))]
    open(P(work, "stage2.uids"), "w").write("\n".join(out) + ("\n" if out else ""))
    print("ESCALATE_OK", len(out))


def final(work):
    targets = Q.load_targets(P(work, "targets.jsonl"))
    plan = json.load(open(P(work, "plan.json"))) if os.path.exists(P(work, "plan.json")) else {"normalize": True}
    orig = {r["uid"]: r for r in Q.read_jsonl([P(work, "judged.orig.jsonl")])}
    cand = defaultdict(list)
    for c in STAGE1 + STAGE2 + STAGE3:
        for r in Q.read_jsonl([P(work, f"judged.{c}.jsonl")]):
            cand[r["uid"]].append(r)
    ev = load_eval(work)
    syn = {(r["uid"], r["cand"]): r for r in Q.read_jsonl(glob.glob(P(work, "cand", "*", "synth.*.jsonl"))) if r.get("ok")}
    summ = Counter()
    unresolved = []
    with open(P(work, "final.jsonl"), "w", encoding="utf-8") as out:
        for t in targets:
            u = t["uid"]
            o = orig.get(u)
            b = best(cand.get(u, []))
            if o is None and b is None:
                summ["no_data"] += 1
                continue
            if o is None:                           # 목록에 없던 글: 통과한 후보만 넣는다(문서 4절, 10/7 콘텐츠 검수 요청)
                choice = b["cand"] if b["tier"] == "pass" else None
            elif b is None:
                choice = "orig"
            elif plan.get("normalize"):
                choice = b["cand"] if Q.RANK[b["tier"]] <= Q.RANK[o["tier"]] else "orig"
            else:
                choice = b["cand"] if Q.RANK[b["tier"]] < Q.RANK[o["tier"]] else "orig"
            chosen = o if choice == "orig" else (b if choice else None)
            if chosen is None or chosen["tier"] != "pass":
                unresolved.append({"uid": u, "voice": t["voice"], "key": t["key"],
                                   "orig_tier": o and o["tier"], "best_tier": b and b["tier"], "choice": choice,
                                   "flags": (chosen or b or {}).get("flags"), "hyp": (chosen or b or {}).get("hyp"),
                                   "dgop": (chosen or b or {}).get("dgop")})
            summ[f"choice_{'orig' if choice == 'orig' else ('none' if choice is None else 'new')}"] += 1
            summ[f"final_{chosen['tier'] if chosen else 'none'}"] += 1
            if choice and choice != "orig":
                e = ev[(u, choice)]
                s = syn.get((u, choice)) or {}
                em = e["metrics"]
                se = (em["dur_ms"] - em["tail_ms"]) if em.get("tail_ms") is not None else None
                out.write(json.dumps({"uid": u, "voice": t["voice"], "key": t["key"], "cand": choice,
                                      "ms": int(round(float(em["dur_ms"]))), "syl": Q.fix_tail_syllables(e["syl"], se),
                                      "syl_raw": e["syl"], "tail_stuck": chosen.get("tail_stuck"),
                                      "tier": chosen["tier"], "orig_tier": o and o["tier"], "dgop": chosen["dgop"],
                                      "per": chosen["per"], "tts_text": s.get("tts_text"),
                                      "peak_limited_db": s.get("peak_limited_db")}, ensure_ascii=False) + "\n")
    # 기존 클립을 그대로 두는 경우에도 음절 시각은 사후 변경 1로 고친다(파일은 그대로, 목록의 syl만)
    with open(P(work, "orig_sylfix.jsonl"), "w", encoding="utf-8") as fo:
        for u, o in orig.items():
            em = o.get("metrics") or {}
            se = (em["dur_ms"] - em["tail_ms"]) if em.get("tail_ms") is not None else None
            t = next((x for x in targets if x["uid"] == u), None)
            if t and t.get("orig_syl"):
                fx = Q.fix_tail_syllables(t["orig_syl"], se)
                if fx != t["orig_syl"]:
                    fo.write(json.dumps({"uid": u, "voice": t["voice"], "key": t["key"], "syl": fx}, ensure_ascii=False) + "\n")
    json.dump({"counts": dict(summ), "unresolved": unresolved}, open(P(work, "summary.json"), "w"), ensure_ascii=False, indent=1)
    print("FINAL_OK", json.dumps(dict(summ), ensure_ascii=False), "unresolved", len(unresolved))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd"); ap.add_argument("work")
    ap.add_argument("--cands", default="orig"); ap.add_argument("--ref", default=None)
    ap.add_argument("--force-normalize", default=None)
    a = ap.parse_args()
    if a.cmd == "judge":
        judge(a.work, [c for c in a.cands.split(",") if c], a.ref)
    elif a.cmd == "ref":
        make_ref(a.work)
    elif a.cmd == "decide":
        decide(a.work, None if a.force_normalize is None else a.force_normalize == "1")
    elif a.cmd == "escalate":
        escalate(a.work)
    elif a.cmd == "final":
        final(a.work)
    else:
        sys.exit("judge|ref|decide|escalate|final")


if __name__ == "__main__":
    main()
