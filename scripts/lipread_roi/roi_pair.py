#!/usr/bin/env python3
"""
roi_pair.py: 독화 ① 판정 1 준비(2026-10-18, docs/lipread-roi-2026-10.md 7절, 판정 전 작성).
ROI p4의 문항을 V1 product4way 문항과 하나하나 맞추고, V1 B1과의 화자별 짝 차이를 계산한다.

  items  --bench B --speakers a,b,… [--v1 p4_B1.json] --out J
         d_bench.cmd_product4way의 문항 구성(어휘 bench.dist_words, hard 오답 순서, idle75 창)을 V1 코드로 다시 만들고,
         roi_train.h4_items·p4_window와 문항 ID·정답·보기 순서·창 프레임이 모두 같은지 확인한다(창은 프레임 번호로
         모은 블렌드셰이프가 d_bench.p4_sequences(idle75, dup1, wide) 출력과 같은지 비교). --v1을 주면 화자 집합,
         bench_id, 문항 수, 어휘 수도 V1 출력과 같아야 한다. 하나라도 다르면 PAIR_FAIL(종료 코드 1).
  judge  --bench B --roi-p4 J --v1 p4_B1.json --dup D [--v1-dup 1] --out J
         ROI p4(--judge 출력)의 iids가 V1 문항 목록과 순서까지 같은지 먼저 확인하고(다르면 판정하지 않음),
         판정 1: Δ = ROI(dup D) − B1(ctc_ll α=1 idle75 hard dup1) ≥ +0.05, 화자 짝 부트스트랩(10,000회, seed 0) 95% CI 하한 > 0
         판정 2: ROI 4지 ≥ 0.40, 화자 부트스트랩 95% CI 하한 > 0.30
평가 화자의 ROI는 읽지 않는다(문항 구성은 벤치 메타데이터만 쓴다). 학습 화자로 시험한다.
"""
import argparse
import json
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import roi_train as RT  # noqa: E402  (LIPLAB_TOOLS 경로를 sys.path에 넣는다)

B = 10000


def v1_items(bench, spks):
    """d_bench.cmd_product4way와 같은 문항(기본 rule, 어휘 bench.dist_words)."""
    from d_bench import Distractors
    pool = list(bench.dist_words)
    ps = set(pool)
    dis = Distractors(bench, pool)
    out = []
    for it in bench.inst:
        if it['ok'] and it['w'] in ps and it['spk'] in spks:
            hard = Distractors.order([it['w']] + dis.hard(it['w']), it['iid'])
            out.append({'iid': it['iid'], 'spk': it['spk'], 'w': it['w'], 'inst': it, 'hard': hard})
    return out, len(pool)


def v1_cell(p4, dup):
    for c in p4['cells']:
        if (c['scoring'] == 'ctc_ll' and c['pad'] == 'idle75' and int(c['dup']) == int(dup) and c['set'] == 'hard'
                and c['alpha'] is not None and abs(float(c['alpha']) - 1.0) < 1e-9):
            return c
    raise KeyError(('ctc_ll', 1.0, 'idle75', dup, 'hard'))


def check_items(bench, spks, v1=None):
    """문항·창 대조. → (보고 dict, 문제 목록)"""
    import d_bench as DB
    from train_lipread import MOUTH_KEYS
    cols = [bench.bs_names.index(k) for k in MOUTH_KEYS]
    prob = []
    va, nvocab = v1_items(bench, spks)
    ra = RT.h4_items(bench, spks)
    if [x['iid'] for x in va] != [x['iid'] for x in ra]:
        sa, sr = {x['iid'] for x in va}, {x['iid'] for x in ra}
        prob.append(f'문항 ID 다름: V1만 {len(sa - sr)}, ROI만 {len(sr - sa)}, 순서 같음 {sa == sr}')
    from train_lipread import decompose
    n_bad_c = 0
    for x, y in zip(va, ra):
        if x['iid'] != y['iid']:
            continue
        if [decompose(w) for w in x['hard']] != y['labs'] or x['hard'].index(x['w']) != y['tgt'] or x['spk'] != y['spk']:
            n_bad_c += 1
    if n_bad_c:
        prob.append(f'보기·정답이 다른 문항 {n_bad_c}')
    lead_v, tail_v = DB._rest_runs(bench, cols)
    lead_r, tail_r = RT.rest_runs_idx(bench, cols, spks)
    n_none_v = n_none_r = n_bad_w = n_cmp = 0
    fb = defaultdict(int)
    for x, y in zip(va, ra):
        if x['iid'] != y['iid']:
            continue
        X = DB.p4_sequences(bench, x['inst'], cols, 'idle75', 1, 'wide', lead_v, tail_v, fb)
        w = RT.p4_window(bench, y['inst'], cols, lead_r, tail_r)
        n_none_v += X is None
        n_none_r += w is None
        if (X is None) != (w is None):
            n_bad_w += 1
            continue
        if X is None:
            continue
        n_cmp += 1
        Y = np.stack([bench.bs[bench.clips[ci]['off'] + f][cols] for ci, f in w]).astype(np.float32)
        # V1은 어절 구간의 NaN 행만 fill_nan으로 채우고, 쉬는 구간은 NaN 없는 프레임만 고른다.
        # 그래서 NaN 아닌 행은 값이 같아야 하고, NaN 행은 모두 어절 구간 프레임이어야 한다.
        ok = ~np.isnan(Y).any(1)
        a0, b0 = y['inst']['wide']
        nan_in_seg = all(ci == y['inst']['c'] and a0 <= f < b0 for (ci, f), g in zip(w, ok) if not g)
        if Y.shape != X.shape or not nan_in_seg or not np.allclose(Y[ok], X[ok], atol=1e-6):
            n_bad_w += 1
    if n_bad_w:
        prob.append(f'창이 다른 문항 {n_bad_w}/{n_cmp + n_bad_w}')
    rep = {'bench_id': bench.bench_id, 'speakers': sorted(spks), 'n_items_v1': len(va), 'n_items_roi': len(ra),
           'vocab_size': nvocab, 'win_compared': n_cmp, 'win_none_v1': n_none_v, 'win_none_roi': n_none_r,
           'idle_fallback_v1': fb.get('idle_fallback', 0), 'iids': [x['iid'] for x in va]}
    if v1 is not None:
        vs = {s for s in v1['speakers'].split(',') if s} if isinstance(v1['speakers'], str) else set(v1['speakers'])
        if vs != set(spks):
            prob.append(f'화자 집합이 V1과 다름(V1 {len(vs)}, 여기 {len(spks)})')
        if v1['bench_id'] != bench.bench_id:
            prob.append(f"bench_id 다름 {v1['bench_id']} ≠ {bench.bench_id}")
        if int(v1['n_instances']) != len(va):
            prob.append(f"문항 수 다름 V1 {v1['n_instances']} ≠ {len(va)}")
        if int(v1['vocab_size']) != nvocab:
            prob.append(f"어휘 수 다름 V1 {v1['vocab_size']} ≠ {nvocab}")
    return rep, prob


def spk_boot(by, seed=0):
    v = np.array([by[s] for s in sorted(by)], float)
    rng = np.random.default_rng(seed)
    m = v[rng.integers(0, len(v), (B, len(v)))].mean(1)
    return float(v.mean()), [float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))]


def paired(by_a, by_b, seed=0):
    ks = sorted(by_a)
    if set(by_a) != set(by_b):
        raise ValueError('짝 화자 집합이 다름')
    d = np.array([by_a[k] - by_b[k] for k in ks], float)
    rng = np.random.default_rng(seed)
    m = d[rng.integers(0, len(d), (B, len(d)))].mean(1)
    return {'delta': float(d.mean()), 'ci': [float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))],
            'n_spk': len(ks), 'n_up': int((d > 0).sum()), 'n_down': int((d < 0).sum())}


def judge(roi, v1, dup, v1_dup, bench, require_v1_speakers=True):
    spks = set(roi['speakers'])
    rep, prob = check_items(bench, spks, v1 if require_v1_speakers else None)
    if roi.get('bench_id') != bench.bench_id:
        prob.append('ROI p4 bench_id 다름')
    if list(roi['iids']) != rep['iids']:
        prob.append(f"ROI p4 iids가 V1 문항 목록과 다름({len(roi['iids'])} vs {len(rep['iids'])})")
    if roi.get('unseg', 0) != rep['win_none_v1']:
        prob.append(f"못 자른 문항 수 다름(ROI {roi.get('unseg')}, V1 창 {rep['win_none_v1']})")
    if roi.get('roi_missing', 0):
        prob.append(f"ROI 없는 문항 {roi['roi_missing']}(오답으로 셈)")      # 보고: 판정은 막지 않음
    hard = [p for p in prob if not p.startswith('ROI 없는')]
    out = {'pair_check': {k: v for k, v in rep.items() if k != 'iids'}, 'problems': prob}
    if hard:
        out['verdict'] = None
        return out, False
    by_r = {s: float(v) for s, v in roi['by_spk'][str(dup)].items()}
    by_v = {s: float(v) for s, v in v1_cell(v1, v1_dup)['by_spk'].items()}
    m, ci = spk_boot(by_r)
    mv, civ = spk_boot(by_v)
    d = paired(by_r, by_v)
    j1 = bool(d['delta'] >= 0.05 and d['ci'][0] > 0)
    j2 = bool(m >= 0.40 and ci[0] > 0.30)
    out.update({'roi': {'dup': dup, 'acc': m, 'ci_spk_boot': ci}, 'v1_b1': {'dup': v1_dup, 'acc': mv, 'ci_spk_boot': civ},
                'paired': d, 'judgment1_pass': j1, 'judgment2_pass': j2})
    return out, True


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('items')
    p.add_argument('--bench', required=True)
    p.add_argument('--speakers', required=True)
    p.add_argument('--v1', default=None)
    p.add_argument('--out', required=True)
    p = sub.add_parser('judge')
    p.add_argument('--bench', required=True)
    p.add_argument('--roi-p4', required=True)
    p.add_argument('--v1', required=True)
    p.add_argument('--dup', type=int, required=True, help='선택된 ROI 모델의 dup(sel.json)')
    p.add_argument('--v1-dup', type=int, default=1, help='V1 B1 선택 dup(주 셀 30.1%%는 dup1)')
    p.add_argument('--test-any-speakers', action='store_true', help='시험용: V1 화자 집합 일치를 요구하지 않음')
    p.add_argument('--out', required=True)
    a = ap.parse_args()
    from d_bench import Bench
    b = Bench(a.bench)
    if a.cmd == 'items':
        v1 = json.load(open(a.v1, encoding='utf-8')) if a.v1 else None
        spks = {s for s in a.speakers.split(',') if s}
        rep, prob = check_items(b, spks, v1)
        rep['problems'] = prob
        RT.wjson(rep, a.out, indent=1)
        print(('PAIR_FAIL ' + ' / '.join(prob)) if prob else
              f"PAIR_OK items={rep['n_items_v1']} vocab={rep['vocab_size']} win={rep['win_compared']} "
              f"unseg={rep['win_none_v1']}", flush=True)
        return 1 if prob else 0
    roi = json.load(open(a.roi_p4, encoding='utf-8'))
    v1 = json.load(open(a.v1, encoding='utf-8'))
    out, ok = judge(roi, v1, a.dup, a.v1_dup, b, not a.test_any_speakers)
    RT.wjson(out, a.out, indent=1)
    if not ok:
        print('ROI_JUDGE_FAIL 판정하지 않음: ' + ' / '.join(out['problems']), flush=True)
        return 1
    d = out['paired']
    print(f"ROI 4지 {100 * out['roi']['acc']:.1f}% [{100 * out['roi']['ci_spk_boot'][0]:.1f}, "
          f"{100 * out['roi']['ci_spk_boot'][1]:.1f}] / B1 {100 * out['v1_b1']['acc']:.1f}% / "
          f"Δ {100 * d['delta']:+.1f} [{100 * d['ci'][0]:+.1f}, {100 * d['ci'][1]:+.1f}] 오름 {d['n_up']}/{d['n_spk']}", flush=True)
    print(f"ROI_JUDGE1 {'PASS' if out['judgment1_pass'] else 'FAIL'}  ROI_JUDGE2 {'PASS' if out['judgment2_pass'] else 'FAIL'}",
          flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
