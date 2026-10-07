"""V13 왕복 r(V2 6.3절 그대로): 원래 실제 계수 대 렌더 재측정. 절반 선택, 두 렌더 폴더 비교."""
import json, os, sys
import numpy as np
sys.path.insert(0, '/Users/namyunsu/Downloads/liplab/.claude/worktrees/agent-add8fe1d30054f08d/scripts')
import v2_avatar_validity as V
L = '/Users/namyunsu/Downloads/liplab-lab/data/'
R = L + 'pod_runs/20261006_oel3rwn7y5zjbv/v2_part2/out/bs_real/'
half = int(sys.argv[1]); dirs = sys.argv[2:]
sel = json.load(open(L + 'v2_avatar/sel.json'))
hs = {s['spk']: s['half'] for s in sel['speakers']}
cs = {c['clip']: c['spk'] for c in sel['clips']}
clips = [c for c in sel['v13_clips'] if hs[cs[c]] == half]
for d in dirs:
    per = {c: [] for c in V.V13_CH}; gain = {c: [] for c in V.V13_CH}
    n = 0
    for clip in clips:
        po, pr = R + clip + '.json', os.path.join(d, f'v13_{clip}.json')
        if not (os.path.exists(po) and os.path.exists(pr)):
            continue
        so, sr = V.load_series(po), V.load_series(pr)
        Ln = min(len(so['t']), len(sr['t'])); n += 1
        for c in V.V13_CH:
            x, y = so['f'][c][:Ln], sr['f'][c][:Ln]
            m = np.isfinite(x) & np.isfinite(y)
            if m.sum() < V.MIN_FRAMES or np.std(x[m]) < 1e-6 or np.std(y[m]) < 1e-6:
                continue
            per[c].append(float(np.corrcoef(x[m], y[m])[0, 1]))
            gain[c].append(float(np.polyfit(x[m], y[m], 1)[0]))
    print(d.split('/')[-2] + '/' + d.split('/')[-1], 'clips', n, ' '.join(f'{c}: r {np.median(per[c]):.3f} [{np.percentile(per[c], 25):.3f},{np.percentile(per[c], 75):.3f}] gain {np.median(gain[c]):.2f}' for c in V.V13_CH))
