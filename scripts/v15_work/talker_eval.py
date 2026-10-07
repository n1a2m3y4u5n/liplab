"""확인 절반 가상 화자(보고만): V15 표·V15 화자 렌더와 V2(지금 표·지금 화자) 렌더의 RSA ρ, 진폭 범위 안 무리 수."""
import json, sys
sys.path.insert(0, '/Users/namyunsu/Downloads/liplab/.claude/worktrees/agent-add8fe1d30054f08d/scripts')
import v15_calibrate as C
import v2_avatar_validity as V
L = '/Users/namyunsu/Downloads/liplab-lab/data/'
R = L + 'pod_runs/20261006_oel3rwn7y5zjbv/v2_part2/out/'
F = L + 'pod_runs/20261007_czde54612e5kcu/v2_final/out/'
NEW = L + 'pod_runs/20261007_zszjqyqz5m03q2/v15/cf_talkers'
sel = json.load(open(L + 'v2_avatar/sel.json'))
real, _, _ = C.human_profiles(sel, R + 'align_real.jsonl', R + 'bs_real', 1)
new = C.render_records(sel, NEW + '/renders', NEW + '/bs', 1)
sids = {r['sid'] for v in new.values() for r in v}
old = C.render_records(sel, F + 'renders', F + 'bs_render', 1, sids=sids)
out = {}
for tag, recs in (('new', new), ('old', old)):
    prof = {c: V.profile(v) for c, v in recs.items() if not c.startswith('default')}
    rsa, amp, leg = C.v2_metrics(real, prof)
    out[tag] = {c: {'n': len(recs[c]), 'rho': rsa['cond'][c]['rho'], 'amp_n_in': amp['cond'][c]['n_in'],
                    'bilabial': leg[c].get('bilabial_closure_rate'), 'rounded': leg[c].get('rounded_R_in_range_rate')} for c in sorted(prof)}
json.dump(out, open('/tmp/v15sp/work/talkers_cf.json', 'w'), indent=1)
for c in sorted(out['new']):
    n, o = out['new'][c], out['old'].get(c, {})
    print(f"{c:8s} n={n['n']:3d} rho {o.get('rho')} -> {n['rho']}  amp {o.get('amp_n_in')} -> {n['amp_n_in']}  bil {n['bilabial']} rnd {n['rounded']}")
