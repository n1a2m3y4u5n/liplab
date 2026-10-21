#!/usr/bin/env python3
"""
roi_web_export.py: 판정 int8 ONNX(roi_train.py export) → 브라우저용 ONNX(docs/lipread-roi-2026-10.md 13.1절).

바꾸는 것은 앞단 정규화뿐이다. 판정 그래프는 roi(0~255) → /255 → 시퀀스 전체 평균·표준편차(clamp 1e-2) → z를 그래프 안에서 계산하는데,
T×80×80(75프레임이면 48만, 259프레임이면 166만 화소)을 float32로 더하는 ReduceMean이 엔진마다 다른 오차를 낸다(onnxruntime-web WASM과
파이썬 CPU 사이 logits 최대 0.37, 13.2절). 그래서 그 노드(Div, ReduceMean, Sub, Mul, ReduceMean, Sqrt, Clip, Div)를 지우고 정규화된
roi_z [B,T,80,80]를 입력으로 받는다. 정규화는 브라우저(lipRoi.roiModelInput)와 파이썬 기준(아래 normalize64)이 float64로 한다. 가중치·
나머지 노드는 바이트 그대로다. roi의 Shape를 쓰던 노드는 roi_z의 Shape를 쓴다(모양이 같다).

  python roi_web_export.py --src D:/liplab/roi/judge/onnx/roi_R2s0.int8.onnx --out D:/liplab/roi/web/kr_lipread_roi.web.onnx
출력: <out>, 같은 이름 .meta.json(어휘·채점 설정·sha256), 확인 표식 ROI_WEB_OK(임의 입력에서 판정 그래프를 float64 정규화로 돌린 값과 비교).
"""
import argparse
import hashlib
import json
import os

import numpy as np

NORM_OPS = ('Div', 'ReduceMean', 'Sub', 'Mul', 'Sqrt', 'Clip')
CHO = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ'
JUNG = 'ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ'
JONG = 'ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ'
VOCAB = ['<blank>', ' '] + sorted(set(CHO + JUNG + JONG))     # train_lipread.VOCAB와 같은 규칙


def normalize64(roi80):
    """roi (T,80,80) 0~255 → float32 z. 학습 normalize와 같은 식(/255, 시퀀스 전체 평균·모분산, 표준편차 clamp 1e-2)을 float64로."""
    x = np.asarray(roi80, np.float64) / 255.0
    m = x.mean()
    sd = max(float(np.sqrt(((x - m) ** 2).mean())), 1e-2)
    return ((x - m) / sd).astype(np.float32)


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def strip(src, dst):
    import onnx
    from onnx import helper, TensorProto
    m = onnx.load(src)
    g = m.graph
    prod = {o: n for n in g.node for o in n.output}
    target = '/Div_1_output_0'
    chain, st = [], [target]
    while st:
        n = prod.get(st.pop())
        if n is None or n in chain:
            continue
        chain.append(n)
        st.extend(n.input)
    rm = [n for n in chain if n.op_type in NORM_OPS]
    assert sorted(n.op_type for n in rm) == sorted(['Div', 'ReduceMean', 'Sub', 'Mul', 'ReduceMean', 'Sqrt', 'Clip', 'Div']), \
        [n.op_type for n in rm]
    for n in rm:
        g.node.remove(n)
    for n in g.node:                                  # 남은 노드에서 roi → roi_z, 정규화 출력 → roi_z
        for k, x in enumerate(n.input):
            if x in ('roi', target):
                n.input[k] = 'roi_z'
    old = [i for i in g.input if i.name == 'roi']
    for i in old:
        g.input.remove(i)
    g.input.insert(0, helper.make_tensor_value_info('roi_z', TensorProto.FLOAT, ['B', 'T', 80, 80]))
    while True:                                       # 지운 노드만 쓰던 Constant 노드(clamp 하한 등)
        used = {x for n in g.node for x in n.input} | {o.name for o in g.output}
        dead = [n for n in g.node if n.op_type == 'Constant' and not (set(n.output) & used)]
        if not dead:
            break
        for n in dead:
            g.node.remove(n)
    for init in list(g.initializer):                  # 지운 노드만 쓰던 상수(clamp 하한 등)
        if init.name not in used:
            g.initializer.remove(init)
    onnx.checker.check_model(m)
    onnx.save(m, dst)
    return [n.op_type for n in rm]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', default='D:/liplab/roi/judge/onnx/roi_R2s0.int8.onnx')
    ap.add_argument('--out', default='D:/liplab/roi/web/kr_lipread_roi.web.onnx')
    a = ap.parse_args()
    import onnxruntime as ort
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    removed = strip(a.src, a.out)
    full = ort.InferenceSession(a.src, providers=['CPUExecutionProvider'])
    web = ort.InferenceSession(a.out, providers=['CPUExecutionProvider'])
    assert [i.name for i in web.get_inputs()] == ['roi_z']
    rng = np.random.default_rng(0)
    # 화소 수가 적은 T=16에서는 그래프 안 float32 정규화 오차가 작으므로, 판정 그래프(원 입력)와 새 그래프(float64 z)를 비교해
    # 나머지 노드가 같은지만 본다(큰 T의 오차는 13.2절 대조 검사에서 따로 잰다).
    roi = rng.integers(0, 256, (16, 80, 80)).astype(np.float32)
    z = normalize64(roi)
    o_full = full.run(['logits'], {'roi': roi[None]})[0]
    o_web = web.run(['logits'], {'roi_z': z[None]})[0]
    d = float(np.abs(o_full - o_web).max())
    meta = {'vocab': VOCAB, 'n_vocab': len(VOCAB), 'input': 'roi_z', 'size': 88, 'crop': 80, 'fps': 30, 'min_len': 75,
            'alpha': 1.0, 'dup': 1, 'score': 'ctc_ll', 'normalize': 'x/255, sequence mean/std (population), std clamp 1e-2, float64',
            'source': os.path.basename(a.src), 'source_sha256': sha(a.src), 'sha256': sha(a.out),
            'bytes': os.path.getsize(a.out), 'removed_ops': removed, 'check_T16_maxdiff_vs_source': d,
            'model': 'R2 s0 (docs/lipread-roi-2026-10.md 10.1)'}
    json.dump(meta, open(os.path.splitext(a.out)[0] + '.meta.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    ok = d < 1e-3 and meta['n_vocab'] == o_web.shape[-1]
    print(('ROI_WEB_OK ' if ok else 'ROI_WEB_FAIL ') + json.dumps({k: meta[k] for k in ('bytes', 'sha256', 'check_T16_maxdiff_vs_source')}),
          flush=True)
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
