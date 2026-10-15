#!/usr/bin/env python3
"""V1 평가 화자 40명 고정(사전등록 docs/lipread-v1-prereg-2026-10.md 3.2절). 받기가 끝난 뒤 한 번만 돌린다.
  python v1_pick_eval.py --root ../data/v1_538r --old-n 68 --out ../data/v1_538r/eval40.txt
후보 = ROOT/.state/<spk>.done, 선택 = sha256("liplab-v1-eval:"+spk) 16진 오름차순 40명.
후보 < 80 이거나 (기존 + 후보 − 40) < 120 이면 V1_PICK_SHORT(종료코드 3): 학습하지 말고 더 받는다."""
import argparse, glob, hashlib, os, sys
from collections import Counter
ap = argparse.ArgumentParser()
ap.add_argument('--root', required=True); ap.add_argument('--old-n', type=int, default=68)
ap.add_argument('--n', type=int, default=40); ap.add_argument('--out', required=True)
a = ap.parse_args()
cand = sorted(os.path.basename(p)[:-5] for p in glob.glob(os.path.join(a.root, '.state', '*.done')))
meta = {}
mp = os.path.join(a.root, 'manifest_meta.tsv')
if os.path.exists(mp):
    for ln in open(mp, encoding='utf-8'):
        t = ln.rstrip('\n').split('\t')
        if t and not t[0].startswith('#') and len(t) > 9:
            meta[t[0]] = {'person': t[2], 'sex': t[3], 'view': t[9]}
ev = sorted(cand, key=lambda s: hashlib.sha256(f'liplab-v1-eval:{s}'.encode()).hexdigest())[:a.n]
rest = a.old_n + len(cand) - len(ev)
short = len(cand) < 80 or rest < 120
with open(a.out, 'w', encoding='utf-8') as f:
    f.write('# V1 평가 화자(sha256("liplab-v1-eval:"+spk) 오름차순 %d명, 후보 %d명)\n' % (len(ev), len(cand)))
    f.write('\n'.join(ev) + '\n')
print('V1_PICK candidates=%d eval=%d rest(train+val)=%d sex=%s view=%s' % (
    len(cand), len(ev), rest, dict(Counter(meta.get(s, {}).get('sex', '?') for s in ev)),
    dict(Counter(meta.get(s, {}).get('view', '?') for s in ev))))
print('V1_PICK_SHORT' if short else 'V1_PICK_OK', '→', a.out)
sys.exit(3 if short else 0)
