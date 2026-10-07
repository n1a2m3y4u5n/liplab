"""V5: 가상 화자 매개변수를 탐색 절반 실제 화자 분포(10~90백분위) 안에서 다시 고른다."""
import json, sys, pickle
import numpy as np
sys.path.insert(0, '/tmp/v15sp/work')
sys.path.insert(0, '/Users/namyunsu/Downloads/liplab/.claude/worktrees/agent-add8fe1d30054f08d/scripts')
import v15_calibrate as C
import v2_avatar_validity as V
from calib2 import load_items
sys.modules['__main__'].FM = C.FM
L = '/Users/namyunsu/Downloads/liplab-lab/data/'
hum = pickle.load(open('/tmp/v15sp/work/human_explore.pkl', 'rb'))
prof, st = hum['prof'], hum['stats']
G = list(C.GROUPS)
scale = {c: [] for c in ('J', 'R', 'S')}
for s, p in prof.items():
    for c in ('J', 'R', 'S'):
        r = [p['amp'][g][c] / st['amp'][g][c] for g in G if g in p['amp'] and st['amp'][g][c] > 0.02]
        if r:
            scale[c].append(float(np.median(r)))
rates = np.array(list(hum['rate'].values()))
rate_scale = rates / np.median(rates)
qs = [10, 25, 50, 75, 90]
out = {'J': np.percentile(scale['J'], qs).round(3).tolist(), 'R': np.percentile(scale['R'], qs).round(3).tolist(),
       'S_n': len(scale['S']), 'rate': np.percentile(rate_scale, qs).round(3).tolist(), 'rate_median_sps': round(float(np.median(rates)), 2)}
print('HUMAN scale quantiles (10,25,50,75,90):', json.dumps(out))
# 모프 배율 → MediaPipe 진폭 배율(탐색 문장 2.0배 시뮬레이션, 무리 중앙값)
fm = pickle.load(open('/tmp/v15sp/work/fm_v15.pkl', 'rb'))
table = {int(k): v for k, v in json.load(open(sys.argv[1]))[sys.argv[2]].items()}
sel = json.load(open(L + 'v2_avatar/sel.json'))
items = load_items(sel, 0, speeds=(2.0,))[:60]
base_sim = C.Sim(fm, items)
pb, _ = base_sim.profiles(table)
p0 = pb['default_2.0']


def ratio(param, k):
    tk = dict(C.TALKERS['default']); tk[param] = k
    C.TALKERS['_probe'] = tk
    sim = C.Sim(fm, [(s, f, '_probe', sp) for s, f, _, sp in items])
    pp, _ = sim.profiles(table)
    p = pp['_probe_2.0']
    ch = {'amp': 'J', 'protrusion': 'R', 'width': 'S'}[param]
    r = [p['amp'][g][ch] / p0['amp'][g][ch] for g in G if g in p['amp'] and p0['amp'][g][ch] > 0.02]
    return float(np.median(r)) if r else float('nan')


curve = {}
for param in ('amp', 'protrusion', 'width'):
    curve[param] = [(k, round(ratio(param, k), 3)) for k in (0.6, 0.8, 0.9, 1.1, 1.25, 1.5)]
    print('CURVE', param, curve[param])
json.dump({'human': out, 'curve': curve}, open('/tmp/v15sp/work/v5_curves.json', 'w'), indent=1)
