import json, sys
sys.path.insert(0, '/Users/namyunsu/Downloads/liplab/.claude/worktrees/agent-add8fe1d30054f08d/scripts')
import v15_calibrate as C
spec = json.load(open('/tmp/v15sp/work/rawmap_a.json'))['lin']
SYM = ['jawOpen', 'mouthClose', 'mouthFunnel', 'mouthPucker', 'mouthSmile', 'mouthStretch', 'mouthUpperUp', 'mouthLowerDown', 'mouthPress',
       'mouthRollLower', 'mouthRollUpper', 'mouthShrugLower', 'mouthShrugUpper']
PAIRED = ('mouthSmile', 'mouthStretch', 'mouthUpperUp', 'mouthLowerDown', 'mouthPress')
rows = {}
for k in C.CTRL:
    key = C.PAIRS[k][0] if k in C.PAIRS else k
    r = spec[key]
    co = [round(r.get(s + 'Left', 0) + r.get(s + 'Right', 0), 3) if s in PAIRED else round(r.get(s, 0), 3) for s in SYM]
    rows[k] = {'b': round(r['_b'], 3), 'w': co}
json.dump({'in': SYM, 'out': rows}, open('/tmp/v15sp/work/rigmap_compact.json', 'w'))
for k, v in rows.items():
    print(k, v)
