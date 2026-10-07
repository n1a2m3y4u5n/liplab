import json, sys, pickle
import numpy as np
sys.path.insert(0, '/tmp/v15sp/work')
sys.path.insert(0, '/Users/namyunsu/Downloads/liplab/.claude/worktrees/agent-add8fe1d30054f08d/scripts')
import v15_calibrate as C
import v2_avatar_validity as V
from calib2 import load_items
sys.modules['__main__'].FM = C.FM
L = '/Users/namyunsu/Downloads/liplab-lab/data/'
fm = pickle.load(open(sys.argv[1], 'rb'))
tab = {int(k): v for k, v in json.load(open(sys.argv[2]))[sys.argv[3]].items()}
rdir = sys.argv[4]
sel = json.load(open(L + 'v2_avatar/sel.json'))
real = C.render_records(sel, rdir + '/renders', rdir + '/bs', 0)
sids = {r['sid'] for r in real['default_1.0']}
items = [it for it in load_items(sel, 0) if it[0] in sids]
sim = C.Sim(fm, items)
prof, cond = sim.profiles(tab)
feats = list(V.RSA_FEATS) + ['G']
for sp in ('1.0', '2.0'):
    c = f'default_{sp}'
    def gm(recs):
        out = {}
        for g in C.GROUPS:
            X = np.array([[v[f] for f in feats] for r in recs for gg, v in r['segs'] if gg == g])
            out[g] = np.nanmean(X, 0)
        return out
    a, b = gm(cond[c]), gm(real[c])
    print('==', c, 'feature: r(sim group means, real group means) | mean abs diff | real sd across groups')
    for j, f in enumerate(feats):
        xs = np.array([a[g][j] for g in C.GROUPS]); ys = np.array([b[g][j] for g in C.GROUPS])
        print(f'  {f:16s} r={np.corrcoef(xs, ys)[0, 1]:.3f} mad={np.mean(np.abs(xs - ys)):.4f} sd_real={ys.std():.4f}  sim3={a[3][j]:.3f} real3={b[3][j]:.3f}')
    pr = V.profile(real[c]); ps = prof[c]
    print('  dist r(sim, real) =', round(float(np.corrcoef(V.dist_vec(ps), V.dist_vec(pr))[0, 1]), 3))
