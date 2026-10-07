#!/bin/bash
# 사용: eval_run.sh HALF NEWDIR OUT
L=$HOME/Downloads/liplab-lab/data
F=$L/pod_runs/20261007_czde54612e5kcu/v2_final/out
R=$L/pod_runs/20261006_oel3rwn7y5zjbv/v2_part2/out
cd /Users/namyunsu/Downloads/liplab/.claude/worktrees/agent-add8fe1d30054f08d/scripts || exit 1
/tmp/v15sp/venv/bin/python v15_calibrate.py evaluate --sel $L/v2_avatar/sel.json --align $R/align_real.jsonl --real-bs $R/bs_real \
  --renders "$2/renders" --render-bs "$2/bs" --old-renders $F/renders --old-bs $F/bs_render --half "$1" --out "$3" 2>&1 | tail -1
/tmp/v15sp/venv/bin/python - "$3" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
for c in ('default_1.0', 'default_2.0'):
    n = d['new'][c]; o = d['old'][c]
    print(c, 'rho', n['rho'], 'amp', n['amp_n_in'], n['per_channel_in'], {k: v for k, v in n['legibility'].items() if k != 'bilabial_gap_p90_real'})
    print('   distinct new/old', {g: (v[0], o['distinct'][g][0]) for g, v in n['distinct'].items()})
    print('   A pct', n['amp_pct'])
    print('   pair_dev', n['pair_dev'][:4])
print('worse', d.get('distinct_worse_1.0'), d.get('distinct_worse_2.0'))
EOF
