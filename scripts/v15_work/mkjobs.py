"""후보 표 렌더 작업: V2 작업(jobs_text.json)에서 절반·화자·속도를 골라 table 이름을 붙인다."""
import json, sys
L = '/Users/namyunsu/Downloads/liplab-lab/data/'
half = int(sys.argv[1]); table = sys.argv[2]; out = sys.argv[3]
talkers = sys.argv[4].split(',') if len(sys.argv) > 4 else ['default']
speeds = [float(x) for x in sys.argv[5].split(',')] if len(sys.argv) > 5 else [1.0, 2.0]
extra = sys.argv[6] if len(sys.argv) > 6 else ''
jobs = json.load(open(L + 'v2_avatar/jobs_text.json'))
if extra:
    jobs += json.load(open(L + 'v2_avatar/' + extra))
sel = json.load(open(L + 'v2_avatar/sel.json'))
want = set()
for e in sel['sentences']:
    if e['half'] == half:
        want.add((e['sid'], 'default' if e['default'] else None))
        if e['talkers']:
            want.add((e['sid'], 'talkers'))
res, seen = [], set()
for j in jobs:
    if j['id'] in seen or j['talker'] not in talkers or j['speed'] not in speeds:
        continue
    key = 'default' if j['talker'] == 'default' else 'talkers'
    if (j['sid'], key) not in want:
        continue
    seen.add(j['id'])
    j = dict(j)
    if table != '-':
        j['table'] = table
    res.append(j)
json.dump(res, open(out, 'w'))
print('JOBS', len(res))
