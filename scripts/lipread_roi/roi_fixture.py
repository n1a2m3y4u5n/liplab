#!/usr/bin/env python3
"""roi_fixture.py: frontend/src/lib/lipRoi.test.mjs의 합성 기준값(데스크탑, cv2 4.9 + liplab-lab/tools/lip_roi_extract.py).

작은 합성 흑백 영상(난수 + 줄무늬)과 일부러 공백·흔들림을 넣은 기하 시퀀스로 plan_crops, crop_frame(cv2, k=1과 k>1),
grid_index·grid_sources(30·25 fps), fill_gaps 결과를 남긴다. 실제 클립 대조는 roi_parity_dump.py·roi_parity.mjs(13.2절).
  python roi_fixture.py --out lipRoi.fixture.json
"""
import argparse
import base64
import json
import sys

import numpy as np

sys.path.insert(0, 'D:/liplab/lab/tools')
import lip_roi_extract as L   # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='lipRoi.fixture.json')
    a = ap.parse_args()
    import cv2
    rng = np.random.default_rng(7)
    W, H = 160, 120
    yy, xx = np.mgrid[0:H, 0:W]
    img = np.clip(rng.normal(128, 40, (H, W)) + 60 * np.sin(xx / 5.0) + 30 * np.cos(yy / 3.0), 0, 255).astype(np.uint8)
    n = 24
    geom = np.stack([80 + 3 * np.sin(np.arange(n) / 3) + rng.normal(0, 0.7, n), 70 + rng.normal(0, 0.7, n),
                     30 + rng.normal(0, 1.5, n), 0.15 + rng.normal(0, 0.05, n)], 1)
    geom[3, 3] += 2 * np.pi       # unwrap 확인
    det = np.ones(n, bool)
    det[[5, 6, 12, 13, 14, 15, 16, 22]] = False
    geom[~det] = np.nan
    cases = []
    for margin, side_note in ((2.0, 'k1'), (12.0, 'k>1')):
        centers, theta, side = L.plan_crops(geom, det, margin, L.SMOOTH, True)
        rois = [L.crop_frame(img, centers[i, 0], centers[i, 1], theta[i], side, 88, cv2) for i in (0, 9, 23)]
        cases.append({'margin': margin, 'note': side_note, 'k': max(1, int(np.ceil(side / 88 / 1.5))),
                      'cx': centers[:, 0].tolist(), 'cy': centers[:, 1].tolist(), 'theta': theta.tolist(), 'side': side,
                      'frames': [0, 9, 23], 'roi_b64': [base64.b64encode(r.tobytes()).decode() for r in rois]})
    grids = []
    for fps, nread in ((30.0, 20), (25.0, 26), (29.97, 31)):
        ks = L.grid_index(nread, fps)
        src, exact = L.grid_sources(ks)
        grids.append({'fps': fps, 't_ms': [int(round(i / fps * 1000)) for i in range(nread)], 'src': src.tolist(), 'exact': exact.tolist()})
    jit = [0, 30, 70, 101, 130, 175, 200, 236, 270, 299]   # 브라우저처럼 고르지 않은 시각
    ks = np.array([int(round(t * 30 / 1000.0)) for t in jit])
    src, exact = L.grid_sources(ks)
    grids.append({'fps': 30, 't_ms': jit, 'src': src.tolist(), 'exact': exact.tolist()})
    dd = np.array([1, 0, 1, 0, 0, 1, 0, 0, 0, 0, 1, 1, 0, 1], bool)
    out = {'W': W, 'H': H, 'img_b64': base64.b64encode(img.tobytes()).decode(),
           'geom': [None if not d else g.tolist() for g, d in zip(geom, det)], 'cases': cases, 'grids': grids,
           'fill_in': dd.tolist(), 'fill_out': L.fill_gaps(dd).tolist(), 'cv2': cv2.__version__}
    json.dump(out, open(a.out, 'w'), separators=(',', ':'))
    print('ROI_FIXTURE_OK', [c['k'] for c in cases])


if __name__ == '__main__':
    main()
