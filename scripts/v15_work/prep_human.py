import json, os, sys, pickle, numpy as np
sys.path.insert(0, '/Users/namyunsu/Downloads/liplab/.claude/worktrees/agent-add8fe1d30054f08d/scripts')
import v15_calibrate as C
L = '/Users/namyunsu/Downloads/liplab-lab/data/'
R = L + 'pod_runs/20261006_oel3rwn7y5zjbv/v2_part2/out/'
sel = json.load(open(L + 'v2_avatar/sel.json'))
prof, rec, rate = C.human_profiles(sel, R + 'align_real.jsonl', R + 'bs_real', 0)
st = C.human_stats(prof, rec)
pickle.dump({'prof': prof, 'stats': st, 'rate': {s: float(np.median(v)) for s, v in rate.items()}}, open('/tmp/v15sp/work/human_explore.pkl', 'wb'))
print('speakers', len(prof))
for g in C.GROUPS:
    print(g, {k: round(v, 3) for k, v in st['amp'][g].items()})
print('floor_raw', {k: round(v, 4) for k, v in st['floor_raw'].items()})
