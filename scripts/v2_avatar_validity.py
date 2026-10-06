"""V2 아바타 자극 타당성 감사 + V13 재표적 왕복 + V14 TTS→A4 기준선. 설계와 판정 기준은 docs/avatar-validity-2026-10.md
(측정 전에 커밋). 아바타 영상은 scripts/v2_render(앱 모듈을 그대로 쓰는 헤드리스 렌더 하네스)로 만들고, 실제 538 영상과 아바타
영상을 같은 MediaPipe 추출기(liplab-lab/tools/extract_blendshapes.py --lips --no-audio)로 잰다. 엔진 계수와 MediaPipe 추정치를
직접 비교하지 않는다.

  select  (맥) 538 정면 클립 고르기, 화자 절반, 아바타 문장 목록   → sel.json
  jobs    (맥) 엔진 프레임으로 텍스트 렌더 작업                       → jobs_text.json
  rawjobs (파드) 실제 MediaPipe 계수(V13)·A4 계수(V14)로 52계수 렌더 작업 → jobs_raw.json
  align   (파드) 실제 음성(·TTS 음성) CTC 정렬 → 엔진 프레임 시작 시각  → align.jsonl
  analyze (맥·파드) 모든 지표와 판정                                  → summary.json
  selftest   합성 자료로 분석 배관 점검
538 원자료와 클립별 파생 파일은 liplab-lab/data/ 아래에만 둔다. 이 저장소에는 집계 수치만 남긴다.
"""
import argparse
import asyncio
import hashlib
import json
import math
import os
import random
import re
import sys
import unicodedata
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
VIEW_RE = re.compile(r"_[CE]\d+_([A-Z])_\d+")
LAG_S = -0.066            # 실제 영상이 음성보다 앞서는 만큼(docs/coarticulation-e.md 6절에서 탐색 절반으로 고른 값, 다시 고르지 않음)
GROUPS = (1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13, 14)   # 엔진이 내는 입모양 무리(9·15는 엔진이 내지 않음)
RSA_FEATS = ("jawOpen", "mouthClose", "mouthFunnel", "mouthPucker", "smile", "stretch", "upperUp", "lowerDown", "press",
             "mouthRollLower", "mouthRollUpper", "mouthShrugLower", "mouthShrugUpper")
AMP_CH = ("J", "R", "S")  # 벌림 jawOpen, 돌출 funnel+pucker, 폭 (smileL+R+stretchL+R)/2
REPORT_CH = ("J", "R", "S", "C", "G")   # C mouthClose, G 안쪽 입술 간격/눈꼬리 거리
AMP_N_PASS = 11           # 13무리 중(종합 계획의 14무리 중 12개를 엔진이 내는 13무리에 맞춤, 허용 밖 2개는 같음)
MIN_SEG = 3
MIN_FACE_RATIO = 0.8
MIN_FRAMES = 15
P_LO, P_HI = 10, 90
V13_CH = ("jawOpen", "mouthClose", "R", "S")


def sid(text):
    return hashlib.sha1(unicodedata.normalize("NFC", text).strip().encode()).hexdigest()[:10]


def half_of(spk):
    return zlib.crc32(spk.encode()) % 2


# ───────────────────────────── select / jobs ─────────────────────────────
def cmd_select(a):
    v1_done = set(open(a.v1_done).read().split()) if a.v1_done else None
    meta = {}
    for root in a.root:
        mp = os.path.join(root, "manifest_meta.tsv")
        if os.path.exists(mp):
            for line in open(mp, encoding="utf-8"):
                p = line.rstrip("\n").split("\t")
                if p[0].startswith("#") or len(p) < 11:
                    continue
                meta[p[0]] = {"sex": p[3], "age": p[4], "noise": p[10], "person": p[2]}
    per, seen = {}, set()
    for root in a.root:
        is_v1 = os.path.basename(os.path.normpath(root)) == "v1_538"
        for line in open(os.path.join(root, "manifest.tsv"), encoding="utf-8"):
            p = line.rstrip("\n").split("\t")
            if len(p) < 3 or p[0].startswith("#"):
                continue
            clip, spk, text = os.path.splitext(p[0])[0], p[1], p[2]
            if is_v1 and v1_done is not None and spk not in v1_done:
                continue
            m = VIEW_RE.search(clip)
            if not m or m.group(1) != "A" or clip in seen:
                continue
            mp4 = next((x for x in (os.path.join(root, "clips", clip + ".mp4"), os.path.join(root, clip + ".mp4")) if os.path.exists(x)), None)
            if not mp4:
                continue
            seen.add(clip)
            per.setdefault(spk, []).append({"clip": clip, "spk": spk, "text": text, "mp4": mp4})
    rng = random.Random(0)
    clips, spk_rows = [], []
    for spk in sorted(per):
        rows = sorted(per[spk], key=lambda r: r["clip"])
        rng.shuffle(rows)
        rows = rows[:a.per_spk]
        h = half_of(spk)
        for k, r in enumerate(rows):
            r.update(half=h, rank=k, sid=sid(r["text"]))
            clips.append(r)
        spk_rows.append({"spk": spk, "half": h, "n": len(rows), **meta.get(spk, {})})
    # 아바타 문장: 화자마다 순서 앞 N_DEF개(기본 얼굴), 앞 N_TK개(가상 화자), V13은 앞 N_V13개 클립, V14는 확인 절반 화자의 첫 클립부터
    sent = {}
    for r in clips:
        key = (r["sid"], r["half"])
        e = sent.setdefault(key, {"sid": r["sid"], "half": r["half"], "text": r["text"], "default": False, "talkers": False})
        if r["rank"] < a.n_default:
            e["default"] = True
        if r["rank"] < a.n_talker:
            e["talkers"] = True
    v13 = [r["clip"] for r in clips if r["rank"] < a.n_v13]
    conf = [r for r in clips if r["half"] == 1]
    v14 = []
    for rank in range(a.per_spk):
        for r in sorted((x for x in conf if x["rank"] == rank), key=lambda x: x["spk"]):
            if len(v14) < a.n_v14 and r["sid"] not in {x["sid"] for x in v14}:
                v14.append({"clip": r["clip"], "sid": r["sid"], "text": r["text"], "spk": r["spk"]})
    out = {"created": a.stamp, "per_spk": a.per_spk, "speakers": spk_rows, "clips": clips,
           "sentences": sorted(sent.values(), key=lambda e: (e["half"], e["sid"])), "v13_clips": v13, "v14": v14,
           "params": {"n_default": a.n_default, "n_talker": a.n_talker, "n_v13": a.n_v13, "n_v14": a.n_v14}}
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    hs = [sum(1 for s in spk_rows if s["half"] == h) for h in (0, 1)]
    print(f"SELECT speakers={len(spk_rows)} (half0 {hs[0]}, half1 {hs[1]}) clips={len(clips)} "
          f"sentences default={sum(e['default'] for e in sent.values())} talkers={sum(e['talkers'] for e in sent.values())} "
          f"v13={len(v13)} v14={len(v14)}")


def cmd_jobs(a):
    sys.path.insert(0, os.path.abspath(a.backend))
    import engine
    sel = json.load(open(a.sel, encoding="utf-8"))
    jobs, frames_by = [], {}
    talkers = ("t1", "t2", "t3", "t4", "h1", "h2")
    for e in sel["sentences"]:
        if e["sid"] not in frames_by:
            text = unicodedata.normalize("NFC", e["text"]).strip()
            frames_by[e["sid"]] = asyncio.run(engine.text_to_visemes(text))
        fr = frames_by[e["sid"]]
        if e["default"]:
            for sp in a.default_speeds:
                jobs.append({"id": f"txt_{e['sid']}_default_{sp}", "kind": "text", "sid": e["sid"], "half": e["half"],
                             "talker": "default", "speed": sp, "frames": fr})
        if e["talkers"]:
            for t in talkers:
                for sp in a.talker_speeds:
                    jobs.append({"id": f"txt_{e['sid']}_{t}_{sp}", "kind": "text", "sid": e["sid"], "half": e["half"],
                                 "talker": t, "speed": sp, "frames": fr})
    # 같은 id는 한 번만(두 절반에 같은 문장이 있으면 영상은 하나, 분석에서 절반마다 쓴다)
    uniq = {}
    for j in jobs:
        uniq.setdefault(j["id"], j)
    jobs = list(uniq.values())
    # 우선순위: 기본 얼굴 1.0 → 2.0 → 가상 화자(렌더가 중간에 끊겨도 앞쪽 조건이 먼저 찬다)
    order = {("default", 1.0): 0, ("default", 2.0): 1}
    jobs.sort(key=lambda j: (order.get((j["talker"], j["speed"]), 2 if j["speed"] == 1.0 else 3), j["half"] == 0, j["id"]))
    json.dump(jobs, open(a.out, "w", encoding="utf-8"), ensure_ascii=False)
    n_ms = sum(sum(f["duration_ms"] for f in j["frames"]) / j["speed"] for j in jobs)
    print(f"JOBS text={len(jobs)} engine_seconds≈{n_ms / 1000:.0f}")


def bs_frames_indexed(d):
    """추출기 JSON → (names, [52값 또는 None]*n_read). 얼굴이 안 잡힌 프레임은 None."""
    fps = d.get("fps") or 30.0
    n = d.get("n_read") or (max((f["t_ms"] for f in d["frames"]), default=0) * fps / 1000 + 1)
    rows = [None] * int(round(n))
    for f in d["frames"]:
        i = int(round(f["t_ms"] * fps / 1000.0))
        if 0 <= i < len(rows):
            rows[i] = f["bs"]
    return d["bs_names"], rows, fps


def cmd_rawjobs(a):
    sel = json.load(open(a.sel, encoding="utf-8"))
    jobs = []
    if a.v13_bs:
        for clip in sel["v13_clips"]:
            p = os.path.join(a.v13_bs, clip + ".json")
            if not os.path.exists(p):
                continue
            d = json.load(open(p, encoding="utf-8"))
            names, rows, fps = bs_frames_indexed(d)
            if sum(r is not None for r in rows) < MIN_FRAMES:
                continue
            jobs.append({"id": f"v13_{clip}", "kind": "raw", "clip": clip, "names": names, "frames": rows, "fps": fps})
    if a.a4_dir:
        for fn in sorted(os.listdir(a.a4_dir)):
            if not fn.endswith(".json"):
                continue
            d = json.load(open(os.path.join(a.a4_dir, fn), encoding="utf-8"))
            tag = os.path.basename(os.path.normpath(a.a4_dir))          # a4_tts → a4_tts_<sid>
            jobs.append({"id": f"{tag}_{os.path.splitext(fn)[0]}", "kind": "raw", "names": d["names"], "frames": d["frames"],
                         "fps": d.get("fps", 30)})
    json.dump(jobs, open(a.out, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"RAWJOBS {len(jobs)}")


# ───────────────────────────── align (파드) ─────────────────────────────
def cmd_align(a):
    """실제 클립(과 TTS 음성)마다 엔진 프레임 시작 시각. coart_pod_eval의 정렬·배치 규칙을 그대로 쓴다."""
    sys.path.insert(0, HERE)
    sys.path.insert(0, os.path.abspath(a.backend))
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    import coart_pod_eval as C
    import engine
    import torch
    torch.set_num_threads(a.threads)
    aligner = a.aligner or os.path.join(os.path.abspath(a.backend), "models", "dgop_ours", "aligner")
    items = [json.loads(l) for l in open(a.items, encoding="utf-8")]
    done = set()
    if os.path.exists(a.out):
        done = {json.loads(l)["key"] for l in open(a.out, encoding="utf-8")}
    shard = [it for k, it in enumerate(items) if k % a.nshard == a.shard and it["key"] not in done]
    with open(a.out, "a", encoding="utf-8") as fo:
        for it in shard:
            try:
                ef = C.engine_frames(engine, it["text"])
                if ef is None:
                    raise ValueError("frame_roles")
                frames, roles, syls_idx, n_syl = ef
                wave = C.load_audio(it["audio"])
                syls = C.align_ctc(wave, unicodedata.normalize("NFC", it["text"]).strip(), aligner)
                if len(syls) != n_syl:
                    raise ValueError(f"syllables {len(syls)} vs {n_syl}")
                starts = C.frame_starts(frames, roles, syls_idx, syls)
                t_first = min(s["on"][0] if s["on"] else s["nu"][0] for s in syls)
                t_last = max((s["co"] or s["nu"])[1] for s in syls)
                row = {"key": it["key"], "visemes": [f["viseme"] for f in frames], "starts": starts,
                       "t_first": t_first, "t_last": t_last, "n_syl": n_syl, "dur": len(wave) / 16000.0,
                       "syl_on": [(s["on"] or s["nu"])[0] for s in syls]}
            except Exception as e:
                row = {"key": it["key"], "error": f"{type(e).__name__}: {e}"}
            fo.write(json.dumps(row, ensure_ascii=False) + "\n")
            fo.flush()
    print("ALIGN_SHARD_DONE", a.shard)


# ───────────────────────────── 분석 ─────────────────────────────
def load_series(path):
    """추출기 JSON → dict(t, 특징 배열들). 얼굴이 없는 프레임은 nan."""
    import numpy as np
    d = json.load(open(path, encoding="utf-8"))
    names, rows, fps = bs_frames_indexed(d)
    n = len(rows)
    ix = {k: i for i, k in enumerate(names)}
    W, H = (d.get("img_wh") or [640, 360])
    lm_by = {int(round(f["t_ms"] * fps / 1000.0)): f.get("lm") for f in d["frames"]}
    out = {"t": np.arange(n) / fps, "valid": np.array([r is not None for r in rows])}

    def col(k):
        return np.array([r[ix[k]] if r is not None else np.nan for r in rows], dtype=float)

    def avg(a_, b_):
        return (col(a_) + col(b_)) / 2

    f = {"jawOpen": col("jawOpen"), "mouthClose": col("mouthClose"), "mouthFunnel": col("mouthFunnel"),
         "mouthPucker": col("mouthPucker"), "smile": avg("mouthSmileLeft", "mouthSmileRight"),
         "stretch": avg("mouthStretchLeft", "mouthStretchRight"), "upperUp": avg("mouthUpperUpLeft", "mouthUpperUpRight"),
         "lowerDown": avg("mouthLowerDownLeft", "mouthLowerDownRight"), "press": avg("mouthPressLeft", "mouthPressRight"),
         "mouthRollLower": col("mouthRollLower"), "mouthRollUpper": col("mouthRollUpper"),
         "mouthShrugLower": col("mouthShrugLower"), "mouthShrugUpper": col("mouthShrugUpper")}
    f["J"] = f["jawOpen"]
    f["R"] = f["mouthFunnel"] + f["mouthPucker"]
    f["S"] = f["smile"] + f["stretch"]          # (smileL+smileR+stretchL+stretchR)/2
    f["C"] = f["mouthClose"]
    g = np.full(n, np.nan)
    for i in range(n):
        lm = lm_by.get(i)
        if lm and len(lm) >= 129:
            p = lambda k: (lm[3 * k] * W, lm[3 * k + 1] * H)
            u, l, ea, eb = p(35), p(25), p(40), p(41)     # 13(윗입술 안쪽 가운데), 14(아랫입술 안쪽 가운데), 33, 263
            iod = math.dist(ea, eb)
            if iod > 1e-6:
                g[i] = math.dist(u, l) / iod
    f["G"] = g
    out["f"] = f
    return out


def seg_value(ser, t0, t1):
    """구간 뒤쪽 절반 [t0 + 0.5(t1 − t0), t1]의 프레임 평균. 없으면 0.75 지점에서 50ms 안의 가장 가까운 프레임. 특징별 dict."""
    import numpy as np
    t, ok = ser["t"], ser["valid"]
    lo = t0 + 0.5 * (t1 - t0)
    m = ok & (t >= lo) & (t <= t1)
    if not m.any():
        c = t0 + 0.75 * (t1 - t0)
        cand = np.where(ok)[0]
        if not len(cand):
            return None
        k = cand[np.argmin(np.abs(t[cand] - c))]
        if abs(t[k] - c) > 0.05:
            return None
        m = np.zeros_like(ok)
        m[k] = True
    mm = ok & (t >= t0) & (t <= t1)
    out = {k: float(np.nanmean(v[m])) for k, v in ser["f"].items()}
    gseg = ser["f"]["G"][mm | m]
    out["Gmin"] = float(np.nanmin(gseg)) if np.isfinite(gseg).any() else float("nan")
    return out


def segments_from_align(row, lag):
    """정렬 결과 → [(무리, t0, t1)] 영상 시각(초). lag(음수 = 영상이 앞섬)를 더한다."""
    vis, st = row["visemes"], row["starts"]
    keep = [i for i, s in enumerate(st) if s is not None]
    segs = []
    for n_, i in enumerate(keep):
        t0 = st[i]
        t1 = st[keep[n_ + 1]] if n_ + 1 < len(keep) else row["t_last"]
        g = vis[i]
        if g in GROUPS and t1 > t0:
            segs.append((g, t0 + lag, t1 + lag))
    return segs, (row["t_first"] + lag, row["t_last"] + lag)


def segments_from_schedule(sch):
    segs = [(s["v"], s["t0"] / 1000.0, s["t1"] / 1000.0) for s in sch["schedule"] if s["v"] in GROUPS]
    return segs, (sch["speech"][0] / 1000.0, sch["speech"][1] / 1000.0)


def clip_record(ser, segs, span, qc=True):
    """클립 하나 → {segs: [(무리, 값 dict)], speech: 특징별 발화 구간 프레임 값} 또는 None(품질 미달)."""
    import numpy as np
    t, ok = ser["t"], ser["valid"]
    lo, hi = span
    m = (t >= lo - 0.15) & (t <= hi + 0.15)
    ratio = float(ok[m].mean()) if m.any() else 0.0
    if qc and (ratio < MIN_FACE_RATIO or int((ok & m).sum()) < MIN_FRAMES):
        return None, ratio
    sp = ok & (t >= lo) & (t <= hi)
    vals = []
    for g, t0, t1 in segs:
        v = seg_value(ser, t0, t1)
        if v is not None:
            vals.append((g, v))
    return {"segs": vals, "speech": {k: ser["f"][k][sp] for k in REPORT_CH + RSA_FEATS}, "dur": hi - lo}, ratio


def profile(records):
    """한 화자(또는 아바타 조건)의 클립 기록들 → 무리별 평균(RSA z 특징, 진폭), 바닥값."""
    import numpy as np
    segs = [(g, v) for r in records for g, v in r["segs"]]
    if not segs:
        return None
    X = np.array([[v[k] for k in RSA_FEATS] for _, v in segs], dtype=float)
    mu, sd = np.nanmean(X, axis=0), np.nanstd(X, axis=0)
    sd_ok = sd > 1e-4
    Z = np.where(sd_ok, (X - mu) / np.where(sd_ok, sd, 1), 0.0)
    floor = {c: float(np.nanpercentile(np.concatenate([r["speech"][c] for r in records]), 5)) for c in REPORT_CH}
    out = {"n": {}, "z": {}, "amp": {}, "seg_amp": {}, "floor": floor, "flat_feats": [RSA_FEATS[i] for i in range(len(RSA_FEATS)) if not sd_ok[i]]}
    for g in GROUPS:
        idx = [i for i, (gg, _) in enumerate(segs) if gg == g]
        out["n"][g] = len(idx)
        if len(idx) >= MIN_SEG:
            out["z"][g] = np.nanmean(Z[idx], axis=0)
            out["amp"][g] = {c: float(np.nanmean([segs[i][1][c] for i in idx])) - floor[c] for c in REPORT_CH}
            out["amp"][g]["A"] = float(math.sqrt(sum(max(0.0, out["amp"][g][c]) ** 2 for c in AMP_CH)))
            out["seg_amp"][g] = {c: [segs[i][1][c] - floor[c] for i in idx] for c in ("J", "R", "S")}
            out["seg_amp"][g]["Gmin"] = [segs[i][1]["Gmin"] for i in idx]
    return out


def dist_vec(p):
    import numpy as np
    gs = [g for g in GROUPS]
    if any(g not in p["z"] for g in gs):
        return None
    V = np.array([p["z"][g] for g in gs])
    D = np.sqrt(((V[:, None, :] - V[None, :, :]) ** 2).sum(-1))
    iu = np.triu_indices(len(gs), 1)
    return D[iu]


def spearman(a, b):
    import numpy as np
    from scipy.stats import spearmanr
    m = np.isfinite(a) & np.isfinite(b)
    return float(spearmanr(a[m], b[m]).correlation)


def pct_rank(vals, x):
    import numpy as np
    v = np.sort(np.asarray(vals, dtype=float))
    return float(np.searchsorted(v, x, side="right") / len(v) * 100)


def rsa_block(real_profiles, cond_profiles):
    """real_profiles: {spk: profile}. cond_profiles: {조건: profile}. LOO 분포, 아바타 ρ, 판정."""
    import numpy as np
    dv = {s: dist_vec(p) for s, p in real_profiles.items()}
    dv = {s: v for s, v in dv.items() if v is not None}
    spks = sorted(dv)
    M = np.array([dv[s] for s in spks])
    loo = {}
    for k, s in enumerate(spks):
        ref = np.delete(M, k, axis=0).mean(0)
        loo[s] = spearman(M[k], ref)
    lv = np.array(list(loo.values()))
    p10 = float(np.percentile(lv, P_LO))
    ref_all = M.mean(0)
    res = {"n_real": len(spks), "excluded_real": sorted(set(real_profiles) - set(spks)),
           "loo": {"p10": round(p10, 4), "median": round(float(np.median(lv)), 4), "min": round(float(lv.min()), 4),
                   "max": round(float(lv.max()), 4)}, "cond": {}}
    for c, p in cond_profiles.items():
        v = dist_vec(p) if p else None
        if v is None:
            res["cond"][c] = {"rho": None, "missing_groups": [g for g in GROUPS if not p or g not in p["z"]]}
            continue
        rho = spearman(v, ref_all)
        loo_mean = float(np.mean([spearman(v, np.delete(M, k, axis=0).mean(0)) for k in range(len(spks))]))
        res["cond"][c] = {"rho": round(rho, 4), "rho_vs_loo_refs_mean": round(loo_mean, 4), "pct_in_loo": round(pct_rank(lv, rho), 1),
                          "pass": bool(rho >= p10), "flat_feats": p.get("flat_feats", [])}
    return res


def _ranges(profiles, g, c):
    import numpy as np
    vals = [p["amp"][g][c] for p in profiles if p and g in p["amp"] and np.isfinite(p["amp"][g][c])]
    if len(vals) < 5:
        return None
    return {"p10": float(np.percentile(vals, P_LO)), "p50": float(np.percentile(vals, 50)), "p90": float(np.percentile(vals, P_HI)),
            "n": len(vals), "_vals": vals}


def _amp_rows(ranges, p):
    """조건 하나의 무리별 범위 판정. 주 판정은 스칼라 진폭 A(벌림·돌출·폭 바닥값 뺀 값의 크기), 채널별은 보고."""
    import numpy as np
    rows, n_in = {}, 0
    for g in GROUPS:
        if not p or g not in p["amp"]:
            rows[g] = {"missing": True}
            continue
        r = {}
        for c in ("A",) + REPORT_CH:
            rg = ranges[g].get(c)
            x = p["amp"][g][c]
            if rg is None or not np.isfinite(x):
                r[c] = None
                continue
            r[c] = {"x": round(x, 4), "pct": round(pct_rank(rg["_vals"], x), 1), "in": bool(rg["p10"] <= x <= rg["p90"])}
        r["in"] = bool(r.get("A") and r["A"]["in"])
        r["in_all3"] = all(isinstance(r.get(c), dict) and r[c]["in"] for c in AMP_CH)
        n_in += r["in"]
        rows[g] = r
    return rows, n_in


def amp_block(real_profiles, cond_profiles):
    import numpy as np
    profs = list(real_profiles.values())
    ranges = {g: {c: _ranges(profs, g, c) for c in ("A",) + REPORT_CH} for g in GROUPS}
    out = {"ranges": {g: {c: ({k: (round(v, 4) if isinstance(v, float) else v) for k, v in rg.items() if k != "_vals"} if rg else None)
                          for c, rg in ranges[g].items()} for g in GROUPS}, "cond": {}}
    for name, p in cond_profiles.items():
        rows, n_in = _amp_rows(ranges, p)
        out["cond"][name] = {"groups": rows, "n_in": n_in, "n_groups": len(GROUPS), "pass": bool(n_in >= AMP_N_PASS),
                             "n_in_all3": sum(1 for g in GROUPS if rows[g].get("in_all3")),
                             "per_channel_in": {c: sum(1 for g in GROUPS if isinstance(rows[g].get(c), dict) and rows[g][c]["in"])
                                                for c in ("A",) + REPORT_CH}}
    # 보정 정보(판정에 쓰지 않음): 실제 화자 한 명을 빼고 나머지로 범위를 잡았을 때 그 화자가 같은 기준을 넘는 비율
    keys = [k for k, p in real_profiles.items() if p]
    cnt = []
    for k in keys:
        others = [real_profiles[o] for o in keys if o != k]
        rg = {g: {c: _ranges(others, g, c) for c in ("A",) + REPORT_CH} for g in GROUPS}
        rows, n_in = _amp_rows(rg, real_profiles[k])
        if all(not rows[g].get("missing") for g in GROUPS):
            cnt.append(n_in)
    if cnt:
        out["human_loo"] = {"n": len(cnt), "median_n_in": float(np.median(cnt)), "pass_rate": round(float(np.mean([c >= AMP_N_PASS for c in cnt])), 3),
                            "p10_n_in": float(np.percentile(cnt, 10))}
    return out


def legibility(real_profiles, p):
    """나1 핵심 자세(보고만): ㅁㅂㅍ 입술 닫힘 달성률, 원순 모음 돌출 사람 범위 비율, ㅏ 턱 벌림 백분위."""
    import numpy as np
    out = {}
    rb = [x for q in real_profiles.values() if q and 1 in q["seg_amp"] for x in q["seg_amp"][1]["Gmin"] if np.isfinite(x)]
    rr = [x for q in real_profiles.values() if q and 4 in q["seg_amp"] for x in q["seg_amp"][4]["R"] if np.isfinite(x)]
    rj = [q["amp"][2]["J"] for q in real_profiles.values() if q and 2 in q["amp"]]
    if p and 1 in p["seg_amp"] and rb:
        thr = float(np.percentile(rb, 90))
        g = [x for x in p["seg_amp"][1]["Gmin"] if np.isfinite(x)]
        out["bilabial_closure_rate"] = round(float(np.mean([x <= thr for x in g])), 3) if g else None
        out["bilabial_gap_p90_real"] = round(thr, 4)
    if p and 4 in p["seg_amp"] and rr:
        lo, hi = np.percentile(rr, [P_LO, P_HI])
        r = [x for x in p["seg_amp"][4]["R"] if np.isfinite(x)]
        out["rounded_R_in_range_rate"] = round(float(np.mean([(lo <= x <= hi) for x in r])), 3) if r else None
    if p and 2 in p["amp"] and rj:
        out["open_a_J_pct"] = round(pct_rank(rj, p["amp"][2]["J"]), 1)
    return out


def cmd_analyze(a):
    import numpy as np
    sel = json.load(open(a.sel, encoding="utf-8"))
    align = {}
    for path in a.align:
        for l in open(path, encoding="utf-8"):
            r = json.loads(l)
            align[r["key"]] = r
    half_of_spk = {s["spk"]: s["half"] for s in sel["speakers"]}
    noise_of = {s["spk"]: s.get("noise") for s in sel["speakers"]}
    summary = {"lag_s": LAG_S, "groups": list(GROUPS), "qc": {}}
    # 실제 화자
    real_rec, qc = {}, {"clips": 0, "no_bs": 0, "align_err": 0, "face_qc": 0, "ok": 0}
    syl_rate = {}
    for c in sel["clips"]:
        qc["clips"] += 1
        bp = os.path.join(a.real_bs, c["clip"] + ".json")
        r = align.get("real:" + c["clip"])
        if not os.path.exists(bp):
            qc["no_bs"] += 1
            continue
        if r is None or "error" in r:
            qc["align_err"] += 1
            continue
        ser = load_series(bp)
        segs, span = segments_from_align(r, LAG_S)
        rec, ratio = clip_record(ser, segs, span)
        if rec is None:
            qc["face_qc"] += 1
            continue
        qc["ok"] += 1
        real_rec.setdefault(c["spk"], []).append(rec)
        syl_rate.setdefault(c["spk"], []).append(r["n_syl"] / max(1e-3, r["t_last"] - r["t_first"]))
    summary["qc"]["real"] = qc
    # 아바타 렌더
    cond_rec, rqc = {}, {}
    sid_half = {}
    for e in sel["sentences"]:
        sid_half.setdefault(e["sid"], set()).add(e["half"])
    for fn in sorted(os.listdir(a.renders)) if a.renders else []:
        if not fn.endswith(".sched.json"):
            continue
        jid = fn[:-len(".sched.json")]
        bp = os.path.join(a.render_bs, jid + ".json")
        q = rqc.setdefault(jid.split("_", 2)[2] if jid.startswith("txt_") else "other", {"jobs": 0, "no_bs": 0, "face_qc": 0, "ok": 0, "face_ratio": []})
        q["jobs"] += 1
        if not jid.startswith("txt_"):
            continue
        if not os.path.exists(bp):
            q["no_bs"] += 1
            continue
        sch = json.load(open(os.path.join(a.renders, fn), encoding="utf-8"))
        _, s_id, cond = jid.split("_", 2)
        ser = load_series(bp)
        segs, span = segments_from_schedule(sch)
        rec, ratio = clip_record(ser, segs, span)
        q["face_ratio"].append(ratio)
        if rec is None:
            q["face_qc"] += 1
            continue
        q["ok"] += 1
        n_syl = len({s.get("i") for s in sch["schedule"]})  # 보고용 아님
        for h in sid_half.get(s_id, ()):
            cond_rec.setdefault((h, cond), []).append(rec)
    for k, q in rqc.items():
        fr = q.pop("face_ratio")
        q["face_ratio_median"] = round(float(np.median(fr)), 3) if fr else None
    summary["qc"]["renders"] = rqc
    # 절반별 지표
    for h, name in ((0, "explore"), (1, "confirm")):
        rp = {s: profile(v) for s, v in real_rec.items() if half_of_spk.get(s) == h}
        cp = {cond: profile(v) for (hh, cond), v in cond_rec.items() if hh == h}
        cp_n = {cond: len(v) for (hh, cond), v in cond_rec.items() if hh == h}
        blk = {"n_real_speakers": len(rp), "n_render_clips": cp_n,
               "real_seg_counts_median": {g: float(np.median([p["n"][g] for p in rp.values() if p])) for g in GROUPS}}
        blk["rsa"] = rsa_block(rp, cp)
        blk["amp"] = amp_block(rp, cp)
        blk["legibility"] = {c: legibility(rp, p) for c, p in cp.items()}
        rates = [float(np.median(v)) for s, v in syl_rate.items() if half_of_spk.get(s) == h]
        blk["real_syl_rate"] = {"p10": round(float(np.percentile(rates, 10)), 2), "p50": round(float(np.median(rates)), 2),
                                "p90": round(float(np.percentile(rates, 90)), 2)} if rates else None
        # 가7(보고만): 소음 라벨별 화자 J 진폭(무리 2·3·4·5 평균), 화자 사이 비교
        bynoise = {}
        for s, p in rp.items():
            if p and all(g in p["amp"] for g in (2, 3, 4, 5)):
                bynoise.setdefault(noise_of.get(s) or "?", []).append(float(np.mean([p["amp"][g]["J"] for g in (2, 3, 4, 5)])))
        blk["noise_J"] = {k: {"n": len(v), "median": round(float(np.median(v)), 4)} for k, v in sorted(bynoise.items())}
        summary[name] = blk
    # V13
    if a.v13_bs and a.real_bs:
        summary["v13"] = v13_block(sel, a)
    # V14
    if a.v14:
        summary["v14"] = v14_block(sel, a, align, real_rec, half_of_spk)
    json.dump(summary, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=lambda o: float(o) if hasattr(o, "__float__") else str(o))
    print("ANALYZE_OK", a.out)


def v13_block(sel, a):
    import numpy as np
    per = {c: [] for c in V13_CH}
    gain = {c: [] for c in V13_CH}
    lagbest = {c: [] for c in V13_CH}
    n = 0
    for clip in sel["v13_clips"]:
        po, pr = os.path.join(a.real_bs, clip + ".json"), os.path.join(a.v13_bs, f"v13_{clip}.json")
        if not (os.path.exists(po) and os.path.exists(pr)):
            continue
        so, sr = load_series(po), load_series(pr)
        L = min(len(so["t"]), len(sr["t"]))
        n += 1
        for c in V13_CH:
            x, y = so["f"][c][:L], sr["f"][c][:L]
            m = np.isfinite(x) & np.isfinite(y)
            if m.sum() < MIN_FRAMES or np.std(x[m]) < 1e-6 or np.std(y[m]) < 1e-6:
                continue
            per[c].append(float(np.corrcoef(x[m], y[m])[0, 1]))
            gain[c].append(float(np.polyfit(x[m], y[m], 1)[0]))
            best = []
            for lag in range(-3, 4):
                xs, ys = (x[:L - lag], y[lag:]) if lag >= 0 else (x[-lag:], y[:L + lag])
                mm = np.isfinite(xs) & np.isfinite(ys)
                best.append(float(np.corrcoef(xs[mm], ys[mm])[0, 1]) if mm.sum() >= MIN_FRAMES else -1)
            lagbest[c].append(int(np.argmax(best)) - 3)
    out = {"clips": n, "channels": {}}
    for c in V13_CH:
        if per[c]:
            out["channels"][c] = {"n": len(per[c]), "median_r": round(float(np.median(per[c])), 3),
                                  "q25": round(float(np.percentile(per[c], 25)), 3), "q75": round(float(np.percentile(per[c], 75)), 3),
                                  "median_gain": round(float(np.median(gain[c])), 3),
                                  "median_best_lag_frames": float(np.median(lagbest[c])), "rig_limit": bool(np.median(per[c]) < 0.80)}
    return out


def v14_block(sel, a, align, real_rec, half_of_spk):
    """TTS 영역 점검(A4 실제 음성 대 TTS 음성 jawOpen, 음절 시각으로 맞춤)과 TTS→A4 렌더의 V2 지표."""
    import numpy as np
    out = {"domain": {}, "render": {}}
    rs = []
    for it in sel["v14"]:
        ar = align.get("real:" + it["clip"])
        at = align.get("tts:" + it["sid"])
        pa, pt = os.path.join(a.v14, "a4_real", it["clip"] + ".json"), os.path.join(a.v14, "a4_tts", it["sid"] + ".json")
        if not (ar and at and "error" not in ar and "error" not in at and os.path.exists(pa) and os.path.exists(pt)):
            continue
        A, T = json.load(open(pa)), json.load(open(pt))
        ja = np.array([f[A["names"].index("jawOpen")] for f in A["frames"]])
        jt = np.array([f[T["names"].index("jawOpen")] for f in T["frames"]])
        xa, xt = np.array(ar["syl_on"] + [ar["t_last"]]), np.array(at["syl_on"] + [at["t_last"]])
        if len(xa) != len(xt) or np.any(np.diff(xt) <= 0) or np.any(np.diff(xa) <= 0):
            continue
        ta = np.arange(len(ja)) / 30.0
        m = (ta >= xa[0]) & (ta <= xa[-1])
        tt = np.interp(ta[m], xa, xt)          # 실제 시각 → TTS 시각(음절 시작점을 잇는 조각 선형)
        jt_w = np.interp(tt, np.arange(len(jt)) / 30.0, jt)
        if m.sum() >= MIN_FRAMES and np.std(ja[m]) > 1e-6 and np.std(jt_w) > 1e-6:
            rs.append(float(np.corrcoef(ja[m], jt_w)[0, 1]))
    out["domain"] = {"n": len(rs), "median_r_jaw": round(float(np.median(rs)), 3) if rs else None,
                     "pass_0.5": bool(rs and np.median(rs) >= 0.5)}
    # TTS→A4 렌더: TTS 정렬로 무리 구간(실제와 같은 지연), 확인 화자 실제 분포와 비교
    recs = []
    for it in sel["v14"]:
        at = align.get("tts:" + it["sid"])
        bp = os.path.join(a.render_bs, f"a4_tts_{it['sid']}.json")
        if not at or "error" in at or not os.path.exists(bp):
            continue
        ser = load_series(bp)
        segs, span = segments_from_align(at, LAG_S)
        rec, _ = clip_record(ser, segs, span)
        if rec:
            recs.append((it["sid"], rec))
    rp = {s: profile(v) for s, v in real_rec.items() if half_of_spk.get(s) == 1}
    sids = {s for s, _ in recs}
    cp = {"tts_a4": profile([r for _, r in recs])}
    # 같은 문장의 규칙 엔진 렌더(기본 얼굴 1.0·2.0)
    for sp in ("1.0", "2.0"):
        rr = []
        for s_ in sids:
            bp = os.path.join(a.render_bs, f"txt_{s_}_default_{sp}.json")
            sp_ = os.path.join(a.renders, f"txt_{s_}_default_{sp}.sched.json")
            if os.path.exists(bp) and os.path.exists(sp_):
                segs, span = segments_from_schedule(json.load(open(sp_)))
                rec, _ = clip_record(load_series(bp), segs, span)
                if rec:
                    rr.append(rec)
        cp[f"rule_{sp}"] = profile(rr) if rr else None
    out["render"] = {"n_sentences": len(recs), "rsa": rsa_block(rp, cp), "amp": amp_block(rp, cp),
                     "legibility": {c: legibility(rp, p) for c, p in cp.items()}}
    return out


# ───────────────────────────── selftest ─────────────────────────────
def cmd_selftest(_a):
    import numpy as np
    rng = np.random.default_rng(0)
    base = {g: rng.normal(0, 1, len(RSA_FEATS)) for g in GROUPS}
    amp = {g: {c: abs(rng.normal(0.2, 0.05)) for c in REPORT_CH} for g in GROUPS}

    def fake(scale, noise):
        p = {"z": {}, "amp": {}, "seg_amp": {}, "n": {}, "flat_feats": []}
        for g in GROUPS:
            p["z"][g] = base[g] + rng.normal(0, noise, len(RSA_FEATS))
            p["amp"][g] = {c: amp[g][c] * scale * (1 + rng.normal(0, 0.1)) for c in REPORT_CH}
            p["amp"][g]["A"] = math.sqrt(sum(p["amp"][g][c] ** 2 for c in AMP_CH))
            p["seg_amp"][g] = {"J": [0.1] * 5, "R": [0.1] * 5, "S": [0.1] * 5, "Gmin": [0.05] * 5}
        return p
    real = {f"s{i}": fake(1.0, 0.5) for i in range(30)}
    good = fake(1.0, 0.5)
    for g in GROUPS:
        good["amp"][g] = {c: float(np.median([q["amp"][g][c] for q in real.values()])) for c in REPORT_CH + ("A",)}
    bad = {"z": {g: rng.normal(0, 1, len(RSA_FEATS)) for g in GROUPS}, "amp": {g: {c: 0.0 for c in REPORT_CH + ("A",)} for g in GROUPS},
                                  "seg_amp": {}, "n": {}, "flat_feats": []}
    r = rsa_block(real, {"good": good, "bad": bad})
    am = amp_block(real, {"good": good, "bad": bad})
    ok = r["cond"]["good"]["pass"] and not r["cond"]["bad"]["pass"] and am["cond"]["good"]["n_in"] >= AMP_N_PASS and am["cond"]["bad"]["n_in"] <= 2
    print("rsa", r["loo"], r["cond"]["good"]["rho"], r["cond"]["bad"]["rho"], "amp", am["cond"]["good"]["n_in"], am["cond"]["bad"]["n_in"],
          "human_loo", am.get("human_loo"))
    print("V2_SELFTEST_OK" if ok else "V2_SELFTEST_FAIL")
    return ok


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("select")
    s.add_argument("--root", action="append", required=True)
    s.add_argument("--v1-done")
    s.add_argument("--per-spk", type=int, default=12)
    s.add_argument("--n-default", type=int, default=4)
    s.add_argument("--n-talker", type=int, default=2)
    s.add_argument("--n-v13", type=int, default=2)
    s.add_argument("--n-v14", type=int, default=50)
    s.add_argument("--stamp", default="")
    s.add_argument("--out", required=True)
    s = sub.add_parser("jobs")
    s.add_argument("--sel", required=True)
    s.add_argument("--backend", default=os.path.join(HERE, "..", "backend"))
    s.add_argument("--default-speeds", type=float, nargs="+", default=[1.0, 2.0])
    s.add_argument("--talker-speeds", type=float, nargs="+", default=[1.0])
    s.add_argument("--out", required=True)
    s = sub.add_parser("rawjobs")
    s.add_argument("--sel", required=True)
    s.add_argument("--v13-bs")
    s.add_argument("--a4-dir")
    s.add_argument("--out", required=True)
    s = sub.add_parser("align")
    s.add_argument("--items", required=True, help="jsonl: {key, text, audio}")
    s.add_argument("--backend", default=os.path.join(HERE, "..", "backend"))
    s.add_argument("--aligner")
    s.add_argument("--shard", type=int, default=0)
    s.add_argument("--nshard", type=int, default=1)
    s.add_argument("--threads", type=int, default=2)
    s.add_argument("--out", required=True)
    s = sub.add_parser("analyze")
    s.add_argument("--sel", required=True)
    s.add_argument("--align", action="append", required=True)
    s.add_argument("--real-bs", required=True)
    s.add_argument("--renders", help="렌더 .sched.json 폴더")
    s.add_argument("--render-bs", help="렌더 영상의 추출 JSON 폴더")
    s.add_argument("--v13-bs", help="V13 렌더의 추출 JSON 폴더")
    s.add_argument("--v14", help="V14 A4 출력 폴더(a4_real/, a4_tts/)")
    s.add_argument("--out", required=True)
    sub.add_parser("selftest")
    a = ap.parse_args()
    {"select": cmd_select, "jobs": cmd_jobs, "rawjobs": cmd_rawjobs, "align": cmd_align, "analyze": cmd_analyze,
     "selftest": cmd_selftest}[a.cmd](a)


if __name__ == "__main__":
    main()
