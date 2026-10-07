"""동결: scripts/data/viseme_v15.json(표·가상 화자·리그 사상·출처)과 표의 sha256."""
import json, hashlib, sys
APP = '/Users/namyunsu/Downloads/liplab/.claude/worktrees/agent-add8fe1d30054f08d/'
tab = {str(k): v for k, v in json.load(open('/tmp/v15sp/work/tables_r3.json'))['D'].items()}
talk = json.load(open('/tmp/v15sp/work/talkers_shrunk_D.json'))
rig = json.load(open('/tmp/v15sp/work/rigmap_compact.json'))
canon = json.dumps(tab, sort_keys=True, separators=(',', ':'))
sha = hashlib.sha256(canon.encode()).hexdigest()
out = {
    'doc': 'docs/viseme-calibration-2026-10.md',
    'preregistration_commit': '2bf2291',
    'table_sha256_canonical': sha,
    'table_canonical_rule': 'json.dumps(table, sort_keys=True, separators=(",", ":")) of the table object below',
    'table': tab,
    'talkers_v15': [{k: t[k] for k in ('id', 'rate', 'amp', 'width', 'protrusion', 'coart')} for t in talk],
    'rig_map': rig,
    'explore_candidates': {},
}
for name, path in (('c', 'eval_c_ex.json'), ('C1', 'eval_C1_ex.json'), ('C2', 'eval_C2_ex.json'), ('D', 'eval_D_ex.json'), ('old', 'eval_old_ex.json')):
    d = json.load(open('/tmp/v15sp/work/' + path))
    row = {}
    for c in ('default_1.0', 'default_2.0'):
        n = d['new'][c]
        row[c] = {'rho': n['rho'], 'amp_n_in': n['amp_n_in'], 'bilabial': n['legibility'].get('bilabial_closure_rate'),
                  'rounded': n['legibility'].get('rounded_R_in_range_rate'), 'distinct': {g: v[0] for g, v in n['distinct'].items()}}
    row['verdict'] = d['verdict']
    out['explore_candidates'][name] = row
json.dump(out, open(APP + 'scripts/data/viseme_v15.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('SHA', sha)
