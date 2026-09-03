#!/usr/bin/env python
"""
OLKAVS(AI Hub 립리딩 데이터) 전처리 — 축 D 자체 립리딩 모델 준비.

라벨 JSON의 문장별 타임스탬프와 프레임별 입술 바운딩박스를 이용해, 원본 mp4를
'문장 단위 입술 ROI 클립 + 텍스트 라벨'로 잘라낸다. 립리딩 학습(영상→텍스트/단어)의
표준 입력 형태다. torch 없이 ffmpeg만으로 동작한다(계획서 우선순위 1: 전처리 파이프라인 검증).

  python scripts/preprocess_olkavs.py --zip ~/Downloads/New_Sample.zip --out ~/olkavs_out --max 3
  python scripts/preprocess_olkavs.py --dir <압축푼폴더> --out <출력>

출력: <out>/clips/<video>_<문장ID>.mp4 (입술 크롭, 96x96) + <out>/labels.jsonl
"""
import argparse
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from typing import List, Optional, Tuple

_CROP = 96  # 립리딩 표준 입력 한 변(px)


def _run(cmd: List[str]) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def union_square_box(boxes: List[List[int]], W: int, H: int,
                     margin: float = 0.35) -> Optional[Tuple[int, int, int, int]]:
    """문장 구간의 프레임별 입술 박스들을 감싸는 정사각형 크롭 박스(x, y, side)."""
    boxes = [b for b in boxes if b and len(b) == 4]
    if not boxes:
        return None
    x1 = min(b[0] for b in boxes); y1 = min(b[1] for b in boxes)
    x2 = max(b[2] for b in boxes); y2 = max(b[3] for b in boxes)
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    side = max(x2 - x1, y2 - y1) * (1 + margin)
    s = int(min(side, W, H))
    x = int(max(0, min(cx - s / 2, W - s)))
    y = int(max(0, min(cy - s / 2, H - s)))
    s -= s % 2  # ffmpeg는 짝수 치수를 선호
    return x, y, s, s


def _iter_samples(zip_path: Optional[str], dir_path: Optional[str]):
    """(라벨 dict, mp4 경로 제공 함수, 정리 함수) 를 순회 산출."""
    if zip_path:
        z = zipfile.ZipFile(zip_path)
        names = z.namelist()
        jsons = [n for n in names if n.endswith(".json")]
        mp4s = [n for n in names if n.endswith(".mp4")]
        for jn in jsons:
            d = json.loads(z.read(jn))[0]
            vname = d["Video_info"]["video_Name"]
            entry = next((m for m in mp4s if m.endswith(vname)), None)
            if not entry:
                continue
            tmp = os.path.join(tempfile.gettempdir(), vname)
            with z.open(entry) as src, open(tmp, "wb") as dst:
                shutil.copyfileobj(src, dst)
            yield d, tmp, (lambda p=tmp: os.path.exists(p) and os.remove(p))
    else:
        for root, _dirs, files in os.walk(dir_path):
            for f in files:
                if not f.endswith(".json"):
                    continue
                d = json.loads(open(os.path.join(root, f), encoding="utf-8").read())[0]
                vname = d["Video_info"]["video_Name"]
                mp4 = None
                for r2, _d2, fs2 in os.walk(dir_path):
                    if vname in fs2:
                        mp4 = os.path.join(r2, vname); break
                if mp4:
                    yield d, mp4, (lambda: None)


def process(zip_path, dir_path, out_dir, max_sentences):
    clips_dir = os.path.join(out_dir, "clips")
    os.makedirs(clips_dir, exist_ok=True)
    labels = []
    for d, mp4, cleanup in _iter_samples(zip_path, dir_path):
        vid = os.path.splitext(d["Video_info"]["video_Name"])[0]
        fps = float(d["Video_info"]["FPS"])
        res = d["Video_info"]["Resolution"].lower().replace("x", "*").split("*")
        W, H = int(res[0]), int(res[1])
        lip = d["Bounding_box_info"]["Lip_bounding_box"]["xtl_ytl_xbr_ybr"]
        sents = d["Sentence_info"]
        if max_sentences:
            sents = sents[:max_sentences]
        for s in sents:
            sf, ef = int(s["start_time"] * fps), int(s["end_time"] * fps)
            box = union_square_box(lip[sf:ef], W, H)
            if not box:
                continue
            x, y, w, h = box
            out_clip = os.path.join(clips_dir, f"{vid}_{s['ID']}.mp4")
            _run(["ffmpeg", "-y", "-ss", str(s["start_time"]), "-to", str(s["end_time"]),
                  "-i", mp4, "-vf", f"crop={w}:{h}:{x}:{y},scale={_CROP}:{_CROP}",
                  "-an", "-loglevel", "error", out_clip])
            labels.append({"id": f"{vid}_{s['ID']}", "text": s["sentence_text"],
                           "topic": s.get("topic"), "start": s["start_time"],
                           "end": s["end_time"], "clip": os.path.relpath(out_clip, out_dir)})
            print(f"  ✓ {vid}_{s['ID']}  \"{s['sentence_text'][:24]}…\"  crop {w}x{h}")
        cleanup()
    with open(os.path.join(out_dir, "labels.jsonl"), "w", encoding="utf-8") as f:
        for row in labels:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\n클립 {len(labels)}개 → {clips_dir}\n라벨 → {os.path.join(out_dir, 'labels.jsonl')}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="OLKAVS 립리딩 전처리(문장 입술 ROI 클립)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--zip", help="OLKAVS 샘플 zip 경로")
    g.add_argument("--dir", help="압축 푼 폴더 경로")
    ap.add_argument("--out", required=True, help="출력 디렉토리")
    ap.add_argument("--max", type=int, default=0, help="영상당 최대 문장 수(0=전체)")
    args = ap.parse_args()
    process(args.zip, args.dir, args.out, args.max)
