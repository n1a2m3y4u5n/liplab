"""정지 구간(1.0배, 150ms 이상 구간의 뒤쪽 절반) 안 프레임 흔들림 = 재측정 잡음 추정."""
import json, sys, os
import numpy as np
sys.path.insert(0, '/Users/namyunsu/Downloads/liplab/.claude/worktrees/agent-add8fe1d30054f08d/scripts')
import v15_calibrate as C
import v2_avatar_validity as V
L = '/Users/namyunsu/Downloads/liplab-lab/data/'
rdir = sys.argv[1]
feats = C.out_feats()
sds = []
for fn in os.listdir(rdir + '/renders'):
    if not fn.endswith('_default_1.0.sched.json'):
        continue
    jid = fn[:-11]
    p = rdir + '/bs/' + jid + '.json'
    if not os.path.exists(p):
        continue
    sch = json.load(open(rdir + '/renders/' + fn))
    s = V.load_series(p)
    t = s['t']
    for seg in sch['schedule']:
        t0, t1 = seg['t0'] / 1000, seg['t1'] / 1000
        if t1 - t0 < 0.15:
            continue
        m = s['valid'] & (t >= t0 + 0.6 * (t1 - t0)) & (t <= t1)
        if m.sum() >= 3:
            X = np.stack([s['f'][f][m] for f in feats], 1)
            sds.append(X.std(0))
sd = np.nanmedian(np.array(sds), 0)
print('windows', len(sds))
for f, v in zip(feats, sd):
    print(f'{f:16s} {v:.4f}')
json.dump({'sd_window': sd.tolist(), 'feats': feats}, open('/tmp/v15sp/work/noise_window.json', 'w'))
