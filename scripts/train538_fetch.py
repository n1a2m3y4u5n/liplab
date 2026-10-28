"""538 학습 자료 재수신(train538): 화자(배치) 하나씩, 연결 하나로, 앞부분만 흘려 받는다.

사전 등록: docs/train538-reacquire-prereg-2026-10-28.md. 이 스크립트는 그 문서의 큐·제외·분할 규칙을 그대로 구현한다.
- Stream(키 한 줄 규칙, 헤더 파일, 인증 실패·401·403·502 즉시 AUTH_STOP, 느리면 SLOW_STOP)은 e2_retry_acquire의 것을
  쓰되, 그 모듈의 ROOT를 이 스크립트의 DATA로 바꿔 E2 폴더에는 아무것도 쓰지 않는다(E2 폴더는 읽기만).
- 요청 횟수는 DATA/request-counts.json에 센다(파일당 최대 2회). 요청 전에 횟수를 먼저 기록한다. 자동 재시도는 없다.
- 영상 tar는 앞 1.8GiB까지만 흘려 받고 완결 mp4만 C:\\liplab-raw\\train538 에 푼다. 라벨 tar는 필요한 JSON을 찾으면 끊는다.
- E2 cohort 인물은 tar 멤버 헤더 이름으로 받기 전에 대조하고, 라벨 speaker_ID로 다시 확인한다.
- E2 transfers.jsonl의 최근 속도가 시작 전 기준보다 30% 넘게 떨어지면 지금 화자를 마친 뒤 TRAIN_YIELD를 남기고 30분 뒤 다시 본다.

사용:
  python scripts/train538_fetch.py --dry-run [--out TSV]   키 없이 큐만 만들고 크기·순서 출력
  python scripts/train538_fetch.py [--target N] [--retry-failed]
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import zlib
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2_retry_acquire as E2
from e2_retry_acquire import AuthFailure, SlowStop, JoinedParts

REPO = Path(__file__).resolve().parents[1]
DATA = Path(r'D:\work\hq\projects\liplab-lab\data\train538')
RAW = Path(r'C:\liplab-raw\train538')
E2_ROOT = Path(r'D:\work\hq\projects\liplab-lab\data\e2_538')
MAIN_OUT = Path(r'D:\work\hq\projects\liplab\out')
TOOLS = Path(r'D:\work\hq\projects\liplab-lab\tools')
FILETREE = MAIN_OUT / 'aihub538-filetree-retry.txt'
EXCLUDED = REPO / 'docs/e2-excluded-speakers-2026-10-27.txt'   # 학습에서는 빼지 않는다(옛 학습 화자, 사전 등록 2절). 해시만 확인
COHORT = REPO / 'docs/train538-e2-cohort-2026-10-28.json'
OVERLAP = REPO / 'docs/train538-e2-overlap-tars-2026-10-28.txt'
EVAL40 = REPO / 'scripts/lipread_v1/eval40.txt'
V3_CONFIRM = ('spk345', 'spk353', 'spk375', 'spk380', 'spk383', 'spk407', 'spk409', 'spk410', 'spk411', 'spk412',
              'spk471', 'spk473', 'spk502', 'spk507', 'spk508', 'spk509', 'spk511', 'spk607', 'spk613')
OLD_SPKC = ('spk297', 'spk298', 'spk299', 'spk300')   # TL1~4: 예전 spkc 자료와 인물이 겹칠 수 있다(v1-data-plan 2절)

VIDEO_CAP = int(1.8 * 2**30)
LABEL_CAP = 2**30
FRONT_FILES = 4          # 한 인물에서 풀 정면 mp4 수 상한(파일당 약 10문장)
CLIPS = 30               # 화자당 문장 클립(v1-data-plan 3절)
MIN_CLIPS = 15
EVAL_FRAC = 0.30         # V1·V17·ROI 평가 화자 비율(해시 기준, 사전 등록 3절). 92배치면 약 27명
YIELD_DROP = 0.30
YIELD_WAIT = 1800
MAX_CONNECTIONS = 2      # E2 포함 538 동시 연결
D_FREE_MIN = 60 * 10**9
NAME_RE = re.compile(r'_([CE]\d+)_([A-Z])_(\d+)\.(mp4|json)$')


def now():
    return datetime.now().isoformat(timespec='seconds')


def log(*parts):
    line = now() + ' ' + ' '.join(str(p) for p in parts)
    print(line, flush=True)
    DATA.mkdir(parents=True, exist_ok=True)
    with (DATA / 'download.log').open('a', encoding='utf-8') as f:
        f.write(line + '\n')


def base_name(member_name):
    return member_name.replace('\\', '/').rsplit('/', 1)[-1]


# ───────────────────────────── 큐(키 없이) ─────────────────────────────
def filetree(path=FILETREE):
    unit = {'MB': 2**20, 'GB': 2**30, 'KB': 1024, 'B': 1}
    return {m[0]: (int(m[1].replace(',', '')) * unit[m[2]], m[3])
            for m in re.findall(r'([TV][LS]\d+\.tar)\s*\|\s*([\d,]+)\s*(GB|MB|KB|B)\s*\|\s*(\d+)', path.read_text(encoding='utf-8'))}


def batch_spk(label_file):
    n = int(re.search(r'\d+', label_file)[0])
    return 'spk' + str(n + (296 if label_file.startswith('TL') else 600))


def read_list(path):
    return {l.split('\t')[0].strip() for l in path.read_text(encoding='utf-8').splitlines() if l.strip() and not l.startswith('#')}


def exclusions():
    """(제외 인물, 제외 배치, 제외 tar). E2 cohort 배치·인물, V1 eval40, V3 확인 19, TL1~4, E2가 요청한 tar."""
    assert hashlib.sha256(EXCLUDED.read_bytes()).hexdigest() == E2.EXHASH
    cohort = json.loads(COHORT.read_text(encoding='utf-8'))
    persons = set(cohort['e2_persons'])
    blocked_spk = set(cohort['e2_plan_spk']) | read_list(EVAL40) | set(V3_CONFIRM) | set(OLD_SPKC)
    return persons, blocked_spk, read_list(OVERLAP)


def build_queue(files, blocked_spk, overlap):
    """라벨·영상 tar 짝을 배치 번호 순서에서 하나 건너 하나(짝수 자리 먼저)로 놓는다. 제외 배치와 E2가 요청한 tar는 뺀다."""
    pairs = []
    for label in files:
        if not label.startswith(('TL', 'VL')):
            continue
        video = label.replace('TL', 'TS').replace('VL', 'VS')
        if video not in files:
            continue
        spk = batch_spk(label)
        if spk in blocked_spk or label in overlap or video in overlap:
            continue
        pairs.append({'spk': spk, 'label_file': label, 'label_fileSn': files[label][1], 'label_bytes': files[label][0],
                      'video_file': video, 'video_fileSn': files[video][1], 'video_bytes': files[video][0]})
    pairs.sort(key=lambda r: int(r['spk'][3:]))
    return pairs[0::2] + pairs[1::2]


def is_eval(spk):
    """V1·V17·ROI 평가 화자. 화자마다 정해져 수신 순서·인원에 따라 바뀌지 않는다."""
    return int(hashlib.sha256(('liplab-train538-eval:' + spk).encode()).hexdigest()[:8], 16) < EVAL_FRAC * 2**32


def half_of(spk):
    return zlib.crc32(spk.encode()) % 2


# ───────────────────────────── 요청 상한·연결 ─────────────────────────────
class Budget:
    def __init__(self, path, limit=2):
        self.path = path; self.limit = limit
        self.counts = json.loads(path.read_text()) if path.exists() else {}

    def take(self, name):
        if self.counts.get(name, 0) >= self.limit:
            raise ValueError('request limit: ' + name)
        self.counts[name] = self.counts.get(name, 0) + 1
        self.path.write_text(json.dumps(self.counts, indent=2, sort_keys=True))   # 요청 전에 남긴다


def auth_stopped():
    return [p for p in (DATA / 'AUTH_STOP', E2_ROOT / 'AUTH_STOP', DATA / 'SLOW_STOP') if p.exists()]


def aihub_connections():
    """538 서버로 가는 curl 수(E2 포함)."""
    cmd = ['powershell', '-NoProfile', '-Command',
           "@(Get-CimInstance Win32_Process -Filter \"Name='curl.exe'\" | Where-Object { $_.CommandLine -like '*api.aihub.or.kr*' }).Count"]
    try:
        return int(subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout.strip() or 0)
    except Exception:
        return MAX_CONNECTIONS   # 모르면 꽉 찬 것으로 본다


# ───────────────────────────── E2 속도·양보 ─────────────────────────────
def e2_transfers(path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def speed(rows, k):
    rows = [r for r in rows if r.get('seconds', 0) >= 60][-k:]
    sec = sum(r['seconds'] for r in rows)
    return sum(r['bytes'] for r in rows) / sec if sec else None


class Yielder:
    """시작 전 E2 최근 5건 속도가 기준. 시작 뒤 새로 생긴 E2 전송의 최근 3건이 기준의 70% 미만이면 양보한다."""
    def __init__(self, path=None, sleep=time.sleep, wait=YIELD_WAIT):
        self.path = path or E2_ROOT / 'transfers.jsonl'; self.sleep = sleep; self.wait = wait
        path = self.path
        rows = e2_transfers(path)
        self.mark = len(rows)
        self.baseline = speed(rows, 5)

    def slow(self):
        rows = e2_transfers(self.path)
        recent = speed(rows[self.mark:], 3)
        return (self.baseline is not None and recent is not None and recent < (1 - YIELD_DROP) * self.baseline), recent

    def check(self):
        """화자 경계에서 부른다. 느리면 TRAIN_YIELD를 남기고 30분씩 기다린다. 그 사이 새 E2 전송이 없으면 다시 시작한다."""
        slow, recent = self.slow()
        while slow:
            with (DATA / 'TRAIN_YIELD').open('a', encoding='utf-8') as f:
                f.write(json.dumps({'time': now(), 'baseline_Bps': self.baseline, 'recent_Bps': recent}) + '\n')
            log('TRAIN_YIELD baseline', round(self.baseline), 'recent', round(recent), 'wait', self.wait)
            self.mark = len(e2_transfers(self.path))
            self.sleep(self.wait)
            slow, recent = self.slow()
        return True


# ───────────────────────────── tar 풀기 ─────────────────────────────
def extract_front(stream, eligible, dest, want=FRONT_FILES):
    """첫 적격 인물의 정면(A) 완결 mp4만 dest에 푼다. 다른 인물·시점은 이름(헤더)만 보고 건너뛴다.
    잘린 마지막 멤버와 ReadError는 버린다. (인물, [mp4 경로]) 반환."""
    person, saved = None, []
    try:
        with tarfile.open(fileobj=stream, mode='r|') as outer:
            with tarfile.open(fileobj=JoinedParts(outer), mode='r|') as inner:
                for m in inner:
                    if not m.isfile():
                        continue
                    name = base_name(m.name)
                    g = NAME_RE.search(name)
                    if not g or g[4] != 'mp4' or g[2] != 'A':
                        continue
                    if person is None:
                        if not eligible(g[1]):
                            continue
                        person = g[1]
                    elif g[1] != person:
                        break
                    out = dest / name
                    tmp = out.with_suffix('.partial')
                    try:
                        with tmp.open('wb') as f:
                            shutil.copyfileobj(inner.extractfile(m), f, 1024 * 1024)
                        if tmp.stat().st_size != m.size:
                            break
                        tmp.replace(out)
                        saved.append(out)
                    finally:
                        tmp.unlink(missing_ok=True)
                    if len(saved) >= want:
                        break
    except (tarfile.ReadError, EOFError):
        pass
    return person, saved


def extract_labels(stream, wanted):
    """wanted(라벨 JSON 이름 집합)를 모두 찾으면 멈춘다. {이름: dict}."""
    found = {}
    try:
        with tarfile.open(fileobj=stream, mode='r|') as outer:
            with tarfile.open(fileobj=JoinedParts(outer), mode='r|') as inner:
                for m in inner:
                    name = base_name(m.name)
                    if not m.isfile() or name not in wanted:
                        continue
                    data = json.load(inner.extractfile(m))
                    found[name] = data[0] if isinstance(data, list) else data
                    if len(found) == len(wanted):
                        break
    except (tarfile.ReadError, EOFError, ValueError):
        pass
    return found


# ───────────────────────────── 화자 하나 ─────────────────────────────
def open_stream(budget, file, fileSn, cap, connections):
    stops = auth_stopped()
    if stops:
        raise AuthFailure('stop file present: ' + ', '.join(str(p) for p in stops))
    while connections() >= MAX_CONNECTIONS:
        log('WAIT_CONNECTIONS', file)
        time.sleep(60)
    budget.take(file)
    return E2.Stream({'video_file': file, 'video_fileSn': fileSn}, cap)


def cut_clips(sources, labels, row, person, ff):
    """정면 mp4 순서, 라벨 문장 순서로 최대 30개를 30fps mp4·16kHz wav로 자른다."""
    sys.path.insert(0, str(TOOLS))
    import parse_sentences
    clips_dir = DATA / 'clips'
    clips_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for src in sources:
        d = labels.get(src.with_suffix('.json').name)
        if d is None:
            continue
        assert d['speaker_info']['speaker_ID'] == person and Path(d['Video_info']['video_Name']).name == src.name
        base = src.stem
        for idx, sid, rs, re_, start, dur, tx in parse_sentences.sentences(d):
            if len(out) >= CLIPS:
                return out
            name = f'{base}_{idx}'
            mp4 = clips_dir / (name + '.mp4')
            wav = mp4.with_suffix('.wav')
            cmd = [ff, '-v', 'error', '-y', '-ss', start, '-i', str(src), '-t', dur, '-map', '0:v:0', '-map', '0:a:0',
                   '-vf', 'scale=640:-2', '-r', '30', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23', '-threads', '2',
                   '-c:a', 'aac', '-ac', '1', str(mp4), '-t', dur, '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', str(wav)]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            out.append({'clip': name, 'text': tx, 'start': float(start), 'duration': float(dur), 'sentence_ID': sid})
    return out


def fetch_speaker(row, eligible, budget, cut=None, connections=aihub_connections):
    """영상 앞부분 → 라벨 → 자르기. 성공하면 메타 dict, 아니면 ValueError."""
    dest = RAW / row['spk']
    dest.mkdir(parents=True, exist_ok=True)
    try:
        s = open_stream(budget, row['video_file'], row['video_fileSn'], VIDEO_CAP, connections)
        try:
            person, sources = extract_front(s, eligible, dest)
        finally:
            s.close()
        log('VIDEO', row['spk'], row['video_file'], 'bytes', s.n, 'person', person, 'front', len(sources))
        if not sources:
            raise ValueError('no eligible complete front mp4')
        s = open_stream(budget, row['label_file'], row['label_fileSn'], LABEL_CAP, connections)
        try:
            labels = extract_labels(s, {p.with_suffix('.json').name for p in sources})
        finally:
            s.close()
        log('LABEL', row['spk'], row['label_file'], 'bytes', s.n, 'found', len(labels))
        if not labels:
            raise ValueError('matching label absent')
        first = next(iter(labels.values()))
        clips = cut(sources, labels, row, person, None) if cut else cut_clips(sources, labels, row, person, ffmpeg())
        if len(clips) < MIN_CLIPS:
            raise ValueError(f'too few clips {len(clips)}')
        info = first.get('speaker_info', {})
        return {'spk': row['spk'], 'person': person, 'label_file': row['label_file'], 'video_file': row['video_file'],
                'half': half_of(row['spk']), 'eval': is_eval(row['spk']), 'gender': info.get('Gender'), 'age': info.get('Age'),
                'specificity': info.get('Specificity'), 'accent': info.get('Accent'),
                'noise': (first.get('Audio_env') or {}).get('Noise'), 'sources': [p.name for p in sources], 'clips': clips}
    finally:
        shutil.rmtree(dest, ignore_errors=True)


def ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        exe = shutil.which('ffmpeg')
        if not exe:
            raise RuntimeError('ffmpeg not found (imageio_ffmpeg or PATH)')
        return exe


# ───────────────────────────── 상태·메타 ─────────────────────────────
def load_state():
    p = DATA / 'state.json'
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {'done': {}, 'failed': {}}


def save_state(st, **extra):
    st.update(extra, updated=now(), pid=os.getpid())
    (DATA / 'state.json').write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding='utf-8')


def write_manifests(st):
    """v2_avatar_validity select가 읽는 형식: manifest.tsv(clip.mp4, spk, 문장), manifest_meta.tsv(화자 한 줄, 11열)."""
    rows, meta = [], ['#spk\tlabel_file\tperson\tsex\tage\tspecificity\taccent\tvideo_file\tn_clips\thalf\tnoise']
    for spk, d in sorted(st['done'].items()):
        rows += [f"{c['clip']}.mp4\t{spk}\t{c['text']}" for c in d['clips']]
        meta.append('\t'.join(str(x) for x in (spk, d['label_file'], d['person'], d['gender'], d['age'], d['specificity'],
                                                d['accent'], d['video_file'], len(d['clips']), d['half'], d['noise'])))
    (DATA / 'manifest.tsv').write_text('\n'.join(sorted(rows)) + '\n', encoding='utf-8')
    (DATA / 'manifest_meta.tsv').write_text('\n'.join(meta) + '\n', encoding='utf-8')


def disk_ok():
    d = shutil.disk_usage('D:\\').free
    c = shutil.disk_usage('C:\\').free
    return d >= D_FREE_MIN and c >= VIDEO_CAP + 2 * 2**30, d, c


# ───────────────────────────── 실행 ─────────────────────────────
def run(queue, ex, target, retry_failed=False, fetch=fetch_speaker, yielder=None, connections=aihub_connections):
    st = load_state()
    budget = Budget(DATA / 'request-counts.json')
    persons = {d['person'] for d in st['done'].values()}
    eligible = lambda p: p not in ex and p not in persons
    yielder = yielder or Yielder()
    log('START queue', len(queue), 'done', len(st['done']), 'baseline_Bps', yielder.baseline)
    for row in queue:
        if len(st['done']) >= target:
            break
        if row['spk'] in st['done'] or (row['spk'] in st['failed'] and not retry_failed):
            continue
        if auth_stopped():
            raise AuthFailure('stop file present')
        ok, d, c = disk_ok()
        if not ok:
            save_state(st, status='disk_low', d_free=d, c_free=c)
            log('DISK_LOW D', d, 'C', c)
            return st
        save_state(st, status='running', current=row['spk'])
        try:
            d = fetch(row, eligible, budget, connections=connections)
            st['done'][row['spk']] = d
            st['failed'].pop(row['spk'], None)
            persons.add(d['person'])
            write_manifests(st)
            log('SPEAKER_DONE', row['spk'], d['person'], 'clips', len(d['clips']), 'done', len(st['done']))
        except AuthFailure:
            save_state(st, status='auth_stop', current=row['spk'])
            log('AUTH_STOP', row['spk'])
            raise
        except Exception as e:
            st['failed'][row['spk']] = {'error': str(e)[:300], 'time': now()}
            log('SPEAKER_FAIL', row['spk'], type(e).__name__, str(e)[:200])
        save_state(st, status='running', current=None)
        yielder.check()
    save_state(st, status='done', current=None)
    log('FETCH_DONE done', len(st['done']), 'failed', len(st['failed']))
    return st


def dry_run(queue, out=None):
    total = 0
    lines = ['#order\tspk\tvideo_file\tvideo_fileSn\tvideo_GB\tlabel_file\tlabel_fileSn\tlabel_GB\trequest_cap_GB\teval\thalf']
    for i, r in enumerate(queue):
        cap = min(VIDEO_CAP, r['video_bytes']) + min(LABEL_CAP, r['label_bytes'])
        total += cap
        lines.append(f"{i}\t{r['spk']}\t{r['video_file']}\t{r['video_fileSn']}\t{r['video_bytes'] / 2**30:.1f}\t{r['label_file']}\t"
                     f"{r['label_fileSn']}\t{r['label_bytes'] / 2**30:.2f}\t{cap / 2**30:.2f}\t{int(is_eval(r['spk']))}\t{half_of(r['spk'])}")
    text = '\n'.join(lines) + '\n'
    if out:
        Path(out).write_text(text, encoding='utf-8')
    print(text if not out else '\n'.join(lines[:11]))
    print(f'DRY_RUN batches={len(queue)} request_cap_GiB={total / 2**30:.1f} eval={sum(is_eval(r["spk"]) for r in queue)} '
          f'halves={[sum(half_of(r["spk"]) == h for r in queue) for h in (0, 1)]}')
    return total


def lock():
    p = DATA / 'fetch.lock'
    if p.exists():
        pid = int(p.read_text().strip() or 0)
        alive = subprocess.run(['tasklist', '/FI', f'PID eq {pid}', '/NH'], capture_output=True, text=True).stdout
        if str(pid) in alive:
            raise SystemExit(f'another train538_fetch is running (pid {pid})')
    p.write_text(str(os.getpid()))
    return p


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--out')
    ap.add_argument('--target', type=int, default=0, help='받을 화자 수(0 = 큐 전부)')
    ap.add_argument('--retry-failed', action='store_true', help='실패 화자에 파일당 남은 요청(최대 2회)을 쓴다')
    a = ap.parse_args(argv)
    ex, blocked, overlap = exclusions()
    queue = build_queue(filetree(), blocked, overlap)
    if a.dry_run:
        dry_run(queue, a.out)
        return
    DATA.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    E2.ROOT = DATA   # Stream의 헤더 임시 파일·AUTH_STOP·SLOW_STOP·transfers.jsonl을 train538 쪽에 둔다
    p = lock()
    try:
        run(queue, ex, a.target or len(queue), a.retry_failed)
    finally:
        p.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
