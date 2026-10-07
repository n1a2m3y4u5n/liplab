import json, sys, copy
import os
BP, BK = os.environ.get('BASE', '/tmp/v15sp/work/tables_c.json:c').split(':')
base = {int(k): v for k, v in json.load(open(BP))[BK].items()}
out = {}
for path in sys.argv[2:]:
    for var in json.load(open(path)):
        t = copy.deepcopy(base)
        for g, sh in var['set'].items():
            t[int(g)] = {k: v for k, v in {**t[int(g)], **sh}.items() if v > 0}
        # 9: 4와 2의 중간(0.6·4 + 0.4·2)
        s4, s2 = t[4], t[2]
        t[9] = {k: round(0.6 * s4.get(k, 0) + 0.4 * s2.get(k, 0), 2) for k in set(s4) | set(s2) if 0.6 * s4.get(k, 0) + 0.4 * s2.get(k, 0) >= 0.01}
        out[var['name']] = t
json.dump(out, open(sys.argv[1], 'w'), indent=0)
print('TABLES', list(out))
