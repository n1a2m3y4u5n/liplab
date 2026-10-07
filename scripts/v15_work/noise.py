"""렌더 재측정 잡음 모형: 실제 렌더(MediaPipe) − 시뮬레이션(순방향 사상)의 프레임 잔차 표준편차와 1차 자기상관."""
import json, sys, pickle, os
import numpy as np
sys.path.insert(0, '/tmp/v15sp/work')
sys.path.insert(0, '/Users/namyunsu/Downloads/liplab/.claude/worktrees/agent-add8fe1d30054f08d/scripts')
import v15_calibrate as C
import v2_avatar_validity as V
sys.modules['__main__'].FM = C.FM
L = '/Users/namyunsu/Downloads/liplab-lab/data/'
fm = pickle.load(open('/tmp/v15sp/work/fm_v15.pkl', 'rb'))
tab = {int(k): v for k, v in json.load(open('/tmp/v15sp/work/tables_c.json'))['c'].items()}
rdir = L + 'pod_runs/20261007_zszjqyqz5m03q2/v15/ex_c/'
jobs = {j['id']: j for j in json.load(open('/tmp/v15sp/work/jobs_ex_c.json'))}
feats = C.out_feats()
res = []
for jid, j in list(jobs.items()):
    p = rdir + 'bs/' + jid + '.json'
    if not os.path.exists(p):
        continue
    Cm, _, _ = C.text_coeffs(j['frames'], 'default', j['speed'])
    Y = fm.predict(C.lagged(Cm @ C.table_matrix(tab, C.TALKERS['default'])))
    s = V.load_series(p)
    Yr = np.stack([s['f'][f] for f in feats], 1)
    n = min(len(Y), len(Yr))
    d = Yr[:n] - Y[:n]
    res.append(d[np.all(np.isfinite(d), 1)])
D = np.concatenate(res)
sd = D.std(0)
ac = np.array([np.corrcoef(np.concatenate([r[:-1, j] for r in res]), np.concatenate([r[1:, j] for r in res]))[0, 1] for j in range(len(feats))])
bias = D.mean(0)
for f, a, b, c in zip(feats, sd, ac, bias):
    print(f'{f:16s} sd {a:.4f} ac1 {b:.2f} bias {c:+.4f}')
json.dump({'sd': sd.tolist(), 'ac1': ac.tolist(), 'feats': feats}, open('/tmp/v15sp/work/noise.json', 'w'))
