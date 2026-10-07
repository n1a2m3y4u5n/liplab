#!/usr/bin/env python3
"""긴 녹화를 촬영 목록 순서대로 잘라 파일 이름을 붙인다(P3 촬영 도우미).

촬영할 때 클립마다 녹화를 켜고 끄는 대신, 한 묶음(예: 화자 T1의 개방형 문장 폼 A 40개)을 프롬프터를 보며 이어서 찍는다.
문장 사이에는 입을 다문 채 2초 이상 쉰다. 이 스크립트는 음성의 조용한 구간(ffmpeg silencedetect)으로 말소리 구간을 찾고,
촬영 목록(docs/pilot/shot-list.csv)의 같은 화자·묶음·폼 순서대로 이름을 붙여 앞뒤 1초를 둔 클립으로 자른다.

다시 찍은 문장이 있으면 그 구간이 하나 더 생긴다. 먼저 --dry-run으로 구간 표(segments.csv)를 만들어 확인하고, 버릴 구간 번호를
--skip 3,7처럼 넘긴 뒤 자른다. 구간 수가 목록 수와 다르면 자르지 않고 멈춘다.

사용:
  python3 scripts/split_takes.py <긴 녹화.mp4> --talker T1 --set sentence --form A --out <영상 폴더> --dry-run
  python3 scripts/split_takes.py <긴 녹화.mp4> --talker T1 --set sentence --form A --out <영상 폴더> --skip 5
"""
import argparse
import csv
import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(ROOT, "docs", "pilot", "shot-list.csv")
PAD = 1.0          # 클립 앞뒤 여백(초): 입을 다문 1초
MIN_SPEECH = 0.35  # 이보다 짧은 소리는 말이 아닌 잡음으로 본다


def speech_segments(path: str, noise_db: float, min_silence: float) -> list:
    """(시작, 끝) 말소리 구간 목록. silencedetect의 조용한 구간 사이를 말로 본다."""
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af",
           f"silencedetect=noise={noise_db}dB:d={min_silence}", "-f", "null", "-"]
    err = subprocess.run(cmd, capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([0-9.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", err)]
    dur = None
    m = re.search(r"Duration: (\d+):(\d+):([0-9.]+)", err)
    if m:
        h, mi, se = m.groups()
        dur = int(h) * 3600 + int(mi) * 60 + float(se)
    segs, t = [], 0.0
    for s, e in zip(starts, ends + [None] * (len(starts) - len(ends))):
        if s - t >= MIN_SPEECH:
            segs.append((t, s))
        t = e if e is not None else s
    if dur and dur - t >= MIN_SPEECH:
        segs.append((t, dur))
    return segs, dur


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--talker", required=True)
    ap.add_argument("--set", required=True, choices=["word", "sentence", "av", "snr"])
    ap.add_argument("--form", required=True, help="A, B, C, 예비, 또는 snr은 -")
    ap.add_argument("--out", required=True, help="영상 폴더(LIPLAB_PILOT_MEDIA_DIR)")
    ap.add_argument("--noise-db", type=float, default=-35.0)
    ap.add_argument("--min-silence", type=float, default=1.2)
    ap.add_argument("--skip", default="", help="버릴 구간 번호(1부터), 쉼표로")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--csv", default=CSV, help="촬영 목록(기본 docs/pilot/shot-list.csv)")
    a = ap.parse_args()

    with open(a.csv, encoding="utf-8") as f:
        shots = [r for r in csv.DictReader(f) if r["talker"] == a.talker and r["set"] == a.set and r["form"] == a.form]
    if not shots:
        raise SystemExit("촬영 목록에 그 화자·묶음·폼이 없다")
    segs, dur = speech_segments(a.video, a.noise_db, a.min_silence)
    skip = {int(x) for x in a.skip.split(",") if x.strip()}
    report = os.path.splitext(a.video)[0] + ".segments.csv"
    with open(report, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["구간", "시작", "끝", "길이", "버림"])
        for i, (s, e) in enumerate(segs, 1):
            w.writerow([i, f"{s:.2f}", f"{e:.2f}", f"{e - s:.2f}", "예" if i in skip else ""])
    kept = [seg for i, seg in enumerate(segs, 1) if i not in skip]
    print(f"말소리 구간 {len(segs)}개(버림 {len(skip)}개) → 남은 {len(kept)}개, 목록 {len(shots)}개. 구간 표: {report}")
    if len(kept) != len(shots):
        raise SystemExit("구간 수가 목록 수와 다르다. 구간 표를 보고 --skip이나 --noise-db/--min-silence를 고친다.")
    if a.dry_run:
        for (s, e), r in zip(kept, shots):
            print(f"  {s:7.2f}–{e:7.2f}  {r['id']:5s} {r['text']}")
        return
    for (s, e), r in zip(kept, shots):
        out = os.path.join(a.out, r["file"])
        os.makedirs(os.path.dirname(out), exist_ok=True)
        st = max(0.0, s - PAD)
        en = min(dur or e + PAD, e + PAD)
        # 다시 인코딩해 프레임 단위로 정확히 자른다(키프레임 탐색으로 자르면 앞이 어긋난다). 60fps·48kHz 유지
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{st:.3f}", "-i", a.video,
                        "-t", f"{en - st:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-r", "60",
                        "-c:a", "aac", "-ar", "48000", "-b:a", "160k", out], check=True)
        print(f"썼음: {r['file']} ({r['text']})")


if __name__ == "__main__":
    main()
