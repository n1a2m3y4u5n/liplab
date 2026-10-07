"""V5 가상 화자 재선정: 탐색 화자 배율 분포의 정해 둔 분위수 → 모프 배율(시뮬레이션 반응 곡선의 역보간)."""
import json, sys, pickle
import numpy as np
sys.path.insert(0, '/tmp/v15sp/work')
sys.path.insert(0, '/Users/namyunsu/Downloads/liplab/.claude/worktrees/agent-add8fe1d30054f08d/scripts')
import v15_calibrate as C
L = '/Users/namyunsu/Downloads/liplab-lab/data/'
cur = json.load(open('/tmp/v15sp/work/v5_curves.json'))
hum = pickle.load(open('/tmp/v15sp/work/human_explore.pkl', 'rb'))
prof, st = hum['prof'], hum['stats']
G = list(C.GROUPS)
scale = {c: [] for c in ('J', 'R')}
for s, p in prof.items():
    for c in ('J', 'R'):
        r = [p['amp'][g][c] / st['amp'][g][c] for g in G if g in p['amp'] and st['amp'][g][c] > 0.02]
        if r:
            scale[c].append(float(np.median(r)))
rates = np.array(list(hum['rate'].values()))
rate_scale = rates / np.median(rates)
# 기본 얼굴 2.0배의 탐색 문장 음절 속도(엔진 프레임: 음절 수 / 발화 길이)
sel = json.load(open(L + 'v2_avatar/sel.json'))
jobs = {j['id']: j for j in json.load(open(L + 'v2_avatar/jobs_text.json'))}
sps = []
for e in sel['sentences']:
    if e['half'] != 0 or not e['default']:
        continue
    j = jobs.get(f"txt_{e['sid']}_default_2.0")
    if not j:
        continue
    n_syl = sum(1 for ch in e['text'] if '\uac00' <= ch <= '\ud7a3')
    dur = sum(f['duration_ms'] for f in j['frames']) / 2.0 / 1000
    sps.append(n_syl / dur)
default_scale = float(np.median(sps)) / float(np.median(rates))


def inv(curve, target):
    pts = sorted([(1.0, 1.0)] + [tuple(x) for x in curve if np.isfinite(x[1])], key=lambda t: t[1])
    ks = np.array([p[0] for p in pts]); rs = np.log(np.array([p[1] for p in pts]))
    return float(np.interp(np.log(target), rs, ks))


Q = {'t1': (70, 40, 60), 't2': (30, 65, 35), 't3': (45, 30, 75), 't4': (60, 60, 45), 'h1': (85, 85, 55), 'h2': (15, 15, 20)}
out = {}
for t, (qa, qp, qr) in Q.items():
    ja = float(np.percentile(scale['J'], qa)); rp = float(np.percentile(scale['R'], qp)); rr = float(np.percentile(rate_scale, qr))
    out[t] = {'amp': round(inv(cur['curve']['amp'], ja), 2), 'protrusion': round(inv(cur['curve']['protrusion'], rp), 2),
              'rate': round(rr / default_scale, 2), 'q': [qa, qp, qr], 'human_scale': [round(ja, 3), round(rp, 3), round(rr, 3)]}
print('default 2.0x syllable rate scale vs explore median', round(default_scale, 3), 'median sps', round(float(np.median(rates)), 2), 'avatar', round(float(np.median(sps)), 2))
print('bounds (p10..p90): amp', round(inv(cur['curve']['amp'], np.percentile(scale['J'], 10)), 2), '..', round(inv(cur['curve']['amp'], np.percentile(scale['J'], 90)), 2),
      'prot', round(inv(cur['curve']['protrusion'], np.percentile(scale['R'], 10)), 2), '..', round(inv(cur['curve']['protrusion'], np.percentile(scale['R'], 90)), 2),
      'rate', round(np.percentile(rate_scale, 10) / default_scale, 2), '..', round(np.percentile(rate_scale, 90) / default_scale, 2))
for t, v in out.items():
    print(t, v)
json.dump(out, open('/tmp/v15sp/work/v5_talkers.json', 'w'), indent=1)
