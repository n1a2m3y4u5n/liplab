#!/usr/bin/env python3
"""
V1 판정(2026-10-15, 사전등록 liplab-integrate docs/lipread-v1-prereg-2026-10.md 4절).
  python v1_judge.py --sel sel.json --p4 d/v1_p4_sel.json --base d/v1_p4_base.json [--others a.json,b.json] --out v1_verdict.json
주 지표: 선택 모델, 평가 화자 40명, 4지 hard, ctc_ll α=1, idle75, 선택한 dup. 화자 평균.
관문: 평균 ≥ 0.40 이고 화자 부트스트랩(10,000회, seed 0, 백분위) 95% CI 하한 > 0.30 → V1_GATE PASS, 아니면 FAIL.
보고만: 현재 제품(greedy_lev·dup2·idle75)과의 화자별 짝 차이, 선택 모델의 greedy_lev 셀, product4way의 그룹 부트스트랩 CI.
"""
import argparse
import json
import os

import numpy as np

B = 10000


def cell(p4, scoring, alpha, pad, dup, setname='hard'):
    for c in p4['cells']:
        if (c['scoring'] == scoring and c['pad'] == pad and int(c['dup']) == int(dup) and c['set'] == setname
                and ((alpha is None and c['alpha'] is None) or (alpha is not None and c['alpha'] is not None
                                                                and abs(float(c['alpha']) - alpha) < 1e-9))):
            return c
    raise KeyError((scoring, alpha, pad, dup, setname))


def spk_boot(by, seed=0):
    v = np.array([by[s] for s in sorted(by)], float)
    rng = np.random.default_rng(seed)
    m = v[rng.integers(0, len(v), (B, len(v)))].mean(1)
    return float(v.mean()), [float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))]


def paired(by_a, by_b, seed=0):
    ks = sorted(set(by_a) & set(by_b))
    d = np.array([by_a[k] - by_b[k] for k in ks], float)
    rng = np.random.default_rng(seed)
    m = d[rng.integers(0, len(d), (B, len(d)))].mean(1)
    return {'delta': float(d.mean()), 'ci': [float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))],
            'n_spk': len(ks), 'n_up': int((d > 0).sum()), 'n_down': int((d < 0).sum())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sel', required=True)
    ap.add_argument('--p4', required=True)
    ap.add_argument('--base', required=True)
    ap.add_argument('--others', default='')
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    sel = json.load(open(a.sel, encoding='utf-8'))['selected']
    p4 = json.load(open(a.p4, encoding='utf-8'))
    base = json.load(open(a.base, encoding='utf-8'))
    dup = int(sel['dup'])
    main_c = cell(p4, 'ctc_ll', 1.0, 'idle75', dup)
    m, ci = spk_boot(main_c['by_spk'])
    ok = bool(m >= 0.40 and ci[0] > 0.30)
    cur = cell(base, 'greedy_lev', None, 'idle75', 2)
    out = {'rule': '선택 모델 · 4지 hard · ctc_ll α=1 · idle75 · dup%d, 화자 평균 ≥ 40%% 그리고 화자 부트스트랩 95%% CI 하한 > 30%%' % dup,
           'selected': sel, 'n_eval_speakers': len(main_c['by_spk']), 'n_instances': p4.get('n_instances'),
           'vocab_size': p4.get('vocab_size'), 'main': {'acc': m, 'ci_spk_boot': ci, 'ci_group_boot_p4': main_c['ci']},
           'pass': ok}
    rep = {}
    cur_m, cur_ci = spk_boot(cur['by_spk'])
    rep['현재 제품(현재 모델·greedy_lev·dup2·idle75)'] = {'acc': cur_m, 'ci': cur_ci}
    rep['선택 모델 − 현재 제품(짝)'] = paired(main_c['by_spk'], cur['by_spk'])
    for name, (sc, al, dd) in {'선택 모델 greedy_lev(같은 dup)': ('greedy_lev', None, dup),
                               '선택 모델 ctc_ll α=1 dup%d' % (3 - dup): ('ctc_ll', 1.0, 3 - dup)}.items():
        c = cell(p4, sc, al, 'idle75', dd)
        mm, cc = spk_boot(c['by_spk'])
        rep[name] = {'acc': mm, 'ci': cc}
    c = cell(base, 'ctc_ll', 1.0, 'idle75', 2)
    mm, cc = spk_boot(c['by_spk'])
    rep['현재 모델 ctc_ll α=1 dup2(P3 셀)'] = {'acc': mm, 'ci': cc}
    for p in [x for x in a.others.split(',') if x]:
        o = json.load(open(p, encoding='utf-8'))
        for dd in (2, 1):
            c = cell(o, 'ctc_ll', 1.0, 'idle75', dd)
            mm, cc = spk_boot(c['by_spk'])
            rep[f'다른 후보 {os.path.basename(p)} ctc_ll dup{dd}'] = {'acc': mm, 'ci': cc}
    out['report_only'] = rep
    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"V1 주 지표 {100 * m:.1f}% [{100 * ci[0]:.1f}, {100 * ci[1]:.1f}] (화자 {len(main_c['by_spk'])}명, "
          f"그룹 CI {main_c['ci']})", flush=True)
    for k, v in rep.items():
        if 'delta' in v:
            print(f"  {k}: Δ {100 * v['delta']:+.1f} [{100 * v['ci'][0]:+.1f}, {100 * v['ci'][1]:+.1f}] "
                  f"오름 {v['n_up']}/{v['n_spk']}", flush=True)
        else:
            print(f"  {k}: {100 * v['acc']:.1f}% [{100 * v['ci'][0]:.1f}, {100 * v['ci'][1]:.1f}]", flush=True)
    print(f"V1_GATE {'PASS' if ok else 'FAIL'}", flush=True)


if __name__ == '__main__':
    main()
