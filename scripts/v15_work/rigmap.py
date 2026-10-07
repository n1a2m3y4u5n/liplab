"""V15 5절: 음성 구동·거울 경로(bsFrameRef)의 원본 계수 → CC 모프 선형 사상. 탐색 V13 클립만 쓴다."""
import json, os, sys, pickle, math
import numpy as np
sys.path.insert(0, '/Users/namyunsu/Downloads/liplab/.claude/worktrees/agent-add8fe1d30054f08d/scripts')
import v15_calibrate as C
import v2_avatar_validity as V
sys.modules['__main__'].FM = C.FM
L = '/Users/namyunsu/Downloads/liplab-lab/data/'
R = L + 'pod_runs/20261006_oel3rwn7y5zjbv/v2_part2/out/'
F = L + 'pod_runs/20261007_czde54612e5kcu/v2_final/out/'
FEATS = C.out_feats(); FI = {f: i for i, f in enumerate(FEATS)}
IN = ['jawOpen', 'mouthClose', 'mouthFunnel', 'mouthPucker', 'mouthSmileLeft', 'mouthSmileRight', 'mouthStretchLeft', 'mouthStretchRight',
      'mouthUpperUpLeft', 'mouthUpperUpRight', 'mouthLowerDownLeft', 'mouthLowerDownRight', 'mouthPressLeft', 'mouthPressRight',
      'mouthRollLower', 'mouthRollUpper', 'mouthShrugLower', 'mouthShrugUpper']
UB = np.array([.6, .8, .6, .5, .5, .9, .9, .6, .5, .5, .5, .4, .4])
fm = pickle.load(open('/tmp/v15sp/work/fm_v15.pkl', 'rb'))
sel = json.load(open(L + 'v2_avatar/sel.json'))
_, v13 = C._explore_sets(sel)


def human(clip):
    d = json.load(open(R + 'bs_real/' + clip + '.json'))
    names, rows, fps = V.bs_frames_indexed(d)
    s = V.load_series(R + 'bs_real/' + clip + '.json')
    return names, rows, fps, s


def batch_inverse(T, Wt, extras, steps=250, lr=0.03):
    """T: [N, F] 목표 특징, Wt: [F] 가중, extras: [N, K] 고정 입력(CTRL 밖 키). 투영 경사(유한차분)."""
    N = len(T)
    U = np.full((N, len(C.CTRL)), 0.05)
    keys_idx = []
    for k in C.CTRL:
        keys_idx.append([C.KEYS.index(kk) for kk in (C.PAIRS[k] if k in C.PAIRS else (k,))])

    def X_of(U):
        X = extras.copy()
        for j, ix in enumerate(keys_idx):
            for i in ix:
                X[:, i] = U[:, j]
        return X

    def loss(U):
        P = fm.static(X_of(U))
        return ((P - T) ** 2 * Wt).sum(1) + 0.02 * (U ** 2).sum(1)
    m = np.zeros_like(U); v = np.zeros_like(U)
    eps = 2e-3
    for t in range(1, steps + 1):
        l0 = loss(U)
        G = np.zeros_like(U)
        for j in range(U.shape[1]):
            U2 = U.copy(); U2[:, j] += eps
            G[:, j] = (loss(U2) - l0) / eps
        m = 0.9 * m + 0.1 * G; v = 0.999 * v + 0.001 * G ** 2
        U = np.clip(U - lr * (m / (1 - 0.9 ** t)) / (np.sqrt(v / (1 - 0.999 ** t)) + 1e-8), 0, UB)
    return U, loss(U)


def main():
    rng = np.random.default_rng(0)
    rows_T, rows_M, rows_E = [], [], []
    for clip in v13:
        names, rows, fps, s = human(clip)
        ix = {k: i for i, k in enumerate(names)}
        for k in range(0, len(rows), 5):
            r = rows[k]
            if r is None or not np.isfinite(s['f']['G'][k]):
                continue
            T = np.array([s['f'][f][k] for f in FEATS])
            rows_T.append(T)
            rows_M.append([r[ix[n]] for n in IN])
            e = np.zeros(len(C.KEYS))
            for j, kk in enumerate(C.KEYS):
                if kk in ix and not any(kk in (C.PAIRS[c] if c in C.PAIRS else (c,)) for c in C.CTRL):
                    e[j] = r[ix[kk]]
            rows_E.append(e)
    T = np.array(rows_T); M = np.array(rows_M); E = np.array(rows_E)
    print('frames', len(T))
    Wt = np.zeros(len(FEATS))
    sd = T.std(0) + 1e-3
    for f in FEATS:
        Wt[FI[f]] = 0.2 / sd[FI[f]] ** 2
    for f, w in (('jawOpen', 3), ('mouthClose', 3), ('mouthPucker', 2), ('mouthFunnel', 1), ('smile', 2), ('stretch', 1), ('G', 3)):
        Wt[FI[f]] = w / sd[FI[f]] ** 2
    U, lu = batch_inverse(T, Wt, E)
    P = fm.static(np.hstack([E]))  # unused
    # 선형 사상(능선 회귀): U ≈ [M, 1] · B
    # 좌우 입력을 평균한 대칭 특징(거울 영상에서 좌우가 바뀌어도 같은 사상)
    SYM = []
    for n in IN:
        base = n.replace('Left', '').replace('Right', '')
        if base not in SYM:
            SYM.append(base)
    Ms = np.zeros((len(M), len(SYM)))
    for i, n in enumerate(IN):
        base = n.replace('Left', '').replace('Right', '')
        w = 0.5 if base != n else 1.0
        Ms[:, SYM.index(base)] += w * M[:, i]
    Xm = np.hstack([Ms, np.ones((len(M), 1))])
    lam = 1e-3 * len(M)
    B = np.linalg.solve(Xm.T @ Xm + lam * np.eye(Xm.shape[1]), Xm.T @ U)
    Uh = np.clip(Xm @ B, 0, UB)
    for j, k in enumerate(C.CTRL):
        print(f'{k:16s} inv mean {U[:, j].mean():.3f} sd {U[:, j].std():.3f}  lin r {np.corrcoef(U[:, j], Uh[:, j])[0, 1] if U[:, j].std() > 1e-4 else float("nan"):.3f}')
    spec = {'lin': {}}
    for j, k in enumerate(C.CTRL):
        row = {}
        for i, n in enumerate(IN):
            base = n.replace('Left', '').replace('Right', '')
            c = float(B[SYM.index(base), j]) * (0.5 if base != n else 1.0)
            if abs(c) >= 5e-4:
                row[n] = round(c, 4)
        row['_b'] = round(float(B[-1, j]), 4)
        for kk in (C.PAIRS[k] if k in C.PAIRS else (k,)):
            spec['lin'][kk] = row
    json.dump(spec, open('/tmp/v15sp/work/rawmap.json', 'w'), indent=1)
    print('SPEC_OK')
    evaluate(spec)


def evaluate(spec):
    res = {'base': {c: [] for c in V.V13_CH}, 'map': {c: [] for c in V.V13_CH}}
    meas = {c: [] for c in V.V13_CH}
    for clip in v13:
        names, rows, fps, s = human(clip)
        for tag, sp in (('base', None), ('map', spec)):
            W = C.raw_inputs(names, rows, fps, rawmap=sp)
            Y = fm.predict(C.lagged(W))
            f = {n: Y[:, i] for i, n in enumerate(FEATS)}
            f['R'] = f['mouthFunnel'] + f['mouthPucker']; f['S'] = f['smile'] + f['stretch']
            n = min(len(Y), len(s['t']))
            for c in V.V13_CH:
                x, y = s['f'][c][:n], f[c][:n]
                m = np.isfinite(x) & np.isfinite(y)
                if m.sum() >= 15 and x[m].std() > 1e-6 and y[m].std() > 1e-6:
                    res[tag][c].append(np.corrcoef(x[m], y[m])[0, 1])
        p = F + 'bs_v13/v13_' + clip + '.json'
        if os.path.exists(p):
            sr = V.load_series(p)
            n = min(len(sr['t']), len(s['t']))
            for c in V.V13_CH:
                x, y = s['f'][c][:n], sr['f'][c][:n]
                m = np.isfinite(x) & np.isfinite(y)
                if m.sum() >= 15 and x[m].std() > 1e-6 and y[m].std() > 1e-6:
                    meas[c].append(np.corrcoef(x[m], y[m])[0, 1])
    for c in V.V13_CH:
        print(f'{c:10s} measured V2 {np.median(meas[c]):.3f} | sim base {np.median(res["base"][c]):.3f} | sim map {np.median(res["map"][c]):.3f}')


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'eval':
        evaluate(json.load(open(sys.argv[2])))
    else:
        main()
