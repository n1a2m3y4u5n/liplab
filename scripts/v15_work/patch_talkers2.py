"""patch_talkers.py를 줄인 값(talkers_shrunk_D.json)을 읽도록 고친다."""
p = '/tmp/v15sp/work/patch_talkers.py'
s = open(p).read()
s = s.replace("sel = json.load(open('/tmp/v15sp/work/v5_talkers.json'))",
              "sel = {t['id']: t for t in json.load(open('/tmp/v15sp/work/talkers_shrunk_D.json'))}")
old_rows = """    v = sel[t]; jit, width, coart = OLD[t]
    rows.append(f"  {{ id: '{t}', label: '{LBL[t][0]}', heldOut: {LBL[t][1]}, rate: {v['rate']:.2f}, amp: {v['amp']:.2f}, width: {width:.2f}, "
                f"protrusion: {v['protrusion']:.2f}, coart: {coart:.2f}, jitter: {jit:.2f} }},")"""
new_rows = """    v = sel[t]; jit = OLD[t][0]
    def f(x):
        return f'{x:.2f}' if abs(x * 100 - round(x * 100)) < 1e-9 else f'{x:.3f}'
    rows.append(f"  {{ id: '{t}', label: '{LBL[t][0]}', heldOut: {LBL[t][1]}, rate: {f(v['rate'])}, amp: {f(v['amp'])}, width: {f(v['width'])}, "
                f"protrusion: {f(v['protrusion'])}, coart: {f(v['coart'])}, jitter: {jit:.2f} }},")"""
assert s.count(old_rows) == 1
s = s.replace(old_rows, new_rows)
old_c = """// 538 중앙값에 가깝다는 점(V2 10.5절)을 기준으로 한 배율이다. 입술 폭은 538 화자의 폭 진폭이 0에 가까워 사람 분포로 정할 수 없어
// 예전 값을 두고, 동시조음·흔들림도 이 자료로 잴 수 없어 예전 값을 둔다."""
new_c = """// 538 중앙값에 가깝다는 점(V2 10.5절)을 기준으로 한 배율이다. 입술 폭은 538 화자의 폭 진폭이 0에 가까워 사람 분포로 정할 수 없어
// 예전 값에서 출발하고, 동시조음·흔들림도 이 자료로 잴 수 없어 예전 값에서 출발한다. 그 뒤 판별 기준 (a)~(d)를 V15 표로 걸어 어긋난
// 화자 3·5·6은 talker-variation.md 4절 규칙(위반 쌍에 관여하는 매개변수만 1에서 벗어난 폭을 5%씩)으로 줄였다(scripts/v15_talker_shrink.mjs)."""
assert s.count(old_c) == 1
s = s.replace(old_c, new_c)
open(p, 'w').write(s)
print('ok')
