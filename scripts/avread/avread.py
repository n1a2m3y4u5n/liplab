#!/usr/bin/env python3
"""아바타 기계 판독 곡선(실험 ①, docs/avatar-readability-2026-10.md). 사전 등록한 문항·조건·울타리·선택·판정을 그대로 코드로 옮겼다.

입모양 표(V1·V15·V3) × 크기(턱 jaw, 입술 lip)로 앱 단어를 렌더하고(scripts/v2_render 하네스), 렌더 영상에서 ROI 독화기와 같은
입술 영역(lip_roi_extract.py 기본값)을 잘라 10/21 판정을 넘은 독화기(R2 s0 int8 ONNX)로 4지 hard ctc_ll 판독을 잰다.

하위명령(데스크탑, PYTHONUTF8=1, LIPLAB_TOOLS = D:/liplab/v1/dax)
  items   --backend B --bench P --out items.json          앱 2단계 풀 → 300낱말(탐색 150·확인 150), 엔진 프레임, 4지 보기
  fence-sents --sel V2SEL --backend B --out fence.json      울타리 문장 30개(V2 기본 얼굴 문장)와 엔진 프레임
  jobs    --items I --fence F --split explore|confirm --conds all|이름,… --out jobs.json [--fence-jobs]
  score   --items I --split S --npz DIR --renders DIR --onnx M --conds … --out score.json   4지 판독(낱말별 정오)
  fence   --fence F --renders DIR --bs DIR --conds … --v2 … --v3 … --out fence_eval.json  양순 닫힘·2.0배 위쪽 진폭
  select  --score S --fence E --out sel.json               관문 0 → 울타리 → 탐색 4지 최고
  judge   --score S --sel J --out judge.json               확인 한 번: 고른 조건 − V1 j1.0 l1.0
  real    --items I --bench P --npz ROI --eval-list E --onnx M --out real.json   보고만: 같은 낱말의 실제 화자(평가 40명) 정확도
  selftest
표식: AVR_ITEMS_OK, AVR_JOBS_OK, AVR_SCORE_OK, AVR_FENCE_OK, AVR_SELECT, AVR_JUDGE, *_FAIL
"""
import argparse
import asyncio
import hashlib
import json
import math
import os
import sys
import time
import unicodedata

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.environ.get('LIPLAB_TOOLS', 'D:/liplab/v1/dax')
for p in (TOOLS, os.path.join(HERE, '..'), os.path.join(HERE, '..', 'lipread_roi')):
    if p not in sys.path:
        sys.path.insert(0, p)

SEED = 'liplab-avread-2026-10'
N_ITEMS = 300
N_FENCE = 30
TABLES = ('V1', 'V15', 'V3')
GRID_GLOBAL = (0.6, 0.8, 1.0, 1.3, 1.6, 2.0)
GRID_SPLIT = ((0.6, 1.6), (1.6, 0.6), (1.0, 1.6), (1.6, 1.0), (1.0, 0.6), (0.6, 1.0))
BASE = 'V1_j1.0_l1.0'
WORD_LEAD_MS = WORD_TAIL_MS = 1500
FENCE_LEAD_MS = FENCE_TAIL_MS = 400
IDLE_LEN, EDGE, REST_GAP, FPS = 75, 6, 3, 30.0
S_ROI, CROP = 88, 80
GATE0_LO = 0.25
PASS_DELTA = 0.05
FENCE_BILABIAL = 0.95
FENCE_MAX_ABOVE = 2
N_BOOT = 10000


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def wjson(obj, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or '.', exist_ok=True)
    tmp = f'{path}.tmp{os.getpid()}'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def sha(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def cond_name(t, j, l):
    return f'{t}_j{j:.1f}_l{l:.1f}'


def all_conds():
    out = []
    for t in TABLES:
        for g in GRID_GLOBAL:
            out.append((cond_name(t, g, g), t, g, g))
        for j, l in GRID_SPLIT:
            out.append((cond_name(t, j, l), t, j, l))
    return out


def parse_cond(name):
    t, j, l = name.split('_')
    return t, float(j[1:]), float(l[1:])


def pick_conds(arg):
    names = [c[0] for c in all_conds()]
    if arg in ('', 'all'):
        return names
    out = [x for x in arg.split(',') if x]
    bad = [x for x in out if x not in names]
    if bad:
        raise SystemExit(f'모르는 조건: {bad}')
    return out


def engine_frames(backend, texts):
    sys.path.insert(0, os.path.abspath(backend))
    import engine
    return {t: asyncio.run(engine.text_to_visemes(t)) for t in texts}


# ───────────────────────────── 문항 ─────────────────────────────
def app_pool(backend):
    """앱 2단계 서빙 풀(main._stage2_table과 같은 규칙): 단어 은행 − 표준검사 단어 − STAGE2_EXCLUDED, 순서 유지·중복 제거."""
    sys.path.insert(0, os.path.abspath(backend))
    import curriculum
    import assessment
    tw = set(assessment.test_only_words())
    ex = set(getattr(curriculum, 'STAGE2_EXCLUDED', {}))
    pool = []
    for w in curriculum.WORD_BANK:
        w = unicodedata.normalize('NFC', w['word']).strip()
        if w and w not in tw and w not in ex and w not in pool:
            pool.append(w)
    return pool


def split_items(pool):
    """sha256(SEED|낱말) 오름차순 앞 300개, 같은 순서의 짝수 순위 = 탐색, 홀수 순위 = 확인."""
    order = sorted(pool, key=lambda w: sha(f'{SEED}|{w}'))[:N_ITEMS]
    return [{'rank': r, 'w': w, 'split': 'explore' if r % 2 == 0 else 'confirm'} for r, w in enumerate(order)]


def cmd_items(a):
    from d_bench import Bench, Distractors
    from train_lipread import decompose
    pool = app_pool(a.backend)
    items = split_items(pool)
    b = Bench(a.bench)
    dis = Distractors(b, list(b.dist_words))
    fr = engine_frames(a.backend, [it['w'] for it in items])
    for it in items:
        w = it['w']
        cands = Distractors.order([w] + dis.hard(w), f'avread|{w}')
        it['cands'] = cands
        it['tgt'] = cands.index(w)
        it['labs'] = [decompose(c) for c in cands]
        it['frames'] = fr[w]
        it['in_eval_vocab'] = w in b.dist_index
        if not all(it['labs']) or not it['frames']:
            print(f'AVR_ITEMS_FAIL 자모나 엔진 프레임이 빈 낱말 {w}', flush=True)
            return 1
    words = [it['w'] for it in items]
    out = {'seed': SEED, 'pool_n': len(pool), 'pool_sha256': sha('\n'.join(pool)), 'bench_id': b.bench_id,
           'dist_words_n': len(b.dist_words), 'items_sha256': sha('\n'.join(f"{it['rank']}\t{it['w']}\t{'|'.join(it['cands'])}" for it in items)),
           'n_explore': sum(it['split'] == 'explore' for it in items), 'n_confirm': sum(it['split'] == 'confirm' for it in items),
           'n_in_eval_vocab': sum(it['in_eval_vocab'] for it in items), 'items': items}
    wjson(out, a.out)
    print(f"AVR_ITEMS_OK pool={len(pool)} items={len(words)} explore={out['n_explore']} confirm={out['n_confirm']} "
          f"in_eval_vocab={out['n_in_eval_vocab']} items_sha256={out['items_sha256'][:16]}", flush=True)
    return 0


def cmd_fence_sents(a):
    sel = json.load(open(a.sel, encoding='utf-8'))
    seen, sents = set(), []
    for e in sel['sentences']:
        if e.get('default') and e['sid'] not in seen:
            seen.add(e['sid'])
            sents.append({'sid': e['sid'], 'text': unicodedata.normalize('NFC', e['text']).strip()})
    sents = sorted(sents, key=lambda e: sha(f"{SEED}|fence|{e['sid']}"))[:N_FENCE]
    fr = engine_frames(a.backend, [e['text'] for e in sents])
    for e in sents:
        e['frames'] = fr[e['text']]
    out = {'n': len(sents), 'sha256': sha('\n'.join(e['sid'] for e in sents)), 'sents': sents}
    wjson(out, a.out)
    print(f"AVR_FENCE_SENTS_OK n={len(sents)} sha256={out['sha256'][:16]}", flush=True)
    return 0


# ───────────────────────────── 렌더 작업 ─────────────────────────────
def amp_of(name):
    t, j, l = parse_cond(name)
    return {'table': t, 'jaw': j, 'lip': l}


def cmd_jobs(a):
    conds = pick_conds(a.conds)
    jobs = []
    if a.fence_jobs:
        fe = json.load(open(a.fence, encoding='utf-8'))
        for c in conds:
            for e in fe['sents']:
                for sp in (1.0, 2.0):
                    jobs.append({'id': f"fs_{e['sid']}_{c}_{sp}", 'kind': 'text', 'talker': 'default', 'speed': sp, 'frames': e['frames'],
                                 'amp': amp_of(c), 'leadMs': FENCE_LEAD_MS, 'tailMs': FENCE_TAIL_MS})
    else:
        items = [it for it in json.load(open(a.items, encoding='utf-8'))['items'] if it['split'] == a.split]
        speeds = [float(x) for x in a.speeds.split(',')]
        for c in conds:
            for it in items:
                for sp in speeds:
                    sfx = '' if sp == 1.0 else f'_s{sp}'
                    jobs.append({'id': f"w{it['rank']:03d}_{c}{sfx}", 'kind': 'text', 'talker': 'default', 'speed': sp,
                                 'frames': it['frames'], 'amp': amp_of(c), 'leadMs': WORD_LEAD_MS, 'tailMs': WORD_TAIL_MS})
    wjson(jobs, a.out)
    print(f'AVR_JOBS_OK n={len(jobs)} conds={len(conds)}', flush=True)
    return 0


# ───────────────────────────── 판독 ─────────────────────────────
def tile(fr, need, from_end):
    if need <= 0:
        return []
    if not len(fr):
        return None
    reps = int(math.ceil(need / float(len(fr))))
    t = np.concatenate([fr] * reps, 0)
    return list(t[-need:] if from_end else t[:need])


def window_idx(n, speech_ms):
    """ROI 판정 창과 같은 규칙: 발화 구간 ±6프레임(문장 끝 규칙), 75프레임보다 짧으면 같은 영상의 쉬는 프레임으로 양쪽을 채운다
    (앞은 [0, 시작−3)의 끝에서, 뒤는 [끝+3, n)의 앞에서, 반씩)."""
    a = int(math.floor(speech_ms[0] * FPS / 1000.0))
    b = int(math.ceil(speech_ms[1] * FPS / 1000.0))
    seg = list(range(max(0, a - EDGE), min(n, b + EDGE)))
    if len(seg) < IDLE_LEN:
        need = IDLE_LEN - len(seg)
        nl, nr = need // 2, need - need // 2
        left = tile(np.arange(0, max(0, a - REST_GAP)), nl, True)
        right = tile(np.arange(min(n, b + REST_GAP), n), nr, False)
        if left is None or right is None:
            return None
        seg = [int(x) for x in left] + seg + [int(x) for x in right]
    return seg


def cmd_score(a):
    import onnxruntime as ort
    import torch
    from roi_train import ctc_scores
    conds = pick_conds(a.conds)
    items = [it for it in json.load(open(a.items, encoding='utf-8'))['items'] if it['split'] == a.split]
    so = ort.SessionOptions()
    so.intra_op_num_threads = a.threads
    so.inter_op_num_threads = 1
    sess = ort.InferenceSession(a.onnx, so, providers=['CPUExecutionProvider'])
    c0 = (S_ROI - CROP) // 2
    res = json.load(open(a.out, encoding='utf-8')) if (a.resume and os.path.exists(a.out)) else {'conds': {}}
    sfx = '' if a.speed == 1.0 else f'_s{a.speed}'
    t0 = time.time()
    for c in conds:
        key = c + sfx
        if key in res['conds'] and len(res['conds'][key]['hit']) == len(items):
            continue
        hit, pick, valid_frac, miss = [], [], [], 0
        for it in items:
            jid = f"w{it['rank']:03d}_{c}{sfx}"
            npz = os.path.join(a.npz, jid + '.npz')
            sch = os.path.join(a.renders, jid + '.sched.json')
            if not (os.path.exists(npz) and os.path.exists(sch)):
                miss += 1
                hit.append(0); pick.append(-1); valid_frac.append(0.0)
                continue
            z = np.load(npz)
            roi, valid = z['roi'], z['valid']
            w = window_idx(len(roi), json.load(open(sch, encoding='utf-8'))['speech'])
            if w is None:
                miss += 1
                hit.append(0); pick.append(-1); valid_frac.append(0.0)
                continue
            vf = float(valid[w].mean())
            valid_frac.append(vf)
            if vf < 0.5:   # ROI 판정 p4_window와 같은 규칙(창의 절반 넘게 얼굴이 없으면 못 자른 문항 = 오답)
                miss += 1
                hit.append(0); pick.append(-1)
                continue
            X = roi[w][:, c0:c0 + CROP, c0:c0 + CROP].astype(np.float32)[None]
            lg = sess.run(['logits'], {'roi': X})[0][0]
            lp = torch.log_softmax(torch.from_numpy(lg).float(), -1)
            sc = ctc_scores(lp, it['labs'])
            k = int(np.argmax(sc))
            pick.append(k)
            hit.append(int(k == it['tgt']))
        res['conds'][key] = {'acc': float(np.mean(hit)), 'hit': hit, 'pick': pick, 'miss': miss,
                             'valid_frac_min': float(np.min(valid_frac)), 'valid_frac_med': float(np.median(valid_frac))}
        res.update({'split': a.split, 'n_items': len(items), 'words': [it['w'] for it in items], 'onnx': os.path.abspath(a.onnx)})
        wjson(res, a.out)
        log(f'AVR_SCORE {key} acc={np.mean(hit):.4f} miss={miss} {time.time() - t0:.0f}s')
    print(f'AVR_SCORE_OK split={a.split} conds={len(conds)} → {a.out}', flush=True)
    return 0


# ───────────────────────────── 울타리 ─────────────────────────────
def human_profiles(a):
    import v2_avatar_validity as V
    import v3_avatar as W
    prof = {}
    for tag, sel_p, al_p, bs in ((('v2',) + tuple(a.v2.split(';'))), (('v3',) + tuple(a.v3.split(';')))):
        sel = json.load(open(sel_p, encoding='utf-8'))
        align = {}
        for l in open(al_p, encoding='utf-8'):
            r = json.loads(l)
            align[r['key']] = r
        rec = W.real_records(sel['clips'], align, bs)
        for s, v in rec.items():
            p = V.profile(v)
            if p:
                prof[f'{tag}:{s}'] = p
    return prof


def fence_one(V, real_prof, ranges, p1, p2):
    out = {}
    for sp, p in (('1.0', p1), ('2.0', p2)):
        lg = V.legibility(real_prof, p) if p else {}
        out[f'bilabial_{sp}'] = lg.get('bilabial_closure_rate')
    above, pct = [], {}
    for g in V.GROUPS:
        if not p2 or g not in p2['amp'] or ranges[g] is None:
            continue
        x = p2['amp'][g]['A']
        pct[g] = round(V.pct_rank(ranges[g]['_vals'], x), 1)
        if x > ranges[g]['p90']:
            above.append(g)
    out['above_p90_2.0'] = above
    out['n_above'] = len(above)
    out['pctA_2.0'] = pct
    out['missing_groups_2.0'] = [g for g in V.GROUPS if not p2 or g not in p2['amp']]
    b1, b2 = out['bilabial_1.0'], out['bilabial_2.0']
    out['pass'] = bool(b1 is not None and b2 is not None and b1 >= FENCE_BILABIAL and b2 >= FENCE_BILABIAL
                       and len(above) <= FENCE_MAX_ABOVE)
    return out


def cmd_fence(a):
    import v2_avatar_validity as V
    fe = json.load(open(a.fence, encoding='utf-8'))
    conds = pick_conds(a.conds)
    real_prof = human_profiles(a)
    profs = list(real_prof.values())
    ranges = {g: V._ranges(profs, g, 'A') for g in V.GROUPS}
    res = {'n_real': len(real_prof), 'n_real_v2': sum(k.startswith('v2:') for k in real_prof),
           'n_real_v3': sum(k.startswith('v3:') for k in real_prof),
           'p90_A': {g: (round(r['p90'], 4) if r else None) for g, r in ranges.items()}, 'conds': {}}
    for c in conds:
        pp = {}
        for sp in ('1.0', '2.0'):
            recs = []
            for e in fe['sents']:
                jid = f"fs_{e['sid']}_{c}_{sp}"
                sp_ = os.path.join(a.renders, jid + '.sched.json')
                bp = os.path.join(a.bs, jid + '.json')
                if not (os.path.exists(sp_) and os.path.exists(bp)):
                    continue
                segs, span = V.segments_from_schedule(json.load(open(sp_, encoding='utf-8')))
                rec, _ = V.clip_record(V.load_series(bp), segs, span)
                if rec:
                    recs.append(rec)
            pp[sp] = (V.profile(recs) if recs else None, len(recs))
        r = fence_one(V, real_prof, ranges, pp['1.0'][0], pp['2.0'][0])
        r['n_clips'] = {'1.0': pp['1.0'][1], '2.0': pp['2.0'][1]}
        res['conds'][c] = r
        log(f"AVR_FENCE {c} pass={r['pass']} bil={r['bilabial_1.0']}/{r['bilabial_2.0']} above={r['above_p90_2.0']} n={r['n_clips']}")
    wjson(res, a.out)
    print(f'AVR_FENCE_OK conds={len(conds)} pass={sum(v["pass"] for v in res["conds"].values())} → {a.out}', flush=True)
    return 0


# ───────────────────────────── 선택·판정 ─────────────────────────────
def boot_ci(x, n=N_BOOT, seed=0):
    x = np.asarray(x, float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), (n, len(x)))
    m = x[idx].mean(1)
    return [float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))]


def tie_key(name):
    t, j, l = parse_cond(name)
    return (max(abs(math.log(j)), abs(math.log(l))), TABLES.index(t))


def select(score, fence):
    sc = score['conds']
    base = sc[BASE]
    g0 = boot_ci(base['hit'])
    out = {'gate0': {'acc': base['acc'], 'ci': g0, 'pass': bool(g0[0] > GATE0_LO)}, 'base': BASE}
    if not out['gate0']['pass']:
        out['selected'] = None
        out['reason'] = '관문 0 미달(V1 j1.0 l1.0 탐색 4지 하한 ≤ 25%)'
        return out
    ok = [c for c in sc if c in fence['conds'] and fence['conds'][c]['pass'] and '_s' not in c.split('_l')[-1]]
    out['fence_pass'] = sorted(ok)
    out['fence_fail'] = sorted(c for c in sc if c in fence['conds'] and not fence['conds'][c]['pass'])
    if not ok:
        out['selected'] = None
        out['reason'] = '울타리를 지킨 조건 없음'
        return out
    best = max(sc[c]['acc'] for c in ok)
    top = sorted([c for c in ok if sc[c]['acc'] == best], key=tie_key)
    out['selected'] = top[0]
    out['selected_acc_explore'] = best
    out['ties'] = top
    return out


def cmd_select(a):
    score = json.load(open(a.score, encoding='utf-8'))
    fence = json.load(open(a.fence, encoding='utf-8'))
    if score.get('split') != 'explore':
        print('AVR_SELECT_FAIL 탐색 점수가 아님', flush=True)
        return 1
    out = select(score, fence)
    out['score_sha256'] = sha(open(a.score, encoding='utf-8').read())
    out['fence_sha256'] = sha(open(a.fence, encoding='utf-8').read())
    wjson(out, a.out)
    print('AVR_SELECT ' + json.dumps({k: out.get(k) for k in ('gate0', 'selected', 'selected_acc_explore', 'reason')}, ensure_ascii=False), flush=True)
    return 0


def judge(score, sel):
    sc = score['conds']
    s = sel['selected']
    b = sc[BASE]
    if s is None:
        return {'selected': None, 'pass': False, 'reason': sel.get('reason')}
    x = sc[s]
    d = np.asarray(x['hit'], float) - np.asarray(b['hit'], float)
    ci = boot_ci(d)
    delta = float(d.mean())
    return {'selected': s, 'acc_selected': x['acc'], 'acc_base': b['acc'], 'ci_selected': boot_ci(x['hit']), 'ci_base': boot_ci(b['hit']),
            'delta': delta, 'delta_ci': ci, 'n_items': len(d), 'n_up': int((d > 0).sum()), 'n_down': int((d < 0).sum()),
            'pass': bool(s != BASE and delta >= PASS_DELTA and ci[0] > 0)}


def cmd_judge(a):
    score = json.load(open(a.score, encoding='utf-8'))
    sel = json.load(open(a.sel, encoding='utf-8'))
    if score.get('split') != 'confirm':
        print('AVR_JUDGE_FAIL 확인 점수가 아님', flush=True)
        return 1
    out = judge(score, sel)
    out['sel_sha256'] = sha(open(a.sel, encoding='utf-8').read())
    wjson(out, a.out)
    print('AVR_JUDGE ' + json.dumps(out, ensure_ascii=False), flush=True)
    return 0


def cmd_real(a):
    """보고만: 문항 낱말 가운데 판독 어휘에도 있는 낱말을 ROI 판정 평가 화자 40명이 말한 어절 문항(같은 창·같은 보기 규칙)으로 같은 ONNX가 읽은 정확도."""
    import onnxruntime as ort
    import torch
    from d_bench import Bench
    from train_lipread import MOUTH_KEYS
    import roi_train as R
    items = json.load(open(a.items, encoding='utf-8'))['items']
    split_of = {it['w']: it['split'] for it in items}
    b = Bench(a.bench)
    spks = set(R.read_list(a.eval_list))
    cols = [b.bs_names.index(k) for k in MOUTH_KEYS]
    lead, tail = R.rest_runs_idx(b, cols, spks)
    h4 = [x for x in R.h4_items(b, spks) if x['w'] in split_of]
    so = ort.SessionOptions()
    so.intra_op_num_threads = a.threads
    sess = ort.InferenceSession(a.onnx, so, providers=['CPUExecutionProvider'])
    c0 = (S_ROI - CROP) // 2
    cache, by_w = {}, {}
    for it in h4:
        w = R.p4_window(b, it['inst'], cols, lead, tail)
        hit = 0
        if w is not None:
            fr = []
            for ci, f in w:
                if ci not in cache:
                    p = os.path.join(a.npz, b.clips[ci]['clip'] + '.npz')
                    cache[ci] = np.load(p)['roi'] if os.path.exists(p) else None
                r = cache[ci]
                if r is None:
                    fr = None
                    break
                fr.append(r[min(f, len(r) - 1)])
            if fr is not None:
                X = np.stack(fr)[:, c0:c0 + CROP, c0:c0 + CROP].astype(np.float32)[None]
                lp = torch.log_softmax(torch.from_numpy(sess.run(['logits'], {'roi': X})[0][0]).float(), -1)
                hit = int(int(np.argmax(R.ctc_scores(lp, it['labs']))) == it['tgt'])
        by_w.setdefault(it['w'], []).append(hit)
    out = {'n_words': len(by_w), 'n_inst': len(h4), 'words': {w: {'split': split_of[w], 'n': len(v), 'acc': float(np.mean(v))} for w, v in by_w.items()}}
    for s in ('explore', 'confirm'):
        ws = [w for w in by_w if split_of[w] == s]
        out[f'acc_word_mean_{s}'] = float(np.mean([np.mean(by_w[w]) for w in ws])) if ws else None
    wjson(out, a.out)
    print(f"AVR_REAL_OK words={len(by_w)} inst={len(h4)} explore={out['acc_word_mean_explore']} confirm={out['acc_word_mean_confirm']}", flush=True)
    return 0


def cmd_selftest(_a):
    ok = True
    # 창: 발화가 짧으면 75프레임, 쉬는 프레임으로 양쪽을 채움
    w = window_idx(150, [1500, 2100])
    ok &= len(w) == 75 and w[0] < 45 and w[-1] >= 63 + EDGE - 1
    # 창: 발화가 길면 채우지 않음
    w2 = window_idx(400, [1500, 4500])
    ok &= len(w2) == (135 + EDGE) - (45 - EDGE)
    # 조건 36개, 이름 왕복
    cs = all_conds()
    ok &= len(cs) == 36 and len({c[0] for c in cs}) == 36 and parse_cond('V15_j0.6_l1.6') == ('V15', 0.6, 1.6)
    # 선택: 울타리 통과 중 최고, 동점은 1에서 덜 먼 쪽
    score = {'conds': {BASE: {'acc': 0.5, 'hit': [1, 0] * 50}, 'V1_j1.3_l1.3': {'acc': 0.6, 'hit': [1] * 60 + [0] * 40},
                       'V3_j1.6_l1.6': {'acc': 0.6, 'hit': [1] * 60 + [0] * 40}, 'V15_j2.0_l2.0': {'acc': 0.9, 'hit': [1] * 90 + [0] * 10}}}
    fence = {'conds': {BASE: {'pass': True}, 'V1_j1.3_l1.3': {'pass': True}, 'V3_j1.6_l1.6': {'pass': True}, 'V15_j2.0_l2.0': {'pass': False}}}
    s = select(score, fence)
    ok &= s['selected'] == 'V1_j1.3_l1.3'
    # 판정: 같은 조건이면 통과 못 함, 확실한 차이는 통과
    cf = {'conds': {BASE: {'acc': 0.3, 'hit': [1] * 30 + [0] * 70}, 'V1_j1.3_l1.3': {'acc': 0.6, 'hit': [1] * 60 + [0] * 40}}}
    ok &= judge(cf, {'selected': 'V1_j1.3_l1.3'})['pass'] and not judge(cf, {'selected': BASE})['pass']
    # 문항 나누기: 결정적, 150·150
    pool = [f'낱말{i}' for i in range(400)]
    it = split_items(pool)
    ok &= len(it) == 300 and sum(x['split'] == 'explore' for x in it) == 150 and it == split_items(list(reversed(pool)))
    print('AVR_SELFTEST_OK' if ok else 'AVR_SELFTEST_FAIL', flush=True)
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description='아바타 기계 판독 곡선(실험 ①)')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('items'); p.add_argument('--backend', required=True); p.add_argument('--bench', required=True); p.add_argument('--out', required=True)
    p = sub.add_parser('fence-sents'); p.add_argument('--sel', required=True); p.add_argument('--backend', required=True); p.add_argument('--out', required=True)
    p = sub.add_parser('jobs')
    p.add_argument('--items'); p.add_argument('--fence'); p.add_argument('--split', default='explore'); p.add_argument('--conds', default='all')
    p.add_argument('--speeds', default='1.0'); p.add_argument('--fence-jobs', action='store_true'); p.add_argument('--out', required=True)
    p = sub.add_parser('score')
    p.add_argument('--items', required=True); p.add_argument('--split', required=True); p.add_argument('--npz', required=True)
    p.add_argument('--renders', required=True); p.add_argument('--onnx', required=True); p.add_argument('--conds', default='all')
    p.add_argument('--speed', type=float, default=1.0); p.add_argument('--threads', type=int, default=2); p.add_argument('--resume', action='store_true')
    p.add_argument('--out', required=True)
    p = sub.add_parser('fence')
    p.add_argument('--fence', required=True); p.add_argument('--renders', required=True); p.add_argument('--bs', required=True)
    p.add_argument('--conds', default='all'); p.add_argument('--v2', required=True, help='sel;align;bs_dir')
    p.add_argument('--v3', required=True, help='sel;align;bs_dir'); p.add_argument('--out', required=True)
    p = sub.add_parser('select'); p.add_argument('--score', required=True); p.add_argument('--fence', required=True); p.add_argument('--out', required=True)
    p = sub.add_parser('judge'); p.add_argument('--score', required=True); p.add_argument('--sel', required=True); p.add_argument('--out', required=True)
    p = sub.add_parser('real')
    p.add_argument('--items', required=True); p.add_argument('--bench', required=True); p.add_argument('--npz', required=True)
    p.add_argument('--eval-list', required=True); p.add_argument('--onnx', required=True); p.add_argument('--threads', type=int, default=2)
    p.add_argument('--out', required=True)
    sub.add_parser('selftest')
    a = ap.parse_args(argv)
    return {'items': cmd_items, 'fence-sents': cmd_fence_sents, 'jobs': cmd_jobs, 'score': cmd_score, 'fence': cmd_fence,
            'select': cmd_select, 'judge': cmd_judge, 'real': cmd_real, 'selftest': cmd_selftest}[a.cmd](a)


if __name__ == '__main__':
    sys.exit(main())
