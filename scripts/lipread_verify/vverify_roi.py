"""입모양 목표 검증 ROI판(사전등록 docs/lipread-verify-roi-2026-10.md).

    python vverify_roi.py align     # 새 인물 8명(N8) 받기 B 클립 정렬(build_cd.align_clip, GPU) → OUT/n8_spans.jsonl, n8_align.json
    python vverify_roi.py explore   # 검증 12명: 창 확인(① 검증 4지 0.5623) → 후보 A1~A4 → 선택·θ → OUT/frozen.json
    python vverify_roi.py confirm   # C-40(평가 40명 재시험)과 C-N8, 한 번만

②의 vverify.py(시도·후보·지표), ①의 roi_train.py(창·모델), V1 벤치 도구(d_bench·build_cd)를 가져다 쓴다.
클립별 점수와 정렬 산출물은 OUT(기본 D:/liplab/roi/vverify)에 둔다.
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

HERE = os.path.dirname(os.path.abspath(__file__))
DAX = os.environ.get('LIPLAB_TOOLS', 'D:/liplab/v1/dax')
for p in (DAX, HERE, os.path.join(HERE, '..', 'lipread_roi')):
    if p not in sys.path:
        sys.path.insert(0, p)

import vverify as VV          # noqa: E402
import roi_train as RT        # noqa: E402

DATA = 'D:/liplab/lab/data'
N8 = ['spk313', 'spk314', 'spk479', 'spk487', 'spk491', 'spk496', 'spk497', 'spk499']
N8_PERSON = {'spk313': 'C190', 'spk314': 'C254', 'spk479': 'E241', 'spk487': 'C657', 'spk491': 'C402',
             'spk496': 'C630', 'spk497': 'C432', 'spk499': 'C796'}
CANDS = ('A1', 'A2', 'A3', 'A4')
VAL4_REF = 0.5623            # ① sel.json run_R2s0 dup1 검증 4지
N8_MIN_POS, N8_MIN_SPK, N8_MIN_SPK_POS = 600, 6, 30


def sha_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def tsv(p):
    return [l.rstrip('\n').split('\t') for l in open(p, encoding='utf-8') if l.strip() and not l.startswith('#')]


def n8_rows():
    rows = []
    for t in tsv(os.path.join(DATA, 'roi538/b/manifest.tsv')):
        if len(t) >= 3 and t[1] in N8:
            nm = t[0][:-4] if t[0].endswith('.mp4') else t[0]
            if f'_{N8_PERSON[t[1]]}_' not in nm:
                raise ValueError(f'N8 클립 인물 번호가 다름: {nm}')
            rows.append((nm, t[1], t[2]))
    return sorted(rows)


# ───────────────────────────── align ─────────────────────────────
def cmd_align(a):
    import build_cd as BC
    os.makedirs(a.out, exist_ok=True)
    rows = n8_rows()
    be = BC.W2VBackend(BC.W2V, 'auto')
    cnt = defaultdict(int)
    t0 = time.time()
    outp = os.path.join(a.out, 'n8_spans.jsonl')
    with open(outp + '.tmp', 'w', encoding='utf-8') as f:
        for i, (nm, spk, text) in enumerate(rows):
            rec = {'clip': nm, 'spk': spk, 'text_raw': text, 'text_norm': BC.normalize_text(text), 'status': 'ok'}
            wavp = os.path.join(DATA, 'roi538/b/clips', nm + '.wav')
            if BC.disallowed_chars(text):
                rec['status'] = 'skip_chars'
            elif not rec['text_norm']:
                rec['status'] = 'empty_text'
            elif not os.path.exists(wavp):
                rec['status'] = 'no_wav'
            if rec['status'] == 'ok':
                r = BC.align_clip(be, BC.load_wav(wavp), rec['text_norm'], 'auto', True, nm)
                rec.update(r)
                rec['flag'] = bool(r.get('asr_cer') is not None and float(r['asr_cer']) > BC.FLAG_CER)
            cnt[rec['status']] += 1
            cnt['flag'] += int(bool(rec.get('flag')))
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
            if i % 50 == 0:
                print(f'  {i}/{len(rows)} {time.time() - t0:.0f}s', flush=True)
    os.replace(outp + '.tmp', outp)
    RT.wjson({'rows': len(rows), 'counts': dict(cnt), 'sha256': sha_file(outp), 'time_sec': round(time.time() - t0, 1)},
             os.path.join(a.out, 'n8_align.json'), indent=1)
    print('VR_ALIGN_DONE ' + json.dumps(dict(cnt)), flush=True)
    return 0


# ───────────────────────────── 자료(창) ─────────────────────────────
class BenchSet:
    """벤치 화자(검증·평가): ① p4와 같은 창(roi_train.p4_window)."""

    def __init__(self, ctx, spks, npz):
        from train_lipread import MOUTH_KEYS
        b = ctx.bench
        self.b, self.npz = b, npz
        self.cols = [b.bs_names.index(k) for k in MOUTH_KEYS]
        self.lead, self.tail = RT.rest_runs_idx(b, self.cols, set(spks))
        self.insts = ctx.instances(spks)
        self.cache = {}

    def roi(self, ci):
        if ci not in self.cache:
            p = os.path.join(self.npz, self.b.clips[ci]['clip'] + '.npz')
            self.cache[ci] = np.load(p)['roi'] if os.path.exists(p) else None
        return self.cache[ci]

    def frames(self, it):
        w = RT.p4_window(self.b, it, self.cols, self.lead, self.tail)
        if w is None:
            return None
        fr = []
        for ci, f in w:
            r = self.roi(ci)
            if r is None:
                return None
            fr.append(r[min(f, len(r) - 1)])
        return np.stack(fr)


class N8Set:
    """새 인물 8명: 정렬 산출물로 d_bench build와 같은 규칙의 인스턴스, ROI valid로 쉬는 구간."""

    def __init__(self, ctx, out, npz):
        import d_bench as DB
        import folds as FO
        self.npz = npz
        self.clips, self.insts, self.cnt = [], [], defaultdict(int)
        spans = [json.loads(l) for l in open(os.path.join(out, 'n8_spans.jsonl'), encoding='utf-8') if l.strip()]
        sp = ctx.split
        held = set(sp['eval']) | set(sp['val'])
        train_txt = set()
        for r in ('v1_538r', 'e538r', 'roi538/a', 'roi538/b'):
            for t in tsv(os.path.join(DATA, r, 'manifest.tsv')):
                if len(t) >= 3 and t[1] not in held and not (r == 'roi538/b' and t[1] in N8):
                    train_txt.add(FO.norm_text(t[2]))
        self.lead, self.tail = defaultdict(list), defaultdict(list)
        for r in spans:
            if r.get('status') != 'ok':
                self.cnt['clip_' + str(r.get('status'))] += 1
                continue
            z = np.load(os.path.join(npz, r['clip'] + '.npz'))
            roi, valid = z['roi'], z['valid'].astype(bool)
            n = len(roi)
            chars = r.get('chars') or []
            words = r['text_norm'].split()
            ci_clip = len(self.clips)
            flag = bool(r.get('flag'))
            self.clips.append({'clip': r['clip'], 'spk': r['spk'], 'roi': roi, 'valid': valid, 'flag': flag,
                               'seen_text': FO.norm_text(r['text_raw']) in train_txt})
            if chars and not flag:
                sa, sb = chars[0][1], chars[-1][2]
                pre = np.arange(0, max(0, sa - 3))
                post = np.arange(min(n, sb + 3), n)
                pre, post = pre[valid[pre]], post[valid[post]]
                if len(pre) >= 3:
                    self.lead[r['spk']].append((ci_clip, pre))
                if len(post) >= 3:
                    self.tail[r['spk']].append((ci_clip, post))
            if sum(len(w) for w in words) != len(chars) or not chars:
                self.cnt['clip_chars_mismatch'] += 1
                continue
            ci = 0
            for k, w in enumerate(words):
                ci0, ci1 = ci, ci + len(w) - 1
                ci += len(w)
                a0, b0 = int(chars[ci0][1]), int(chars[ci1][2])
                why = ''
                if flag:
                    why = 'flag_cer'
                elif b0 - a0 > DB.MAX_SEG:
                    why = 'too_long'
                elif a0 >= n or b0 <= 0:
                    why = 'outside_video'
                elif w not in ctx.pset:
                    why = 'not_in_pool'
                self.cnt['inst_' + (why or 'ok')] += 1
                if why:
                    continue
                self.insts.append({'iid': f"n8|{r['clip']}|{k}", 'c': ci_clip, 'spk': r['spk'], 'w': w,
                                   'wide': DB.seg_wide(chars, ci0, ci1, n)})

    def frames(self, it):
        c = self.clips[it['c']]
        a, b = it['wide']
        if b <= a or c['valid'][a:b].mean() < 0.5:
            return None
        seg = [(it['c'], f) for f in range(a, b)]
        if len(seg) < RT.IDLE_LEN:
            need = RT.IDLE_LEN - len(seg)
            nl, nr = need // 2, need - need // 2
            key = RT.crc(f"idle|{it['iid']}")
            L_runs, R_runs = self.lead.get(it['spk']), self.tail.get(it['spk'])
            left = RT.tile_idx(L_runs[key % len(L_runs)], nl, True) if L_runs else [seg[0]] * nl
            right = RT.tile_idx(R_runs[(key // 7) % len(R_runs)], nr, False) if R_runs else [seg[-1]] * nr
            seg = left + seg + right
        return np.stack([self.clips[ci]['roi'][min(f, len(self.clips[ci]['roi']) - 1)] for ci, f in seg])


# ───────────────────────────── 모델·점수 ─────────────────────────────
class Model:
    def __init__(self, path, amp=1):
        import torch
        torch.set_num_threads(2)
        frac = float(os.environ.get('ROI_GPU_FRAC', '0.45'))
        self.dev = 'cuda' if torch.cuda.is_available() else 'cpu'
        if self.dev == 'cuda':
            torch.cuda.set_per_process_memory_fraction(frac)
        self.front, self.head, _ = RT.load_model(path, self.dev)
        self.amp = amp

    def logprobs(self, seqs):
        """seqs: (T,88,88) uint8 목록 → (T,53) log-softmax numpy 목록(dup1)."""
        import torch
        import torch.nn.functional as F
        from train_lipread import forward_packed
        L = max(len(g) for g in seqs)
        Tp = int(math.ceil(L / 4.0) * 4)
        c0 = (RT.S_ROI - RT.CROP) // 2
        X = np.zeros((len(seqs), Tp, RT.CROP, RT.CROP), np.uint8)
        for i, g in enumerate(seqs):
            X[i, :len(g)] = g[:, c0:c0 + RT.CROP, c0:c0 + RT.CROP]
        lens = np.array([len(g) for g in seqs], np.int64)
        with torch.no_grad():
            x = RT.normalize(X, lens, None, None, self.dev)
            lt = torch.from_numpy(lens)
            f = RT.run_front(self.front, x, lt, self.amp)
            lp = F.log_softmax(forward_packed(self.head, f, lt).float(), -1)
        return [lp[i, :int(lens[i])].cpu() for i in range(len(seqs))]


def score_rows(ctx, model, ds, four_way=False):
    """②의 score_set에서 B1을 뺀 것. rows = (spk, iid, kind, w, t, A1, A2, A3, A4)."""
    DB = ctx.DB
    insts = ds.insts
    ctx.set_swap_pool(insts)
    rows, n_null, hits = [], 0, defaultdict(list)
    t0 = time.time()
    for bi in range(0, len(insts), 64):
        chunk = insts[bi:bi + 64]
        seqs = [ds.frames(it) for it in chunk]
        okk = [i for i, s in enumerate(seqs) if s is not None]
        lps = model.logprobs([seqs[i] for i in okk]) if okk else []
        lp_of = dict(zip(okk, lps))
        for j, it in enumerate(chunk):
            if j not in lp_of:
                n_null += 1
                if four_way:
                    hits[it['spk']].append(0)
                continue
            lpt = lp_of[j]
            lp = lpt.numpy().astype(np.float64)
            if four_way:
                hard = DB.Distractors.order([it['w']] + ctx.dis.hard(it['w']), it['iid'])
                sc = RT.ctc_scores(lpt, [ctx.labels(v) for v in hard])
                hits[it['spk']].append(int(int(np.argmax(sc)) == hard.index(it['w'])))
            P = np.exp(lp)
            Pc = np.zeros((P.shape[0], 1 + len(VV.CLS)))
            np.add.at(Pc.T, ctx.jmap, P.T)
            lpc = np.log(np.maximum(Pc, 1e-30))
            best = float(lp.max(1).sum())
            other, near, homo, swap = ctx.claims(it)
            claims = [('pos', it['w'])] + [('other', t) for t in other] + [('near', t) for t in near] + \
                     [('homo', t) for t in homo] + [('swap', t) for t in swap]
            words = {t for _, t in claims}
            coh_words = {v for n in {VV.n_syl(t) for t in words} for v in ctx.cohort[n]}
            allw = sorted(words | coh_words)
            ll = dict(zip(allw, DB.ctc_loglik_multi(lp, [ctx.labels(v) for v in allw])))
            llc = dict(zip(allw, DB.ctc_loglik_multi(lpc, [ctx.cls_seq(v) for v in allw])))
            lmx = lambda z: float(np.logaddexp.reduce(z) - math.log(len(z)))   # noqa: E731
            for kind, t in claims:
                coh = [v for v in ctx.cohort[VV.n_syl(t)] if v != t][:VV.N_COHORT]
                L_t = len(ctx.labels(t))
                rows.append((it['spk'], it['iid'], kind, it['w'], t, ll[t] / L_t, (ll[t] - best) / L_t,
                             ll[t] - lmx(np.array([ll[v] for v in coh])), llc[t] - lmx(np.array([llc[v] for v in coh]))))
        if bi % 1280 == 0:
            print(f'  {bi}/{len(insts)} {time.time() - t0:.0f}s', flush=True)
    four = float(np.mean([np.mean(v) for v in hits.values()])) if four_way else None
    return rows, n_null, len(insts), four


def to_arrays(rows):
    spk = np.array([r[0] for r in rows])
    kind = np.array([r[2] for r in rows])
    S = np.array([r[5:9] for r in rows], float)
    return spk, kind, {k: S[:, i] for i, k in enumerate(CANDS)}


def common_meta(a):
    return {'model': a.model, 'model_sha256': sha_file(a.model), 'script_sha256': sha_file(os.path.abspath(__file__)),
            'vverify_sha256': sha_file(VV.__file__), 'roi_train_sha256': sha_file(RT.__file__)}


def cmd_explore(a):
    ctx = VV.Ctx(DAX)
    model = Model(a.model)
    ds = BenchSet(ctx, ctx.split['val'], a.npz)
    rows, n_null, n_inst, four = score_rows(ctx, model, ds, four_way=True)
    print(f'VR_WINDOW_CHECK val4={four:.4f} ref={VAL4_REF}', flush=True)
    if abs(four - VAL4_REF) > 0.003:
        print('VR_EXPLORE_FAIL 창·모델이 ① 검증 4지와 다름', flush=True)
        return 1
    RT.wjson(rows, os.path.join(a.out, 'explore_rows.json'))
    spk, kind, S = to_arrays(rows)
    res = {k: VV.metrics(spk, kind, v, B=a.boot) for k, v in S.items()}
    top = max(res[k]['auc_swap'] for k in CANDS)
    chosen = [k for k in CANDS if res[k]['auc_swap'] >= top - 0.005][0]
    theta = float(np.percentile(S[chosen][kind == 'pos'], 100 * VV.FRR_TARGET))
    det = VV.metrics(spk, kind, S[chosen], theta=theta, B=a.boot, rows=rows, ctx=ctx)
    al = json.load(open(os.path.join(a.out, 'n8_align.json'), encoding='utf-8'))
    frozen = dict(common_meta(a), chosen=chosen, theta=theta, n_cohort=VV.N_COHORT, bench_id=ctx.bench.bench_id,
                  n8_spans_sha256=al['sha256'])
    frozen['sha256'] = hashlib.sha256(json.dumps(frozen, sort_keys=True).encode('utf-8')).hexdigest()
    RT.wjson(frozen, os.path.join(a.out, 'frozen.json'), indent=1)
    RT.wjson({'phase': 'explore', 'speakers': ctx.split['val'], 'n_inst': n_inst, 'n_null': n_null, 'val4': four,
              'cands': res, 'chosen': chosen, 'chosen_detail': det, 'theta': theta, 'frozen_sha256': frozen['sha256']},
             os.path.join(a.out, 'explore_summary.json'), indent=1)
    print('VR_EXPLORE ' + json.dumps({k: [round(res[k]['auc_swap'], 4), round(res[k]['auc_other'], 4),
                                          round(res[k]['auc_near'], 4), res[k].get('ci_swap')] for k in res}), flush=True)
    print('VR_CHOSEN_DETAIL ' + json.dumps({k: det[k] for k in ('frr', 'flag_swap', 'flag_other', 'flag_near', 'flag_homo',
                                                                 'spk_auc_swap', 'near_by_class', 'auc_swap_by_nsyl')},
                                            ensure_ascii=False), flush=True)
    print(f'VR_CHOSEN {chosen} theta={theta:.4f} n_inst={n_inst} null={n_null} sha={frozen["sha256"][:12]}', flush=True)
    return 0


def judge(m):
    return bool(m['auc_swap'] >= 0.75 and m['ci_swap'][0] > 0.70 and m['frr'] <= 0.30 and m['flag_swap'] >= 0.50)


def per_spk_auc(spk, kind, s):
    out = {}
    for k in sorted(set(spk)):
        p, n = s[(spk == k) & (kind == 'pos')], s[(spk == k) & (kind == 'swap')]
        if len(p) and len(n):
            out[k] = VV.auc(p, n)
    return out


def cmd_confirm(a):
    out_sum = os.path.join(a.out, 'confirm_summary.json')
    if os.path.exists(out_sum) and not a.force:
        print('VR_CONFIRM_ALREADY (한 번만)', flush=True)
        return 2
    frozen = json.load(open(os.path.join(a.out, 'frozen.json'), encoding='utf-8'))
    now = common_meta(a)
    for k, v in now.items():
        if frozen.get(k) != v:
            print(f'VR_CONFIRM_FAIL 동결 뒤 바뀜: {k}', flush=True)
            return 1
    al = json.load(open(os.path.join(a.out, 'n8_align.json'), encoding='utf-8'))
    if al['sha256'] != frozen['n8_spans_sha256'] or sha_file(os.path.join(a.out, 'n8_spans.jsonl')) != al['sha256']:
        print('VR_CONFIRM_FAIL N8 정렬 산출물이 동결과 다름', flush=True)
        return 1
    ctx = VV.Ctx(DAX)
    model = Model(a.model)
    ch, theta = frozen['chosen'], frozen['theta']
    summ = {'phase': 'confirm', 'chosen': ch, 'theta': theta, 'frozen_sha256': frozen['sha256'], 'sets': {}}
    # C-40(재시험)
    ds40 = BenchSet(ctx, ctx.split['eval'], a.npz)
    rows40, null40, ninst40, _ = score_rows(ctx, model, ds40)
    RT.wjson(rows40, os.path.join(a.out, 'confirm40_rows.json'))
    spk, kind, S = to_arrays(rows40)
    m40 = VV.metrics(spk, kind, S[ch], theta=theta, B=10000, rows=rows40, ctx=ctx)
    m40['all_cands'] = {k: VV.metrics(spk, kind, v) for k, v in S.items()}
    m40.update(n_inst=ninst40, n_null=null40, n_speakers=len(set(spk)), pass_=judge(m40))
    # ② A1과 같은 문항의 화자별 짝 차이(보고만)
    try:
        bs = json.load(open(os.path.join(DAX, 'vverify', 'confirm_rows.json'), encoding='utf-8'))
        key_r = {(r[1], r[2], r[4]) for r in rows40}
        key_b = {(r[1], r[2], r[4]) for r in bs}
        b_spk, b_kind = np.array([r[0] for r in bs]), np.array([r[2] for r in bs])
        pa_b = per_spk_auc(b_spk, b_kind, np.array([r[5] for r in bs], float))
        pa_r = per_spk_auc(spk, kind, S[ch])
        ks = sorted(set(pa_b) & set(pa_r))
        d = np.array([pa_r[k] - pa_b[k] for k in ks])
        rng = np.random.default_rng(0)
        bd = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(10000)]
        m40['paired_vs_blendshape_A1'] = {'same_claims': key_r == key_b, 'n_spk': len(ks), 'mean_delta': float(d.mean()),
                                          'ci': [float(np.percentile(bd, 2.5)), float(np.percentile(bd, 97.5))],
                                          'n_up': int((d > 0).sum())}
    except Exception as e:      # 보고만이라 판정에 영향 없음
        m40['paired_vs_blendshape_A1'] = {'error': repr(e)}
    summ['sets']['C40_retest'] = m40
    print(f'VR_C40 auc_swap={m40["auc_swap"]:.4f} ci={m40["ci_swap"]} frr={m40["frr"]:.3f} flag={m40["flag_swap"]:.3f} '
          f'auc_other={m40["auc_other"]:.4f} auc_near={m40["auc_near"]:.4f} pass={m40["pass_"]}', flush=True)
    # C-N8(새 인물)
    ds8 = N8Set(ctx, a.out, a.npz)
    rows8, null8, ninst8, _ = score_rows(ctx, model, ds8)
    RT.wjson(rows8, os.path.join(a.out, 'confirm_n8_rows.json'))
    spk8, kind8, S8 = to_arrays(rows8)
    pos_by = defaultdict(int)
    for r in rows8:
        if r[2] == 'pos':
            pos_by[r[0]] += 1
    n_pos = sum(pos_by.values())
    enough = n_pos >= N8_MIN_POS and sum(1 for v in pos_by.values() if v >= N8_MIN_SPK_POS) >= N8_MIN_SPK
    m8 = VV.metrics(spk8, kind8, S8[ch], theta=theta, B=10000, rows=rows8, ctx=ctx)
    m8['all_cands'] = {k: VV.metrics(spk8, kind8, v) for k, v in S8.items()}
    seen_clip = {f"n8|{c['clip']}|": c['seen_text'] for c in ds8.clips}
    unseen = np.array([not seen_clip.get(r[1].rsplit('|', 1)[0] + '|', True) for r in rows8])
    m8['unseen_text_subset'] = {'n_pos': int((unseen & (kind8 == 'pos')).sum()),
                                'auc_swap': VV.auc(S8[ch][unseen & (kind8 == 'pos')], S8[ch][unseen & (kind8 == 'swap')])}
    m8.update(n_inst=ninst8, n_null=null8, n_speakers=len(set(spk8)), pos_by_spk=dict(pos_by), enough=bool(enough),
              data_counts=dict(ds8.cnt), pass_=judge(m8) if enough else None)
    summ['sets']['CN8_new'] = m8
    print(f'VR_CN8 auc_swap={m8["auc_swap"]:.4f} ci={m8["ci_swap"]} frr={m8["frr"]:.3f} flag={m8["flag_swap"]:.3f} '
          f'n_pos={n_pos} enough={enough} pass={m8["pass_"]}', flush=True)
    if enough:
        summ['verdict'] = 'PASS' if (m40['pass_'] and m8['pass_']) else 'FAIL'
    else:
        summ['verdict'] = ('PASS' if m40['pass_'] else 'FAIL') + '(재시험 한정, N8 판정 불가)'
    summ['rule'] = '집합마다 AUC_swap >= 0.75, CI 하한 > 0.70, θ에서 FRR <= 0.30, N_swap 표시율 >= 0.50; C-40과 C-N8 모두'
    RT.wjson(summ, out_sum, indent=1)
    print(f'VR_VERDICT {summ["verdict"]}', flush=True)
    return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument('cmd', choices=['align', 'explore', 'confirm'])
    p.add_argument('--out', default='D:/liplab/roi/vverify')
    p.add_argument('--npz', default='D:/liplab/roi/npz')
    p.add_argument('--model', default='D:/liplab/roi/run/run_R2s0/model.pt')
    p.add_argument('--boot', type=int, default=2000)
    p.add_argument('--force', action='store_true')
    a = p.parse_args()
    os.makedirs(a.out, exist_ok=True)
    return {'align': cmd_align, 'explore': cmd_explore, 'confirm': cmd_confirm}[a.cmd](a)


if __name__ == '__main__':
    sys.exit(main())
