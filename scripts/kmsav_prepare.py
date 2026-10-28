#!/usr/bin/env python3
r"""kmsav_prepare.py: 받은 KMSAV 원본(C:\liplab-raw\kmsav\<id>.mp4)에서 발화 클립과 입 ROI 팩을 만든다(학습 전용).

  1) HOWTO대로 ffmpeg로 wav 추출 → utils/crop_video.py(ASD 정보로 문장별 얼굴 224x224 클립) → data/kmsav/cropped/<id>/utts
  2) 얼굴 클립(<utt>.mp4, _audio 제외)을 data/kmsav/roi_in/<id>_<utt>.mp4 로 하드링크
  3) 기존 전처리 liplab-lab/tools/lip_roi_extract.py(88x88 흑백, MediaPipe)로 data/kmsav/roi/ 에 npz (--roi)
  --keep-frames 가 없으면 프레임 jpg(원본 용량의 수 배)는 클립을 만든 뒤 지운다. --delete-raw 면 처리 끝난 원본도 지운다.
원자료·영상은 앱·공개 저장소에 넣지 않는다.
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(r'D:\work\hq\projects\liplab-lab\ext\kmsav-repo')
RAW = Path(r'C:\liplab-raw\kmsav')
DATA = Path(r'D:\work\hq\projects\liplab-lab\data\kmsav')
LAB = Path(r'D:\work\hq\projects\liplab-lab')
PY_PREP = LAB / 'venv-kmsav' / 'Scripts' / 'python.exe'   # opencv + ffmpeg
PY_ROI = LAB / 'venv-mp' / 'Scripts' / 'python.exe'       # mediapipe
ROI_TOOL = LAB / 'tools' / 'lip_roi_extract.py'


def env():
    e = dict(os.environ)
    e['PYTHONUTF8'] = '1'   # crop_video가 open()을 인코딩 없이 써서 cp949로 읽다 깨진다
    e['PATH'] = str(LAB / 'venv-kmsav' / 'bin') + os.pathsep + e['PATH']   # ffmpeg.exe
    return e


def asd_size(vid):
    for f in sorted((DATA / 'kmsav_asd_v0.2' / vid).glob('??????.txt'))[:1]:
        for line in f.read_text(encoding='utf-8').splitlines():
            if line.startswith('# ImageSize:'):
                w, h = line.split(':')[1].split()
                return int(w), int(h)
    return None


def crop_one(vid, keep_frames):
    video = RAW / f'{vid}.mp4'
    wav = RAW / f'{vid}.wav'
    cropped = DATA / 'cropped'
    if (cropped / vid / 'DONE').exists():
        return 'skip'
    if not wav.exists():
        subprocess.run([str(LAB / 'venv-kmsav' / 'bin' / 'ffmpeg.exe'), '-y', '-loglevel', 'error', '-i', str(video), '-qscale:a', '0', '-ac', '1', '-vn',
                        '-ar', '16000', str(wav)], check=True, env=env())
    # crop_video.avi2images는 Windows에서 ffmpeg 호출이 깨지므로(명령이 튜플, PATH) 프레임은 여기서 먼저 뽑는다. 있으면 그대로 재사용한다.
    frames = cropped / vid / 'frames'
    if not (frames / '000001.jpg').exists():
        frames.mkdir(parents=True, exist_ok=True)
        scale = asd_size(vid)   # ASD 좌표는 ImageSize 기준이라 프레임을 그 크기로 맞춘다
        subprocess.run([str(LAB / 'venv-kmsav' / 'bin' / 'ffmpeg.exe'), '-y', '-loglevel', 'error', '-i', str(video),
                        '-qscale:v', '2', '-vf', 'fps=25' + (f',scale={scale[0]}:{scale[1]}' if scale else ''), '-f', 'image2', str(frames / '%06d.jpg')], check=True)
    p = subprocess.run([str(PY_PREP), str(REPO / 'utils' / 'crop_video.py'), '--asdinfo-dir', str(DATA / 'kmsav_asd_v0.2'),
                        '--save-root', str(cropped), str(video)], env=env(), capture_output=True, text=True)
    if p.returncode != 0:
        return 'fail: ' + (p.stderr or '')[-200:]
    if not keep_frames:
        shutil.rmtree(cropped / vid / 'frames', ignore_errors=True)
    wav.unlink(missing_ok=True)
    (cropped / vid / 'DONE').write_text('ok')
    return 'ok'


def link_roi_inputs(vid):
    dst = DATA / 'roi_in'
    dst.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in sorted((DATA / 'cropped' / vid / 'utts').glob('??????.mp4')):
        d = dst / f'{vid}_{f.stem}.mp4'
        if not d.exists():
            os.link(f, d)
        n += 1
    return n


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--ids', default='', help='쉼표로 나눈 영상 ID. 비우면 RAW의 모든 mp4')
    ap.add_argument('--roi', action='store_true', help='입 ROI 팩(88x88 npz)까지 만든다')
    ap.add_argument('--keep-frames', action='store_true')
    ap.add_argument('--delete-raw', action='store_true')
    ap.add_argument('--workers', type=int, default=2)
    a = ap.parse_args(argv)
    ids = a.ids.split(',') if a.ids else sorted(p.stem for p in RAW.glob('*.mp4'))
    done = []
    for vid in ids:
        r = crop_one(vid, a.keep_frames)
        n = link_roi_inputs(vid) if r in ('ok', 'skip') else 0
        print(vid, r, 'utts', n, flush=True)
        if r in ('ok', 'skip'):
            done.append(vid)
    if a.roi and done:
        p = subprocess.run([str(PY_ROI), str(ROI_TOOL), '--clips', str(DATA / 'roi_in'), '--out', str(DATA / 'roi'),
                            '--workers', str(a.workers)])
        if p.returncode:
            print('ROI rc', p.returncode)
            return 1
    if a.delete_raw and (not a.roi or p.returncode == 0):
        for vid in done:
            (RAW / f'{vid}.mp4').unlink(missing_ok=True)   # 상태 json에는 남으므로 다시 받지 않는다
    return 0


if __name__ == '__main__':
    sys.exit(main())
