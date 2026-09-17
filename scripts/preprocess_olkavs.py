#!/usr/bin/env python
"""
OLKAVS(AI Hub 립리딩 데이터) 전처리 — 축 A·B(오디오) · 축 D(립리딩) 학습 데이터 준비.

라벨 JSON의 문장별 타임스탬프와 프레임별 입술 바운딩박스를 이용해, 원본 mp4를
'문장 단위 입술 ROI 클립 + 오디오 + 텍스트 라벨'로 잘라낸다. torch 없이 ffmpeg만으로
동작한다(GPU 불필요 — 로컬 CPU에서 돌린 뒤 결과만 GPU 서버로 올리는 것이 전제).

왜 로컬에서 먼저 줄이는가. OLKAVS 전체는 20TB급(다각도 고해상도)이라 그대로 클라우드에
올리면 저장 비용만 월 $1,000 규모다. 여기서 오디오(16kHz 모노)와 96x96 입술 크롭만
남기면 수십 GB로 줄어 업로드·저장이 현실적이 된다.

  # 오디오만 (가장 빠름 — 영상 디코딩을 건너뛴다. 축 A·B 착수용)
  python scripts/preprocess_olkavs.py --dir <데이터> --out <출력> --mode audio

  # 입술 클립만 (축 D 립리딩용)
  python scripts/preprocess_olkavs.py --dir <데이터> --out <출력> --mode video

  # 둘 다 / 일부만 / 병렬도 지정
  python scripts/preprocess_olkavs.py --dir <데이터> --out <출력> --mode both --limit 50 --jobs 8

출력: <out>/clips/<video>_<문장ID>.mp4  (입술 크롭 96x96, 무음)
      <out>/audio/<video>_<문장ID>.flac (16kHz 모노)
      <out>/labels.jsonl                (문장 텍스트 + 시각 + 파일 경로)
"""
import argparse
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple

_CROP = 96      # 립리딩 표준 입력 한 변(px)
_SR = 16000     # 음향 모델(wav2vec2/WavLM) 표준 샘플레이트


def _run(cmd: List[str]) -> bool:
    """ffmpeg 실행. 한 클립 실패가 전체 배치를 멈추지 않도록 예외 대신 성공 여부를 돌려준다."""
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


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


def index_media(dir_path: str) -> Tuple[List[str], Dict[str, str]]:
    """
    폴더를 **한 번만** 순회해 (라벨 JSON 목록, mp4 파일명→경로 인덱스)를 만든다.

    예전 구현은 JSON 하나마다 전체 폴더를 다시 훑어(O(n²)) 파일이 수만 개인 실제
    데이터셋에서는 사실상 끝나지 않았다. 20TB 규모에서 이 인덱싱이 전처리 가능/불가능을
    가른다.
    """
    jsons: List[str] = []
    mp4s: Dict[str, str] = {}
    for root, _dirs, files in os.walk(dir_path):
        for f in files:
            if f.endswith(".json"):
                jsons.append(os.path.join(root, f))
            elif f.endswith(".mp4"):
                mp4s.setdefault(f, os.path.join(root, f))
    return sorted(jsons), mp4s


def _load_label(path_or_bytes) -> Optional[dict]:
    """라벨 JSON은 항목 하나를 리스트로 감싼 형태다. 깨진 파일은 건너뛴다."""
    try:
        if isinstance(path_or_bytes, (bytes, bytearray)):
            data = json.loads(path_or_bytes)
        else:
            with open(path_or_bytes, encoding="utf-8") as f:
                data = json.load(f)
        return data[0] if isinstance(data, list) and data else (data if isinstance(data, dict) else None)
    except (json.JSONDecodeError, OSError, IndexError):
        return None


def _iter_samples(zip_path: Optional[str], dir_path: Optional[str], limit: int):
    """(라벨 dict, mp4 경로, 정리 함수)를 순회 산출. limit>0이면 영상 수를 제한한다."""
    n = 0
    if zip_path:
        z = zipfile.ZipFile(zip_path)
        names = z.namelist()
        mp4s = [x for x in names if x.endswith(".mp4")]
        for jn in (x for x in names if x.endswith(".json")):
            if limit and n >= limit:
                return
            d = _load_label(z.read(jn))
            if not d:
                continue
            vname = d.get("Video_info", {}).get("video_Name")
            entry = next((m for m in mp4s if vname and m.endswith(vname)), None)
            if not entry:
                continue
            tmp = os.path.join(tempfile.gettempdir(), vname)
            with z.open(entry) as src, open(tmp, "wb") as dst:
                shutil.copyfileobj(src, dst)
            n += 1
            yield d, tmp, (lambda p=tmp: os.path.exists(p) and os.remove(p))
    else:
        jsons, mp4s = index_media(dir_path)
        print(f"인덱싱 완료 — 라벨 {len(jsons)}개, 영상 {len(mp4s)}개")
        for jp in jsons:
            if limit and n >= limit:
                return
            d = _load_label(jp)
            if not d:
                continue
            vname = d.get("Video_info", {}).get("video_Name")
            mp4 = mp4s.get(vname) if vname else None
            if mp4:
                n += 1
                yield d, mp4, (lambda: None)


def _clip_jobs(d: dict, mp4: str, out_dir: str, mode: str, max_sentences: int,
               full_audio: Optional[str]) -> Tuple[List[Tuple], List[dict]]:
    """한 영상에서 뽑을 (ffmpeg 명령, 산출 경로) 목록과 라벨 행을 만든다."""
    vinfo = d.get("Video_info", {})
    vid = os.path.splitext(vinfo.get("video_Name", ""))[0]
    try:
        fps = float(vinfo["FPS"])
        res = str(vinfo["Resolution"]).lower().replace("x", "*").split("*")
        W, H = int(res[0]), int(res[1])
    except (KeyError, ValueError, IndexError):
        return [], []
    lip = d.get("Bounding_box_info", {}).get("Lip_bounding_box", {}).get("xtl_ytl_xbr_ybr", [])
    sents = d.get("Sentence_info", []) or []
    if max_sentences:
        sents = sents[:max_sentences]

    jobs, rows = [], []
    for s in sents:
        try:
            start, end = float(s["start_time"]), float(s["end_time"])
        except (KeyError, ValueError):
            continue
        name = f"{vid}_{s.get('ID')}"
        row = {"id": name, "text": s.get("sentence_text"), "topic": s.get("topic"),
               "start": start, "end": end}

        if mode in ("video", "both"):
            box = union_square_box(lip[int(start * fps):int(end * fps)], W, H)
            if not box:
                continue  # 입술 박스가 없으면 립리딩 학습에 쓸 수 없다
            x, y, w, h = box
            clip = os.path.join(out_dir, "clips", f"{name}.mp4")
            row["clip"] = os.path.relpath(clip, out_dir)
            # 이미 만든 산출물은 건너뛴다 — 며칠 걸리는 작업이라 중단 후 이어서 돌릴 수 있어야 한다.
            if not os.path.exists(clip):
                jobs.append((["ffmpeg", "-y", "-ss", str(start), "-to", str(end), "-i", mp4,
                              "-vf", f"crop={w}:{h}:{x}:{y},scale={_CROP}:{_CROP}",
                              "-an", "-loglevel", "error", clip], clip))

        if mode in ("audio", "both") and full_audio:
            wav = os.path.join(out_dir, "audio", f"{name}.flac")
            row["audio"] = os.path.relpath(wav, out_dir)
            if not os.path.exists(wav):
                # 영상이 아니라 이미 뽑아둔 전체 오디오에서 자른다(디코딩이 훨씬 싸다).
                jobs.append((["ffmpeg", "-y", "-ss", str(start), "-to", str(end), "-i", full_audio,
                              "-c:a", "flac", "-loglevel", "error", wav], wav))

        rows.append(row)
    return jobs, rows


def process(zip_path, dir_path, out_dir, max_sentences, mode="video", jobs_n=4, limit=0):
    if mode in ("video", "both"):
        os.makedirs(os.path.join(out_dir, "clips"), exist_ok=True)
    if mode in ("audio", "both"):
        os.makedirs(os.path.join(out_dir, "audio"), exist_ok=True)

    labels_path = os.path.join(out_dir, "labels.jsonl")
    # 이어서 돌릴 때 이전 라벨을 잃지 않도록 append로 열고, 중복 id는 나중에 걸러진다.
    done_ids = set()
    if os.path.exists(labels_path):
        with open(labels_path, encoding="utf-8") as f:
            for line in f:
                try:
                    done_ids.add(json.loads(line)["id"])
                except (json.JSONDecodeError, KeyError):
                    pass
        print(f"이어서 진행 — 기존 라벨 {len(done_ids)}개")

    n_video = n_clip = n_fail = 0
    with open(labels_path, "a", encoding="utf-8") as lf:
        for d, mp4, cleanup in _iter_samples(zip_path, dir_path, limit):
            vid = os.path.splitext(d.get("Video_info", {}).get("video_Name", ""))[0]
            full_audio = None
            try:
                if mode in ("audio", "both"):
                    # 영상당 한 번만 전체 오디오를 뽑아 두고(단일 패스), 문장별로는 여기서
                    # 잘라낸다. 문장마다 원본 영상을 다시 열면 디코딩이 문장 수만큼 반복된다.
                    full_audio = os.path.join(tempfile.gettempdir(), f"{vid}_full.flac")
                    if not _run(["ffmpeg", "-y", "-i", mp4, "-vn", "-ac", "1", "-ar", str(_SR),
                                 "-c:a", "flac", "-loglevel", "error", full_audio]):
                        full_audio = None

                jobs, rows = _clip_jobs(d, mp4, out_dir, mode, max_sentences, full_audio)
                rows = [r for r in rows if r["id"] not in done_ids]

                if jobs:
                    with ThreadPoolExecutor(max_workers=jobs_n) as ex:
                        # ffmpeg는 별도 프로세스라 대기 중 GIL을 놓는다 → 스레드로 충분하다.
                        results = list(ex.map(lambda j: _run(j[0]), jobs))
                    n_fail += results.count(False)

                for r in rows:
                    lf.write(json.dumps(r, ensure_ascii=False) + "\n")
                    done_ids.add(r["id"])
                lf.flush()  # 중단되어도 여기까지는 남는다

                n_video += 1
                n_clip += len(rows)
                print(f"[{n_video}] {vid} — 문장 {len(rows)}개 (누적 {n_clip})")
            finally:
                if full_audio and os.path.exists(full_audio):
                    os.remove(full_audio)
                cleanup()

    print(f"\n영상 {n_video}개 · 문장 {n_clip}개 → {out_dir}")
    if n_fail:
        print(f"⚠️ ffmpeg 실패 {n_fail}건 (해당 항목은 라벨에 남아 있으니 재실행하면 다시 시도한다)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="OLKAVS 전처리(문장 단위 입술 클립·오디오)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--zip", help="OLKAVS 샘플 zip 경로")
    g.add_argument("--dir", help="압축 푼 폴더 경로")
    ap.add_argument("--out", required=True, help="출력 디렉토리")
    ap.add_argument("--mode", choices=["video", "audio", "both"], default="video",
                    help="video=입술 클립(축 D) / audio=오디오만(축 A·B, 가장 빠름) / both")
    ap.add_argument("--max", type=int, default=0, help="영상당 최대 문장 수(0=전체)")
    ap.add_argument("--limit", type=int, default=0, help="처리할 영상 수 제한(0=전체)")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 4, help="동시 ffmpeg 개수")
    args = ap.parse_args()
    process(args.zip, args.dir, args.out, args.max, args.mode, args.jobs, args.limit)
