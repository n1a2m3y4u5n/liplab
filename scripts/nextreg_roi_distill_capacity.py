"""Two separately fixed capacity presets for one registered B33 distillation curve.

No modification or reinterpretation of the earlier compact candidate's result.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import roi_train as R
import nextreg_roi_distill as D

TEACHER_SHA256 = 'd499c9f26affd57ef9cc4014c48337669ecfed7466a1ef8ac81c68742007ca1a'
PRESETS = {'25': dict(stem=12, channels=(16, 32, 64, 112), hidden=192),
           '38': dict(stem=16, channels=(24, 48, 96, 192), hidden=224)}


def build_student(size, n_vocab=53, proj_dim=0):
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    config = PRESETS[size]
    stem, channels, hidden = config['stem'], config['channels'], config['hidden']

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
            self.c3 = nn.Conv3d(1, stem, (5, 7, 7), (1, 2, 2), (2, 3, 3), bias=False)
            self.b3 = nn.BatchNorm2d(stem)
            self.stages = nn.ModuleList([Block(stem if i == 0 else channels[i - 1], c, 1 if i == 0 else 2)
                                         for i, c in enumerate(channels)])
            self.fc = nn.Linear(channels[-1], 256)
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
            out = v.new_zeros(B, T, 256)
            out[m] = v
            return out

    class Head(nn.Module):
        def __init__(self):
            super().__init__()
            self.norm = nn.LayerNorm(256)
            self.gru = nn.GRU(256, hidden, num_layers=2, batch_first=True, bidirectional=True, dropout=.2)
            self.out = nn.Linear(hidden * 2, n_vocab)

        def forward(self, x):
            return self.out(self.gru(self.norm(x))[0])

    assert not proj_dim
    return Front(), Head(), None


def parameter_counts(size):
    tf, th, _ = R.build_models()
    sf, sh, _ = build_student(size)
    nt = sum(p.numel() for m in (tf, th) for p in m.parameters())
    nf, nh = [sum(p.numel() for p in m.parameters()) for m in (sf, sh)]
    ns = nf + nh
    assert ({'25': .24, '38': .38}[size]) <= ns / nt <= ({'25': .25, '38': .39}[size])
    return dict(teacher_parameters=nt, student_parameters=ns, student_front_parameters=nf,
                student_head_parameters=nh, parameter_ratio=ns / nt, size=size, preset=PRESETS[size])


def load_capacity(path, dev, size):
    import torch
    ck = torch.load(path, map_location='cpu', weights_only=False)
    assert ck['architecture'] == 'capacity_roi_' + size + '_v1'
    f, h, _ = build_student(size, len(ck['vocab']))
    f.load_state_dict(ck['front'])
    h.load_state_dict(ck['head'])
    return f.to(dev).eval(), h.to(dev).eval(), ck


def train(a):
    assert D.sha(a.teacher) == TEACHER_SHA256, 'Fixed B33 teacher changed'
    original_save = R.save_atomic
    original_main = R.main

    def tagged_save(obj, path):
        if 'front' in obj:
            obj['architecture'] = 'capacity_roi_' + a.size + '_v1'
        return original_save(obj, path)

    R.save_atomic = tagged_save

    def main_with_fraction(argv):
        argv = list(argv)
        argv[argv.index('--gpu-frac') + 1] = str(a.gpu_frac)
        return original_main(argv)

    R.main = main_with_fraction
    D.build_student = lambda n_vocab=53, proj_dim=0: build_student(a.size, n_vocab, proj_dim)
    D.counts = lambda: parameter_counts(a.size)
    return D.train(a)


def export_capacity(path, out, size):
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    import onnxruntime as ort
    f, h, _ = load_capacity(path, 'cpu', size)
    stem = PRESETS[size]['stem']

    class Wrap(nn.Module):
        def __init__(self):
            super().__init__()
            self.front, self.head = f, h

        def forward(self, roi):
            x = roi / 255.
            x = x - x.mean(dim=(1, 2, 3), keepdim=True)
            x = x / x.square().mean(dim=(1, 2, 3), keepdim=True).sqrt().clamp(min=.01)
            x = F.avg_pool3d(x.unsqueeze(1), (1, 2, 2), (1, 2, 2))
            B, _, T, H, W = x.shape
            v = self.front.c3(x).transpose(1, 2).reshape(B * T, stem, H // 2, W // 2)
            v = F.max_pool2d(F.relu(self.front.b3(v)), 3, 2, 1)
            for st in self.front.stages:
                v = st(v)
            z = self.front.fc(v.mean(dim=(2, 3))).reshape(B, T, 256)
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
    return {'bytes': Path(out).stat().st_size, 'sha256': D.sha(out), 'wrap_diff': a, 'onnx_diff': b}


def finish(a):
    import torch
    assert D.sha(a.teacher) == TEACHER_SHA256, 'Fixed B33 teacher changed'
    D.validate(a.run)
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
        torch.cuda.set_per_process_memory_fraction(a.gpu_frac)
    for label, path, student in [('teacher', a.teacher, False), ('student', a.student, True)]:
        f, h, _ = load_capacity(path, dev, a.size) if student else R.load_model(path, dev)
        by = R.score4(f, h, run, seqs, run.val_items, dev, 0, gather)
        rows[label] = {'mean': float(np.mean([np.mean(list(by[d].values())) for d in R.DUPS])), 'by_speaker': by,
                       'cer': R.val_cer(f, h, run, dev, 0, gather), 'checkpoint_sha256': D.sha(path)}
        del f, h
        if dev == 'cuda':
            torch.cuda.empty_cache()
    delta = rows['student']['mean'] - rows['teacher']['mean']
    rows.update(accuracy_delta=delta, accuracy_ok=bool(delta >= -.02), status='validation_selection_only_no_adjudication',
                size=a.size, overall_keep_path=None, pending=['onnx_size', 'cpu_wasm_timing'])
    (out / 'selection.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    export = {'teacher': D.export_one(a.teacher, out / 'teacher.onnx', False),
              'student': export_capacity(a.student, out / 'student.onnx', a.size)}
    export['size_ratio'] = export['student']['bytes'] / export['teacher']['bytes']
    export['size_ok'] = export['size_ratio'] <= .4
    (out / 'export.json').write_text(json.dumps(export, indent=2), encoding='utf-8')
    return 0


def smoke(a):
    import torch
    from train_lipread import forward_packed
    torch.set_num_threads(2)
    f, h, _ = build_student(a.size)
    f.eval(); h.eval()
    x = torch.rand(2, 1, 12, 80, 80)
    with torch.no_grad():
        z = forward_packed(h, f(x, torch.tensor([9, 12])), torch.tensor([9, 12]))
    assert tuple(z.shape) == (2, 12, 53) and torch.isfinite(z).all()
    print(json.dumps(parameter_counts(a.size) | {'shape': list(z.shape), 'finite': True}), flush=True)
    return 0


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='cmd', required=True)
    t = sub.add_parser('train')
    t.add_argument('--run', required=True); t.add_argument('--out', required=True); t.add_argument('--teacher', required=True)
    t.add_argument('--size', choices=PRESETS, required=True)
    t.add_argument('--gpu-frac', type=float, choices=[.45, .92], required=True)
    t.set_defaults(seed=0)
    e = sub.add_parser('finish')
    for arg in ('run', 'out', 'teacher', 'student'):
        e.add_argument('--' + arg, required=True)
    e.add_argument('--size', choices=PRESETS, required=True)
    e.add_argument('--gpu-frac', type=float, choices=[.45, .92], required=True)
    s = sub.add_parser('smoke')
    s.add_argument('--size', choices=PRESETS, required=True)
    a = p.parse_args()
    return {'train': train, 'finish': finish, 'smoke': smoke}[a.cmd](a)


if __name__ == '__main__':
    raise SystemExit(main())
