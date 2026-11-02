"""Registered 65% B33 student, mandatory seed0 then seed1.

Adds a preset to an imported module in this process only; old sources and
historical 12/25/38/50 results remain unchanged.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import roi_train as R
import nextreg_roi_distill as D
import nextreg_roi_distill_capacity as C

SIZE = '65'
PRESET = dict(stem=16, channels=(24, 48, 96, 192), hidden=332)
C.PRESETS[SIZE] = PRESET
TEACHER_SHA256 = C.TEACHER_SHA256
_TEACHER_BUILDER = R.build_models


def build_student(n_vocab=53, proj_dim=0):
    """Public factory for this separately registered fixed-capacity student."""
    return C.build_student(SIZE, n_vocab, proj_dim)


def parameter_counts(size=SIZE):
    assert size == SIZE
    tf, th, _ = _TEACHER_BUILDER()
    sf, sh, _ = build_student()
    nt = sum(p.numel() for m in (tf, th) for p in m.parameters())
    nf, nh = [sum(p.numel() for p in m.parameters()) for m in (sf, sh)]
    assert nt == 6047005 and nf + nh == 3940973
    return dict(teacher_parameters=nt, student_parameters=nf + nh,
                student_front_parameters=nf, student_head_parameters=nh,
                parameter_ratio=(nf + nh) / nt, size=SIZE, preset=PRESET)


def load_student(path, dev):
    return C.load_capacity(path, dev, SIZE)


def train(a):
    assert a.seed in (0, 1) and a.gpu_frac == .45 and a.size == SIZE
    original_main = R.main

    def seeded_main(argv):
        argv = list(argv)
        argv[argv.index('--seed') + 1] = str(a.seed)
        return original_main(argv)

    R.main = seeded_main
    C.parameter_counts = parameter_counts
    # C.train preserves GPU fraction, tags capacity_roi_65_v1, and invokes the
    # original distillation core. a.seed also controls its initial setup.
    return C.train(a)


def finish(a):
    import torch
    assert a.seed in (0, 1) and a.gpu_frac == .45 and a.size == SIZE
    assert D.sha(a.teacher) == TEACHER_SHA256, 'Frozen B33 seed0 teacher changed'
    D.validate(a.run)
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if (out / 'selection.json').exists():
        raise RuntimeError('Refuse duplicate seed validation selection')
    run = R.Run(a.run)
    seqs = [None if it['win'] is None else np.array([run.off[ci] + min(fr, run.T[ci]-1) for ci, fr in it['win']], np.int64)
            for it in run.val_items]

    def gather(gl):
        X, lens, *_ = R.make_batch(run, gl)
        return X, lens

    dev = 'cuda' if torch.cuda.is_available() else 'cpu'
    if dev == 'cuda':
        torch.cuda.set_per_process_memory_fraction(a.gpu_frac)
    rows = {}
    for label, path, student in [('teacher', a.teacher, False), ('student', a.student, True)]:
        f, h, ck = load_student(path, dev) if student else R.load_model(path, dev)
        assert ck['meta']['seed'] == (a.seed if student else 0)
        by = R.score4(f, h, run, seqs, run.val_items, dev, 0, gather)
        rows[label] = {'mean': float(np.mean([np.mean(list(by[d].values())) for d in R.DUPS])),
                       'by_speaker': by, 'cer': R.val_cer(f, h, run, dev, 0, gather),
                       'checkpoint_sha256': D.sha(path), 'seed': ck['meta']['seed'], 'epoch': ck['meta']['epoch']}
        del f, h, ck
        if dev == 'cuda':
            torch.cuda.empty_cache()
    delta = rows['student']['mean'] - rows['teacher']['mean']
    rows.update(accuracy_delta=delta, accuracy_ok=bool(delta >= -.02), seed=a.seed,
                status='validation_selection_only_no_adjudication', size=SIZE,
                thresholds={'accuracy_delta_min': -.02, 'size_ratio_max': .75, 'latency_ratio_max': .6},
                overall_seed_pass=None, pending=['onnx_size', 'cpu_wasm_timing'])
    (out / 'selection.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    export = {'teacher': D.export_one(a.teacher, out / 'teacher.onnx', False),
              'student': C.export_capacity(a.student, out / 'student.onnx', SIZE)}
    export['size_ratio'] = export['student']['bytes'] / export['teacher']['bytes']
    export['size_ok'] = export['size_ratio'] <= .75
    export['size_ratio_max'] = .75
    export['seed'] = a.seed
    (out / 'export.json').write_text(json.dumps(export, indent=2), encoding='utf-8')
    return 0


def smoke(a):
    import torch
    from train_lipread import forward_packed
    torch.set_num_threads(2)
    f, h, _ = build_student()
    f.eval(); h.eval()
    with torch.no_grad():
        lt = torch.tensor([9, 12])
        z = forward_packed(h, f(torch.rand(2, 1, 12, 80, 80), lt), lt)
    assert tuple(z.shape) == (2, 12, 53) and torch.isfinite(z).all()
    print(json.dumps(parameter_counts() | {'shape': list(z.shape), 'finite': True}), flush=True)
    return 0


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='cmd', required=True)
    for command in ('train', 'finish'):
        q = sub.add_parser(command)
        for arg in ('run', 'out', 'teacher'):
            q.add_argument('--' + arg, required=True)
        if command == 'finish':
            q.add_argument('--student', required=True)
        q.add_argument('--seed', type=int, choices=[0, 1], required=True)
        q.add_argument('--gpu-frac', type=float, choices=[.45], default=.45)
        q.add_argument('--size', choices=[SIZE], default=SIZE)
    sub.add_parser('smoke')
    a = p.parse_args()
    return {'train': train, 'finish': finish, 'smoke': smoke}[a.cmd](a)


if __name__ == '__main__':
    raise SystemExit(main())
