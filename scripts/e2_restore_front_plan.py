"""미달로 끝난 위치 조사에서 보존 가능한 라벨만 복구한다. 세 번째 요청은 금지한다."""
import hashlib
import json
import re
import shutil
import tarfile
import zlib

from e2_retry_acquire import ROOT, REPO, EXHASH, Stream, JoinedParts, AuthFailure


def main():
    original = json.loads((ROOT / 'plan.json').read_text(encoding='utf-8'))
    by_spk = {r['spk']: r for r in original}
    visited = set(json.loads((ROOT / 'original-label-requests.json').read_text()))
    done = {r['spk'] for r in json.loads((ROOT / 'manifest-meta.json').read_text(encoding='utf-8'))}
    plan = [r for r in original if r['spk'] in done]
    text = (REPO / 'out/e2-front-plan.log').read_text(encoding='utf-16')
    selected = re.findall(r'FRONT_SELECT (spk\d+) ([CE]\d+)', text)
    files = {m[0]: (int(m[1].replace(',', '')) * {'MB': 2**20, 'GB': 2**30, 'KB': 1024, 'B': 1}[m[2]], m[3]) for m in re.findall(r'([TV][LS]\d+\.tar)\s*\|\s*([\d,]+)\s*(GB|MB|KB|B)\s*\|\s*(\d+)', (REPO / 'out/aihub538-filetree-retry.txt').read_text(encoding='utf-8'))}
    counts_path = ROOT / 'request-counts.json'
    counts = json.loads(counts_path.read_text())
    corrections = []
    # 첫 조사 43회와 정확히 일치하는 재현 결과로 미요청 라벨의 보수적 가산 1만 취소한다.
    for name in list(counts):
        if name.startswith(('TL', 'VL')) and name not in visited and counts[name] == 2:
            corrections.append(name)
            counts[name] = 1
    counts_path.write_text(json.dumps(counts, indent=2))
    (ROOT / 'request-count-corrections.json').write_text(json.dumps({'original_survey_count': len(visited), 'removed_assumed_prior_request': corrections}, indent=2))
    cache = ROOT / 'front-label-cache'
    cache.mkdir(exist_ok=True)
    failures = []
    for spk, person in selected:
        row = by_spk.get(spk)
        try:
            if row and row['person'] == person:
                row = dict(row)
            else:
                number = int(spk[3:])
                label_name = ('VL' + str(number - 600) if number >= 600 else 'TL' + str(number - 296)) + '.tar'
                video_name = label_name.replace('VL', 'VS').replace('TL', 'TS')
                cached = cache / (spk + '.json')
                if cached.exists():
                    data = json.loads(cached.read_text(encoding='utf-8'))
                else:
                    if counts.get(label_name, 1 if label_name in visited else 0) >= 2:
                        raise ValueError('label already requested twice; missing durable metadata')
                    counts[label_name] = counts.get(label_name, 1 if label_name in visited else 0) + 1
                    counts_path.write_text(json.dumps(counts, indent=2))
                    source = {'spk': spk, 'video_file': label_name, 'video_fileSn': files[label_name][1]}
                    stream = Stream(source, files[label_name][0] + 2**20)
                    data = None
                    try:
                        with tarfile.open(fileobj=stream, mode='r|') as outer:
                            with tarfile.open(fileobj=JoinedParts(outer), mode='r|') as inner:
                                for member in inner:
                                    if member.isfile() and re.search('_' + person + r'_A_001\.json$', member.name):
                                        data = json.load(inner.extractfile(member))
                                        data = data[0] if isinstance(data, list) else data
                                        break
                    finally:
                        stream.close()
                    if data is None:
                        raise ValueError('matching A001 label not found')
                    cached.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
                assert data['speaker_info']['speaker_ID'] == person
                row = {'spk': spk, 'person': person, 'half': zlib.crc32(spk.encode()) % 2, 'label_file': label_name, 'video_file': video_name, 'video_fileSn': files[video_name][1]}
                row.update({k: data[k] for k in ('Video_info', 'Sentence_info', 'speaker_info')})
            row['front_only'] = True
            row['selection_basis'] = 'previous first A MP4 header and matching label; no deeper search'
            plan.append(row)
            (ROOT / 'front-plan-progress.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
            print('RESTORED', spk, person, flush=True)
        except AuthFailure:
            raise
        except Exception as error:
            failures.append({'spk': spk, 'person': person, 'error': str(error)})
            print('RESTORE_BLOCKED', spk, str(error), flush=True)
    shutil.copy2(ROOT / 'plan.json', ROOT / 'plan-before-front.json')
    shutil.copy2(ROOT / 'cohort-frozen.json', ROOT / 'cohort-frozen-before-front.json')
    (ROOT / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
    frozen = {'speakers': [{k: r[k] for k in ('spk', 'person', 'half')} for r in plan], 'halves': [sum(r['half'] == h for r in plan) for h in (0, 1)], 'plan_sha256': hashlib.sha256((ROOT / 'plan.json').read_bytes()).hexdigest(), 'excluded_sha256': EXHASH, 'rule_commit': '9922f006', 'selection_executed': False, 'confirmation_executed': False, 'minimum_not_met': True}
    (ROOT / 'cohort-frozen.json').write_text(json.dumps(frozen, ensure_ascii=False, indent=2), encoding='utf-8')
    (ROOT / 'front-restore-failures.json').write_text(json.dumps(failures, indent=2))
    print('RESTORE_FROZEN', len(plan), frozen['halves'], flush=True)


if __name__ == '__main__':
    main()
