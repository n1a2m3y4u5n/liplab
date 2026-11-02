#!/usr/bin/env python3
"""KMSAV ROI 후보 도구(docs/lipread-roi-kmsav-prereg-2026-11-02.md).

  prep-k --base RUN --roi DIR --cropped DIR --bench B --split S --manifest M --out RUN_K [--max-clips N]
         roi_train prep으로 만든 train538 기반 실행(RUN, 학습 33명 + 검증 12명)에 KMSAV 문장 클립을 섞어 새 pack을 만든다.
         기반 항목은 학습 클립 번호만 옮기고 내용은 그대로다. KMSAV는 prep.json의 'kms' 목록으로만 들어가고,
         검증 문항·쉬는 구간·평가 화자에는 들어가지 않는다.
  judge  --sel sel.json --cand-dir D --base-dir D --b33-dir D --out J
         판정 1회: Δ(후보 − B33) ≥ +0.05, 화자 짝 부트스트랩(10,000회, seed 0, 백분위) 95% CI 하한 > 0.
         보고만: R2 s0 짝 비교(평가 인물을 학습에 씀), 옛 벤치 번호대 화자 제외 부분집합, 열화 하락폭.
표식: KMS_PREP_OK, KMS_JUDGE PASS|FAIL
"""
import argparse
import json
import os
import re
import sys
import time
from collections import Counter

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import roi_train as RT  # noqa: E402
from roi_pair import paired, spk_boot  # noqa: E402

# 입력 규칙(등록 4절)
MAX_T, MIN_T, MIN_VALID = 450, 10, 0.5
BAD_TEXT = re.compile(r'[0-9A-Za-z%]')       # 숫자·로마자·퍼센트: 읽는 소리와 자모열이 어긋난다
# 보고용 부분집합(등록 7절): R2 s0 학습 화자와 겹치거나 겹칠 가능성이 있는 옛 벤치 v2 번호대
OLD_BENCH = {f'spk{n}' for n in range(301, 331)}
CONDS = ['low', 'jpeg', 'geo', 'bright', 'all']
DELTA_MIN = 0.05


def scan_kmsav(a, held_txt):
    """pack에 넣을 KMSAV 클립을 고른다. → (목록, 보고)"""
    import folds as FO
    from train_lipread import decompose
    rep = Counter()
    out = []
    names = sorted(f[:-4] for f in os.listdir(a.roi) if f.endswith('.npz'))
    rep['npz'] = len(names)
    for k, nm in enumerate(names):
        vid, utt = nm.rsplit('_', 1)
        tp = os.path.join(a.cropped, vid, 'utts', utt + '.txt')
        if not os.path.exists(tp):
            rep['drop_no_text'] += 1
            continue
        text = open(tp, encoding='utf-8').read().strip().replace('\n', ' ')
        if not text or BAD_TEXT.search(text):
            rep['drop_digit_latin' if text else 'drop_no_text'] += 1
            continue
        if FO.norm_text(text) in held_txt:
            rep['drop_shared_text'] += 1
            continue
        try:
            with np.load(os.path.join(a.roi, nm + '.npz'), allow_pickle=False) as z:
                v = z['valid'].astype(bool)
                fps = float(z['fps'])
                size = int(z['size'])
        except Exception:  # noqa: BLE001
            rep['drop_bad_npz'] += 1
            continue
        T = len(v)
        if size != RT.S_ROI:
            rep['drop_bad_size'] += 1
            continue
        if T < MIN_T or T > MAX_T:
            rep['drop_length'] += 1
            continue
        if v.mean() < MIN_VALID:
            rep['drop_low_valid'] += 1
            continue
        tg = decompose(text)
        if not tg or len(tg) > T:
            rep['drop_label_length'] += 1
            continue
        rep[f'src_fps_{round(fps)}'] += 1
        out.append({'clip': nm, 'vid': vid, 'text': text, 'tg': tg, 'T': T, 'vfrac': float(v.mean()),
                    'valid_bits': np.packbits(v).tobytes().hex()})
        if (k + 1) % 5000 == 0:
            RT.log(f'[prep-k] 살핌 {k + 1}/{len(names)} 남음 {len(out)}')
    return out, rep


def cmd_prep_k(a):
    import folds as FO
    from d_bench import Bench
    t0 = time.time()
    b = Bench(a.bench)
    sp = json.load(open(a.split, encoding='utf-8'))
    ev, va = set(sp['eval']), set(sp['val'])
    base = json.load(open(os.path.join(a.base, 'prep.json'), encoding='utf-8'))
    held_txt = {FO.norm_text(c['text']) for c in b.clips if c['spk'] in ev | va}
    held_txt.discard('')
    kms, rep = scan_kmsav(a, held_txt)
    # 격리 확인: KMSAV 이름 공간과 train538 이름·화자가 겹치지 않아야 한다
    t5 = [l.rstrip('\n').split('\t') for l in open(a.manifest, encoding='utf-8') if l.strip()]
    names538 = {t[0][:-4] if t[0].endswith('.mp4') else t[0] for t in t5}
    spk538 = {t[1] for t in t5}
    vids = {k['vid'] for k in kms}
    over_name = {k['clip'] for k in kms} & names538
    over_spk = vids & spk538
    bench_over = {k['clip'] for k in kms} & {c['clip'] for c in b.clips}
    if over_name or over_spk or bench_over:
        raise ValueError(f'KMSAV와 train538이 겹침: 이름 {len(over_name)}, 화자 {len(over_spk)}, 벤치 {len(bench_over)}')
    if a.max_clips:
        rng0 = np.random.default_rng(0)
        kms = [kms[i] for i in sorted(rng0.permutation(len(kms))[:a.max_clips])]
    S = RT.S_ROI
    tr_old = [i for i, c in enumerate(base['clips']) if c['role'] == 'train']
    va_old = [i for i, c in enumerate(base['clips']) if c['role'] != 'train']
    rng = np.random.default_rng(23456)
    mix = [('b', i) for i in tr_old] + [('k', i) for i in range(len(kms))]
    order = [mix[i] for i in rng.permutation(len(mix))] + [('b', i) for i in va_old]
    os.makedirs(os.path.join(a.out, 'pack'), exist_ok=True)
    bp = np.memmap(os.path.join(a.base, 'pack', 'roi_u8.bin'), np.uint8, 'r', shape=(base['meta']['frames'], S, S))
    pack = os.path.join(a.out, 'pack', 'roi_u8.bin')
    clips, new_of, kms_items, off = [], {}, [], 0
    with open(pack + '.tmp', 'wb') as f:
        for n, (src, i) in enumerate(order):
            if src == 'b':
                c = dict(base['clips'][i])
                roi = bp[c['off']:c['off'] + c['T']]
                new_of[i] = len(clips)
            else:
                k = kms[i]
                with np.load(os.path.join(a.roi, k['clip'] + '.npz'), allow_pickle=False) as z:
                    roi = z['roi']
                if roi.shape != (k['T'], S, S) or roi.dtype != np.uint8:
                    rep['drop_bad_roi'] += 1
                    continue
                c = {'clip': k['clip'], 'spk': 'kms:' + k['vid'], 'src': 'kmsav', 'role': 'train', 'bench_ci': -1, 'wav': None,
                     'text': k['text'], 'T': k['T'], 'vfrac': k['vfrac'], 'valid_bits': k['valid_bits']}
                kms_items.append([len(clips), k['tg']])
            f.write(np.ascontiguousarray(roi).tobytes())
            c['off'] = off
            off += int(c['T'])
            clips.append(c)
            if (n + 1) % 2000 == 0:
                RT.log(f'[prep-k] pack {n + 1}/{len(order)} frames={off}')
    os.replace(pack + '.tmp', pack)

    def mv_runs(dct):
        return {s: [[new_of[ci], fr] for ci, fr in v] for s, v in dct.items()}
    sent = [[new_of[i], tg] for i, tg in base['sent']]
    words = [[new_of[w[0]]] + w[1:] for w in base['words']]
    vitems = []
    for it in base['val_items']:
        it2 = dict(it)
        if it['win'] is not None:
            it2['win'] = [[new_of[ci], fr] for ci, fr in it['win']]
        vitems.append(it2)
    vsent = [[new_of[i], tg] for i, tg in base['val_sent']]
    frames_k = sum(clips[i]['T'] for i, _ in kms_items)
    meta = dict(base['meta'])
    meta.update(frames=off, kmsav={'report': dict(rep), 'clips': len(kms_items), 'frames': frames_k,
                                   'hours': round(frames_k / 30.0 / 3600.0, 1), 'videos': len({k['vid'] for k in kms}),
                                   'overlap_name_538': 0, 'overlap_spk_538': 0, 'overlap_bench': 0,
                                   'rules': {'max_T': MAX_T, 'min_T': MIN_T, 'min_valid': MIN_VALID}})
    RT.wjson({'meta': meta, 'clips': clips, 'sent': sent, 'words': words, 'kms': kms_items, 'lead': mv_runs(base['lead']),
              'tail': mv_runs(base['tail']), 'val_items': vitems, 'val_sent': vsent}, os.path.join(a.out, 'prep.json'))
    if {c['spk'] for c in clips} & ev:
        raise ValueError('평가 화자가 pack에 있음')
    if any(c['src'] == 'kmsav' and c['role'] != 'train' for c in clips):
        raise ValueError('KMSAV가 학습 밖 역할로 들어감')
    print(f"KMS_PREP_OK clips={len(clips)} frames={off} ({off * S * S / 1e9:.1f} GB) kms={len(kms_items)} kms_h={meta['kmsav']['hours']} "
          f"videos={meta['kmsav']['videos']} report={json.dumps(dict(rep), ensure_ascii=False)} {time.time() - t0:.0f}s", flush=True)
    return 0


def load(p):
    return json.load(open(p, encoding='utf-8'))


def by_of(p4, dup):
    return {k: float(v) for k, v in p4['by_spk'][str(dup)].items()}


def cmd_judge(a):
    sel = load(a.sel)['selected']
    dup = int(sel['dup'])
    cand, base = load(os.path.join(a.cand_dir, 'p4.json')), load(os.path.join(a.base_dir, 'p4.json'))
    b33 = load(os.path.join(a.b33_dir, 'p4.json'))
    b33_dup = int(load(a.b33_sel)['selected']['dup'])
    prob = []
    for name, p in (('후보', cand), ('R2 s0', base), ('B33', b33)):
        if p['iids'] != cand['iids']:
            prob.append(f'{name} 문항 순서가 다름')
        if p['unseg'] or p['roi_missing']:
            prob.append(f"{name} 못 자른 문항 {p['unseg']}, ROI 없는 문항 {p['roi_missing']}")
        if not p['judge']:
            prob.append(f'{name} p4가 --judge가 아님')
    if len(cand['speakers']) != 19:
        prob.append(f"화자 수 {len(cand['speakers'])} ≠ 19")
    if prob:
        print('KMS_JUDGE_FAIL ' + '; '.join(prob), flush=True)
        return 1
    bc, bb, bk = by_of(cand, dup), by_of(base, 1), by_of(b33, b33_dup)
    main_d = paired(bc, bk)
    ok = main_d['delta'] >= DELTA_MIN and main_d['ci'][0] > 0

    def sub(by):
        return {k: v for k, v in by.items() if k not in OLD_BENCH}
    rep = {'sel': sel, 'n_items': cand['n_items'], 'bench_id': cand['bench_id'],
           'cand': dict(zip(('acc', 'ci'), spk_boot(bc))), 'r2s0': dict(zip(('acc', 'ci'), spk_boot(bb))),
           'b33': dict(zip(('acc', 'ci'), spk_boot(bk))), 'b33_dup': b33_dup,
           'main': main_d, 'pass': bool(ok), 'rule': f'Δ ≥ +{DELTA_MIN}, 95% CI 하한 > 0',
           'report_only': {'cand_minus_r2s0': paired(bc, bb), 'b33_minus_r2s0': paired(bk, bb),
                           'subset_excluded': sorted(set(bc) & OLD_BENCH), 'subset_n': len(sub(bc)),
                           'subset_cand_minus_r2s0': paired(sub(bc), sub(bb)), 'subset_cand_minus_b33': paired(sub(bc), sub(bk)),
                           'subset_acc': {'cand': spk_boot(sub(bc))[0], 'r2s0': spk_boot(sub(bb))[0], 'b33': spk_boot(sub(bk))[0]}}}
    deg = {}
    for c in CONDS:
        row = {}
        for name, d, dp, clean in (('cand', a.cand_dir, dup, bc), ('r2s0', a.base_dir, 1, bb), ('b33', a.b33_dir, b33_dup, bk)):
            q = load(os.path.join(d, f'p4_{c}.json'))
            if q['iids'] != cand['iids']:
                print(f'KMS_JUDGE_FAIL 열화 {c} {name} 문항 다름', flush=True)
                return 1
            by = by_of(q, dp)
            row[name] = {'acc': spk_boot(by)[0], 'drop': paired(clean, by)}
        deg[c] = row
    rep['report_only']['degrade'] = deg
    RT.wjson(rep, a.out, indent=1)
    print(f"KMS_JUDGE {'PASS' if ok else 'FAIL'} cand={rep['cand']['acc']:.4f} {rep['cand']['ci']} b33={rep['b33']['acc']:.4f} "
          f"delta={main_d['delta']:+.4f} {main_d['ci']} r2s0={rep['r2s0']['acc']:.4f} → {a.out}", flush=True)
    return 0


def main():
    ap = argparse.ArgumentParser()
    s = ap.add_subparsers(dest='cmd', required=True)
    p = s.add_parser('prep-k')
    for k in ('base', 'roi', 'cropped', 'bench', 'split', 'manifest', 'out'):
        p.add_argument('--' + k, required=True)
    p.add_argument('--max-clips', type=int, default=0)
    p = s.add_parser('judge')
    for k in ('sel', 'b33-sel', 'cand-dir', 'base-dir', 'b33-dir', 'out'):
        p.add_argument('--' + k, required=True)
    a = ap.parse_args()
    sys.exit({'prep-k': cmd_prep_k, 'judge': cmd_judge}[a.cmd](a))


if __name__ == '__main__':
    main()
