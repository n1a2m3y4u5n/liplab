"""영상 헤더 위치와 라벨만으로 미수신 계획을 다시 동결한다."""
import hashlib
import json
import re
import shutil
import tarfile
import zlib

from e2_retry_acquire import ROOT, REPO, EXHASH, Stream, JoinedParts


def request(record, cap, initial=0):
    path = ROOT / 'request-counts.json'
    counts = json.loads(path.read_text())
    name = record['video_file']
    prior = counts.get(name, initial)
    if prior >= 2:
        raise ValueError('request limit: ' + name)
    counts[name] = prior + 1
    path.write_text(json.dumps(counts, indent=2))
    return Stream(record, cap)


def front(record):
    stream = request(record, 2**20)
    try:
        with tarfile.open(fileobj=stream, mode='r|') as outer:
            with tarfile.open(fileobj=JoinedParts(outer), mode='r|') as inner:
                for member in inner:
                    if member.isfile() and member.name.endswith('.mp4'):
                        name = member.name.replace('\\', '/').rsplit('/', 1)[-1]
                        return name, member.offset, member.size
    finally:
        stream.close()
    raise ValueError('no front mp4 header')


def label(record, target, files):
    source = dict(record, video_file=record['label_file'], video_fileSn=files[record['label_file']][1])
    # 이전 조사에서 라벨을 한 번 요청한 것으로 보수적으로 계산한다.
    stream = request(source, 512 * 2**20, initial=1)
    try:
        with tarfile.open(fileobj=stream, mode='r|') as outer:
            with tarfile.open(fileobj=JoinedParts(outer), mode='r|') as inner:
                for member in inner:
                    if member.isfile() and member.name.replace('\\', '/').rsplit('/', 1)[-1] == target.replace('.mp4', '.json'):
                        data = json.load(inner.extractfile(member))
                        return data[0] if isinstance(data, list) else data
    finally:
        stream.close()
    raise ValueError('matching label absent')


def main():
    excluded = REPO / 'docs/e2-excluded-speakers-2026-10-27.txt'
    assert hashlib.sha256(excluded.read_bytes()).hexdigest() == EXHASH
    ex = set(excluded.read_text().splitlines())
    original = json.loads((ROOT / 'plan.json').read_text(encoding='utf-8'))
    done = {r['spk'] for r in json.loads((ROOT / 'manifest-meta.json').read_text(encoding='utf-8'))}
    plan = [r for r in original if r['spk'] in done]
    persons = {r['person'] for r in plan}
    halves = [sum(r['half'] == h for r in plan) for h in (0, 1)]
    files = {m[0]: (int(m[1].replace(',', '')) * {'MB': 2**20, 'GB': 2**30, 'KB': 1024, 'B': 1}[m[2]], m[3]) for m in re.findall(r'([TV][LS]\d+\.tar)\s*\|\s*([\d,]+)\s*(GB|MB|KB|B)\s*\|\s*(\d+)', (REPO / 'out/aihub538-filetree-retry.txt').read_text(encoding='utf-8'))}
    candidates = [dict(r) for r in original if r['spk'] not in done]
    seen = {r['spk'] for r in original}
    for name in sorted((n for n in files if n.startswith(('TL', 'VL'))), key=lambda n: files[n][0]):
        number = int(re.search(r'\d+', name)[0])
        spk = 'spk' + str(number + (296 if name.startswith('TL') else 600))
        if spk in seen or spk in ex:
            continue
        video = name.replace('TL', 'TS').replace('VL', 'VS')
        candidates.append({'spk': spk, 'half': zlib.crc32(spk.encode()) % 2, 'label_file': name, 'video_file': video, 'video_fileSn': files[video][1]})
    failures = []
    for record in candidates:
        if min(halves) >= 15:
            break
        if record['spk'] in ex or halves[record['half']] >= 15:
            continue
        try:
            target, offset, size = front(record)
            match = re.search(r'_([CE]\d+)_A_\d+\.mp4$', target)
            if not match or match[1] in ex or match[1] in persons:
                print('FRONT_SKIP', record['spk'], target, flush=True)
                continue
            data = label(record, target, files)
            assert data['speaker_info']['speaker_ID'] == match[1]
            assert data['Video_info']['video_Name'] == target
            row = {k: record[k] for k in ('spk', 'half', 'label_file', 'video_file', 'video_fileSn')}
            row.update({k: data[k] for k in ('Video_info', 'Sentence_info', 'speaker_info')})
            row.update(person=match[1], source_offset=offset, source_bytes=size, selection_basis='first MP4 tar header and matching label only')
            plan.append(row)
            (ROOT / 'front-plan-progress.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
            persons.add(match[1])
            halves[row['half']] += 1
            print('FRONT_SELECT', row['spk'], row['person'], halves, flush=True)
        except Exception as error:
            from e2_retry_acquire import AuthFailure
            if isinstance(error, AuthFailure):
                raise
            failures.append({'spk': record['spk'], 'error': str(error)[:200]})
            print('FRONT_ERROR', record['spk'], str(error)[:100], flush=True)
    (ROOT / 'front-plan-progress.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
    assert min(halves) >= 15, 'insufficient metadata candidates: ' + str(halves)
    shutil.copy2(ROOT / 'plan.json', ROOT / 'plan-before-front.json')
    shutil.copy2(ROOT / 'cohort-frozen.json', ROOT / 'cohort-frozen-before-front.json')
    (ROOT / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
    frozen = {'speakers': [{k: r[k] for k in ('spk', 'person', 'half')} for r in plan], 'halves': halves, 'plan_sha256': hashlib.sha256((ROOT / 'plan.json').read_bytes()).hexdigest(), 'excluded_sha256': EXHASH, 'rule_commit': '9922f006', 'selection_executed': False, 'confirmation_executed': False}
    (ROOT / 'cohort-frozen.json').write_text(json.dumps(frozen, ensure_ascii=False, indent=2), encoding='utf-8')
    (ROOT / 'front-plan-failures.json').write_text(json.dumps(failures, indent=2))
    print('FRONT_FROZEN', halves, frozen['plan_sha256'], flush=True)


if __name__ == '__main__':
    main()
