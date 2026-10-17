#!/usr/bin/env python3
"""ROI 받기 큐 만들기(2026-10-17, docs/lipread-roi-2026-10.md 11절).
A: spkmap538_full.tsv에서 V1 루트·S4 평가 루트(manifest_meta의 vsn)와 V1 큐 시도분(queue_run.tsv)에 없는 배치.
B: 두 루트의 화자(학습·검증 화자 먼저, V1 평가 40명은 맨 뒤). 화자 ID는 spkNNN = tr번호 + 296(dl_more 규칙).
사용: python3 roi_queue.py <lab>/data <out_dir> <eval40.txt>"""
import sys, os
data, out, ev = sys.argv[1], sys.argv[2], sys.argv[3]
def rows(p):
    return [l.rstrip('\n').split('\t') for l in open(p, encoding='utf-8') if l.strip() and not l.startswith('#')]
full = rows(os.path.join(data, 'spkmap538_full.tsv'))          # tr, vsn, lsn, set
metas = []
for r in ('v1_538r', 'e538r'):
    for p in rows(os.path.join(data, r, 'manifest_meta.tsv')):  # spk vsn person ... lsn(7) set(8)
        metas.append((p[0], p[1], p[7], p[8]))
held = {m[1] for m in metas}
tried = {p[1] for p in rows(os.path.join(data, 'v1_538r', 'queue_run.tsv'))}
evs = {l.strip() for l in open(ev, encoding='utf-8') if l.strip() and not l.startswith('#')}
H = '#spk\tvideo_fileSn\tlabel_fileSn\tset\n'
a = [('spk%d' % (int(t[2:]) + 296), v, l, s) for t, v, l, s in full if v not in held and v not in tried]
seen, b = set(), []
for m in sorted(metas, key=lambda m: (m[0] in evs, m[0])):
    if m[0] in seen: continue
    seen.add(m[0]); b.append(m)
for name, q in (('queue_a.tsv', a), ('queue_b.tsv', b)):
    with open(os.path.join(out, name), 'w', encoding='utf-8') as f:
        f.write(H); f.writelines('\t'.join(r) + '\n' for r in q)
print('ROI_QUEUE a=%d b=%d (b 중 평가 %d명 맨 뒤)' % (len(a), len(b), sum(m[0] in evs for m in b)))
