"""V7b 전문가 화자 안 낭독 대 자유발화 진폭 비. 설계와 판정 기준은 docs/v7-clear-speech-2026-10.md 7.3절(측정 전에 커밋).

  plan    (맥) 전문가 라벨 tar 전체 요약 → 화자별 낭독·자유발화 대본(라벨만으로 정함, 7.4절)
  select  (맥) 받은 클립 → 계획한 대본의 클립 목록
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

READ_MIN = 0.10      # 낭독 대본: 다른 인물 라벨과 같은 문장 비율 ≥ 0.10(전문가는 대본을 조금씩 바꿔 읽어 비율이 낮다)
SPONT_MAX = 0.02     # 자유발화 대본: 같은 문장 비율 ≤ 0.02
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


def script_layout(full_path, pool, person_of):
    """전문가 배치 라벨 tar 전체 요약 → {spk: {대본: 같은 문장 비율}} (정면 A만)."""
    out = {}
    for l in open(full_path, encoding="utf-8"):
        r = json.loads(l)
        person = person_of.get(r["spk"])
        if not person:
            continue
        rows = {}
        for f in r["files"]:
            if f.get("person") != person or f.get("view") != "A":
                continue
            hs = f.get("texts_sha") or []
            rows[f["name"].rsplit("_", 1)[1]] = sum(1 for h in hs if pool.get(h, set()) - {person}) / max(1, len(hs))
        out[r["spk"]] = rows
    return out


def plan_conditions(rows):
    """대본별 비율 → (낭독 대본들, 자유발화 대본들, 가장 큰 대본 번호) 또는 None.
    낭독(≥ READ_MIN)과 자유발화(≤ SPONT_MAX)가 맞닿은 경계 가운데 필요한 대본 번호가 가장 작은 것을 고르고, 경계 양쪽에서 같은 종류가 이어지는
    대본을 최대 2개씩 쓴다(시간상 가까운 대본끼리 비교)."""
    sc = sorted(rows)
    kind = {k: ("R" if rows[k] >= READ_MIN else "S" if rows[k] <= SPONT_MAX else None) for k in sc}
    best = None
    for i in range(len(sc) - 1):
        a, b = sc[i], sc[i + 1]
        if kind[a] and kind[b] and kind[a] != kind[b] and int(b) == int(a) + 1:
            left = [a] + ([sc[i - 1]] if i >= 1 and kind[sc[i - 1]] == kind[a] and int(sc[i - 1]) == int(a) - 1 else [])
            right = [b] + ([sc[i + 2]] if i + 2 < len(sc) and kind[sc[i + 2]] == kind[b] and int(sc[i + 2]) == int(b) + 1 else [])
            mx = int(max(left + right))
            if best is None or mx < best[2]:
                R = sorted(left if kind[a] == "R" else right)
                S = sorted(right if kind[a] == "R" else left)
                best = (R, S, mx)
    return best


def cmd_plan(a):
    pool = load_pool(a.pool)
    for l in open(a.full, encoding="utf-8"):
        for f in json.loads(l)["files"]:
            for h in f.get("texts_sha") or []:
                pool.setdefault(h, set()).add(f.get("person"))
    person_of = {}
    for l in open(a.meta, encoding="utf-8"):
        p = l.rstrip("\n").split("\t")
        if not p[0].startswith("#") and len(p) > 2:
            person_of[p[0]] = p[2]
    lay = script_layout(a.full, pool, person_of)
    plan = {}
    for spk, rows in lay.items():
        b = plan_conditions(rows)
        plan[spk] = {"person": person_of[spk], "half": half_of(spk), "rows": {k: round(v, 3) for k, v in sorted(rows.items())},
                     "read": b[0] if b else None, "spont": b[1] if b else None, "max_script": b[2] if b else None}
        print(spk, person_of[spk], "half", half_of(spk), "read", plan[spk]["read"], "spont", plan[spk]["spont"], "max", plan[spk]["max_script"])
    json.dump(plan, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def cmd_select(a):
    pool = load_pool(a.pool)
    plan = json.load(open(a.plan, encoding="utf-8"))
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
        pl = plan.get(spk)
        if not person.startswith("E") or not pl or not pl["read"] or person != pl["person"]:
            continue
        cond = "read" if script in pl["read"] else "spont" if script in pl["spont"] else None
        if cond is None:
            continue
        hit = bool(pool.get(sh(text), set()) - {person})
        by.setdefault(spk, {"person": person, "read": [], "spont": [], "hits": {"read": 0, "spont": 0}})
        by[spk][cond].append(clip)
        by[spk]["hits"][cond] += hit
    speakers = []
    for spk, d in sorted(by.items()):
        ok = len(d["read"]) >= MIN_CLIPS and len(d["spont"]) >= MIN_CLIPS
        why = [] if ok else [w for w, bad in (("read_clips<20", len(d["read"]) < MIN_CLIPS), ("spont_clips<20", len(d["spont"]) < MIN_CLIPS)) if bad]
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
    b = plan_conditions({"001": 0.0, "002": 0.0, "003": 0.3, "004": 0.2, "005": 0.0})
    assert b == (["003", "004"], ["001", "002"], 4), b
    assert plan_conditions({"001": 0.0, "002": 0.0}) is None
    b = plan_conditions({"008": 0.12, "009": 0.02, "010": 0.12})
    assert b == (["008"], ["009"], 9), b
    assert SCRIPT_RE.search("spk407_lip_K_3_F_03_E214_A_007_12").groups() == ("E214", "A", "007")
    assert sh("가  나\n다") == sh("가 나 다")
    ci = boot_ci([math.log(1.2)] * 5 + [math.log(1.1)] * 5)
    assert 1.1 <= ci[0] <= ci[1] <= 1.2
    print("V7B_SELFTEST_OK")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("plan"); s.add_argument("--full", required=True); s.add_argument("--pool", required=True)
    s.add_argument("--meta", required=True); s.add_argument("--out", required=True)
    s = sub.add_parser("select"); s.add_argument("--root", required=True); s.add_argument("--pool", required=True); s.add_argument("--plan", required=True)
    s.add_argument("--out", required=True); s.add_argument("--list", default="")
    s = sub.add_parser("analyze"); s.add_argument("--sel", required=True); s.add_argument("--bs", required=True); s.add_argument("--out", required=True)
    sub.add_parser("selftest")
    a = ap.parse_args()
    {"plan": cmd_plan, "select": cmd_select, "analyze": cmd_analyze, "selftest": cmd_selftest}[a.cmd](a)


if __name__ == "__main__":
    main()
