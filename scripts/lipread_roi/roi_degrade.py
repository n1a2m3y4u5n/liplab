#!/usr/bin/env python3
"""KMSAV ROI 후보 보조 지표: 평가 화자 ROI 열화 묶음을 만든다(docs/lipread-roi-kmsav-prereg-2026-11-02.md 6절).

venv-mp(cv2)로 실행한다. 정답·점수는 읽지 않는다. 입력 88×88 ROI에 클립마다 고정 시드(crc32 "조건|클립")로 건다.
  low     44×44로 줄였다가(INTER_AREA) 88×88로 키움(INTER_LINEAR)
  jpeg    프레임마다 JPEG 품질 20
  geo     클립마다 회전 ±6°, 평행이동 ±4화소(부호 무작위) + 프레임마다 위치 흔들림 σ 0.7화소, 가장자리 반복
  bright  밝기 ×0.6 × (1 + 0.15·sin(2πt/2초 + 위상)), 0~255로 자름
  all     low → jpeg → geo → bright 순서
출력: OUT/<조건>/<클립>.npz(roi만). 표식 ROI_DEGRADE_OK.
"""
import argparse
import os
import zlib

import cv2
import numpy as np

S = 88


def low(r, _rng):
    out = np.empty_like(r)
    for i, f in enumerate(r):
        out[i] = cv2.resize(cv2.resize(f, (44, 44), interpolation=cv2.INTER_AREA), (S, S), interpolation=cv2.INTER_LINEAR)
    return out


def jpeg(r, _rng):
    out = np.empty_like(r)
    for i, f in enumerate(r):
        ok, b = cv2.imencode('.jpg', f, [cv2.IMWRITE_JPEG_QUALITY, 20])
        if not ok:
            raise ValueError('JPEG 실패')
        out[i] = cv2.imdecode(b, cv2.IMREAD_GRAYSCALE)
    return out


def geo(r, rng):
    ang = 6.0 * rng.choice([-1.0, 1.0])
    dx, dy = 4.0 * rng.choice([-1.0, 1.0]), 4.0 * rng.choice([-1.0, 1.0])
    jit = rng.normal(0.0, 0.7, (len(r), 2))
    out = np.empty_like(r)
    for i, f in enumerate(r):
        M = cv2.getRotationMatrix2D(((S - 1) / 2.0, (S - 1) / 2.0), ang, 1.0)
        M[0, 2] += dx + jit[i, 0]
        M[1, 2] += dy + jit[i, 1]
        out[i] = cv2.warpAffine(f, M, (S, S), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return out


def bright(r, rng):
    ph = rng.uniform(0.0, 2.0 * np.pi)
    t = np.arange(len(r)) / 30.0
    g = 0.6 * (1.0 + 0.15 * np.sin(2.0 * np.pi * t / 2.0 + ph))
    return np.clip(r.astype(np.float32) * g[:, None, None], 0, 255).round().astype(np.uint8)


def all_(r, rng):
    return bright(geo(jpeg(low(r, rng), rng), rng), rng)


CONDS = {'low': low, 'jpeg': jpeg, 'geo': geo, 'bright': bright, 'all': all_}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--manifest', required=True)
    ap.add_argument('--speakers', required=True, help='평가 화자 목록 파일')
    ap.add_argument('--npz', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    spk = {x.strip() for x in open(a.speakers, encoding='utf-8') if x.strip() and not x.startswith('#')}
    clips = []
    for line in open(a.manifest, encoding='utf-8'):
        p = line.rstrip('\n').split('\t')
        if len(p) >= 2 and p[1] in spk:
            clips.append(p[0][:-4] if p[0].endswith('.mp4') else p[0])
    n = 0
    for c in clips:
        src = os.path.join(a.npz, c + '.npz')
        if not os.path.exists(src):
            continue
        with np.load(src, allow_pickle=False) as z:
            roi = z['roi']
        for name, fn in CONDS.items():
            d = os.path.join(a.out, name)
            os.makedirs(d, exist_ok=True)
            rng = np.random.default_rng(zlib.crc32(f'{name}|{c}'.encode('utf-8')))
            res = fn(roi, rng)
            if res.shape != roi.shape or res.dtype != np.uint8:
                raise ValueError(f'모양 다름: {c} {name}')
            np.savez(os.path.join(d, c + '.npz'), roi=res)
        n += 1
    print(f'ROI_DEGRADE_OK clips={n}/{len(clips)} conds={sorted(CONDS)} speakers={len(spk)}', flush=True)


if __name__ == '__main__':
    main()
