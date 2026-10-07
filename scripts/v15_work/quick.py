"""잔차 보정 시뮬레이션으로 표 변형을 빠르게 비교(탐색 절반)."""
import json, sys, pickle, copy
import numpy as np
sys.path.insert(0, '/tmp/v15sp/work')
sys.path.insert(0, '/Users/namyunsu/Downloads/liplab/.claude/worktrees/agent-add8fe1d30054f08d/scripts')
import v15_calibrate as C
import v2_avatar_validity as V
import calib4 as K
import calib5 as K5
from calib2 import load_items, G_LIST
sys.modules['__main__'].FM = C.FM
L = '/Users/namyunsu/Downloads/liplab-lab/data/'
fm = pickle.load(open('/tmp/v15sp/work/fm_v15.pkl', 'rb'))
hum = pickle.load(open('/tmp/v15sp/work/human_explore.pkl', 'rb'))
sel = json.load(open(L + 'v2_avatar/sel.json'))
RD = L + 'pod_runs/20261007_zszjqyqz5m03q2/v15/' + (sys.argv[4] if len(sys.argv) > 4 else 'ex_c')
base = {int(k): v for k, v in json.load(open(sys.argv[2] if len(sys.argv) > 2 else '/tmp/v15sp/work/tables_c.json'))[sys.argv[3] if len(sys.argv) > 3 else 'c'].items()}
Rres = K5.residual(fm, sel, base, RD)
extra = K5.seg_extra_sd(fm, sel, base, RD, Rres)
K.noisy_profiles = K5.make_noisy(extra)
sim = C.Sim(fm, load_items(sel, 0), resid=Rres)
ro = json.load(open('/tmp/v15sp/work/eval_old_ex.json'))['new']
rec_old = {sp: {int(g): v[0] for g, v in ro[f'default_{sp}']['distinct'].items()} for sp in (1.0, 2.0)}


def ev(tab, label):
    ds, prof, cond = K.dyn_stats(sim, tab)
    rsa, amp, leg = C.v2_metrics(hum['prof'], prof)
    d = {f'{sp}:{g}': round(ds[sp]['recall'][g][0] - rec_old[sp][g], 2) for sp in (1.0, 2.0) for g in G_LIST if ds[sp]['recall'][g][0] < rec_old[sp][g] - 0.05}
    print(label, 'rho1', rsa['cond']['default_1.0']['rho'], 'rho2', rsa['cond']['default_2.0']['rho'], 'amp2', amp['cond']['default_2.0']['n_in'],
          'leg', leg['default_1.0'].get('rounded_R_in_range_rate'), leg['default_2.0'].get('rounded_R_in_range_rate'),
          'dev', rsa['cond']['default_1.0']['pair_dev'][:4], 'def', d, flush=True)
    return rsa['cond']['default_1.0']['rho']


if __name__ == '__main__':
    ev(base, 'c')
    for variant in json.load(open(sys.argv[1])):
        t = copy.deepcopy(base)
        for g, sh in variant['set'].items():
            t[int(g)] = {**t[int(g)], **sh}
            t[int(g)] = {k: v for k, v in t[int(g)].items() if v > 0}
        ev(t, variant['name'])
