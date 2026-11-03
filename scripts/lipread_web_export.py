#!/usr/bin/env python3
"""
lipread_web_export.py: 등록된 후보(C65) 학생 PT → 브라우저용 int8 ONNX(입력 roi_z)를 직접 내보낸다(11/03 검토 M1·M2·M18, 묶음 D).

왜 새 스크립트인가: 후보 ONNX(devcands 내보내기)는 입력이 `roi`(0~255 원화소)이고 정규화가 그래프 안에 있다. 앱(lipreadRoiModel.js)은
정규화된 `roi_z`를 요구한다(그래프 안 ReduceMean이 엔진마다 다른 오차를 내서, 13.2절). 기존 roi_web_export.py는 R2 그래프의 노드 이름에
묶여 있어 후보 그래프에서는 단언에 걸린다. 그래서 PyTorch Wrap에서 정규화만 뺀 그래프를 처음부터 내보낸다(가중치는 PT 그대로).

순서
  1) 등록 PT·등록 FP32 ONNX의 sha256이 등록부 값과 같은지 확인한다(다르면 멈춘다).
  2) 정규화를 뺀 Wrap(roi_z)을 FP32 opset17로 내보낸다.
  3) FP32 웹 그래프(roi_z=float64 정규화)가 등록 ONNX(roi 원화소, 그래프 안 정규화)와 같은 logits를 내는지 합성 입력으로 확인한다.
  4) roi_train.weight_int8로 가중치만 int8로 바꾼다. FP32 대비 logits 차이·그리디 일치율을 잰다(합성 입력, 판정 아님).
  5) 같은 이름 .meta.json(어휘·채점 설정·sha256·등록 ID·입력 목록)과 매니페스트 항목(.manifest-entry.json)을 쓴다.

산출물은 --out(기본 out\\impl-2026-11-03\\C65-web)에만 둔다. frontend/public/이나 배포 설정에 복사하지 않는다(판정 전, 기본 끔).
CPU만 쓴다(GPU 없음). 학습·평가 자료를 쓰지 않는다. 필요한 모듈: torch, onnx, onnxruntime, numpy.

  python scripts/lipread_web_export.py [--pt model.pt] [--out 폴더]
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

os.environ.setdefault('CUDA_VISIBLE_DEVICES', '')
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'lipread_roi'))
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402

DEV = Path(r'D:\work\hq\projects\liplab\out\devcands-2026-11')
CANDIDATES = {
    'C65': {
        'pt': DEV / 'C65' / 'seed0' / 'model.pt',
        'pt_sha256': '4355af944ba41736a12ff0c9e70dff395745f6d18ef2b6c3578688aff547a9ca',        # C65-registry-entry.json model_sha256
        'onnx': DEV / 'C65' / 'seed0' / 'student.onnx',
        'onnx_sha256': '1b521cec40c2fb363bdd1468422a0a0a907e891ad03e1b3bde25e596a0c969ce',      # C65-registry-entry.json input_contract
        'architecture': 'capacity_roi_65_v1',     # nextreg_distill65.py가 만든 65% 학생(stem 16, channels 24/48/96/192, hidden 332)
    },
}
DEFAULT_OUT = Path(r'D:\work\hq\projects\liplab\out\impl-2026-11-03\C65-web')


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def normalize64(roi):
    """roi (T,80,80) 0~255 → float32 z. roi_web_export.normalize64와 같은 식(float64, 표준편차 clamp 1e-2)."""
    x = np.asarray(roi, np.float64) / 255.0
    m = x.mean()
    sd = max(float(np.sqrt(((x - m) ** 2).mean())), 1e-2)
    return ((x - m) / sd).astype(np.float32)


def build_wrap(front, head):
    import torch.nn as nn
    import torch.nn.functional as F

    class WrapZ(nn.Module):
        """nextreg_roi_distill_capacity.export_capacity의 Wrap에서 정규화(/255, 평균 빼기, RMS 나누기)만 뺀 것. 입력은 이미 정규화된 roi_z."""

        def __init__(self):
            super().__init__()
            self.front, self.head = front, head

        def forward(self, roi_z):
            x = roi_z.unsqueeze(1)
            x = F.avg_pool3d(x, (1, 2, 2), (1, 2, 2))
            B, _, T, H, W = x.shape
            v = self.front.c3(x).transpose(1, 2).reshape(B * T, 16, H // 2, W // 2)
            v = F.max_pool2d(F.relu(self.front.b3(v)), 3, 2, 1)
            for st in self.front.stages:
                v = st(v)
            z = self.front.fc(v.mean(dim=(2, 3))).reshape(B, T, 256)
            return self.head(z)

    return WrapZ().eval()


def greedy(logits):
    """프레임별 argmax에서 반복·blank를 걷어 낸 id열(그리디 CTC)."""
    best = logits.argmax(-1)
    out, prev = [], -1
    for b in best:
        if b != prev and b != 0:
            out.append(int(b))
        prev = b
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--candidate', default='C65', choices=sorted(CANDIDATES))
    ap.add_argument('--pt', default=None)
    ap.add_argument('--out', default=str(DEFAULT_OUT))
    ap.add_argument('--tol-fp32', type=float, default=1e-2, help='FP32 웹 그래프 ↔ 등록 ONNX logits 최대 차이 허용')
    a = ap.parse_args(argv)
    c = CANDIDATES[a.candidate]
    pt = Path(a.pt) if a.pt else c['pt']
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    # 1) 등록 sha256 확인
    got_pt, got_onnx = sha(pt), sha(c['onnx'])
    if got_pt != c['pt_sha256']:
        print(f'EXPORT_ABORT PT sha256이 등록과 다르다: {got_pt[:12]} != {c["pt_sha256"][:12]}')
        return 1
    if got_onnx != c['onnx_sha256']:
        print(f'EXPORT_ABORT 등록 ONNX sha256이 다르다: {got_onnx[:12]} != {c["onnx_sha256"][:12]}')
        return 1

    import onnxruntime as ort
    import torch
    import roi_train as R
    import nextreg_distill65  # noqa: F401  (65% 프리셋을 nextreg_roi_distill_capacity에 등록한다)
    import nextreg_roi_distill_capacity as C
    torch.set_num_threads(2)
    torch.set_grad_enabled(False)

    front, head, ck = C.load_capacity(str(pt), 'cpu', '65')
    assert ck['architecture'] == c['architecture']
    n_vocab = len(ck['vocab'])
    model = build_wrap(front, head)

    # 2) FP32 웹 그래프
    fp32 = out / f'{a.candidate}.web.fp32.onnx'
    rng = np.random.default_rng(20261103)
    example = normalize64(rng.integers(0, 256, (75, 80, 80)))[None]
    torch.onnx.export(model, torch.from_numpy(example), str(fp32), input_names=['roi_z'], output_names=['logits'],
                      dynamic_axes={'roi_z': {0: 'B', 1: 'T'}, 'logits': {0: 'B', 1: 'T'}}, opset_version=17, dynamo=False)

    # 3) 등록 ONNX(roi 원화소) ↔ FP32 웹 그래프(roi_z)
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 2
    reg = ort.InferenceSession(str(c['onnx']), sess_options=opts, providers=['CPUExecutionProvider'])
    web32 = ort.InferenceSession(str(fp32), sess_options=opts, providers=['CPUExecutionProvider'])
    assert [i.name for i in web32.get_inputs()] == ['roi_z']
    diffs32 = []
    seqs = [rng.integers(0, 256, (T, 80, 80)).astype(np.float32) for T in (75, 75, 90)]
    for roi in seqs:
        ref = reg.run(['logits'], {'roi': roi[None]})[0]
        now = web32.run(['logits'], {'roi_z': normalize64(roi)[None]})[0]
        diffs32.append(float(np.abs(ref - now).max()))
    if max(diffs32) > a.tol_fp32:
        print(f'EXPORT_FAIL FP32 웹 그래프가 등록 ONNX와 다르다: max {max(diffs32):.5f} > {a.tol_fp32}')
        return 1

    # 4) 가중치 int8
    int8 = out / f'{a.candidate}.web.int8.onnx'
    R.weight_int8(str(fp32), str(int8))
    q = ort.InferenceSession(str(int8), sess_options=opts, providers=['CPUExecutionProvider'])
    assert [i.name for i in q.get_inputs()] == ['roi_z']
    diffs8, same = [], []
    for roi in seqs + [rng.integers(0, 256, (75, 80, 80)).astype(np.float32) for _ in range(5)]:
        z = normalize64(roi)[None]
        a32 = web32.run(['logits'], {'roi_z': z})[0][0]
        a8 = q.run(['logits'], {'roi_z': z})[0][0]
        diffs8.append(float(np.abs(a32 - a8).max()))
        same.append(float((a32.argmax(-1) == a8.argmax(-1)).mean()))

    # 5) meta·매니페스트 항목
    import roi_web_export as W
    meta = {'vocab': W.VOCAB, 'n_vocab': n_vocab, 'input': 'roi_z', 'inputs': ['roi_z'], 'size': 88, 'crop': 80, 'fps': 30, 'min_len': 75,
            'alpha': 1.0, 'dup': 1, 'score': 'ctc_ll',
            'normalize': 'x/255, sequence mean/std (population), std clamp 1e-2, float64',
            'registered_id': a.candidate, 'source_pt_sha256': got_pt, 'source_onnx_sha256': got_onnx,
            'sha256': sha(int8), 'bytes': int8.stat().st_size, 'weights': 'int8 per-output-channel (roi_train.weight_int8)',
            'status': 'development candidate, not judged; default off'}
    assert n_vocab == len(W.VOCAB), (n_vocab, len(W.VOCAB))
    meta_path = out / f'{a.candidate}.web.meta.json'
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding='utf-8')
    entry = {a.candidate: {'model': f'/models/lipread/{a.candidate}/{int8.name}', 'meta': f'/models/lipread/{a.candidate}/{meta_path.name}',
                           'inputs': ['roi_z'], 'sha256': meta['sha256']}}
    (out / f'{a.candidate}.manifest-entry.json').write_text(json.dumps({'models': entry}, indent=1), encoding='utf-8')
    report = {'candidate': a.candidate, 'fp32_bytes': fp32.stat().st_size, 'int8_bytes': int8.stat().st_size,
              'registered_onnx_vs_web_fp32_max_logit_diff': diffs32,
              'fp32_vs_int8_max_logit_diff': {'max': max(diffs8), 'mean': float(np.mean(diffs8))},
              'fp32_vs_int8_greedy_frame_agreement': {'min': min(same), 'mean': float(np.mean(same))},
              'note': 'synthetic random inputs only: parity check, not a judgment; int8 equivalence on real data is a human decision (M10)',
              'pt_sha256': got_pt, 'int8_sha256': meta['sha256']}
    (out / 'parity.json').write_text(json.dumps(report, indent=1), encoding='utf-8')
    print('LIPREAD_WEB_EXPORT_OK ' + json.dumps({k: report[k] for k in ('fp32_bytes', 'int8_bytes', 'int8_sha256')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
