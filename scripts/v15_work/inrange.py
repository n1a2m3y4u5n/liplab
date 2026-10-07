import json, sys
sys.path.insert(0, '/Users/namyunsu/Downloads/liplab/.claude/worktrees/agent-add8fe1d30054f08d/scripts')
import v15_calibrate as C, v2_avatar_validity as V
L = '/Users/namyunsu/Downloads/liplab-lab/data/'
R = L + 'pod_runs/20261006_oel3rwn7y5zjbv/v2_part2/out/'
sel = json.load(open(L + 'v2_avatar/sel.json'))
half = int(sys.argv[2])
real, _, _ = C.human_profiles(sel, R + 'align_real.jsonl', R + 'bs_real', half)
new = C.render_records(sel, sys.argv[1] + '/renders', sys.argv[1] + '/bs', half)
prof = {c: V.profile(v) for c, v in new.items()}
amp = V.amp_block(real, prof)
for c in ('default_1.0', 'default_2.0'):
    g = amp['cond'][c]['groups']
    print(c, 'A in:', [k for k, r in g.items() if r.get('in')], '| J in:', [k for k, r in g.items() if r.get('J') and r['J']['in']])
    print('  out (A, p10, p90):', {k: (r['A']['x'], amp['ranges'][k]['A']['p10'], amp['ranges'][k]['A']['p90']) for k, r in g.items() if not r.get('in')})
