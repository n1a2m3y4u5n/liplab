"""Registered seed1 reproduction of the frozen 38% B33 student selection.

The teacher remains B33 seed0. No model export or timing is repeated here.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import roi_train as R
import nextreg_roi_distill as D
import nextreg_roi_distill_capacity as C

FROZEN = {
    'selection_commit': 'e5249451',
    'size_ratio': 0.3838760645347203,
    'latency_ratio': 0.19819926872660118,
    'export_json': r'D:\work\hq\projects\liplab\out\nextreg-2026-11-02\distill_capacity\38\export.json',
    'export_json_sha256': '0880f6264169543a17edc57bbef1d25b136fe026cb0db01b89d305070888df67',
    'wasm_json': r'D:\work\hq\projects\liplab\out\nextreg-2026-11-02\distill_capacity\38\wasm.json',
    'wasm_json_sha256': '4b690a5199f2244a72a1ac84b0e05a8a8f36787370bb52267c008f3499aff8e4',
    'reused_seed0_measurements': True,
}


def train(a):
    assert a.seed == 1 and a.size == '38' and a.gpu_frac == .92
    original_main = R.main
    original_save = R.save_atomic

    def seed1_main(argv):
        argv = list(argv)
        argv[argv.index('--seed') + 1] = '1'
        return original_main(argv)

    def tagged_save(obj, path):
        if 'front' in obj:
            obj['reproduction'] = {'student_seed': 1, 'teacher_seed': 0,
                                   'teacher_sha256': C.TEACHER_SHA256,
                                   'parent_selection_commit': FROZEN['selection_commit']}
        return original_save(obj, path)

    # C.train captures this main wrapper, then D.train resets the initial setup
    # using a.seed=1. The final R.main invocation must also receive --seed=1.
    R.main = seed1_main
    R.save_atomic = tagged_save
    return C.train(a)


def finish(a):
    import torch
    assert a.seed == 1 and a.size == '38' and a.gpu_frac == .92
    assert D.sha(a.teacher) == C.TEACHER_SHA256, 'Frozen B33 seed0 teacher changed'
    D.validate(a.run)
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if (out / 'selection.json').exists() or (out / 'decision.json').exists():
        raise RuntimeError('Refuse duplicate seed1 reproduction selection')
    run = R.Run(a.run)
    seqs = [None if it['win'] is None else np.array([run.off[ci] + min(fr, run.T[ci]-1) for ci, fr in it['win']], np.int64)
            for it in run.val_items]

    def gather(gl):
        X, lens, *_ = R.make_batch(run, gl)
        return X, lens

    dev = 'cuda' if torch.cuda.is_available() else 'cpu'
    if dev == 'cuda':
        torch.cuda.set_per_process_memory_fraction(.92)
    rows = {}
    for label, path, student in [('teacher', a.teacher, False), ('student', a.student, True)]:
        f, h, ck = C.load_capacity(path, dev, '38') if student else R.load_model(path, dev)
        assert ck['meta']['seed'] == (1 if student else 0)
        by = R.score4(f, h, run, seqs, run.val_items, dev, 0, gather)
        rows[label] = {'mean': float(np.mean([np.mean(list(by[d].values())) for d in R.DUPS])),
                       'by_speaker': by, 'cer': R.val_cer(f, h, run, dev, 0, gather),
                       'checkpoint_sha256': D.sha(path), 'seed': ck['meta']['seed'], 'epoch': ck['meta']['epoch']}
        del f, h, ck
        if dev == 'cuda':
            torch.cuda.empty_cache()
    delta = rows['student']['mean'] - rows['teacher']['mean']
    reproduced = bool(delta >= -.02)
    rows.update(accuracy_delta=delta, accuracy_ok=reproduced, seed1_reproduced=reproduced,
                status='validation_selection_only_no_adjudication', frozen_seed0=FROZEN,
                historical_seed0_selection_preserved=True, scientific_change='student_seed0_to_seed1_only',
                annotation='seed1 재현' if reproduced else 'seed1 미재현')
    (out / 'selection.json').write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding='utf-8')
    decision = {'seed1_reproduced': reproduced, 'accuracy_delta': delta, 'accuracy_threshold': -.02,
                'reused_seed0_size_ok': FROZEN['size_ratio'] <= .4,
                'reused_seed0_latency_ok': FROZEN['latency_ratio'] <= .5,
                'frozen_seed0': FROZEN, 'annotation': rows['annotation'],
                'historical_seed0_selection_preserved': True, 'no_best_seed_selection': True,
                'status': 'validation_reproduction_only_no_adjudication'}
    (out / 'decision.json').write_text(json.dumps(decision, indent=2, ensure_ascii=False), encoding='utf-8')
    print('DISTILL38_REPRO ' + json.dumps(decision, ensure_ascii=False), flush=True)
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
        q.add_argument('--seed', type=int, choices=[1], default=1)
        q.add_argument('--size', choices=['38'], default='38')
        q.add_argument('--gpu-frac', type=float, choices=[.92], default=.92)
    a = p.parse_args()
    return {'train': train, 'finish': finish}[a.cmd](a)


if __name__ == '__main__':
    raise SystemExit(main())
