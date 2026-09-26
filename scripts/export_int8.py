#!/usr/bin/env python3
"""D-GOP 정렬기·채점기(fp32 CTC 체크포인트)를 int8 파일로 미리 변환하고, 실행 중 변환과 비트 단위로 같은지 확인한다.

배포 이미지에는 결과 폴더(model.int8.safetensors + config·전처리 파일)만 싣는다. 호스팅 기계는 루트 파일시스템 읽기가
초당 약 17MB라(9/26 liplab-dev 실측), fp32(모델당 1.26GB)를 읽어 변환하던 적재가 모델당 76초 걸렸다(DEPLOY.md 9항).

  backend/.venv/bin/python scripts/export_int8.py <fp32 폴더> <출력 폴더> [--wav 음성.wav]

확인: (1) 모든 텐서가 quantize_linears() 결과와 같다(torch.equal), (2) 무작위 3초·실제 음성(--wav)의 로짓이 같다.
하나라도 다르면 종료 코드 1. torch·transformers는 배포 이미지와 같은 판(2.14.0·5.17.0)을 쓴다.
"""
import argparse
import gc
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

import torch  # noqa: E402

import quant_int8 as Q  # noqa: E402


def _wave(path):
    import wave

    import numpy as np
    with wave.open(path, "rb") as w:
        if w.getframerate() != 16000 or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise SystemExit(f"{path}: 16kHz 모노 16비트 wav만 받는다")
        y = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    y = (y - y.mean()) / (y.std() + 1e-7)
    return torch.from_numpy(y)[None]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--wav", help="로짓 비교에 쓸 실제 음성(16kHz 모노 wav)")
    a = ap.parse_args()
    from transformers import AutoModelForCTC

    t0 = time.time()
    info = Q.export_ctc(a.src, a.out)
    t_export = time.time() - t0
    gc.collect()

    ref = AutoModelForCTC.from_pretrained(a.src).eval()
    Q.quantize_linears(ref)
    t0 = time.time()
    got = Q.load_ctc(a.out)
    t_load = time.time() - t0
    sa, sb = ref.state_dict(), got.state_dict()
    bad = [k for k in sa if k not in sb or sa[k].dtype != sb[k].dtype or not torch.equal(sa[k], sb[k])]
    bad += [k for k in sb if k not in sa]
    inputs = [("무작위 3초", torch.randn(1, 48000, generator=torch.Generator().manual_seed(0)))]
    if a.wav:
        inputs.append((os.path.basename(a.wav), _wave(a.wav)))
    same = []
    with torch.no_grad():
        for name, x in inputs:
            la, lb = ref(x).logits, got(x).logits
            same.append((name, bool(torch.equal(la, lb)), float((la - lb).abs().max())))

    src_bytes = os.path.getsize(os.path.join(a.src, "model.safetensors"))
    print(f"{a.out}")
    print(f"  선형층 {info['replaced']}개 int8, 파일 {info['file_bytes'] / 1e6:.0f}MB (fp32 {src_bytes / 1e6:.0f}MB, "
          f"{info['file_bytes'] / src_bytes:.1%}), 변환 {t_export:.1f}초, 파일에서 적재 {t_load:.1f}초")
    print(f"  텐서 {len(sa)}개 중 다른 것 {len(bad)}개" + (f": {bad[:5]}" if bad else ""))
    for name, eq, d in same:
        print(f"  로짓 [{name}] 같음={eq} 최대차={d:g}")
    ok = not bad and all(eq for _, eq, _ in same)
    print("  결과:", "통과" if ok else "실패")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
