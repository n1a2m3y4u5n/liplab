#!/usr/bin/env python3
"""kmsav_fetch.py: KMSAV(ETRI, CC BY-NC-SA 4.0) 원본 영상 받기. 학습 전용 자료(docs/decisions-2026-10-27.md).

규칙(사용자 승인 10/28)
  - yt-dlp는 별도 venv(liplab-lab/venv-kmsav)에서만 돈다. 로그인·쿠키 없이, 동시 1개, --limit-rate 5M.
  - 영상 사이 5~15초 무작위로 쉰다.
  - 지워졌거나 막힌 영상은 건너뛰고 사유를 센다.
  - HTTP 429나 봇 확인("Sign in to confirm") 문구가 한 번이라도 나오면 KMSAV_STOP을 남기고 전체를 멈춘다.
  - 538 E2 받기 보호: E2 transfers.jsonl 최근 속도가 시작 전 기준보다 30% 넘게 떨어지면 현재 영상을 마치고 30분 양보.
    (train538_fetch.Yielder와 같은 방식. 이 파일은 그 코드를 읽지 않고 같은 규칙을 따로 구현한다.)
  - 재개 가능: 이미 받은 영상(<id>.mp4)은 건너뛴다. 상태는 state.json, 로그는 fetch.log.
"""
import argparse
import json
import random
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(r'D:\work\hq\projects\liplab-lab\ext\kmsav-repo')
RAW = Path(r'C:\liplab-raw\kmsav')
DATA = Path(r'D:\work\hq\projects\liplab-lab\data\kmsav')
E2_TRANSFERS = Path(r'D:\work\hq\projects\liplab-lab\data\e2_538\transfers.jsonl')
YT_DLP_PY = Path(r'D:\work\hq\projects\liplab-lab\venv-kmsav\Scripts\python.exe')
YIELD_DROP = 0.30
YIELD_WAIT = 1800
FATAL = re.compile(r"HTTP Error 429|Too Many Requests|Sign in to confirm you(?:'|’)?re not a bot", re.I)   # 10/28: 연령 제한('confirm your age')은 쿠키 없이 못 받으니 건너뛴다
GONE = [
    (re.compile(r'Video unavailable|has been removed|account.*terminated|no longer available', re.I), 'removed'),
    (re.compile(r'private video', re.I), 'private'),
    (re.compile(r'not available in your country|blocked it in your country|geo', re.I), 'geo'),
    (re.compile(r'confirm your age|age-restricted|inappropriate for some users', re.I), 'age'),
    (re.compile(r'members-only|Join this channel', re.I), 'members'),
    (re.compile(r'Requested format is not available', re.I), 'no_format'),
]


def now():
    return datetime.now().isoformat(timespec='seconds')


def log(*parts):
    line = now() + ' ' + ' '.join(str(p) for p in parts)
    print(line, flush=True)
    DATA.mkdir(parents=True, exist_ok=True)
    with (DATA / 'fetch.log').open('a', encoding='utf-8') as f:
        f.write(line + '\n')


def read_list(splits, asd_dir=None):
    out = []
    for line in (REPO / 'data' / 'list.txt').read_text(encoding='utf-8').splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        vid, domain, npart, sec, split = line.split()[:5]
        if split in splits and (asd_dir is None or (asd_dir / vid).is_dir()):
            out.append({'id': vid, 'domain': domain, 'sec': int(sec), 'split': split})
    return out


def e2_rows(path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass
    return rows


def speed(rows, k):
    rows = [r for r in rows if r.get('seconds', 0) >= 60][-k:]
    sec = sum(r['seconds'] for r in rows)
    return sum(r['bytes'] for r in rows) / sec if sec else None


class Yielder:
    """시작 전 E2 최근 5건 속도가 기준. 시작 뒤 새 E2 전송 최근 3건이 기준의 70% 미만이면 양보."""
    def __init__(self, path=E2_TRANSFERS, sleep=time.sleep, wait=YIELD_WAIT):
        self.path, self.sleep, self.wait = path, sleep, wait
        rows = e2_rows(path)
        self.mark = len(rows)
        self.baseline = speed(rows, 5)

    def slow(self):
        recent = speed(e2_rows(self.path)[self.mark:], 3)
        return (self.baseline is not None and recent is not None
                and recent < (1 - YIELD_DROP) * self.baseline), recent

    def check(self):
        slow, recent = self.slow()
        while slow:
            with (DATA / 'KMSAV_YIELD').open('a', encoding='utf-8') as f:
                f.write(json.dumps({'time': now(), 'baseline_Bps': self.baseline, 'recent_Bps': recent}) + '\n')
            log('KMSAV_YIELD baseline', round(self.baseline), 'recent', round(recent), 'wait', self.wait)
            self.mark = len(e2_rows(self.path))
            self.sleep(self.wait)
            slow, recent = self.slow()


def classify(text):
    if FATAL.search(text):
        return 'FATAL'
    for rx, name in GONE:
        if rx.search(text):
            return name
    return 'error'


def ffmpeg_exe():
    r = subprocess.run([str(YT_DLP_PY), '-c', 'import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())'],
                       capture_output=True, text=True)
    return r.stdout.strip()


def download(vid, args):
    """returns (status, detail). status: ok | FATAL | removed/private/geo/age/members/no_format/error"""
    out = RAW / f'{vid}.mp4'
    fmt = f'bestvideo[height={args.height}]+bestaudio/bestvideo[height<=1080][height>={args.height}]+bestaudio'   # ASD 좌표가 ImageSize(1280x720) 기준이라 720을 기본으로 받고, kmsav_prepare가 그 크기로 맞춰 자른다
    cmd = [str(YT_DLP_PY), '-m', 'yt_dlp', '--no-simulate', '--no-playlist', '--no-cookies', '--ffmpeg-location', ffmpeg_exe(),
           '--limit-rate', args.limit_rate, '--concurrent-fragments', '1', '-f', fmt,
           '--merge-output-format', 'mp4', '--no-part', '--retries', '3',
           '-o', str(RAW / f'{vid}.%(ext)s'), f'https://youtube.com/watch?v={vid}']
    p = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    text = (p.stdout or '') + '\n' + (p.stderr or '')
    if FATAL.search(text):
        return 'FATAL', text[-400:]
    if p.returncode == 0 and out.exists() and out.stat().st_size > 0:
        return 'ok', out.stat().st_size
    return classify(text), text.strip().splitlines()[-1][:200] if text.strip() else ''


def load_state():
    p = DATA / 'state.json'
    if p.exists():
        return json.loads(p.read_text(encoding='utf-8'))
    return {'done': [], 'skipped': {}, 'bytes': 0}


def save_state(st):
    tmp = DATA / 'state.json.tmp'
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding='utf-8')
    tmp.replace(DATA / 'state.json')


def run(queue, args, dl=download, yielder=None, sleep=time.sleep):
    RAW.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    stop = DATA / 'KMSAV_STOP'
    if stop.exists():
        log('KMSAV_STOP 있음: 사람이 확인하고 지우기 전에는 시작하지 않는다')
        return 2
    st = load_state()
    yielder = yielder or Yielder()
    got = 0
    log('START queue', len(queue), 'done', len(st['done']), 'skipped', len(st['skipped']), 'baseline_Bps', yielder.baseline)
    for row in queue:
        vid = row['id']
        if vid in st['done'] or vid in st['skipped'] or (RAW / f'{vid}.mp4').exists():
            if vid not in st['done'] and (RAW / f'{vid}.mp4').exists() and vid not in st['skipped']:
                st['done'].append(vid)
            continue
        if args.max_videos and got >= args.max_videos:
            break
        if stop.exists():
            return 2
        yielder.check()
        status, detail = dl(vid, args)
        if status == 'FATAL':
            stop.write_text(json.dumps({'time': now(), 'video': vid, 'detail': detail}, ensure_ascii=False), encoding='utf-8')
            log('KMSAV_STOP', vid, detail.replace('\n', ' ')[:200])
            save_state(st)
            return 2
        if status == 'ok':
            st['done'].append(vid)
            st['bytes'] += int(detail)
            got += 1
            log('OK', vid, int(detail) // 1_000_000, 'MB')
        else:
            st['skipped'][vid] = {'reason': status, 'detail': detail}
            log('SKIP', vid, status, detail)
        save_state(st)
        sleep(random.uniform(args.pause_min, args.pause_max))
    reasons = {}
    for v in st['skipped'].values():
        reasons[v['reason']] = reasons.get(v['reason'], 0) + 1
    log('END done', len(st['done']), 'skipped', len(st['skipped']), reasons, 'GB', round(st['bytes'] / 1e9, 1))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--splits', default='train,valid,test', help='list.txt의 split. 기본은 ASD 정보가 있는 train,valid,test')
    ap.add_argument('--asd-dir', default=str(DATA / 'kmsav_asd_v0.2'), help='이 폴더에 있는 영상만 받는다(없으면 --no-asd-filter)')
    ap.add_argument('--no-asd-filter', action='store_true')
    ap.add_argument('--height', type=int, default=720)
    ap.add_argument('--limit-rate', default='5M')
    ap.add_argument('--pause-min', type=float, default=5)
    ap.add_argument('--pause-max', type=float, default=15)
    ap.add_argument('--max-videos', type=int, default=0, help='이번 실행에서 새로 받을 최대 개수(0이면 제한 없음). 시험은 1~2')
    ap.add_argument('--only', default='', help='쉼표로 나눈 영상 ID만(시험용)')
    ap.add_argument('--dry-run', action='store_true', help='개수·총 시간·예상 용량만 출력')
    args = ap.parse_args(argv)
    queue = read_list(set(args.splits.split(',')), None if args.no_asd_filter else Path(args.asd_dir))
    if args.only:
        keep = set(args.only.split(','))
        queue = [r for r in queue if r['id'] in keep]
    if args.dry_run:
        sec = sum(r['sec'] for r in queue)
        print(json.dumps({'videos': len(queue), 'hours': round(sec / 3600, 1),
                          'est_GB_at_720p_1_to_2_Mbps': [round(sec * 1e6 / 8e9), round(sec * 2e6 / 8e9)]}))
        return 0
    return run(queue, args)


if __name__ == '__main__':
    sys.exit(main())
