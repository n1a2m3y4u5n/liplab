"""V15 보정 원형 2: 정적 근사 목적함수(RSA 피어슨 대리 + 진폭 + 가독성 + 자세 단순성)를 L-BFGS-B로, 동적 시뮬레이션으로 확인·보정."""
import json, os, sys, pickle, time
import numpy as np
from scipy.optimize import minimize
from scipy.stats import spearmanr
sys.path.insert(0, '/Users/namyunsu/Downloads/liplab/.claude/worktrees/agent-add8fe1d30054f08d/scripts')
import v15_calibrate as C
import v2_avatar_validity as V
sys.modules['__main__'].FM = C.FM
L = '/Users/namyunsu/Downloads/liplab-lab/data/'
FEATS = C.out_feats()
FI = {f: i for i, f in enumerate(FEATS)}
RSA_IDX = [FI[f] for f in V.RSA_FEATS]
G_LIST = list(C.GROUPS)
NC = len(C.CTRL)
CI = {k: i for i, k in enumerate(C.CTRL)}

# 무리별 상한(조음상 그럴듯한 범위). 하한은 0(ㅏ 턱만 0.12 이상).
def bounds_for(g):
    ub = {k: 0.0 for k in C.CTRL}
    lb = {k: 0.0 for k in C.CTRL}
    if g in (1, 11):
        ub.update(jawOpen=.35, mouthClose=.8, press=.4, mouthRollLower=.3, mouthRollUpper=.3, mouthFunnel=.3, mouthPucker=.6, smile=.15,
                  stretch=.1, upperUp=.1, lowerDown=.1, mouthShrugUpper=.2, mouthShrugLower=.2)
    elif g == 2:
        ub.update(jawOpen=.6, press=.15, mouthFunnel=.3, mouthPucker=.3, smile=.2, stretch=.2, upperUp=.3, lowerDown=.3,
                  mouthShrugUpper=.15, mouthShrugLower=.15)
        lb['jawOpen'] = .12
    elif g == 3:
        ub.update(jawOpen=.4, press=.15, mouthFunnel=.2, mouthPucker=.4, smile=.2, stretch=.2, upperUp=.3, lowerDown=.3,
                  mouthShrugUpper=.15, mouthShrugLower=.15)
    elif g == 4:
        ub.update(jawOpen=.3, mouthClose=.3, press=.15, mouthRollLower=.2, mouthRollUpper=.2, mouthFunnel=.8, mouthPucker=.8, upperUp=.15,
                  lowerDown=.15, mouthShrugUpper=.2, mouthShrugLower=.2)
    else:
        ub.update(jawOpen=.5, mouthClose=.3, press=.2, mouthRollLower=.15, mouthRollUpper=.15, mouthFunnel=.5, mouthPucker=.6, smile=.15,
                  stretch=.15, upperUp=.3, lowerDown=.3, mouthShrugUpper=.15, mouthShrugLower=.15)
    return [(lb[k], ub[k]) for k in C.CTRL]


BOUNDS = [b for g in G_LIST for b in bounds_for(g)]


def load_items(sel, half, speeds=(1.0, 2.0), talkers=('default',), sids=None):
    jobs = json.load(open(L + 'v2_avatar/jobs_text.json'))
    frames = {j['sid']: j['frames'] for j in jobs}
    items = []
    for e in sel['sentences']:
        if e['half'] != half or not e['default'] or (sids is not None and e['sid'] not in sids):
            continue
        for sp in speeds:
            for t in talkers:
                items.append((e['sid'], frames[e['sid']], t, sp))
    return items


def wquant(vals, w, q):
    o = np.argsort(vals)
    cw = np.cumsum(w[o]) / w.sum()
    return vals[o][np.searchsorted(cw, q)]


class Static:
    def __init__(self, fm, hum, shares1, shares2):
        self.fm, self.h = fm, hum
        st = hum['stats']
        self.st = st
        prof = hum['prof']
        D = np.array([v for v in (V.dist_vec(p) for p in prof.values()) if v is not None])
        self.ref = D.mean(0)
        self.pi1 = np.array([shares1.get(g, 1e-3) for g in G_LIST]); self.pi1 /= self.pi1.sum()
        self.pi2 = np.array([shares2.get(g, 1e-3) for g in G_LIST]); self.pi2 /= self.pi2.sum()
        rg = {}
        for g in G_LIST:
            rg[g] = {}
            for c in ('A', 'J', 'R'):
                vals = [p['amp'][g][c] for p in prof.values() if p and g in p['amp']]
                rg[g][c] = (np.percentile(vals, 10), np.percentile(vals, 50), np.percentile(vals, 90))
        self.rg = rg
        self.adj = {g: {'J': 0.0, 'R': 0.0} for g in G_LIST}
        self.legG = None
        self.w_rsa, self.w_reg = 3.0, 0.15

    def predict(self, U):
        X = np.array([C.ctrl_vec(dict(zip(C.CTRL, u))) for u in U])
        return self.fm.static(X)

    def metrics(self, Y):
        Z = Y[:, RSA_IDX]
        mu = (self.pi1[:, None] * Z).sum(0)
        sd = np.sqrt((self.pi1[:, None] * (Z - mu) ** 2).sum(0)) + 1e-6
        Zs = (Z - mu) / sd
        Dm = np.sqrt(((Zs[:, None, :] - Zs[None, :, :]) ** 2).sum(-1))
        iu = np.triu_indices(len(G_LIST), 1)
        d = Dm[iu]
        pr = np.corrcoef(d, self.ref)[0, 1]
        J = Y[:, FI['jawOpen']]; R = Y[:, FI['mouthFunnel']] + Y[:, FI['mouthPucker']]; S = Y[:, FI['smile']] + Y[:, FI['stretch']]
        fJ, fR, fS = wquant(J, self.pi2, 0.05), wquant(R, self.pi2, 0.05), wquant(S, self.pi2, 0.05)
        Jp = np.maximum(J - fJ, 0); Rp = np.maximum(R - fR, 0); Sp = np.maximum(S - fS, 0)
        A = np.sqrt(Jp ** 2 + Rp ** 2 + Sp ** 2)
        return pr, d, Jp, Rp, A

    def loss(self, x, w_rsa=None, w_amp=1.0, w_reg=None, verbose=False):
        w_rsa = self.w_rsa if w_rsa is None else w_rsa
        w_reg = self.w_reg if w_reg is None else w_reg
        U = x.reshape(len(G_LIST), NC)
        Y = self.predict(U)
        pr, d, Jp, Rp, A = self.metrics(Y)
        amp = 0.0
        for i, g in enumerate(G_LIST):
            lo, md, hi = self.rg[g]['A']; s = (hi - lo) / 2.56
            amp += ((A[i] + self.adj[g].get('A', 0) - md) / s) ** 2
            lo, md, hi = self.rg[g]['J']; s = (hi - lo) / 2.56
            amp += 0.5 * ((Jp[i] + self.adj[g]['J'] - md) / s) ** 2
            lo, md, hi = self.rg[g]['R']; s = (hi - lo) / 2.56
            amp += 0.5 * ((Rp[i] + self.adj[g]['R'] - md) / s) ** 2
        amp /= len(G_LIST)
        # 가독성: 양순 1·11 입술 닫힘(G ≤ 0.02), 원순 4 돌출은 진폭 항이 맡는다
        leg = 0.0
        for g in (1, 11):
            gi = G_LIST.index(g)
            leg += max(0.0, Y[gi, FI['G']] - 0.02) ** 2 * 2e4
        # 사람 G(입술 간격) 무리 평균에 가깝게(보이는 입 벌림)
        gl = 0.0
        for i, g in enumerate(G_LIST):
            if g not in (1, 11):
                gl += ((Y[i, FI['G']] - self.st['raw'][g]['G']) / 0.02) ** 2
        gl /= len(G_LIST)
        reg = float(np.sum(U ** 2)) / len(G_LIST)
        L_ = -w_rsa * pr + w_amp * amp + 0.3 * gl + leg + w_reg * reg
        if verbose:
            return {'pearson': round(float(pr), 4), 'spearman': round(float(spearmanr(d, self.ref).correlation), 4), 'amp': round(float(amp), 3),
                    'gl': round(float(gl), 3), 'leg': round(float(leg), 4), 'reg': round(reg, 3),
                    'A_in': int(sum(self.rg[g]['A'][0] <= A[i] <= self.rg[g]['A'][2] for i, g in enumerate(G_LIST)))}
        return L_

    def optimize(self, x0, iters=300):
        res = minimize(self.loss, x0, method='L-BFGS-B', bounds=BOUNDS, options={'maxiter': iters, 'eps': 2e-3, 'maxfun': 200000})
        return res.x, res


def old_x():
    x = []
    for g in G_LIST:
        old = {k: 0.0 for k in C.CTRL}
        for k, v in (C.OLD_TABLE.get(g) or {}).items():
            for ck, pair in C.PAIRS.items():
                if k in pair:
                    old[ck] = v
            if k in old:
                old[k] = v
        x += [old[k] for k in C.CTRL]
    return np.clip(np.array(x), [b[0] for b in BOUNDS], [b[1] for b in BOUNDS])


def to_table(x):
    U = x.reshape(len(G_LIST), NC)
    out = {}
    for g, u in zip(G_LIST, U):
        sh = {}
        for k, v in C.expand({kk: float(xx) for kk, xx in zip(C.CTRL, u)}).items():
            if v >= 0.01:
                sh[k] = round(v, 2)
        out[g] = sh
    s4, s2 = out.get(4, {}), out.get(2, {})
    out[9] = {k: round(0.6 * s4.get(k, 0) + 0.4 * s2.get(k, 0), 2) for k in set(s4) | set(s2) if 0.6 * s4.get(k, 0) + 0.4 * s2.get(k, 0) >= 0.01}
    out[15] = {}
    return {int(k): out[k] for k in sorted(out)}


def shares(sim, speed):
    tot = {}
    for it in sim.items:
        if it['speed'] != speed:
            continue
        for v, t0, t1 in it['segs']:
            tot[v] = tot.get(v, 0) + (t1 - t0)
    return tot


def dyn_eval(sim, table, real_prof):
    prof, cond = sim.profiles(table)
    rsa, amp, leg = C.v2_metrics(real_prof, prof)
    out = {}
    for c in sorted(prof):
        out[c] = {'rho': rsa['cond'][c]['rho'], 'amp_in': amp['cond'][c]['n_in'], 'ch_in': amp['cond'][c]['per_channel_in'],
                  'leg': {k: v for k, v in leg[c].items() if k != 'bilabial_gap_p90_real'}, 'distinct': C.distinctiveness(cond[c]),
                  'pair_dev': rsa['cond'][c]['pair_dev'][:5]}
    return out, prof, amp


if __name__ == '__main__':
    t0 = time.time()
    fm = pickle.load(open('/tmp/v15sp/work/fm_v15.pkl', 'rb'))
    hum = pickle.load(open('/tmp/v15sp/work/human_explore.pkl', 'rb'))
    sel = json.load(open(L + 'v2_avatar/sel.json'))
    sids, _ = C._explore_sets(sel)
    sim = C.Sim(fm, load_items(sel, 0))
    S = Static(fm, hum, shares(sim, 1.0), shares(sim, 2.0))
    x = old_x()
    print('OLD static', S.loss(x, verbose=True))
    w_rsa = float(sys.argv[1]) if len(sys.argv) > 1 else 3.0
    w_reg = float(sys.argv[2]) if len(sys.argv) > 2 else 0.15
    n_outer = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    tag = sys.argv[4] if len(sys.argv) > 4 else 'a'
    S.w_rsa, S.w_reg = w_rsa, w_reg
    for outer in range(n_outer):
        x, res = S.optimize(x) if outer == 0 else S.optimize(x, 200)
        st = S.loss(x, w_rsa=w_rsa, w_reg=w_reg, verbose=True)
        tab = to_table(x)
        ev, prof, amp = dyn_eval(sim, tab, hum['prof'])
        p2 = prof['default_2.0']
        Y = S.predict(x.reshape(len(G_LIST), NC))
        _, _, Jp, Rp, A = S.metrics(Y)
        for i, g in enumerate(G_LIST):   # 정적 근사와 동적(2.0배) 진폭 차이를 보정량으로
            if g in p2['amp']:
                S.adj[g]['J'] = 0.7 * (p2['amp'][g]['J'] - Jp[i]) + 0.3 * S.adj[g]['J']
                S.adj[g]['R'] = 0.7 * (p2['amp'][g]['R'] - Rp[i]) + 0.3 * S.adj[g]['R']
                S.adj[g]['A'] = 0.7 * (p2['amp'][g]['A'] - A[i]) + 0.3 * S.adj[g].get('A', 0)
        print(f'outer {outer} t={time.time() - t0:.0f}s static={st}')
        print('   dyn', json.dumps({c: {k: v for k, v in d.items() if k in ('rho', 'amp_in', 'leg')} for c, d in ev.items()}))
    old_ev, _, _ = dyn_eval(sim, C.OLD_TABLE, hum['prof'])
    json.dump({'table': tab, 'x': x.tolist(), 'eval': ev, 'old_eval': old_ev, 'adj': S.adj}, open(f'/tmp/v15sp/work/calib2_{tag}.json', 'w'), indent=1, default=str)
    print('TABLE', json.dumps(tab))
    for c in ('default_1.0', 'default_2.0'):
        print(c, 'distinct new/old', {g: (ev[c]['distinct'][g][0], old_ev[c]['distinct'][g][0]) for g in G_LIST})
