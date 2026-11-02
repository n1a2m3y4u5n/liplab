"""Two matched small CTC runs; frozen BS-lips preregistration."""
import argparse
import json
import os
from pathlib import Path

import numpy as np
import v1_train as V
import train_lipread as T
from d_bench import Bench
from extract_blendshapes import LIPS_MIRROR


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--bench', required=True)
    p.add_argument('--split', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--lips', action='store_true')
    p.add_argument('--smoke', action='store_true')
    a = p.parse_args()
    mouth = list(T.MOUTH_KEYS)
    perm = T._mirror_perm()

    class InputBench(Bench):
        def __init__(self, path):
            super().__init__(path)
            if a.lips:
                self.bs = np.concatenate([self.bs, self.lips], axis=1)
                self.bs_names = self.bs_names + ['lip%d' % i for i in range(80)]

    V.Bench = InputBench
    V.MOUTH_KEYS = mouth + (['lip%d' % i for i in range(80)] if a.lips else [])
    V._mirror_perm = lambda: perm

    def raw(x, rng):
        b = T.aug_raw(x[:, :27], rng)
        return np.concatenate([b, x[:, 27:]], 1) if a.lips else b

    def post(x, rng, unused):
        n = len(x)
        n2 = max(2, int(round(n / rng.uniform(.8, 1.25))))
        pos = np.linspace(0, n - 1, n2)
        i = np.floor(pos).astype(int)
        w = (pos - i)[:, None]
        x = x[i] * (1 - w) + x[np.minimum(i + 1, n - 1)] * w
        if rng.random() < .5:
            b = x[:, :27][:, perm]
            if a.lips:
                lips = x[:, 27:].reshape(-1, 40, 2)[:, LIPS_MIRROR].copy()
                lips[:, :, 0] *= -1
                x = np.concatenate([b, lips.reshape(-1, 80)], 1)
            else:
                x = b
        m = int(rng.integers(0, 4))
        if 0 < m < len(x):
            s = int(rng.integers(0, len(x) - m + 1))
            x[s:s + m] = 0
        return x.astype(np.float32)

    V.aug_raw, V.aug_post = raw, post
    split = json.loads(Path(a.split).read_text(encoding='utf-8'))
    b = Bench(a.bench)
    assert {c['spk'] for c in b.clips} <= set(split['train']) | set(split['val'])
    assert len(split['train']) == 33 and len(split['val']) == 12
    if a.smoke:
        import torch
        torch.set_num_threads(4)
        data = V.Data(a.bench, a.split, 'B')
        model = V.build(len(V.MOUTH_KEYS), len(V.VOCAB))
        x = np.stack(data.val_seq[V.DUPS[0]][:2])
        with torch.no_grad():
            y = model(torch.from_numpy(x))
        assert tuple(y.shape) == (len(x), x.shape[1], len(V.VOCAB))
        q = post(x[0], np.random.default_rng(17), perm)
        assert q.shape[1] == len(V.MOUTH_KEYS) and np.isfinite(q).all()
        print('SMOKE_OK', len(V.MOUTH_KEYS), 'sent', len(data.sent), 'words', len(data.words), 'val_items', len(data.val_items), flush=True)
        return 0
    # Both models use a new subset benchmark; no evaluation frames are present.
    opts = argparse.Namespace(bench=a.bench, split=a.split, out=a.out, cand='B', seed=0, threads=4,
                              epochs=40, batch=64, lr=3e-4, eval_every=2, patience=6, idle_p=.5,
                              max_items=0, max_val=0)
    return V.cmd_train(opts)


if __name__ == '__main__':
    raise SystemExit(main())
