"""Offline only: inspect existing 538 headers, request ledgers and measured speed."""
import ast
import csv
import hashlib
import json
import re
import statistics
from pathlib import Path
from clean_eval_audit import DATA, OUT, REPO
from train538_fetch import filetree, batch_spk, half_of


def main():
    audit = json.loads((OUT / 'audit.json').read_text(encoding='utf-8'))
    with (OUT / 'person-usage.csv').open(encoding='utf-8-sig') as f:
        excluded = {r['person'] for r in csv.DictReader(f)}
    with (OUT / 'batch-budget.csv').open(encoding='utf-8-sig') as f:
        budgets = {r['spk']: r for r in csv.DictReader(f)}
    rates = []
    source_hashes = []
    for root in ('train538', 'e2_538'):
        p = DATA / root / 'transfers.jsonl'
        source_hashes.append({'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()})
        for line in p.read_text(encoding='utf-8').splitlines():
            r = json.loads(line)
            if r.get('seconds', 0) >= 60 and r.get('bytes', 0) >= 100 * 2**20:
                rates.append(r['bytes'] / r['seconds'] / 1e6)
    median = statistics.median(rates)
    observations = {}
    for root in ('e2_538',):
        p = DATA / root / 'download.log'
        source_hashes.append({'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()})
        for line in p.read_text(encoding='utf-8', errors='replace').splitlines():
            m = re.search(r'STREAM (spk\d+) \d+ last (\{.*\})', line)
            if not m:
                continue
            r = ast.literal_eval(m[2])
            n = re.search(r'_([CE]\d+)_([A-Z])_\d+\.mp4$', r['name'])
            if not n or n[2] != 'A':
                continue
            key = (m[1], n[1])
            if key not in observations or r['offset'] < observations[key]['offset']:
                observations[key] = r
    rows = []
    for (spk, person), r in sorted(observations.items()):
        b = budgets[spk]
        need = (r['offset'] + r['size']) / 1e9
        rows.append({'spk': spk, 'half': half_of(spk), 'observed_person': person,
                     'known_use': person in excluded, 'front_offset_GB': round(r['offset']/1e9, 4),
                     'observed_one_file_end_GB': round(need, 4),
                     'time_to_one_file_min_at_median': round(need*1000/median/60, 2),
                     'label': b['label'], 'video': b['video'],
                     'label_requests_lower_bound': b['label_requests_lower_bound'],
                     'video_requests_lower_bound': b['video_requests_lower_bound'],
                     'video_requests_remaining_normal_cap2': max(0, 2-int(b['video_requests_lower_bound'])),
                     'identity_grade': 'observed filename; training non-use unproved',
                     'label_order_is_video_order': 'not established; historical mismatch',
                     'minimum_15_clips_proved': False})
    with (OUT/'observed-front-costs.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    files = filetree()
    # All 251 batches: theoretical later-person request costs; not a certified cohort.
    deep = []
    for label, (size, sn) in files.items():
        if not label.startswith(('TL','VL')):
            continue
        spk=batch_spk(label); b=budgets[spk]
        deep.append({**b, 'later_person': 'unknown', 'later_person_video_offset': 'unknown',
                     'label_fileSn': sn, 'video_fileSn': files[b['video']][1],
                     'label_stream_upper_GB': round(size/1e9,3),
                     'video_tar_total_GB': round(files[b['video']][0]/1e9,3),
                     'additional_label_request_if_uncached': 1,
                     'additional_video_requests_if_single_connection_reaches': 1,
                     'extra_requests_authorized': False,
                     'remaining_after_hypothetical_label_request': max(0,1-int(b['label_requests_lower_bound'])),
                     'remaining_after_hypothetical_video_request': max(0,1-int(b['video_requests_lower_bound'])),
                     'later_person_coverage': 'not certified'})
    with (OUT/'deep-batch-costs.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(deep[0]));w.writeheader();w.writerows(deep)
    exclusion_audit=Path(r'D:\work\hq\projects\liplab\out\e2-exclusion-audit.json')
    ea=json.loads(exclusion_audit.read_text(encoding='utf-8'))
    summary={'network_requests':0,'eligible_certified_new_persons':0,
             'observed_front_persons':len(rows),
             'observed_not_in_known_person_exclusions':sum(not r['known_use'] for r in rows),
             'measured_transfer_samples':len(rates),'measured_median_MB_s':median,
             'measured_quartiles_MB_s':statistics.quantiles(rates,n=4),
             'frozen_exclusion_origin_rule':ea['rule'],
             'frozen_exclusion_is_R2_training_manifest':False,
             'frozen_exclusion_source_files':len(ea['sources']),
             'frozen_exclusion_person_ids':sum(bool(re.fullmatch('[CE]\\d+',s)) for s in (REPO/'docs/e2-excluded-speakers-2026-10-27.txt').read_text().splitlines()),
             'sources':source_hashes,
             'remaining_first_person_batches':audit['remaining_first_person_batches']}
    (OUT/'feasibility.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k not in ('sources','remaining_first_person_batches')},ensure_ascii=False))


if __name__=='__main__':
    main()
