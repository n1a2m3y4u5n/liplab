import json
d = json.load(open('/tmp/v15sp/work/talkers_cf.json'))
rows = []
for c in ('t1_1.0', 't2_1.0', 't3_1.0', 't4_1.0', 'h1_1.0', 'h2_1.0', 't1_2.0', 't2_2.0', 't3_2.0', 't4_2.0', 'h1_2.0', 'h2_2.0'):
    n, o = d['new'][c], d['old'][c]
    rows.append(f"{c.replace('_', ' ')}배 ρ {o['rho']:.2f} → {n['rho']:.2f}, A 범위 안 {o['amp_n_in']} → {n['amp_n_in']}, 원순 범위 안 {n['rounded']:.2f}")
rho_new = [d['new'][c]['rho'] for c in d['new']]
amp_new = [d['new'][c]['amp_n_in'] for c in d['new']]
txt = (f"ρ는 12조건 모두 0.82~0.88(지금 0.46~0.60)로 확인 LOO 하위 10백분위 근처나 위다. 2.0배 A 범위 안 무리는 {min(amp_new)}~{max(amp_new)}개"
       f"(지금 0~3개)이고, 돌출 배율이 1보다 큰 화자 2·4·5에서 9~11개로 많다(화자 4의 2.0배 11개). 대신 이 화자들은 1.0배 원순 돌출이 실제 90백분위를"
       f" 넘는 구간이 많다(원순 범위 안 0.17~0.37). 조건별: " + '; '.join(rows) + '. 기본 얼굴의 진폭이 확인 화자 분포의 아래쪽에 있다는 10.2의 해석과 맞는다.')
p = '/tmp/v15sp/work/sec10.md'
s = open(p).read().replace('__TALKERS__', txt)
open(p, 'w').write(s)
print(txt[:300])
