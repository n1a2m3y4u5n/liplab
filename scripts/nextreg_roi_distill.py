"""One registered B33 -> compact ROI augmentation-consistency distillation run.

Imports the sealed existing B33 training implementation; never builds a new split.
Teacher logits are cached on training clips only, in <=400-frame clean windows.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np
import roi_train as R


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1048576), b''):
            h.update(b)
    return h.hexdigest()


def validate(run):
    d = json.loads((Path(run) / 'prep.json').read_text(encoding='utf-8'))
    assert len(d['meta']['train_spk']) == 33 and len(d['meta']['val_spk']) == 12
    assert {c['role'] for c in d['clips']} <= {'train', 'val'}
    assert not any(c.get('src') == 'kmsav' or c.get('source') == 'kmsav' for c in d['clips'])
    assert all(d['clips'][int(s[0])]['role'] == 'train' for s in d['sent'])
    assert all(d['clips'][int(s[0])]['role'] == 'train' for s in d['words'])
    return d


def build_student(n_vocab=53, proj_dim=0):
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    class Block(nn.Module):
        def __init__(self, cin, cout, stride):
            super().__init__()
            self.c1 = nn.Conv2d(cin, cout, 3, stride, 1, bias=False)
            self.b1 = nn.BatchNorm2d(cout)
            self.c2 = nn.Conv2d(cout, cout, 3, 1, 1, bias=False)
            self.b2 = nn.BatchNorm2d(cout)
            self.down = nn.Sequential(nn.Conv2d(cin, cout, 1, stride, bias=False), nn.BatchNorm2d(cout))

        def forward(self, x):
            return F.relu(self.b2(self.c2(F.relu(self.b1(self.c1(x))))) + self.down(x))

    class Front(nn.Module):
        def __init__(self):
            super().__init__()
            self.c3 = nn.Conv3d(1, 8, (5, 7, 7), (1, 2, 2), (2, 3, 3), bias=False)
            self.b3 = nn.BatchNorm2d(8)
            self.stages = nn.ModuleList([Block(8, 16, 1), Block(16, 32, 2), Block(32, 64, 2), Block(64, 96, 2)])
            self.fc = nn.Linear(96, 128)
            self.ckpt = False

        def forward(self, x, lens):
            x = F.avg_pool3d(x, (1, 2, 2), (1, 2, 2))
            B, _, T, H, W = x.shape
            L = lens.to(x.device)
            m = torch.arange(T, device=x.device)[None, :] < L[:, None]
            start = torch.cumsum(torch.cat([L.new_zeros(1), L[:-1] + 2]), 0)
            pos = (start[:, None] + torch.arange(T, device=x.device)[None, :])[m]
            cat = x.new_zeros(int(L.sum()) + 2 * (B - 1), H, W)
            cat[pos] = x[:, 0][m]
            h = self.c3(cat[None, None])[0].transpose(0, 1)[pos]
            v = F.max_pool2d(F.relu(self.b3(h)), 3, 2, 1)
            for st in self.stages:
                v = st(v)
            v = self.fc(v.mean(dim=(2, 3)))
            out = v.new_zeros(B, T, 128)
            out[m] = v
            return out

    class Head(nn.Module):
        def __init__(self):
            super().__init__()
            self.norm = nn.LayerNorm(128)
            self.gru = nn.GRU(128, 128, num_layers=2, batch_first=True, bidirectional=True, dropout=.2)
            self.out = nn.Linear(256, n_vocab)

        def forward(self, x):
            return self.out(self.gru(self.norm(x))[0])

    assert not proj_dim
    return Front(), Head(), None


def counts():
    tf, th, _ = R.build_models()
    sf, sh, _ = build_student()
    teacher = sum(p.numel() for m in (tf, th) for p in m.parameters())
    student = sum(p.numel() for m in (sf, sh) for p in m.parameters())
    assert student <= teacher / 4
    return {'teacher_parameters': teacher, 'student_parameters': student, 'parameter_ratio': student / teacher}


def cache_teacher(a, run, dev):
    import torch
    from train_lipread import forward_packed
    p = Path(a.out) / 'teacher_logits_f16.bin'
    meta_path = Path(a.out) / 'teacher_logits.json'
    if p.exists() or meta_path.exists():
        raise RuntimeError('Refuse existing cache or duplicate run')
    front, head, ck = R.load_model(a.teacher, dev)
    assert ck['meta']['seed'] == 0
    expected = json.loads((Path(a.run) / 'prep.json').read_text(encoding='utf-8'))['meta']['bench_id']
    assert ck['meta']['bench_id'] == expected
    teacher_hash = sha(a.teacher)
    tmp = Path(str(p) + '.tmp')
    arr = np.memmap(tmp, np.float16, 'w+', shape=(run.meta['frames'], 53))
    arr[:] = 0
    clips = [i for i, c in enumerate(run.clips) if c['role'] == 'train']
    with torch.no_grad():
        for ni, ci in enumerate(clips):
            for st in range(0, int(run.T[ci]), 400):
                g = run.gidx(ci, np.arange(st, min(st + 400, run.T[ci])))
                X, lens, _, _, _ = R.make_batch(run, [g])
                x = R.normalize(X, lens, None, None, dev)
                lt = torch.from_numpy(lens)
                lo = forward_packed(head, R.run_front(front, x, lt, 0), lt)[0, :len(g)]
                arr[g] = lo.cpu().numpy().astype(np.float16)
            if ni % 25 == 0:
                R.log(f'KD_CACHE clips={ni + 1}/{len(clips)} {R.mem_note(dev)}')
    arr.flush()
    del arr, front, head
    if dev == 'cuda':
        torch.cuda.empty_cache()
    os.replace(tmp, p)
    meta = dict(teacher_sha256=teacher_hash, teacher_seed=0, teacher_window_frames=400,
                train_clip_count=len(clips), frames=run.meta['frames'], dtype='float16', dim=53,
                targets='clean_center_crop_teacher; student_augmented_consistency; train_only')
    meta_path.write_text(json.dumps(meta, indent=2), encoding='utf-8')
    return np.memmap(p, np.float16, 'r', shape=(run.meta['frames'], 53)), meta


def train(a):
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    if Path(a.out).exists() and any(Path(a.out).iterdir()):
        raise RuntimeError('Refuse nonempty output: one registered seed, no retry/resume')
    Path(a.out).mkdir(parents=True, exist_ok=True)
    validate(a.run)
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    dev = R.setup(a)
    run = R.Run(a.run)
    info = counts()
    targets, provenance = cache_teacher(a, run, dev)
    (Path(a.out) / 'architecture.json').write_text(json.dumps(info | provenance, indent=2), encoding='utf-8')
    original_batch, original_front, original_save = R.make_batch, R.run_front, R.save_atomic
    base_ctc = nn.CTCLoss
    context = {}

    def make_batch(run, gl, rng=None, **kw):
        result = original_batch(run, gl, rng=rng, **kw)
        if rng is not None:
            X, lens, *_ = result
            t = np.zeros((len(gl), X.shape[1], 53), np.float16)
            for j, g in enumerate(gl):
                t[j, :len(g)] = targets[g]
            context.update(target=t, cursor=0, batch_size=len(gl), frames=int(lens.sum()))
        return result

    def run_front(front, x, lt, amp):
        if front.training:
            lo, hi = context['cursor'], context['cursor'] + len(lt)
            context['current'] = torch.from_numpy(context['target'][lo:hi, :x.shape[2]].copy()).to(x.device).float()
            context['cursor'] = hi
        return original_front(front, x, lt, amp)

    class KDCTC(nn.Module):
        def __init__(self, *args, **kwargs):
            super().__init__()
            self.base = base_ctc(*args, **kwargs)

        def forward(self, logp, target, lens, target_lens):
            ctc = self.base(logp, target, lens, target_lens)
            # logp is normalized at T=1; dividing it by T gives equivalent T-scaled logits after log_softmax.
            slp = F.log_softmax(logp.transpose(0, 1) / 2, -1)
            tp = F.softmax(context['current'] / 2, -1)
            mask = torch.arange(slp.shape[1], device=slp.device)[None] < lens.to(slp.device)[:, None]
            # R.cmd_train applies group_size/batch_size outside this loss. Undo that
            # factor for KD so summed microgroups give the full-batch frame mean.
            kd = (F.kl_div(slp, tp, reduction='none').sum(-1) * mask).sum()
            kd = kd / context['frames'] * (context['batch_size'] / len(lens))
            return .5 * ctc + .5 * 4 * kd

    def save(obj, path):
        if 'front' in obj:
            obj['architecture'] = 'compact_roi_v1'
            obj['distillation'] = info | provenance | {'temperature': 2, 'ctc_weight': .5, 'kd_weight': .5}
        return original_save(obj, path)

    R.build_models = build_student
    R.make_batch, R.run_front, R.save_atomic = make_batch, run_front, save
    R.Prefetch = lambda gen: iter(gen)  # synchronous batch/target pairing; no mutable cross-thread context
    nn.CTCLoss = KDCTC
    return R.main(['train', '--run', a.run, '--out', a.out, '--cand', 'R1', '--seed', '0',
                   '--epochs', '40', '--patience', '6', '--batch', '32', '--max-frames', '4000',
                   '--gpu-frac', '.92', '--amp', '0', '--log-every', '100'])


def load_student(path, dev):
    import torch
    ck = torch.load(path, map_location='cpu', weights_only=False)
    assert ck['architecture'] == 'compact_roi_v1'
    f, h, _ = build_student(len(ck['vocab']))
    f.load_state_dict(ck['front'])
    h.load_state_dict(ck['head'])
    return f.to(dev).eval(), h.to(dev).eval(), ck


def export_one(path, out, student):
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    import onnxruntime as ort
    f, h, _ = load_student(path, 'cpu') if student else R.load_model(path, 'cpu')

    class Wrap(nn.Module):
        def __init__(self):
            super().__init__()
            self.front, self.head = f, h

        def forward(self, roi):
            x = roi / 255.
            x = x - x.mean(dim=(1, 2, 3), keepdim=True)
            x = x / x.square().mean(dim=(1, 2, 3), keepdim=True).sqrt().clamp(min=.01)
            x = x.unsqueeze(1)
            if student:
                x = F.avg_pool3d(x, (1, 2, 2), (1, 2, 2))
            B, _, T, H, W = x.shape
            width, dim = (8, 128) if student else (24, 256)
            v = self.front.c3(x).transpose(1, 2).reshape(B * T, width, H // 2, W // 2)
            v = F.max_pool2d(F.relu(self.front.b3(v)), 3, 2, 1)
            for st in self.front.stages:
                v = st(v)
            z = self.front.fc(v.mean(dim=(2, 3))).reshape(B, T, dim)
            return self.head(z)

    model = Wrap().eval()
    x = torch.from_numpy(np.random.default_rng(20261102).integers(0, 256, (1, 75, 80, 80)).astype(np.float32))
    with torch.no_grad():
        ref = model(x).numpy()
        expected = h(f(R.normalize(x.numpy().astype(np.uint8), np.array([75]), None, None, 'cpu'), torch.tensor([75]))).numpy()
    torch.onnx.export(model, x, str(out), input_names=['roi'], output_names=['logits'],
                      dynamic_axes={'roi': {0: 'B', 1: 'T'}, 'logits': {0: 'B', 1: 'T'}}, opset_version=17, dynamo=False)
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    session = ort.InferenceSession(str(out), sess_options=options, providers=['CPUExecutionProvider'])
    actual = session.run(['logits'], {'roi': x.numpy()})[0]
    a, b = float(abs(ref - expected).max()), float(abs(ref - actual).max())
    assert a < .001 and b < .001, (a, b)
    return {'bytes': Path(out).stat().st_size, 'sha256': sha(out), 'wrap_diff': a, 'onnx_diff': b}


def finish(a):
    import torch
    validate(a.run)
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if (out / 'selection.json').exists():
        raise RuntimeError('Refuse duplicate validation selection')
    run = R.Run(a.run)
    seqs = [None if it['win'] is None else np.array([run.off[ci] + min(fr, run.T[ci]-1) for ci, fr in it['win']], np.int64) for it in run.val_items]

    def gather(gl):
        X, lens, *_ = R.make_batch(run, gl)
        return X, lens

    rows = {}
    dev = 'cuda' if torch.cuda.is_available() else 'cpu'
    if dev == 'cuda':
        torch.cuda.set_per_process_memory_fraction(.92)
    for label, path, student in [('teacher', a.teacher, False), ('student', a.student, True)]:
        f, h, _ = load_student(path, dev) if student else R.load_model(path, dev)
        by = R.score4(f, h, run, seqs, run.val_items, dev, 0, gather)
        rows[label] = {'mean': float(np.mean([np.mean(list(by[d].values())) for d in R.DUPS])), 'by_speaker': by,
                       'cer': R.val_cer(f, h, run, dev, 0, gather), 'checkpoint_sha256': sha(path)}
        del f, h
        if dev == 'cuda':
            torch.cuda.empty_cache()
    delta = rows['student']['mean'] - rows['teacher']['mean']
    rows.update(accuracy_delta=delta, accuracy_ok=bool(delta >= -.02), status='validation_selection_only_no_adjudication',
                overall_keep_path=None, pending=['onnx_size', 'cpu_wasm_timing'])
    (out / 'selection.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    export = {k: export_one(p, out / (k + '.onnx'), s) for k, p, s in [('teacher', a.teacher, False), ('student', a.student, True)]}
    export['size_ratio'] = export['student']['bytes'] / export['teacher']['bytes']
    export['size_ok'] = export['size_ratio'] <= .4
    (out / 'export.json').write_text(json.dumps(export, indent=2), encoding='utf-8')
    return 0


def smoke(a):
    import torch
    from train_lipread import forward_packed
    torch.set_num_threads(2)
    f, h, _ = build_student()
    f.eval(); h.eval()
    x = torch.rand(2, 1, 12, 80, 80)
    lt = torch.tensor([9, 12])
    with torch.no_grad():
        z = forward_packed(h, f(x, lt), lt)
    assert tuple(z.shape) == (2, 12, 53) and torch.isfinite(z).all()
    print(json.dumps(counts() | {'shape': list(z.shape), 'finite': True}), flush=True)
    return 0


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='cmd', required=True)
    t = sub.add_parser('train')
    t.add_argument('--run', required=True); t.add_argument('--out', required=True); t.add_argument('--teacher', required=True)
    t.set_defaults(seed=0, gpu_frac=.92)
    e = sub.add_parser('finish')
    for arg in ('run', 'out', 'teacher', 'student'):
        e.add_argument('--' + arg, required=True)
    sub.add_parser('smoke')
    a = p.parse_args()
    return {'train': train, 'finish': finish, 'smoke': smoke}[a.cmd](a)


if __name__ == '__main__':
    raise SystemExit(main())
