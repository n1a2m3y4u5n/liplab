"""V18 입술 돌출 기준(538 비정면 시점). 설계와 판정 기준은 docs/lip-protrusion-v18-2026-10.md(측정 전에 커밋).

돌출 P: MediaPipe 얼굴 랜드마크(extract_blendshapes.py --lips가 남긴 43점 xyz와 얼굴 변환행렬 fx)로, 머리 자세를 되돌린 얼굴 좌표계에서
바깥 입술 가운데 6점(0, 17, 37, 267, 84, 314)이 눈꼬리 두 점(33, 263)의 가운데보다 얼마나 앞(얼굴 정면 방향)에 있는지를 눈꼬리 거리로
나눈 값이다. 정면 영상에서는 깊이를 MediaPipe가 추정만 하고, 비정면 영상에서는 같은 깊이가 화면 위 위치 차이로 드러난다. 같은 계산을
정면·비정면, 실제·아바타에 똑같이 쓴다. 엔진 계수와 MediaPipe 추정치를 직접 비교하지 않는 V2 원칙은 그대로다.

  angles  (맥) 추출 JSON 폴더들 → 시점(파일 이름의 시점 글자)별 머리 방향(yaw·pitch) 중앙값
  items   (맥) 비정면 클립 → 정렬 작업(items_side.jsonl)과 화자 절반 표(side_sel.json)
  jobs    (맥) V2 기본 얼굴 문장 작업에서 비정면 렌더 작업(지금 표, V15 표)
  analyze (맥) 모든 지표와 판정 → summary.json
  selftest   합성 자료로 P 계산·AUC·순위 배관 점검
538 원자료와 클립별 파생 파일은 liplab-lab/data/ 아래에만 둔다. 이 저장소에는 집계 수치만 남긴다.
"""
import argparse
import json
import math
import os
import re
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import v2_avatar_validity as V  # noqa: E402  (구간 규칙·특징·품질 기준을 그대로 쓴다)

# extract_blendshapes.py --lips의 lm_idx(43점) 안에서의 위치
LM_IDX = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185,
          78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308, 415, 310, 311, 312, 13, 82, 81, 80, 191, 33, 263, 1]
POS = {k: i for i, k in enumerate(LM_IDX)}
LIP_SETS = {"P6": (0, 17, 37, 267, 84, 314), "Pup": (0, 37, 267), "Pcorner": (61, 291), "P8": (0, 17, 37, 267, 84, 314, 61, 291)}
LIP_MID = [POS[k] for k in LIP_SETS["P6"]]


def set_lip(name):
    """입술 점 후보를 고른다(사전 등록 5.1절: 탐색 절반에서 하나를 골라 동결)."""
    global LIP_MID
    LIP_MID = [POS[k] for k in LIP_SETS[name]]
EYE_A, EYE_B = POS[33], POS[263]
ROUNDED = (4,)              # ㅗ ㅛ ㅜ ㅠ
UNROUNDED = (2, 3, 5)       # ㅏ ㅐ ㅑ ㅒ / ㅣ ㅔ ㅖ / ㅓ ㅕ ㅡ
AUC_PASS = 0.85
AUC_MARGIN = 0.05
RHO_PASS = 0.6
VIEW_RE = re.compile(r"_[CE]\d+_([A-Z])_\d+")


def half_of(spk):
    return zlib.crc32(spk.encode()) % 2


def _rot(fx):
    """fx(16값, 행 우선 4×4) → 3×3 회전(SVD로 직교화). 얼굴 좌표계 → 카메라 좌표계(OpenGL: x 오른쪽, y 위, z 카메라 쪽)."""
    import numpy as np
    M = np.array(fx, dtype=float).reshape(4, 4)[:3, :3]
    u, _, vt = np.linalg.svd(M)
    R = u @ vt
    if np.linalg.det(R) < 0:
        u[:, -1] *= -1
        R = u @ vt
    return R


def frame_pts(lm, W, H):
    """lm(129값) → 43×3 카메라 좌표(x·W, −y·H, −z·W). MediaPipe z는 작을수록 카메라에 가깝고 x와 같은 척도다."""
    import numpy as np
    a = np.array(lm, dtype=float).reshape(-1, 3)
    return np.stack([a[:, 0] * W, -a[:, 1] * H, -a[:, 2] * W], axis=1)


def protrusion(lm, fx, W, H):
    """한 프레임의 돌출 P와 머리 방향(yaw, pitch, 도). 계산할 수 없으면 None."""
    import numpy as np
    if not lm or len(lm) < 129 or not fx or len(fx) != 16:
        return None
    p = frame_pts(lm, W, H)
    R = _rot(fx)
    ref = (p[EYE_A] + p[EYE_B]) / 2
    iod = float(np.linalg.norm(p[EYE_A] - p[EYE_B]))
    if iod < 1e-6:
        return None
    c = (p - ref) @ R          # 행벡터 표기: (R^T (p − ref))^T
    P = float(c[LIP_MID, 2].mean() / iod)
    f = R @ np.array([0.0, 0.0, 1.0])     # 얼굴 정면 방향(카메라 좌표)
    yaw = math.degrees(math.atan2(f[0], f[2]))
    pitch = math.degrees(math.atan2(f[1], math.hypot(f[0], f[2])))
    return P, yaw, pitch


def load_series_p(path):
    """V2 load_series에 P(돌출)를 더한다. 머리 방향은 프레임별 배열로 함께 돌려준다."""
    import numpy as np
    ser = V.load_series(path)
    d = json.load(open(path, encoding="utf-8"))
    fps = d.get("fps") or 30.0
    W, H = (d.get("img_wh") or [640, 360])
    n = len(ser["t"])
    P = np.full(n, np.nan)
    yaw = np.full(n, np.nan)
    pitch = np.full(n, np.nan)
    for fr in d["frames"]:
        i = int(round(fr["t_ms"] * fps / 1000.0))
        if 0 <= i < n:
            r = protrusion(fr.get("lm"), fr.get("fx"), W, H)
            if r:
                P[i], yaw[i], pitch[i] = r
    ser["f"]["P"] = P
    ser["valid"] = ser["valid"] & np.isfinite(P)
    ser["yaw"], ser["pitch"] = yaw, pitch
    return ser


def clip_rec(ser, segs, span):
    """클립 하나 → {segs: [(무리, {P, R, ...})], speechP: 발화 구간 P, angle: (yaw, pitch) 중앙값} 또는 None(V2 품질 기준)."""
    import numpy as np
    rec, ratio = V.clip_record(ser, segs, span)
    if rec is None:
        return None
    t, ok = ser["t"], ser["valid"]
    sp = ok & (t >= span[0]) & (t <= span[1])
    rec["speechP"] = ser["f"]["P"][sp]
    rec["speechR"] = ser["f"]["R"][sp]
    rec["angle"] = (float(np.nanmedian(ser["yaw"][sp])), float(np.nanmedian(ser["pitch"][sp])))
    return rec


def auc(pos, neg):
    """Mann–Whitney AUC(같은 값은 0.5)."""
    import numpy as np
    pos = np.asarray([x for x in pos if np.isfinite(x)], dtype=float)
    neg = np.asarray([x for x in neg if np.isfinite(x)], dtype=float)
    if len(pos) < V.MIN_SEG or len(neg) < V.MIN_SEG:
        return None
    from scipy.stats import rankdata
    r = rankdata(np.concatenate([pos, neg]))
    return float((r[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def speaker_auc(records, ch):
    pos = [v[ch] for r in records for g, v in r["segs"] if g in ROUNDED]
    neg = [v[ch] for r in records for g, v in r["segs"] if g in UNROUNDED]
    return auc(pos, neg)


def group_profile(records, ch="P"):
    """무리별 평균(발화 구간 중앙값을 뺀 값). 무리 구간이 MIN_SEG개 미만이면 뺀다."""
    import numpy as np
    base = float(np.nanmedian(np.concatenate([r["speech" + ch] for r in records]))) if records else float("nan")
    out = {}
    for g in V.GROUPS:
        vals = [v[ch] - base for r in records for gg, v in r["segs"] if gg == g and np.isfinite(v[ch])]
        if len(vals) >= V.MIN_SEG:
            out[g] = float(np.mean(vals))
    return out


def mean_profile(profiles):
    """화자 프로필들의 무리별 평균(절반 이상의 화자에게 있는 무리만)."""
    import numpy as np
    ps = list(profiles)
    return {g: float(np.mean([p[g] for p in ps if g in p])) for g in V.GROUPS
            if ps and sum(1 for p in ps if g in p) >= max(1, (len(ps) + 1) // 2)}


def loo_rho(prof):
    import numpy as np
    out = []
    for s, p in prof.items():
        ref = mean_profile([q for o, q in prof.items() if o != s])
        rho, _ = spearman_profiles(p, ref)
        if rho is not None:
            out.append(rho)
    return {"n": len(out), "median": round(float(np.median(out)), 3) if out else None, "p10": round(float(np.percentile(out, 10)), 3) if out else None}


def boot_mean(vals, n=4000, seed=0):
    import numpy as np
    v = np.asarray([x for x in vals if x is not None], dtype=float)
    if len(v) < 2:
        return None
    rng = np.random.default_rng(seed)
    bs = rng.choice(v, size=(n, len(v)), replace=True).mean(1)
    return [round(float(np.percentile(bs, 2.5)), 4), round(float(np.percentile(bs, 97.5)), 4)]


def boot_diff(a, b, n=4000, seed=0):
    import numpy as np
    a = np.asarray([x for x in a if x is not None], dtype=float)
    b = np.asarray([x for x in b if x is not None], dtype=float)
    if len(a) < 2 or len(b) < 2:
        return None
    rng = np.random.default_rng(seed)
    d = rng.choice(a, size=(n, len(a))).mean(1) - rng.choice(b, size=(n, len(b))).mean(1)
    return [round(float(np.percentile(d, 2.5)), 4), round(float(np.percentile(d, 97.5)), 4)]


def spearman_profiles(pa, pb):
    import numpy as np
    gs = [g for g in V.GROUPS if g in pa and g in pb]
    if len(gs) < 5:
        return None, gs
    return V.spearman(np.array([pa[g] for g in gs]), np.array([pb[g] for g in gs])), gs


# ───────────────────────────── angles / items / jobs ─────────────────────────────
def cmd_angles(a):
    import numpy as np
    by = {}
    for d in a.dirs:
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".json") or fn.endswith(".sched.json"):
                continue
            m = VIEW_RE.search(fn)
            view = m.group(1) if m else ("render" if fn.startswith("txt_") else "?")
            dd = json.load(open(os.path.join(d, fn), encoding="utf-8"))
            W, H = dd.get("img_wh") or [640, 360]
            ys, ps = [], []
            for fr in dd["frames"][::5]:
                r = protrusion(fr.get("lm"), fr.get("fx"), W, H)
                if r:
                    ys.append(r[1]); ps.append(r[2])
            if ys:
                by.setdefault((os.path.basename(os.path.normpath(d)), view), []).append((float(np.median(ys)), float(np.median(ps))))
    out = {}
    for (d, v), xs in sorted(by.items()):
        y = np.array([x[0] for x in xs]); p = np.array([x[1] for x in xs])
        out[f"{d}:{v}"] = {"n_clips": len(xs), "yaw_median": round(float(np.median(y)), 1), "yaw_p10_p90": [round(float(np.percentile(y, 10)), 1), round(float(np.percentile(y, 90)), 1)],
                           "pitch_median": round(float(np.median(p)), 1), "pitch_p10_p90": [round(float(np.percentile(p, 10)), 1), round(float(np.percentile(p, 90)), 1)]}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    if a.out:
        json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def cmd_items(a):
    """manifest_meta(시점이 A가 아닌 화자)와 manifest.tsv → 정렬 작업과 화자 표."""
    speakers, clips = [], []
    for root in a.root:
        meta = {}
        for line in open(os.path.join(root, "manifest_meta.tsv"), encoding="utf-8"):
            p = line.rstrip("\n").split("\t")
            if p[0].startswith("#") or len(p) < 11:
                continue
            meta[p[0]] = {"person": p[2], "view": p[9], "noise": p[10], "spec": "E" if p[2].startswith("E") else "C"}
        side = {s for s, m in meta.items() if m["view"] != "A" and "," not in m["view"]}
        for s in sorted(side):
            speakers.append({"spk": s, "half": half_of(s), **meta[s], "root": root})
        for line in open(os.path.join(root, "manifest.tsv"), encoding="utf-8"):
            p = line.rstrip("\n").split("\t")
            if len(p) < 3 or p[1] not in side:
                continue
            mp4 = os.path.join(root, "clips", p[0])
            m = VIEW_RE.search(p[0])
            clips.append({"clip": p[0][:-4], "spk": p[1], "text": p[2], "mp4": mp4, "wav": mp4[:-4] + ".wav",
                          "view": m.group(1) if m else "?", "half": half_of(p[1])})
    json.dump({"speakers": speakers, "clips": clips}, open(a.out_sel, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(a.out_items, "w", encoding="utf-8") as fo:
        for c in clips:
            fo.write(json.dumps({"key": "real:" + c["clip"], "text": c["text"], "audio": "/workspace/v18/clips/" + os.path.basename(c["wav"])}, ensure_ascii=False) + "\n")
    from collections import Counter
    print("ITEMS", len(speakers), "speakers", len(clips), "clips", dict(Counter((s["half"], s["view"]) for s in speakers)))


def cmd_jobs(a):
    jobs = [j for j in json.load(open(a.jobs, encoding="utf-8")) if j.get("talker") == "default" and j["kind"] == "text"]
    out = []
    for j in jobs:
        out.append(dict(j))
        if a.v15_table:
            k = dict(j); k["id"] = j["id"].replace("_default_", "_v15_"); k["table"] = "v15"
            out.append(k)
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False)
    if a.v15_table:
        t = json.load(open(a.v15_table, encoding="utf-8"))["table"]
        json.dump({"v15": t}, open(a.out_tables, "w", encoding="utf-8"), ensure_ascii=False)
    print("JOBS", len(out))


# ───────────────────────────── analyze ─────────────────────────────
def real_records(clips, bs_dir, align):
    import numpy as np
    rec, qc, ang = {}, {"clips": 0, "no_bs": 0, "align_err": 0, "face_qc": 0, "ok": 0}, {}
    for c in clips:
        qc["clips"] += 1
        bp = os.path.join(bs_dir, c["clip"] + ".json")
        r = align.get("real:" + c["clip"])
        if not os.path.exists(bp):
            qc["no_bs"] += 1
            continue
        if r is None or "error" in r:
            qc["align_err"] += 1
            continue
        ser = load_series_p(bp)
        segs, span = V.segments_from_align(r, V.LAG_S)
        x = clip_rec(ser, segs, span)
        if x is None:
            qc["face_qc"] += 1
            continue
        qc["ok"] += 1
        rec.setdefault(c["spk"], []).append(x)
        ang.setdefault(c.get("view", "A"), []).append(x["angle"])
    angles = {v: {"yaw": round(float(np.median([q[0] for q in xs])), 1), "pitch": round(float(np.median([q[1] for q in xs])), 1), "n": len(xs)}
              for v, xs in ang.items()}
    return rec, qc, angles


def render_records(renders, bs_dir, sid_half, tag):
    """렌더 폴더 → {(절반, 조건): [기록]}. 조건 = 작업 id의 셋째 이후(예: default_2.0, v15_1.0)."""
    import numpy as np
    out, qc, ang = {}, {"jobs": 0, "no_bs": 0, "face_qc": 0, "ok": 0}, []
    if not renders or not os.path.isdir(renders):
        return out, qc, None
    for fn in sorted(os.listdir(renders)):
        if not fn.endswith(".sched.json") or not fn.startswith("txt_"):
            continue
        jid = fn[:-len(".sched.json")]
        qc["jobs"] += 1
        bp = os.path.join(bs_dir, jid + ".json")
        if not os.path.exists(bp):
            qc["no_bs"] += 1
            continue
        sch = json.load(open(os.path.join(renders, fn), encoding="utf-8"))
        _, s_id, cond = jid.split("_", 2)
        ser = load_series_p(bp)
        segs, span = V.segments_from_schedule(sch)
        x = clip_rec(ser, segs, span)
        if x is None:
            qc["face_qc"] += 1
            continue
        qc["ok"] += 1
        ang.append(x["angle"])
        for h in sid_half.get(s_id, ()):
            out.setdefault((h, f"{tag}:{cond}"), []).append(x)
    angle = {"yaw": round(float(np.median([q[0] for q in ang])), 1), "pitch": round(float(np.median([q[1] for q in ang])), 1)} if ang else None
    return out, qc, angle


def load_align(paths):
    align = {}
    for path in paths:
        for l in open(path, encoding="utf-8"):
            r = json.loads(l)
            align[r["key"]] = r
    return align


def cmd_analyze(a):
    import numpy as np
    set_lip(a.lip)
    sel = json.load(open(a.sel, encoding="utf-8"))              # V2 sel.json(정면 실제 화자·문장 절반)
    side = json.load(open(a.side_sel, encoding="utf-8"))
    align = load_align(a.align)
    front_half = {s["spk"]: s["half"] for s in sel["speakers"]}
    side_half = {s["spk"]: s["half"] for s in side["speakers"]}
    side_view = {s["spk"]: s["view"] for s in side["speakers"]}
    front_rec, qf, ang_f = real_records(sel["clips"], a.front_bs, align)
    side_rec, qs, ang_s = real_records(side["clips"], a.side_bs, align)
    sid_half = {}
    for e in sel["sentences"]:
        sid_half.setdefault(e["sid"], set()).add(e["half"])
    cond_rec, rqc, rang, tag_views = {}, {}, {}, {}
    for spec in a.render:            # 태그=시점(정면은 -, 비정면은 H+I 등)=렌더폴더=추출폴더
        tag, views, rd, bd = spec.split("=", 3)
        tag_views[tag] = None if views == "-" else set(views.split("+"))
        rr, q, ag = render_records(rd, bd, sid_half, tag)
        cond_rec.update(rr)
        rqc[tag], rang[tag] = q, ag
    summary = {"lip_set": a.lip, "criteria": {"auc_pass": AUC_PASS, "auc_margin": AUC_MARGIN, "rho_pass": RHO_PASS, "rounded": ROUNDED, "unrounded": UNROUNDED},
               "qc": {"front_real": qf, "side_real": qs, "renders": rqc},
               "angles": {"front_real": ang_f, "side_real": ang_s, "renders": rang}}
    for h, name in ((0, "explore"), (1, "confirm")):
        blk = {}
        fr = {s: v for s, v in front_rec.items() if front_half.get(s) == h}
        sr = {s: v for s, v in side_rec.items() if side_half.get(s) == h}
        aucs = {"side_P": {s: speaker_auc(v, "P") for s, v in sr.items()}, "side_R": {s: speaker_auc(v, "R") for s, v in sr.items()},
                "front_P": {s: speaker_auc(v, "P") for s, v in fr.items()}, "front_R": {s: speaker_auc(v, "R") for s, v in fr.items()}}
        blk["n_speakers"] = {"front": len(fr), "side": len(sr), "side_views": {v: sum(1 for s in sr if side_view.get(s) == v) for v in sorted(set(side_view.values()))}}
        blk["auc"] = {}
        for k, d in aucs.items():
            vals = [x for x in d.values() if x is not None]
            blk["auc"][k] = {"mean": round(float(np.mean(vals)), 4) if vals else None, "ci95": boot_mean(vals),
                             "median": round(float(np.median(vals)), 4) if vals else None, "n": len(vals),
                             "per_speaker": {s: (round(x, 4) if x is not None else None) for s, x in sorted(d.items())}}
        sp, fr_ = blk["auc"]["side_P"]["mean"], blk["auc"]["front_R"]["mean"]
        blk["diff_sideP_frontR"] = {"point": round(sp - fr_, 4) if sp is not None and fr_ is not None else None,
                                    "ci95": boot_diff(list(aucs["side_P"].values()), list(aucs["front_R"].values()))}
        blk["diff_sideP_frontP"] = {"point": round(sp - blk["auc"]["front_P"]["mean"], 4) if sp is not None and blk["auc"]["front_P"]["mean"] is not None else None,
                                    "ci95": boot_diff(list(aucs["side_P"].values()), list(aucs["front_P"].values()))}
        blk["pass_a"] = bool(sp is not None and fr_ is not None and sp >= AUC_PASS and sp - fr_ >= AUC_MARGIN)
        # 순위: 실제 화자 무리 프로필 평균 vs 아바타 조건(같은 시점끼리)
        sprof = {s: group_profile(v, "P") for s, v in sr.items()}
        fprof = {s: group_profile(v, "P") for s, v in fr.items()}
        mean_side = mean_profile(sprof.values())
        mean_front = mean_profile(fprof.values())
        blk["rank"] = {"real_side_profile": {g: round(x, 4) for g, x in mean_side.items()},
                       "real_front_profile": {g: round(x, 4) for g, x in mean_front.items()},
                       "real_side_vs_front_rho": spearman_profiles(mean_side, mean_front)[0],
                       "human_loo_rho_side": loo_rho(sprof), "human_loo_rho_front": loo_rho(fprof), "cond": {}}
        conds = {}
        for (hh, key), recs in cond_rec.items():
            if hh != h:
                continue
            tag, cond = key.split(":", 1)
            views = tag_views[tag]
            if views is None:
                ref, nsp = mean_front, len(fprof)
            else:
                ps = [p for s, p in sprof.items() if side_view.get(s) in views]
                ref, nsp = mean_profile(ps), len(ps)
            p = group_profile(recs, "P")
            rho, gs = spearman_profiles(p, ref)
            blk["rank"]["cond"][key] = {"rho": round(rho, 4) if rho is not None else None, "n_groups": len(gs), "n_clips": len(recs),
                                        "n_real_speakers": nsp, "profile": {g: round(x, 4) for g, x in p.items()},
                                        "auc_rounded_P": speaker_auc(recs, "P"), "auc_rounded_R": speaker_auc(recs, "R")}
            if views is not None and rho is not None and nsp:
                conds.setdefault(cond, []).append((rho, nsp))
        blk["rank"]["side_weighted"] = {c: round(sum(r * n for r, n in xs) / sum(n for _, n in xs), 4) for c, xs in conds.items()}
        prim = blk["rank"]["side_weighted"].get(a.primary)
        blk["primary_cond"] = a.primary
        blk["pass_b"] = bool(prim is not None and prim >= RHO_PASS)
        summary[name] = blk
    c = summary["confirm"]
    summary["verdict"] = {"a_side_auc": c["pass_a"], "b_avatar_rank": c["pass_b"], "v18_pass": bool(c["pass_a"] and c["pass_b"]),
                          "note": "b는 a를 통과해야 판정으로 읽는다(지표가 검증되지 않으면 순위는 보고만)."}
    json.dump(summary, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1,
              default=lambda o: float(o) if hasattr(o, "__float__") else str(o))
    print("ANALYZE_OK", a.out, json.dumps(summary["verdict"], ensure_ascii=False))


def cmd_explore(a):
    """탐색 절반 비정면 화자에서 입술 점 후보별 평균 화자 AUC(사전 등록 5.1절). 확인 절반은 읽지 않는다."""
    import numpy as np
    side = json.load(open(a.side_sel, encoding="utf-8"))
    align = load_align(a.align)
    clips = [c for c in side["clips"] if c["half"] == 0]
    out = {}
    for name in LIP_SETS:
        set_lip(name)
        rec, qc, ang = real_records(clips, a.side_bs, align)
        p = [speaker_auc(v, "P") for v in rec.values()]
        r = [speaker_auc(v, "R") for v in rec.values()]
        p = [x for x in p if x is not None]; r = [x for x in r if x is not None]
        out[name] = {"mean_auc_P": round(float(np.mean(p)), 4), "n": len(p), "mean_auc_R_side": round(float(np.mean(r)), 4), "qc": qc, "angles": ang}
    best = max(LIP_SETS, key=lambda k: (out[k]["mean_auc_P"], -list(LIP_SETS).index(k)))
    out["chosen"] = best
    print(json.dumps(out, ensure_ascii=False, indent=1))
    if a.out:
        json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


# ───────────────────────────── selftest ─────────────────────────────
def cmd_selftest(_a):
    import numpy as np
    rng = np.random.default_rng(0)
    # 정면 얼굴의 가짜 랜드마크: 눈꼬리 (±0.1, 0.4), 입술 가운데 6점은 z로 앞에 나온다
    base = np.zeros((43, 3))
    base[EYE_A] = [0.4, 0.4, 0.0]
    base[EYE_B] = [0.6, 0.4, 0.0]
    for k in LIP_MID:
        base[k] = [0.5, 0.6, -0.05]
    def lm_of(b):
        return [float(x) for x in b.reshape(-1)]
    eye = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, -40, 0, 0, 0, 1]
    P0, y0, p0 = protrusion(lm_of(base), eye, 640, 360)
    assert abs(y0) < 1e-6 and abs(p0) < 1e-6, (y0, p0)
    assert abs(P0 - 0.05 * 640 / (0.2 * 640)) < 1e-6, P0
    # 머리를 y축으로 30° 돌리고 같은 회전을 fx에 넣으면 P가 같아야 한다(좌표계 되돌림 확인)
    th = math.radians(30)
    Ry = np.array([[math.cos(th), 0, math.sin(th)], [0, 1, 0], [-math.sin(th), 0, math.cos(th)]])
    cam = frame_pts(lm_of(base), 640, 360)
    ctr = cam.mean(0)
    rot = (cam - ctr) @ Ry.T + ctr
    back = np.stack([rot[:, 0] / 640, -rot[:, 1] / 360, -rot[:, 2] / 640], axis=1)
    fx = np.eye(4); fx[:3, :3] = Ry
    P1, y1, _ = protrusion(lm_of(back), list(fx.reshape(-1)), 640, 360)
    assert abs(P1 - P0) < 1e-6 and abs(y1 - 30) < 1e-6, (P1, P0, y1)
    # AUC
    assert abs(auc([2, 3, 4], [0, 1, 1.5]) - 1.0) < 1e-9
    assert abs(auc([1, 1, 1], [1, 1, 1]) - 0.5) < 1e-9
    assert auc([1, 2], [0, 0, 0]) is None
    # 순위
    pa = {g: float(i) for i, g in enumerate(V.GROUPS)}
    pb = {g: float(i) + rng.normal(0, 0.1) for i, g in enumerate(V.GROUPS)}
    rho, gs = spearman_profiles(pa, pb)
    assert rho > 0.95 and len(gs) == len(V.GROUPS)
    print("V18_SELFTEST_OK")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("angles"); s.add_argument("dirs", nargs="+"); s.add_argument("--out", default="")
    s = sub.add_parser("items"); s.add_argument("--root", action="append", required=True); s.add_argument("--out-sel", required=True)
    s.add_argument("--out-items", required=True)
    s = sub.add_parser("jobs"); s.add_argument("--jobs", required=True); s.add_argument("--out", required=True)
    s.add_argument("--v15-table", default=""); s.add_argument("--out-tables", default="")
    s = sub.add_parser("analyze")
    s.add_argument("--sel", required=True); s.add_argument("--side-sel", required=True)
    s.add_argument("--align", action="append", required=True)
    s.add_argument("--front-bs", required=True); s.add_argument("--side-bs", required=True)
    s.add_argument("--render", action="append", default=[], help="태그=시점(-|H+I)=렌더폴더=추출폴더")
    s.add_argument("--primary", default="default_2.0"); s.add_argument("--out", required=True)
    s.add_argument("--lip", required=True, choices=list(LIP_SETS))
    s = sub.add_parser("explore"); s.add_argument("--side-sel", required=True); s.add_argument("--align", action="append", required=True)
    s.add_argument("--side-bs", required=True); s.add_argument("--out", default="")
    sub.add_parser("selftest")
    a = ap.parse_args()
    {"angles": cmd_angles, "items": cmd_items, "explore": cmd_explore, "jobs": cmd_jobs, "analyze": cmd_analyze, "selftest": cmd_selftest}[a.cmd](a)


if __name__ == "__main__":
    main()
