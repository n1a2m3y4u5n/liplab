import json, os, sys, numpy as np
sys.path.insert(0, '/Users/namyunsu/Downloads/liplab/.claude/worktrees/agent-add8fe1d30054f08d/scripts')
import v2_avatar_validity as V
import v15_calibrate as C
OUT = C.out_feats()
base = '/Users/namyunsu/Downloads/liplab-lab/data/'
run = base + 'pod_runs/20261007_zszjqyqz5m03q2/v15/'


def load(jobs_path, bs_dir, prefix):
    rows = []
    conv = []
    for j in json.load(open(jobs_path)):
        if not j['id'].startswith(prefix):
            continue
        p = os.path.join(bs_dir, j['id'] + '.json')
        if not os.path.exists(p):
            continue
        Y, ok = C._series_Y(p)
        h = j['hold']
        for i, pose in enumerate(j['poses']):
            ks = [i * h + h - 3, i * h + h - 2, i * h + h - 1]
            if ks[-1] >= len(Y) or not all(ok[k] for k in ks):
                continue
            y = Y[ks].mean(0)
            traj = Y[i * h:(i + 1) * h]
            conv.append(np.abs(traj - Y[ks[-1]]).max(1))
            rows.append((pose, y))
    return rows, np.array(conv)


if __name__ == '__main__':
    prefix = sys.argv[1] if len(sys.argv) > 1 else 'pose_orig'
    sub = 'sweep10o' if prefix == 'pose_orig' else 'sweep10'
    jp = '/tmp/v15sp/poses10/jobs_poses10_%s.json' % ('orig' if prefix == 'pose_orig' else 'slim')
    rows, conv = load(jp, run + sub + '/bs', prefix)
    print('poses', len(rows))
    print('convergence: max|y(t)-y(last)| by frame in hold:', ' '.join(f'{x:.3f}' for x in np.nanmedian(conv, 0)))
    print('   p90:', ' '.join(f'{x:.3f}' for x in np.nanpercentile(conv, 90, 0)))
    sets = {}
    for pose, y in rows:
        sets.setdefault(pose['_set'], []).append((pose, y))
    show = ['jawOpen', 'mouthClose', 'mouthPucker', 'mouthFunnel', 'press', 'mouthRollLower', 'mouthRollUpper', 'mouthShrugLower', 'G']
    for name, lst in sorted(sets.items()):
        if name == 'rand':
            continue
        print('==', name)
        var = [k for k in lst[0][0] if k not in ('_set', 'jawOpen')]
        for pose, y in sorted(lst, key=lambda t: (t[0]['jawOpen'], [t[0].get(k, 0) for k in var])):
            print('  jaw %.2f %s | %s' % (pose['jawOpen'], ' '.join(f'{k}={pose[k]:.2f}' for k in var),
                                         ' '.join(f'{s[:6]}={y[OUT.index(s)]:.3f}' for s in show)))
