#!/usr/bin/env python3
"""촬영한 P3 영상 점검. 촬영 목록(docs/pilot/shot-list.csv)의 파일이 영상 폴더에 다 있는지, 형식이 맞는지 본다.

확인하는 것(ffprobe 필요): 파일이 있는지, 해상도 세로 1080 이상, 초당 프레임 59 이상, 길이 1~12초, 소리 '필수' 클립에 음성 트랙(48kHz)이
있는지. 잡음 파일(noise/babble.wav)도 본다. 문제만 출력하고, 끝에 묶음별 준비 수를 낸다.

사용:
  python3 scripts/check_pilot_media.py <영상 폴더>      # 예: backend/data/pilot/media
"""
import csv
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(ROOT, "docs", "pilot", "shot-list.csv")


def probe(path: str) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path],
                         capture_output=True, text=True)
    if out.returncode != 0:
        return {}
    return json.loads(out.stdout or "{}")


def fps_of(stream: dict) -> float:
    num, _, den = (stream.get("avg_frame_rate") or "0/1").partition("/")
    try:
        return float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        return 0.0


def check(path: str, need_sound: bool) -> list:
    info = probe(path)
    if not info:
        return ["읽을 수 없음"]
    errs = []
    v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
    if not v:
        errs.append("영상 트랙 없음")
    else:
        if int(v.get("height") or 0) < 1080:
            errs.append(f"세로 {v.get('height')}")
        if fps_of(v) < 59:
            errs.append(f"{fps_of(v):.1f}fps")
    dur = float((info.get("format") or {}).get("duration") or 0)
    if not (1.0 <= dur <= 12.0):
        errs.append(f"길이 {dur:.1f}초")
    if need_sound:
        if not a:
            errs.append("음성 트랙 없음")
        elif int(a.get("sample_rate") or 0) != 48000:
            errs.append(f"음성 {a.get('sample_rate')}Hz")
    return errs


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    media = sys.argv[1]
    with open(CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    ready, total, problems = {}, {}, 0
    for r in rows:
        key = r["set"]
        total[key] = total.get(key, 0) + 1
        p = os.path.join(media, r["file"])
        if not os.path.exists(p):
            print(f"없음: {r['file']} ({r['talker']} {r['id']} {r['text']})")
            problems += 1
            continue
        errs = check(p, r["sound"] == "필수")
        if errs:
            print(f"형식: {r['file']} → {', '.join(errs)}")
            problems += 1
        else:
            ready[key] = ready.get(key, 0) + 1
    noise = os.path.join(media, "noise", "babble.wav")
    if not os.path.exists(noise):
        print("없음: noise/babble.wav")
        problems += 1
    for k in total:
        print(f"{k}: 준비 {ready.get(k, 0)} / {total[k]}")
    print(f"문제 {problems}개")


if __name__ == "__main__":
    main()
