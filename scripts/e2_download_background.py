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
    status = 'done' if min(halves) >= 15 and not error and not missing else 'blocked'
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
        f"최소 15/15명까지 {max(0, 15 - halves[0])}/{max(0, 15 - halves[1])}명 부족; 남은 받기는 듣기 개편 뒤. 탐색·확인 판정 미실행.\n"
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--wait-pid', type=int)
    parser.add_argument('--wait-log', type=Path, default=REPO / 'out/e2-acquire-front.log')
    parser.add_argument('--deep-budget-gib', type=float, default=0)
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
            result = subprocess.run([sys.executable, '-u', str(REPO / 'scripts/e2_retry_acquire.py')], cwd=REPO, env=env, stdout=target, stderr=target)
            if result.returncode:
                error = 'acquirer exit ' + str(result.returncode)
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
