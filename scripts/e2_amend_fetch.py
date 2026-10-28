"""538 절반 1 개정 등록(docs/e2-amend-2026-10-28.md): 영상 tar 앞 4GiB 안의 첫 비제외 인물 정면 A를 그 배치의 화자로 삼는다.

배치마다 영상 요청 1회(앞 4GiB, 첫 정면 A를 꺼내면 바로 끊는다) + 라벨 요청 1회. 전체 최대 18요청·45GB.
절반 1이 15명이 되면 바로 멈춘다. 401/403/429/502는 즉시 전체 중단(AUTH_STOP), 느리면 SLOW_STOP.
"""
import hashlib, json, msvcrt, os, re, shutil, subprocess, sys, tarfile, zlib
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from e2_retry_acquire import ROOT, REPO, EXHASH, AuthFailure, Stream, JoinedParts

ORDER = ['spk298', 'spk397', 'spk610', 'spk605', 'spk604', 'spk625', 'spk498',
         'spk458', 'spk451', 'spk500', 'spk450', 'spk299', 'spk388', 'spk300']   # 등록 순서(기록상 정면 A가 얕은 배치부터)
CAP = 4 * 2**30
MAX_REQUESTS = 18
MAX_BYTES = 45 * 10**9
TARGET = 15
COUNTS = ROOT / 'amend-request-counts.json'
BASIS = 'amend 2026-10-28: first non-excluded front A mp4 within the first 4GiB of the video tar'


def log(line):
    with (ROOT / 'download.log').open('a', encoding='utf-8') as f:
        f.write(line + '\n')
    print(line, flush=True)


def state(**values):
    values['updated'] = datetime.now().isoformat(timespec='seconds')
    (ROOT / 'downloader-state.json').write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding='utf-8')


def budget():
    counts = json.loads(COUNTS.read_text()) if COUNTS.exists() else {'files': {}, 'requests': 0, 'bytes': 0}
    return counts


def stream(counts, record, file, sn, cap):
    """요청 1회. 파일당 1회, 전체 18회를 넘기지 않는다."""
    if counts['files'].get(file, 0) >= 1 or counts['requests'] >= MAX_REQUESTS:
        raise ValueError('amend request limit: ' + file)
    counts['files'][file] = counts['files'].get(file, 0) + 1
    counts['requests'] += 1
    COUNTS.write_text(json.dumps(counts, indent=2))
    return Stream(dict(record, video_file=file, video_fileSn=sn), cap)


def charge(counts, s):
    counts['bytes'] += s.n
    COUNTS.write_text(json.dumps(counts, indent=2))


def first_front(s, skip, dest):
    """앞에서부터 처음 나오는, 제외되지 않은 인물의 정면 A mp4를 완결로 꺼낸다."""
    try:
        with tarfile.open(fileobj=s, mode='r|') as outer:
            with tarfile.open(fileobj=JoinedParts(outer), mode='r|') as inner:
                for m in inner:
                    name = Path(m.name.replace('\\', '/')).name
                    hit = m.isfile() and re.search(r'_([CE]\d+)_A_\d+\.mp4$', name)
                    if not hit or hit[1] in skip:
                        continue
                    tmp = dest.with_suffix('.partial')
                    try:
                        with tmp.open('wb') as f:
                            shutil.copyfileobj(inner.extractfile(m), f, 1024 * 1024)
                        if tmp.stat().st_size != m.size:   # 4GiB 경계에서 잘림: 이 배치는 기준에 닿지 못했다
                            log(f'AMEND_CUT {name} offset={m.offset}')
                            return None
                        tmp.replace(dest)
                        return name, hit[1], m.offset
                    finally:
                        tmp.unlink(missing_ok=True)
    except (tarfile.ReadError, EOFError) as error:
        log('AMEND_TAR_STOP ' + type(error).__name__ + ' ' + str(error)[:120])
    return None


def label(s, target):
    want = target.replace('.mp4', '.json')
    try:
        with tarfile.open(fileobj=s, mode='r|') as outer:
            with tarfile.open(fileobj=JoinedParts(outer), mode='r|') as inner:
                for m in inner:
                    if m.isfile() and Path(m.name.replace('\\', '/')).name == want:
                        data = json.load(inner.extractfile(m))
                        return data[0] if isinstance(data, list) else data
    except (tarfile.ReadError, EOFError) as error:
        log('AMEND_LABEL_STOP ' + type(error).__name__ + ' ' + str(error)[:120])
    return None


def halves():
    done = {r['spk'] for r in json.loads((ROOT / 'manifest-meta.json').read_text(encoding='utf-8'))}
    return done, [sum(zlib.crc32(s.encode()) % 2 == h for s in done) for h in (0, 1)]


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
    excluded = REPO / 'docs/e2-excluded-speakers-2026-10-27.txt'
    assert hashlib.sha256(excluded.read_bytes()).hexdigest() == EXHASH
    ex = set(excluded.read_text().splitlines())
    tree = (REPO / 'out/aihub538-filetree-retry.txt').read_text(encoding='utf-8')
    files = {m[0]: (int(m[1].replace(',', '')) * {'MB': 2**20, 'GB': 2**30, 'KB': 1024, 'B': 1}[m[2]], m[3]) for m in re.findall(r'([TV][LS]\d+\.tar)\s*\|\s*([\d,]+)\s*(GB|MB|KB|B)\s*\|\s*(\d+)', tree)}
    if not (ROOT / 'plan-before-amend.json').exists():
        shutil.copy2(ROOT / 'plan.json', ROOT / 'plan-before-amend.json')
    log('\nAMEND_FETCH_START ' + datetime.now().isoformat(timespec='seconds'))
    state(status='running', mode='amend', log=str(ROOT / 'download.log'))
    error = None
    results = json.loads((ROOT / 'amend-results.json').read_text()) if (ROOT / 'amend-results.json').exists() else []
    try:
        for spk in ORDER:
            done, hv = halves()
            if hv[1] >= TARGET:
                break
            if (ROOT / 'AUTH_STOP').exists() or (ROOT / 'SLOW_STOP').exists():
                raise AuthFailure('stop file present')
            if spk in done or any(r['spk'] == spk for r in results):
                continue
            counts = budget()
            if counts['requests'] + 2 > MAX_REQUESTS or counts['bytes'] + CAP + 2**30 > MAX_BYTES:
                log(f'AMEND_BUDGET_END requests={counts["requests"]} bytes={counts["bytes"]}')
                break
            plan = json.loads((ROOT / 'plan.json').read_text(encoding='utf-8'))
            record = next(r for r in plan if r['spk'] == spk)
            assert spk not in ex and record['half'] == zlib.crc32(spk.encode()) % 2 == 1
            meta = json.loads((ROOT / 'manifest-meta.json').read_text(encoding='utf-8'))
            skip = ex | {m['person'] for m in meta}
            dest = ROOT / f'amend-source-{spk}.mp4'
            log(f'AMEND_TRY {spk} {record["video_file"]} halves={hv} requests={counts["requests"]}')
            s = stream(counts, record, record['video_file'], files[record['video_file']][1], CAP)
            try:
                found = first_front(s, skip, dest)
            finally:
                s.close(); charge(counts, s)
            log(f'AMEND_VIDEO {spk} found={found} bytes={s.n}')
            if not found:
                results.append({'spk': spk, 'result': 'no front A within 4GiB', 'bytes': s.n})
                (ROOT / 'amend-results.json').write_text(json.dumps(results, indent=2))
                continue
            target, person, offset = found
            s = stream(counts, record, record['label_file'], files[record['label_file']][1], files[record['label_file']][0] + 2**20)
            try:
                data = label(s, target)
            finally:
                s.close(); charge(counts, s)
            if not data or data['speaker_info']['speaker_ID'] != person or data['Video_info']['video_Name'] != target:
                dest.unlink(missing_ok=True)
                log(f'AMEND_LABEL_ABSENT {spk} {target}')
                results.append({'spk': spk, 'person': person, 'video': target, 'result': 'front A label absent'})
                (ROOT / 'amend-results.json').write_text(json.dumps(results, indent=2))
                continue
            row = {k: record[k] for k in ('spk', 'half', 'label_file', 'video_file', 'video_fileSn')}
            row.update({k: data[k] for k in ('Video_info', 'Sentence_info', 'speaker_info')})
            row.update(person=person, selection_basis=BASIS, amend_offset=offset, resume_source=str(dest))
            plan = [row if r['spk'] == spk else r for r in plan]
            (ROOT / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
            frozen = json.loads((ROOT / 'cohort-frozen.json').read_text(encoding='utf-8'))
            frozen['plan_sha256'] = hashlib.sha256((ROOT / 'plan.json').read_bytes()).hexdigest()
            frozen['amend_rule'] = 'docs/e2-amend-2026-10-28.md'
            (ROOT / 'cohort-frozen.json').write_text(json.dumps(frozen, ensure_ascii=False, indent=2), encoding='utf-8')
            env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1', E2_ONLY_SPK=spk)
            with (ROOT / 'download.log').open('a', encoding='utf-8') as out:
                rc = subprocess.run([sys.executable, '-u', str(REPO / 'scripts/e2_retry_acquire.py')], cwd=REPO, env=env, stdout=out, stderr=out).returncode
            dest.unlink(missing_ok=True)
            done, hv = halves()
            results.append({'spk': spk, 'person': person, 'video': target, 'offset': offset, 'result': 'acquired' if spk in done else 'cut failed', 'rc': rc})
            (ROOT / 'amend-results.json').write_text(json.dumps(results, indent=2))
            log(f'AMEND_DONE {spk} {person} acquired={spk in done} halves={hv}')
        done, hv = halves()
        log(f'AMEND_FETCH_COMPLETE halves={hv} requests={budget()["requests"]} bytes={budget()["bytes"]}')
    except Exception as e:
        error = type(e).__name__ + ': ' + str(e)[:200]
        log('AMEND_FETCH_STOP ' + error)
    done, hv = halves()
    state(status='blocked' if error or hv[1] < TARGET else 'done', mode='amend', halves=hv, error=error, log=str(ROOT / 'download.log'))


if __name__ == '__main__':
    main()
