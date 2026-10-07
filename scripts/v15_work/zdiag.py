import json, sys, pickle
import numpy as np
sys.path.insert(0, '/tmp/v15sp/work')
sys.path.insert(0, '/Users/namyunsu/Downloads/liplab/.claude/worktrees/agent-add8fe1d30054f08d/scripts')
import v15_calibrate as C
import v2_avatar_validity as V
from calib2 import load_items
from calib4 import noisy_profiles
sys.modules['__main__'].FM = C.FM
L = '/Users/namyunsu/Downloads/liplab-lab/data/'
fm = pickle.load(open('/tmp/v15sp/work/fm_v15.pkl', 'rb'))
hum = pickle.load(open('/tmp/v15sp/work/human_explore.pkl', 'rb'))
sel = json.load(open(L + 'v2_avatar/sel.json'))
sim = C.Sim(fm, load_items(sel, 0, speeds=(1.0,)))
G = list(C.GROUPS)
zh = np.array([np.mean([p['z'][g] for p in hum['prof'].values() if p and g in p['z']], axis=0) for g in G])
ref = np.array([v for v in (V.dist_vec(p) for p in hum['prof'].values()) if v is not None]).mean(0)
for name, tab in [('old', C.OLD_TABLE)] + [(a, {int(k): v for k, v in json.load(open(a)).get('table', {}).items()}) for a in sys.argv[1:] if a.endswith('.json') and 'tables' not in a] + \
        [(a + ':' + k, {int(kk): vv for kk, vv in t.items()}) for a in sys.argv[1:] if 'tables' in a for k, t in json.load(open(a)).items()]:
    for noisy in (False, True):
        prof, cond = noisy_profiles(sim, tab) if noisy else sim.profiles(tab)
        p = prof['default_1.0']
        za = np.array([p['z'][g] for g in G])
        rho = V.spearman(V.dist_vec(p), ref)
        print(f'== {name} noisy={noisy} rho={rho:.3f} zm={np.mean((za - zh) ** 2):.3f}')
        if noisy:
            continue
        for j, f in enumerate(V.RSA_FEATS):
            print(f'   {f[:10]:10s} r={np.corrcoef(za[:, j], zh[:, j])[0, 1]:+.2f}  av: ' + ' '.join(f'{x:+.1f}' for x in za[:, j]) + '  | hu: ' + ' '.join(f'{x:+.1f}' for x in zh[:, j]))
