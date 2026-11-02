"""One frozen compact38+coordinates CTC seed; development selection only."""
import argparse
import json
import os
from pathlib import Path
import statistics

os.environ['OMP_NUM_THREADS'] = '2'
os.environ['MKL_NUM_THREADS'] = '2'
os.environ['OPENBLAS_NUM_THREADS'] = '2'
import numpy as np
import roi_train as R
import nextreg_roi_lips as L
import nextreg_roi_distill_capacity as C

ARCH = 'compact38_roi256_plus_LN80_Linear64_GELU_Linear256_ctc_v1'
FULL_ARCH = L.ARCH
FULL_BUILD = L._build
FULL_SHA = '42b5fc382377c3a6db4567a989d372b741d8b34504323956bd92bb58ed084c35'
B33_SHA = 'd499c9f26affd57ef9cc4014c48337669ecfed7466a1ef8ac81c68742007ca1a'
INPUT_SHA = {'roi': '3b2b48ccab377f037ed82015d9cbc84f811392a4c3fa7fa7539a744534c8ccc7',
             'lips': '7c8383e4a505b00880d73e2079d59cb4167efba8aa112109c8affb14b8ce9ad3',
             'combined': '0fe46e1232254fb6193d2fd25d295893394894f2058337f67d018fe771b6c2a8'}
COUNTS = {'full_parameters': 6068989, 'compact_parameters': 2341877, 'coordinate_parameters': 21984}
WASM_PROTOCOL = ('5 warmups/model; 20 alternating-order pairs; median walltime session.run only; '
                 'roi B1T75x80x80 plus lips B1T75x80; xorshift20261102')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def configure(compact):
    L._build = (lambda n_vocab=53, proj_dim=0: C.build_student('38', n_vocab, proj_dim)) if compact else FULL_BUILD
    L.ARCH = ARCH if compact else FULL_ARCH


def references(a):
    assert L.sha(a.full_reference) == FULL_SHA, 'Frozen full fusion seed0 changed'
    assert L.sha(Path(a.baseline) / 'model.pt') == B33_SHA, 'Frozen B33 seed0 changed'


def synthetic_inputs():
    import hashlib
    state = 20261102
    def next_u32():
        nonlocal state
        state = (state ^ (state << 13)) & 0xffffffff
        state ^= state >> 17
        state = (state ^ (state << 5)) & 0xffffffff
        return state
    roi = np.fromiter((next_u32() % 256 for _ in range(75 * 80 * 80)), np.float32).reshape(1, 75, 80, 80)
    lips = np.fromiter((next_u32() / 4294967296 - .5 for _ in range(75 * 80)), np.float32).reshape(1, 75, 80)
    hashes = {'roi': hashlib.sha256(roi.tobytes()).hexdigest(), 'lips': hashlib.sha256(lips.tobytes()).hexdigest(),
              'combined': hashlib.sha256(roi.tobytes() + lips.tobytes()).hexdigest()}
    assert hashes == INPUT_SHA
    return roi, lips


def train(a):
    references(a)
    L.allowed(a.run)
    out = Path(a.out)
    if out.exists() and any(out.iterdir()):
        raise RuntimeError('One scientific seed; refuse nonempty training output')
    out.mkdir(parents=True, exist_ok=True)
    configure(True)
    manifest = L.install(a.lips)
    provenance = dict(COUNTS, architecture=ARCH, method='ctc_from_scratch_no_distillation', seed=0,
                      full_reference_sha256=FULL_SHA, baseline_sha256=B33_SHA,
                      lips_manifest_sha256=L.sha(Path(a.lips) / 'manifest.json'),
                      lips_pack_sha256=manifest['pack_sha256'], prep_sha256=manifest['prep_sha256'])
    L.dump(out / 'architecture.json', provenance)
    save = R.save_atomic
    def tagged_save(obj, path):
        obj['full_reference_sha256'] = FULL_SHA
        obj['training_method'] = 'ctc_from_scratch_no_distillation'
        return save(obj, path)
    R.save_atomic = tagged_save
    return R.main(['train', '--run', a.run, '--out', str(out), '--cand', 'R1', '--seed', '0',
                   '--epochs', '40', '--patience', '6', '--batch', '32', '--max-frames', '4000',
                   '--gpu-frac', '.45', '--log-every', '100', '--amp', '1'])


def compare(a):
    references(a)
    configure(True)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    target = out / 'accuracy-selection.json'
    opts = argparse.Namespace(run=a.run, out=str(target), seed=0, candidate=a.candidate, baseline=a.baseline)
    L.compare(opts)
    return read(target)


def load_pair(path, compact):
    import torch
    if not compact:
        assert L.sha(path) == FULL_SHA
    ck = torch.load(path, map_location='cpu', weights_only=False)
    configure(compact)
    assert ck['fusion_architecture'] == (ARCH if compact else FULL_ARCH)
    assert ck['meta']['seed'] == 0 and ck['meta']['init'] is None
    if compact:
        assert ck['full_reference_sha256'] == FULL_SHA and ck['training_method'] == 'ctc_from_scratch_no_distillation'
    front, head, _ = L.models(len(ck['vocab']))
    front.load_state_dict(ck['front'])
    head.load_state_dict(ck['head'])
    total = sum(p.numel() for m in (front, head) for p in m.parameters())
    assert total == COUNTS['compact_parameters' if compact else 'full_parameters']
    return front.float().eval(), head.float().eval()


def wrapper(front, head, compact):
    import torch.nn as nn
    import torch.nn.functional as F
    class Wrap(nn.Module):
        def __init__(self):
            super().__init__()
            self.front, self.head = front, head

        def forward(self, roi, lips):
            x = roi / 255.
            x = x - x.mean(dim=(1, 2, 3), keepdim=True)
            x = x / x.square().mean(dim=(1, 2, 3), keepdim=True).sqrt().clamp(min=.01)
            x = x.unsqueeze(1)
            if compact:
                x = F.avg_pool3d(x, (1, 2, 2), (1, 2, 2))
            B, _, T, H, W = x.shape
            pixel = self.front.pixel
            v = pixel.c3(x).transpose(1, 2).reshape(B * T, 16 if compact else 24, H // 2, W // 2)
            v = F.max_pool2d(F.relu(pixel.b3(v)), 3, 2, 1)
            for stage in pixel.stages:
                v = stage(v)
            features = pixel.fc(v.mean(dim=(2, 3))).reshape(B, T, 256)
            return self.head(features + self.front.lips(lips))
    return Wrap().eval()


def reference_logits(front, head, roi, lips):
    import torch
    lens = np.array([roi.shape[1]], np.int64)
    x = L._normalize(roi.numpy().astype(np.uint8), lens, None, None, 'cpu')
    keep = torch.ones(roi.shape[:2])
    return head(front((x, lips, keep), torch.from_numpy(lens)))


def export_one(path, out, compact):
    import torch
    import onnx
    import onnxruntime as ort
    assert not Path(out).exists(), 'Refuse overwrite of frozen export'
    front, head = load_pair(path, compact)
    model = wrapper(front, head, compact)
    roi, lips = map(torch.from_numpy, synthetic_inputs())
    with torch.no_grad():
        expected = reference_logits(front, head, roi, lips).numpy()
        actual_wrapper = model(roi, lips).numpy()
    wrap_diff = float(np.abs(expected - actual_wrapper).max())
    assert wrap_diff < 1e-3, ('wrapper', compact, wrap_diff)
    torch.onnx.export(model, (roi, lips), str(out), input_names=['roi', 'lips'], output_names=['logits'],
                      dynamic_axes={'roi': {0: 'B', 1: 'T'}, 'lips': {0: 'B', 1: 'T'}, 'logits': {0: 'B', 1: 'T'}},
                      opset_version=17, dynamo=False)
    graph = onnx.load(str(out))
    onnx.checker.check_model(graph)
    assert all(i.data_type not in (onnx.TensorProto.FLOAT16, onnx.TensorProto.BFLOAT16, onnx.TensorProto.DOUBLE)
               for i in graph.graph.initializer)
    assert any(o.version == 17 and o.domain in ('', 'ai.onnx') for o in graph.opset_import)
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    session = ort.InferenceSession(str(out), sess_options=options, providers=['CPUExecutionProvider'])
    result = session.run(['logits'], {'roi': roi.numpy(), 'lips': lips.numpy()})[0]
    onnx_diff = float(np.abs(actual_wrapper - result).max())
    assert result.shape == (1, 75, 53) and np.isfinite(result).all() and onnx_diff < 1e-3, ('onnx', compact, onnx_diff)
    return {'bytes': Path(out).stat().st_size, 'sha256': L.sha(out), 'checkpoint_sha256': L.sha(path),
            'wrap_diff': wrap_diff, 'onnx_diff': onnx_diff, 'weights': 'FP32', 'opset': 17,
            'input_sha256': INPUT_SHA, 'input_shapes': {'roi': [1, 75, 80, 80], 'lips': [1, 75, 80]}}


def finish(a):
    import torch
    torch.set_num_threads(2)
    references(a)
    out = Path(a.out)
    accuracy = read(out / 'accuracy-selection.json') if (out / 'accuracy-selection.json').exists() else compare(a)
    assert accuracy['architecture'] == ARCH and accuracy['baseline_model_sha256'] == B33_SHA
    assert accuracy['candidate_model_sha256'] == L.sha(Path(a.candidate) / 'model.pt')
    if (out / 'export.json').exists():
        raise RuntimeError('Refuse duplicate registered exports')
    exports = {'full': export_one(a.full_reference, out / 'full.onnx', False),
               'compact': export_one(Path(a.candidate) / 'model.pt', out / 'compact.onnx', True)}
    exports.update(size_ratio=exports['compact']['bytes'] / exports['full']['bytes'],
                   status='pending_wasm_and_full_fusion_seed1_confirmation')
    exports['size_ok'] = exports['size_ratio'] <= .4
    L.dump(out / 'export.json', exports)
    print('COMPACT_FUSION_EXPORTED', exports['size_ratio'], exports['size_ok'], flush=True)


def finalize(a):
    import math
    out = Path(a.out)
    assert not (out / 'selection.json').exists(), 'Refuse overwrite of final development selection'
    accuracy, export, wasm = (read(out / n) for n in ('accuracy-selection.json', 'export.json', 'wasm.json'))
    confirmation = read(a.fusion_seed1_selection)
    assert confirmation['seed'] == 1 and confirmation['architecture'] == FULL_ARCH
    assert type(confirmation['keep_path']) is bool
    assert accuracy['architecture'] == ARCH and accuracy['seed'] == 0 and accuracy['baseline_model_sha256'] == B33_SHA
    assert export['full']['checkpoint_sha256'] == FULL_SHA
    assert export['compact']['checkpoint_sha256'] == accuracy['candidate_model_sha256']
    assert wasm['input_sha256'] == INPUT_SHA and wasm['host'].upper() == 'CNSAI2025'
    assert wasm['ort_version'] == '1.19.2' and wasm['num_threads'] == 1 and wasm['node'].startswith('v24.')
    assert wasm['execution_provider'] == 'onnxruntime-web WASM CPU'
    assert wasm['protocol'] == WASM_PROTOCOL
    assert all(math.isfinite(accuracy[k]) for k in ('accuracy_delta', 'cer_delta'))
    medians = {}
    for key in ('full', 'compact'):
        path = out / (key + '.onnx')
        assert L.sha(path) == export[key]['sha256'] == wasm['model_sha256'][key]
        assert path.stat().st_size == export[key]['bytes']
        assert export[key]['weights'] == 'FP32' and export[key]['opset'] == 17
        assert 0 <= export[key]['wrap_diff'] < 1e-3 and 0 <= export[key]['onnx_diff'] < 1e-3
        times = wasm['samples_ms'][key]
        assert len(times) == 20 and all(math.isfinite(x) and x > 0 for x in times)
        medians[key] = statistics.median(times)
        assert math.isclose(medians[key], wasm[key + '_median_ms'], rel_tol=1e-12, abs_tol=1e-9)
    size_ratio = export['compact']['bytes'] / export['full']['bytes']
    latency_ratio = medians['compact'] / medians['full']
    assert math.isclose(size_ratio, export['size_ratio'], rel_tol=1e-12, abs_tol=1e-12)
    assert math.isclose(latency_ratio, wasm['latency_ratio'], rel_tol=1e-12, abs_tol=1e-12)
    gates = {'accuracy': accuracy['accuracy_delta'] >= .02, 'cer': accuracy['cer_delta'] <= .02,
             'size': size_ratio <= .4, 'latency': latency_ratio <= .5}
    assert accuracy['keep_path'] == (gates['accuracy'] and gates['cer'])
    assert export['size_ok'] == gates['size'] and wasm['latency_ok'] == gates['latency']
    confirmed = confirmation['keep_path']
    result = {'status': 'validation_selection_only_no_adjudication', 'architecture': ARCH, 'seed': 0,
              'gates': gates, 'numerical_all_four_pass': all(gates.values()),
              'combination_confirmation': 'confirmed_seed1' if confirmed else 'combination_unconfirmed',
              'overall_keep_path': all(gates.values()) and confirmed,
              'accuracy_delta': accuracy['accuracy_delta'], 'cer_delta': accuracy['cer_delta'],
              'size_ratio': size_ratio, 'latency_ratio': latency_ratio, **COUNTS,
              'full_reference_sha256': FULL_SHA, 'baseline_sha256': B33_SHA,
              'candidate_sha256': accuracy['candidate_model_sha256'],
              'source_sha256': {n: L.sha(out / n) for n in ('accuracy-selection.json', 'export.json', 'wasm.json')},
              'full_fusion_seed1_selection_sha256': L.sha(a.fusion_seed1_selection),
              'interpretation': 'Development validation n12; no independent judgement; clean evaluation pending; no app or Android measurement.'}
    L.dump(out / 'selection.json', result)
    print('COMPACT_FUSION_FINAL', json.dumps(result), flush=True)


def smoke(a):
    import torch
    configure(True)
    L.smoke(a)
    roi, lips = map(torch.from_numpy, synthetic_inputs())
    for compact in (False, True):
        configure(compact)
        torch.manual_seed(0)
        front, head, _ = L.models()
        front.eval(); head.eval()
        count = sum(p.numel() for m in (front, head) for p in m.parameters())
        assert count == COUNTS['compact_parameters' if compact else 'full_parameters']
        with torch.no_grad():
            ref = reference_logits(front, head, roi, lips)
            result = wrapper(front, head, compact)(roi, lips)
        diff = float((result - ref).abs().max())
        assert result.shape == (1, 75, 53) and torch.isfinite(result).all() and diff < 1e-3
        print('COMPACT_FUSION_SYNTHETIC_WRAPPER', compact, 'params', count, 'max_diff', diff, flush=True)
    print('COMPACT_FUSION_SMOKE_OK', json.dumps(COUNTS), 'input_sha256', json.dumps(INPUT_SHA), flush=True)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='cmd', required=True)
    for cmd in ('smoke', 'train', 'compare', 'finish', 'finalize'):
        t = sub.add_parser(cmd)
        if cmd != 'finalize':
            t.add_argument('--run', required=True)
        if cmd in ('smoke', 'train', 'compare', 'finish'):
            t.add_argument('--lips', required=cmd in ('smoke', 'train'))
        if cmd != 'smoke':
            t.add_argument('--out', required=True)
        if cmd in ('train', 'compare', 'finish'):
            t.add_argument('--full-reference', '--reference', dest='full_reference', required=True)
            t.add_argument('--baseline', required=True)
        if cmd in ('compare', 'finish'):
            t.add_argument('--candidate', required=True)
        if cmd == 'finalize':
            t.add_argument('--fusion-seed1-selection', required=True)
    a = p.parse_args()
    return {'smoke': smoke, 'train': train, 'compare': compare, 'finish': finish, 'finalize': finalize}[a.cmd](a)


if __name__ == '__main__':
    raise SystemExit(main())
