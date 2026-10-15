"""V3 간이판: 538 문맥 평균 궤적 표(docs/avatar-v3-2026-10.md, 사전 등록).

규칙 엔진의 입모양 프레임(타이밍 그대로) → 30fps 사람 MediaPipe 계수 13채널(rigMap 입력과 같은 좌우 평균) → 앱 bsFrameRef 경로(rigMap, LERP 34/s).
표의 값은 (무리, 구간 칸, 앞 모음 갈래, 뒤 모음 갈래)마다 538 실제 구간 칸들의 계수 평균이고, 칸마다 20개 이상 구간·5명 이상 화자일 때만 남긴다(집계 값).

  select   (맥) 확인 화자(V2에 없는 538 전문가 화자) 클립 고르기             → sel_confirm.json, items_confirm.jsonl
  dataset  (맥) V2 실제 클립(MediaPipe·정렬) → 구간 칸 평균 자료             → cells.pkl
  fit      (맥) 칸 자료 → 표(JSON, 화자 절반 선택 가능)                        → table.json
  human    (맥) 렌더 없이 사람 공간에서 V2 지표(다른 절반의 실제 정렬 시각)
  jobs     (맥) 렌더 작업(지금 표·V15 표·V3)                                   → jobs.json
  classifier (맥) 탐색 75명 실제 구간으로 무리 판독기 학습                      → clf.pkl
  evaluate (맥) 렌더 추출 → V2 지표·가독성(사전 등록 6절)
  selftest   파이썬·JS 구현 일치용 기준 출력
538 원자료와 클립별 파생 파일은 liplab-lab/data/ 아래에만 둔다. 저장소에는 표(집계)와 집계 수치만 남긴다.
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

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# 출력 채널(rigMap 입력 순서와 같다). 좌우 짝은 평균.
CH = ['jawOpen', 'mouthClose', 'mouthFunnel', 'mouthPucker', 'smile', 'stretch', 'upperUp', 'lowerDown', 'press',
      'mouthRollLower', 'mouthRollUpper', 'mouthShrugLower', 'mouthShrugUpper']
PAIR_OUT = {'smile': 'mouthSmile', 'stretch': 'mouthStretch', 'upperUp': 'mouthUpperUp', 'lowerDown': 'mouthLowerDown', 'press': 'mouthPress'}
# 이득을 함께 받는 채널 무리
GAIN_GROUPS = {'open': ['jawOpen', 'upperUp', 'lowerDown'], 'round': ['mouthFunnel', 'mouthPucker'], 'width': ['smile', 'stretch'],
               'close': ['mouthClose', 'press', 'mouthRollLower', 'mouthRollUpper', 'mouthShrugLower', 'mouthShrugUpper']}
VOWEL_CLASS = {2: 2, 3: 3, 4: 4, 5: 5, 9: 4}
BREAK = (14, 15)
NB = 3                 # 구간 칸 수
REST_SPAN = 1.0        # 쉼 구간의 칸은 발화에 붙은 쪽 1초 안에
MIN_SEG, MIN_SPK = 20, 5
LAG_S = -0.066


# ───────────────────────────── 표 모델(앱 lib/visemeV3.js와 같아야 한다) ─────────────────────────────
def pad_segments(segs):
    """[(입모양, t0, t1)](초) → 앞뒤 쉼 구간을 붙인 목록. 15(중립)는 쉼으로 본다."""
    segs = [(14 if v == 15 else v, a, b) for v, a, b in segs]
    return [(14, segs[0][1] - 1e3, segs[0][1])] + segs + [(14, segs[-1][2], segs[-1][2] + 1e3)]


def contexts(vs):
    """입모양 열 → [(앞 모음 갈래, 뒤 모음 갈래)]. 쉼(14·15)을 넘지 않는다. 없으면 0."""
    out = []
    for i in range(len(vs)):
        p = n = 0
        for j in range(i - 1, -1, -1):
            if vs[j] in BREAK:
                break
            if vs[j] in VOWEL_CLASS:
                p = VOWEL_CLASS[vs[j]]
                break
        for j in range(i + 1, len(vs)):
            if vs[j] in BREAK:
                break
            if vs[j] in VOWEL_CLASS:
                n = VOWEL_CLASS[vs[j]]
                break
        out.append((p, n))
    return out


def seg_window(i, n, t0, t1):
    """칸을 놓을 범위. 앞뒤에 붙인 쉼 구간은 발화에 붙은 쪽 REST_SPAN 안으로."""
    if i == 0:
        return t1 - REST_SPAN, t1
    if i == n - 1:
        return t0, t0 + REST_SPAN
    return t0, t1


def cell_keys(g, b, p, n):
    return {'full': f'{g}|{b}|{p}|{n}', 'n': f'{g}|{b}|*|{n}', 'p': f'{g}|{b}|{p}|*', 'base': f'{g}|{b}|*|*'}


def lookup(cells, g, b, p, n, mode):
    k = cell_keys(g, b, p, n)
    base = cells.get(k['base'])
    if base is None:
        base = cells.get(f'14|{b}|*|*') or cells['14|1|*|*']
    if mode == 'base':
        return base
    if mode == 'full' and k['full'] in cells:
        return cells[k['full']]
    a, c = cells.get(k['n']), cells.get(k['p'])
    if a is not None and c is not None:
        return [x + y - z for x, y, z in zip(a, c, base)]
    return a if a is not None else (c if c is not None else base)


def anchors(segs, cells, mode):
    """앞뒤 쉼을 붙인 구간 → [(시각, 13채널 값)], 시각순."""
    vs = [v for v, _, _ in segs]
    cx = contexts(vs)
    out = []
    for i, ((v, t0, t1), (p, n)) in enumerate(zip(segs, cx)):
        a, b_ = seg_window(i, len(segs), t0, t1)
        for b in range(NB):
            out.append((a + (b + 0.5) / NB * (b_ - a), lookup(cells, v, b, p, n, mode)))
    out.sort(key=lambda x: x[0])
    return out


def predict_series(model, segs, times):
    """model: 표 JSON. segs: 실제 또는 재생 일정 구간(초, 쉼 붙이기 전). times: 표본 시각(초) → [len, 13]."""
    import numpy as np
    A = anchors(pad_segments(segs), model['cells'], model['mode'])
    at = np.array([a for a, _ in A])
    av = np.array([v for _, v in A], dtype=float)
    Y = np.stack([np.interp(times, at, av[:, j]) for j in range(len(CH))], 1)
    mu = np.array(model['mu'])
    g = np.array([model['gain'][grp] for grp in channel_gain_groups()])
    Y = mu + (Y - mu) * g
    return np.clip(Y, 0.0, 1.0)


def channel_gain_groups():
    inv = {c: grp for grp, cs in GAIN_GROUPS.items() for c in cs}
    return [inv[c] for c in CH]


def schedule_segments(frames, speed=1.0, lead_ms=400):
    """엔진 프레임 → 재생 일정 구간(초). 하네스 renderText와 같은 일정(applyTalkerTiming·동시조음 없음, 기본 얼굴)."""
    segs, t = [], lead_ms
    for f in frames:
        ln = (f.get('duration_ms') or 0) / speed
        segs.append((f['viseme'], t / 1000.0, (t + ln) / 1000.0))
        t += ln
    return segs, (lead_ms / 1000.0, t / 1000.0)


def frames_to_coeffs(model, frames, speed=1.0, lead_ms=400, tail_ms=400, fps=30):
    """엔진 프레임 → 30fps 계수(이름 → 값) 목록. 0번 표본은 재생 시각 0(앞 쉼 시작)."""
    import numpy as np
    segs, (s0, s1) = schedule_segments(frames, speed, lead_ms)
    segs = [s for s in segs if s[2] > s[1]]
    n = int(math.ceil((s1 + tail_ms / 1000.0) * fps))
    Y = predict_series(model, segs, np.arange(n) / fps)
    return [coeff_obj(y) for y in Y]


def coeff_obj(y):
    o = {}
    for c, v in zip(CH, y):
        v = round(float(v), 4)
        if c in PAIR_OUT:
            o[PAIR_OUT[c] + 'Left'] = v
            o[PAIR_OUT[c] + 'Right'] = v
        else:
            o[c] = v
    return o


# ───────────────────────────── select(확인 화자) ─────────────────────────────
HANGUL = re.compile(r'[가-힣]')
ALLOWED = re.compile(r'^[가-힣\s.,?!~\'"·…]+$')
CLIP_RE = re.compile(r'_([CE]\d+)_([A-Z])_(\d+)_\d+$')


def cmd_select(a):
    import v2_avatar_validity as V
    v2 = json.load(open(a.v2_sel, encoding='utf-8'))
    v2_spk = {s['spk'] for s in v2['speakers']}
    v2_person = {CLIP_RE.search(c['clip']).group(1) for c in v2['clips']}
    per = {}
    seen = set()
    for root in a.root:
        for line in open(os.path.join(root, 'manifest.tsv'), encoding='utf-8'):
            p = line.rstrip('\n').split('\t')
            if len(p) < 3 or p[0].startswith('#'):
                continue
            clip, spk, text = os.path.splitext(p[0])[0], p[1], unicodedata.normalize('NFC', p[2]).strip()
            m = CLIP_RE.search(clip)
            if not m or m.group(2) != 'A' or clip in seen:
                continue
            if spk in v2_spk or m.group(1) in v2_person:
                continue
            mp4 = next((x for x in (os.path.join(root, 'mp4', clip + '.mp4'), os.path.join(root, 'clips', clip + '.mp4')) if os.path.exists(x)), None)
            wav = mp4[:-4] + '.wav' if mp4 else None
            if not mp4 or not os.path.exists(wav):
                continue
            seen.add(clip)
            per.setdefault(spk, []).append({'clip': clip, 'spk': spk, 'person': m.group(1), 'text': text, 'mp4': mp4, 'wav': wav})
    rng = random.Random(0)
    clips, spk_rows = [], []
    for spk in sorted(per):
        rows = sorted(per[spk], key=lambda r: r['clip'])
        rng.shuffle(rows)
        keep = []
        for r in rows:
            nh = len(HANGUL.findall(r['text']))
            if 4 <= nh <= 40 and ALLOWED.match(r['text']):
                keep.append(r)
            if len(keep) >= a.per_spk:
                break
        for k, r in enumerate(keep):
            r.update(rank=k, sid=V.sid(r['text']), n_hangul=len(HANGUL.findall(r['text'])))
            clips.append(r)
        spk_rows.append({'spk': spk, 'person': keep[0]['person'] if keep else None, 'n': len(keep)})
    sent = {}
    for r in clips:
        e = sent.setdefault(r['sid'], {'sid': r['sid'], 'text': r['text'], 'default': False})
        if r['rank'] < a.n_default:
            e['default'] = True
    out = {'created': a.stamp, 'per_spk': a.per_spk, 'n_default': a.n_default, 'speakers': spk_rows, 'clips': clips,
           'sentences': sorted(sent.values(), key=lambda e: e['sid'])}
    json.dump(out, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    with open(a.items, 'w', encoding='utf-8') as fo:
        for r in clips:
            fo.write(json.dumps({'key': 'real:' + r['clip'], 'text': r['text'], 'audio': f"clips/{r['clip']}.wav"}, ensure_ascii=False) + '\n')
    h = hashlib.sha256(open(a.out, 'rb').read()).hexdigest()
    print(f"SELECT speakers={len(spk_rows)} clips={len(clips)} default_sentences={sum(e['default'] for e in sent.values())} "
          f"sha256={h}")
    for s in spk_rows:
        print('  ', s)


# ───────────────────────────── dataset / fit ─────────────────────────────
def real_segments(row):
    """정렬 결과 → [(입모양, t0, t1)] 영상 시각(V2 segments_from_align과 같은 규칙이지만 모든 입모양을 남긴다)."""
    vis, st = row['visemes'], row['starts']
    keep = [i for i, s in enumerate(st) if s is not None]
    segs = []
    for n_, i in enumerate(keep):
        t0 = st[i]
        t1 = st[keep[n_ + 1]] if n_ + 1 < len(keep) else row['t_last']
        if t1 > t0:
            segs.append((vis[i], t0 + LAG_S, t1 + LAG_S))
    return segs


def cmd_dataset(a):
    """클립마다 구간 칸의 계수 평균과 열쇠. 칸 평균은 그 칸에 든 얼굴이 잡힌 프레임 평균이다."""
    import pickle
    import numpy as np
    import v2_avatar_validity as V
    sel = json.load(open(a.sel, encoding='utf-8'))
    align = {}
    for l in open(a.align, encoding='utf-8'):
        r = json.loads(l)
        align[r['key']] = r
    hs = {s['spk']: s['half'] for s in sel['speakers']}
    rows, clips = [], []
    for c in sel['clips']:
        r = align.get('real:' + c['clip'])
        bp = os.path.join(a.real_bs, c['clip'] + '.json')
        if r is None or 'error' in r or not os.path.exists(bp):
            continue
        ser = V.load_series(bp)
        Y = np.stack([ser['f'][k] for k in CH], 1)
        ok = ser['valid'] & np.all(np.isfinite(Y), 1)
        t = ser['t']
        segs = pad_segments(real_segments(r))
        cx = contexts([v for v, _, _ in segs])
        for i, ((v, t0, t1), (p, n)) in enumerate(zip(segs, cx)):
            lo_, hi_ = seg_window(i, len(segs), t0, t1)
            for b in range(NB):
                lo, hi = lo_ + b / NB * (hi_ - lo_), lo_ + (b + 1) / NB * (hi_ - lo_)
                m = ok & (t >= lo) & (t < hi)
                if m.any():
                    rows.append((c['spk'], hs[c['spk']], c['clip'], v, b, p, n, Y[m].mean(0)))
        clips.append({'clip': c['clip'], 'spk': c['spk'], 'half': hs[c['spk']], 'segs': real_segments(r),
                      'span': (r['t_first'] + LAG_S, r['t_last'] + LAG_S)})
    pickle.dump({'rows': rows, 'clips': clips}, open(a.out, 'wb'))
    print(f'DATASET cells_rows={len(rows)} clips={len(clips)}')


def fit_table(rows, halves=(0, 1), mode='add', gain=None, min_seg=MIN_SEG, min_spk=MIN_SPK):
    import numpy as np
    acc = {}
    for spk, h, clip, v, b, p, n, y in rows:
        if h not in halves:
            continue
        g = 14 if v == 15 else v
        for key in cell_keys(g, b, p, n).values():
            e = acc.setdefault(key, [np.zeros(len(CH)), 0, set()])
            e[0] += y
            e[1] += 1
            e[2].add(spk)
    cells = {k: [round(float(x), 4) for x in e[0] / e[1]] for k, e in acc.items() if e[1] >= min_seg and len(e[2]) >= min_spk}
    base = [v for k, v in cells.items() if k.endswith('|*|*')]
    mu = [round(float(x), 4) for x in np.mean(base, 0)]
    gain = gain or {g: 1.0 for g in GAIN_GROUPS}
    return {'version': 1, 'mode': mode, 'nb': NB, 'channels': CH, 'gain': gain, 'mu': mu, 'cells': dict(sorted(cells.items())),
            'min_seg': min_seg, 'min_spk': min_spk, 'halves': list(halves)}


def table_sha(model):
    s = json.dumps({k: model[k] for k in ('mode', 'nb', 'channels', 'gain', 'mu', 'cells')}, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(s.encode()).hexdigest()


def cmd_fit(a):
    import pickle
    d = pickle.load(open(a.data, 'rb'))
    gain = json.loads(a.gain) if a.gain else None
    halves = tuple(int(x) for x in a.halves.split(','))
    m = fit_table(d['rows'], halves, a.mode, gain)
    m['sha256'] = table_sha(m)
    json.dump(m, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print(f"FIT cells={len(m['cells'])} mode={m['mode']} halves={halves} gain={m['gain']} sha256={m['sha256']} bytes={os.path.getsize(a.out)}")


# ───────────────────────────── 사람 공간 점검(렌더 없음) ─────────────────────────────
def _ser(times, Y):
    import numpy as np
    f = {k: Y[:, j] for j, k in enumerate(CH)}
    f['J'] = f['jawOpen']; f['R'] = f['mouthFunnel'] + f['mouthPucker']; f['S'] = f['smile'] + f['stretch']; f['C'] = f['mouthClose']
    f['G'] = np.full(len(Y), np.nan)
    return {'t': times, 'valid': np.ones(len(Y), bool), 'f': f}


def cmd_human(a):
    import pickle
    import numpy as np
    import v2_avatar_validity as V
    import v15_calibrate as C
    d = pickle.load(open(a.data, 'rb'))
    sel = json.load(open(a.sel, encoding='utf-8'))
    res = {}
    for tr, te in ((0, 1), (1, 0)):
        prof, _, _ = C.human_profiles(sel, a.align, a.real_bs, te)
        for mode in a.modes.split(','):
            for gs in a.gains.split(';'):
                gain = {g: float(x) for g, x in zip(GAIN_GROUPS, gs.split(','))}
                m = fit_table(d['rows'], (tr,), mode, gain)
                recs = []
                for c in d['clips']:
                    if c['half'] != te:
                        continue
                    n = int(math.ceil((c['span'][1] + 0.5) * 30))
                    times = np.arange(n) / 30.0
                    Y = predict_series(m, c['segs'], times)
                    segs = [(v, t0, t1) for v, t0, t1 in c['segs'] if v in V.GROUPS]
                    x, _ = V.clip_record(_ser(times, Y), segs, c['span'])
                    if x:
                        recs.append(x)
                cp = {'m': V.profile(recs)}
                rs, am = V.rsa_block(prof, cp), V.amp_block(prof, cp)
                key = f'{tr}->{te} {mode} {gs}'
                res[key] = {'rho': rs['cond']['m']['rho'], 'p10': rs['loo']['p10'], 'amp_n_in': am['cond']['m']['n_in'],
                            'pctA': {g: (am['cond']['m']['groups'][g].get('A') or {}).get('pct') for g in V.GROUPS},
                            'per_channel_in': am['cond']['m']['per_channel_in']}
                print('HUMAN', key, json.dumps(res[key]), flush=True)
    if a.out:
        json.dump(res, open(a.out, 'w'), indent=1)


# ───────────────────────────── jobs ─────────────────────────────
def cmd_jobs(a):
    """렌더 작업. 조건마다 같은 문장. cond: v1(하네스에 빌드된 지금 표), v15(표 주입), v3:<표 이름>(V3 표 주입), v3app(앱 모듈 표)."""
    sys.path.insert(0, os.path.abspath(a.backend))
    import engine
    sel = json.load(open(a.sel, encoding='utf-8'))
    sents = [e for e in sel['sentences'] if e.get('default')]
    if a.half is not None:
        sents = [e for e in sents if e.get('half') == a.half]
    jobs = []
    for e in sents:
        fr = asyncio.run(engine.text_to_visemes(unicodedata.normalize('NFC', e['text']).strip()))
        for cond in a.cond.split(','):
            for sp in a.speeds:
                j = {'id': f"txt_{e['sid']}_{cond.replace(':', '-')}_{sp}", 'kind': 'text', 'sid': e['sid'], 'talker': 'default', 'speed': sp,
                     'frames': fr}
                if cond == 'v15':
                    j['table'] = 'v15'
                elif cond.startswith('v3:'):
                    j['v3'] = cond[3:]
                elif cond == 'v3app':
                    j['v3'] = 'app'
                jobs.append(j)
    uniq = {}
    for j in jobs:
        uniq.setdefault(j['id'], j)
    jobs = list(uniq.values())
    json.dump(jobs, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False)
    n_ms = sum(sum(f['duration_ms'] for f in j['frames']) / j['speed'] for j in jobs)
    print(f'JOBS {len(jobs)} sentences={len(sents)} engine_seconds≈{n_ms / 1000:.0f}')


# ───────────────────────────── 판독기·평가 ─────────────────────────────
LM_IDX = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185, 78, 95, 88, 178, 87, 14, 317, 402, 318,
          324, 308, 415, 310, 311, 312, 13, 82, 81, 80, 191, 33, 263, 1]
CLF_FEATS = None   # 실행 때 채움: RSA 13 + W, H, G


def load_series_geo(path):
    """V2 load_series + 입술 폭 W(61–291), 바깥 입술 높이 H(0–17). 모두 눈꼬리 거리로 나눈다."""
    import numpy as np
    import v2_avatar_validity as V
    s = V.load_series(path)
    d = json.load(open(path, encoding='utf-8'))
    fps = d.get('fps') or 30.0
    W_, H_ = d.get('img_wh') or [640, 360]
    n = len(s['t'])
    w, h = np.full(n, np.nan), np.full(n, np.nan)
    ix = {k: i for i, k in enumerate(d.get('lm_idx') or LM_IDX)}
    for fr in d['frames']:
        i = int(round(fr['t_ms'] * fps / 1000.0))
        lm = fr.get('lm')
        if not (0 <= i < n) or not lm:
            continue
        p = lambda k: (lm[3 * ix[k]] * W_, lm[3 * ix[k] + 1] * H_)
        iod = math.dist(p(33), p(263))
        if iod > 1e-6:
            w[i] = math.dist(p(61), p(291)) / iod
            h[i] = math.dist(p(0), p(17)) / iod
    s['f']['W'] = w
    s['f']['H'] = h
    return s


def clf_feats():
    import v2_avatar_validity as V
    return list(V.RSA_FEATS) + ['W', 'H', 'G']


def seg_matrix(records):
    """클립 기록들(한 화자 또는 한 조건) → (무리 배열, 16특징 z 점수 행렬). 정규화는 그 화자(조건)의 모든 구간."""
    import numpy as np
    segs = [(g, v) for r in records for g, v in r['segs']]
    F = clf_feats()
    X = np.array([[v.get(k, np.nan) for k in F] for _, v in segs], dtype=float)
    mu, sd = np.nanmean(X, 0), np.nanstd(X, 0)
    ok = sd > 1e-4
    Z = np.where(ok, (X - mu) / np.where(ok, sd, 1), 0.0)
    return np.array([g for g, _ in segs]), np.nan_to_num(Z)


def real_records(sel_clips, align, bs_dir, key_spk='spk'):
    import v2_avatar_validity as V
    rec = {}
    for c in sel_clips:
        r = align.get('real:' + c['clip'])
        bp = os.path.join(bs_dir, c['clip'] + '.json')
        if r is None or 'error' in r or not os.path.exists(bp):
            continue
        segs, span = V.segments_from_align(r, V.LAG_S)
        x, _ = V.clip_record(load_series_geo(bp), segs, span)
        if x:
            x['sid'] = V.sid(c['text']) if 'text' in c else c['clip']
            rec.setdefault(c[key_spk], []).append(x)
    return rec


def cmd_classifier(a):
    import pickle
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    sel = json.load(open(a.sel, encoding='utf-8'))
    align = {json.loads(l)['key']: json.loads(l) for l in open(a.align, encoding='utf-8')}
    rec = real_records(sel['clips'], align, a.real_bs)
    Xs, ys = [], []
    for spk, rs in rec.items():
        g, Z = seg_matrix(rs)
        Xs.append(Z); ys.append(g)
    X, y = np.concatenate(Xs), np.concatenate(ys)
    clf = LogisticRegression(C=1.0, class_weight='balanced', max_iter=2000, solver='lbfgs')
    clf.fit(X, y)
    pickle.dump({'clf': clf, 'feats': clf_feats(), 'n_seg': int(len(y)), 'n_spk': len(rec)}, open(a.out, 'wb'))
    print(f'CLASSIFIER segs={len(y)} spk={len(rec)} train_macro_recall={macro_recall(clf, X, y)[0]:.3f}')


def macro_recall(clf, X, y):
    import numpy as np
    import v2_avatar_validity as V
    pred = clf.predict(X)
    per = {int(g): (float(np.mean(pred[y == g] == g)) if (y == g).any() else None) for g in V.GROUPS}
    vals = [v for v in per.values() if v is not None]
    return float(np.mean(vals)), per


def render_records_geo(renders, bs_dir, cond_filter=None):
    """렌더 폴더 → {조건: [클립 기록]}. 조건 = 작업 id의 문장 id 뒤 부분(예: v1_1.0, v3-app_2.0)."""
    import v2_avatar_validity as V
    out = {}
    for fn in sorted(os.listdir(renders)):
        if not fn.endswith('.sched.json') or not fn.startswith('txt_'):
            continue
        jid = fn[:-len('.sched.json')]
        _, s_id, cond = jid.split('_', 2)
        if cond_filter and not cond_filter(s_id, cond):
            continue
        bp = os.path.join(bs_dir, jid + '.json')
        if not os.path.exists(bp):
            continue
        sch = json.load(open(os.path.join(renders, fn), encoding='utf-8'))
        segs, span = V.segments_from_schedule(sch)
        x, _ = V.clip_record(load_series_geo(bp), segs, span)
        if x:
            x['sid'] = s_id
            out.setdefault(cond, []).append(x)
    return out


def evaluate_block(real_rec, cond_rec, clf, base_cond=None):
    """사람 기록 {화자: [기록]}, 조건 기록 {조건: [기록]} → 조건별 V2 지표·가독성."""
    import v2_avatar_validity as V
    import v15_calibrate as C
    real_prof = {s: V.profile(v) for s, v in real_rec.items()}
    prof = {c: V.profile(v) for c, v in cond_rec.items()}
    rsa, amp = V.rsa_block(real_prof, prof), V.amp_block(real_prof, prof)
    res = {'n_real': len(real_prof), 'loo': rsa['loo'], 'n_rsa_real': rsa['n_real'], 'amp_human_loo': amp.get('human_loo'), 'cond': {}}
    for c in sorted(prof):
        g, Z = seg_matrix(cond_rec[c])
        mr, per = macro_recall(clf, Z, g)
        leg = V.legibility(real_prof, prof[c])
        ag = amp['cond'][c]['groups']
        res['cond'][c] = {
            'n_clips': len(cond_rec[c]), 'rho': rsa['cond'][c]['rho'], 'rho_pass': rsa['cond'][c].get('pass'),
            'pair_dev': rsa['cond'][c].get('pair_dev', [])[:6], 'amp_n_in': amp['cond'][c]['n_in'],
            'per_channel_in': amp['cond'][c]['per_channel_in'],
            'pctA': {gg: (ag[gg].get('A') or {}).get('pct') for gg in V.GROUPS},
            'S_i': ag[3].get('S'), 'legibility': leg, 'reader_macro': round(mr, 4), 'reader_per': per,
            'distinct13': C.distinctiveness(cond_rec[c]), 'distinct16': distinct16(cond_rec[c])}
    # 판독기 자체 성능: 사람 화자 구간
    import numpy as np
    Xs, ys = [], []
    for s, rs in real_rec.items():
        gg, Z = seg_matrix(rs)
        Xs.append(Z); ys.append(gg)
    if Xs:
        res['reader_human_macro'] = round(macro_recall(clf, np.concatenate(Xs), np.concatenate(ys))[0], 4)
    return res


def distinct16(records):
    """V15 6.3 구별성(조건 안, 자기 문장 뺀 최근접 중심)을 16특징으로."""
    import numpy as np
    import v2_avatar_validity as V
    g, Z = seg_matrix(records)
    sids = np.array([r['sid'] for r in records for _ in r['segs']])
    G = list(V.GROUPS)
    hit = {k: [0, 0] for k in G}
    for i in range(len(g)):
        m = sids != sids[i]
        best, bd = None, np.inf
        for k in G:
            mk = m & (g == k)
            if mk.any():
                d = np.sqrt(((Z[mk].mean(0) - Z[i]) ** 2).sum())
                if d < bd:
                    best, bd = k, d
        hit[int(g[i])][1] += 1
        hit[int(g[i])][0] += int(best == g[i])
    return {k: (round(h / n, 4) if n else None, n) for k, (h, n) in hit.items()}


def verdict(res, v3='v3-app', v1='v1'):
    import v2_avatar_validity as V
    c = res['cond']
    a1, a2, b1, b2 = c[f'{v3}_1.0'], c[f'{v3}_2.0'], c[f'{v1}_1.0'], c[f'{v1}_2.0']
    p10 = res['loo']['p10']
    v = {'rsa': bool(a1['rho'] is not None and a1['rho'] >= p10 and a1['rho'] > (b1['rho'] or -1)),
         'amp': bool(a2['amp_n_in'] >= V.AMP_N_PASS and a2['amp_n_in'] >= b2['amp_n_in'])}
    for sp, x, y in (('1.0', a1, b1), ('2.0', a2, b2)):
        v[f'bilabial_{sp}'] = bool((x['legibility'].get('bilabial_closure_rate') or 0) >= 0.95)
        v[f'rounded_{sp}'] = bool((x['legibility'].get('rounded_R_in_range_rate') or 0) >= 0.80)
        v[f'reader_{sp}'] = bool(x['reader_macro'] >= y['reader_macro'] - 0.02)
    v['all'] = all(v.values())
    return v


def cmd_evaluate(a):
    import pickle
    clf = pickle.load(open(a.clf, 'rb'))['clf']
    sel = json.load(open(a.sel, encoding='utf-8'))
    align = {}
    for p in a.align:
        for l in open(p, encoding='utf-8'):
            r = json.loads(l)
            align[r['key']] = r
    clips = sel['clips']
    if a.half is not None:
        hs = {s['spk']: s['half'] for s in sel['speakers']}
        clips = [c for c in clips if hs[c['spk']] == a.half]
    real_rec = real_records(clips, align, a.real_bs)
    sids = None
    if a.half is not None:
        sids = {e['sid'] for e in sel['sentences'] if e.get('half') == a.half and e.get('default')}
    cond_rec = {}
    for rd, bd in zip(a.renders, a.render_bs):
        for c, v in render_records_geo(rd, bd, (lambda s, c_: s in sids) if sids else None).items():
            cond_rec.setdefault(c, []).extend(v)
    res = evaluate_block(real_rec, cond_rec, clf)
    if a.verdict:
        res['verdict'] = verdict(res, a.v3, a.v1)
    json.dump(res, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=str)
    print('EVALUATE n_real', res['n_real'], 'p10', res['loo']['p10'], 'reader_human', res.get('reader_human_macro'))
    for c, r in res['cond'].items():
        print(f"  {c:16s} n={r['n_clips']:3d} rho={r['rho']} amp={r['amp_n_in']} chan={r['per_channel_in']} "
              f"bil={r['legibility'].get('bilabial_closure_rate')} rnd={r['legibility'].get('rounded_R_in_range_rate')} "
              f"reader={r['reader_macro']} pctA={list(r['pctA'].values())}")
    if a.verdict:
        print('VERDICT', json.dumps(res['verdict']))


# ───────────────────────────── selftest(JS 구현 일치 기준) ─────────────────────────────
def cmd_selftest(a):
    model = json.load(open(a.table, encoding='utf-8'))
    frames = json.load(open(a.frames, encoding='utf-8'))
    out = []
    for case in frames:
        co = frames_to_coeffs(model, case['frames'], case.get('speed', 1.0))
        out.append({'name': case['name'], 'n': len(co), 'first': co[0], 'mid': co[len(co) // 2], 'last': co[-1]})
    json.dump(out, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('SELFTEST', len(out))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('select')
    s.add_argument('--v2-sel', required=True)
    s.add_argument('--root', nargs='+', required=True)
    s.add_argument('--per-spk', type=int, default=12)
    s.add_argument('--n-default', type=int, default=6)
    s.add_argument('--stamp', default='')
    s.add_argument('--out', required=True)
    s.add_argument('--items', required=True)
    s = sub.add_parser('dataset')
    s.add_argument('--sel', required=True)
    s.add_argument('--align', required=True)
    s.add_argument('--real-bs', required=True)
    s.add_argument('--out', required=True)
    s = sub.add_parser('fit')
    s.add_argument('--data', required=True)
    s.add_argument('--halves', default='0,1')
    s.add_argument('--mode', default='add')
    s.add_argument('--gain', default='')
    s.add_argument('--out', required=True)
    s = sub.add_parser('human')
    s.add_argument('--data', required=True)
    s.add_argument('--sel', required=True)
    s.add_argument('--align', required=True)
    s.add_argument('--real-bs', required=True)
    s.add_argument('--modes', default='base,add,full')
    s.add_argument('--gains', default='1,1,1,1')
    s.add_argument('--out', default='')
    s = sub.add_parser('jobs')
    s.add_argument('--sel', required=True)
    s.add_argument('--backend', required=True)
    s.add_argument('--cond', required=True)
    s.add_argument('--speeds', type=float, nargs='+', default=[1.0, 2.0])
    s.add_argument('--half', type=int, default=None)
    s.add_argument('--out', required=True)
    s = sub.add_parser('classifier')
    s.add_argument('--sel', required=True)
    s.add_argument('--align', required=True)
    s.add_argument('--real-bs', required=True)
    s.add_argument('--out', required=True)
    s = sub.add_parser('evaluate')
    s.add_argument('--sel', required=True)
    s.add_argument('--align', nargs='+', required=True)
    s.add_argument('--real-bs', required=True)
    s.add_argument('--renders', nargs='+', required=True)
    s.add_argument('--render-bs', nargs='+', required=True)
    s.add_argument('--clf', required=True)
    s.add_argument('--half', type=int, default=None)
    s.add_argument('--verdict', action='store_true')
    s.add_argument('--v3', default='v3-app')
    s.add_argument('--v1', default='v1')
    s.add_argument('--out', required=True)
    s = sub.add_parser('selftest')
    s.add_argument('--table', required=True)
    s.add_argument('--frames', required=True)
    s.add_argument('--out', required=True)
    a = ap.parse_args()
    {'select': cmd_select, 'dataset': cmd_dataset, 'fit': cmd_fit, 'human': cmd_human, 'jobs': cmd_jobs, 'classifier': cmd_classifier,
     'evaluate': cmd_evaluate, 'selftest': cmd_selftest}[a.cmd](a)


if __name__ == '__main__':
    main()
