"""고정 예제로 D-GOP 스레드 지연 비교. 실행 규칙은 gpu-dev-dgop-threads-prereg 문서."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time

import numpy as np
import soundfile as sf

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'backend'))
from dgop_stream import OnnxStudent

MODEL = Path('D:/work/hq/projects/liplab-lab/models/dgop_stream_HC_2026-10-17/student_w8.onnx')
YIELD = Path('D:/work/hq/shared/gpu-yield.txt')


def guard():
    if YIELD.exists():
        raise RuntimeError('GPU yield requested; experiment stopped')


def wave(i):
    guard()
    y, sr = sf.read(REPO / f'frontend/public/a2f-examples/clip_{i}.wav', dtype='float32')
    if sr != 16000:
        raise ValueError(f'Expected 16000Hz, got {sr}')
    if y.ndim == 2:
        y = y.mean(axis=1)
    if len(y) == 0:
        raise ValueError('empty wave')
    return np.tile(y, int(np.ceil(153600 / len(y))))[:153600]


def manifest():
    paths = [MODEL] + [REPO / f'frontend/public/a2f-examples/clip_{i}.wav' for i in range(1, 6)]
    return [{'path': str(p), 'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--stage', choices=['explore', 'confirm'], required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--selection')
    a = p.parse_args()
    guard()
    files = manifest()
    selected = None
    if a.stage == 'confirm':
        sel = json.loads(Path(a.selection).read_text(encoding='utf-8'))
        if files != sel['files']:
            raise RuntimeError('input files changed after selection')
        selected = sel['selected']
        if selected is None:
            raise RuntimeError('no candidate; confirmation prohibited')
    threads = [1, 2, 4] if a.stage == 'explore' else [2, selected]
    sessions, load = {}, {}
    for t in threads:
        guard()
        start = time.perf_counter()
        sessions[t] = OnnxStudent(str(MODEL), threads=t)
        load[str(t)] = time.perf_counter() - start
        for _ in range(2):
            sessions[t](wave(1))
    rows = []
    for i in ([1, 2, 3] if a.stage == 'explore' else [4, 5]):
        y = wave(i)
        reference = sessions[2](y)
        for repeat in range(3):
            order = threads[repeat % len(threads):] + threads[:repeat % len(threads)]
            for t in order:
                guard()
                start = time.perf_counter()
                outputs = sessions[t](y)
                elapsed = time.perf_counter() - start
                shape_equal = all(o.shape == r.shape for o, r in zip(outputs, reference))
                finite = all(np.isfinite(o).all() for o in outputs)
                diff = max(float(np.max(np.abs(o - r))) for o, r in zip(outputs, reference)) if shape_equal else float('inf')
                same = shape_equal and all(np.array_equal(o.argmax(-1), r.argmax(-1)) for o, r in zip(outputs, reference))
                rows.append(dict(clip=i, repeat=repeat, threads=t, seconds=elapsed, max_abs_diff=diff, argmax_equal=same, finite=bool(finite), shape_equal=shape_equal))
        print(f'{a.stage}: clip {i} complete', flush=True)
    summary = {}
    for t in threads:
        rr = [r for r in rows if r['threads'] == t]
        summary[str(t)] = dict(median=statistics.median(r['seconds'] for r in rr), maximum=max(r['seconds'] for r in rr), fidelity=all(r['max_abs_diff'] <= 1e-4 and r['argmax_equal'] and r['finite'] and r['shape_equal'] for r in rr), max_abs_diff=max(r['max_abs_diff'] for r in rr))
    result = dict(stage=a.stage, files=files, load_seconds=load, summary=summary, rows=rows)
    if a.stage == 'explore':
        eligible = [t for t in threads if summary[str(t)]['fidelity']]
        winner = min(eligible, key=lambda t: (summary[str(t)]['median'], t)) if eligible else None
        result['selected'] = winner if winner != 2 else None
    else:
        base, cand = summary['2'], summary[str(selected)]
        result['selected'] = selected
        result['median_speedup'] = 1 - cand['median'] / base['median']
        result['max_ratio'] = cand['maximum'] / base['maximum']
        result['pass'] = bool(base['fidelity'] and cand['fidelity'] and result['median_speedup'] >= .20 and result['max_ratio'] <= 1.10)
    Path(a.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k in ('summary', 'selected', 'pass', 'median_speedup', 'max_ratio')}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
