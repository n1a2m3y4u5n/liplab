"""V7b 전문가 화자 안 낭독 대 자유발화 진폭 비. 설계와 판정 기준은 docs/v7-clear-speech-2026-10.md 7.3절(측정 전에 커밋).

  select  (맥) 받은 전문가 배치(dl_more 결과 폴더) → 화자 포함 규칙 적용, 낭독(대본 005·006)·자유발화(007·008) 클립 목록
  analyze (맥) MediaPipe 추출 JSON → 화자별 jawOpen 95백분위 비, 절반별 기하평균과 부트스트랩 구간, 판정
  selftest
538 원자료와 클립별 파생 파일은 liplab-lab/data/ 아래에만 둔다. 이 저장소에는 집계 수치만 남긴다.
"""
import argparse
import hashlib
import json
import math
import os
import re
import sys
import unicodedata
import zlib

READ = ("005", "006")
SPONT = ("007", "008")
MIN_CLIPS = 20
MIN_HALF = 8
PAD = 0.08
SCRIPT_RE = re.compile(r"_([CE]\d+)_([A-Z])_(\d{3})_\d+$")


def half_of(spk):
    return zlib.crc32(spk.encode()) % 2


def sh(t):
    """tools/../data/v18/tl_survey.py와 같은 문장 해시."""
    return hashlib.sha1(unicodedata.normalize("NFC", " ".join(str(t).split())).encode()).hexdigest()[:10]


def load_pool(path):
    """라벨 머리 조사 → {문장 해시: 그 문장이 나온 인물 집합}."""
    pool = {}
    for l in open(path, encoding="utf-8"):
        r = json.loads(l)
        for f in r["files"]:
            for h in f.get("texts_sha") or []:
                pool.setdefault(h, set()).add(f.get("person"))
    return pool


def cmd_select(a):
    pool = load_pool(a.pool)
    rows = []
    for l in open(os.path.join(a.root, "manifest.tsv"), encoding="utf-8"):
        p = l.rstrip("\n").split("\t")
        if len(p) >= 3:
            rows.append((p[0][:-4], p[1], p[2]))
    by = {}
    for clip, spk, text in rows:
        m = SCRIPT_RE.search(clip)
        if not m or m.group(2) != "A":
            continue
        person, script = m.group(1), m.group(3)
        if not person.startswith("E"):
            continue
        cond = "read" if script in READ else "spont" if script in SPONT else None
        if cond is None:
            continue
        hit = bool(pool.get(sh(text), set()) - {person})
        by.setdefault(spk, {"person": person, "read": [], "spont": [], "hits": {"read": 0, "spont": 0}})
        by[spk][cond].append(clip)
        by[spk]["hits"][cond] += hit
    speakers = []
    for spk, d in sorted(by.items()):
        ok = d["hits"]["read"] >= 3 and d["hits"]["spont"] <= 1 and len(d["read"]) >= MIN_CLIPS and len(d["spont"]) >= MIN_CLIPS
        why = [] if ok else [w for w, bad in (("read_hits<3", d["hits"]["read"] < 3), ("spont_hits>1", d["hits"]["spont"] > 1),
                                               ("read_clips<20", len(d["read"]) < MIN_CLIPS), ("spont_clips<20", len(d["spont"]) < MIN_CLIPS)) if bad]
        speakers.append({"spk": spk, "person": d["person"], "half": half_of(spk), "n_read": len(d["read"]), "n_spont": len(d["spont"]),
                         "hits": d["hits"], "include": ok, "why": why, "read": d["read"], "spont": d["spont"]})
    json.dump({"root": a.root, "speakers": speakers}, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if a.list:
        with open(a.list, "w", encoding="utf-8") as fo:
            for s in speakers:
                if s["include"]:
                    for c in s["read"] + s["spont"]:
                        fo.write(c + "\n")
    for s in speakers:
        print(s["spk"], s["person"], "half", s["half"], "read", s["n_read"], "spont", s["n_spont"], "hits", s["hits"], "IN" if s["include"] else "OUT " + ",".join(s["why"]))


def clip_values(path):
    """추출 JSON → 문장 구간(앞뒤 0.08초 여유를 뺀 구간)의 프레임별 J, R, S."""
    d = json.load(open(path, encoding="utf-8"))
    ix = {k: i for i, k in enumerate(d["bs_names"])}
    fps = d.get("fps") or 30.0
    n = d.get("n_read") or d.get("n_frames") or 0
    t1 = n / fps - PAD
    J, R, S = [], [], []
    for f in d["frames"]:
        t = f["t_ms"] / 1000.0
        if t < PAD or t > t1:
            continue
        b = f["bs"]
        J.append(b[ix["jawOpen"]])
        R.append(b[ix["mouthFunnel"]] + b[ix["mouthPucker"]])
        S.append((b[ix["mouthSmileLeft"]] + b[ix["mouthSmileRight"]] + b[ix["mouthStretchLeft"]] + b[ix["mouthStretchRight"]]) / 2)
    face_ratio = len(d["frames"]) / max(1, n)
    return J, R, S, face_ratio, n / fps


def boot_ci(logs, n=4000, seed=0):
    import numpy as np
    v = np.asarray(logs, dtype=float)
    rng = np.random.default_rng(seed)
    bs = rng.choice(v, size=(n, len(v)), replace=True).mean(1)
    return [round(float(math.exp(np.percentile(bs, 2.5))), 4), round(float(math.exp(np.percentile(bs, 97.5))), 4)]


def cmd_analyze(a):
    import numpy as np
    sel = json.load(open(a.sel, encoding="utf-8"))
    texts = {}
    for l in open(os.path.join(sel["root"], "manifest.tsv"), encoding="utf-8"):
        p = l.rstrip("\n").split("\t")
        if len(p) >= 3:
            texts[p[0][:-4]] = p[2]
    per = {}
    for s in sel["speakers"]:
        if not s["include"]:
            continue
        cond_vals = {}
        for cond in ("read", "spont"):
            J, R, S, n_ok, syl, secs = [], [], [], 0, 0, 0.0
            for c in s[cond]:
                p = os.path.join(a.bs, c + ".json")
                if not os.path.exists(p):
                    continue
                j, r, ss, fr, dur = clip_values(p)
                if fr < 0.8 or len(j) < 15:          # V2 품질 기준과 같은 값
                    continue
                n_ok += 1
                J += j; R += r; S += ss
                syl += len(re.findall(r"[가-힣]", texts.get(c, "")))
                secs += max(0.0, dur - 2 * PAD)
            cond_vals[cond] = {"n": n_ok, "J95": float(np.percentile(J, 95)) if J else None, "J50": float(np.percentile(J, 50)) if J else None,
                               "R95": float(np.percentile(R, 95)) if R else None, "S95": float(np.percentile(S, 95)) if S else None,
                               "syl_rate": syl / secs if secs else None}
        rd, sp = cond_vals["read"], cond_vals["spont"]
        if rd["n"] < MIN_CLIPS or sp["n"] < MIN_CLIPS or not rd["J95"] or not sp["J95"]:
            per[s["spk"]] = {"half": s["half"], "excluded": "qc_clips", **{f"{k}_{c}": v for c, d in cond_vals.items() for k, v in d.items()}}
            continue
        ratio = lambda k: (rd[k] / sp[k]) if rd[k] and sp[k] else None
        per[s["spk"]] = {"half": s["half"], "person": s["person"], "n_read": rd["n"], "n_spont": sp["n"], "r_J95": ratio("J95"), "r_J50": ratio("J50"),
                         "r_R95": ratio("R95"), "r_S95": ratio("S95"), "r_syl_rate": ratio("syl_rate"), "J95_read": rd["J95"], "J95_spont": sp["J95"]}
    out = {"per_speaker": per}
    for h, name in ((0, "explore"), (1, "confirm"), (None, "both")):
        xs = [v for v in per.values() if "r_J95" in v and (h is None or v["half"] == h)]
        blk = {"n": len(xs)}
        for k in ("r_J95", "r_J50", "r_R95", "r_S95", "r_syl_rate"):
            logs = [math.log(v[k]) for v in xs if v.get(k)]
            if len(logs) >= 2:
                blk[k] = {"geomean": round(math.exp(float(np.mean(logs))), 4), "ci95": boot_ci(logs), "n": len(logs),
                          "n_above_1": sum(1 for x in logs if x > 0)}
        out[name] = blk
    c = out["confirm"]
    if c["n"] < MIN_HALF:
        verdict = {"result": "판정 불가", "reason": f"확인 절반 화자 {c['n']}명 < {MIN_HALF}명"}
    else:
        lo = c["r_J95"]["ci95"][0]
        verdict = {"result": "통과" if lo > 1.0 else "미달", "ci_low": lo, "geomean": c["r_J95"]["geomean"]}
    if "r_J95" in out["both"]:
        r = out["both"]["r_J95"]["geomean"]
        verdict["scaffold_ratio_r"] = r
        verdict["morph_scale_m"] = round(r ** (-1 / 3.3), 4)
    out["verdict"] = verdict
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("V7B_ANALYZE_OK", json.dumps(verdict, ensure_ascii=False))


def cmd_selftest(_a):
    assert SCRIPT_RE.search("spk407_lip_K_3_F_03_E214_A_007_12").groups() == ("E214", "A", "007")
    assert sh("가  나\n다") == sh("가 나 다")
    ci = boot_ci([math.log(1.2)] * 5 + [math.log(1.1)] * 5)
    assert 1.1 <= ci[0] <= ci[1] <= 1.2
    print("V7B_SELFTEST_OK")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("select"); s.add_argument("--root", required=True); s.add_argument("--pool", required=True)
    s.add_argument("--out", required=True); s.add_argument("--list", default="")
    s = sub.add_parser("analyze"); s.add_argument("--sel", required=True); s.add_argument("--bs", required=True); s.add_argument("--out", required=True)
    sub.add_parser("selftest")
    a = ap.parse_args()
    {"select": cmd_select, "analyze": cmd_analyze, "selftest": cmd_selftest}[a.cmd](a)


if __name__ == "__main__":
    main()
