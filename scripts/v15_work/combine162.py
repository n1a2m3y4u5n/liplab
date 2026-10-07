"""사전 등록 6절의 '확인 문장 162클립'(V2 분석 규칙: 문장 id가 확인 절반에 있으면 셈)을 맞추려고, 확인 렌더 151문장에
탐색 렌더(같은 동결 표 D, 주입 경로) 가운데 확인 절반에도 나오는 문장 11개를 더한 폴더를 만든다(심볼릭 링크)."""
import json, os
L = '/Users/namyunsu/Downloads/liplab-lab/data/'
CF = L + 'pod_runs/20261007_zszjqyqz5m03q2/v15/cf_default'
EX = L + 'pod_runs/20261007_zszjqyqz5m03q2/v15/ex_D'
OUT = '/tmp/v15sp/work/cf162'
sel = json.load(open(L + 'v2_avatar/sel.json'))
sid_half = {}
for e in sel['sentences']:
    sid_half.setdefault(e['sid'], set()).add(e['half'])
for sub in ('renders', 'bs'):
    os.makedirs(os.path.join(OUT, sub), exist_ok=True)
n = {'cf': 0, 'ex': 0}
cf_sids = set()
for fn in os.listdir(CF + '/renders'):
    if fn.endswith('.sched.json'):
        cf_sids.add(fn.split('_')[1])
for src, tag in ((CF, 'cf'), (EX, 'ex')):
    for fn in os.listdir(src + '/renders'):
        if not fn.endswith('.sched.json'):
            continue
        sid = fn.split('_')[1]
        if tag == 'ex' and (sid in cf_sids or 1 not in sid_half.get(sid, ())):
            continue
        jid = fn[:-len('.sched.json')]
        for sub, name in (('renders', fn), ('bs', jid + '.json')):
            dst = os.path.join(OUT, sub, name)
            if not os.path.exists(dst):
                os.symlink(os.path.join(src, sub, name), dst)
        n[tag] += 1
print(n)
