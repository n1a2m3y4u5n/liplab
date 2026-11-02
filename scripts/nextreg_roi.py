"""One-variable B33 degradation augmentation and validation-only comparison."""
import argparse
import json
import math
import os
from pathlib import Path
import zlib

import cv2
import numpy as np
import roi_train as R


def degrade(x, cond, rng):
    x = x.copy()
    n, h, w = x.shape
    if cond == 'low':
        return np.array([cv2.resize(cv2.resize(f, (w//2, h//2), interpolation=cv2.INTER_AREA), (w, h), interpolation=cv2.INTER_LINEAR) for f in x])
    if cond == 'jpeg':
        return np.array([cv2.imdecode(cv2.imencode('.jpg', f, [cv2.IMWRITE_JPEG_QUALITY, 20])[1], 0) for f in x])
    if cond == 'bright':
        phase = rng.uniform(0, 2*math.pi)
        gain = .6 * (1 + .15*np.sin(2*math.pi*np.arange(n)/60 + phase))
        return np.clip(x.astype(float)*gain[:, None, None], 0, 255).astype(np.uint8)
    angle = rng.uniform(-6, 6)
    dx, dy = rng.uniform(-4, 4, 2)
    mat = cv2.getRotationMatrix2D(((w-1)/2, (h-1)/2), angle, 1)
    out = []
    for f in x:
        m = mat.copy()
        m[:, 2] += [dx, dy] + rng.normal(0, .7, 2)
        out.append(cv2.warpAffine(f, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE))
    return np.asarray(out)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='cmd', required=True)
    t = sub.add_parser('train')
    t.add_argument('--run', required=True)
    t.add_argument('--out', required=True)
    t.add_argument('--seed', type=int, default=0)
    t.add_argument('--resume', action='store_true')
    e = sub.add_parser('compare')
    e.add_argument('--run', required=True)
    e.add_argument('--candidate', required=True)
    e.add_argument('--baseline', required=True)
    e.add_argument('--out', required=True)
    a = p.parse_args()
    d = json.loads((Path(a.run)/'prep.json').read_text(encoding='utf-8'))
    assert len(d['meta']['train_spk']) == 33 and len(d['meta']['val_spk']) == 12
    assert {c['role'] for c in d['clips']} <= {'train', 'val'}
    assert not any(c.get('source') == 'kmsav' for c in d['clips'])
    original = R.make_batch
    if a.cmd == 'train':
        arng = np.random.default_rng(a.seed + 20261102)
        if a.resume and (Path(a.out)/'last.pt').exists():
            import torch
            ck = torch.load(Path(a.out)/'last.pt', map_location='cpu', weights_only=False)
            arng.bit_generator.state = ck['augmentation_rng']
            del ck
        save = R.save_atomic
        def save_with_rng(obj, path):
            if 'opt' in obj:
                obj['augmentation_rng'] = arng.bit_generator.state
            return save(obj, path)
        R.save_atomic = save_with_rng

        def batch(run, gl, rng=None, **kw):
            result = original(run, gl, rng=rng, **kw)
            if rng is None:
                return result
            x, lens, flips, mask, teach = result
            for i, n in enumerate(lens):
                if arng.random() < .5:
                    c = ('low', 'jpeg', 'geo', 'bright')[int(arng.integers(4))]
                    x[i, :n] = degrade(x[i, :n], c, arng)
            return x, lens, flips, mask, teach

        R.make_batch = batch
        argv = ['train', '--run', a.run, '--out', a.out, '--cand', 'R1', '--seed', str(a.seed),
                '--epochs', '40', '--patience', '6', '--batch', '32', '--max-frames', '4000',
                '--gpu-frac', '.45', '--log-every', '100', '--amp', '1']
        if a.resume:
            argv.append('--resume')
        return R.main(argv)
    if Path(a.out).exists():
        raise SystemExit('Refuse duplicate selection')
    import torch
    torch.set_num_threads(4)
    run = R.Run(a.run)
    seqs = [None if it['win'] is None else np.array([run.off[ci] + min(f, run.T[ci]-1) for ci, f in it['win']], np.int64) for it in run.val_items]
    result = {}
    for label, model in [('baseline', a.baseline), ('candidate', a.candidate)]:
        front, head, _ = R.load_model(model, 'cuda')
        row = {}
        for cond in ('clean', 'low', 'jpeg', 'geo', 'bright'):
            def gather(gl):
                x, lens, _, _, _ = original(run, gl)
                if cond != 'clean':
                    for i, (g, n) in enumerate(zip(gl, lens)):
                        ci = int(np.argmax(np.bincount(np.searchsorted(run.off, g, side='right')-1)))
                        key = 'nextreg-val|'+cond+'|'+run.clips[ci]['clip']
                        x[i, :n] = degrade(x[i, :n], cond, np.random.default_rng(zlib.crc32(key.encode())))
                return x, lens
            by = R.score4(front, head, run, seqs, run.val_items, 'cuda', 1, gather)
            row[cond] = {'by_speaker': by, 'mean': float(np.mean([np.mean(list(by[k].values())) for k in R.DUPS]))}
        result[label] = row
        del front, head
        torch.cuda.empty_cache()
    clean = result['candidate']['clean']['mean']-result['baseline']['clean']['mean']
    degraded = float(np.mean([result['candidate'][k]['mean']-result['baseline'][k]['mean'] for k in ('low','jpeg','geo','bright')]))
    result.update(clean_delta=clean, degraded_delta=degraded, keep_path=bool(clean >= -.02 and degraded >= .03),
                  status='validation_selection_only_no_adjudication')
    boot = np.random.default_rng(20261102)
    speakers = sorted(run.meta['val_spk'])
    for name, conditions in [('clean', ['clean']), ('degraded', ['low','jpeg','geo','bright'])]:
        delta = []
        for spk in speakers:
            delta.append(float(np.mean([result['candidate'][k]['by_speaker'][dup][spk] - result['baseline'][k]['by_speaker'][dup][spk]
                                        for k in conditions for dup in R.DUPS])))
        v = np.asarray(delta)
        result[name+'_delta_ci95'] = np.quantile(v[boot.integers(0,len(v),(10000,len(v)))].mean(1), [.025,.975]).tolist()
    Path(a.out).write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('SELECTION', clean, degraded, result['keep_path'], flush=True)


if __name__ == '__main__':
    raise SystemExit(main())
