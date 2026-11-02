"""Frozen ROI+lips development candidate; no held-out evaluation interface."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path

os.environ.setdefault('OMP_NUM_THREADS', '2')
os.environ.setdefault('MKL_NUM_THREADS', '2')
os.environ.setdefault('OPENBLAS_NUM_THREADS', '2')
import numpy as np
import roi_train as R
from extract_blendshapes import LIPS_MIRROR

ARCH = 'B33_pixel256_plus_LN80_Linear64_GELU_Linear256_v1'
_build = R.build_models
_batch = R.make_batch
_normalize = R.normalize
_run = R.Run


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def dump(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2), encoding='utf-8')


def allowed(run):
    d = json.loads((Path(run) / 'prep.json').read_text(encoding='utf-8'))
    tr, va = set(d['meta']['train_spk']), set(d['meta']['val_spk'])
    assert len(tr) == 33 and len(va) == 12 and not tr & va
    assert {c['role'] for c in d['clips']} <= {'train', 'val'}
    assert all(c['spk'] in (tr if c['role'] == 'train' else va) for c in d['clips'])
    assert not any(c.get('src') == 'kmsav' or c.get('source') == 'kmsav' for c in d['clips'])
    return d


def prepare(a):
    d = allowed(a.run)
    out = Path(a.lips)
    out.mkdir(parents=True, exist_ok=True)
    target = out / 'lips_f32.bin'
    if target.exists() or (out / 'manifest.json').exists():
        raise ValueError('Refuse to overwrite coordinate input pack')
    rows, frames, missing, all_missing, duplicates = [], 0, 0, 0, 0
    tmp = out / 'lips_f32.bin.tmp'
    with tmp.open('wb') as f:
        for c in d['clips']:
            assert c['off'] == frames
            src = Path(a.bs) / (c['clip'] + '.json')
            obj = json.loads(src.read_text(encoding='utf-8'))
            assert abs(float(obj['fps']) - 30.0) <= .05, src
            assert abs(int(obj.get('n_read', obj['n_frames'])) - c['T']) <= 2, src
            x = np.full((c['T'], 80), np.nan, np.float32)
            for fr in obj['frames']:
                j = int(round(float(fr['t_ms']) * 30.0 / 1000.0))
                v = fr.get('lips')
                if 0 <= j < len(x) and v is not None and len(v) == 80 and np.isfinite(v).all():
                    duplicates += int(np.isfinite(x[j]).all())
                    x[j] = v
            valid = np.isfinite(x).all(1)
            n_missing = int((~valid).sum())
            missing += n_missing
            if valid.any():
                jj = np.arange(len(x))
                for k in range(80):
                    x[:, k] = np.interp(jj, jj[valid], x[valid, k])
            else:
                x[:] = 0
                all_missing += 1
            assert np.isfinite(x).all()
            f.write(x.tobytes(order='C'))
            rows.append({'clip': c['clip'], 'role': c['role'], 'T': c['T'], 'missing': n_missing,
                         'all_missing': not bool(valid.any()), 'source_sha256': sha(src)})
            frames += len(x)
    assert frames == d['meta']['frames']
    tmp.replace(target)
    manifest = {'architecture': ARCH, 'frames': frames, 'channels': 80, 'dtype': 'float32',
                'train_speakers': 33, 'val_speakers': 12, 'clips': len(rows),
                'missing_frames_interpolated': missing, 'all_missing_clips_zero_filled': all_missing,
                'duplicate_source_indices': duplicates, 'prep_sha256': sha(Path(a.run) / 'prep.json'),
                'pack_sha256': sha(target), 'fps': 30, 'rows': rows}
    dump(out / 'manifest.json', manifest)
    print('LIPS_PREP_OK', json.dumps({k: v for k, v in manifest.items() if k != 'rows'}), flush=True)


class PairedPixels(np.ndarray):
    """Keep coordinates attached through the base trainer's batch/frame slicing."""
    def __new__(cls, pixels, lips):
        obj = np.asarray(pixels).view(cls)
        obj.lips = lips
        return obj

    def __array_finalize__(self, obj):
        self.lips = getattr(obj, 'lips', None)

    def __getitem__(self, key):
        out = super().__getitem__(key)
        if isinstance(out, PairedPixels):
            k = key if isinstance(key, tuple) else (key,)
            out.lips = self.lips[k[:2]]
        return out


def models(n_vocab=53, proj_dim=0):
    import torch
    import torch.nn as nn
    pixel, head, proj = _build(n_vocab, proj_dim)

    class Fusion(nn.Module):
        def __init__(self):
            super().__init__()
            self.pixel = pixel
            self.lips = nn.Sequential(nn.LayerNorm(80), nn.Linear(80, 64), nn.GELU(), nn.Linear(64, 256))

        @property
        def ckpt(self):
            return self.pixel.ckpt

        @ckpt.setter
        def ckpt(self, value):
            self.pixel.ckpt = value

        def forward(self, pair, lens):
            x, lips, keep = pair
            f = self.pixel(x, lens)
            return f + self.lips(lips) * keep[:, :, None]

    return Fusion(), head, proj


def install(lips_root):
    import torch
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    manifest = json.loads((Path(lips_root) / 'manifest.json').read_text(encoding='utf-8'))

    class InputRun(_run):
        def __init__(self, path):
            allowed(path)
            assert sha(Path(path) / 'prep.json') == manifest['prep_sha256']
            super().__init__(path)
            assert self.meta['frames'] == manifest['frames']
            self.lips = np.memmap(Path(lips_root) / 'lips_f32.bin', np.float32, 'r',
                                  shape=(manifest['frames'], 80))

    def batch(run, gl, rng=None, **kw):
        x, lens, flips, mask, teach = _batch(run, gl, rng=rng, **kw)
        lips = np.zeros((x.shape[0], x.shape[1], 80), np.float32)
        for i, g in enumerate(gl):
            lips[i, :len(g)] = run.lips[g]
        return PairedPixels(x, lips), lens, flips, mask, teach

    def normalize(x, lens, flips, mask, dev):
        lips = np.asarray(x.lips).copy().reshape(x.shape[0], x.shape[1], 40, 2)
        if flips is not None and flips.any():
            mirrored = lips[flips][:, :, LIPS_MIRROR].copy()
            mirrored[:, :, :, 0] *= -1
            lips[flips] = mirrored
        lips = lips.reshape(x.shape[0], x.shape[1], 80)
        keep = np.arange(x.shape[1])[None, :] < lens[:, None]
        if mask is not None:
            keep &= ~mask
        lips *= keep[:, :, None]
        pix = _normalize(np.asarray(x), lens, flips, mask, dev)
        return (pix, torch.from_numpy(lips).to(dev, non_blocking=True),
                torch.from_numpy(keep.astype(np.float32)).to(dev, non_blocking=True))

    def run_front(front, x, lens, amp):
        with torch.autocast('cuda', dtype=torch.bfloat16, enabled=bool(amp) and x[0].is_cuda):
            f = front(x, lens)
        return f.float()

    R.Run, R.build_models, R.make_batch, R.normalize, R.run_front = InputRun, models, batch, normalize, run_front
    save = R.save_atomic

    def save_pair(obj, path):
        obj['fusion_architecture'] = ARCH
        obj['lips_manifest_sha256'] = sha(Path(lips_root) / 'manifest.json')
        if 'meta' in obj:
            obj['meta']['fusion_architecture'] = ARCH
        return save(obj, path)
    R.save_atomic = save_pair
    return manifest


def smoke(a):
    import torch
    install(a.lips)
    run = R.Run(a.run)
    ci = run.sent[0][0]
    gl = [run.gidx(ci, np.arange(3)), run.gidx(ci, np.arange(5))]
    rng1, rng2 = np.random.default_rng(17), np.random.default_rng(17)
    xx, ll, ff, mm, _ = R.make_batch(run, gl, rng1)
    bx, bl, bf, bm, _ = _batch(run, gl, rng2)
    assert np.array_equal(xx, bx) and np.array_equal(ll, bl)
    assert np.array_equal(ff, bf) and np.array_equal(mm, bm)
    assert rng1.bit_generator.state == rng2.bit_generator.state
    sl = xx[np.array([1]), :4]
    assert sl.lips.shape == (1, 4, 80) and np.array_equal(sl.lips[0], run.lips[gl[1][:4]])
    assert np.array_equal(np.asarray(LIPS_MIRROR)[LIPS_MIRROR], np.arange(40))
    torch.manual_seed(101)
    base, bh, _ = _build()
    torch.manual_seed(101)
    front, head, _ = models()
    assert all(torch.equal(v, front.pixel.state_dict()[k]) for k, v in base.state_dict().items())
    assert all(torch.equal(v, head.state_dict()[k]) for k, v in bh.state_dict().items())
    extra = sum(p.numel() for p in front.lips.parameters())
    assert extra == 21984
    del base, bh
    ff[:] = True
    mm[:] = False
    mm[0, 1] = True
    norm = R.normalize(xx, ll, ff, mm, 'cpu')
    expected = xx.lips[0, 0].reshape(40, 2)[LIPS_MIRROR].copy()
    expected[:, 0] *= -1
    assert np.array_equal(norm[1][0, 0].numpy(), expected.reshape(80))
    assert norm[1][0, 1].abs().sum() == 0 and norm[2][0, 1] == 0
    assert norm[1][0, 3:].abs().sum() == 0 and norm[2][0, 3:].sum() == 0
    front.eval()
    with torch.no_grad():
        feat = R.run_front(front, norm, torch.from_numpy(ll), 0)
        from train_lipread import forward_packed
        logits = forward_packed(head, feat, torch.from_numpy(ll))
    assert tuple(feat.shape) == (2, 8, 256) and tuple(logits.shape) == (2, 8, 53)
    assert torch.isfinite(feat).all() and feat[0, 3:].abs().sum() == 0
    print('FUSION_SMOKE_OK', 'additional_params', extra, 'sent', len(run.sent),
          'words', len(run.words), 'val_items', len(run.val_items), flush=True)


def compare(a):
    import torch
    d = allowed(a.run)
    if Path(a.out).exists():
        raise ValueError('Refuse duplicate development selection')
    candidate = json.loads((Path(a.candidate) / 'train_summary.json').read_text(encoding='utf-8'))
    baseline = json.loads((Path(a.baseline) / 'train_summary.json').read_text(encoding='utf-8'))
    assert candidate['seed'] == baseline['seed'] == a.seed
    assert candidate['n_sent'] == baseline['n_sent'] == len(d['sent'])
    assert candidate['n_words'] == baseline['n_words'] == len(d['words'])
    assert candidate['n_val_items'] == baseline['n_val_items'] == len(d['val_items'])
    for root, fused in [(a.baseline, False), (a.candidate, True)]:
        ck = torch.load(Path(root) / 'model.pt', map_location='cpu', weights_only=False)
        assert ck['meta']['seed'] == a.seed and ck['meta']['bench_id'] == d['meta']['bench_id']
        assert bool(ck.get('fusion_architecture')) == fused
        assert ck['meta']['init'] is None
        if fused:
            assert ck['fusion_architecture'] == ARCH
        del ck
    acc = candidate['best_val_4way_mean'] - baseline['best_val_4way_mean']
    cer = candidate['best']['val_cer'] - baseline['best']['val_cer']
    result = {'status': 'validation_selection_only_no_adjudication', 'seed': a.seed,
              'architecture': ARCH, 'accuracy_delta': acc, 'cer_delta': cer,
              'keep_path': bool(acc >= .02 and cer <= .02),
              'thresholds': {'accuracy_delta_min': .02, 'cer_delta_max': .02},
              'baseline': {k: baseline[k] for k in ('best_epoch', 'best_val_4way_mean', 'best')},
              'candidate': {k: candidate[k] for k in ('best_epoch', 'best_val_4way_mean', 'best')},
              'baseline_model_sha256': sha(Path(a.baseline) / 'model.pt'),
              'candidate_model_sha256': sha(Path(a.candidate) / 'model.pt'),
              'prep_sha256': sha(Path(a.run) / 'prep.json')}
    dump(a.out, result)
    print('FUSION_SELECTION', a.seed, acc, cer, result['keep_path'], flush=True)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='cmd', required=True)
    for cmd in ('prep', 'smoke', 'train', 'compare'):
        t = sub.add_parser(cmd)
        t.add_argument('--run', required=True)
        if cmd != 'compare':
            t.add_argument('--lips', required=True)
        if cmd == 'prep':
            t.add_argument('--bs', required=True)
        if cmd == 'train':
            t.add_argument('--out', required=True)
            t.add_argument('--seed', type=int, choices=(0, 1), default=0)
            t.add_argument('--previous-selection')
            t.add_argument('--gpu-frac', type=float, default=.45)
        if cmd == 'compare':
            t.add_argument('--out', required=True)
            t.add_argument('--seed', type=int, choices=(0, 1), required=True)
            t.add_argument('--candidate', required=True)
            t.add_argument('--baseline', required=True)
    a = p.parse_args()
    if a.cmd == 'prep':
        return prepare(a)
    if a.cmd == 'smoke':
        return smoke(a)
    if a.cmd == 'compare':
        return compare(a)
    allowed(a.run)
    if a.seed == 1:
        prev = json.loads(Path(a.previous_selection).read_text(encoding='utf-8'))
        assert prev['seed'] == 0 and prev['keep_path'] is True
    if any((Path(a.out) / n).exists() for n in ('model.pt', 'last.pt', 'train_summary.json')):
        raise ValueError('Refuse to repeat a started scientific seed')
    install(a.lips)
    return R.main(['train', '--run', a.run, '--out', a.out, '--cand', 'R1', '--seed', str(a.seed),
                   '--epochs', '40', '--patience', '6', '--batch', '32', '--max-frames', '4000',
                   '--gpu-frac', str(a.gpu_frac), '--log-every', '100', '--amp', '1'])


if __name__ == '__main__':
    raise SystemExit(main())
