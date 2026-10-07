"""V15 보정 원형 5: 실제 렌더 잔차 보정(입모양별, 궤적 계수로 섞음) + 잡음 포함 시뮬레이션 + 구별성 여백 + 신뢰 영역."""
import json, sys, pickle, time
import numpy as np
from scipy.optimize import minimize
sys.path.insert(0, '/tmp/v15sp/work')
sys.path.insert(0, '/Users/namyunsu/Downloads/liplab/.claude/worktrees/agent-add8fe1d30054f08d/scripts')
import v15_calibrate as C
import v2_avatar_validity as V
import calib4 as K
from calib2 import BOUNDS, load_items, old_x, to_table, G_LIST, NC, FEATS, FI, RSA_IDX
sys.modules['__main__'].FM = C.FM
L = '/Users/namyunsu/Downloads/liplab-lab/data/'
NG = len(G_LIST)


def table_to_x(tab):
    x = []
    for g in G_LIST:
        sh = tab.get(g) or tab.get(str(g)) or {}
        for k in C.CTRL:
            kk = C.PAIRS[k][0] if k in C.PAIRS else k
            x.append(sh.get(kk, 0.0))
    return np.clip(np.array(x), [b[0] for b in BOUNDS], [b[1] for b in BOUNDS])


def residual(fm, sel, tab, rdir):
    """실제 렌더(rdir) − 잡음 없는 시뮬레이션의 1.0배 무리 평균 → [15, 특징]."""
    real = C.render_records(sel, rdir + '/renders', rdir + '/bs', 0)
    sids = {r['sid'] for r in real['default_1.0']}
    sim = C.Sim(fm, [it for it in load_items(sel, 0, speeds=(1.0,)) if it[0] in sids])
    _, cond = sim.profiles(tab)
    R = np.zeros((15, len(FEATS)))
    for g in G_LIST:
        a = np.array([[v[f] for f in FEATS] for r in real['default_1.0'] for gg, v in r['segs'] if gg == g])
        b = np.array([[v[f] for f in FEATS] for r in cond['default_1.0'] for gg, v in r['segs'] if gg == g])
        R[g - 1] = np.nanmean(a, 0) - np.nanmean(b, 0)
    return R


def seg_extra_sd(fm, sel, tab, rdir, Rres):
    """무리·속도별 구간 값의 추가 흩어짐: 실제 렌더 무리 안 분산 − 시뮬레이션(잔차 보정) 무리 안 분산."""
    real = C.render_records(sel, rdir + '/renders', rdir + '/bs', 0)
    sids = {r['sid'] for r in real['default_1.0']}
    sim = C.Sim(fm, [it for it in load_items(sel, 0) if it[0] in sids], resid=Rres)
    _, cond = sim.profiles(tab)
    out = {}
    for sp in (1.0, 2.0):
        c = f'default_{sp}'
        E = np.zeros((15, len(FEATS)))
        for g in G_LIST:
            a = np.array([[v[f] for f in FEATS] for r in real[c] for gg, v in r['segs'] if gg == g])
            b = np.array([[v[f] for f in FEATS] for r in cond[c] for gg, v in r['segs'] if gg == g])
            E[g - 1] = np.sqrt(np.maximum(0, np.nanvar(a, 0) - np.nanvar(b, 0)))
        out[sp] = E
    return out


def make_noisy(extra):
    def noisy_profiles(sim, table, seed=0):
        """구간 값에만 무리·속도별 추가 흩어짐을 더한다(프레임·바닥값은 그대로)."""
        rng = np.random.default_rng(seed)
        _, cond = sim.profiles(table)
        out = {}
        for c, recs in cond.items():
            sp = float(c.split('_')[1])
            nr = []
            for r in recs:
                r2 = dict(r)
                segs = []
                for g, v in r['segs']:
                    v2 = dict(v)
                    e = extra[sp][g - 1] * rng.normal(0, 1, len(FEATS))
                    for j, f in enumerate(FEATS):
                        v2[f] = v[f] + e[j]
                    v2['J'] = v2['jawOpen']; v2['R'] = v2['mouthFunnel'] + v2['mouthPucker']; v2['S'] = v2['smile'] + v2['stretch']; v2['C'] = v2['mouthClose']
                    segs.append((g, v2))
                r2['segs'] = segs
                nr.append(r2)
            out[c] = nr
        return {c: V.profile(v) for c, v in out.items()}, out
    return noisy_profiles


def run(base_tab, rdir, tag, w_rsa=3.0, w_tr=2.0, n_outer=6, wd0=1.0, margin=0.03):
    t0 = time.time()
    fm = pickle.load(open('/tmp/v15sp/work/fm_v15.pkl', 'rb'))
    hum = pickle.load(open('/tmp/v15sp/work/human_explore.pkl', 'rb'))
    sel = json.load(open(L + 'v2_avatar/sel.json'))
    Rres = residual(fm, sel, base_tab, rdir)
    extra = seg_extra_sd(fm, sel, base_tab, rdir, Rres)
    K.noisy_profiles = make_noisy(extra)
    sim = C.Sim(fm, load_items(sel, 0), resid=Rres)
    S = K.Surr(fm, hum, sim)
    S.w_rsa, S.w_reg, S.w_z = w_rsa, 0.15, 0.0
    # 정적 예측에도 같은 잔차를 더한다
    pred0 = S.predict
    S.predict = lambda U: pred0(U) + Rres[[g - 1 for g in G_LIST]]
    # 지금 표 여백 기준(지금 표는 잔차 보정 없이, 잡음 포함 동적 통계)
    sim_old = C.Sim(fm, load_items(sel, 0))
    So = K.Surr(fm, hum, sim_old)
    Uo = old_x().reshape(NG, NC)
    Yo = So.predict(Uo)
    dso, _, _ = K.dyn_stats(sim_old, C.OLD_TABLE)
    So.update(dso, Yo, eta=1.0)
    _, _, _, _, m1o, m2o, _ = So.parts(Yo)
    S.m_old = {1.0: m1o, 2.0: m2o}
    ro = json.load(open('/tmp/v15sp/work/eval_old_ex.json'))['new']
    rec_old = {sp: {int(g): v[0] for g, v in ro[f'default_{sp}']['distinct'].items()} for sp in (1.0, 2.0)}
    S.wd[:] = wd0
    xc = table_to_x(base_tab)
    loss0 = S.loss

    def loss_tr(x, verbose=False):
        v = loss0(x, verbose=verbose)
        if verbose:
            return v
        return v + w_tr * float(np.sum((x - xc) ** 2)) / NG
    # 시작점의 동적 보정
    ds, prof0, _ = K.dyn_stats(sim, base_tab)
    rsa0, amp0, leg0 = C.v2_metrics(hum['prof'], prof0)
    print('BASE sim', json.dumps({'rho1': rsa0['cond']['default_1.0']['rho'], 'amp2': amp0['cond']['default_2.0']['n_in'],
                                  'leg1': leg0['default_1.0'].get('rounded_R_in_range_rate'),
                                  'recall1': {g: ds[1.0]['recall'][g][0] for g in G_LIST}, 'recall2': {g: ds[2.0]['recall'][g][0] for g in G_LIST}}), flush=True)
    S.update(ds, S.predict(xc.reshape(NG, NC)), eta=1.0)
    x = xc.copy()
    hist = []
    for outer in range(n_outer):
        res = minimize(loss_tr, x, method='L-BFGS-B', bounds=BOUNDS, options={'maxiter': 200, 'eps': 2e-3, 'maxfun': 100000})
        x = res.x
        tab = to_table(x)
        ds, prof, cond = K.dyn_stats(sim, tab)
        rsa, amp, leg = C.v2_metrics(hum['prof'], prof)
        deficit = {}
        for sp in (1.0, 2.0):
            for i, g in enumerate(G_LIST):
                dn = ds[sp]['recall'][g][0]
                if dn < rec_old[sp][g] + margin:
                    deficit[f'{sp}:{g}'] = round(dn - rec_old[sp][g], 3)
                    S.wd[i] = max(S.wd[i] * 1.7, 2.0)
        row = {'outer': outer, 't': round(time.time() - t0), 'rho1': rsa['cond']['default_1.0']['rho'], 'rho2': rsa['cond']['default_2.0']['rho'],
               'amp2': amp['cond']['default_2.0']['n_in'], 'amp1': amp['cond']['default_1.0']['n_in'],
               'leg': [leg['default_1.0'].get('bilabial_closure_rate'), leg['default_1.0'].get('rounded_R_in_range_rate'),
                       leg['default_2.0'].get('bilabial_closure_rate'), leg['default_2.0'].get('rounded_R_in_range_rate')],
               'move': round(float(np.sqrt(np.mean((x - xc) ** 2))), 4), 'deficit': deficit}
        print(json.dumps(row), flush=True)
        hist.append({'row': row, 'table': tab, 'recall': {str(sp): {g: ds[sp]['recall'][g][0] for g in G_LIST} for sp in (1.0, 2.0)}})
        S.update(ds, S.predict(x.reshape(NG, NC)))
    json.dump({'hist': hist, 'rec_old': {str(k): v for k, v in rec_old.items()}}, open(f'/tmp/v15sp/work/calib5_{tag}.json', 'w'), indent=1, default=str)


if __name__ == '__main__':
    a = sys.argv
    base = {int(k): v for k, v in json.load(open(a[1]))[a[2]].items()}
    run(base, a[3], a[4], w_rsa=float(a[5]), w_tr=float(a[6]), n_outer=int(a[7]), wd0=float(a[8]))
