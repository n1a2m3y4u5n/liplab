"""V15 보정 원형 3: 정적 근사 + 동적 보정(무리별 특징 차이, 무리 안 분산) + 구별성 대리 항."""
import json, os, sys, pickle, time
import numpy as np
from scipy.optimize import minimize
from scipy.stats import spearmanr
sys.path.insert(0, '/tmp/v15sp/work')
sys.path.insert(0, '/Users/namyunsu/Downloads/liplab/.claude/worktrees/agent-add8fe1d30054f08d/scripts')
import v15_calibrate as C
import v2_avatar_validity as V
from calib2 import bounds_for, BOUNDS, load_items, wquant, old_x, to_table, shares, G_LIST, NC, FEATS, FI, RSA_IDX
sys.modules['__main__'].FM = C.FM
L = '/Users/namyunsu/Downloads/liplab-lab/data/'
NG = len(G_LIST)


NOISE = json.load(open('/tmp/v15sp/work/noise.json'))
NSD = np.array(NOISE['sd']); NAC = np.array(NOISE['ac1'])


def noisy_profiles(sim, table, seed=0):
    """시뮬레이션 계열에 재측정 잡음(AR(1), 특징별 표준편차·자기상관)을 더해 V2 프로필·기록을 만든다."""
    rng = np.random.default_rng(seed)
    cond = {}
    for it, ser in sim.series(table):
        n = len(ser['t'])
        E = np.zeros((n, len(FEATS)))
        e = rng.normal(0, 1, len(FEATS)) * NSD
        for k in range(n):
            e = NAC * e + np.sqrt(1 - NAC ** 2) * NSD * rng.normal(0, 1, len(FEATS))
            E[k] = e
        f = dict(ser['f'])
        for j, name in enumerate(FEATS):
            f[name] = ser['f'][name] + E[:, j]
        f['J'] = f['jawOpen']; f['R'] = f['mouthFunnel'] + f['mouthPucker']; f['S'] = f['smile'] + f['stretch']; f['C'] = f['mouthClose']
        rec, _ = V.clip_record({'t': ser['t'], 'valid': ser['valid'], 'f': f}, it['segs'], it['span'])
        if rec:
            rec['sid'] = it['sid']
            cond.setdefault(f"{it['tid']}_{it['speed']}", []).append(rec)
    return {c: V.profile(v) for c, v in cond.items()}, cond


def dyn_stats(sim, table):
    """동적 시뮬레이션(잡음 포함): 속도별 무리 평균(원값, 특징 전체), 무리 안 분산 평균(특징별), 지표."""
    prof, cond = noisy_profiles(sim, table)
    out = {}
    for sp in (1.0, 2.0):
        recs = cond[f'default_{sp}']
        segs = [(g, np.array([v[f] for f in FEATS])) for r in recs for g, v in r['segs']]
        M = np.zeros((NG, len(FEATS))); W = np.zeros(len(FEATS)); n = 0
        for i, g in enumerate(G_LIST):
            X = np.array([x for gg, x in segs if gg == g])
            M[i] = np.nanmean(X, 0)
            W += np.nansum((X - M[i]) ** 2, 0); n += len(X)
        out[sp] = {'mean': M, 'within': W / n, 'recall': C.distinctiveness(recs)}
    return out, prof, cond


class Surr:
    def __init__(self, fm, hum, sim):
        self.fm, self.h, self.st = fm, hum, hum['stats']
        prof = hum['prof']
        D = np.array([v for v in (V.dist_vec(p) for p in prof.values()) if v is not None])
        self.ref = D.mean(0)
        s1, s2 = shares(sim, 1.0), shares(sim, 2.0)
        self.pi = {1.0: np.array([s1.get(g, 1e-3) for g in G_LIST]), 2.0: np.array([s2.get(g, 1e-3) for g in G_LIST])}
        for k in self.pi:
            self.pi[k] = self.pi[k] / self.pi[k].sum()
        self.rg = {g: {c: tuple(np.percentile([p['amp'][g][c] for p in prof.values() if p and g in p['amp']], [10, 50, 90]))
                       for c in ('A', 'J', 'R')} for g in G_LIST}
        self.off = {1.0: np.zeros((NG, len(FEATS))), 2.0: np.zeros((NG, len(FEATS)))}
        self.within = {1.0: np.zeros(len(FEATS)), 2.0: np.zeros(len(FEATS))}
        self.wd = np.zeros(NG)          # 구별성 가중
        self.m_old = None               # 지금 표의 무리별 여백(속도별)
        self.w_rsa, self.w_reg, self.w_amp = 3.0, 0.15, 1.0
        self.w_z = 1.0
        self.zh = np.array([np.mean([p['z'][g] for p in prof.values() if p and g in p['z']], axis=0) for g in G_LIST])

    def predict(self, U):
        return self.fm.static(np.array([C.ctrl_vec(dict(zip(C.CTRL, u))) for u in U]))

    def zspace(self, Y, sp):
        Ye = Y + self.off[sp]
        Z = Ye[:, RSA_IDX]
        pi = self.pi[sp]
        mu = (pi[:, None] * Z).sum(0)
        var = (pi[:, None] * (Z - mu) ** 2).sum(0) + self.within[sp][RSA_IDX]
        ok = var > 1e-8
        return np.where(ok, (Z - mu) / np.sqrt(np.where(ok, var, 1)), 0.0), Ye

    def margins(self, Zs):
        Dm = np.sqrt(((Zs[:, None, :] - Zs[None, :, :]) ** 2).sum(-1))
        Dm[np.arange(NG), np.arange(NG)] = np.inf
        return Dm.min(1), Dm

    def amps(self, Ye, sp):
        J = Ye[:, FI['jawOpen']]; R = Ye[:, FI['mouthFunnel']] + Ye[:, FI['mouthPucker']]; S = Ye[:, FI['smile']] + Ye[:, FI['stretch']]
        pi = self.pi[sp]
        fJ, fR, fS = wquant(J, pi, 0.05), wquant(R, pi, 0.05), wquant(S, pi, 0.05)
        Jp, Rp, Sp = np.maximum(J - fJ, 0), np.maximum(R - fR, 0), np.maximum(S - fS, 0)
        return Jp, Rp, np.sqrt(Jp ** 2 + Rp ** 2 + Sp ** 2)

    def parts(self, Y):
        Z1, Ye1 = self.zspace(Y, 1.0)
        Z2, Ye2 = self.zspace(Y, 2.0)
        m1, Dm = self.margins(Z1)
        m2, _ = self.margins(Z2)
        iu = np.triu_indices(NG, 1)
        d = Dm[iu]
        pr = np.corrcoef(d, self.ref)[0, 1]
        return pr, d, self.amps(Ye1, 1.0), self.amps(Ye2, 2.0), m1, m2, Ye1

    def loss(self, x, verbose=False):
        U = x.reshape(NG, NC)
        Y = self.predict(U)
        pr, d, (J1, R1, A1), (J2, R2, A2), m1, m2, Ye1 = self.parts(Y)
        amp, bar = 0.0, 0.0
        for i, g in enumerate(G_LIST):
            for c, v, w in (('A', A1[i], 1.0), ('J', J1[i], 0.5), ('R', R1[i], 0.5)):
                lo, md, hi = self.rg[g][c]
                amp += w * ((v - md) / ((hi - lo) / 2.56)) ** 2
            lo, md, hi = self.rg[g]['A']
            bar += (max(0.0, lo * 1.2 - A2[i]) / lo) ** 2 + (max(0.0, A2[i] - hi * 0.9) / hi) ** 2
        amp /= NG
        i4 = G_LIST.index(4)
        for r in (R1[i4], R2[i4]):
            bar += (max(0.0, 0.12 - r) / 0.1) ** 2 + (max(0.0, r - 0.85) / 0.1) ** 2
        leg = sum(max(0.0, Y[G_LIST.index(g), FI['G']] - 0.02) ** 2 * 2e4 for g in (1, 11))
        gl = np.mean([((Ye1[i, FI['G']] - self.st['raw'][g]['G']) / 0.02) ** 2 for i, g in enumerate(G_LIST) if g not in (1, 11)])
        dist = 0.0
        if self.m_old is not None:
            dist = float(np.sum(self.wd * (np.maximum(0, self.m_old[1.0] - m1) ** 2 + np.maximum(0, self.m_old[2.0] - m2) ** 2)))
        reg = float(np.sum(U ** 2)) / NG
        Z1, _ = self.zspace(Y, 1.0)
        zm = float(np.mean((Z1 - self.zh) ** 2))
        Lx = -self.w_rsa * pr + self.w_amp * amp + 3.0 * bar + 0.3 * gl + leg + self.w_reg * reg + dist + self.w_z * zm
        if verbose:
            return {'zm': round(float(np.mean((self.zspace(Y, 1.0)[0] - self.zh) ** 2)), 3), 'pearson': round(float(pr), 4), 'spearman': round(float(spearmanr(d, self.ref).correlation), 4), 'amp': round(float(amp), 3),
                    'bar': round(float(bar), 3), 'gl': round(float(gl), 3), 'leg': round(float(leg), 4), 'dist': round(dist, 3), 'reg': round(reg, 3),
                    'A2_in': int(sum(self.rg[g]['A'][0] <= A2[i] <= self.rg[g]['A'][2] for i, g in enumerate(G_LIST))),
                    'R4': [round(float(R1[i4]), 3), round(float(R2[i4]), 3)]}
        return Lx

    def update(self, ds, Ystatic, eta=0.5):
        for sp in (1.0, 2.0):
            self.off[sp] = eta * (ds[sp]['mean'] - Ystatic) + (1 - eta) * self.off[sp]
            self.within[sp] = ds[sp]['within']


def run(w_rsa=3.0, w_reg=0.15, n_outer=6, tag='b', x0=None, wd0=0.0, kappa=1.0, tol=0.0, w_z=1.0):
    t0 = time.time()
    fm = pickle.load(open('/tmp/v15sp/work/fm_v15.pkl', 'rb'))
    hum = pickle.load(open('/tmp/v15sp/work/human_explore.pkl', 'rb'))
    sel = json.load(open(L + 'v2_avatar/sel.json'))
    sim = C.Sim(fm, load_items(sel, 0))
    S = Surr(fm, hum, sim)
    S.w_rsa, S.w_reg, S.w_z = w_rsa, w_reg, w_z
    # 지금 표: 동적 보정을 같은 방식으로 맞춘 뒤 여백 기준을 잡는다
    xo = old_x()
    Uo = xo.reshape(NG, NC)
    Yo = S.predict(Uo)
    dso, _, _ = dyn_stats(sim, C.OLD_TABLE)
    So = Surr(fm, hum, sim); So.update(dso, Yo, eta=1.0)
    _, _, _, _, m1o, m2o, _ = So.parts(Yo)
    S.m_old = {1.0: kappa * m1o, 2.0: kappa * m2o}
    ro = json.load(open('/tmp/v15sp/work/eval_old_ex.json'))['new']
    rec_old = {sp: {int(g): v for g, v in ro[f'default_{sp}']['distinct'].items()} for sp in (1.0, 2.0)}
    S.wd[:] = wd0
    x = old_x() if x0 is None else np.array(x0)
    hist = []
    for outer in range(n_outer):
        res = minimize(S.loss, x, method='L-BFGS-B', bounds=BOUNDS, options={'maxiter': 250, 'eps': 2e-3, 'maxfun': 200000})
        x = res.x
        tab = to_table(x)
        Ys = S.predict(x.reshape(NG, NC))
        ds, prof, cond = dyn_stats(sim, tab)
        rsa, amp, leg = C.v2_metrics(hum['prof'], prof)
        sv = S.loss(x, verbose=True)
        deficit = {}
        for sp in (1.0, 2.0):
            for i, g in enumerate(G_LIST):
                dnew, dold = ds[sp]['recall'][g][0], rec_old[sp][g][0]
                if dnew < dold - tol:
                    deficit[(sp, g)] = round(dnew - dold, 3)
                    S.wd[i] = max(S.wd[i] * 2, 2.0)
        row = {'outer': outer, 't': round(time.time() - t0), 'static': sv,
               'rho1': rsa['cond']['default_1.0']['rho'], 'rho2': rsa['cond']['default_2.0']['rho'],
               'amp2_in': amp['cond']['default_2.0']['n_in'], 'amp1_in': amp['cond']['default_1.0']['n_in'],
               'leg1': {k: v for k, v in leg['default_1.0'].items() if k != 'bilabial_gap_p90_real'},
               'leg2': {k: v for k, v in leg['default_2.0'].items() if k != 'bilabial_gap_p90_real'},
               'deficit': {f'{sp}:{g}': v for (sp, g), v in deficit.items()}}
        print(json.dumps(row), flush=True)
        hist.append({'row': row, 'x': x.tolist(), 'table': tab,
                     'recall': {str(sp): {g: ds[sp]['recall'][g][0] for g in G_LIST} for sp in (1.0, 2.0)}})
        S.update(ds, Ys)
    json.dump({'hist': hist, 'recall_old': {str(sp): {g: rec_old[sp][g][0] for g in G_LIST} for sp in (1.0, 2.0)}},
              open(f'/tmp/v15sp/work/calib3_{tag}.json', 'w'), indent=1, default=str)
    return hist


if __name__ == '__main__':
    a = sys.argv
    run(float(a[1]), float(a[2]), int(a[3]), a[4], wd0=float(a[5]) if len(a) > 5 else 0.0, w_z=float(a[6]) if len(a) > 6 else 1.0)
