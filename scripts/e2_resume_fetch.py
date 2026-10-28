"""538 절반 1: 이어받기(curl -C -)로 영상 tar를 C:에 받아 정면 A만 꺼내고 tar를 지운다(10/28 사용자 승인).

서버가 한 연결을 5~10GB에서 끊어(curl 18) 앞부분 흘려 읽기로는 깊은 정면 A에 닿지 못했다.
규칙: tar는 한 번에 하나, tar당 이어받기 요청 최대 15회, 401/403/429/502는 즉시 전체 중단(AUTH_STOP),
이어받기에 206이 아니면 그 tar는 멈춤, C: 여유 200GB 아래면 멈춤, 정면 A가 얕을 것으로 보이는 화자부터.
"""
import hashlib, json, msvcrt, os, re, shutil, subprocess, sys, tempfile, time, zlib
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from e2_retry_acquire import ROOT, REPO, KEY, AuthFailure, extract_target

RAW = Path(r'C:\liplab-raw\e2_538')
MAX_REQ = 15
MIN_FREE = 200 * 2**30
COUNTS = ROOT / 'resume-request-counts.json'


def log(line):
    with (ROOT / 'download.log').open('a', encoding='utf-8') as f:
        f.write(line + '\n')
    print(line, flush=True)


def state(**values):
    values['updated'] = datetime.now().isoformat(timespec='seconds')
    (ROOT / 'downloader-state.json').write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding='utf-8')


def halves():
    done = {r['spk'] for r in json.loads((ROOT / 'manifest-meta.json').read_text(encoding='utf-8'))}
    return done, [sum(zlib.crc32(s.encode()) % 2 == h for s in done) for h in (0, 1)]


def expected_depth(record, lines):
    """앞선 흘려 읽기에서 닿은 마지막 인물·위치로 정면 A 깊이를 어림한다(순서 정하기에만 쓴다)."""
    best = None
    for line in lines:
        m = re.match(r"STREAM " + record['spk'] + r" (\d+) last \{'name': '([^']+)', 'offset': (\d+)", line)
        if m and (not best or int(m[3]) > best[0]):   # 가장 깊이 닿은 기록
            best = (int(m[3]), m[2])
    if not best:
        return float('inf')
    offset, name = best
    seen = re.search(r'_([CE])(\d+)_', name)
    want = re.match(r'([CE])(\d+)', record['person'])
    if seen and want and seen[1] == want[1] and int(seen[2]) > 0:
        return offset * max(1.0, int(want[2]) / int(seen[2]))
    return offset * 2


def request(record, tmp, n):
    """이어받기 요청 1회. 받은 바이트와 HTTP 코드를 transfers.jsonl에 남긴다."""
    before = tmp.stat().st_size if tmp.exists() else 0
    fd, header = tempfile.mkstemp(dir=ROOT, suffix='.header'); os.close(fd)
    response, err = header + '.response', header + '.curlerr'
    key = KEY.read_text(encoding='utf-8-sig').strip()
    if not key or len(key.splitlines()) != 1:
        raise ValueError('single key required')
    Path(header).write_text('apikey:' + key, encoding='utf-8'); del key
    t = time.time()
    try:
        with open(err, 'wb') as ef:
            rc = subprocess.run(['curl.exe', '-sS', '-L', '-f', '-C', '-', '--connect-timeout', '30', '--max-time', '3600',
                                 '-H', '@' + header, '-D', response, '-o', str(tmp),
                                 'https://api.aihub.or.kr/down/0.6/538.do?fileSn=' + record['video_fileSn']],
                                stdout=subprocess.DEVNULL, stderr=ef).returncode
        codes = re.findall(r'HTTP/\S+\s+(\d+)', Path(response).read_text(errors='replace')) if Path(response).exists() else []
        message = Path(err).read_text(errors='replace').strip()[:200] if Path(err).exists() else ''
    finally:
        for p in (header, response, err):
            Path(p).unlink(missing_ok=True)
    after = tmp.stat().st_size if tmp.exists() else 0
    seconds = round(time.time() - t, 3)
    with (ROOT / 'transfers.jsonl').open('a') as f:
        f.write(json.dumps({'file': record['video_file'], 'mode': 'resume', 'request': n, 'start_byte': before,
                            'bytes': after - before, 'seconds': seconds, 'http': codes, 'curl_rc': rc, 'curl_err': message}) + '\n')
    if any(c in ('401', '403', '429', '502') for c in codes):
        (ROOT / 'AUTH_STOP').write_text('Authentication/account HTTP response during resume: do not retry.')
        raise AuthFailure('account response ' + ','.join(codes))
    if before == 0 and after < 2**20 and tmp.exists() and ('인증실패'.encode() in tmp.read_bytes() or '인증실패'.encode('cp949') in tmp.read_bytes()):
        (ROOT / 'AUTH_STOP').write_text('Authentication failure: do not retry.')
        raise AuthFailure('authentication failed')
    if seconds > 180 and (after - before) / seconds < 512 * 1024:
        (ROOT / 'SLOW_STOP').write_text(time.strftime('%Y-%m-%dT%H:%M:%S') + ' ' + record['video_file'] + ' resume')
        raise AuthFailure('server too slow; stopped')
    return before, after, codes, rc


def fetch(record, size):
    """정면 A를 꺼내면 그 경로, 못 꺼내면 None."""
    RAW.mkdir(parents=True, exist_ok=True)
    tmp = RAW / record['video_file']
    target = record['Video_info']['video_Name']
    dest = ROOT / 'source.mp4'
    counts = json.loads(COUNTS.read_text()) if COUNTS.exists() else {}
    try:
        while counts.get(record['video_file'], 0) < MAX_REQ:
            if (ROOT / 'AUTH_STOP').exists():
                raise AuthFailure('authentication stop')
            if shutil.disk_usage('C:\\').free < MIN_FREE:
                log('RESUME_DISK_STOP C: free < 200GB')
                raise AuthFailure('disk low; stopped')
            n = counts.get(record['video_file'], 0) + 1
            counts[record['video_file']] = n
            COUNTS.write_text(json.dumps(counts, indent=2))
            before, after, codes, rc = request(record, tmp, n)
            log(f'RESUME_REQ {record["spk"]} {record["video_file"]} n={n} {before}->{after} http={codes} rc={rc}')
            if before > 0 and after > before and (not codes or codes[-1] != '206'):
                log(f'RESUME_NO_206 {record["video_file"]} http={codes}: stop this tar')
                return None
            if rc == 33:   # 서버가 이어받기를 받지 않음
                log(f'RESUME_NO_RANGE {record["video_file"]}: stop this tar')
                return None
            with tmp.open('rb') as f:
                source, last = extract_target(f, target, dest)
            log(f'RESUME_SCAN {record["spk"]} found={bool(source)} last={last}')
            if source:
                return source
            if rc == 0 or after >= size:
                log(f'RESUME_TAR_END {record["video_file"]}: front A absent')
                return None
        log(f'RESUME_EXHAUSTED {record["spk"]} {record["video_file"]}')
        return None
    finally:
        tmp.unlink(missing_ok=True)   # 정면 A를 꺼냈든 못 했든 tar는 지운다


def main():
    lock = (ROOT / 'downloader.lock').open('a+b')
    lock.seek(0)
    if not lock.read(1):
        lock.write(b'1'); lock.flush()
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        return
    files = {m[0]: int(m[1].replace(',', '')) * {'MB': 2**20, 'GB': 2**30, 'KB': 1024, 'B': 1}[m[2]] for m in re.findall(r'([TV][LS]\d+\.tar)\s*\|\s*([\d,]+)\s*(GB|MB|KB|B)\s*\|\s*(\d+)', (REPO / 'out/aihub538-filetree-retry.txt').read_text(encoding='utf-8'))}
    log('\nRESUME_FETCH_START ' + datetime.now().isoformat(timespec='seconds'))
    state(status='running', mode='resume', log=str(ROOT / 'download.log'))
    error = None
    try:
        lines = (ROOT / 'download.log').read_text(encoding='utf-8').splitlines()
        tried = set()
        while True:
            done, hv = halves()
            if hv[1] >= 20:
                break
            plan = json.loads((ROOT / 'plan.json').read_text(encoding='utf-8'))
            counts = json.loads(COUNTS.read_text()) if COUNTS.exists() else {}
            pool = [r for r in plan if r['half'] == 1 and r['spk'] not in done and r['spk'] not in tried and 'Video_info' in r
                    and r['video_file'] in files and counts.get(r['video_file'], 0) < MAX_REQ]
            if not pool:
                break
            record = min(pool, key=lambda r: expected_depth(r, lines))
            tried.add(record['spk'])
            log(f'RESUME_TRY {record["spk"]} {record["person"]} {record["video_file"]} est={expected_depth(record, lines):.0f} halves={hv}')
            source = fetch(record, files[record['video_file']])
            if not source:
                continue
            record['resume_source'] = str(source)
            (ROOT / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
            frozen = json.loads((ROOT / 'cohort-frozen.json').read_text(encoding='utf-8'))
            frozen['plan_sha256'] = hashlib.sha256((ROOT / 'plan.json').read_bytes()).hexdigest()
            (ROOT / 'cohort-frozen.json').write_text(json.dumps(frozen, ensure_ascii=False, indent=2), encoding='utf-8')
            env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1', E2_ONLY_SPK=record['spk'])
            with (ROOT / 'download.log').open('a', encoding='utf-8') as target:
                result = subprocess.run([sys.executable, '-u', str(REPO / 'scripts/e2_retry_acquire.py')], cwd=REPO, env=env, stdout=target, stderr=target)
            if result.returncode:
                raise RuntimeError('cut exit ' + str(result.returncode))
        done, hv = halves()
        log(f'RESUME_FETCH_COMPLETE halves={hv}' + ('' if hv[1] >= 15 else ' (half 1 < 15: E2 보류)'))
    except Exception as e:
        error = type(e).__name__ + ': ' + str(e)[:200]
        log('RESUME_FETCH_STOP ' + error)
    done, hv = halves()
    state(status='blocked' if error or hv[1] < 15 else 'done', mode='resume', halves=hv, error=error, log=str(ROOT / 'download.log'))


if __name__ == '__main__':
    main()
