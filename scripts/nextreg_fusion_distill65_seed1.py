"""Registered paired-input full-fusion to65%-fusion distillation; student seed1; frozen teacher seed0."""
import argparse
import json
import os
from pathlib import Path
import statistics
import tempfile

import numpy as np
import roi_train as R
ORIGINAL_B33_BUILD = R.build_models
import nextreg_roi_lips as L
FULL_BUILD, FULL_ARCH = L._build, L.ARCH
import nextreg_distill65 as C
import nextreg_compact_fusion as M
ORIGINAL_FULL_LOADER = M.load_pair
for key in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS'):
    os.environ[key] = '4'

ARCH = 'fusion_distill65_roi256_lips80_kd_v1'
TEACHER_SHA = M.FULL_SHA
B33_SHA = 'a0d2ff6c17799a0036f20dcf346594de0de794dfc358480d64c211928983c35f'
COUNTS = {'teacher_parameters': 6068989, 'student_parameters': 3962957, 'roi_parameters': 3940973,
          'coordinate_parameters': 21984, 'parameter_ratio': 3962957 / 6068989}


def configure(compact=True):
    L._build = C.build_student if compact else FULL_BUILD
    L.ARCH = ARCH if compact else FULL_ARCH


def references(a):
    assert L.sha(a.teacher) == TEACHER_SHA, 'Frozen full fusion seed0 changed'
    assert L.sha(Path(a.baseline) / 'model.pt') == B33_SHA, 'Frozen B33 seed1 changed'


def cache_chunks(run, out, predict):
    """Shared cache writing logic; predict receives ONLY training-role global frames."""
    out = Path(out)
    p, meta_path = out / 'teacher_logits_f16.bin', out / 'teacher_logits.json'
    if p.exists() or meta_path.exists():
        raise RuntimeError('Refuse duplicate teacher cache')
    tmp = Path(str(p) + '.tmp')
    arr = np.memmap(tmp, np.float16, 'w+', shape=(run.meta['frames'], 53))
    arr[:] = 0
    clips = [i for i, c in enumerate(run.clips) if c['role'] == 'train']
    for ni, ci in enumerate(clips):
        for st in range(0, int(run.T[ci]), 400):
            g = run.gidx(ci, np.arange(st, min(st + 400, run.T[ci])))
            values = np.asarray(predict(g), dtype=np.float16)
            assert values.shape == (len(g), 53) and np.isfinite(values).all()
            arr[g] = values
        if ni % 25 == 0:
            print('FUSION65_S1_KD_CACHE', ni + 1, '/', len(clips), flush=True)
    arr.flush()
    del arr
    tmp.replace(p)
    meta = {'teacher_sha256': TEACHER_SHA, 'teacher_seed': 0, 'teacher_architecture': FULL_ARCH,
            'teacher_window_frames': 400, 'train_clip_count': len(clips),
            'validation_clip_count_not_predicted': sum(c['role'] == 'val' for c in run.clips),
            'frames': run.meta['frames'], 'dtype': 'float16', 'dim': 53,
            'targets': 'paired_clean_center_roi_and_lips; train_only; student_augmented_consistency',
            'cache_sha256': L.sha(p)}
    L.dump(meta_path, meta)
    return np.memmap(p, np.float16, 'r', shape=(run.meta['frames'], 53)), meta


def cache_teacher(a, run, dev):
    import torch
    from train_lipread import forward_packed
    front, head = ORIGINAL_FULL_LOADER(a.teacher, False)
    front.to(dev).eval(); head.to(dev).eval()
    configure(True)
    def predict(g):
        x, lens, *_ = R.make_batch(run, [g])
        pair = R.normalize(x, lens, None, None, dev)
        lt = torch.from_numpy(lens)
        return forward_packed(head, R.run_front(front, pair, lt, 0), lt)[0, :len(g)].cpu().numpy()
    with torch.no_grad():
        target, provenance = cache_chunks(run, a.out, predict)
    del front, head
    if dev == 'cuda':
        torch.cuda.empty_cache()
    return target, provenance


def frame_kl(logp, teacher, lens, total_frames, batch_size):
    """Undo the external microgroup item fraction, preserving full-batch frame mean."""
    import torch
    import torch.nn.functional as F
    slp = F.log_softmax(logp.transpose(0, 1) / 2, -1)
    tp = F.softmax(teacher / 2, -1)
    valid = torch.arange(slp.shape[1], device=slp.device)[None] < lens.to(slp.device)[:, None]
    kd = (F.kl_div(slp, tp, reduction='none').sum(-1) * valid).sum()
    return kd / total_frames * (batch_size / len(lens))


def train(a):
    import torch
    import torch.nn as nn
    references(a)
    L.allowed(a.run)
    if Path(a.out).exists() and any(Path(a.out).iterdir()):
        raise RuntimeError('One student seed1; refuse nonempty training output')
    Path(a.out).mkdir(parents=True, exist_ok=True)
    configure(True)
    manifest = L.install(a.lips)
    torch.set_num_threads(4)
    dev = R.setup(argparse.Namespace(seed=1, gpu_frac=.45))
    run = R.Run(a.run)
    targets, provenance = cache_teacher(a, run, dev)
    info = dict(COUNTS, architecture=ARCH, seed=1, method='paired_full_fusion_distillation_T2',
                lips_manifest_sha256=L.sha(Path(a.lips) / 'manifest.json'),
                lips_pack_sha256=manifest['pack_sha256'], prep_sha256=manifest['prep_sha256'])
    L.dump(Path(a.out) / 'architecture.json', info | provenance)
    original_batch, original_front, original_save = R.make_batch, R.run_front, R.save_atomic
    base_ctc = nn.CTCLoss
    context = {}
    def batch(run, gl, rng=None, **kw):
        result = original_batch(run, gl, rng=rng, **kw)
        if rng is not None:
            x, lens, *_ = result
            target = np.zeros((len(gl), x.shape[1], 53), np.float16)
            for j, g in enumerate(gl):
                target[j, :len(g)] = targets[g]
            context.update(target=target, cursor=0, batch_size=len(gl), frames=int(lens.sum()))
        return result
    def run_front(front, pair, lt, amp):
        if front.training:
            lo, hi = context['cursor'], context['cursor'] + len(lt)
            assert hi <= len(context['target'])
            context['current'] = torch.from_numpy(context['target'][lo:hi, :pair[0].shape[2]].copy()).to(pair[0].device).float()
            context['cursor'] = hi
        return original_front(front, pair, lt, amp)
    class KDCTC(nn.Module):
        def __init__(self, *args, **kw):
            super().__init__()
            self.base = base_ctc(*args, **kw)
        def forward(self, logp, target, lens, target_lens):
            return .5 * self.base(logp, target, lens, target_lens) + .5 * 4 * frame_kl(
                logp, context['current'], lens, context['frames'], context['batch_size'])
    def save(obj, path):
        if 'front' in obj:
            obj['architecture'] = ARCH
            obj['student_seed'] = 1
            obj['teacher_seed'] = 0
            obj['full_reference_sha256'] = TEACHER_SHA
            obj['training_method'] = 'paired_full_fusion_distillation_T2'
            obj['distillation'] = info | provenance | {'temperature': 2, 'ctc_weight': .5, 'kd_weight': .5}
        return original_save(obj, path)
    R.make_batch, R.run_front, R.save_atomic = batch, run_front, save
    R.Prefetch = lambda gen: iter(gen)
    nn.CTCLoss = KDCTC
    return R.main(['train', '--run', a.run, '--out', a.out, '--cand', 'R1', '--seed', '1',
                   '--epochs', '40', '--patience', '6', '--batch', '32', '--max-frames', '4000',
                   '--gpu-frac', '.45', '--amp', '0', '--log-every', '100'])


def load_pair(path, compact):
    import torch
    if not compact:
        return ORIGINAL_FULL_LOADER(path, False)
    ck = torch.load(path, map_location='cpu', weights_only=False)
    assert ck['architecture'] == ARCH and ck['fusion_architecture'] == ARCH
    assert ck['meta']['seed'] == 1 and ck['meta']['init'] is None
    assert ck['student_seed'] == 1 and ck['teacher_seed'] == 0
    assert ck['distillation']['teacher_sha256'] == TEACHER_SHA
    configure(True)
    f, h, _ = L.models(len(ck['vocab']))
    f.load_state_dict(ck['front']); h.load_state_dict(ck['head'])
    assert sum(p.numel() for m in (f, h) for p in m.parameters()) == COUNTS['student_parameters']
    return f.float().eval(), h.float().eval()


def finish(a):
    import torch
    references(a)
    configure(True)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    student = Path(a.student)
    assert student.name == 'model.pt'
    accuracy_path = out / 'accuracy-selection.json'
    if not accuracy_path.exists():
        L.compare(argparse.Namespace(run=a.run, out=str(accuracy_path), seed=1,
                                    candidate=str(student.parent), baseline=a.baseline))
    accuracy = M.read(accuracy_path)
    assert accuracy['architecture'] == ARCH and accuracy['baseline_model_sha256'] == B33_SHA
    assert accuracy['candidate_model_sha256'] == L.sha(student)
    if (out / 'export.json').exists():
        raise RuntimeError('Refuse duplicate FP32 exports')
    torch.set_num_threads(4)
    M.load_pair = load_pair
    exports = {'full': M.export_one(a.teacher, out / 'full.onnx', False),
               'compact': M.export_one(student, out / 'compact.onnx', True)}
    exports.update(size_ratio=exports['compact']['bytes'] / exports['full']['bytes'], size_ratio_max=.75,
                   status='pending_wasm_development_selection')
    exports['size_ok'] = exports['size_ratio'] <= .75
    L.dump(out / 'export.json', exports)
    print('FUSION65_S1_EXPORTED', exports['size_ratio'], exports['size_ok'], flush=True)


def finalize(a):
    import math
    out = Path(a.out)
    if (out / 'selection.json').exists():
        raise RuntimeError('Refuse overwrite of final four-gate decision')
    accuracy, export, wasm = (M.read(out / n) for n in ('accuracy-selection.json', 'export.json', 'wasm.json'))
    assert accuracy['architecture'] == ARCH and accuracy['seed'] == 1 and accuracy['baseline_model_sha256'] == B33_SHA
    assert export['full']['checkpoint_sha256'] == TEACHER_SHA
    assert export['compact']['checkpoint_sha256'] == accuracy['candidate_model_sha256']
    assert export['size_ratio_max'] == .75
    assert wasm['input_sha256'] == M.INPUT_SHA and wasm['host'].upper() == 'CNSAI2025'
    assert wasm['ort_version'] == '1.19.2' and wasm['num_threads'] == 1 and wasm['node'].startswith('v24.')
    assert wasm['execution_provider'] == 'onnxruntime-web WASM CPU' and wasm['protocol'] == M.WASM_PROTOCOL
    medians = {}
    for key in ('full', 'compact'):
        p = out / (key + '.onnx')
        assert L.sha(p) == export[key]['sha256'] == wasm['model_sha256'][key]
        assert p.stat().st_size == export[key]['bytes'] and export[key]['weights'] == 'FP32' and export[key]['opset'] == 17
        assert 0 <= export[key]['wrap_diff'] < .001 and 0 <= export[key]['onnx_diff'] < .001
        values = wasm['samples_ms'][key]
        assert len(values) == 20 and all(math.isfinite(v) and v > 0 for v in values)
        medians[key] = statistics.median(values)
        assert math.isclose(medians[key], wasm[key + '_median_ms'], rel_tol=1e-12, abs_tol=1e-9)
    size_ratio = export['compact']['bytes'] / export['full']['bytes']
    latency_ratio = medians['compact'] / medians['full']
    assert math.isclose(size_ratio, export['size_ratio'], rel_tol=1e-12, abs_tol=1e-12)
    assert math.isclose(latency_ratio, wasm['latency_ratio'], rel_tol=1e-12, abs_tol=1e-12)
    assert all(math.isfinite(accuracy[k]) for k in ('accuracy_delta', 'cer_delta'))
    gates = {'accuracy': accuracy['accuracy_delta'] >= .02, 'cer': accuracy['cer_delta'] <= .02,
             'size': size_ratio <= .75, 'latency': latency_ratio <= .6}
    assert accuracy['keep_path'] == (gates['accuracy'] and gates['cer']) and export['size_ok'] == gates['size']
    result = {'status': 'validation_selection_only_no_adjudication', 'architecture': ARCH, 'seed': 1,
              'gates': gates, 'thresholds': {'accuracy_delta_min': .02, 'cer_delta_max': .02, 'size_ratio_max': .75, 'latency_ratio_max': .6},
              'overall_keep_path': all(gates.values()), 'accuracy_delta': accuracy['accuracy_delta'],
              'per_seed_all_four_pass': all(gates.values()), 'seed1_registered_by_new_user_directive': True,
              'original_seed0_deferral_superseded_prospectively': True,
              'stability_evidence_condition': 'Only if D65s0 passes all four gates; otherwise RECORD_ONLY regardless seed1 result; never choose the better seed.',
              'registered_wasm_global_order': ['C0', 'C1', 'D0', 'D1', 'C65s0', 'C65s1', 'D65s0', 'D65s1'],
              'student_seed': 1, 'teacher_seed': 0,
              'cer_delta': accuracy['cer_delta'], 'size_ratio': size_ratio, 'latency_ratio': latency_ratio, **COUNTS,
              'teacher_sha256': TEACHER_SHA, 'baseline_sha256': B33_SHA,
              'candidate_sha256': accuracy['candidate_model_sha256'],
              'shared_harness_old_50percent_latency_flag_not_used': wasm.get('latency_ok'),
              'source_sha256': {n: L.sha(out / n) for n in ('accuracy-selection.json', 'export.json', 'wasm.json')},
              'interpretation': 'Development validation12; no independent judgement; clean evaluation pending; no app/Android claim.'}
    L.dump(out / 'selection.json', result)
    print('FUSION65_S1_FINAL', json.dumps(result), flush=True)


def smoke(a):
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    torch.set_num_threads(4)
    configure(True)
    from unittest.mock import patch
    with patch.object(torch.cuda, 'is_available', return_value=False):
        assert R.setup(argparse.Namespace(seed=1, gpu_frac=.45)) == 'cpu'
    assert torch.initial_seed() == 1
    base, bh, _ = C.build_student()
    torch.manual_seed(1)
    f, h, _ = L.models()
    assert all(torch.equal(v, f.pixel.state_dict()[k]) for k, v in base.state_dict().items())
    assert all(torch.equal(v, h.state_dict()[k]) for k, v in bh.state_dict().items())
    assert sum(p.numel() for m in (f, h) for p in m.parameters()) == 3962957
    assert sum(p.numel() for m in (base, bh) for p in m.parameters()) == 3940973
    torch.manual_seed(0)
    other, oh, _ = C.build_student()
    assert not torch.equal(base.c3.weight, other.c3.weight)
    del other, oh
    del base, bh
    roi, lips = map(torch.from_numpy, M.synthetic_inputs())
    f.eval(); h.eval()
    with torch.no_grad():
        ref = M.reference_logits(f, h, roi, lips)
        lo = M.wrapper(f, h, True)(roi, lips)
    assert lo.shape == (1, 75, 53) and torch.isfinite(lo).all() and (lo - ref).abs().max() < 1e-3
    with tempfile.TemporaryDirectory(prefix='fusion65-s1-synthetic-') as tmp:
        tmp = Path(tmp)
        lp = np.repeat((np.arange(12, dtype=np.float32) / 16)[:, None], 80, 1)
        lp.tofile(tmp / 'lips_f32.bin')
        L.dump(tmp / 'manifest.json', {'pack_sha256': L.sha(tmp / 'lips_f32.bin'), 'frames': 12, 'prep_sha256': 'SYNTHETIC'})
        L.install(tmp)
        torch.set_num_threads(4)
        class Fake:
            meta = {'frames': 12}
            clips = [{'role': 'train'}, {'role': 'train'}, {'role': 'val'}]
            T = np.array([3, 5, 4]); off = np.array([0, 3, 8])
            roi = np.repeat(np.arange(12, dtype=np.uint8)[:, None, None], 88 * 88, 1).reshape(12, 88, 88)
            lips = lp
            gidx = R.Run.gidx
        fake = Fake()
        seen = []
        def predict(g):
            seen.extend(g.tolist())
            x, lens, *_ = R.make_batch(fake, [g])
            assert np.array_equal(x.lips[0, :len(g)], lp[g])
            assert np.all(np.asarray(x)[0, :len(g)] == g[:, None, None])
            return np.repeat(x.lips[0, :len(g), :1], 53, 1)
        target, provenance = cache_chunks(fake, tmp, predict)
        assert seen == list(range(8)) and provenance['train_clip_count'] == 2
        assert np.array_equal(target[:8, 0], (np.arange(8) / 16).astype(np.float16)) and not target[8:].any()
        sampled = np.array([4, 0, 7, 4])
        assert np.array_equal(target[sampled, 0], lp[sampled, 0].astype(np.float16))
        x, lens, flips, mask, _ = R.make_batch(fake, [sampled, np.array([2, 1, 0])])
        flips[:] = True; mask[:] = False; mask[0, 1] = True
        pair = R.normalize(x, lens, flips, mask, 'cpu')
        assert isinstance(pair, tuple) and pair[0].shape[2] == 4 and pair[0].device.type == 'cpu'
        assert pair[1][0, 1].abs().sum() == 0 and pair[2][0, 1] == 0
        assert pair[1][1, 3:].abs().sum() == 0
        del target
    torch.manual_seed(2)
    lengths = torch.tensor([3, 5, 8])
    logp = F.log_softmax(torch.randn(8, 3, 53), -1)
    teacher = torch.randn(3, 8, 53)
    whole = frame_kl(logp, teacher, lengths, 16, 3)
    grouped = sum(frame_kl(logp[:, g], teacher[g], lengths[g], 16, 3) * len(g) / 3
                  for g in R.frame_groups(lengths.numpy(), 8))
    assert torch.allclose(whole, grouped, atol=1e-7, rtol=1e-6)
    smoke_seed_controller()
    print('FUSION65_S1_SYNTHETIC_SMOKE_OK params3962957 trueinitialseed1_Rmainseed1_checkpointseed1_teacher0 pairedtrainonlycache tuple_masks aligned_reindex fullbatchKL wrapper CPU4 cap.45', flush=True)


def smoke_seed_controller():
    """Intercept actual train controller with synthetic I/O; never allocate a GPU."""
    import torch.nn as nn
    from contextlib import ExitStack
    from unittest.mock import patch
    captured = {}
    with tempfile.TemporaryDirectory(prefix='fusion65-s1-controller-synthetic-') as tmp:
        out = Path(tmp) / 'new_seed1'
        def setup(opts):
            captured['setup'] = (opts.seed, opts.gpu_frac)
            return 'cpu'
        def main(argv):
            captured['argv'] = list(argv)
            R.save_atomic({'front': {}, 'meta': {'seed': int(argv[argv.index('--seed') + 1])}}, out / 'synthetic.pt')
            return 0
        with ExitStack() as stack:
            stack.enter_context(patch.dict(globals(), {'references': lambda a: None,
                'cache_teacher': lambda a, run, dev: (np.zeros((1, 53), np.float16),
                    {'teacher_seed': 0, 'teacher_sha256': TEACHER_SHA})}))
            stack.enter_context(patch.object(L, 'allowed', lambda path: None))
            stack.enter_context(patch.object(L, 'install', lambda path: {'pack_sha256': 'SYNTHETIC', 'prep_sha256': 'SYNTHETIC'}))
            stack.enter_context(patch.object(L, 'sha', lambda path: 'SYNTHETIC'))
            stack.enter_context(patch.object(R, 'setup', setup))
            stack.enter_context(patch.object(R, 'main', main))
            stack.enter_context(patch.object(R, 'Run', lambda path: object()))
            stack.enter_context(patch.object(R, 'save_atomic', lambda obj, path: captured.update(checkpoint=dict(obj))))
            for name in ('make_batch', 'run_front', 'Prefetch'):
                stack.enter_context(patch.object(R, name, getattr(R, name)))
            stack.enter_context(patch.object(nn, 'CTCLoss', nn.CTCLoss))
            train(argparse.Namespace(run='SYNTHETIC', teacher='SYNTHETIC', baseline='SYNTHETIC', lips='SYNTHETIC', out=str(out)))
        argv = captured['argv']
        assert captured['setup'] == (1, .45)
        assert argv[argv.index('--seed') + 1] == '1' and argv[argv.index('--gpu-frac') + 1] == '.45'
        assert argv[argv.index('--amp') + 1] == '0'
        ck = captured['checkpoint']
        assert ck['meta']['seed'] == ck['student_seed'] == ck['distillation']['seed'] == 1
        assert ck['teacher_seed'] == ck['distillation']['teacher_seed'] == 0
        assert ck['distillation']['teacher_sha256'] == TEACHER_SHA
        assert M.read(out / 'architecture.json')['seed'] == 1


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='cmd', required=True)
    for cmd in ('train', 'finish'):
        q = sub.add_parser(cmd)
        for arg in ('run', 'teacher', 'lips', 'baseline', 'out'):
            q.add_argument('--' + arg, required=True)
        if cmd == 'finish':
            q.add_argument('--student', required=True)
        q.add_argument('--seed', type=int, choices=[1], default=1)
        q.add_argument('--gpu-frac', type=float, choices=[.45], default=.45)
    sub.add_parser('smoke')
    q = sub.add_parser('finalize'); q.add_argument('--out', required=True)
    a = p.parse_args()
    return {'train': train, 'finish': finish, 'smoke': smoke, 'finalize': finalize}[a.cmd](a)


if __name__ == '__main__':
    raise SystemExit(main())
