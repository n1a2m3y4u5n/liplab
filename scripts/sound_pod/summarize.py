"""비교 결과 요약(맥이나 파드, 표준 라이브러리만).
    python summarize.py RUN_DIR   (RUN_DIR/out/cmp/<엔진>/synth.jsonl, utmos.jsonl, RUN_DIR/eval/<엔진>.*.jsonl, RUN_DIR/out/cpu/<엔진>/synth.jsonl)
표본 범주(한 음절, 단어, 문맥 문장, 문장 풀, 대화)별로도 나눈다."""
import glob, json, os, statistics as st, sys

run = sys.argv[1]
sample = {e["key"]: e for e in json.load(open(os.path.join(run, "sample.json"), encoding="utf-8"))}


def cat(e):
    if e["n_syl"] == 1:
        return "1음절"
    s = e["sources"]
    if "closure" in s:
        return "문맥"
    if "sentence" in s:
        return "문장"
    if "convo" in s:
        return "대화"
    return "단어"


def jl(paths):
    out = {}
    for p in paths:
        for line in open(p, encoding="utf-8"):
            try:
                r = json.loads(line)
                out[r["id"]] = r
            except ValueError:
                pass
    return out


def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(st.mean(xs), 3) if xs else None


rows = []
for d in sorted(glob.glob(os.path.join(run, "out", "cmp", "*"))):
    name = os.path.basename(d)
    syn = jl([os.path.join(d, "synth.jsonl")])
    ev = jl(glob.glob(os.path.join(run, "eval", f"{name}.*.jsonl")))
    mos = jl(glob.glob(os.path.join(d, "utmos.jsonl")))
    cpu = jl(glob.glob(os.path.join(run, "out", "cpu", {"st_F1": "supertonic", "cb": "chatterbox", "melo": "melo"}.get(name, "-"), "synth.jsonl")))
    asr = jl(glob.glob(os.path.join(run, "asr", f"{name}.asr.jsonl")))
    for i, x in asr.items():
        ev.setdefault(i, {"id": i, "key": x["key"]}).update({"asr": x["asr"], "cer": x["cer"], "app_score": x["app_score"]})
    recs = list(ev.values())
    r = {"engine": name, "n_synth_ok": sum(1 for s in syn.values() if s.get("ok")), "n_eval": len(recs)}
    for m in ("base", "large-v3-turbo"):
        asr_ = m
        c = [x["cer"].get(m) for x in recs if m in (x.get("cer") or {})]
        if c:
            r[f"cer_{m}"] = mean(c)
            r[f"exact_{m}"] = round(sum(1 for v in c if v == 0) / len(c), 3)
            r[f"app_{m}"] = mean([(x.get("app_score") or {}).get(m) for x in recs])
    r["dgop"] = mean([x.get("dgop") for x in recs])
    dg = [x for x in recs if "timing_ok" in x]
    r["timing_ok"] = round(sum(1 for x in dg if x.get("timing_ok")) / len(dg), 3) if dg else None
    r["utmos"] = mean([m["mos"] for m in mos.values()])
    gs = [s for s in syn.values() if s.get("ok")]
    r["gpu_rtf"] = round(sum(s["sec"] for s in gs) / max(1e-9, sum(s.get("raw_dur", s["dur"]) for s in gs)), 4) if gs else None
    if cpu:
        cs = [s for s in cpu.values() if s.get("ok")]
        r["cpu2_rtf"] = round(sum(s["sec"] for s in cs) / sum(s.get("raw_dur", s["dur"]) for s in cs), 3)
        r["cpu2_sec_per_sentence"] = round(st.mean(s["sec"] for s in cs), 2)
    r["dur_over_syl_ms"] = round(1000 * st.mean(s["dur"] / max(1, sample[s["key"]]["n_syl"]) for s in gs if s["key"] in sample), 0) if gs else None
    by = {}
    for x in recs:
        e = sample.get(x["key"])
        if not e:
            continue
        b = by.setdefault(cat(e), {"cer": [], "dgop": []})
        b["cer"].append((x.get("cer") or {}).get("large-v3-turbo", (x.get("cer") or {}).get("base")))
        b["dgop"].append(x.get("dgop"))
    r["by_cat"] = {k: {"n": len(v["cer"]), "cer": mean(v["cer"]), "dgop": mean(v["dgop"])} for k, v in sorted(by.items())}
    rows.append(r)
print(json.dumps(rows, ensure_ascii=False, indent=1))
