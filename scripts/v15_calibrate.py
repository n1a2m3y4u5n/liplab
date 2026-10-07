"""V15 간이 경로: 538 탐색 절반 분포로 입모양 목표 표 보정(docs/viseme-calibration-2026-10.md, 사전 등록 2bf2291).

신경망 없이 규칙 엔진의 목표 표(frontend/src/lib/visemeShapes.js)만 다시 맞춘다. 아바타 렌더와 실제 538 영상은 V2와 같은 MediaPipe
추출기로 재고(scripts/v2_avatar_validity.py), 이 스크립트는 그 사이의 계산을 맡는다.

  poses     (맥) 리그 측정·순방향 사상용 정지 자세 렌더 작업          → jobs_poses_*.json
  dataset   (맥) 정지 자세·탐색 V2 렌더·탐색 V13 → (모프 입력, MediaPipe 특징) 표   → ds.npz
  fit       (맥) 순방향 사상(모프 가중치·턱 → MediaPipe 특징) 학습·검증          → fm.pkl
  rig       (맥) 정지 자세 격자로 mouthClose·입술 닫힘 모프의 반응 보고
  calibrate (맥) 탐색 절반 실제 분포를 목표로 표 맞추기(시뮬레이션)             → tables.json
  simulate  (맥) 표 하나로 탐색 절반 V2 지표 예측
  textjobs  (맥) 후보 표로 V2 문장 렌더 작업                                  → jobs_text_v15.json
  distinct  (맥) 6.3절 무리별 구별성(문장 하나 빼기 최근접 중심 재현율)과 V2 지표 묶음
모프 궤적은 하네스(scripts/v2_render/main.js)의 화면마다 계산을 옮긴 것이다(전환 이징, 프레임 길이 60% 안, 가상 화자 배율과 타이밍).
538 원자료와 클립별 파생 파일은 liplab-lab/data/ 아래에만 둔다. 이 저장소에는 표의 값과 집계만 남긴다.
"""
import argparse
import json
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

TICK_MS = 1000.0 / 60.0
LERP_TEXT = min(1.0, (1 / 60) * 22)
LERP_RAW = min(1.0, (1 / 60) * 34)
VIS = list(range(1, 16))
GROUPS = (1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13, 14)
# 앱 표(visemeShapes.js)가 쓰는 ARKit 모프. 좌우 짝은 같은 값으로 둔다.
ACTIVE = ["mouthClose", "mouthPressLeft", "mouthPressRight", "mouthRollLower", "mouthRollUpper", "jawOpen",
          "mouthLowerDownLeft", "mouthLowerDownRight", "mouthUpperUpLeft", "mouthUpperUpRight", "mouthSmileLeft",
          "mouthSmileRight", "mouthStretchLeft", "mouthStretchRight", "mouthFunnel", "mouthPucker", "mouthShrugUpper"]
# 순방향 사상 입력: 표가 쓸 수 있는 모프(위 + mouthShrugLower)와 V13 원본 계수에만 나오는 입 주변 모프
EXTRA = ['mouthShrugLower', 'jawForward', 'jawLeft', 'jawRight', 'mouthLeft', 'mouthRight', 'mouthFrownLeft', 'mouthFrownRight',
         'mouthDimpleLeft', 'mouthDimpleRight', 'cheekPuff', 'cheekSquintLeft', 'cheekSquintRight', 'noseSneerLeft', 'noseSneerRight',
         'tongueOut']
KEYS = ACTIVE + EXTRA
PAIRS = {'press': ('mouthPressLeft', 'mouthPressRight'), 'smile': ('mouthSmileLeft', 'mouthSmileRight'),
         'stretch': ('mouthStretchLeft', 'mouthStretchRight'), 'upperUp': ('mouthUpperUpLeft', 'mouthUpperUpRight'),
         'lowerDown': ('mouthLowerDownLeft', 'mouthLowerDownRight')}
# 표의 조절 축(좌우 묶음): 무리마다 이 값들을 정한다
CTRL = ['jawOpen', 'mouthClose', 'press', 'mouthRollLower', 'mouthRollUpper', 'mouthFunnel', 'mouthPucker', 'smile', 'stretch',
        'upperUp', 'lowerDown', 'mouthShrugUpper', 'mouthShrugLower']
AMP_KEYS = ['jawOpen', 'mouthLowerDownLeft', 'mouthLowerDownRight', 'mouthUpperUpLeft', 'mouthUpperUpRight']
WIDTH_KEYS = ['mouthSmileLeft', 'mouthSmileRight', 'mouthStretchLeft', 'mouthStretchRight']
PROT_KEYS = ['mouthFunnel', 'mouthPucker']
TALKERS = {
    'default': dict(rate=1, amp=1, width=1, protrusion=1, coart=1, jitter=0),
    't1': dict(rate=1.10, amp=1.15, width=1.10, protrusion=0.95, coart=1.15, jitter=0.10),
    't2': dict(rate=0.90, amp=0.85, width=0.90, protrusion=1.10, coart=0.85, jitter=0.08),
    't3': dict(rate=1.20, amp=0.90, width=1.05, protrusion=0.90, coart=1.25, jitter=0.15),
    't4': dict(rate=0.95, amp=1.10, width=0.88, protrusion=1.12, coart=0.75, jitter=0.12),
    'h1': dict(rate=1.05, amp=1.20, width=0.95, protrusion=1.15, coart=1.30, jitter=0.12),
    'h2': dict(rate=0.88, amp=0.80, width=1.15, protrusion=0.85, coart=0.70, jitter=0.15),
}
# V2 시점의 앱 표(지금 표). 렌더 궤적 재현과 비교에 쓴다. visemeShapes.js와 같아야 한다(selftest가 확인).
OLD_TABLE = {
    1: {'mouthClose': 0.35, 'mouthPressLeft': 0.22, 'mouthPressRight': 0.22, 'mouthRollLower': 0.12, 'mouthRollUpper': 0.12},
    2: {'jawOpen': 0.5, 'mouthLowerDownLeft': 0.12, 'mouthLowerDownRight': 0.12, 'mouthUpperUpLeft': 0.06, 'mouthUpperUpRight': 0.06},
    3: {'mouthSmileLeft': 0.45, 'mouthSmileRight': 0.45, 'mouthStretchLeft': 0.2, 'mouthStretchRight': 0.2, 'jawOpen': 0.1,
        'mouthUpperUpLeft': 0.08, 'mouthUpperUpRight': 0.08},
    4: {'mouthFunnel': 0.62, 'mouthPucker': 0.48, 'jawOpen': 0.05},
    5: {'jawOpen': 0.22, 'mouthFunnel': 0.06},
    6: {'jawOpen': 0.22, 'mouthUpperUpLeft': 0.1, 'mouthUpperUpRight': 0.1, 'mouthShrugUpper': 0.05},
    7: {'jawOpen': 0.22}, 8: {'jawOpen': 0.26},
    9: {'jawOpen': 0.16, 'mouthFunnel': 0.38, 'mouthPucker': 0.32},
    10: {'jawOpen': 0.18, 'mouthFunnel': 0.14, 'mouthSmileLeft': 0.12, 'mouthSmileRight': 0.12},
    11: {'mouthClose': 0.18, 'mouthPressLeft': 0.1, 'mouthPressRight': 0.1}, 12: {'jawOpen': 0.08}, 13: {'jawOpen': 0.1}, 14: {}, 15: {},
}
M32 = 0xffffffff


# ───────────────────────────── 하네스 궤적 재현 ─────────────────────────────
def _imul(a, b):
    return ((a & M32) * (b & M32)) & M32


def hash_seed(s):
    """talkers.hashSeed(FNV-1a). 입모양 번호·쉼표·영문만 들어가므로 charCodeAt = ord."""
    h = 0x811c9dc5
    for ch in str(s):
        h ^= ord(ch)
        h = _imul(h, 0x01000193)
    return h & M32


def unit_noise(seed, i):
    x = (seed ^ _imul(i + 1, 0x9e3779b1)) & M32
    x = _imul(x ^ (x >> 16), 0x85ebca6b)
    x = _imul(x ^ (x >> 13), 0xc2b2ae35)
    x = (x ^ (x >> 16)) & M32
    return (x / 0xffffffff) * 2 - 1


def _js_round(x):
    return math.floor(x + 0.5)


def talker_timing(frames, tk, tid, seed=0):
    """talkers.applyTalkerTiming."""
    if all(tk[k] == 1 for k in ('amp', 'width', 'protrusion', 'coart', 'rate')) and not tk['jitter']:
        return frames
    rate = tk['rate'] if tk['rate'] > 0 else 1
    s = hash_seed(f"{seed}|{tid}|{','.join(str(f['viseme']) for f in frames)}")
    out = []
    for i, f in enumerate(frames):
        o = dict(f)
        if isinstance(f.get('duration_ms'), (int, float)):
            o['duration_ms'] = max(16, _js_round((f['duration_ms'] / rate) * (1 + (tk['jitter'] or 0) * unit_noise(s, i))))
        if isinstance(f.get('transition_ms'), (int, float)):
            o['transition_ms'] = _js_round((f['transition_ms'] * tk['coart']) / rate)
        out.append(o)
    return out


def _ease(t):
    x = max(0.0, min(1.0, t))
    return 4 * x * x * x if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def _progress(elapsed, tr, dur, speed):
    """visemeTiming.transitionProgress."""
    if tr is None:
        return None
    s = speed if speed > 0 else 1
    cap = dur * 0.6 if (dur is not None and dur > 0) else tr
    return _ease(elapsed / (max(16, min(tr, cap)) / s))


def text_coeffs(frames, tid='default', speed=1.0, lead=400, tail=400, tk=None):
    """main.js renderText의 모프 궤적을 표 행의 선형 결합으로: C[이미지, 15]. 이미지 k = 눈금 2k 뒤 상태.
    모든 키가 같은 이징을 따르므로 궤적 = C @ T(T는 화자 배율을 곱한 표). 반환: C, [(입모양, t0, t1)](ms), 발화 구간(ms)."""
    import numpy as np
    tk = tk or TALKERS[tid]
    vis = talker_timing(frames, tk, tid)
    sched, t = [], lead
    for f in vis:
        ln = (f.get('duration_ms') or 0) / speed
        sched.append((f['viseme'], t, t + ln, f.get('transition_ms'), f.get('duration_ms')))
        t += ln
    end = t
    n_ticks = math.ceil((end + tail) / TICK_MS) + 1
    cur, frm = np.zeros(15), np.zeros(15)
    last, el, j = None, 0.0, 0
    rows = []
    for n in range(n_ticks):
        now = n * TICK_MS
        if now < lead:
            v, tr, dur = 15, None, None
        else:
            while j + 1 < len(sched) and sched[j + 1][1] <= now:
                j += 1
            v, _, _, tr, dur = sched[min(j, len(sched) - 1)]
        if last != v:
            last, frm, el = v, cur.copy(), 0.0
        else:
            el += TICK_MS
        e = _progress(el, tr, dur, speed)
        tgt = np.zeros(15)
        tgt[v - 1] = 1.0
        cur = cur + (tgt - cur) * LERP_TEXT if e is None else frm + (tgt - frm) * e
        if n % 2 == 0:
            rows.append(cur.copy())
    return np.array(rows), [(v, a, b) for v, a, b, _, _ in sched], (lead, end)


def scale_shape(shape, tk, v):
    """talkers.scaleShape."""
    co = tk['coart'] if v in (11, 12, 13) else 1
    out = {}
    for k, w in (shape or {}).items():
        s = co
        if k in AMP_KEYS:
            s *= tk['amp']
        elif k in WIDTH_KEYS:
            s *= tk['width']
        elif k in PROT_KEYS:
            s *= tk['protrusion']
        out[k] = max(0.0, min(1.0, w * s))
    return out


def table_matrix(table, tk, keys=KEYS):
    import numpy as np
    T = np.zeros((15, len(keys)))
    for v in VIS:
        for k, w in scale_shape(table.get(v) or table.get(str(v)) or {}, tk, v).items():
            if k in keys:
                T[v - 1, keys.index(k)] = w
    return T


def raw_inputs(names, rows, fps, keys=KEYS, rawmap=None):
    """main.js renderRaw(bsFrameRef 경로): 원본 계수를 LERP 34/s로 따라간 모프 값(이미지마다). 얼굴 없는 칸은 앞 값."""
    import numpy as np
    ix = {k: i for i, k in enumerate(names) if k and k[0] != '_'}
    dur = len(rows) / fps * 1000
    n_ticks = math.ceil(dur / TICK_MS)
    cur = np.zeros(len(keys))
    last, out = None, []
    for n in range(n_ticks):
        now = n * TICK_MS
        raw = None
        if 0 <= now < dur:
            idx = min(len(rows) - 1, int(math.floor(now / 1000 * fps)))
            raw = rows[idx] if rows[idx] is not None else last
            if rows[idx] is not None:
                last = rows[idx]
        if raw is not None:
            o = {k: raw[i] for k, i in ix.items()}
            if rawmap:
                o = map_raw(rawmap, o)
            tgt = np.array([o.get(k, 0.0) for k in keys])
            cur = cur + (tgt - cur) * LERP_RAW
        else:
            cur = cur * (1 - LERP_TEXT)
        if n % 2 == 0:
            out.append(cur.copy())
    return np.array(out)


def map_raw(spec, o):
    """main.js mapRaw와 같은 사상(원본 계수 → 아바타 모프)."""
    out = {k: v * (spec.get('gain', {}).get(k, 1)) for k, v in o.items()}
    for k, row in (spec.get('lin') or {}).items():
        x = row.get('_b', 0) + sum(c * o.get(j, 0) for j, c in row.items() if j != '_b')
        out[k] = max(0.0, min(1.0, x))
    return {k: max(0.0, min(1.0, v)) for k, v in out.items()}


# ───────────────────────────── poses ─────────────────────────────
JAW_GRID = [0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5]
CC_LIP = ['Mouth_Lips_Jaw_Adjust', 'V_Explosive', 'Mouth_Plosive', 'Mouth_Lips_Tight', 'V_Tight', 'Mouth_Lips_Part', 'Mouth_Lips_Open',
          'Mouth_Lips_Tuck', 'Mouth_Pucker', 'V_Tight_O', 'Mouth_Widen', 'V_Wide', 'Mouth_Bottom_Lip_Trans', 'Mouth_Top_Lip_Under']
RAND_MAX = {'jawOpen': .6, 'mouthClose': .6, 'press': .6, 'mouthRollLower': .5, 'mouthRollUpper': .5, 'mouthFunnel': .9,
            'mouthPucker': .9, 'smile': .7, 'stretch': .5, 'upperUp': .5, 'lowerDown': .5, 'mouthShrugUpper': .4, 'mouthShrugLower': .4}
HUMAN_MAX = {'jawOpen': .35, 'mouthClose': .3, 'press': .3, 'mouthRollLower': .2, 'mouthRollUpper': .2, 'mouthFunnel': .4,
             'mouthPucker': .5, 'smile': .25, 'stretch': .15, 'upperUp': .2, 'lowerDown': .2, 'mouthShrugUpper': .2, 'mouthShrugLower': .2}


def expand(ctrl):
    """조절 축 값(좌우 묶음) → 모프 이름 dict."""
    out = {}
    for k, v in ctrl.items():
        if k in PAIRS:
            for kk in PAIRS[k]:
                out[kk] = v
        else:
            out[k] = v
    return out


def cmd_poses(a):
    rng = random.Random(0)
    slim, orig = [], []
    for j in JAW_GRID:   # (a) 턱 × mouthClose
        for c in (0, .05, .1, .15, .2, .3, .4, .5, .6, .8, 1.0):
            slim.append({'_set': 'jaw_close', 'jawOpen': j, 'mouthClose': c})
    for j in JAW_GRID:   # (b) 압착·말아 넣기·으쓱과 턱
        for p in (.2, .4, .7):
            slim.append({'_set': 'jaw_press', 'jawOpen': j, **expand({'press': p})})
        for r in (.2, .4):
            slim.append({'_set': 'jaw_roll', 'jawOpen': j, 'mouthRollLower': r, 'mouthRollUpper': r})
        for c in (.2, .4):
            slim.append({'_set': 'jaw_close_press', 'jawOpen': j, 'mouthClose': c, **expand({'press': .3})})
        for s in (.2, .4):
            slim.append({'_set': 'jaw_shrugL', 'jawOpen': j, 'mouthShrugLower': s})
            slim.append({'_set': 'jaw_shrugU', 'jawOpen': j, 'mouthShrugUpper': s})
    for j in JAW_GRID:   # (c) 원본 GLB의 CC 입술 모프와 턱
        for m in CC_LIP:
            for w in (.3, .6, 1.0):
                orig.append({'_set': 'cc_' + m, 'jawOpen': j, m: w})
        for c in (0, .2, .5, 1.0):   # 원본과 슬림이 같은 반응인지
            orig.append({'_set': 'orig_jaw_close', 'jawOpen': j, 'mouthClose': c})
    for i in range(a.n_random):   # (d) 무작위 조합(절반은 드문드문 넓게, 절반은 사람 범위 근처 촘촘히)
        if i % 2 == 0:
            ctrl = {k: rng.uniform(0, mx) for k, mx in RAND_MAX.items() if rng.random() < 0.35}
        else:
            ctrl = {k: rng.uniform(0, mx) for k, mx in HUMAN_MAX.items()}
        slim.append({'_set': 'rand', **expand({k: round(v, 4) for k, v in ctrl.items()})})
    rng.shuffle(slim)
    rng.shuffle(orig)

    def jobs(poses, tag):
        out = []
        for k in range(0, len(poses), a.chunk):
            out.append({'id': f'pose_{tag}_{k // a.chunk:03d}', 'kind': 'poses', 'hold': a.hold, 'poses': poses[k:k + a.chunk]})
        return out
    js, jo = jobs(slim, 'slim'), jobs(orig, 'orig')
    json.dump(js, open(os.path.join(a.out, 'jobs_poses_slim.json'), 'w'))
    json.dump(jo, open(os.path.join(a.out, 'jobs_poses_orig.json'), 'w'))
    print(f'POSES slim={len(slim)} ({len(js)} jobs) orig={len(orig)} ({len(jo)} jobs) hold={a.hold}')


# ───────────────────────────── 순방향 사상(모프 → MediaPipe) ─────────────────────────────
LAGS = (0, 1, 2, 3, 5)      # MediaPipe VIDEO 모드는 랜드마크를 시간으로 다듬어(정지 자세 3장으로는 수렴하지 않음) 앞 이미지 입력을 함께 넣는다


def out_feats():
    import v2_avatar_validity as V
    return list(V.RSA_FEATS) + ['G']


def lagged(W):
    import numpy as np
    cols = []
    for l in LAGS:
        cols.append(W if l == 0 else np.vstack([np.repeat(W[:1], l, 0), W[:-l]]))
    return np.hstack(cols)


def ctrl_vec(ctrl):
    """조절 축 dict → KEYS 순서 벡터."""
    import numpy as np
    x = np.zeros(len(KEYS))
    for k, v in expand(ctrl).items():
        if k in KEYS:
            x[KEYS.index(k)] = v
    return x


def _series_Y(path):
    import numpy as np
    import v2_avatar_validity as V
    s = V.load_series(path)
    return np.stack([s['f'][k] for k in out_feats()], 1), s['valid']


def _explore_sets(sel):
    """탐색 절반에만 속한 문장 id와 탐색 절반 V13 클립(확인 절반과 겹치는 문장은 뺀다)."""
    halves = {}
    for e in sel['sentences']:
        halves.setdefault(e['sid'], set()).add(e['half'])
    sids = {s for s, h in halves.items() if h == {0}}
    spk_half = {s['spk']: s['half'] for s in sel['speakers']}
    clip_spk = {c['clip']: c['spk'] for c in sel['clips']}
    v13 = [c for c in sel['v13_clips'] if spk_half[clip_spk[c]] == 0]
    return sids, v13


def cmd_dataset(a):
    import numpy as np
    import v2_avatar_validity as V
    sel = json.load(open(a.sel, encoding='utf-8'))
    sids, v13 = _explore_sets(sel)
    Xs, Ys, src, grp = [], [], [], []

    def add(W, Y, ok, s, g):
        n = min(len(W), len(Y))
        X = lagged(W[:n])
        m = ok[:n] & np.all(np.isfinite(Y[:n]), 1)
        Xs.append(X[m]); Ys.append(Y[:n][m]); src.extend([s] * int(m.sum())); grp.extend([g] * int(m.sum()))
    # 정지 자세 스윕(슬림 GLB)
    for jp, bd in zip(a.pose_jobs, a.pose_bs):
        for j in json.load(open(jp)):
            p = os.path.join(bd, j['id'] + '.json')
            if not os.path.exists(p) or not j['id'].startswith('pose_slim'):
                continue
            Y, ok = _series_Y(p)
            W = np.repeat(np.array([ctrl_vec_raw(q) for q in j['poses']]), j['hold'], 0)
            add(W, Y, ok, 'pose', j['id'])
    # V2 탐색 문장 렌더(지금 표, 기본 얼굴·가상 화자)
    jobs = {}
    for p in a.v2_jobs:
        for j in json.load(open(p, encoding='utf-8')):
            jobs[j['id']] = j
    n_txt = 0
    for fn in sorted(os.listdir(a.v2_bs)):
        jid = fn[:-5]
        if not jid.startswith('txt_') or jid.split('_')[1] not in sids:
            continue
        j = jobs[jid]
        tk = TALKERS[j['talker']]
        Cm, _, _ = text_coeffs(j['frames'], j['talker'], j['speed'], tk=tk)
        Y, ok = _series_Y(os.path.join(a.v2_bs, fn))
        add(Cm @ table_matrix(OLD_TABLE, tk), Y, ok, 'text', jid.split('_')[1])
        n_txt += 1
    # V13 탐색 클립(실제 계수 → bsFrameRef 경로)
    for clip in v13:
        po, pr = os.path.join(a.real_bs, clip + '.json'), os.path.join(a.v13_bs, f'v13_{clip}.json')
        if not (os.path.exists(po) and os.path.exists(pr)):
            continue
        names, rows, fps = V.bs_frames_indexed(json.load(open(po, encoding='utf-8')))
        Y, ok = _series_Y(pr)
        add(raw_inputs(names, rows, fps), Y, ok, 'v13', clip)
    X, Y = np.concatenate(Xs), np.concatenate(Ys)
    np.savez_compressed(a.out, X=X, Y=Y, src=np.array(src), grp=np.array(grp))
    print(f'DATASET rows={len(X)} text_clips={n_txt} v13={len(v13)} by_src=' +
          json.dumps({s: int((np.array(src) == s).sum()) for s in ('pose', 'text', 'v13')}))


def ctrl_vec_raw(pose):
    """정지 자세 dict(모프 이름) → KEYS 벡터(_로 시작하는 키·모르는 모프는 뺀다)."""
    import numpy as np
    x = np.zeros(len(KEYS))
    for k, v in pose.items():
        if k in KEYS:
            x[KEYS.index(k)] = v
    return x


class FM:
    """순방향 사상: 지연 입력(KEYS × LAGS) → MediaPipe 특징(RSA 13 + G). 출력마다 표준화한 다층 퍼셉트론 묶음."""

    def __init__(self, models, xm, xs, ym, ys):
        self.models, self.xm, self.xs, self.ym, self.ys = models, xm, xs, ym, ys

    def predict(self, X):
        import numpy as np
        Z = (X - self.xm) / self.xs
        P = np.mean([m.predict(Z) for m in self.models], axis=0)
        return P * self.ys + self.ym

    def static(self, U):
        """정지 자세(행마다 KEYS 벡터) → 수렴한 MediaPipe 값."""
        import numpy as np
        U = np.atleast_2d(U)
        return self.predict(np.hstack([U] * len(LAGS)))


def cmd_fit(a):
    import pickle
    import numpy as np
    from sklearn.neural_network import MLPRegressor
    d = np.load(a.ds)
    X, Y, src, grp = d['X'], d['Y'], d['src'], d['grp']
    rng = np.random.default_rng(0)
    ug = np.unique(grp)
    test = set(rng.choice(ug, size=max(1, len(ug) // 6), replace=False))
    te = np.array([g in test for g in grp])
    keep = (~te) & ((src != 'text') | (rng.random(len(X)) < a.text_frac))
    xm, xs = X[keep].mean(0), X[keep].std(0) + 1e-3
    ym, ys = Y[keep].mean(0), Y[keep].std(0) + 1e-4
    models = []
    for seed in range(a.ensemble):
        m = MLPRegressor(hidden_layer_sizes=(192, 192), activation='relu', alpha=1e-4, batch_size=512, learning_rate_init=1e-3,
                         max_iter=a.epochs, early_stopping=True, validation_fraction=0.1, n_iter_no_change=8, random_state=seed)
        m.fit((X[keep] - xm) / xs, (Y[keep] - ym) / ys)
        models.append(m)
        print(f'FIT member {seed} iters={m.n_iter_} loss={m.loss_:.4f}', flush=True)
    import v15_calibrate as _self   # __main__으로 돌려도 피클이 모듈 이름으로 남게
    fm = _self.FM(models, xm, xs, ym, ys)
    P = fm.predict(X[te])
    rep = {}
    for j, name in enumerate(out_feats()):
        rep[name] = {}
        for s in ('pose', 'text', 'v13'):
            mk = src[te] == s
            if mk.sum() > 50 and Y[te][mk, j].std() > 1e-6:
                rep[name][s] = [round(float(np.corrcoef(P[mk, j], Y[te][mk, j])[0, 1]), 3),
                                round(float(np.sqrt(np.mean((P[mk, j] - Y[te][mk, j]) ** 2))), 4), round(float(Y[te][mk, j].std()), 4)]
        print('FIT', name, json.dumps(rep[name]))
    pickle.dump(fm, open(a.out, 'wb'))
    json.dump(rep, open(a.out + '.report.json', 'w'), indent=1)
    print('FIT_OK', a.out)


# ───────────────────────────── 실제 화자(탐색 절반) 분포 ─────────────────────────────
def human_profiles(sel, align_path, real_bs, half):
    """V2 분석과 같은 규칙으로 절반 하나의 실제 화자 프로필과 클립 기록."""
    import v2_avatar_validity as V
    align = {}
    for l in open(align_path, encoding='utf-8'):
        r = json.loads(l)
        align[r['key']] = r
    hs = {s['spk']: s['half'] for s in sel['speakers']}
    rec, rate = {}, {}
    for c in sel['clips']:
        if hs[c['spk']] != half:
            continue
        r = align.get('real:' + c['clip'])
        bp = os.path.join(real_bs, c['clip'] + '.json')
        if r is None or 'error' in r or not os.path.exists(bp):
            continue
        segs, span = V.segments_from_align(r, V.LAG_S)
        x, _ = V.clip_record(V.load_series(bp), segs, span)
        if x:
            rec.setdefault(c['spk'], []).append(x)
            rate.setdefault(c['spk'], []).append(r['n_syl'] / max(1e-3, r['t_last'] - r['t_first']))
    prof = {s: V.profile(v) for s, v in rec.items()}
    return prof, rec, rate


def human_stats(prof, rec):
    """목표: 무리별 중앙값. amp(바닥값 뺀 J·R·S·C·G), raw(RSA 특징·G의 무리 평균 원값), 특징별 바닥값."""
    import numpy as np
    import v2_avatar_validity as V
    feats = out_feats()
    st = {'amp': {}, 'raw': {}, 'floor_raw': {}}
    floors = {}
    for s, rs in rec.items():
        floors[s] = {f: float(np.nanpercentile(np.concatenate([r['speech'][f] for r in rs]), 5)) for f in feats if f in rs[0]['speech']}
    for g in GROUPS:
        st['amp'][g] = {c: float(np.median([p['amp'][g][c] for p in prof.values() if p and g in p['amp']])) for c in ('J', 'R', 'S', 'C', 'G', 'A')}
        st['raw'][g] = {}
        for f in feats:
            vals = []
            for s, rs in rec.items():
                xs = [v[f] for r in rs for gg, v in r['segs'] if gg == g and np.isfinite(v[f])]
                if len(xs) >= V.MIN_SEG:
                    vals.append(np.mean(xs))
            st['raw'][g][f] = float(np.median(vals))
    for f in feats:
        st['floor_raw'][f] = float(np.median([floors[s][f] for s in floors if f in floors[s]]))
    return st


# ───────────────────────────── 시뮬레이션 ─────────────────────────────
class Sim:
    """탐색(또는 다른) 문장 렌더를 순방향 사상으로 예측하고 V2 지표를 계산한다."""

    def __init__(self, fm, items, resid=None):
        # items: [(sid, frames, talker, speed)]. resid: [15, 특징] 입모양별 보정(실제 렌더 − 시뮬레이션 무리 평균). 궤적 계수로 섞어 더한다.
        self.fm = fm
        self.resid = resid
        self.items = []
        for sid, frames, tid, speed in items:
            Cm, sched, sp = text_coeffs(frames, tid, speed)
            self.items.append({'sid': sid, 'C': Cm, 'tid': tid, 'speed': speed,
                               'segs': [(v, t0 / 1000.0, t1 / 1000.0) for v, t0, t1 in sched if v in GROUPS],
                               'span': (sp[0] / 1000.0, sp[1] / 1000.0)})

    def series(self, table, which=None):
        import numpy as np
        out = []
        idx = [k for k, it in enumerate(self.items) if which is None or which(it)]
        mats = {}
        Xs, lens = [], []
        for k in idx:
            it = self.items[k]
            T = mats.get(it['tid'])
            if T is None:
                T = mats[it['tid']] = table_matrix(table, TALKERS[it['tid']])
            X = lagged(it['C'] @ T)
            Xs.append(X); lens.append(len(X))
        Y = self.fm.predict(np.vstack(Xs)) if Xs else np.zeros((0, len(out_feats())))
        o = 0
        feats = out_feats()
        for k, n in zip(idx, lens):
            y = Y[o:o + n]; o += n
            if self.resid is not None:
                y = y + self.items[k]['C'] @ self.resid
            f = {name: y[:, j] for j, name in enumerate(feats)}
            f['J'] = f['jawOpen']; f['R'] = f['mouthFunnel'] + f['mouthPucker']; f['S'] = f['smile'] + f['stretch']; f['C'] = f['mouthClose']
            out.append((self.items[k], {'t': np.arange(n) / 30.0, 'valid': np.ones(n, bool), 'f': f}))
        return out

    def profiles(self, table):
        import v2_avatar_validity as V
        cond = {}
        for it, ser in self.series(table):
            rec, _ = V.clip_record(ser, it['segs'], it['span'])
            if rec:
                rec['sid'] = it['sid']
                cond.setdefault(f"{it['tid']}_{it['speed']}", []).append(rec)
        return {c: V.profile(v) for c, v in cond.items()}, cond


def v2_metrics(real_prof, cond_prof):
    import v2_avatar_validity as V
    rsa = V.rsa_block(real_prof, cond_prof)
    amp = V.amp_block(real_prof, cond_prof)
    leg = {c: V.legibility(real_prof, p) for c, p in cond_prof.items()}
    return rsa, amp, leg


# ───────────────────────────── 6.3 구별성 ─────────────────────────────
def distinctiveness(records):
    """조건 하나의 클립 기록(rec['sid'] 필요) → 무리별 재현율. 구간 값(RSA 13특징)을 조건 전체 평균·표준편차로 z 점수화하고,
    자기 문장을 뺀 나머지 구간의 무리 중심 중 가장 가까운 것으로 분류한다(사전 등록 6.3절)."""
    import numpy as np
    import v2_avatar_validity as V
    rows = [(r['sid'], g, [v[k] for k in V.RSA_FEATS]) for r in records for g, v in r['segs']]
    X = np.array([x for _, _, x in rows], dtype=float)
    mu, sd = np.nanmean(X, 0), np.nanstd(X, 0)
    ok = sd > 1e-4
    Z = np.where(ok, (X - mu) / np.where(ok, sd, 1), 0.0)
    Z = np.nan_to_num(Z)
    sids = np.array([s for s, _, _ in rows]); gs = np.array([g for _, g, _ in rows])
    # 문장별 무리 합·개수로 '자기 문장 뺀 중심'을 빠르게 계산
    G = list(GROUPS)
    tot = np.zeros((len(G), Z.shape[1])); cnt = np.zeros(len(G))
    per = {}
    for i in range(len(rows)):
        gi = G.index(gs[i])
        tot[gi] += Z[i]; cnt[gi] += 1
        d = per.setdefault(sids[i], [np.zeros((len(G), Z.shape[1])), np.zeros(len(G))])
        d[0][gi] += Z[i]; d[1][gi] += 1
    hit = {g: [0, 0] for g in G}
    for i in range(len(rows)):
        ps, pc = per[sids[i]]
        c = cnt - pc
        cen = (tot - ps) / np.where(c > 0, c, 1)[:, None]
        dist = np.sqrt(((cen - Z[i]) ** 2).sum(1))
        dist[c <= 0] = np.inf
        pred = G[int(np.argmin(dist))]
        hit[gs[i]][1] += 1
        hit[gs[i]][0] += int(pred == gs[i])
    return {g: (round(h / n, 4) if n else None, n) for g, (h, n) in hit.items()}


# ───────────────────────────── 판정 묶음(사전 등록 6절) ─────────────────────────────
def render_records(sel, renders, render_bs, half, sids=None):
    """렌더 폴더의 텍스트 렌더 → {조건: [클립 기록(sid 포함)]}. 절반은 문장 id로 가른다(V2 analyze와 같은 규칙)."""
    import v2_avatar_validity as V
    sid_half = {}
    for e in sel['sentences']:
        sid_half.setdefault(e['sid'], set()).add(e['half'])
    out = {}
    for fn in sorted(os.listdir(renders)):
        if not fn.endswith('.sched.json') or not fn.startswith('txt_'):
            continue
        jid = fn[:-len('.sched.json')]
        _, s_id, cond = jid.split('_', 2)
        if half not in sid_half.get(s_id, ()) or (sids is not None and s_id not in sids):
            continue
        bp = os.path.join(render_bs, jid + '.json')
        if not os.path.exists(bp):
            continue
        sch = json.load(open(os.path.join(renders, fn), encoding='utf-8'))
        segs, span = V.segments_from_schedule(sch)
        rec, _ = V.clip_record(V.load_series(bp), segs, span)
        if rec:
            rec['sid'] = s_id
            out.setdefault(cond, []).append(rec)
    return out


def cmd_evaluate(a):
    """새 표 렌더와 지금 표 렌더(V2)를 같은 문장·같은 절반에서 비교하고 사전 등록 6절 기준으로 판정한다."""
    import numpy as np
    import v2_avatar_validity as V
    sel = json.load(open(a.sel, encoding='utf-8'))
    real_prof, _, _ = human_profiles(sel, a.align, a.real_bs, a.half)
    new = render_records(sel, a.renders, a.render_bs, a.half)
    sids = {r['sid'] for c in ('default_1.0', 'default_2.0') for r in new.get(c, [])}
    old = render_records(sel, a.old_renders, a.old_bs, a.half, sids=sids)
    res = {'half': a.half, 'n_real': len(real_prof), 'n_clips': {c: len(v) for c, v in new.items()},
           'n_clips_old': {c: len(v) for c, v in old.items()}}
    for tag, recs in (('new', new), ('old', old)):
        prof = {c: V.profile(v) for c, v in recs.items()}
        rsa, amp, leg = v2_metrics(real_prof, prof)
        res[tag] = {c: {'rho': rsa['cond'][c]['rho'], 'rho_pass': rsa['cond'][c].get('pass'), 'amp_n_in': amp['cond'][c]['n_in'],
                        'amp_pass': amp['cond'][c]['pass'], 'per_channel_in': amp['cond'][c]['per_channel_in'],
                        'amp_groups': {g: (r.get('A') or {}).get('x') for g, r in amp['cond'][c]['groups'].items()},
                        'amp_pct': {g: (r.get('A') or {}).get('pct') for g, r in amp['cond'][c]['groups'].items()},
                        'legibility': leg[c], 'pair_dev': rsa['cond'][c].get('pair_dev', [])[:6],
                        'distinct': distinctiveness(recs[c])} for c in sorted(prof)}
        res['loo'] = rsa['loo']
        res['amp_human_loo'] = amp.get('human_loo')
    # 판정(6.1~6.3)
    n, o = res['new'], res['old']
    v = {'rsa': bool(n['default_1.0']['rho'] is not None and n['default_1.0']['rho'] >= res['loo']['p10']),
         'amp': bool(n['default_2.0']['amp_n_in'] >= V.AMP_N_PASS)}
    for sp in ('1.0', '2.0'):
        c = f'default_{sp}'
        lg = n[c]['legibility']
        v[f'bilabial_{sp}'] = bool((lg.get('bilabial_closure_rate') or 0) >= 0.95)
        v[f'rounded_{sp}'] = bool((lg.get('rounded_R_in_range_rate') or 0) >= 0.80)
        worse = {g: (n[c]['distinct'][g][0], o[c]['distinct'][g][0]) for g in GROUPS
                 if n[c]['distinct'][g][0] is not None and o[c]['distinct'][g][0] is not None
                 and n[c]['distinct'][g][0] < o[c]['distinct'][g][0] - 0.05}
        v[f'distinct_{sp}'] = not worse
        res[f'distinct_worse_{sp}'] = worse
    v['all'] = all(v.values())
    res['verdict'] = v
    json.dump(res, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=str)
    print('EVALUATE', json.dumps(v), 'rho', n['default_1.0']['rho'], 'p10', res['loo']['p10'], 'amp2', n['default_2.0']['amp_n_in'])


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('poses')
    s.add_argument('--n-random', type=int, default=3600)
    s.add_argument('--chunk', type=int, default=150)
    s.add_argument('--hold', type=int, default=3)
    s.add_argument('--out', required=True)
    s = sub.add_parser('dataset')
    s.add_argument('--sel', required=True)
    s.add_argument('--pose-jobs', nargs='*', default=[])
    s.add_argument('--pose-bs', nargs='*', default=[])
    s.add_argument('--v2-jobs', nargs='+', required=True)
    s.add_argument('--v2-bs', required=True)
    s.add_argument('--real-bs', required=True)
    s.add_argument('--v13-bs', required=True)
    s.add_argument('--out', required=True)
    s = sub.add_parser('fit')
    s.add_argument('--ds', required=True)
    s.add_argument('--text-frac', type=float, default=0.5)
    s.add_argument('--ensemble', type=int, default=3)
    s.add_argument('--epochs', type=int, default=60)
    s.add_argument('--out', required=True)
    s = sub.add_parser('evaluate')
    s.add_argument('--sel', required=True)
    s.add_argument('--align', required=True)
    s.add_argument('--real-bs', required=True)
    s.add_argument('--renders', required=True)
    s.add_argument('--render-bs', required=True)
    s.add_argument('--old-renders', required=True)
    s.add_argument('--old-bs', required=True)
    s.add_argument('--half', type=int, required=True)
    s.add_argument('--out', required=True)
    a = ap.parse_args()
    {'poses': cmd_poses, 'dataset': cmd_dataset, 'fit': cmd_fit, 'evaluate': cmd_evaluate}[a.cmd](a)


if __name__ == '__main__':
    main()
