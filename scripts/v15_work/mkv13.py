import json, sys, os
sys.path.insert(0, '/Users/namyunsu/Downloads/liplab/.claude/worktrees/agent-add8fe1d30054f08d/scripts')
import v2_avatar_validity as V
L = '/Users/namyunsu/Downloads/liplab-lab/data/'
R = L + 'pod_runs/20261006_oel3rwn7y5zjbv/v2_part2/out/bs_real/'
half = int(sys.argv[1]); spec = json.load(open(sys.argv[2])) if sys.argv[2] != '-' else None; out = sys.argv[3]
sel = json.load(open(L + 'v2_avatar/sel.json'))
hs = {s['spk']: s['half'] for s in sel['speakers']}
cs = {c['clip']: c['spk'] for c in sel['clips']}
jobs = []
for clip in sel['v13_clips']:
    if hs[cs[clip]] != half:
        continue
    d = json.load(open(R + clip + '.json'))
    names, rows, fps = V.bs_frames_indexed(d)
    j = {'id': f'v13_{clip}', 'kind': 'raw', 'clip': clip, 'names': names, 'frames': rows, 'fps': fps}
    if spec:
        j['rawMap'] = spec
    jobs.append(j)
json.dump(jobs, open(out, 'w'))
print('V13JOBS', len(jobs))
