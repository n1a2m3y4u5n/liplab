"""Read-only provenance inventory; never interprets missing provenance as unused."""
import csv
import hashlib
import json
import re
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DATA = Path(r'D:\work\hq\projects\liplab-lab\data')
OUT = Path(r'D:\work\hq\projects\liplab\out\cleaneval-2026-11-02')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    people, mapping, evidence = {}, {}, []

    def read(path):
        raw = path.read_bytes()
        evidence.append({'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest()})
        return json.loads(raw.decode('utf-8-sig'))

    def add(person, spk, use):
        if not re.fullmatch(r'[CE]\d+', person or ''):
            return
        p = people.setdefault(person, {'spk': set(), 'uses': set()})
        if spk:
            p['spk'].add(spk)
            mapping.setdefault(spk, set()).add(person)
        p['uses'].add(use)

    st = read(DATA / 'train538/state.json')
    split = read(DATA / 'train538/v1prep/split.json')
    for spk, row in st['done'].items():
        role = next((r for r in ('train', 'val', 'eval') if spk in split[r]), 'unknown')
        add(row['person'], spk, 'train538_received')
        add(row['person'], spk, 'V1_538_' + role)
        add(row['person'], spk, 'B33_K1_K2_' + role)
        add(row['person'], spk, 'V3_538_' + ('confirm' if zlib.crc32(spk.encode()) % 2 else 'explore'))

    for name, use in [('cohort-acquired.json', 'E2_acquired'), ('plan.json', 'E2_plan')]:
        for row in read(DATA / 'e2_538' / name):
            add(row.get('person'), row.get('spk'), use)
    for row in read(DATA / 'roi_judge_2026-10-21/parity/_dump_summary.json'):
        clip = row['clip']
        m = re.search(r'_([CE]\d+)_', clip)
        if m:
            # A parity fixture proves use, not membership of the complete training set.
            add(m[1], clip.split('_')[0], 'R2_parity_fixture_seen')

    frozen = REPO / 'docs/e2-excluded-speakers-2026-10-27.txt'
    raw = frozen.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == 'a826028983d56eab1a3d9017ee647dc875854fdfb607bdb4ed3beccf9f2a233f'
    evidence.append({'path': str(frozen), 'sha256': hashlib.sha256(raw).hexdigest()})
    old_excluded = set(raw.decode('utf-8').splitlines())
    for person in old_excluded:
        add(person, None, 'old_frozen_exclusion_use_unspecified')

    eval40 = {s.strip() for s in (REPO / 'scripts/lipread_v1/eval40.txt').read_text(encoding='utf-8').splitlines()
              if s.strip() and not s.startswith('#')}
    old_v3 = set(('spk345 spk353 spk375 spk380 spk383 spk407 spk409 spk410 spk411 spk412 '
                  'spk471 spk473 spk502 spk507 spk508 spk509 spk511 spk607 spk613').split())
    unresolved = []
    for use, speakers in [('old_eval40', eval40), ('old_V3_confirm', old_v3),
                          ('TL1_4', {'spk297', 'spk298', 'spk299', 'spk300'})]:
        for spk in sorted(speakers):
            if spk not in mapping:
                unresolved.append({'spk': spk, 'use': use, 'person': 'unknown'})
            for person in mapping.get(spk, set()):
                add(person, spk, use + '_batch_link_only')

    with (OUT / 'person-usage.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['person', 'known_batches', 'observed_uses', 'R2_full_training_membership',
                    'old_V1_full_membership', 'old_V3_full_membership', 'eligible'])
        for person, row in sorted(people.items()):
            w.writerow([person, ';'.join(sorted(row['spk'])), ';'.join(sorted(row['uses'])),
                        'unknown', 'unknown', 'unknown', 'no: used or unresolved provenance'])
    budgets = {}
    for root in ('train538', 'e2_538'):
        for p in sorted((DATA / root).glob('*request*.json')):
            budgets[str(p)] = read(p)
    # E2 request-counts already incorporates original survey and its corrections.
    # Amend/resume have independent ledgers. Also compare transfers as a lower bound.
    totals = {}
    for root, name, nested in [('train538', 'request-counts.json', False),
                                ('e2_538', 'request-counts.json', False),
                                ('e2_538', 'amend-request-counts.json', True),
                                ('e2_538', 'resume-request-counts.json', False)]:
        d = budgets[str(DATA / root / name)]
        if nested:
            d = d['files']
        for file, n in d.items():
            totals[file] = totals.get(file, 0) + n
    transfer_counts = {}
    for root in ('train538', 'e2_538'):
        p = DATA / root / 'transfers.jsonl'
        evidence.append({'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()})
        for line in p.read_text(encoding='utf-8').splitlines():
            r = json.loads(line)
            file = r.get('file')
            if file:
                transfer_counts[file] = transfer_counts.get(file, 0) + 1
    blocked = old_excluded | eval40 | old_v3 | set(st['done']) | {'spk297', 'spk298', 'spk299', 'spk300'}
    blocked |= {r['spk'] for r in read(DATA / 'e2_538/plan.json')}
    from train538_fetch import filetree, batch_spk, half_of
    pairs = []
    for label in filetree():
        if not label.startswith(('TL', 'VL')):
            continue
        spk = batch_spk(label)
        video = label.replace('TL', 'TS').replace('VL', 'VS')
        used = {f: max(totals.get(f, 0), transfer_counts.get(f, 0)) for f in (label, video)}
        reason = 'prior-use batch exclusion' if spk in blocked else ('request budget exhausted' if max(used.values()) >= 2 else 'metadata survey possible; person not certified')
        pairs.append({'spk': spk, 'half': half_of(spk), 'label': label, 'video': video,
                      'label_requests_lower_bound': used[label], 'video_requests_lower_bound': used[video], 'reason': reason})
    with (OUT / 'batch-budget.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(pairs[0]))
        w.writeheader()
        w.writerows(pairs)
    remaining = [r for r in pairs if r['reason'].startswith('metadata')]
    result = {'status': 'blocked', 'known_persons': len(people), 'train538_persons': len(st['done']),
              'unresolved_batches': unresolved, 'sources': evidence,
              'request_ledgers_raw': budgets,
              'budget_note': 'Original survey/corrections already incorporated in E2 counts; independent train/amend/resume added; max with transfers is conservative lower bound. No special E2 per-file extension is reused.',
              'remaining_first_person_batches': remaining,
              'missing': ['R2 pretrain/train/val complete person manifest', 'old V1 full person manifest',
                          'old V3 full person manifest', 'complete batch/person map'],
              'new_download_requests': 0, 'new_person_inference': 0, 'sealed_bundle': False}
    (OUT / 'audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('status', 'known_persons', 'train538_persons', 'sealed_bundle')}))


if __name__ == '__main__':
    main()
