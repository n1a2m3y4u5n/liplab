#!/usr/bin/env python3
"""독화 ① 입술 영역 화소 전단 R1·R2 학습 도구(2026-10-18, 사전등록 docs/lipread-roi-2026-10.md 3·5·6절).

V1 학습 도구(scripts/lipread_v1/v1_train.py)의 후보 B(문장 + 어절 wide 구간, 어절 절반을 idle75 창에 넣음)를 입력만
블렌드셰이프 27채널에서 입술 영역 화소(88×88 흑백, 학습 80×80 임의 자르기)로 바꾼 것이다. 머리(LayerNorm → BiGRU 3층
256 → 자모 53 CTC)와 검증 4지 채점(ctc_ll α=1, idle75, dup1·dup2 평균, 화자 평균)은 V1과 같다.
평가 화자 40명의 ROI는 이 도구의 prep·teacher·pretrain·train이 읽지 않는다. p4는 평가 화자를 --judge 없이 거부한다.

하위명령(데스크탑 D:\\liplab\\vlip\\Scripts\\python.exe, 도구 폴더 LIPLAB_TOOLS = D:/liplab/v1/dax의 d_bench 등을 가져다 쓴다)
  prep     --bench B --split S --npz DIR --extra ROOT … --out RUN [--max-clips N]
           학습 항목·검증 문항·쉬는 구간을 만들고, 학습·검증 화자 ROI를 한 파일(RUN/pack/roi_u8.bin, uint8 프레임×88×88)로
           모은다. 학습 클립은 무작위 순서로 적어 에폭마다 덩어리 단위로 거의 순차로 읽는다(D:가 HDD라 임의 읽기를 피함).
           추가 루트(roi538/a·b, e538r, v1_538r)의 클립은 벤치에 없으면 문장 항목으로만 들어간다(어절 구간이 없음).
           받기 B는 화자 ID의 인물이 기존 manifest_meta와 다르면 그 화자의 B 클립을 쓰지 않는다.
  teacher  --run RUN [--layer 9]          R2 교사: 학습 화자 클립 음성의 WavLM Base+ 9층(50 Hz → ROI 30 fps 선형 보간,
                                          화자 평균 빼기) → RUN/pack/wavlm_f16.bin
  pretrain --run RUN --seed S --out DIR [--epochs 20]   R2 1단계: 전단 + 1차원 합성곱 2층 투영, 손실 L1 + (1 − 코사인)
  train    --run RUN --cand R1|R2 --seed S --out DIR [--init DIR/pre.pt]   CTC 학습·검증·체크포인트(끊기면 --resume)
  select   --runs D1,D2,… --out sel.json     6절 선택(동점은 목록 순서·dup2 먼저)
  p4       --model M --bench B --npz DIR --speakers a,b,… --out J [--max-items N] [--judge --eval-list E]
           4지 hard ctc_ll α=1 idle75 dup1·2(채점 경로). 평가 화자가 들어 있으면 --judge 없이는 멈춘다.
  export   --model M --out X.onnx          ONNX(입력 roi [1,T,80,80] 0~255 float, 출력 logits [1,T,53]) + int8 + 크기·일치 확인
  probe    --run RUN [--batch 32]          가장 긴 배치로 GPU 메모리 최고치와 단계 시간 측정(시험용)
  all      --run RUN [--seeds 0,1]         teacher → R1 s0 → R2 s0(사전학습 → 미세조정) → R1 s1 → R2 s1 → select 순서로
                                          한 프로세스에서 하나씩 돌린다. 끝난 단계는 건너뛰고 끊긴 단계는 이어 한다.
표식: ROI_PREP_OK, ROI_TEACHER_OK, ROI_PRE_DONE, ROI_TRAIN_DONE, ROI_SELECT, ROI_P4_DONE, ROI_EXPORT_OK, ROI_ALL_OK, *_FAIL
"""
import argparse
import hashlib
import json
import math
import os
import sys
import threading
import queue
import time
from collections import defaultdict

import numpy as np

TOOLS = os.environ.get('LIPLAB_TOOLS', 'D:/liplab/v1/dax')
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

S_ROI, CROP, IDLE_LEN, DUPS, ALPHA = 88, 80, 75, (2, 1), 1.0
FPS = 30.0
MAX_INVALID = 0.5


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def wjson(obj, path, **kw):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = f'{path}.tmp{os.getpid()}'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, **kw)
    os.replace(tmp, path)


def read_list(p):
    return [x.strip() for x in open(p, encoding='utf-8') if x.strip() and not x.startswith('#')]


def crc(s):
    import zlib
    return zlib.crc32(s.encode('utf-8')) & 0xffffffff


def tsv(p):
    return [l.rstrip('\n').split('\t') for l in open(p, encoding='utf-8') if l.strip() and not l.startswith('#')]


# ───────────────────────────── 쉬는 구간·창(프레임 번호) ─────────────────────────────
def rest_runs_idx(bench, cols, spks):
    """d_bench._rest_runs와 같은 규칙·같은 순서로, 배열 대신 (클립 번호, 프레임 번호 배열)을 화자별로."""
    lead, tail = defaultdict(list), defaultdict(list)
    for ci, c in enumerate(bench.clips):
        if c['flag'] or c['spk'] not in spks:
            continue
        X = bench.bs[c['off']:c['off'] + c['n']][:, cols]
        a, b = c['speech']
        ok = ~np.isnan(X).any(1)
        pre = np.arange(0, max(0, a - 3))
        post = np.arange(min(c['n'], b + 3), c['n'])
        pre, post = pre[ok[pre]], post[ok[post]]
        if len(pre) >= 3:
            lead[c['spk']].append((ci, pre))
        if len(post) >= 3:
            tail[c['spk']].append((ci, post))
    return lead, tail


def tile_idx(run, need, from_end):
    ci, fr = run
    if need <= 0:
        return []
    reps = int(math.ceil(need / float(len(fr))))
    t = np.concatenate([fr] * reps, 0)
    t = t[-need:] if from_end else t[:need]
    return [(ci, int(f)) for f in t]


def p4_window(bench, inst, cols, lead, tail):
    """d_bench.p4_sequences(pad=idle75, seg=wide, dup=1)와 같은 창을 (클립 번호, 프레임) 목록으로. 못 자르면 None."""
    c = bench.clips[inst['c']]
    off = c['off']
    a, b = inst['wide']
    X = bench.bs[off + a:off + b][:, cols]
    if len(X) == 0 or np.isnan(X[:, 0]).mean() > 0.5:
        return None
    seg = [(inst['c'], f) for f in range(a, b)]
    if len(seg) < IDLE_LEN:
        need = IDLE_LEN - len(seg)
        nl, nr = need // 2, need - need // 2
        key = crc(f"idle|{inst['iid']}")
        L_runs, R_runs = lead.get(inst['spk']), tail.get(inst['spk'])
        left = tile_idx(L_runs[key % len(L_runs)], nl, True) if L_runs else [seg[0]] * nl
        right = tile_idx(R_runs[(key // 7) % len(R_runs)], nr, False) if R_runs else [seg[-1]] * nr
        seg = left + seg + right
    return seg


def h4_items(bench, spks):
    """product4way와 같은 문항(어휘 = bench.dist_words, hard 오답 순서)."""
    from d_bench import Distractors
    from train_lipread import decompose
    pool = list(bench.dist_words)
    ps = set(pool)
    dis = Distractors(bench, pool)
    out = []
    for it in bench.inst:
        if it['ok'] and it['w'] in ps and it['spk'] in spks:
            hard = Distractors.order([it['w']] + dis.hard(it['w']), it['iid'])
            out.append({'iid': it['iid'], 'spk': it['spk'], 'w': it['w'], 'inst': it,
                        'labs': [decompose(w) for w in hard], 'tgt': hard.index(it['w'])})
    return out


# ───────────────────────────── prep ─────────────────────────────
def cmd_prep(a):
    import folds as FO
    from d_bench import Bench
    from train_lipread import MOUTH_KEYS, decompose
    t0 = time.time()
    b = Bench(a.bench)
    sp = json.load(open(a.split, encoding='utf-8'))
    if sp.get('bench_id') and sp['bench_id'] != b.bench_id:
        raise ValueError('split의 bench_id가 벤치와 다름')
    ev, va, tr_b = set(sp['eval']), set(sp['val']), set(sp['train'])
    cols = [b.bs_names.index(k) for k in MOUTH_KEYS]
    os.makedirs(os.path.join(a.out, 'pack'), exist_ok=True)
    rep = defaultdict(int)

    # 추가 루트: manifest(클립, 화자, 문장) + manifest_meta(화자 → 인물)
    bench_names = {c['clip'] for c in b.clips}
    person = {}                                   # 기존 루트(V1·S4)의 화자 → 인물
    for r in a.extra:
        mp = os.path.join(r, 'manifest_meta.tsv')
        if os.path.exists(mp) and os.path.basename(os.path.normpath(r)) != 'b':
            for p in tsv(mp):
                person.setdefault(p[0], p[2])
    extra, seen = [], set(bench_names)
    for r in a.extra:
        mf = os.path.join(r, 'manifest.tsv')
        if not os.path.exists(mf):
            continue
        is_b = os.path.basename(os.path.normpath(r)) == 'b'
        bad_b = set()
        if is_b:
            for p in tsv(os.path.join(r, 'manifest_meta.tsv')):
                if p[0] in person and person[p[0]] != p[2]:
                    bad_b.add(p[0])
            rep['b_person_mismatch_spk'] = len(bad_b)
        for t in tsv(mf):
            if len(t) < 3:
                continue
            nm = t[0][:-4] if t[0].endswith('.mp4') else t[0]
            if nm in seen:
                rep['extra_dup_name'] += 1
                continue
            if t[1] in bad_b:
                rep['b_person_drop_clip'] += 1
                continue
            seen.add(nm)
            extra.append({'clip': nm, 'spk': t[1], 'text': t[2], 'wav': os.path.join(r, 'clips', nm + '.wav'),
                          'src': os.path.basename(os.path.normpath(r))})
    # 내용 분리: 검증·평가 화자가 읽은 문장(벤치 + 추가 루트)
    held_txt = {FO.norm_text(c['text']) for c in b.clips if c['spk'] in ev | va}
    held_txt |= {FO.norm_text(e['text']) for e in extra if e['spk'] in ev | va}
    held_txt.discard('')
    # 학습 화자 = 벤치 학습 화자 + 추가 루트에서 검증·평가가 아닌 화자
    tr_x = {e['spk'] for e in extra} - ev - va
    tr = tr_b | tr_x
    rep['train_spk_bench'], rep['train_spk_extra_only'] = len(tr_b), len(tr_x - tr_b)

    def npz_path(nm):
        p = os.path.join(a.npz, nm + '.npz')
        return p if os.path.exists(p) else None

    # 클립 목록(학습 + 검증 화자 벤치 클립)
    clips = []                                    # dict(name, spk, src, text, wav, bench_ci)
    by_clip = defaultdict(list)
    for it in b.inst:
        if it['ok']:
            by_clip[it['c']].append(it)
    for ci, c in enumerate(b.clips):
        if c['spk'] in tr or c['spk'] in va:
            clips.append({'clip': c['clip'], 'spk': c['spk'], 'text': c['text'], 'bench_ci': ci, 'src': 'bench',
                          'wav': None, 'role': 'val' if c['spk'] in va else 'train'})
    for e in extra:
        if e['spk'] in tr:
            clips.append(dict(e, bench_ci=-1, role='train'))
    wav_of = {e['clip']: e['wav'] for e in extra}
    for r in a.extra:                             # 벤치 클립의 음성(받은 루트의 clips/*.wav)
        for c in clips:
            if c['wav'] is None:
                p = os.path.join(r, 'clips', c['clip'] + '.wav')
                if os.path.exists(p):
                    c['wav'] = p
    for c in clips:
        if c['wav'] is None and c['clip'] in wav_of:
            c['wav'] = wav_of[c['clip']]
    if a.max_clips:                               # 시험용: 학습 화자 클립 일부만
        rng0 = np.random.default_rng(0)
        trc = [c for c in clips if c['role'] == 'train']
        keep = {id(trc[i]) for i in rng0.permutation(len(trc))[:a.max_clips]}
        clips = [c for c in clips if c['role'] == 'val' or id(c) in keep]
    # ROI 읽기 → pack(학습 클립은 무작위 순서, 검증 클립은 뒤에)
    rng = np.random.default_rng(12345)
    trc = [c for c in clips if c['role'] == 'train']
    vac = [c for c in clips if c['role'] == 'val']
    order = [trc[i] for i in rng.permutation(len(trc))] + vac
    pack_p = os.path.join(a.out, 'pack', 'roi_u8.bin')
    kept, off = [], 0
    with open(pack_p + '.tmp', 'wb') as f:
        for k, c in enumerate(order):
            p = npz_path(c['clip'])
            if p is None:
                rep['roi_missing_' + c['role']] += 1
                continue
            try:
                with np.load(p, allow_pickle=False) as z:
                    v = z['valid'].astype(bool)
                    roi = np.zeros((len(v), S_ROI, S_ROI), np.uint8) if a.dry else z['roi']
            except Exception:  # noqa: BLE001
                rep['roi_bad'] += 1
                continue
            if roi.ndim != 3 or roi.shape[1:] != (S_ROI, S_ROI) or roi.dtype != np.uint8 or len(v) != len(roi):
                rep['roi_bad'] += 1
                continue
            if c['bench_ci'] >= 0 and abs(len(roi) - b.clips[c['bench_ci']]['n']) > 2:
                rep['roi_len_mismatch'] += 1
                continue
            if not a.dry:
                f.write(np.ascontiguousarray(roi).tobytes())
            c2 = {k2: c[k2] for k2 in ('clip', 'spk', 'src', 'role', 'bench_ci', 'wav', 'text')}
            c2.update(off=off, T=int(len(roi)), vfrac=float(v.mean()), valid_bits=np.packbits(v).tobytes().hex())
            kept.append(c2)
            off += len(roi)
            if (k + 1) % 1000 == 0:
                log(f'[prep] pack {k + 1}/{len(order)} frames={off}')
    os.replace(pack_p + '.tmp', pack_p)
    idx_of = {c['clip']: i for i, c in enumerate(kept)}
    # 학습 항목
    sent, words = [], []
    for i, c in enumerate(kept):
        if c['role'] != 'train':
            continue
        if c['bench_ci'] >= 0 and b.clips[c['bench_ci']]['flag']:
            rep['train_flag'] += 1
            continue
        if not c['text']:
            continue
        if FO.norm_text(c['text']) in held_txt:
            rep['train_drop_shared_text'] += 1
            continue
        if c['vfrac'] < 0.5 or c['T'] < 10:
            rep['train_low_valid'] += 1
            continue
        tg = decompose(c['text'])
        if tg:
            sent.append([i, tg])
        if c['bench_ci'] >= 0:
            for it in by_clip.get(c['bench_ci'], ()):
                s0, s1 = it['wide']
                s1 = min(s1, c['T'])
                tw = decompose(it['w'])
                if s1 - s0 >= 3 and tw:
                    words.append([i, int(s0), int(s1), tw])
    # 쉬는 구간(학습 화자: idle 창 증강용, 검증 화자: 검증 창)
    lead, tail = rest_runs_idx(b, cols, tr_b | va)

    def runs_json(dct):
        out = {}
        for s, lst in dct.items():
            rr = [[idx_of[b.clips[ci]['clip']], fr.tolist()] for ci, fr in lst if b.clips[ci]['clip'] in idx_of]
            if rr:
                out[s] = rr
        return out
    # 검증 문항(4지 hard, idle75)
    vitems = []
    nwin_none = nwin_miss = 0
    for x in h4_items(b, va):
        w = p4_window(b, x['inst'], cols, lead, tail)
        rec = {'iid': x['iid'], 'spk': x['spk'], 'labs': x['labs'], 'tgt': x['tgt'], 'win': None}
        if w is None:
            nwin_none += 1
        else:
            names = {b.clips[ci]['clip'] for ci, _ in w}
            if all(n in idx_of for n in names):
                rec['win'] = [[idx_of[b.clips[ci]['clip']], f] for ci, f in w]
            else:
                nwin_miss += 1
        vitems.append(rec)
    vsent = [[i, decompose(c['text'])] for i, c in enumerate(kept) if c['role'] == 'val' and c['text']
             and not b.clips[c['bench_ci']]['flag'] and c['T'] >= 10]
    meta = {'bench': os.path.abspath(a.bench), 'bench_id': b.bench_id, 'split': os.path.abspath(a.split),
            'npz': os.path.abspath(a.npz), 'extra': [os.path.abspath(r) for r in a.extra], 'S': S_ROI,
            'frames': off, 'train_spk': sorted(tr), 'val_spk': sorted(va), 'n_eval_spk_excluded': len(ev),
            'max_clips': a.max_clips, 'report': dict(rep), 'n_sent': len(sent), 'n_words': len(words),
            'n_val_items': len(vitems), 'val_win_unseg': nwin_none, 'val_win_roi_missing': nwin_miss,
            'n_val_sent': len(vsent), 'time_sec': round(time.time() - t0),
            'frames_sent': int(sum(kept[i]['T'] for i, _ in sent)), 'frames_words': int(sum(e - s0 for _, s0, e, _ in words)),
            'frames_teacher_clips': int(sum(c['T'] for c in kept if c['role'] == 'train' and c['wav']))}
    wjson({'meta': meta, 'clips': kept, 'sent': sent, 'words': words, 'lead': runs_json(lead), 'tail': runs_json(tail),
           'val_items': vitems, 'val_sent': vsent}, os.path.join(a.out, 'prep.json'))
    leak = set(meta['train_spk']) & (ev | va)
    if leak:
        raise ValueError(f'학습 화자에 검증·평가 화자: {sorted(leak)[:5]}')
    log('[prep]', json.dumps({k: v for k, v in meta.items() if k not in ('train_spk', 'val_spk')}, ensure_ascii=False))
    print(f'ROI_PREP_OK clips={len(kept)} frames={off} ({off * S_ROI * S_ROI / 1e9:.1f} GB) sent={len(sent)} '
          f'words={len(words)} val_items={len(vitems)} train_spk={len(tr)}', flush=True)
    return 0


# ───────────────────────────── 자료(메모리 매핑) ─────────────────────────────
class Run:
    def __init__(self, run):
        self.dir = run
        d = json.load(open(os.path.join(run, 'prep.json'), encoding='utf-8'))
        self.meta, self.clips = d['meta'], d['clips']
        self.sent, self.words = d['sent'], d['words']
        self.lead = {s: [(ci, np.array(fr, np.int64)) for ci, fr in v] for s, v in d['lead'].items()}
        self.tail = {s: [(ci, np.array(fr, np.int64)) for ci, fr in v] for s, v in d['tail'].items()}
        self.val_items, self.val_sent = d['val_items'], d['val_sent']
        S = self.meta['S']
        self.roi = np.memmap(os.path.join(run, 'pack', 'roi_u8.bin'), np.uint8, 'r', shape=(self.meta['frames'], S, S))
        self.off = np.array([c['off'] for c in self.clips], np.int64)
        self.T = np.array([c['T'] for c in self.clips], np.int64)
        self.spk = [c['spk'] for c in self.clips]
        tp = os.path.join(run, 'pack', 'wavlm_f16.bin')
        self.teach = None
        if os.path.exists(tp) and os.path.exists(tp + '.json'):
            tj = json.load(open(tp + '.json', encoding='utf-8'))
            self.teach = np.memmap(tp, np.float16, 'r', shape=(self.meta['frames'], tj['dim']))
            self.has_teach = np.zeros(len(self.clips), bool)
            self.has_teach[tj['clips']] = True

    def gidx(self, ci, fr):
        fr = np.clip(np.asarray(fr, np.int64), 0, self.T[ci] - 1)
        return self.off[ci] + fr


def frame_groups(lens, maxf):
    """배치 안 순서를 지키며 유효 프레임 합이 maxf를 넘지 않게 나눈 번호 묶음(0 = 나누지 않음)."""
    if not maxf or int(lens.sum()) <= maxf:
        return [np.arange(len(lens))]
    out, cur, acc = [], [], 0
    for i, n in enumerate(lens):
        if cur and acc + int(n) > maxf:
            out.append(np.array(cur))
            cur, acc = [], 0
        cur.append(i)
        acc += int(n)
    out.append(np.array(cur))
    return out


def chunked_order(items, run, rng, chunk=192):
    """학습 항목을 클립 pack 순서 덩어리(chunk개 클립)로 묶어 덩어리 순서와 덩어리 안 순서를 섞는다(HDD 순차 읽기)."""
    ci = np.array([it[1][0] for it in items])
    blk = ci // chunk
    ub = rng.permutation(np.unique(blk))
    out = []
    for k in range(0, len(ub), 2):              # 덩어리 두 개씩 섞어 배치 구성의 다양성을 조금 더 준다
        sel = np.nonzero(np.isin(blk, ub[k:k + 2]))[0]
        out.extend(sel[rng.permutation(len(sel))].tolist())
    return [items[i] for i in out]


def speed_idx(n, rng):
    T2 = max(2, int(round(n / rng.uniform(0.8, 1.25))))
    return np.round(np.linspace(0.0, n - 1.0, T2)).astype(np.int64)


def idle_window_idx(run, gi, spk, rng):
    """V1 Data.idle_window과 같은 규칙(임의 위치, 같은 화자 쉬는 구간), 전역 프레임 번호로."""
    L = len(gi)
    if L >= IDLE_LEN:
        return gi
    need = IDLE_LEN - L
    nl = int(rng.integers(0, need + 1))
    nr = need - nl
    Lr, Rr = run.lead.get(spk), run.tail.get(spk)

    def tile(r, n, end):
        ci, fr = r
        g = run.gidx(ci, fr)
        reps = int(math.ceil(n / float(len(g))))
        t = np.concatenate([g] * reps)
        return t[-n:] if end else t[:n]
    left = tile(Lr[int(rng.integers(len(Lr)))], nl, True) if (Lr and nl) else np.repeat(gi[:1], nl)
    right = tile(Rr[int(rng.integers(len(Rr)))], nr, False) if (Rr and nr) else np.repeat(gi[-1:], nr)
    return np.concatenate([left, gi, right])


def make_batch(run, gidx_list, rng=None, crop=CROP, with_teacher=False):
    """전역 프레임 번호 목록들 → uint8 (B,Tp,crop,crop), lens, flips, tmask[, 교사(B,Tp,D)]. 읽기는 정렬된 번호로 한 번에."""
    B = len(gidx_list)
    L = max(len(g) for g in gidx_list)
    Tp = int(math.ceil(L / 4.0) * 4)
    S = run.roi.shape[1]
    allg = np.concatenate(gidx_list)
    uq, inv = np.unique(allg, return_inverse=True)
    frames = run.roi[uq]                           # 정렬된 번호 → 대부분 순차 읽기
    X = np.zeros((B, Tp, crop, crop), np.uint8)
    lens = np.array([len(g) for g in gidx_list], np.int64)
    flips = np.zeros(B, bool)
    tmask = np.zeros((B, Tp), bool)
    c0 = (S - crop) // 2
    tch = None
    if with_teacher:
        tf = run.teach[uq].astype(np.float32)
        tch = np.zeros((B, Tp, tf.shape[1]), np.float32)
    p = 0
    for i, g in enumerate(gidx_list):
        n = len(g)
        fr = frames[inv[p:p + n]]
        if rng is not None:
            oy, ox = int(rng.integers(0, S - crop + 1)), int(rng.integers(0, S - crop + 1))
        else:
            oy = ox = c0
        X[i, :n] = fr[:, oy:oy + crop, ox:ox + crop]
        if tch is not None:
            tch[i, :n] = tf[inv[p:p + n]]
        if rng is not None:
            flips[i] = rng.random() < 0.5
            if not with_teacher:
                m = int(rng.integers(0, 4))
                if 0 < m < n:
                    st = int(rng.integers(0, n - m + 1))
                    tmask[i, st:st + m] = True
        p += n
    return X, lens, flips, tmask, tch


class Prefetch:
    """배치 만들기(디스크 읽기)를 GPU 계산과 겹친다(스레드 하나, 큐 4)."""

    def __init__(self, gen, depth=4):
        self.q = queue.Queue(depth)
        self.err = None

        def work():
            try:
                for x in gen:
                    self.q.put(x)
            except Exception as e:  # noqa: BLE001
                self.err = e
            self.q.put(None)
        self.t = threading.Thread(target=work, daemon=True)
        self.t.start()

    def __iter__(self):
        while True:
            x = self.q.get()
            if x is None:
                if self.err:
                    raise self.err
                return
            yield x


# ───────────────────────────── 모델 ─────────────────────────────
def build_models(n_vocab=53, proj_dim=0):
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from train_lipread import build as build_head

    class Block(nn.Module):
        def __init__(s, cin, cout, stride):
            super().__init__()
            s.c1 = nn.Conv2d(cin, cout, 3, stride, 1, bias=False)
            s.b1 = nn.BatchNorm2d(cout)
            s.c2 = nn.Conv2d(cout, cout, 3, 1, 1, bias=False)
            s.b2 = nn.BatchNorm2d(cout)
            s.down = None
            if stride != 1 or cin != cout:
                s.down = nn.Sequential(nn.Conv2d(cin, cout, 1, stride, bias=False), nn.BatchNorm2d(cout))

        def forward(s, x):
            y = F.relu(s.b1(s.c1(x)))
            y = s.b2(s.c2(y))
            return F.relu(y + (x if s.down is None else s.down(x)))

    class Front(nn.Module):
        """5절 전단: Conv3d(1→24, 5×7×7, 보폭 1×2×2) + BN + ReLU + 최대풀링 1×3×3(보폭 1×2×2) → 프레임별 ResNet-18 폭 0.5
        (32·64·128·256, 블록 2·2·2·2) → 전역 평균 → 선형 256. BN은 유효 프레임만 모아 계산한다(패딩이 통계에 안 섞임)."""

        def __init__(s, ckpt=False):
            super().__init__()
            s.c3 = nn.Conv3d(1, 24, (5, 7, 7), (1, 2, 2), (2, 3, 3), bias=False)
            s.b3 = nn.BatchNorm2d(24)
            chans, cin, layers = (32, 64, 128, 256), 24, []
            for k, c in enumerate(chans):
                layers.append(nn.Sequential(Block(cin, c, 1 if k == 0 else 2), Block(c, c, 1)))
                cin = c
            s.stages = nn.ModuleList(layers)
            s.fc = nn.Linear(256, 256)
            s.ckpt = ckpt

        def forward(s, x, lens):
            """x (B,1,T,H,W) 정규화된 화소, lens (B,) → (B,T,256), 패딩 프레임은 0.
            Conv3d는 유효 프레임만 시간축으로 이어 붙여(시퀀스 사이 0 프레임 2개, 시간 커널 5의 덧대기와 같음) 한 번에 돌린다.
            시퀀스마다 따로 덧대어 돌린 것과 값이 같고, 패딩 프레임 계산·메모리가 없다."""
            B, _, T, H, W = x.shape
            dv = x.device
            L = lens.to(dv)
            m = torch.arange(T, device=dv)[None, :] < L[:, None]
            start = torch.cumsum(torch.cat([L.new_zeros(1), L[:-1] + 2]), 0)          # 시퀀스 b의 시작 위치
            pos = (start[:, None] + torch.arange(T, device=dv)[None, :])[m]           # (N,) 유효 프레임 위치
            ntot = int(L.sum()) + 2 * (B - 1)
            cat = x.new_zeros(ntot, H, W)
            cat[pos] = x[:, 0][m]
            h = s.c3(cat[None, None])[0].transpose(0, 1)[pos]                         # (N,24,H/2,W/2)
            v = F.max_pool2d(F.relu(s.b3(h)), 3, 2, 1)
            for st in s.stages:
                if s.ckpt and v.requires_grad:
                    from torch.utils.checkpoint import checkpoint
                    v = checkpoint(st, v, use_reentrant=False)
                else:
                    v = st(v)
            v = s.fc(v.mean(dim=(2, 3)))
            out = v.new_zeros(B, T, 256)
            out[m] = v
            return out

    class Proj(nn.Module):
        def __init__(s, d):
            super().__init__()
            s.c1 = nn.Conv1d(256, 512, 3, 1, 1)
            s.c2 = nn.Conv1d(512, d, 3, 1, 1)

        def forward(s, f):                                      # (B,T,256) → (B,T,d)
            return s.c2(F.gelu(s.c1(f.transpose(1, 2)))).transpose(1, 2)

    front = Front()
    head = build_head(256, n_vocab)
    proj = Proj(proj_dim) if proj_dim else None
    return front, head, proj


def normalize(X, lens, flips, tmask, dev):
    """장치에서: /255 → 시퀀스별 z-정규화(유효 프레임 화소 통계) → 좌우 반전 → 시간 마스크 0 → (B,1,T,H,W)."""
    import torch
    x = torch.from_numpy(X).to(dev, non_blocking=True).float().div_(255.0)
    T = x.shape[1]
    L = torch.from_numpy(lens).to(dev)
    m = (torch.arange(T, device=dev)[None, :] < L[:, None]).float()
    npx = float(x.shape[2] * x.shape[3])
    cnt = (m.sum(1) * npx).clamp(min=1.0)
    mean = (x.sum(dim=(2, 3)) * m).sum(1) / cnt
    xc = x - mean[:, None, None, None]
    var = ((xc * xc).sum(dim=(2, 3)) * m).sum(1) / cnt
    x = xc / var.sqrt().clamp(min=1e-2)[:, None, None, None]
    if flips is not None and flips.any():
        f = torch.from_numpy(flips).to(dev)[:, None, None, None]
        x = torch.where(f, x.flip(-1), x)
    keep = m
    if tmask is not None and tmask.any():
        keep = keep * (~torch.from_numpy(tmask).to(dev)).float()
    return (x * keep[:, :, None, None]).unsqueeze(1).contiguous()


def run_front(front, x, lens_t, amp):
    import torch
    with torch.autocast('cuda', dtype=torch.bfloat16, enabled=bool(amp) and x.is_cuda):
        f = front(x, lens_t)
    return f.float()


# ───────────────────────────── 검증 4지·CER ─────────────────────────────
def ctc_scores(lp, labs):
    """lp (T,V) 로그확률 → 후보마다 −NLL/길이^α(V1 val_4way·product4way ctc_ll과 같은 식)."""
    import torch
    import torch.nn.functional as F
    n = len(labs)
    lpi = lp[None].repeat(n, 1, 1).transpose(0, 1).cpu().double()
    tg = torch.tensor([x for l in labs for x in l], dtype=torch.long)
    tl = torch.tensor([len(l) for l in labs], dtype=torch.long)
    il = torch.full((n,), lp.shape[0], dtype=torch.long)
    nll = F.ctc_loss(lpi, tg, il, tl, blank=0, reduction='none', zero_infinity=False)
    return (-nll / tl.double() ** ALPHA).numpy()


def cmd_selftest(a):
    """채점식 확인: 정답 자모열을 그대로 내는 로그확률이면 4지에서 정답을 고르고, 균일 로그확률이면 첫 최대 규칙을 따른다."""
    import torch
    from train_lipread import decompose
    rng = np.random.default_rng(0)
    words = ['사과', '바다', '나무', '하늘', '가방', '마음', '구름', '노래']
    ok = 0
    for k in range(40):
        cand = [decompose(w) for w in rng.choice(words, 4, replace=False)]
        tgt = int(rng.integers(4))
        lab = cand[tgt]
        T = 3 * len(lab) + 4
        lp = torch.full((T, 53), -9.0)
        lp[:, 0] = 0.0
        for j, c in enumerate(lab):
            lp[2 + 3 * j, :] = -9.0
            lp[2 + 3 * j, c] = 0.0
        ok += int(np.argmax(ctc_scores(torch.log_softmax(lp, -1), cand)) == tgt)
    print(f'ROI_SELFTEST oracle_pick={ok}/40', flush=True)
    print('ROI_SELFTEST_OK' if ok == 40 else 'ROI_SELFTEST_FAIL', flush=True)
    return 0 if ok == 40 else 1


def score4(front, head, run_or_none, seqs, items, dev, amp, gather):
    """seqs[i] = 전역 프레임 번호(또는 None=못 자름). V1 val_4way와 같은 ctc_ll α=1, 동점은 첫 최대. → {dup: by_spk}"""
    import torch
    import torch.nn.functional as F
    from train_lipread import forward_packed
    front.eval()
    head.eval()
    res = {}
    with torch.no_grad():
        for dup in DUPS:
            hits = defaultdict(list)
            ok = [i for i, s in enumerate(seqs) if s is not None]
            for i, s in enumerate(seqs):
                if s is None:
                    hits[items[i]['spk']].append(0)
            for k in range(0, len(ok), 64):
                ch = ok[k:k + 64]
                X, lens = gather([seqs[i] for i in ch])
                x = normalize(X, lens, None, None, dev)
                lt = torch.from_numpy(lens)
                f = run_front(front, x, lt, amp)
                if dup > 1:
                    f = f.repeat_interleave(dup, 1)
                    lt = lt * dup
                lp = F.log_softmax(forward_packed(head, f, lt).float(), -1)
                for r, i in enumerate(ch):
                    it = items[i]
                    Ti = int(lt[r])
                    sc = ctc_scores(lp[r, :Ti], it['labs'])
                    hits[it['spk']].append(int(int(np.argmax(sc)) == it['tgt']))
            res[dup] = {s: float(np.mean(v)) for s, v in hits.items()}
    return res


def val_cer(front, head, run, dev, amp, gather, cap=0):
    import torch
    from train_lipread import forward_packed, greedy_decode, cer
    front.eval()
    head.eval()
    items = run.val_sent[:cap] if cap else run.val_sent
    cs = []
    with torch.no_grad():
        for k in range(0, len(items), 16):
            ch = items[k:k + 16]
            X, lens = gather([run.gidx(ci, np.arange(run.T[ci])) for ci, _ in ch])
            x = normalize(X, lens, None, None, dev)
            lt = torch.from_numpy(lens)
            lo = forward_packed(head, run_front(front, x, lt, amp), lt).float().cpu()
            for j, (_, tg) in enumerate(ch):
                cs.append(cer(greedy_decode(lo[j, :int(lens[j])]), tg))
    return float(np.mean(cs)) if cs else float('nan')


# ───────────────────────────── 학습 공통 ─────────────────────────────
def setup(a):
    import random
    import torch
    torch.manual_seed(a.seed)
    np.random.seed(a.seed)
    random.seed(a.seed)
    torch.backends.cudnn.benchmark = bool(int(os.environ.get('ROI_CUDNN_BENCH', '0')))
    dev = 'cuda' if torch.cuda.is_available() else 'cpu'
    if dev == 'cuda' and getattr(a, 'gpu_frac', 0):
        torch.cuda.set_per_process_memory_fraction(a.gpu_frac)
    return dev


def rng_state(rng):
    import random
    import torch
    st = {'np': rng.bit_generator.state, 'py': random.getstate(), 'torch': torch.get_rng_state()}
    if torch.cuda.is_available():
        st['cuda'] = torch.cuda.get_rng_state_all()
    return st


def rng_restore(rng, st):
    import random
    import torch
    rng.bit_generator.state = st['np']
    random.setstate(st['py'])
    torch.set_rng_state(st['torch'])
    if 'cuda' in st and torch.cuda.is_available():
        torch.cuda.set_rng_state_all(st['cuda'])


def save_atomic(obj, path):
    import torch
    torch.save(obj, path + '.tmp')
    os.replace(path + '.tmp', path)


def mem_note(dev):
    import torch
    if dev != 'cuda':
        return ''
    return f'gpu_peak={torch.cuda.max_memory_allocated() / 2**30:.2f}G reserved={torch.cuda.max_memory_reserved() / 2**30:.2f}G'


# ───────────────────────────── train(R1, R2 미세조정) ─────────────────────────────
def cmd_train(a):
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from train_lipread import VOCAB, forward_packed
    t0 = time.time()
    dev = setup(a)
    rng = np.random.default_rng(a.seed)
    os.makedirs(a.out, exist_ok=True)
    run = Run(a.run)
    front, head, _ = build_models(len(VOCAB))
    front.ckpt = a.ckpt_front
    if a.init:
        ck = torch.load(a.init, map_location='cpu', weights_only=False)
        front.load_state_dict(ck['front'])
        log(f'[train] 전단 초기화 ← {a.init} (사전학습 ep{ck["meta"]["epoch"]})')
    front.to(dev)
    head.to(dev)
    params = list(front.parameters()) + list(head.parameters())
    log(f'[train] cand={a.cand} seed={a.seed} params front={sum(p.numel() for p in front.parameters()) / 1e6:.2f}M '
        f'head={sum(p.numel() for p in head.parameters()) / 1e6:.2f}M sent={len(run.sent)} words={len(run.words)} '
        f'val_items={len(run.val_items)} dev={dev} amp={a.amp}')
    opt = torch.optim.AdamW(params, lr=a.lr, weight_decay=1e-4)
    ctc = nn.CTCLoss(blank=0, zero_infinity=True)
    best, best_ep, bad, hist, start = -1.0, -1, 0, [], 0
    lastp = os.path.join(a.out, 'last.pt')
    if a.resume and os.path.exists(lastp):
        ck = torch.load(lastp, map_location='cpu', weights_only=False)
        front.load_state_dict(ck['front'])
        head.load_state_dict(ck['head'])
        opt.load_state_dict(ck['opt'])
        best, best_ep, bad, hist, start = ck['best'], ck['best_ep'], ck['bad'], ck['hist'], ck['epoch'] + 1
        rng_restore(rng, ck['rng'])
        log(f'[train] 이어 하기: ep{start}부터 (best ep{best_ep} {best:.4f}, bad={bad})')
        if ck.get('stopped'):
            start = a.epochs
    vitems = run.val_items[:a.max_val] if a.max_val else run.val_items
    vseqs = [None if it['win'] is None else np.array([run.off[ci] + min(f, run.T[ci] - 1) for ci, f in it['win']], np.int64)
             for it in vitems]

    def gather(gl):
        X, lens, _, _, _ = make_batch(run, gl)
        return X, lens

    def batches(items):
        for k in range(0, len(items), a.batch):
            ch = items[k:k + a.batch]
            gl, tg = [], []
            for kind, it in ch:
                if kind == 's':
                    ci, t = it
                    g = run.gidx(ci, np.arange(run.T[ci]))
                else:
                    ci, s0, s1, t = it
                    g = run.gidx(ci, np.arange(s0, s1))
                    if rng.random() < a.idle_p:
                        g = idle_window_idx(run, g, run.spk[ci], rng)
                g = g[speed_idx(len(g), rng)]
                gl.append(g)
                tg.append(t)
            X, lens, flips, tmask, _ = make_batch(run, gl, rng)
            yield X, lens, flips, tmask, tg
    stop_now = start >= a.epochs
    for ep in range(start, a.epochs):
        front.train()
        head.train()
        if dev == 'cuda':
            torch.cuda.reset_peak_memory_stats()
        items = [('s', (s[0], s[1])) for s in run.sent] + [('w', tuple(w)) for w in run.words]
        items = chunked_order(items, run, rng)
        if a.max_items:
            items = items[:a.max_items]
        te = time.time()
        tl, nb, nfr = 0.0, 0, 0
        for X, lens, flips, tmask, tg in Prefetch(batches(items)):
            opt.zero_grad(set_to_none=True)
            B = len(lens)
            loss_sum = 0.0
            for g in frame_groups(lens, a.max_frames):           # 프레임이 많은 배치만 나눠 기울기를 모은다(평균은 같음)
                Lg = lens[g]
                Tg = int(math.ceil(Lg.max() / 4.0) * 4)
                x = normalize(X[g, :Tg], Lg, flips[g], tmask[g, :Tg], dev)
                lt = torch.from_numpy(Lg)
                f = run_front(front, x, lt, a.amp)
                logp = F.log_softmax(forward_packed(head, f, lt).float(), -1).transpose(0, 1)
                tgg = [tg[i] for i in g]
                tgt = torch.from_numpy(np.concatenate([np.asarray(t, np.int64) for t in tgg])).to(dev)
                tlen = torch.tensor([len(t) for t in tgg], dtype=torch.int64)
                loss = ctc(logp, tgt, lt, tlen) * (len(g) / B)
                loss.backward()
                loss_sum += float(loss.item())
            torch.nn.utils.clip_grad_norm_(params, 5.0)
            opt.step()
            loss = torch.tensor(loss_sum)
            tl += loss.item()
            nb += 1
            nfr += int(lens.sum())
            if a.log_every and nb % a.log_every == 0:
                log(f'  ep{ep} b{nb} ctc={tl / nb:.3f} {nfr / (time.time() - te):.0f} fr/s {mem_note(dev)}')
        t_ep = time.time() - te
        rec = {'epoch': ep, 'train_ctc': round(tl / max(nb, 1), 4), 'ep_sec': round(t_ep), 'frames': nfr,
               'sec': round(time.time() - t0)}
        if ep % a.eval_every == a.eval_every - 1 or ep == a.epochs - 1:
            tv = time.time()
            by = score4(front, head, run, vseqs, vitems, dev, a.amp, gather)
            acc = {d: float(np.mean(list(by[d].values()))) if by[d] else float('nan') for d in DUPS}
            m = float(np.mean([acc[d] for d in DUPS]))
            vc = val_cer(front, head, run, dev, a.amp, gather, a.max_val)
            rec.update(val_4way={str(d): round(acc[d], 4) for d in DUPS}, val_4way_mean=round(m, 4), val_cer=round(vc, 4),
                       val_sec=round(time.time() - tv))
            log(f'ep{ep:3d} ctc={rec["train_ctc"]:.3f} val4 dup2={acc[2]:.3f} dup1={acc[1]:.3f} mean={m:.3f} cer={vc:.3f} '
                f'ep {t_ep:.0f}s val {rec["val_sec"]}s {mem_note(dev)}')
            hist.append(rec)
            if m > best:
                best, best_ep, bad = m, ep, 0
                meta = {'cand': a.cand, 'seed': a.seed, 'epoch': ep, 'val_4way': rec['val_4way'], 'val_4way_mean': m,
                        'val_cer': rec['val_cer'], 'run': os.path.abspath(a.run), 'bench_id': run.meta['bench_id'],
                        'batch': a.batch, 'lr': a.lr, 'idle_p': a.idle_p, 'init': a.init, 'crop': CROP}
                save_atomic({'front': {k: v.detach().cpu() for k, v in front.state_dict().items()},
                             'head': {k: v.detach().cpu() for k, v in head.state_dict().items()},
                             'vocab': VOCAB, 'meta': meta, 'best_by_spk': {str(d): by[d] for d in DUPS}},
                            os.path.join(a.out, 'model.pt'))
            else:
                bad += 1
                if bad >= a.patience:
                    log(f'조기 종료: {a.patience}회 검증 동안 나아지지 않음')
                    stop_now = True
        else:
            log(f'ep{ep:3d} ctc={rec["train_ctc"]:.3f} ep {t_ep:.0f}s {mem_note(dev)}')
            hist.append(rec)
        save_atomic({'front': front.state_dict(), 'head': head.state_dict(), 'opt': opt.state_dict(), 'epoch': ep,
                     'best': best, 'best_ep': best_ep, 'bad': bad, 'hist': hist, 'rng': rng_state(rng), 'stopped': stop_now},
                    lastp)
        if stop_now:
            break
    if best_ep < 0:
        print('ROI_TRAIN_FAIL 검증 기록 없음', flush=True)
        return 1
    ck = torch.load(os.path.join(a.out, 'model.pt'), map_location='cpu', weights_only=False)
    bh = [h for h in hist if h['epoch'] == best_ep]
    summ = {'cand': a.cand, 'seed': a.seed, 'best_epoch': best_ep, 'best_val_4way_mean': best, 'best': bh[0] if bh else None,
            'best_by_spk': ck['best_by_spk'], 'history': hist, 'n_sent': len(run.sent), 'n_words': len(run.words),
            'n_val_items': len(vitems), 'time_sec': round(time.time() - t0), 'device': dev, 'init': a.init,
            'max_items': a.max_items, 'max_val': a.max_val}
    wjson(summ, os.path.join(a.out, 'train_summary.json'), indent=1)
    print(f'ROI_TRAIN_DONE cand={a.cand} seed={a.seed} best_ep={best_ep} val4_mean={best:.4f} → {a.out}/model.pt', flush=True)
    return 0


# ───────────────────────────── teacher(WavLM) ─────────────────────────────
def cmd_teacher(a):
    import torch
    import soundfile as sf
    from transformers import WavLMModel
    t0 = time.time()
    run = Run(a.run)
    dev = 'cuda' if torch.cuda.is_available() else 'cpu'
    m = WavLMModel.from_pretrained(a.model).to(dev).eval()
    D = m.config.hidden_size
    tp = os.path.join(a.run, 'pack', 'wavlm_f16.bin')
    todo = [i for i, c in enumerate(run.clips) if c['role'] == 'train' and c['wav'] and os.path.exists(c['wav'])]
    mm = np.memmap(tp + '.tmp', np.float16, 'w+', shape=(run.meta['frames'], D))
    sums, cnts = defaultdict(lambda: np.zeros(D, np.float64)), defaultdict(int)
    feats = {}
    with torch.no_grad():
        for k, i in enumerate(todo):
            c = run.clips[i]
            w, sr = sf.read(c['wav'], dtype='float32', always_2d=False)
            if w.ndim > 1:
                w = w.mean(1)
            if sr != 16000:
                import librosa
                w = librosa.resample(w, orig_sr=sr, target_sr=16000)
            w = (w - w.mean()) / (w.std() + 1e-7)          # Wav2Vec2FeatureExtractor(do_normalize)와 같음
            x = torch.from_numpy(w)[None].to(dev)
            with torch.autocast('cuda', dtype=torch.float16, enabled=dev == 'cuda'):
                hs = m(x, output_hidden_states=True).hidden_states[a.layer][0].float().cpu().numpy()   # (N50,D)
            n50, T = len(hs), c['T']
            t_roi = np.arange(T) / FPS                     # ROI 프레임 시각(초)
            t50 = (np.arange(n50) + 0.5) * 0.02            # WavLM 프레임 가운데(20 ms 보폭)
            f = np.stack([np.interp(t_roi, t50, hs[:, d]) for d in range(D)], 1).astype(np.float32)
            feats[i] = f
            sums[c['spk']] += f.sum(0)
            cnts[c['spk']] += T
            if (k + 1) % 500 == 0:
                log(f'[teacher] {k + 1}/{len(todo)} {time.time() - t0:.0f}s')
    for i, f in feats.items():
        c = run.clips[i]
        mu = (sums[c['spk']] / max(cnts[c['spk']], 1)).astype(np.float32)
        mm[c['off']:c['off'] + c['T']] = (f - mu).astype(np.float16)
    mm.flush()
    del mm
    os.replace(tp + '.tmp', tp)
    wjson({'dim': D, 'layer': a.layer, 'model': a.model, 'clips': sorted(feats), 'norm': '화자 평균 빼기',
           'interp': '50 Hz 가운데 시각 → 30 fps 선형'}, tp + '.json')
    print(f'ROI_TEACHER_OK clips={len(feats)}/{sum(c["role"] == "train" for c in run.clips)} dim={D} '
          f'{time.time() - t0:.0f}s', flush=True)
    return 0


# ───────────────────────────── pretrain(R2 1단계) ─────────────────────────────
def cmd_pretrain(a):
    import torch
    import torch.nn.functional as F
    t0 = time.time()
    dev = setup(a)
    rng = np.random.default_rng(a.seed + 1000)
    os.makedirs(a.out, exist_ok=True)
    run = Run(a.run)
    if run.teach is None:
        print('ROI_PRE_FAIL 교사 특징 없음(teacher 먼저)', flush=True)
        return 1
    D = run.teach.shape[1]
    front, _, proj = build_models(53, D)
    front.ckpt = a.ckpt_front
    front.to(dev)
    proj.to(dev)
    params = list(front.parameters()) + list(proj.parameters())
    opt = torch.optim.AdamW(params, lr=a.lr, weight_decay=1e-4)
    items = [i for i in range(len(run.clips)) if run.has_teach[i] and run.clips[i]['vfrac'] >= 0.5 and run.T[i] >= 10]
    lastp = os.path.join(a.out, 'pre_last.pt')
    start, hist = 0, []
    if a.resume and os.path.exists(lastp):
        ck = torch.load(lastp, map_location='cpu', weights_only=False)
        front.load_state_dict(ck['front'])
        proj.load_state_dict(ck['proj'])
        opt.load_state_dict(ck['opt'])
        start, hist = ck['epoch'] + 1, ck['hist']
        rng_restore(rng, ck['rng'])
        log(f'[pre] 이어 하기: ep{start}부터')
    log(f'[pre] seed={a.seed} clips={len(items)} D={D} epochs={a.epochs} dev={dev}')
    for ep in range(start, a.epochs):
        front.train()
        proj.train()
        if dev == 'cuda':
            torch.cuda.reset_peak_memory_stats()
        order = [x[1] for x in chunked_order([('s', (i,)) for i in items], run, rng)]
        if a.max_items:
            order = order[:a.max_items]

        def batches():
            for k in range(0, len(order), a.batch):
                gl = [run.gidx(i[0], np.arange(run.T[i[0]])) for i in order[k:k + a.batch]]
                yield make_batch(run, gl, rng, with_teacher=True)
        te = time.time()
        tl, nb = 0.0, 0
        for X, lens, flips, _, tch in Prefetch(batches()):
            opt.zero_grad(set_to_none=True)
            NF = float(lens.sum())
            loss_sum = 0.0
            for g in frame_groups(lens, a.max_frames):
                Lg = lens[g]
                Tg = int(math.ceil(Lg.max() / 4.0) * 4)
                x = normalize(X[g, :Tg], Lg, flips[g], None, dev)
                lt = torch.from_numpy(Lg)
                y = proj(run_front(front, x, lt, a.amp))
                tgt = torch.from_numpy(tch[g, :Tg]).to(dev)
                msk = (torch.arange(y.shape[1], device=dev)[None, :] < lt.to(dev)[:, None])
                yv, tv = y[msk], tgt[msk]
                # 전체 배치 프레임 평균과 같아지도록 프레임 수 비율로 가중
                loss = ((yv - tv).abs().mean(-1) + (1.0 - F.cosine_similarity(yv, tv, dim=-1))).sum() / NF
                loss.backward()
                loss_sum += float(loss.item())
            torch.nn.utils.clip_grad_norm_(params, 5.0)
            opt.step()
            loss = torch.tensor(loss_sum)
            tl += loss.item()
            nb += 1
            if a.log_every and nb % a.log_every == 0:
                log(f'  pre ep{ep} b{nb} loss={tl / nb:.4f} {mem_note(dev)}')
        rec = {'epoch': ep, 'loss': round(tl / max(nb, 1), 5), 'ep_sec': round(time.time() - te)}
        hist.append(rec)
        log(f'pre ep{ep:3d} loss={rec["loss"]:.4f} ep {rec["ep_sec"]}s {mem_note(dev)}')
        save_atomic({'front': front.state_dict(), 'proj': proj.state_dict(), 'opt': opt.state_dict(), 'epoch': ep,
                     'hist': hist, 'rng': rng_state(rng)}, lastp)
    save_atomic({'front': {k: v.detach().cpu() for k, v in front.state_dict().items()},
                 'meta': {'epoch': a.epochs - 1, 'seed': a.seed, 'hist': hist, 'run': os.path.abspath(a.run)}},
                os.path.join(a.out, 'pre.pt'))
    print(f'ROI_PRE_DONE seed={a.seed} epochs={a.epochs} loss={hist[-1]["loss"] if hist else float("nan"):.4f} '
          f'{time.time() - t0:.0f}s → {a.out}/pre.pt', flush=True)
    return 0


# ───────────────────────────── select ─────────────────────────────
def cmd_select(a):
    rows = []
    for order, d in enumerate([x for x in a.runs.split(',') if x]):
        s = json.load(open(os.path.join(d, 'train_summary.json'), encoding='utf-8'))
        for dj, dup in enumerate(DUPS):
            rows.append((-s['best']['val_4way'][str(dup)], order, dj, d, dup, s['cand'], s['seed'], s['best_epoch']))
    rows.sort()
    r = rows[0]
    out = {'rule': '각 실행 최고 체크포인트에서 (실행, dup) 중 검증 4지 최대, 동점은 R1 s0, s1, R2 s0, s1 순서·dup2 먼저',
           'selected': {'run': r[3], 'model': os.path.join(r[3], 'model.pt'), 'dup': r[4], 'cand': r[5], 'seed': r[6],
                        'epoch': r[7], 'val_4way': -r[0]},
           'table': [{'run': x[3], 'cand': x[5], 'seed': x[6], 'dup': x[4], 'epoch': x[7], 'val_4way': -x[0]}
                     for x in sorted(rows, key=lambda x: (x[1], x[2]))]}
    wjson(out, a.out, indent=1)
    print(f"ROI_SELECT run={r[3]} cand={r[5]} seed={r[6]} dup={r[4]} val4={-r[0]:.4f}", flush=True)
    return 0


# ───────────────────────────── p4(채점 경로) ─────────────────────────────
def load_model(path, dev):
    import torch
    ck = torch.load(path, map_location='cpu', weights_only=False)
    front, head, _ = build_models(len(ck['vocab']))
    front.load_state_dict(ck['front'])
    head.load_state_dict(ck['head'])
    return front.to(dev).eval(), head.to(dev).eval(), ck


def cmd_p4(a):
    import torch
    from d_bench import Bench
    from train_lipread import MOUTH_KEYS
    t0 = time.time()
    spks = {s for s in a.speakers.split(',') if s}
    if a.eval_list and os.path.exists(a.eval_list):
        ev = set(read_list(a.eval_list))
        if spks & ev and not a.judge:
            print(f'ROI_P4_FAIL 평가 화자 {len(spks & ev)}명이 들어 있음(판정 때만 --judge)', flush=True)
            return 1
    elif not a.judge:
        print('ROI_P4_FAIL --eval-list(평가 화자 목록)이 없어 평가 화자 여부를 확인할 수 없음', flush=True)
        return 1
    dev = 'cuda' if torch.cuda.is_available() else 'cpu'
    b = Bench(a.bench)
    cols = [b.bs_names.index(k) for k in MOUTH_KEYS]
    lead, tail = rest_runs_idx(b, cols, spks)
    items = h4_items(b, spks)
    if a.max_items:
        items = items[:a.max_items]
    cache = {}

    def roi_of(ci):
        if ci not in cache:
            p = os.path.join(a.npz, b.clips[ci]['clip'] + '.npz')
            cache[ci] = np.load(p)['roi'] if os.path.exists(p) else None
        return cache[ci]
    seqs, n_unseg, n_miss = [], 0, 0
    for it in items:
        w = p4_window(b, it['inst'], cols, lead, tail)
        if w is None:
            n_unseg += 1
            seqs.append(None)
            continue
        fr = []
        for ci, f in w:
            r = roi_of(ci)
            if r is None:
                fr = None
                break
            fr.append(r[min(f, len(r) - 1)])
        if fr is None:
            n_miss += 1
        seqs.append(None if fr is None else np.stack(fr))

    def gather(gl):
        L = max(len(g) for g in gl)
        Tp = int(math.ceil(L / 4.0) * 4)
        c0 = (S_ROI - CROP) // 2
        X = np.zeros((len(gl), Tp, CROP, CROP), np.uint8)
        for i, g in enumerate(gl):
            X[i, :len(g)] = g[:, c0:c0 + CROP, c0:c0 + CROP]
        return X, np.array([len(g) for g in gl], np.int64)
    front, head, ck = load_model(a.model, dev)
    by = score4(front, head, None, seqs, items, dev, a.amp, gather)
    if not items:
        print('ROI_P4_FAIL 문항 0개(화자가 벤치에 없음?)', flush=True)
        return 1
    acc = {str(d): float(np.mean(list(by[d].values()))) if by[d] else float('nan') for d in DUPS}
    out = {'model': os.path.abspath(a.model), 'bench_id': b.bench_id, 'speakers': sorted(spks), 'n_items': len(items),
           'unseg': n_unseg, 'roi_missing': n_miss, 'acc_4way_hard': acc, 'by_spk': {str(d): by[d] for d in DUPS},
           'iids': [it['iid'] for it in items], 'judge': bool(a.judge), 'time_sec': round(time.time() - t0, 1)}
    wjson(out, a.out, indent=1)
    print(f'ROI_P4_DONE items={len(items)} unseg={n_unseg} roi_missing={n_miss} → {a.out}', flush=True)
    return 0


# ───────────────────────────── export ─────────────────────────────
def weight_int8(src, dst, min_elems=1024):
    """가중치만 int8(출력 채널별 대칭 눈금) + DequantizeLinear로 바꾼다. 계산은 float 그대로라 ConvInteger 같은
    정수 연산자가 필요 없다(onnxruntime CPU·WASM 모두 DequantizeLinear·Conv·GRU만 쓰면 된다). 파일 크기만 약 4분의 1."""
    import onnx
    from onnx import numpy_helper, helper
    m = onnx.load(src)
    g = m.graph
    users = defaultdict(list)
    for n in g.node:
        for k, x in enumerate(n.input):
            users[x].append((n.op_type, k))
    new_init, new_nodes = [], []
    for init in list(g.initializer):
        w = numpy_helper.to_array(init)
        if w.dtype != np.float32 or w.size < min_elems or not users.get(init.name):
            new_init.append(init)
            continue
        ax = 0 if w.ndim >= 2 else None
        if ax is None:
            new_init.append(init)
            continue
        red = tuple(range(1, w.ndim))
        sc = (np.abs(w).max(axis=red) / 127.0).astype(np.float32)
        sc[sc == 0] = 1.0
        qw = np.clip(np.round(w / sc.reshape((-1,) + (1,) * (w.ndim - 1))), -127, 127).astype(np.int8)
        qn, sn, zn = init.name + '_q', init.name + '_s', init.name + '_z'
        new_init += [numpy_helper.from_array(qw, qn), numpy_helper.from_array(sc, sn),
                     numpy_helper.from_array(np.zeros(len(sc), np.int8), zn)]
        new_nodes.append(helper.make_node('DequantizeLinear', [qn, sn, zn], [init.name], axis=0, name=init.name + '_dq'))
    del g.initializer[:]
    g.initializer.extend(new_init)
    nodes = new_nodes + list(g.node)
    del g.node[:]
    g.node.extend(nodes)
    if m.opset_import[0].version < 13:
        m.opset_import[0].version = 13
    onnx.checker.check_model(m)
    onnx.save(m, dst)


def cmd_export(a):
    import torch
    import torch.nn as nn
    import onnxruntime as ort
    front, head, ck = load_model(a.model, 'cpu')

    class Wrap(nn.Module):
        """roi [B,T,80,80] 0~255 float(가운데 80×80, 패딩 없음) → logits [B,T,53]. 정규화는 학습과 같다(시퀀스별 z)."""

        def __init__(s):
            super().__init__()
            s.front, s.head = front, head

        def forward(s, roi):
            x = roi / 255.0
            mean = x.mean(dim=(1, 2, 3), keepdim=True)
            xc = x - mean
            sd = (xc * xc).mean(dim=(1, 2, 3), keepdim=True).sqrt().clamp(min=1e-2)
            x = (xc / sd).unsqueeze(1)
            B, T = roi.shape[0], roi.shape[1]
            h = s.front.c3(x).transpose(1, 2).reshape(B * T, 24, x.shape[3] // 2, x.shape[4] // 2)
            v = torch.nn.functional.max_pool2d(torch.relu(s.front.b3(h)), 3, 2, 1)
            for st in s.front.stages:
                v = st(v)
            f = s.front.fc(v.mean(dim=(2, 3))).reshape(B, T, 256)
            return s.head(f)
    w = Wrap().eval()
    x = torch.from_numpy(np.random.default_rng(0).integers(0, 256, (1, 75, CROP, CROP)).astype(np.float32))
    with torch.no_grad():
        ref = w(x).numpy()
        lt = torch.tensor([75])
        X = x.numpy().astype(np.uint8)
        ref2 = head(front(normalize(X, np.array([75]), None, None, 'cpu'), lt)).numpy()
    d_wrap = float(np.abs(ref - ref2).max())
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    torch.onnx.export(w, x, a.out, input_names=['roi'], output_names=['logits'],
                      dynamic_axes={'roi': {0: 'B', 1: 'T'}, 'logits': {0: 'B', 1: 'T'}}, opset_version=17, dynamo=False)
    q = os.path.splitext(a.out)[0] + '.int8.onnx'
    weight_int8(a.out, q)
    o32 = ort.InferenceSession(a.out, providers=['CPUExecutionProvider']).run(['logits'], {'roi': x.numpy()})[0]
    s8 = ort.InferenceSession(q, providers=['CPUExecutionProvider'])
    t1 = time.time()
    o8 = s8.run(['logits'], {'roi': x.numpy()})[0]
    t8 = time.time() - t1
    mb32, mb8 = os.path.getsize(a.out) / 2**20, os.path.getsize(q) / 2**20
    res = {'wrap_vs_train_maxdiff': d_wrap, 'fp32_maxdiff': float(np.abs(ref - o32).max()),
           'int8_argmax_agree': float((o8.argmax(-1) == ref.argmax(-1)).mean()), 'fp32_mb': round(mb32, 2),
           'int8_mb': round(mb8, 2), 'int8_cpu_sec_75fr': round(t8, 3), 'size_ok': mb8 <= 20.0}
    wjson(res, os.path.splitext(a.out)[0] + '.export.json', indent=1)
    ok = res['size_ok'] and d_wrap < 1e-3 and res['fp32_maxdiff'] < 1e-3
    print(('ROI_EXPORT_OK ' if ok else 'ROI_EXPORT_FAIL ') + json.dumps(res, ensure_ascii=False), flush=True)
    return 0 if ok else 1


# ───────────────────────────── probe(메모리·시간) ─────────────────────────────
def cmd_probe(a):
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from train_lipread import VOCAB, forward_packed
    dev = setup(a)
    run = Run(a.run)
    front, head, proj = build_models(len(VOCAB), 768)
    front.ckpt = a.ckpt_front
    front.to(dev), head.to(dev), proj.to(dev)
    params = list(front.parameters()) + list(head.parameters())
    opt = torch.optim.AdamW(params, lr=3e-4, weight_decay=1e-4)
    ctc = nn.CTCLoss(blank=0, zero_infinity=True)
    rng = np.random.default_rng(0)
    longest = np.argsort(-run.T)[:a.batch]
    L = int(run.T[longest].max())
    worst = [run.gidx(int(ci), np.round(np.linspace(0, run.T[ci] - 1, int(run.T[ci] * 1.25))).astype(np.int64))
             for ci in longest]                                  # 가장 긴 문장 32개를 속도 0.8배로 늘린 최악 배치
    typ = [run.gidx(int(run.sent[i][0]), np.arange(run.T[run.sent[i][0]]))
           for i in rng.permutation(len(run.sent))[:a.batch]]
    tg = [np.array(run.sent[0][1], np.int64)] * a.batch
    front.eval()
    with torch.no_grad():                                       # 이어 붙인 Conv3d = 시퀀스별 Conv3d 확인
        X, lens, _, _, _ = make_batch(run, typ[:3])
        x = normalize(X, lens, None, None, dev)
        fb = front(x, torch.from_numpy(lens))
        d = 0.0
        for i in range(3):
            xi = normalize(X[i:i + 1, :lens[i]], lens[i:i + 1], None, None, dev)
            fi = front(xi, torch.from_numpy(lens[i:i + 1]))
            d = max(d, float((fb[i, :lens[i]] - fi[0]).abs().max()))
    print(f'ROI_PROBE stem_concat_vs_single_maxdiff={d:.2e}', flush=True)
    front.train()
    for name, gl in (('typical', typ), ('worst', worst)):
        if dev == 'cuda':
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
        t1 = time.time()
        X, lens, flips, tmask, _ = make_batch(run, gl, rng)
        t_io = time.time() - t1
        ts = []
        for k in range(4):
            t1 = time.time()
            opt.zero_grad()
            for g in frame_groups(lens, a.max_frames):
                Lg = lens[g]
                Tg = int(math.ceil(Lg.max() / 4.0) * 4)
                x = normalize(X[g, :Tg], Lg, flips[g], tmask[g, :Tg], dev)
                lt = torch.from_numpy(Lg)
                f = run_front(front, x, lt, a.amp)
                logp = F.log_softmax(forward_packed(head, f, lt).float(), -1).transpose(0, 1)
                tgg = [tg[i] for i in g]
                loss = ctc(logp, torch.from_numpy(np.concatenate(tgg)).to(dev), lt, torch.tensor([len(t) for t in tgg]))
                (loss * len(g) / len(lens)).backward()
            opt.step()
            if dev == 'cuda':
                torch.cuda.synchronize()
            ts.append(time.time() - t1)
        nf = int(lens.sum())
        print(f'ROI_PROBE {name} batch={len(gl)} maxT={int(lens.max())} frames={nf} io={t_io:.2f}s step={min(ts[1:]):.2f}s '
              f'gpu {nf / min(ts[1:]):.0f} fr/s {mem_note(dev)} ckpt_front={a.ckpt_front} amp={a.amp}', flush=True)
    return 0


# ───────────────────────────── all(순서대로 하나씩) ─────────────────────────────
def cmd_all(a):
    import subprocess
    py = sys.executable
    me = os.path.abspath(__file__)
    R = a.run
    seeds = [int(s) for s in a.seeds.split(',')]
    common = ['--batch', str(a.batch), '--max-frames', str(a.max_frames)] + (['--ckpt-front'] if a.ckpt_front else []) + \
             (['--max-items', str(a.max_items)] if a.max_items else []) + (['--gpu-frac', str(a.gpu_frac)] if a.gpu_frac else [])

    def done(path, mark):
        return os.path.exists(path) and mark in open(path, encoding='utf-8', errors='replace').read()

    def step(name, args, mark):
        lp = os.path.join(R, 'logs', name + '.log')
        os.makedirs(os.path.dirname(lp), exist_ok=True)
        if done(lp, mark):
            log(f'[all] {name} 끝남, 건너뜀')
            return
        log(f'[all] {name} 시작')
        with open(lp, 'a', encoding='utf-8') as f:
            p = subprocess.run([py, '-u', me] + args, stdout=f, stderr=subprocess.STDOUT)
        if p.returncode != 0 or not done(lp, mark):
            print(f'ROI_ALL_FAIL {name} rc={p.returncode} ({lp})', flush=True)
            sys.exit(1)
        log(f'[all] {name} 끝 ' + open(lp, encoding='utf-8', errors='replace').read().strip().splitlines()[-1][:160])
    if a.wait_roi:
        lg = 'D:/liplab/roi/logs/roi_extract.log'
        while not (os.path.exists(lg) and 'ROI_LOOP_DONE' in open(lg, encoding='utf-8', errors='replace').read()):
            log('[all] ROI 추출 끝(ROI_LOOP_DONE) 기다림')
            time.sleep(600)
    if not os.path.exists(os.path.join(R, 'prep.json')):
        step('prep', ['prep', '--bench', a.bench, '--split', a.split, '--npz', a.npz, '--out', R] +
             sum([['--extra', x] for x in a.extra], []) + (['--max-clips', str(a.max_clips)] if a.max_clips else []),
             'ROI_PREP_OK')
    if 'R2' in a.cands:
        step('teacher', ['teacher', '--run', R, '--model', a.teacher_model], 'ROI_TEACHER_OK')
    runs = []
    order = [(c, s) for s in seeds for c in ('R1', 'R2') if c in a.cands]
    ep = ['--epochs', str(a.epochs)] if a.epochs else []
    for c, s in order:
        out = os.path.join(R, f'run_{c}s{s}')
        if c == 'R2':
            step(f'pre_s{s}', ['pretrain', '--run', R, '--seed', str(s), '--out', out, '--resume'] + common +
                 (['--epochs', str(a.pre_epochs)] if a.pre_epochs else []), 'ROI_PRE_DONE')
        step(f'train_{c}s{s}', ['train', '--run', R, '--cand', c, '--seed', str(s), '--out', out, '--resume'] + common + ep +
             (['--init', os.path.join(out, 'pre.pt')] if c == 'R2' else []) +
             (['--max-val', str(a.max_val)] if a.max_val else []), 'ROI_TRAIN_DONE')
    sel_order = [os.path.join(R, f'run_{c}s{s}') for c in ('R1', 'R2') for s in seeds if c in a.cands]
    runs = ','.join(sel_order)
    step('select', ['select', '--runs', runs, '--out', os.path.join(R, 'sel.json')], 'ROI_SELECT')
    print(f'ROI_ALL_OK runs={runs}', flush=True)
    return 0


# ───────────────────────────── main ─────────────────────────────
def _train_common(p):
    p.add_argument('--run', required=True)
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--batch', type=int, default=32)
    p.add_argument('--lr', type=float, default=3e-4)
    p.add_argument('--amp', type=int, default=1, help='전단 bf16 자동혼합정밀(1 = 켬)')
    p.add_argument('--ckpt-front', action='store_true', help='전단 단계별 기울기 체크포인트(메모리 절약, 결과 같음)')
    p.add_argument('--gpu-frac', type=float, default=float(os.environ.get('ROI_GPU_FRAC', '0.45')),
                   help='이 프로세스 GPU 메모리 상한 비율(12 GB의 0.45 = 약 5.4 GB, 캐시가 이 위로 쌓이지 않게, 0 = 없음)')
    p.add_argument('--max-items', type=int, default=0, help='시험용: 에폭당 항목 상한')
    p.add_argument('--log-every', type=int, default=50)
    p.add_argument('--resume', action='store_true')
    p.add_argument('--max-frames', type=int, default=int(os.environ.get('ROI_MAX_FRAMES', '4000')),
                   help='한 번에 GPU에 올리는 유효 프레임 상한(넘으면 배치를 나눠 기울기를 모음, 배치 크기·평균은 그대로)')


def main(argv=None):
    ap = argparse.ArgumentParser(description='독화 ① 입술 영역 화소 전단 R1·R2')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('prep')
    p.add_argument('--bench', required=True)
    p.add_argument('--split', required=True)
    p.add_argument('--npz', required=True)
    p.add_argument('--extra', action='append', default=[])
    p.add_argument('--out', required=True)
    p.add_argument('--max-clips', type=int, default=0, help='시험용: 학습 화자 클립 수 상한')
    p.add_argument('--dry', action='store_true', help='pack을 쓰지 않고 항목·프레임 수만 센다(시간 추정용)')
    t = sub.add_parser('teacher')
    t.add_argument('--run', required=True)
    t.add_argument('--model', default='microsoft/wavlm-base-plus')
    t.add_argument('--layer', type=int, default=9)
    p = sub.add_parser('pretrain')
    _train_common(p)
    p.add_argument('--out', required=True)
    p.add_argument('--epochs', type=int, default=20)
    p = sub.add_parser('train')
    _train_common(p)
    p.add_argument('--cand', choices=['R1', 'R2'], required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--init', default=None)
    p.add_argument('--epochs', type=int, default=60)
    p.add_argument('--eval-every', type=int, default=2)
    p.add_argument('--patience', type=int, default=10)
    p.add_argument('--idle-p', type=float, default=0.5)
    p.add_argument('--max-val', type=int, default=0, help='시험용: 검증 문항 상한')
    p = sub.add_parser('select')
    p.add_argument('--runs', required=True)
    p.add_argument('--out', required=True)
    p = sub.add_parser('p4')
    p.add_argument('--model', required=True)
    p.add_argument('--bench', required=True)
    p.add_argument('--npz', required=True)
    p.add_argument('--speakers', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--eval-list', default='D:/liplab/repo/scripts/lipread_v1/eval40.txt')
    p.add_argument('--judge', action='store_true')
    p.add_argument('--max-items', type=int, default=0)
    p.add_argument('--amp', type=int, default=1)
    p = sub.add_parser('export')
    p.add_argument('--model', required=True)
    p.add_argument('--out', required=True)
    sub.add_parser('selftest')
    p = sub.add_parser('probe')
    _train_common(p)
    p = sub.add_parser('all')
    p.add_argument('--run', required=True)
    p.add_argument('--bench', default='D:/liplab/v1/dax/v1/bench_v1.pkl')
    p.add_argument('--split', default='D:/liplab/v1/dax/v1/split.json')
    p.add_argument('--npz', default='D:/liplab/roi/npz')
    p.add_argument('--extra', action='append', default=None)
    p.add_argument('--seeds', default='0,1')
    p.add_argument('--cands', default='R1,R2')
    p.add_argument('--teacher-model', default='microsoft/wavlm-base-plus')
    p.add_argument('--batch', type=int, default=32)
    p.add_argument('--ckpt-front', action='store_true')
    p.add_argument('--gpu-frac', type=float, default=float(os.environ.get('ROI_GPU_FRAC', '0.45')))
    p.add_argument('--max-frames', type=int, default=int(os.environ.get('ROI_MAX_FRAMES', '4000')))
    p.add_argument('--wait-roi', action='store_true')
    p.add_argument('--max-clips', type=int, default=0)
    p.add_argument('--max-items', type=int, default=0)
    p.add_argument('--max-val', type=int, default=0)
    p.add_argument('--epochs', type=int, default=0, help='0 = 등록값(60)')
    p.add_argument('--pre-epochs', type=int, default=0, help='0 = 등록값(20)')
    a = ap.parse_args(argv)
    if a.cmd == 'all' and a.extra is None:
        L = 'D:/liplab/lab/data'
        a.extra = [f'{L}/v1_538r', f'{L}/e538r', f'{L}/roi538/a', f'{L}/roi538/b']
    fn = {'prep': cmd_prep, 'teacher': cmd_teacher, 'pretrain': cmd_pretrain, 'train': cmd_train, 'select': cmd_select,
          'p4': cmd_p4, 'export': cmd_export, 'probe': cmd_probe, 'all': cmd_all, 'selftest': cmd_selftest}[a.cmd]
    try:
        rc = fn(a)
    except SystemExit:
        raise
    except Exception as ex:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        print(f'ROI_{a.cmd.upper()}_FAIL {type(ex).__name__}: {str(ex)[:300]}', flush=True)
        rc = 1
    sys.exit(rc)


if __name__ == '__main__':
    main()
