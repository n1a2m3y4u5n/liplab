"""다시 합성 후보 고르기(docs/listen-voice-contrast-2026-10.md 5절). 파드에서 contrast_run.sh resynth가 부른다(가벼운 계산).

    python contrast_pick.py wavmap WORK   → 표준 출력 {uid: [[후보, wav 경로], …]}(합성된 후보 c0~c15)
    python contrast_pick.py pick WORK     → WORK/pick.json(후보마다 등급·가장 작은 margin, 고른 후보), WORK/enc.list(후보/uid)
    python contrast_pick.py encmap WORK   → 표준 출력 {uid: [["enc:" + 후보, ogg 경로]]}
    python contrast_pick.py final WORK    → WORK/final.jsonl(소리 품질 점검 final과 같은 꼴, Ogg로도 모든 margin > 0인 것만)

WORK 안: targets.jsonl(소리 점검 대상 꼴), comps.jsonl(대조 대상 꼴, uid가 같음), cand/<후보>/<uid>.wav, judged.<후보>.jsonl,
cand_score.jsonl·enc_score.jsonl(contrast_score.py 결과), eval/*.jsonl, cand/*/synth.*.jsonl.
채택 조건: 등급 pass이고 판정 가능한 모든 경쟁 글에 margin > 0. 그중 가장 작은 margin이 가장 큰 후보.
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
CANDS = [f"c{i}" for i in range(16)]


def jl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()] if os.path.exists(p) else []


def min_margin(rec):
    """판정 가능한 비교의 가장 작은 margin. 오류나 판정 가능한 비교가 없으면 None."""
    if not rec or rec.get("err"):
        return None
    ms = [c["margin"] for c in rec.get("comps", []) if c.get("status") == "ok"]
    return min(ms) if ms else None


def main():
    cmd, W = sys.argv[1], sys.argv[2]
    comps = {r["uid"]: r for r in jl(os.path.join(W, "comps.jsonl"))}
    if cmd == "wavmap":
        out = {}
        for u in comps:
            out[u] = [[c, p] for c in CANDS for p in [os.path.join(W, "cand", c, u + ".wav")] if os.path.exists(p)]
        json.dump(out, sys.stdout, ensure_ascii=False)
    elif cmd == "pick":
        tier = {}
        for c in CANDS:
            for r in jl(os.path.join(W, f"judged.{c}.jsonl")):
                tier[(r["uid"], c)] = r
        sc = {(r["uid"], r["cand"]): r for r in jl(os.path.join(W, "cand_score.jsonl"))}
        pick, enc = {}, []
        for u in comps:
            rows = []
            for c in CANDS:
                j, s = tier.get((u, c)), sc.get((u, c))
                if j is None and s is None:
                    continue
                mm = min_margin(s)
                rows.append({"cand": c, "tier": j and j["tier"], "flags": j and j.get("flags"), "hyp": j and j.get("hyp"),
                             "dgop": j and j.get("dgop"), "min_margin": mm, "greedy": s and s.get("greedy"),
                             "ok": bool(j and j["tier"] == "pass" and mm is not None and mm > 0)})
            ok = [r for r in rows if r["ok"]]
            best = max(ok, key=lambda r: r["min_margin"]) if ok else None
            pick[u] = {"cands": rows, "chosen": best and best["cand"]}
            if best:
                enc.append(f"{best['cand']}/{u}")
        json.dump(pick, open(os.path.join(W, "pick.json"), "w"), ensure_ascii=False, indent=1)
        open(os.path.join(W, "enc.list"), "w").write("\n".join(enc) + ("\n" if enc else ""))
        print("PICK_OK targets", len(comps), "chosen", len(enc), flush=True)
    elif cmd == "encmap":
        pick = json.load(open(os.path.join(W, "pick.json"), encoding="utf-8"))
        out = {u: [["enc:" + p["chosen"], os.path.join(W, "enc", f"{p['chosen']}_{u}.ogg")]] for u, p in pick.items() if p["chosen"]}
        json.dump(out, sys.stdout, ensure_ascii=False)
    elif cmd == "final":
        import qa_judge as J
        import qa_rules as Q
        pick = json.load(open(os.path.join(W, "pick.json"), encoding="utf-8"))
        es = {r["uid"]: r for r in jl(os.path.join(W, "enc_score.jsonl"))}
        targets = {t["uid"]: t for t in Q.load_targets(os.path.join(W, "targets.jsonl"))}
        ev = J.load_eval(W)
        syn = {(r["uid"], r["cand"]): r for r in Q.read_jsonl(glob.glob(os.path.join(W, "cand", "*", "synth.*.jsonl"))) if r.get("ok")}
        n = 0
        with open(os.path.join(W, "final.jsonl"), "w", encoding="utf-8") as out:
            for u, p in pick.items():
                c = p["chosen"]
                if not c:
                    continue
                mm = min_margin(es.get(u))
                p["enc_min_margin"] = mm
                if mm is None or mm <= 0:
                    p["enc_rejected"] = True
                    continue
                t = targets[u]
                j = next(r for r in p["cands"] if r["cand"] == c)
                e = ev[(u, c)]
                s = syn.get((u, c)) or {}
                em = e["metrics"]
                se = (em["dur_ms"] - em["tail_ms"]) if em.get("tail_ms") is not None else None
                out.write(json.dumps({"uid": u, "voice": t["voice"], "key": t["key"], "cand": c,
                                      "ms": int(round(float(em["dur_ms"]))), "syl": Q.fix_tail_syllables(e["syl"], se),
                                      "syl_raw": e["syl"], "tier": j["tier"], "orig_tier": None, "dgop": j["dgop"],
                                      "min_margin": j["min_margin"], "enc_min_margin": mm, "tts_text": s.get("tts_text"),
                                      "peak_limited_db": s.get("peak_limited_db")}, ensure_ascii=False) + "\n")
                n += 1
        json.dump(pick, open(os.path.join(W, "pick.json"), "w"), ensure_ascii=False, indent=1)
        print("FINAL_OK replaced", n, flush=True)
    else:
        sys.exit("wavmap|pick|encmap|final")


if __name__ == "__main__":
    main()
