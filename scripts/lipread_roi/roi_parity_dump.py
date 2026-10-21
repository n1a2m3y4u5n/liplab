#!/usr/bin/env python3
"""
roi_parity_dump.py: 브라우저 ROI 경로 대조 검사용 기준값(데스크탑, docs/lipread-roi-2026-10.md 13.2절).

학습 화자 클립 몇 개를 학습 추출기(liplab-lab/tools/lip_roi_extract.py)와 같은 방식으로 다시 돌려, 브라우저 코드(frontend/src/lib/lipRoi.js,
lipreadRoiModel.js)에 넣을 입력과 파이썬 기준 출력을 남긴다. 평가·검증 화자는 쓰지 않는다(분할 파일로 확인하고 멈춘다).

클립마다 <out>/<clip>/
  gray.u8      디코드 프레임 흑백(cv2 BGR2GRAY) n×H×W
  rgba.u8      앞 4프레임 RGBA(흑백 변환식 대조용)
  gray_rgba.u8 그 4프레임의 cv2 흑백
  meta.json    W, H, fps, t_ms(디코드 프레임 시각), lms(프레임별 필요한 랜드마크 정규화 좌표 또는 null), py_geom
  roi_py.u8    extract_clip과 같은 계산의 30fps 격자 ROI T×88×88
  roi_npz.u8   학습에 쓴 D:/liplab/roi/npz의 ROI(같은지 확인용)
  logits_full.f32, logits_w75.f32  브라우저용 int8 ONNX + float64 정규화(파이썬 onnxruntime) 출력(전체 / 앞 75프레임)
  logits_graphnorm.f32  판정 그래프 그대로(정규화가 그래프 안 float32) 출력, 참고용
  scores.json  후보 단어 ctc_ll(α=1, roi_train.ctc_scores와 같은 torch 계산)
그 밖에 <out>/_float_path/: 2배 키운 프레임으로 과표본(k>1, float) 경로를 따로 시험한 입력·출력.

사용(데스크탑): python roi_parity_dump.py --out D:/liplab/roi/parity --n 6
"""
import argparse
import json
import os
import sys

import numpy as np

LAB_TOOLS = 'D:/liplab/lab/tools'
V1_TOOLS = 'D:/liplab/v1/dax'
HERE = os.path.dirname(os.path.abspath(__file__))
for p in (LAB_TOOLS, V1_TOOLS, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import lip_roi_extract as L                                    # noqa: E402

SPLIT = 'D:/liplab/v1/dax/v1/split.json'
NPZ = 'D:/liplab/roi/npz'
ONNX = 'D:/liplab/roi/judge/onnx/roi_R2s0.int8.onnx'
WEB_ONNX = 'D:/liplab/roi/web/kr_lipread_roi.web.onnx'      # roi_web_export.py 출력
CLIP_DIRS = ['D:/liplab/lab/data/v1_538r/clips', 'D:/liplab/lab/data/e538r/clips',
             'D:/liplab/lab/data/roi538/a/clips', 'D:/liplab/lab/data/roi538/b/clips']
NEED = sorted(set(L.LIP_OUTER) | {L.EYE_A, L.EYE_B, L.LIP_TOP_IN, L.LIP_BOT_IN})
CANDS = ['사과', '학교에', '친구', '바나나', '고맙습니다', '안녕하세요', '물', '버스']


def decode(video):
    import cv2
    cap = cv2.VideoCapture(video)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0) or 30.0
    frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(f)
    cap.release()
    return frames, fps


def landmarks(frames, fps):
    """extract_clip과 같은 VIDEO 모드 검출(클립마다 새 검출기)."""
    M = L._mods()
    cv2, mp = M['cv2'], M['mp']
    lm = L._landmarker(L.MODEL_PATH)
    out = []
    try:
        for i, f in enumerate(frames):
            t_ms = int(round(i / fps * 1000))
            res = lm.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(f, cv2.COLOR_BGR2RGB)), t_ms)
            out.append(res.face_landmarks[0] if res.face_landmarks else None)
    finally:
        lm.close()
    return out


def py_roi(grays, lms, W, H, fps, S=88):
    """extract_clip의 자르기·격자 계산(검출 결과를 받아서)."""
    import cv2
    n = len(grays)
    geom = np.full((n, 4), np.nan)
    det = np.zeros(n, bool)
    for i, l in enumerate(lms):
        if l is not None:
            cx, cy, w_, th, _ = L.landmark_geometry(l, W, H)
            geom[i] = (cx, cy, w_, th)
            det[i] = True
    plan = L.plan_crops(geom, det, L.MARGIN, L.SMOOTH, True)
    centers, theta, side = plan
    roi_dec = np.stack([L.crop_frame(g, centers[i, 0], centers[i, 1], theta[i], side, S, cv2) for i, g in enumerate(grays)])
    src, exact = L.grid_sources(L.grid_index(n, fps))
    det_g = det[src] & exact
    return roi_dec[src], L.fill_gaps(det_g), geom, float(side)


def run_onnx(sess, roi):
    """판정 그래프(정규화가 그래프 안, float32)."""
    c0 = (88 - 80) // 2
    x = roi[:, c0:c0 + 80, c0:c0 + 80].astype(np.float32)[None]
    return sess.run(['logits'], {'roi': x})[0][0]


def run_web(sess, roi):
    """브라우저용 그래프 + float64 정규화(파이썬 기준값)."""
    from roi_web_export import normalize64
    c0 = (88 - 80) // 2
    return sess.run(['logits'], {'roi_z': normalize64(roi[:, c0:c0 + 80, c0:c0 + 80])[None]})[0][0]


def scores(logits):
    import torch
    import torch.nn.functional as F
    from roi_train import ctc_scores
    from train_lipread import decompose
    lp = F.log_softmax(torch.from_numpy(logits).double(), -1)
    return {'cands': CANDS, 'labels': [decompose(w) for w in CANDS],
            'ctc_ll': [float(v) for v in ctc_scores(lp, [decompose(w) for w in CANDS])]}


def find_video(clip):
    for d in CLIP_DIRS:
        p = os.path.join(d, clip + '.mp4')
        if os.path.exists(p):
            return p
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='D:/liplab/roi/parity')
    ap.add_argument('--n', type=int, default=6)
    a = ap.parse_args()
    import cv2
    import onnxruntime as ort
    sp = json.load(open(SPLIT, encoding='utf-8'))
    train, banned = set(sp['train']), set(sp['eval']) | set(sp['val'])
    sess = ort.InferenceSession(ONNX, providers=['CPUExecutionProvider'])
    wsess = ort.InferenceSession(WEB_ONNX, providers=['CPUExecutionProvider'])
    picked, seen = [], set()
    for f in sorted(os.listdir(NPZ)):
        if not f.endswith('.npz'):
            continue
        clip = f[:-4]
        spk = clip.split('_')[0]
        if spk in banned or spk not in train or spk in seen:
            continue
        v = find_video(clip)
        if v:
            picked.append((clip, v))
            seen.add(spk)
        if len(picked) >= a.n:
            break
    assert all(c.split('_')[0] in train and c.split('_')[0] not in banned for c, _ in picked)
    summary = []
    for clip, video in picked:
        od = os.path.join(a.out, clip)
        os.makedirs(od, exist_ok=True)
        frames, fps = decode(video)
        H, W = frames[0].shape[:2]
        grays = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in frames]
        lms = landmarks(frames, fps)
        roi, valid, geom, side = py_roi(grays, lms, W, H, fps)
        np.stack(grays).tofile(os.path.join(od, 'gray.u8'))
        np.stack([cv2.cvtColor(f, cv2.COLOR_BGR2RGBA) for f in frames[:4]]).tofile(os.path.join(od, 'rgba.u8'))
        np.stack(grays[:4]).tofile(os.path.join(od, 'gray_rgba.u8'))
        roi.tofile(os.path.join(od, 'roi_py.u8'))
        zr = np.load(os.path.join(NPZ, clip + '.npz'))['roi']
        zr.tofile(os.path.join(od, 'roi_npz.u8'))
        lf = run_web(wsess, roi)
        lw = run_web(wsess, roi[:75])
        lf.astype(np.float32).tofile(os.path.join(od, 'logits_full.f32'))
        lw.astype(np.float32).tofile(os.path.join(od, 'logits_w75.f32'))
        run_onnx(sess, roi).astype(np.float32).tofile(os.path.join(od, 'logits_graphnorm.f32'))  # 판정 그래프(참고)
        meta = {'clip': clip, 'W': W, 'H': H, 'fps': fps, 'n': len(frames), 'T': int(len(roi)), 'side': side,
                't_ms': [int(round(i / fps * 1000)) for i in range(len(frames))],
                'lms': [None if l is None else {str(k): [float(l[k].x), float(l[k].y)] for k in NEED} for l in lms],
                'py_geom': [None if not np.isfinite(g).all() else [float(x) for x in g] for g in geom],
                'valid_frac': float(valid.mean()), 'V': int(lf.shape[-1])}
        json.dump(meta, open(os.path.join(od, 'meta.json'), 'w', encoding='utf-8'))
        sc = scores(lf)
        sc['w75'] = scores(lw)['ctc_ll']
        json.dump(sc, open(os.path.join(od, 'scores.json'), 'w', encoding='utf-8'), ensure_ascii=False)
        same = zr.shape == roi.shape and int(np.abs(zr.astype(int) - roi.astype(int)).max()) if zr.shape == roi.shape else None
        summary.append({'clip': clip, 'W': W, 'H': H, 'fps': fps, 'T': len(roi), 'side': round(side, 2),
                        'k': max(1, int(np.ceil(side / 88 / 1.5))), 'npz_vs_rerun_maxdiff': same})
        print('DUMP', json.dumps(summary[-1], ensure_ascii=False), flush=True)
    # 과표본(float) 경로: 첫 클립 앞 40프레임을 3배로 키워(INTER_CUBIC) 입 너비를 늘린다
    clip, video = picked[0]
    frames, fps = decode(video)
    frames = [cv2.resize(f, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC) for f in frames[:40]]
    H, W = frames[0].shape[:2]
    grays = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in frames]
    lms = landmarks(frames, fps)
    roi, valid, geom, side = py_roi(grays, lms, W, H, fps)
    od = os.path.join(a.out, '_float_path')
    os.makedirs(od, exist_ok=True)
    np.stack(grays).tofile(os.path.join(od, 'gray.u8'))
    roi.tofile(os.path.join(od, 'roi_py.u8'))
    json.dump({'clip': clip + '_x3', 'W': W, 'H': H, 'fps': fps, 'n': len(frames), 'T': int(len(roi)), 'side': side,
               't_ms': [int(round(i / fps * 1000)) for i in range(len(frames))],
               'lms': [None if l is None else {str(k): [float(l[k].x), float(l[k].y)] for k in NEED} for l in lms]},
              open(os.path.join(od, 'meta.json'), 'w', encoding='utf-8'))
    print('DUMP_FLOAT', json.dumps({'W': W, 'H': H, 'side': round(side, 2), 'k': max(1, int(np.ceil(side / 88 / 1.5)))}), flush=True)
    json.dump(summary, open(os.path.join(a.out, '_dump_summary.json'), 'w', encoding='utf-8'), indent=1)
    print('PARITY_DUMP_OK', len(summary), flush=True)


if __name__ == '__main__':
    main()
