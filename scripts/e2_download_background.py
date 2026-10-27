"""동결 계획의 수신을 재개하고, 사람 감시 없이 로그와 종료 보고를 남긴다.

완료 화자는 manifest에서 이어받고 요청 횟수는 디스크에 보존한다.
파일당 총 2회 상한과 AUTH_STOP을 유지한다. 별도 탐색·평가는 실행하지 않는다.
"""
import argparse
import ctypes
from datetime import datetime
import json
import msvcrt
import os
import re
from pathlib import Path
import subprocess
import sys
import time

from e2_retry_acquire import ROOT, REPO, EXHASH
OUTBOX = Path(r'D:\work\hq\outbox')


def state(**values):
    values.update(pid=os.getpid(), updated=datetime.now().isoformat(timespec='seconds'))
    (ROOT / 'downloader-state.json').write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding='utf-8')


def wait_existing(pid, previous_log, log):
    """이미 수신 중인 프로세스와 겹쳐 요청하지 않는다."""
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    if previous_log.exists():
        log.write_text(previous_log.read_text(encoding='utf-16', errors='replace'), encoding='utf-8')
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x100000, False, pid)
    if not handle:
        if ctypes.get_last_error() == 87:  # 이미 종료됨
            return
        raise OSError(ctypes.get_last_error(), 'cannot safely wait for existing downloader')
    try:
        while True:
            if previous_log.exists():
                log.write_text(previous_log.read_text(encoding='utf-16', errors='replace'), encoding='utf-8')
            result = kernel.WaitForSingleObject(handle, 3000)
            if result == 0:
                if previous_log.exists():
                    log.write_text(previous_log.read_text(encoding='utf-16', errors='replace'), encoding='utf-8')
                return
            if result != 258:
                raise OSError('waiting for existing downloader failed')
    finally:
        kernel.CloseHandle(handle)


def write_report(error, started, log):
    manifest = ROOT / 'manifest.tsv'
    rows = [line.split('\t', 2) for line in manifest.read_text(encoding='utf-8').splitlines()] if manifest.exists() else []
    import zlib
    speakers = {row[1] for row in rows}
    halves = [sum(zlib.crc32(s.encode()) % 2 == h for s in speakers) for h in (0, 1)]
    media = [path for row in rows for path in (ROOT / 'clips' / row[0], (ROOT / 'clips' / row[0]).with_suffix('.wav'))]
    media_bytes = sum(path.stat().st_size for path in media if path.exists())
    failures_path = ROOT / 'acquire-failures.json'
    failures = json.loads(failures_path.read_text(encoding='utf-8')) if failures_path.exists() else []
    plan = json.loads((ROOT / 'plan.json').read_text(encoding='utf-8'))
    names = {r['spk']: r['video_file'] for r in plan}
    for failure in failures:
        failure['file'] = names.get(failure['spk'], failure.get('file', 'unknown'))
    failed_names = sorted({r['file'] for r in failures if r['spk'] in names})
    missing = sorted(set(names) - speakers)
    status = 'done' if min(halves) >= 20 and not error else 'blocked'
    transfers = [json.loads(line) for line in (ROOT / 'transfers.jsonl').read_text(encoding='utf-8').splitlines()]
    audit = json.loads((ROOT / 'audit.json').read_text(encoding='utf-8')) if (ROOT / 'audit.json').exists() else {}
    download_bytes = audit.get('consumed_download_bytes', sum(t['bytes'] for t in transfers))
    seconds = audit.get('download_seconds', sum(t['seconds'] for t in transfers))
    body = (
        f"status: {status}\ntask: 538 E2 동결 계획의 백그라운드 수신\n"
        f"outputs: {ROOT}; {log}; {REPO / 'out/e2-data-2026-10-27.md'}\n---\n"
        f"화자 {len(speakers)}명, 클립 {len(rows)}개, 절반별 {halves[0]}/{halves[1]}명; 저장 {media_bytes / 1e9:.6f} GB.\n"
        f"누적 수신 최소 {download_bytes / 1e9:.6f} GB, 기록 수신시간 최소 {seconds:.1f}초; 중단 요청의 일부 계측 누락으로 하한값.\n"
        f"실패 파일: {', '.join(failed_names) or '없음'}; 미수신 계획 화자: {', '.join(missing) or '없음'}; 실행 오류: {error or '없음'}.\n"
        f"최소 15/15명까지 {max(0, 15 - halves[0])}/{max(0, 15 - halves[1])}명 부족; 대체 화자는 같은 규칙으로 남은 요청 1회에 tar 끝까지 읽어 계속 받는다. 탐색·확인 판정 미실행.\n"
        f"시작 {started}; 종료 {datetime.now().isoformat(timespec='seconds')}.\n"
    )
    outbox = OUTBOX / (datetime.now().strftime('%Y%m%d-%H%M') + '-liplab-538-download.md')
    outbox.write_text(body, encoding='utf-8')
    report = REPO / 'out/e2-data-2026-10-27.md'
    with report.open('a', encoding='utf-8') as target:
        target.write('\n\n## 백그라운드 수신 종료 — ' + datetime.now().strftime('%Y-%m-%d %H:%M KST') + '\n\n' + body)
    state(status=status, report=str(outbox), speakers=len(speakers), clips=len(rows), halves=halves, failures=failures, error=error, log=str(log))


def extend_known_plan(budget_gib, target, env):
    """추가 라벨 요청 없이 원래 동결된 메타데이터의 알려진 인물만 제한 수신한다."""
    import hashlib
    import zlib
    budget_path = ROOT / 'deep-budget-state.json'
    if not budget_path.exists():
        count = len((ROOT / 'transfers.jsonl').read_text(encoding='utf-8').splitlines())
        budget_path.write_text(json.dumps({'start_transfer_index': count, 'max_bytes': int(budget_gib * 2**30)}))
    budget = json.loads(budget_path.read_text())
    original = json.loads((ROOT / 'plan-before-front.json').read_text(encoding='utf-8'))
    log_text = (REPO / 'out/e2-front-plan.log').read_text(encoding='utf-16')
    headers = dict(re.findall(r'FRONT_SKIP (spk\d+) (\S+\.mp4)', log_text))
    excluded = REPO / 'docs/e2-excluded-speakers-2026-10-27.txt'
    assert hashlib.sha256(excluded.read_bytes()).hexdigest() == EXHASH
    ex = set(excluded.read_text().splitlines())
    for row in original:
        if (ROOT / 'AUTH_STOP').exists():
            return
        done = {r['spk'] for r in json.loads((ROOT / 'manifest-meta.json').read_text(encoding='utf-8'))}
        halves = [sum(zlib.crc32(s.encode()) % 2 == h for s in done) for h in (0, 1)]
        if min(halves) >= 15:
            return
        plan = json.loads((ROOT / 'plan.json').read_text(encoding='utf-8'))
        if len(plan) >= 40:
            return
        if row['spk'] in {r['spk'] for r in plan} or row['person'] in {r['person'] for r in plan} or halves[row['half']] >= 15:
            continue
        match = re.search(r'_([CE]\d+)_[A-Z]_\d+\.mp4$', headers.get(row['spk'], ''))
        counts = json.loads((ROOT / 'request-counts.json').read_text())
        if not match or match[1] != row['person'] or row['spk'] in ex or row['person'] in ex or counts.get(row['video_file'], 0) != 1:
            continue
        transfers = [json.loads(line) for line in (ROOT / 'transfers.jsonl').read_text(encoding='utf-8').splitlines()][budget['start_transfer_index']:]
        used = sum(r['bytes'] for r in transfers if r.get('file', '').startswith(('TS', 'VS')))
        remaining = budget['max_bytes'] - used
        if remaining < 2**20:
            return
        candidate = dict(row, front_only=False, source_cap=min(4 * 2**30, remaining), selection_basis='original frozen label and known first-header person; bounded deeper prefix')
        plan.append(candidate)
        (ROOT / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
        frozen = {'speakers': [{k: r[k] for k in ('spk', 'person', 'half')} for r in plan], 'plan_sha256': hashlib.sha256((ROOT / 'plan.json').read_bytes()).hexdigest(), 'excluded_sha256': EXHASH, 'rule_commit': '9922f006', 'deep_budget': budget, 'selection_executed': False, 'confirmation_executed': False}
        (ROOT / 'cohort-frozen.json').write_text(json.dumps(frozen, ensure_ascii=False, indent=2), encoding='utf-8')
        target.write('BACKGROUND_DEEP_PLAN ' + row['spk'] + ' cap=' + str(candidate['source_cap']) + '\n')
        target.flush()
        result = subprocess.run([sys.executable, '-u', str(REPO / 'scripts/e2_retry_acquire.py')], cwd=REPO, env=env, stdout=target, stderr=target)
        if result.returncode:
            raise RuntimeError('bounded acquirer exit ' + str(result.returncode))
    target.write('BACKGROUND_DEEP_COMPLETE: no further eligible frozen metadata/header pairs within request limits\n')
    target.flush()



def front_label(record, person, files):
    """라벨 tar에서 그 인물의 첫 정면 A 라벨을 찾는다(첫 MP4가 다른 각도였던 화자용)."""
    import tarfile
    from e2_front_plan import request
    from e2_retry_acquire import JoinedParts
    source = dict(record, video_file=record['label_file'], video_fileSn=files[record['label_file']][1])
    # 라벨 tar는 500~900MB라 512MiB에서 끊으면 못 찾는다. tar 전체 크기까지 읽는다.
    stream = request(source, files[record['label_file']][0] + 2**20, initial=0)
    try:
        with tarfile.open(fileobj=stream, mode='r|') as outer:
            with tarfile.open(fileobj=JoinedParts(outer), mode='r|') as inner:
                for member in inner:
                    name = member.name.replace('\\', '/').rsplit('/', 1)[-1]
                    if member.isfile() and re.search(r'_' + person + r'_A_\d+\.json$', name):
                        data = json.load(inner.extractfile(member))
                        return data[0] if isinstance(data, list) else data
    finally:
        stream.close()
    raise ValueError('front A label absent: ' + person)


def extend_skipped_deep(budget_gib, target, env):
    """첫 MP4가 다른 각도라 건너뛴 화자를 모자란 절반부터 깊게 받는다. 선정 규칙은 같고 받는 순서만 바꾼다."""
    import hashlib
    import zlib
    from e2_retry_acquire import AuthFailure
    excluded = REPO / 'docs/e2-excluded-speakers-2026-10-27.txt'
    assert hashlib.sha256(excluded.read_bytes()).hexdigest() == EXHASH
    ex = set(excluded.read_text().splitlines())
    files = {m[0]: (int(m[1].replace(',', '')) * {'MB': 2**20, 'GB': 2**30, 'KB': 1024, 'B': 1}[m[2]], m[3]) for m in re.findall(r'([TV][LS]\d+\.tar)\s*\|\s*([\d,]+)\s*(GB|MB|KB|B)\s*\|\s*(\d+)', (REPO / 'out/aihub538-filetree-retry.txt').read_text(encoding='utf-8'))}
    skipped, tar = {}, None   # spk → (첫 MP4 이름, 영상 tar): NEXT_TAR 바로 뒤의 NEXT_SKIP만 짝짓는다
    for line in (ROOT / 'download.log').read_text(encoding='utf-8').splitlines():
        m = re.match(r'NEXT_TAR (\S+\.tar)', line)
        if m:
            tar = m[1]
            continue
        m = re.match(r'NEXT_SKIP (spk\d+) (\S+\.mp4)$', line)
        if m and tar:
            skipped[m[1]] = (m[2], tar)
        tar = None
    start = len((ROOT / 'transfers.jsonl').read_text(encoding='utf-8').splitlines())
    while True:
        if (ROOT / 'AUTH_STOP').exists():
            raise AuthFailure('authentication stop')
        meta = json.loads((ROOT / 'manifest-meta.json').read_text(encoding='utf-8'))
        done = {r['spk'] for r in meta}
        halves = [sum(zlib.crc32(s.encode()) % 2 == h for s in done) for h in (0, 1)]
        if min(halves) >= 20:
            break
        transfers = [json.loads(line) for line in (ROOT / 'transfers.jsonl').read_text(encoding='utf-8').splitlines()][start:]
        if sum(r.get('bytes', 0) for r in transfers) >= budget_gib * 2**30:
            target.write('SKIPPED_DEEP_BUDGET_END\n'); target.flush()
            break
        plan = json.loads((ROOT / 'plan.json').read_text(encoding='utf-8'))
        persons = {r['person'] for r in plan} | {r['person'] for r in meta}
        counts = json.loads((ROOT / 'request-counts.json').read_text())
        pick = None
        for half in sorted((0, 1), key=lambda h: halves[h]):   # 모자란 절반부터
            if halves[half] >= 20:
                continue
            for spk, (filename, video_file) in sorted(skipped.items()):
                m = re.search(r'_([CE]\d+)_[A-Z]_\d+\.mp4$', filename)
                label_file = video_file.replace('TS', 'TL').replace('VS', 'VL')
                if (zlib.crc32(spk.encode()) % 2 != half or not m or spk in done or spk in ex or m[1] in ex or m[1] in persons
                        or counts.get(video_file, 0) >= (3 if half == 1 else 2) or counts.get(label_file, 0) >= 2 or video_file not in files or label_file not in files):
                    continue
                pick = (spk, m[1], half, video_file, label_file)
                break
            if pick:
                break
        if not pick:
            target.write('SKIPPED_DEEP_COMPLETE halves=' + str(halves) + '\n'); target.flush()
            break
        spk, person, half, video_file, label_file = pick
        record = dict(spk=spk, half=half, label_file=label_file, video_file=video_file, video_fileSn=files[video_file][1])
        target.write('SKIPPED_DEEP_TRY ' + spk + ' ' + person + ' half=' + str(half) + ' halves=' + str(halves) + '\n'); target.flush()
        try:
            data = front_label(record, person, files)
        except AuthFailure:
            raise
        except Exception as error:
            target.write('SKIPPED_DEEP_NOLABEL ' + spk + ' ' + str(error)[:120] + '\n'); target.flush()
            skipped.pop(spk, None)
            continue
        assert data['speaker_info']['speaker_ID'] == person
        record.update({k: data[k] for k in ('Video_info', 'Sentence_info', 'speaker_info')})
        # 10/27 승인: 절반 1 영상 tar만 정상 응답에서 깊게 읽는 3번째 요청을 연다(1명당 4GiB).
        record.update(person=person, front_only=False, source_cap=4 * 2**30, max_requests=3 if half == 1 else 2, selection_basis='skipped first header; same frozen rule, half-first order; bounded deeper prefix')
        plan = [r for r in plan if r['spk'] != spk] + [record]
        (ROOT / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
        frozen = dict(speakers=[{k: r[k] for k in ('spk', 'person', 'half')} for r in plan], plan_sha256=hashlib.sha256((ROOT / 'plan.json').read_bytes()).hexdigest(), excluded_sha256=EXHASH, rule_commit='9922f006', selection_executed=False, confirmation_executed=False)
        (ROOT / 'cohort-frozen.json').write_text(json.dumps(frozen, ensure_ascii=False, indent=2), encoding='utf-8')
        skipped.pop(spk, None)
        result = subprocess.run([sys.executable, '-u', str(REPO / 'scripts/e2_retry_acquire.py')], cwd=REPO, env=env, stdout=target, stderr=target)
        if result.returncode:
            raise RuntimeError('skipped-deep acquirer exit ' + str(result.returncode))


def extend_retry_deep(each_gib, budget_gib, target, env):
    """10/27 승인: 4GiB에서 정면 영상을 못 찾은 절반 1 화자를 1명당 12GiB로 한 번 더 받는다(요청 1회 추가)."""
    import zlib
    from e2_retry_acquire import AuthFailure
    failures = json.loads((ROOT / 'acquire-failures.json').read_text())
    tried = [f['spk'] for f in failures if 'bounded requests exhausted' in f['error']]
    start = len((ROOT / 'transfers.jsonl').read_text(encoding='utf-8').splitlines())
    for spk in tried:
        if (ROOT / 'AUTH_STOP').exists():
            raise AuthFailure('authentication stop')
        done = {r['spk'] for r in json.loads((ROOT / 'manifest-meta.json').read_text(encoding='utf-8'))}
        halves = [sum(zlib.crc32(s.encode()) % 2 == h for s in done) for h in (0, 1)]
        if halves[1] >= 20:
            break
        transfers = [json.loads(line) for line in (ROOT / 'transfers.jsonl').read_text(encoding='utf-8').splitlines()][start:]
        if sum(r.get('bytes', 0) for r in transfers) + each_gib * 2**30 > budget_gib * 2**30:
            target.write('RETRY_DEEP_BUDGET_END\n'); target.flush()
            break
        plan = json.loads((ROOT / 'plan.json').read_text(encoding='utf-8'))
        record = next((r for r in plan if r['spk'] == spk), None)
        counts = json.loads((ROOT / 'request-counts.json').read_text())
        if spk in done or not record or record['half'] != 1 or record.get('deep_retry'):
            continue
        target.write('RETRY_DEEP_TRY ' + spk + ' ' + record['person'] + ' halves=' + str(halves) + '\n'); target.flush()
        record.update(front_only=False, source_cap=int(each_gib * 2**30), max_requests=counts.get(record['video_file'], 0) + 1, deep_retry=True)
        (ROOT / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
        frozen = json.loads((ROOT / 'cohort-frozen.json').read_text(encoding='utf-8'))
        import hashlib
        frozen['plan_sha256'] = hashlib.sha256((ROOT / 'plan.json').read_bytes()).hexdigest()
        (ROOT / 'cohort-frozen.json').write_text(json.dumps(frozen, ensure_ascii=False, indent=2), encoding='utf-8')
        result = subprocess.run([sys.executable, '-u', str(REPO / 'scripts/e2_retry_acquire.py')], cwd=REPO, env=env, stdout=target, stderr=target)
        if (ROOT / 'AUTH_STOP').exists():
            raise AuthFailure('authentication stop')
        if result.returncode:
            raise RuntimeError('retry-deep acquirer exit ' + str(result.returncode))
    target.write('RETRY_DEEP_COMPLETE\n'); target.flush()


def extend_next_tars(target, env):
    """?? ?? ? ??(?? ??): ?? tar ??/?? ??? ???? ??."""
    import hashlib
    import zlib
    from e2_front_plan import front, label
    from e2_retry_acquire import AuthFailure
    excluded = REPO / 'docs/e2-excluded-speakers-2026-10-27.txt'
    assert hashlib.sha256(excluded.read_bytes()).hexdigest() == EXHASH
    ex = set(excluded.read_text().splitlines())
    assert len(ex) == 249
    files = {m[0]: (int(m[1].replace(',', '')) * {'MB': 2**20, 'GB': 2**30, 'KB': 1024, 'B': 1}[m[2]], m[3]) for m in re.findall(r'([TV][LS]\d+\.tar)\s*\|\s*([\d,]+)\s*(GB|MB|KB|B)\s*\|\s*(\d+)', (REPO / 'out/aihub538-filetree-retry.txt').read_text(encoding='utf-8'))}
    for name in sorted((n for n in files if n.startswith(('TL', 'VL'))), key=lambda n: (files[n][0], n)):
        if (ROOT / 'AUTH_STOP').exists():
            raise AuthFailure('authentication stop')
        meta = json.loads((ROOT / 'manifest-meta.json').read_text(encoding='utf-8'))
        done = {r['spk'] for r in meta}
        halves = [sum(zlib.crc32(s.encode()) % 2 == h for s in done) for h in (0, 1)]
        if min(halves) >= 20:
            break
        number = int(re.search(r'\d+', name)[0])
        spk = 'spk' + str(number + (296 if name.startswith('TL') else 600))
        half = zlib.crc32(spk.encode()) % 2
        video = name.replace('TL', 'TS').replace('VL', 'VS')
        counts = json.loads((ROOT / 'request-counts.json').read_text())
        if spk in done or spk in ex or halves[half] >= 20 or counts.get(video, 0) >= 2:
            continue
        record = dict(spk=spk, half=half, label_file=name, video_file=video, video_fileSn=files[video][1])
        target.write('NEXT_TAR ' + video + ' halves=' + str(halves) + '\n'); target.flush()
        try:
            # A failed header request gets at most one retry, shared with acquisition.
            while True:
                try:
                    filename, offset, size = front(record)
                    break
                except AuthFailure:
                    raise
                except Exception:
                    if json.loads((ROOT / 'request-counts.json').read_text()).get(video, 0) >= 2:
                        raise
            match = re.search(r'_([CE]\d+)_A_\d+\.mp4$', filename)
            if not match or match[1] in ex or match[1] in {r['person'] for r in meta}:
                target.write('NEXT_SKIP ' + spk + ' ' + filename + '\n'); target.flush()
                continue
            while True:
                try:
                    data = label(record, filename, files, initial=0)
                    break
                except AuthFailure:
                    raise
                except Exception:
                    if json.loads((ROOT / 'request-counts.json').read_text()).get(name, 0) >= 2:
                        raise
            assert data['speaker_info']['speaker_ID'] == match[1]
            assert data['Video_info']['video_Name'] == filename
            record.update({k: data[k] for k in ('Video_info', 'Sentence_info', 'speaker_info')})
            record.update(person=match[1], source_offset=offset, source_bytes=size, selection_basis='?? ?? ? ??(?? ??): first MP4 header and matching label')
            plan = json.loads((ROOT / 'plan.json').read_text(encoding='utf-8'))
            plan = [r for r in plan if r['spk'] != spk]
            plan.append(record)
            (ROOT / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
            frozen = dict(speakers=[{k:r[k] for k in ('spk','person','half')} for r in plan], plan_sha256=hashlib.sha256((ROOT / 'plan.json').read_bytes()).hexdigest(), excluded_sha256=EXHASH, rule_commit='9922f006', selection_executed=False, confirmation_executed=False)
            (ROOT / 'cohort-frozen.json').write_text(json.dumps(frozen, ensure_ascii=False, indent=2), encoding='utf-8')
            target.write('NEXT_PLAN ' + spk + ' ' + match[1] + '\n'); target.flush()
            result = subprocess.run([sys.executable, '-u', str(REPO / 'scripts/e2_retry_acquire.py')], cwd=REPO, env=env, stdout=target, stderr=target)
            if (ROOT / 'AUTH_STOP').exists():
                raise AuthFailure('authentication stop')
            if result.returncode:
                raise RuntimeError('acquirer exit ' + str(result.returncode))
        except AuthFailure:
            raise
        except Exception as error:
            with (ROOT / 'next-tar-failures.jsonl').open('a', encoding='utf-8') as failures:
                failures.write(json.dumps(dict(file=video, label=name, spk=spk, error=str(error)[:300]), ensure_ascii=False) + '\n')
            target.write('NEXT_ERROR ' + video + ' ' + str(error)[:200] + '\n'); target.flush()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--wait-pid', type=int)
    parser.add_argument('--wait-log', type=Path, default=REPO / 'out/e2-acquire-front.log')
    parser.add_argument('--deep-budget-gib', type=float, default=0)
    # 주면 이 단계만 돈다(앞 단계를 다시 돌면 건너뛴 tar의 남은 요청 1회를 헤더 재요청에 써 버린다).
    parser.add_argument('--skipped-deep-gib', type=float, default=0)
    parser.add_argument('--retry-deep-each-gib', type=float, default=0)
    parser.add_argument('--retry-deep-budget-gib', type=float, default=80)
    args = parser.parse_args()
    started = datetime.now().isoformat(timespec='seconds')
    lock = (ROOT / 'downloader.lock').open('a+b')
    lock.seek(0)
    if not lock.read(1):
        lock.write(b'1')
        lock.flush()
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        return  # 다른 백그라운드 실행이 이미 담당 중이다.
    log = ROOT / 'download.log'
    error = None
    state(status='running', waiting_for_pid=args.wait_pid, log=str(log), started=started)
    try:
        if args.wait_pid:
            wait_existing(args.wait_pid, args.wait_log, log)
        env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
        with log.open('a', encoding='utf-8', buffering=1) as target:
            target.write('\nBACKGROUND_RESUME ' + datetime.now().isoformat(timespec='seconds') + '\n')
            if args.retry_deep_each_gib > 0:
                extend_retry_deep(args.retry_deep_each_gib, args.retry_deep_budget_gib, target, env)
                return
            if args.skipped_deep_gib > 0:
                extend_skipped_deep(args.skipped_deep_gib, target, env)
                return
            result = subprocess.run([sys.executable, '-u', str(REPO / 'scripts/e2_retry_acquire.py')], cwd=REPO, env=env, stdout=target, stderr=target)
            if result.returncode:
                error = 'acquirer exit ' + str(result.returncode)
            if not error:
                extend_next_tars(target, env)
            if not error and args.deep_budget_gib > 0:
                extend_known_plan(args.deep_budget_gib, target, env)
    except Exception as exception:
        error = type(exception).__name__ + ': ' + str(exception)
    finally:
        try:
            env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
            with log.open('a', encoding='utf-8') as target:
                checked = subprocess.run([sys.executable, str(REPO / 'scripts/e2_data_audit.py')], cwd=REPO, env=env, stdout=target, stderr=target)
            if checked.returncode:
                error = (error + '; ' if error else '') + 'media audit failed'
        except Exception as audit_error:
            error = (error + '; ' if error else '') + str(audit_error)
        write_report(error, started, log)
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        lock.close()


if __name__ == '__main__':
    main()
