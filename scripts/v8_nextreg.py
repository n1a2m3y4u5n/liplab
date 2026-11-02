"""Frozen V8 CPU analysis; see docs/V8-prereg-2026-11-02.md."""
import argparse
import collections
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np


def metrics(d):
    frames = d['frames']
    if len(frames) < 30:
        return None, None
    t = np.array([f['t_ms'] for f in frames], dtype=float) / 1000
    if t[-1] - t[0] < 1:
        return None, None
    u = (t - t[0]) / (t[-1] - t[0])
    mid, end = (u >= .4) & (u < .6), u >= .8
    ix = [d['bs_names'].index(n) for n in ('browInnerUp', 'browOuterUpLeft', 'browOuterUpRight')]
    b = np.array([[f['bs'][i] for i in ix] for f in frames]).mean(axis=1)
    brow = float(b[end].mean() - b[mid].mean()) if mid.any() and end.any() and np.isfinite(b).all() else None
    pitch = []
    for f in frames:
        fx = f.get('fx')
        if fx is None or np.size(fx) != 16:
            pitch.append(float('nan'))
            continue
        r = np.asarray(fx).reshape(4, 4)
        pitch.append(math.degrees(math.atan2(r[2, 1], math.hypot(r[2, 0], r[2, 2]))))
    pitch = np.array(pitch)
    speed = []
    for mask in (mid, end):
        ts, ps = t[mask], pitch[mask]
        if len(ts) < 5 or not np.isfinite(ps).all():
            return brow, None
        dt = np.diff(ts)
        ok = (dt > 0) & (dt <= .1)
        if not ok.any():
            return brow, None
        speed.append(float(np.abs(np.diff(ps))[ok].sum() / dt[ok].sum()))
    return brow, speed[1] - speed[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    if a.out.exists():
        raise SystemExit('Refuse repeated adjudication: output exists')
    manifest = a.root / 'manifest.tsv'
    rows = list(csv.reader(manifest.open(encoding='utf-8'), delimiter='\t'))
    groups = collections.defaultdict(lambda: {'q': [], 's': [], 'head': []})
    excluded = collections.Counter()
    for filename, spk, text in rows:
        f = a.root / 'rebuild' / 'real_bs' / (Path(filename).stem + '.json')
        if not f.is_file():
            excluded['missing_json'] += 1
            continue
        brow, head = metrics(json.loads(f.read_text(encoding='utf-8')))
        if brow is None:
            excluded['brow_quality'] += 1
        else:
            groups[spk]['q' if '?' in text or '？' in text else 's'].append(brow)
        if head is None:
            excluded['head_quality'] += 1
        else:
            groups[spk]['head'].append(head)
    rng = np.random.default_rng(20261102)
    result = {}
    for key, threshold in [('brow', .02), ('head', 1.)]:
        values = {}
        for spk, g in sorted(groups.items()):
            if key == 'brow' and min(len(g['q']), len(g['s'])) >= 2:
                values[spk] = float(np.mean(g['q']) - np.mean(g['s']))
            elif key == 'head' and g['head']:
                values[spk] = float(np.mean(g['head']))
        v = np.array(list(values.values()))
        if len(v) < 20:
            result[key] = {'status': 'insufficient_speakers', 'n': len(v), 'speaker_effects': values}
            continue
        means = v[rng.integers(0, len(v), (10000, len(v)))].mean(axis=1)
        lo, hi = np.quantile(means, [.0125, .9875])
        result[key] = {'n': len(v), 'mean': float(v.mean()), 'ci97_5': [float(lo), float(hi)],
                       'threshold': threshold, 'pass': bool(v.mean() >= threshold and lo > 0), 'speaker_effects': values}
    result.update(clips=len(rows), excluded=dict(excluded),
                  manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
                  overall_pass=all(result[k].get('pass', False) for k in ('brow', 'head')))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: {x: y for x, y in v.items() if x != 'speaker_effects'} if isinstance(v, dict) else v for k, v in result.items()}, ensure_ascii=True))


if __name__ == '__main__':
    main()
