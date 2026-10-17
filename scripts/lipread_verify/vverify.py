"""V-verify: 입모양 목표 검증(사전등록 docs/lipread-verify-2026-10.md).

    python vverify.py explore --dax D:/liplab/v1/dax      # 탐색(검증 화자 12명) → 선택·동결(vverify/frozen.json)
    python vverify.py confirm --dax D:/liplab/v1/dax      # 확인(평가 화자 40명), 한 번

d_bench 도구(DAX 폴더의 d_bench.py·train_lipread.py)를 읽기만 한다. 클립별 점수와 가중치는 DAX/vverify/에 둔다.
"""
import argparse
import hashlib
import json
import math
import os
import sys
import time
from collections import defaultdict

import numpy as np

SEED_TAG = 'vverify'
N_COHORT = 30
RIDGE_ALPHA = 10.0
LAMBDAS = (0.25, 0.5, 1.0, 2.0)
ORDER = ('A1', 'A2', 'A3', 'A4', 'B1', 'F')
FRR_TARGET = 0.20
CLS = 'BAIUEWC'
CLASS_OF = {}
for ch in 'ㅂㅃㅍㅁ':
    CLASS_OF[ch] = 'B'
for ch in 'ㅏㅐㅑㅒ':
    CLASS_OF[ch] = 'A'
for ch in 'ㅣㅔㅖ':
    CLASS_OF[ch] = 'I'
for ch in 'ㅗㅛㅜㅠ':
    CLASS_OF[ch] = 'U'
for ch in 'ㅓㅕㅡ':
    CLASS_OF[ch] = 'E'
for ch in 'ㅘㅙㅚㅝㅞㅟㅢ':
    CLASS_OF[ch] = 'W'
for ch in 'ㄷㄸㅌㄴㄹㅅㅆㄱㄲㅋㅎㅈㅉㅊㄳㄵㄶㄺㄻㄼㄽㄾㄿㅀㅄ':
    CLASS_OF[ch] = 'C'
PROFILE = 'BAIUEW'    # B1이 예측하는 부류 개수


def crc(s):
    return int(hashlib.sha256(s.encode('utf-8')).hexdigest()[:12], 16)


def n_syl(w):
    return sum(1 for ch in w if 0xAC00 <= ord(ch) <= 0xD7A3)


def auc(pos, neg):
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    if len(pos) == 0 or len(neg) == 0:
        return float('nan')
    allv = np.concatenate([pos, neg])
    u, inv, cnt = np.unique(allv, return_inverse=True, return_counts=True)
    start = np.concatenate([[0], np.cumsum(cnt)[:-1]])
    ranks = (start + (cnt + 1) / 2.0)[inv]        # 동점은 평균 순위
    rp = ranks[:len(pos)].sum()
    return float((rp - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def boot_auc(pos_by, neg_by, B, seed=0):
    spks = sorted(set(pos_by) & set(neg_by))
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(B):
        pick = rng.integers(0, len(spks), len(spks))
        p = np.concatenate([pos_by[spks[k]] for k in pick])
        n = np.concatenate([neg_by[spks[k]] for k in pick])
        vals.append(auc(p, n))
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]


class Ctx:
    def __init__(self, dax):
        sys.path.insert(0, dax)
        import d_bench as DB
        from train_lipread import VOCAB, decompose
        self.DB, self.VOCAB, self.decompose = DB, VOCAB, decompose
        self.dax = dax
        v1 = os.path.join(dax, 'v1')
        self.split = json.load(open(os.path.join(v1, 'split.json'), encoding='utf-8'))
        self.sel = json.load(open(os.path.join(v1, 'sel.json'), encoding='utf-8'))['selected']
        t0 = time.time()
        self.bench = DB.Bench(os.path.join(v1, 'bench_v1.pkl'))
        print(f'bench {self.bench.bench_id} {time.time() - t0:.0f}s', flush=True)
        self.runner = None
        self.cols = None
        self.pool = list(self.bench.dist_words)
        self.pset = set(self.pool)
        self.dis = DB.Distractors(self.bench, self.pool)
        self._cls = {}
        by_n = defaultdict(list)
        for v in self.pool:
            by_n[n_syl(v)].append(v)
        self.by_n = by_n
        self.cohort = {n: [v for _, v in sorted((crc(f'{SEED_TAG}|cohort|{n}|{v}'), v) for v in vs)][:N_COHORT + 1]
                       for n, vs in by_n.items()}
        # 자모 → 부류 사상(53 → 8, 0 = blank·공백·ㅇ)
        self.jmap = np.zeros(len(VOCAB), np.int64)
        for i, ch in enumerate(VOCAB):
            c = CLASS_OF.get(ch)
            self.jmap[i] = 0 if c is None else 1 + CLS.index(c)

    def load_runner(self):
        import torch
        torch.set_num_threads(4)
        self.runner = self.DB.CTCRunner(os.path.join(self.dax, self.sel['model']), None)
        self.cols = [self.bench.bs_names.index(k) for k in self.runner.keys]
        self.lead, self.tail = self.DB._rest_runs(self.bench, self.cols)

    def labels(self, w):
        return list(self.decompose(w))

    def cls_seq(self, w):
        if w not in self._cls:
            self._cls[w] = [int(c) for c in self.jmap[self.labels(w)] if c > 0]
        return self._cls[w]

    def cls_str(self, w):
        return ''.join(CLS[c - 1] for c in self.cls_seq(w))

    def counts(self, w):
        s = self.cls_str(w)
        return np.array([s.count(c) for c in PROFILE], float)

    def instances(self, spks):
        ss = set(spks)
        return [it for it in self.bench.inst if it['ok'] and it['w'] in self.pset and it['spk'] in ss]

    def window(self, it):
        cnt = defaultdict(int)
        return self.DB.p4_sequences(self.bench, it, self.cols, 'idle75', 1, 'wide', self.lead, self.tail, cnt)

    def set_swap_pool(self, insts):
        self.swap_by_n = defaultdict(list)
        for it in insts:
            self.swap_by_n[n_syl(it['w'])].append(it['w'])

    def claims(self, it):
        w = it['w']
        cw = self.cls_str(w)
        n = n_syl(w)
        other = [v for _, v in sorted((crc(f'{SEED_TAG}|other|{it["iid"]}|{v}'), v)
                                      for v in self.by_n[n] if v != w and self.cls_str(v) != cw)][:3]
        hard = self.dis.hard(w)
        near = [v for v in hard if self.cls_str(v) != cw]
        homo = [v for v in hard if self.cls_str(v) == cw]
        pool = self.swap_by_n[n]
        cand = sorted((crc(f'{SEED_TAG}|swap|{it["iid"]}|{k}'), k) for k in range(len(pool)))
        swap = []
        for _, k in cand:
            v = pool[k]
            if v != w and self.cls_str(v) != cw:
                swap.append(v)
            if len(swap) == 3:
                break
        return other, near, homo, swap


# ── B1 특징 ──────────────────────────────────────────────────────────────────
def b1_feats(X, cols_names):
    ref = np.median(X, 0)
    D = X - ref
    f = [D.max(0), D.mean(0), X.std(0)]
    ic = cols_names.index('mouthClose')
    ip = [cols_names.index('mouthPressLeft'), cols_names.index('mouthPressRight')]
    c = X[:, ic] + X[:, ip].mean(1)
    c = np.convolve(np.pad(c, (1, 1), mode='edge'), np.ones(3) / 3, mode='valid')
    med, mx = np.median(c), c.max()
    thr = med + 0.5 * (mx - med)
    peaks = sum(1 for t in range(1, len(c) - 1) if c[t] > thr and c[t] >= c[t - 1] and c[t] > c[t + 1])
    act = np.abs(D).mean(1)
    lo, hi = act.min(), act.max()
    alen = float((act > lo + 0.2 * (hi - lo)).sum()) if hi > lo else 0.0
    return np.concatenate(f + [np.array([peaks, alen])])


def fit_b1(ctx, train_spks):
    names = list(ctx.runner.keys)
    Xs, Ys = [], []
    FO = ctx.DB.FO
    held = set(ctx.split['val']) | set(ctx.split['eval'])
    held_txt = {FO.norm_text(c['text']) for c in ctx.bench.clips if c['spk'] in held}
    n_drop = 0
    for it in ctx.instances(train_spks):
        if FO.norm_text(ctx.bench.clips[it['c']]['text']) in held_txt:   # 내용 분리(V1 3.3절과 같은 규칙)
            n_drop += 1
            continue
        X = ctx.window(it)
        if X is None or len(X) < 10:
            continue
        Xs.append(b1_feats(X, names))
        Ys.append(ctx.counts(it['w']))
    F, Y = np.array(Xs), np.array(Ys)
    mu, sd = F.mean(0), F.std(0) + 1e-6
    Z = (F - mu) / sd
    ym = Y.mean(0)
    W = np.linalg.solve(Z.T @ Z + RIDGE_ALPHA * np.eye(Z.shape[1]), Z.T @ (Y - ym))
    res = Y - (Z @ W + ym)
    var = res.var(0) + 1e-6
    r2 = 1 - res.var(0) / (Y.var(0) + 1e-9)
    print(f'B1 fit n={len(F)} drop_shared={n_drop} R2 ' + ' '.join(f'{c}:{r:.2f}' for c, r in zip(PROFILE, r2)), flush=True)
    return {'mu': mu.tolist(), 'sd': sd.tolist(), 'W': W.tolist(), 'ym': ym.tolist(), 'var': var.tolist(),
            'r2': dict(zip(PROFILE, map(float, r2))), 'n': len(F), 'n_drop_shared_text': n_drop}


# ── 점수 ─────────────────────────────────────────────────────────────────────
def score_set(ctx, spks, b1):
    DB = ctx.DB
    names = list(ctx.runner.keys)
    mu, sd, W, ym, var = (np.array(b1[k]) for k in ('mu', 'sd', 'W', 'ym', 'var'))
    insts = ctx.instances(spks)
    ctx.set_swap_pool(insts)
    rows = []          # (spk, iid, kind, w, t, A1, A2, A3, A4, B1)
    n_null = 0
    t0 = time.time()
    for bi in range(0, len(insts), 64):
        chunk = insts[bi:bi + 64]
        seqs = [ctx.window(it) for it in chunk]
        ok = [s is not None and len(s) >= 10 for s in seqs]
        lg = ctx.runner.logits([s if o else None for s, o in zip(seqs, ok)])
        for it, X, o, L in zip(chunk, seqs, ok, lg):
            if not o:
                n_null += 1
                continue
            lp = DB.log_softmax_np(L)
            # 부류 공간 사후확률
            P = np.exp(lp)
            Pc = np.zeros((P.shape[0], 1 + len(CLS)))
            np.add.at(Pc.T, ctx.jmap, P.T)
            lpc = np.log(np.maximum(Pc, 1e-30))
            best = float(lp.max(1).sum())
            pred = (b1_feats(X, names) - mu) / sd @ W + ym
            other, near, homo, swap = ctx.claims(it)
            claims = [('pos', it['w'])] + [('other', t) for t in other] + [('near', t) for t in near] + \
                     [('homo', t) for t in homo] + [('swap', t) for t in swap]
            words = {t for _, t in claims}
            ns = {n_syl(t) for t in words}
            coh_words = {v for n in ns for v in ctx.cohort[n]}
            allw = sorted(words | coh_words)
            ll = dict(zip(allw, DB.ctc_loglik_multi(lp, [ctx.labels(v) for v in allw])))
            cl_seqs = {v: ctx.cls_seq(v) for v in allw}
            llc = dict(zip(allw, DB.ctc_loglik_multi(lpc, [cl_seqs[v] for v in allw])))
            for kind, t in claims:
                n = n_syl(t)
                coh = [v for v in ctx.cohort[n] if v != t][:N_COHORT]
                a = np.array([ll[v] for v in coh])
                ac = np.array([llc[v] for v in coh])
                lmx = lambda z: float(np.logaddexp.reduce(z) - math.log(len(z)))
                L_t = len(ctx.labels(t))
                s1 = ll[t] / L_t
                s2 = (ll[t] - best) / L_t
                s3 = ll[t] - lmx(a)
                s4 = llc[t] - lmx(ac)
                s5 = -float((((pred - ctx.counts(t)) ** 2) / var).sum())
                rows.append((it['spk'], it['iid'], kind, it['w'], t, s1, s2, s3, s4, s5))
        if bi % 1280 == 0:
            print(f'  {bi}/{len(insts)} {time.time() - t0:.0f}s', flush=True)
    return rows, n_null, len(insts)


def to_arrays(rows):
    spk = np.array([r[0] for r in rows])
    kind = np.array([r[2] for r in rows])
    S = np.array([r[5:10] for r in rows], float)
    return spk, kind, {k: S[:, i] for i, k in enumerate(('A1', 'A2', 'A3', 'A4', 'B1'))}


def metrics(spk, kind, s, theta=None, B=0, rows=None, ctx=None):
    pos, oth, near, homo = (kind == 'pos'), (kind == 'other'), (kind == 'near'), (kind == 'homo')
    swp = (kind == 'swap')
    out = {'auc_swap': auc(s[pos], s[swp]), 'auc_other': auc(s[pos], s[oth]), 'auc_near': auc(s[pos], s[near]),
           'n_swap': int(swp.sum()),
           'n_pos': int(pos.sum()), 'n_other': int(oth.sum()), 'n_near': int(near.sum()), 'n_homo': int(homo.sum())}
    if B:
        pb = {k: s[pos & (spk == k)] for k in set(spk)}
        ob = {k: s[oth & (spk == k)] for k in set(spk)}
        nb = {k: s[near & (spk == k)] for k in set(spk)}
        sb = {k: s[swp & (spk == k)] for k in set(spk)}
        out['ci_swap'] = boot_auc(pb, sb, B)
        out['ci_other'] = boot_auc(pb, ob, min(B, 2000))
        out['ci_near'] = boot_auc(pb, nb, min(B, 2000))
        per = [auc(pb[k], sb[k]) for k in sorted(pb)]
        out['spk_auc_swap'] = {'median': float(np.median(per)), 'q25': float(np.percentile(per, 25)),
                                'q75': float(np.percentile(per, 75)), 'min': float(min(per)), 'max': float(max(per))}
    if theta is not None:
        out['frr'] = float((s[pos] < theta).mean())
        out['flag_swap'] = float((s[swp] < theta).mean())
        out['flag_other'] = float((s[oth] < theta).mean())
        out['flag_near'] = float((s[near] < theta).mean())
        out['flag_homo'] = float((s[homo] < theta).mean()) if homo.any() else None
    if rows is not None and ctx is not None:
        # 부류별 신뢰도(N_near 짝, 목표와 실제 단어의 부류 개수가 다른 것)
        diff = {'B 닫힘': [0], 'U+W 원순': [3, 5], 'A 벌림': [1], 'I 평순': [2]}
        cat = {}
        idx_near = np.nonzero(near)[0]
        for name, ks in diff.items():
            sel = [i for i in idx_near if sum(ctx.counts(rows[i][3])[k] for k in ks) != sum(ctx.counts(rows[i][4])[k] for k in ks)]
            cat[name] = {'n': len(sel), 'auc': auc(s[pos], s[sel]) if sel else None}
        out['near_by_class'] = cat
        nsy = np.array([n_syl(r[4]) for r in rows])
        out['auc_swap_by_nsyl'] = {int(n): {'n_pos': int((pos & (nsy == n)).sum()),
                                            'auc': auc(s[pos & (nsy == n)], s[swp & (nsy == n)])}
                                    for n in sorted(set(nsy[pos])) if (pos & (nsy == n)).sum() >= 30}
    return out


def zstats(x):
    return float(x.mean()), float(x.std() + 1e-9)


def cmd_explore(a):
    ctx = Ctx(a.dax)
    ctx.load_runner()
    out_dir = os.path.join(a.dax, 'vverify')
    os.makedirs(out_dir, exist_ok=True)
    b1 = fit_b1(ctx, ctx.split['train'])
    rows, n_null, n_inst = score_set(ctx, ctx.split['val'], b1)
    json.dump(rows, open(os.path.join(out_dir, 'explore_rows.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    spk, kind, S = to_arrays(rows)
    res = {k: metrics(spk, kind, v, B=a.boot) for k, v in S.items()}
    bestA = max(('A1', 'A2', 'A3', 'A4'), key=lambda k: (res[k]['auc_swap'], -ORDER.index(k)))
    zA, zB = zstats(S[bestA]), zstats(S['B1'])
    fbest = None
    for lam in LAMBDAS:
        f = (S[bestA] - zA[0]) / zA[1] + lam * (S['B1'] - zB[0]) / zB[1]
        m = metrics(spk, kind, f)
        res[f'F_l{lam}'] = m
        if fbest is None or m['auc_swap'] > fbest[1]['auc_swap']:
            fbest = (lam, m, f)
    S['F'] = fbest[2]
    res['F'] = metrics(spk, kind, S['F'], B=a.boot)
    # 선택: 합동 AUC_other 최고, 0.005 안이면 ORDER 앞의 것
    top = max(res[k]['auc_swap'] for k in ORDER)
    chosen = [k for k in ORDER if res[k]['auc_swap'] >= top - 0.005][0]
    theta = float(np.percentile(S[chosen][kind == 'pos'], 100 * FRR_TARGET))
    res_ch = metrics(spk, kind, S[chosen], theta=theta, B=a.boot, rows=rows, ctx=ctx)
    frozen = {'chosen': chosen, 'theta': theta, 'bestA': bestA, 'lambda': fbest[0], 'zA': zA, 'zB': zB, 'b1': b1,
              'model': ctx.sel['model'], 'n_cohort': N_COHORT, 'bench_id': ctx.bench.bench_id}
    blob = json.dumps(frozen, sort_keys=True, ensure_ascii=False)
    frozen['sha256'] = hashlib.sha256(blob.encode('utf-8')).hexdigest()
    json.dump(frozen, open(os.path.join(out_dir, 'frozen.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    summ = {'phase': 'explore', 'speakers': ctx.split['val'], 'n_inst': n_inst, 'n_null': n_null,
            'cands': {k: {kk: vv for kk, vv in v.items()} for k, v in res.items()}, 'chosen': chosen,
            'chosen_detail': res_ch, 'frozen_sha256': frozen['sha256'], 'lambda': fbest[0], 'bestA': bestA,
            'b1_r2': b1['r2'], 'theta': theta}
    json.dump(summ, open(os.path.join(out_dir, 'explore_summary.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('VV_EXPLORE ' + json.dumps({k: [round(res[k]['auc_swap'], 4), round(res[k]['auc_other'], 4),
                                          round(res[k]['auc_near'], 4)] for k in res}), flush=True)
    print('VV_CHOSEN_DETAIL ' + json.dumps({k: res_ch[k] for k in ('frr', 'flag_swap', 'flag_other', 'flag_near',
                                                                    'flag_homo', 'ci_swap', 'spk_auc_swap')}), flush=True)
    print(f'VV_CHOSEN {chosen} theta={theta:.4f} sha={frozen["sha256"][:12]}', flush=True)
    return 0


def cmd_confirm(a):
    ctx = Ctx(a.dax)
    ctx.load_runner()
    out_dir = os.path.join(a.dax, 'vverify')
    frozen = json.load(open(os.path.join(out_dir, 'frozen.json'), encoding='utf-8'))
    if os.path.exists(os.path.join(out_dir, 'confirm_summary.json')) and not a.force:
        print('VV_CONFIRM_ALREADY (한 번만)', flush=True)
        return 2
    rows, n_null, n_inst = score_set(ctx, ctx.split['eval'], frozen['b1'])
    json.dump(rows, open(os.path.join(out_dir, 'confirm_rows.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    spk, kind, S = to_arrays(rows)
    zA, zB = frozen['zA'], frozen['zB']
    S['F'] = (S[frozen['bestA']] - zA[0]) / zA[1] + frozen['lambda'] * (S['B1'] - zB[0]) / zB[1]
    ch = frozen['chosen']
    main = metrics(spk, kind, S[ch], theta=frozen['theta'], B=10000, rows=rows, ctx=ctx)
    others = {k: metrics(spk, kind, v) for k, v in S.items()}
    ok = (main['auc_swap'] >= 0.75 and main['ci_swap'][0] > 0.70 and main['frr'] <= 0.30 and main['flag_swap'] >= 0.50)
    summ = {'phase': 'confirm', 'n_speakers': len(set(spk)), 'n_inst': n_inst, 'n_null': n_null, 'chosen': ch,
            'frozen_sha256': frozen['sha256'], 'main': main, 'all_cands': others, 'pass': bool(ok),
            'rule': 'AUC_swap >= 0.75, CI 하한 > 0.70, θ에서 FRR <= 0.30, N_swap 표시율 >= 0.50(9.2절 수정)'}
    json.dump(summ, open(os.path.join(out_dir, 'confirm_summary.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'VV_CONFIRM {ch} auc_swap={main["auc_swap"]:.4f} ci={main["ci_swap"]} frr={main["frr"]:.3f} '
          f'flag={main["flag_swap"]:.3f} auc_other={main["auc_other"]:.4f} auc_near={main["auc_near"]:.4f} pass={ok}', flush=True)
    print('VV_ALL ' + json.dumps({k: [round(v['auc_swap'], 4), round(v['auc_other'], 4), round(v['auc_near'], 4)]
                                  for k, v in others.items()}), flush=True)
    return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument('cmd', choices=['explore', 'confirm'])
    p.add_argument('--dax', default='D:/liplab/v1/dax')
    p.add_argument('--boot', type=int, default=2000)
    p.add_argument('--force', action='store_true')
    a = p.parse_args()
    return cmd_explore(a) if a.cmd == 'explore' else cmd_confirm(a)


if __name__ == '__main__':
    sys.exit(main())
