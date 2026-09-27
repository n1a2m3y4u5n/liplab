"""동형 폼 A·B 난이도 비교(가상 학습자, docs/assessment-design.md 9절).

    backend/.venv/bin/python scripts/form_equating_sim.py <판본 v1|v2> <시드> [uniform|confuse]

모형 uniform: 자리마다 확률 eps로 무작위 입모양(1~10)으로 잘못 봄. confuse: 잘못 볼 때 같은 무리 쪽으로 더 자주(입 안쪽 무리끼리 70%).
학습자는 본 열(입 안쪽 무리는 한 기호)과 가장 가까운 보기를 고르고, 동점이면 무작위."""
import json, random, statistics as st, sys
import os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'backend'))
import content_rules as cr
INSIDE = cr._INSIDE_CLUSTER
VIS = list(range(1, 11))
def grp(v): return 'C' if v in INSIDE else v
def perceive(v, eps, rng, model):
    if rng.random() >= eps:
        return grp(v)
    if model == 'confuse' and v in INSIDE and rng.random() < 0.7:
        return 'C'
    return grp(rng.choice(VIS))
def sim_item(item, eps, rng, model, n=4000):
    ans = item['word']; opts = item['options']
    sigs = {o: [grp(v) for v in cr.viseme_signature(o)] for o in opts}
    tgt = cr.viseme_signature(ans); ok = 0
    for _ in range(n):
        per = [perceive(v, eps, rng, model) for v in tgt]
        def dist(s):
            m = min(len(s), len(per))
            return abs(len(s) - len(per)) + sum(1 for a, b in zip(s[:m], per[:m]) if a != b)
        ds = {o: dist(sigs[o]) for o in opts}
        best = min(ds.values()); cands = [o for o, x in ds.items() if x == best]
        ok += (rng.choice(cands) == ans)
    return ok / n
ver, seed = sys.argv[1], int(sys.argv[2]); model = sys.argv[3] if len(sys.argv) > 3 else 'uniform'
d = json.load(open(os.path.join(HERE, '..', 'backend', 'data', 'assessment', f'forms_{ver}.json'), encoding='utf-8'))
rng = random.Random(seed)
res = {}
for eps in (0.1, 0.25, 0.4):
    a = st.mean(sim_item(it, eps, rng, model) for it in d['A']) * 100
    b = st.mean(sim_item(it, eps, rng, model) for it in d['B']) * 100
    res[eps] = (round(a, 1), round(b, 1), round(a - b, 1))
print(ver, 'seed', seed, model, '(A, B, A−B)', res, 'max|gap|', max(abs(v[2]) for v in res.values()))
