"""파드: 선행 동시조음(CLAUDE.md 3D 모션 E) 검증. 설계와 판정 기준은 docs/coarticulation-e.md(계산 전에 적음).

538 정상 화자 문장 영상에서 MediaPipe FaceLandmarker 블렌드셰이프(funnel·pucker·smile·stretch·jawOpen)를 프레임마다 뽑고,
같은 문장을 아바타가 어떻게 움직이는지(엔진 프레임 + 아바타 입모양 표, 동시조음 끔/켬)를 음성 정렬 시각에 맞춰 흉내 내
두 궤적의 상관을 잰다. 입모양 표와 동시조음 규칙은 frontend에서 내보낸 scripts/viseme_shapes.json을 그대로 읽는다
(생성: node scripts/export_viseme_shapes.mjs). 프레임은 backend/engine.py의 text_to_visemes를 그대로 쓴다.

  # 파드(정렬기 = backend/models/dgop_ours/aligner, 화자 절반 0 탐색 → 절반 1 확인을 한 번에)
  python scripts/coart_pod_eval.py --root /workspace/c538 --out /workspace/out/coart_e --workers 16 \
      --face-model /workspace/face_landmarker.task
  # 로컬 스모크(정렬기 없이 음절을 발화 구간에 고르게 놓는다. 판정에는 쓰지 않는다)
  python scripts/coart_pod_eval.py --root <538 클립 폴더> --limit 3 --align uniform --out <임시 폴더> --face-model <task>
  # JSON 이식 확인만
  python scripts/coart_pod_eval.py --selftest

--root 폴더에는 manifest.tsv(클립\t화자\t문장)가 있고, 클립 mp4는 root/ 또는 root/clips/에 있어야 한다. 음성은 같은 이름의
.wav·.flac가 있으면 그것을, 없으면 mp4에서 ffmpeg로 뽑는다. 결과: <out>/clips.jsonl(클립별), <out>/summary.json(판정).
MediaPipe 결과는 <out>/cache/에 남겨, 다시 돌리면 영상 처리를 건너뛴다.
"""
import argparse
import asyncio
import json
import math
import os
import random
import re
import subprocess
import sys
import unicodedata
import zlib
from concurrent.futures import ProcessPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
FEATS = ("R", "S", "J")                 # 둥글림 funnel+pucker, 당김 smile+stretch(좌우 평균), 벌림 jawOpen
W_GRID = (0.5, 0.6, 0.7)                # 탐색 절반에서 고르는 섞는 비율(앱 기본 COART_W는 JSON의 coart.w)
LAGS_MS = tuple(range(-132, 133, 33))   # 영상이 음성보다 앞서는 만큼(음수 = 실제 입이 먼저 움직임), 탐색 절반에서 고른다
MIN_SAMPLES = 15
MIN_FACE_RATIO = 0.8
DELTA_R_MIN = 0.05                      # 판정: 둥글림 상관이 이만큼 올라야 한다
GUARD_DROP = 0.02                       # 판정: 벌림·당김 상관이 이보다 더 떨어지면 안 된다
VIEW_RE = re.compile(r"_C\d+_([A-Z])_\d+")


# ── 입모양 표·동시조음 규칙(frontend/src/lib/coarticulation.js 이식, 표는 JSON 하나를 같이 쓴다) ──────────────────────
def load_shapes(path):
    d = json.load(open(path, encoding="utf-8"))
    table = {int(k): v for k, v in d["blendshapes"].items()}
    c = d["coart"]
    cfg = {"targets": set(c["targets"]), "vowels": set(c["vowels"]), "stops": set(c["stops"]),
           "lip_keys": list(c["lip_keys"]), "w": float(c["w"])}
    return table, cfg, d.get("fixtures", [])


def apply_coart(visemes, cfg):
    """프레임 입모양 열 → 프레임마다 섞을 모음(없으면 None). 같은 단어 안의 다음 모음, 없으면 앞 모음. 9는 원순 활음(4)으로."""
    n = len(visemes)
    nxt, nv = [None] * n, None
    for i in range(n - 1, -1, -1):
        v = visemes[i]
        if v in cfg["stops"]:
            nv = None
        elif v in cfg["vowels"]:
            nv = v
        nxt[i] = nv
    out, pv = [], None
    for i, v in enumerate(visemes):
        if v in cfg["stops"]:
            pv = None
        elif v in cfg["vowels"]:
            pv = v
        lv = (nxt[i] if nxt[i] is not None else pv) if v in cfg["targets"] else None
        out.append(4 if lv == 9 else lv)
    return out


def next_vowel(visemes, cfg):
    """프레임마다 같은 단어 안의 다음 모음(선행만, 잔류 없음). 전제 확인용."""
    out, nv = [None] * len(visemes), None
    for i in range(len(visemes) - 1, -1, -1):
        v = visemes[i]
        if v in cfg["stops"]:
            nv = None
        elif v in cfg["vowels"]:
            nv = 4 if v == 9 else v
        out[i] = nv
    return out


def blend_lip(base, vowel, w, lip_keys):
    """max(자음 값, (1-w)·자음 값 + w·모음 값)을 입술 모프에만. 턱·닫힘은 자음 값 그대로(coarticulation.blendLip과 같은 식)."""
    out = dict(base)
    for k in lip_keys:
        b = base.get(k, 0.0)
        x = max(b, (1 - w) * b + w * vowel.get(k, 0.0))
        if x > 0:
            out[k] = x
    return out


def shape_of(table, cfg, v, lv, w):
    base = table.get(v, {})
    if lv is None or v not in cfg["targets"] or not w > 0:
        return base
    return blend_lip(base, table.get(lv, {}), w, cfg["lip_keys"])


def feat_vec(shape):
    g = lambda k: float(shape.get(k, 0.0))
    return (g("mouthFunnel") + g("mouthPucker"),
            (g("mouthSmileLeft") + g("mouthSmileRight") + g("mouthStretchLeft") + g("mouthStretchRight")) / 2,
            g("jawOpen"))


def selftest(shapes_path):
    table, cfg, fixtures = load_shapes(shapes_path)
    bad = 0
    for fx in fixtures:
        lip = apply_coart(fx["visemes"], cfg)
        if lip != fx["coart_v"]:
            bad += 1
            print("coart_v 불일치", fx["visemes"], lip, fx["coart_v"])
        for v, lv, want in zip(fx["visemes"], lip, fx["shapes"]):
            got = shape_of(table, cfg, v, lv, cfg["w"])
            keys = set(got) | set(want)
            if any(abs(got.get(k, 0) - want.get(k, 0)) > 1e-9 for k in keys):
                bad += 1
                print("모양 불일치", v, lv, got, want)
    print(f"selftest: 표본 {len(fixtures)}개, 불일치 {bad}")
    return bad == 0


# ── 엔진 프레임과 음절 역할 ────────────────────────────────────────────────────────────────────────────────
def engine_frames(engine, text):
    """(프레임 목록, 역할 목록, 음절 번호 목록). 역할: on·nu·nu2·co·tr(음절), pause(음절 밖). 어긋나면 None."""
    text = unicodedata.normalize("NFC", text or "").strip()
    frames = asyncio.run(engine.text_to_visemes(text))
    toks = engine.to_pronounced_syllables(text)
    roles_by_tok = {}
    syl_of_tok = {}
    k = 0
    for i, tok in enumerate(toks):
        if not isinstance(tok, list):
            continue
        ini, med, fin = tok
        if not med:
            continue
        nxt_ini = toks[i + 1][0] if i + 1 < len(toks) and isinstance(toks[i + 1], list) else None
        r = (["on"] if ini else []) + (["nu", "nu2"] if med in engine.DIPHTHONG_GLIDE else ["nu"])
        if fin:
            r.append("co")
            if engine.get_transition_viseme(fin, nxt_ini)[0]:
                r.append("tr")
        roles_by_tok[i] = r
        syl_of_tok[i] = k
        k += 1
    roles, syls, seen = [], [], {}
    for f in frames:
        ti = f.get("text_index")
        if ti in roles_by_tok:
            j = seen.get(ti, 0)
            seen[ti] = j + 1
            if j >= len(roles_by_tok[ti]):
                return None
            roles.append(roles_by_tok[ti][j])
            syls.append(syl_of_tok[ti])
        else:
            roles.append("pause")
            syls.append(None)
    if any(seen.get(ti, 0) != len(r) for ti, r in roles_by_tok.items()):
        return None
    return frames, roles, syls, k


# ── 음성 정렬 → 음절별 시각 ──────────────────────────────────────────────────────────────────────────────────
def load_audio(clip_path):
    import numpy as np
    stem = os.path.splitext(clip_path)[0]
    for ext in (".wav", ".flac"):
        if os.path.exists(stem + ext):
            try:
                import soundfile as sf
                y, sr = sf.read(stem + ext, dtype="float32")
                if y.ndim > 1:
                    y = y.mean(axis=1)
                if sr == 16000:
                    return y
            except Exception:
                pass
            clip_path = stem + ext
            break
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", clip_path, "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def parse_syllables(tokens, spans_sec):
    """자모 토큰열(o:·n:·c:·|)과 토큰별 (t0, t1) → 음절 목록 [{on, nu, co, word_end}]."""
    syls = []
    for tok, sp in zip(tokens, spans_sec):
        if tok == "|":
            if syls:
                syls[-1]["word_end"] = True
            continue
        kind = tok[:2]
        if kind == "o:":
            syls.append({"on": sp, "nu": None, "co": None, "word_end": False})
        elif kind == "n:":
            if syls and syls[-1]["nu"] is None and syls[-1]["on"] is not None:
                syls[-1]["nu"] = sp
            else:
                syls.append({"on": None, "nu": sp, "co": None, "word_end": False})
        elif kind == "c:" and syls:
            syls[-1]["co"] = sp
    if syls:
        syls[-1]["word_end"] = True
    return syls


def align_ctc(wave, text, aligner):
    import dgop_acoustic as D
    tokens = D.tokens_for_text(text, model_id=aligner)
    lp, vocab = D.ctc_log_probs(wave, 16000, model_id=aligner)
    spans = D.align_targets(lp, vocab, tokens)
    spf = (len(wave) / 16000.0) / max(1, int(lp.shape[0]))
    sec = [(s["start"] * spf, (s["end"] + 1) * spf) for s in spans]
    return parse_syllables(tokens, sec)


def align_uniform(wave, n_syl, word_end_after):
    """스모크 전용: 발화 구간(에너지)에 음절을 고르게 놓는다. 음절 안은 초성 0~30%, 중성 30~80%, 종성 80~100%."""
    import numpy as np
    hop = 320
    n = len(wave) // hop
    e = np.array([float(np.sqrt(np.mean(wave[i * hop:(i + 1) * hop] ** 2)) + 1e-9) for i in range(n)])
    db = 20 * np.log10(e / e.max())
    on = np.where(db > -35)[0]
    a, b = (on[0] * hop / 16000.0, (on[-1] + 1) * hop / 16000.0) if len(on) else (0.0, len(wave) / 16000.0)
    step = (b - a) / max(1, n_syl)
    syls = []
    for j in range(n_syl):
        s = a + j * step
        syls.append({"on": (s, s + 0.3 * step), "nu": (s + 0.3 * step, s + 0.8 * step), "co": (s + 0.8 * step, s + step),
                     "word_end": j in word_end_after or j == n_syl - 1})
    return syls


def frame_starts(frames, roles, syls_idx, syls):
    """엔진 프레임마다 시작 시각(초). 없는 앵커는 음절 안 비율로 채운다. 짧은 쉼(80ms 미만)은 None으로 빼 버린다."""
    n_syl = len(syls)
    starts = []
    for f, role, j in zip(frames, roles, syls_idx):
        if j is None:
            starts.append(None)
            continue
        s = syls[j]
        a_n = s["nu"][0]
        nxt = syls[j + 1] if j + 1 < n_syl else None
        nxt_start = (nxt["on"] or nxt["nu"])[0] if nxt else (s["co"] or s["nu"])[1] + 0.05
        end = nxt_start
        if role == "on":
            t = s["on"][0] if s["on"] else a_n - 0.06
        elif role == "nu":
            t = a_n
        elif role == "nu2":
            e_nu = s["co"][0] if s["co"] else end
            t = a_n + 0.35 * max(0.0, e_nu - a_n)
        elif role == "co":
            t = s["co"][0] if s["co"] else a_n + 0.6 * max(0.0, end - a_n)
        else:  # tr
            c0 = s["co"][0] if s["co"] else a_n + 0.6 * max(0.0, end - a_n)
            t = max(c0 + 0.5 * max(0.0, end - c0), end - 0.055)
        starts.append(t)
    # 쉼: 앞 음절 마지막 토큰 끝에서 시작, 다음 음절까지 80ms가 안 되면 뺀다(실제 말에는 단어 사이 쉼이 거의 없다)
    for i, (role, j) in enumerate(zip(roles, syls_idx)):
        if role != "pause":
            continue
        prev = next((syls_idx[k] for k in range(i - 1, -1, -1) if syls_idx[k] is not None), None)
        nxt_i = next((k for k in range(i + 1, len(roles)) if starts[k] is not None and syls_idx[k] is not None), None)
        if prev is None or nxt_i is None:
            continue
        s = syls[prev]
        t = (s["co"] or s["nu"])[1]
        if starts[nxt_i] - t >= 0.08:
            starts[i] = t
    # 단조 증가(같은 시각이면 5ms씩 민다)
    last = -1e9
    for i, t in enumerate(starts):
        if t is None:
            continue
        if t < last + 0.005:
            t = last + 0.005
        starts[i] = t
        last = t
    return starts


# ── 아바타 궤적 흉내(AvatarVRM: 전환은 transition_ms, 프레임 길이 60% 안, easeInOutCubic) ───────────────────────────
def ease(x):
    x = min(1.0, max(0.0, x))
    return 4 * x * x * x if x < 0.5 else 1 - ((-2 * x + 2) ** 3) / 2


def simulate(events, ts):
    """events: [(시작 초, 목표 (R,S,J), transition_ms)] 시간순. ts: 표본 시각 배열 → (len(ts), 3)."""
    import numpy as np
    out = np.zeros((len(ts), 3))
    cur = (0.0, 0.0, 0.0)
    segs = []
    for k, (t0, tgt, tr) in enumerate(events):
        dur = (events[k + 1][0] - t0) if k + 1 < len(events) else 0.3
        T = max(0.016, min(tr / 1000.0, 0.6 * dur)) if dur > 0 else 0.016
        segs.append((t0, cur, tgt, T))
        e = ease(dur / T) if dur > 0 else 1.0
        cur = tuple(a + (b - a) * e for a, b in zip(cur, tgt))
    j = -1
    for i, t in enumerate(ts):
        while j + 1 < len(segs) and segs[j + 1][0] <= t:
            j += 1
        if j < 0:
            continue
        t0, a, b, T = segs[j]
        e = ease((t - t0) / T)
        out[i] = [x + (y - x) * e for x, y in zip(a, b)]
    return out


# ── MediaPipe ───────────────────────────────────────────────────────────────────────────────────────────────
def mediapipe_series(path, model):
    import cv2
    import mediapipe as mp
    import numpy as np
    from mediapipe.tasks.python import BaseOptions, vision
    # CPU로 고정한다(파드는 CPU로 돈다). 맥의 mediapipe 파이썬은 CPU로 고정해도 얼굴 검출에서 Metal 오류로 죽어 --face stub으로만 돌린다.
    try:
        base = BaseOptions(model_asset_path=model, delegate=BaseOptions.Delegate.CPU)
    except (AttributeError, TypeError):
        base = BaseOptions(model_asset_path=model)
    opts = vision.FaceLandmarkerOptions(base_options=base, running_mode=vision.RunningMode.VIDEO,
                                        output_face_blendshapes=True, num_faces=1)
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    rows = []
    with vision.FaceLandmarker.create_from_options(opts) as lm:
        i = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            img = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            res = lm.detect_for_video(img, int(round(i * 1000.0 / fps)))
            if res.face_blendshapes:
                d = {c.category_name: c.score for c in res.face_blendshapes[0]}
                rows.append(feat_vec(d))
            else:
                rows.append((math.nan, math.nan, math.nan))
            i += 1
    cap.release()
    return float(fps), np.array(rows, dtype=float).reshape(-1, 3)


def pearson(a, b):
    import numpy as np
    if len(a) < MIN_SAMPLES or np.std(a) < 1e-6 or np.std(b) < 1e-6:
        return None
    return float(np.corrcoef(a, b)[0, 1])


# ── 클립 하나 ─────────────────────────────────────────────────────────────────────────────────────────────────
def clip_job(args):
    clip_path, clip, spk, text, a = args
    try:
        import numpy as np
        sys.path.insert(0, a["backend"])
        os.environ.setdefault("BACKBONE_QUANT", "int8")
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        try:
            import torch
            torch.set_num_threads(2)
        except Exception:
            pass
        import engine
        table, cfg, _ = load_shapes(a["shapes"])
        ef = engine_frames(engine, text)
        if ef is None:
            return {"clip": clip, "spk": spk, "error": "frame_roles"}
        frames, roles, syls_idx, n_syl = ef
        wave = load_audio(clip_path)
        if a["align"] == "ctc":
            syls = align_ctc(wave, text, a["aligner"])
        else:
            word_end = {syls_idx[i - 1] for i, r in enumerate(roles) if r == "pause" and i and syls_idx[i - 1] is not None}
            syls = align_uniform(wave, n_syl, word_end)
        if len(syls) != n_syl:
            return {"clip": clip, "spk": spk, "error": f"syllables {len(syls)} vs {n_syl}"}
        starts = frame_starts(frames, roles, syls_idx, syls)
        vis = [f["viseme"] for f in frames]
        lip = apply_coart(vis, cfg)
        keep = [i for i, t in enumerate(starts) if t is not None]
        t_first = min(s["on"][0] if s["on"] else s["nu"][0] for s in syls)
        t_last = max((s["co"] or s["nu"])[1] for s in syls)
        conds = {"off": None, **{f"on{w}": w for w in W_GRID}}

        def events(w):
            ev = []
            for i in keep:
                v = vis[i]
                shp = shape_of(table, cfg, v, lip[i] if w is not None else None, w or 0)
                tr = frames[i].get("transition_ms")
                ev.append((starts[i], feat_vec(shp), 30 if tr is None else tr))
            ev.append((t_last + 0.1, (0.0, 0.0, 0.0), 150))   # 끝나면 쉼 자세로(MouthAvatar의 중립 복귀)
            return ev

        ev = {c: events(w) for c, w in conds.items()}
        if a["face"] == "stub":
            # 스모크 전용(맥은 MediaPipe 파이썬이 Metal 오류로 죽는다): '실제' 궤적을 켬(0.6) 흉내에 잡음을 더해 만든다.
            # 분석 배관(정렬·흉내·상관·집계)이 켬 쪽 향상을 제대로 잡는지만 본다. 판정에는 쓰지 않는다.
            import cv2
            cap = cv2.VideoCapture(clip_path)
            fps, nfr = cap.get(cv2.CAP_PROP_FPS) or 30.0, int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.release()
            sim = simulate(ev["on0.6"], np.arange(nfr) / fps)
            noise = np.random.default_rng(zlib.crc32(clip.encode())).normal(0, 1, sim.shape) * (sim.std(axis=0) * 0.5 + 1e-3)
            real = sim + noise
        else:
            cache = os.path.join(a["out"], "cache", clip + ".npz")
            if os.path.exists(cache):
                z = np.load(cache)
                fps, real = float(z["fps"]), z["real"]
            else:
                fps, real = mediapipe_series(clip_path, a["face_model"])
                np.savez_compressed(cache, fps=fps, real=real)
        ts_all = np.arange(real.shape[0]) / fps
        lo, hi = t_first - 0.15, t_last + 0.15
        m = (ts_all >= lo) & (ts_all <= hi)
        face_ratio = float(np.mean(~np.isnan(real[m, 0]))) if m.any() else 0.0
        valid = m & ~np.isnan(real[:, 0])
        ts, rv = ts_all[valid], real[valid]
        res = {"clip": clip, "spk": spk, "n": int(valid.sum()), "face_ratio": round(face_ratio, 3), "n_syl": n_syl,
               "align": a["align"], "face": a["face"], "r": {}, "seg": []}
        for c in conds:
            res["r"][c] = {f: [] for f in FEATS}
            for lag in LAGS_MS:
                sim = simulate(ev[c], ts - lag / 1000.0)
                for fi, fname in enumerate(FEATS):
                    res["r"][c][fname].append(pearson(sim[:, fi], rv[:, fi]))
        # 전제 확인(서술): 선행 대상 자음 구간의 실제 둥글림(클립 안 z)을 다음 모음이 원순인지로 나눈다
        if len(rv) >= MIN_SAMPLES and np.std(rv[:, 0]) > 1e-6:
            zr = (rv[:, 0] - rv[:, 0].mean()) / rv[:, 0].std()
            sims = {c: simulate(ev[c], ts) for c in ("off", "on0.6")}
            zs = {c: (s[:, 0] - s[:, 0].mean()) / (s[:, 0].std() or 1.0) for c, s in sims.items()}
            nxt_v = next_vowel(vis, cfg)
            for i in keep:
                if vis[i] not in cfg["targets"] or nxt_v[i] is None:
                    continue
                later = [k for k in keep if starts[k] > starts[i]]
                t0, t1 = starts[i], (starts[later[0]] if later else starts[i] + 0.1)
                row = {"v": vis[i], "next": nxt_v[i], "t0": round(t0, 3), "t1": round(t1, 3), "real": []}
                for lag in LAGS_MS:
                    sel = (ts - lag / 1000.0 >= t0) & (ts - lag / 1000.0 < t1)
                    row["real"].append(float(zr[sel].mean()) if sel.any() else None)
                sel0 = (ts >= t0) & (ts < t1)
                for c in zs:
                    row[c] = float(zs[c][sel0].mean()) if sel0.any() else None
                res["seg"].append(row)
        return res
    except Exception as e:
        return {"clip": clip, "spk": spk, "error": f"{type(e).__name__}: {e}"}


# ── 집계와 판정 ───────────────────────────────────────────────────────────────────────────────────────────────
def half_of(spk):
    return zlib.crc32(spk.encode()) % 2


def rbar(clips, cond, feat, li, spks=None):
    """화자마다 클립 r의 Fisher z 평균 → 화자 평균 → r. off·cond 둘 다 정의된 클립만."""
    by = {}
    for c in clips:
        a, b = c["r"]["off"][feat][li], c["r"][cond][feat][li]
        if a is None or b is None:
            continue
        by.setdefault(c["spk"], []).append(math.atanh(max(-0.999, min(0.999, b))))
    keys = spks if spks is not None else sorted(by)
    zs = [sum(by[s]) / len(by[s]) for s in keys if s in by]
    return (math.tanh(sum(zs) / len(zs)), len(zs)) if zs else (None, 0)


def delta(clips, cond, feat, li, spks=None):
    on, n = rbar(clips, cond, feat, li, spks)
    off, _ = rbar(clips, "off", feat, li, spks)
    return (None if on is None or off is None else on - off), n


def boot_ci(clips, cond, feat, li, reps=2000, seed=1):
    """화자 재표집 95% 구간(같은 화자를 여러 번 뽑으면 그만큼 무게를 준다)."""
    zc = lambda r: math.atanh(max(-0.999, min(0.999, r)))
    per = {}
    for c in clips:
        a, b = c["r"]["off"][feat][li], c["r"][cond][feat][li]
        if a is not None and b is not None:
            per.setdefault(c["spk"], []).append((zc(b), zc(a)))
    zs = [(sum(x for x, _ in v) / len(v), sum(y for _, y in v) / len(v)) for v in per.values()]
    rng = random.Random(seed)
    vals = []
    for _ in range(reps if zs else 0):
        pick = [zs[rng.randrange(len(zs))] for _ in zs]
        vals.append(math.tanh(sum(p[0] for p in pick) / len(pick)) - math.tanh(sum(p[1] for p in pick) / len(pick)))
    vals.sort()
    return (round(vals[int(0.025 * len(vals))], 4), round(vals[int(0.975 * len(vals)) - 1], 4)) if vals else (None, None)


def premise(clips, li, cond=None):
    """선행 대상 자음 구간의 z 둥글림: 다음 모음이 원순(4)인 구간 − 아닌 구간(2·3·5), 화자 평균."""
    per = {}
    for c in clips:
        for s in c.get("seg", []):
            x = s["real"][li] if cond is None else s.get(cond)
            if x is None:
                continue
            per.setdefault(c["spk"], {"r": [], "n": []})["r" if s["next"] == 4 else "n"].append(x)
    d = [sum(v["r"]) / len(v["r"]) - sum(v["n"]) / len(v["n"]) for v in per.values() if v["r"] and v["n"]]
    return (round(sum(d) / len(d), 4), len(d)) if d else (None, 0)


def summarize(results):
    ok = [c for c in results if "error" not in c and c["n"] >= MIN_SAMPLES and c["face_ratio"] >= MIN_FACE_RATIO]
    halves = {h: [c for c in ok if half_of(c["spk"]) == h] for h in (0, 1)}
    s = {"n_clips": len(results), "n_ok": len(ok), "errors": {},
         "halves": {h: {"clips": len(v), "speakers": len({c["spk"] for c in v})} for h, v in halves.items()}}
    for c in results:
        if "error" in c:
            k = c["error"].split(":")[0][:40]
            s["errors"][k] = s["errors"].get(k, 0) + 1
    ex = halves[0]
    # 1) 지연: 끔 조건의 벌림(J) 상관이 가장 큰 지연(벌림은 동시조음이 바꾸지 않아 두 조건에 중립)
    lag_r = [rbar(ex, "off", "J", li)[0] for li in range(len(LAGS_MS))]
    cand = [(r, li) for li, r in enumerate(lag_r) if r is not None]
    if not cand:
        s["verdict"] = "탐색 절반에 쓸 클립이 없다"
        return s
    li = max(cand)[1]
    s["explore"] = {"lag_ms": LAGS_MS[li], "off_J_by_lag": dict(zip(LAGS_MS, [None if r is None else round(r, 4) for r in lag_r])),
                    "by_w": {}}
    best = None
    for w in W_GRID:
        c = f"on{w}"
        row = {f: delta(ex, c, f, li)[0] for f in FEATS}
        row["off_R"] = rbar(ex, "off", "R", li)[0]
        row["on_R"] = rbar(ex, c, "R", li)[0]
        s["explore"]["by_w"][str(w)] = {k: (None if v is None else round(v, 4)) for k, v in row.items()}
        guard = all(row[f] is not None and row[f] >= -GUARD_DROP for f in ("S", "J"))
        if row["R"] is not None and guard and (best is None or row["R"] > best[1]):
            best = (w, row["R"])
    s["explore"]["premise_real"] = premise(ex, li)
    s["explore"]["premise_off"] = premise(ex, li, "off")
    s["explore"]["premise_on0.6"] = premise(ex, li, "on0.6")
    if best is None:
        s["verdict"] = "탐색 절반에서 지킴 조건을 만족하는 w가 없다(확인 안 함)"
        return s
    w = best[0]
    s["explore"]["w"] = w
    # 2) 확인 절반: 고른 지연·w 하나만 본다
    cf = halves[1]
    c = f"on{w}"
    d = {f: delta(cf, c, f, li) for f in FEATS}
    s["confirm"] = {"lag_ms": LAGS_MS[li], "w": w,
                    "delta": {f: (None if v[0] is None else round(v[0], 4)) for f, v in d.items()},
                    "speakers": {f: v[1] for f, v in d.items()},
                    "off_R": rbar(cf, "off", "R", li)[0], "on_R": rbar(cf, c, "R", li)[0],
                    "delta_R_ci95": boot_ci(cf, c, "R", li),
                    "premise_real": premise(cf, li), "premise_off": premise(cf, li, "off"), "premise_on0.6": premise(cf, li, "on0.6")}
    dr, ds, dj = (d[f][0] for f in FEATS)
    passed = dr is not None and dr >= DELTA_R_MIN and ds is not None and ds >= -GUARD_DROP and dj is not None and dj >= -GUARD_DROP
    s["verdict"] = ("통과: 플래그를 켜고 COART_W를 %s로" % w) if passed else "불통과: 플래그를 끈 채 둔다"
    if any(c.get("align") == "uniform" or c.get("face") == "stub" for c in results):
        s["verdict"] += " (uniform 정렬·가짜 궤적 스모크라 판정에 쓰지 않는다)"
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", action="append", default=[], help="manifest.tsv가 있는 538 폴더(여러 번 줄 수 있다)")
    ap.add_argument("--out", default="out/coart_e")
    ap.add_argument("--backend", default=os.path.join(HERE, "..", "backend"))
    ap.add_argument("--shapes", default=os.path.join(HERE, "viseme_shapes.json"))
    ap.add_argument("--face-model", default=os.path.join(HERE, "face_landmarker.task"))
    ap.add_argument("--aligner", default=None, help="기본: <backend>/models/dgop_ours/aligner")
    ap.add_argument("--align", choices=("ctc", "uniform"), default="ctc")
    ap.add_argument("--face", choices=("mediapipe", "stub"), default="mediapipe", help="stub: 스모크 전용 가짜 궤적(맥)")
    ap.add_argument("--views", default="A", help="쓸 촬영 방향(클립 이름의 _C###_X_). 빈 값이면 모두")
    ap.add_argument("--per-spk", type=int, default=12, help="화자마다 최대 클립 수")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if not selftest(a.shapes):
        sys.exit("viseme_shapes.json 이식 불일치: node scripts/export_viseme_shapes.mjs 로 다시 만들고 이 스크립트의 규칙을 확인한다")
    if a.selftest:
        return
    if not a.root:
        sys.exit("--root 필요")
    if a.face == "mediapipe" and not os.path.exists(a.face_model):
        sys.exit(f"FaceLandmarker 모델이 없다: {a.face_model}\n  curl -L -o {a.face_model} "
                 "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task")
    backend = os.path.abspath(a.backend)
    aligner = a.aligner or os.path.join(backend, "models", "dgop_ours", "aligner")
    os.makedirs(os.path.join(a.out, "cache"), exist_ok=True)
    views = set(a.views) if a.views else None
    jobs, seen, per = [], set(), {}
    for root in a.root:
        root = os.path.expanduser(root)
        for line in open(os.path.join(root, "manifest.tsv"), encoding="utf-8"):
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3 or parts[0].startswith("#"):
                continue
            clip, spk, text = parts[0], parts[1], parts[2]
            name = os.path.splitext(clip)[0]
            if name in seen:
                continue
            m = VIEW_RE.search(name)
            if views and (not m or m.group(1) not in views):
                continue
            path = next((p for p in (os.path.join(root, name + ".mp4"), os.path.join(root, "clips", name + ".mp4")) if os.path.exists(p)), None)
            if not path:
                continue
            seen.add(name)
            per.setdefault(spk, []).append((path, name, spk, text))
    rng = random.Random(0)
    for spk in sorted(per):
        rows = sorted(per[spk], key=lambda r: r[1])
        rng.shuffle(rows)
        jobs += rows[:a.per_spk]
    jobs.sort(key=lambda r: r[1])
    if a.limit:
        jobs = jobs[:a.limit]
    conf = {"backend": backend, "shapes": os.path.abspath(a.shapes), "face_model": os.path.abspath(a.face_model),
            "aligner": aligner, "align": a.align, "face": a.face, "out": os.path.abspath(a.out)}
    print(f"클립 {len(jobs)}개, 화자 {len({j[2] for j in jobs})}명, 정렬 {a.align}", flush=True)
    results = []
    with open(os.path.join(a.out, "clips.jsonl"), "w", encoding="utf-8") as fo:
        if a.workers <= 1:
            it = map(clip_job, [(*j, conf) for j in jobs])
        else:
            ex = ProcessPoolExecutor(a.workers)
            it = ex.map(clip_job, [(*j, conf) for j in jobs], chunksize=1)
        for k, r in enumerate(it, 1):
            results.append(r)
            fo.write(json.dumps(r, ensure_ascii=False) + "\n")
            if k % 20 == 0 or k == len(jobs):
                print(f"  {k}/{len(jobs)} (오류 {sum('error' in x for x in results)})", flush=True)
    s = summarize(results)
    json.dump(s, open(os.path.join(a.out, "summary.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(s, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
