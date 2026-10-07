"""talkers.js: 지금 화자 값(TALKERS_V1)과 V5 재선정 값(TALKERS_V15)을 나란히 두고 표 플래그로 고른다."""
import json, re
P = '/Users/namyunsu/Downloads/liplab/.claude/worktrees/agent-add8fe1d30054f08d/frontend/src/lib/talkers.js'
sel = {t['id']: t for t in json.load(open('/tmp/v15sp/work/talkers_shrunk_D.json'))}
s = open(P, encoding='utf-8').read()
OLD = {'t1': (0.10, 1.10, 1.15), 't2': (0.08, 0.90, 0.85), 't3': (0.15, 1.05, 1.25), 't4': (0.12, 0.88, 0.75), 'h1': (0.12, 0.95, 1.30), 'h2': (0.15, 1.15, 0.70)}
LBL = {'t1': ('화자 1', 'false'), 't2': ('화자 2', 'false'), 't3': ('화자 3', 'false'), 't4': ('화자 4', 'false'), 'h1': ('화자 5', 'true'), 'h2': ('화자 6', 'true')}
rows = []
for t in ('t1', 't2', 't3', 't4', 'h1', 'h2'):
    v = sel[t]; jit = OLD[t][0]
    def f(x):
        return f'{x:.2f}' if abs(x * 100 - round(x * 100)) < 1e-9 else f'{x:.3f}'
    rows.append(f"  {{ id: '{t}', label: '{LBL[t][0]}', heldOut: {LBL[t][1]}, rate: {f(v['rate'])}, amp: {f(v['amp'])}, width: {f(v['width'])}, "
                f"protrusion: {f(v['protrusion'])}, coart: {f(v['coart'])}, jitter: {jit:.2f} }},")
new_block = '''// V5(docs/viseme-calibration-2026-10.md 7절): V15 표와 함께 쓰는 값. 538 탐색 절반 화자 37명의 화자별 배율(무리별 진폭 / 무리 중앙값의
// 무리 사이 중앙값: 벌림 J, 돌출 R)과 음절 속도 배율의 10~90백분위 안에서 정한 분위수(화자 1~4는 25~75 사이, 검사 화자 5·6은 15·85)를
// 고르고, 앱 렌더 시뮬레이션의 반응 곡선(모프 배율 → MediaPipe 진폭 배율)을 거꾸로 따라 모프 배율로 옮겼다. 말 속도는 기본 얼굴 2.0배가
// 538 중앙값에 가깝다는 점(V2 10.5절)을 기준으로 한 배율이다. 입술 폭은 538 화자의 폭 진폭이 0에 가까워 사람 분포로 정할 수 없어
// 예전 값에서 출발하고, 동시조음·흔들림도 이 자료로 잴 수 없어 예전 값에서 출발한다. 그 뒤 판별 기준 (a)~(d)를 V15 표로 걸어 어긋난
// 화자 3·5·6은 talker-variation.md 4절 규칙(위반 쌍에 관여하는 매개변수만 1에서 벗어난 폭을 5%씩)으로 줄였다(scripts/v15_talker_shrink.mjs).
export const TALKERS_V15 = Object.freeze([
''' + '\n'.join(rows) + '''
].map((t) => Object.freeze(t)))

/** 앱이 쓰는 가상 화자 6명(입모양 표와 같은 플래그로 고른다). */
export const TALKERS = VISEME_V15_ENABLED ? TALKERS_V15 : TALKERS_V1'''
if 'TALKERS_V15' not in s:
    s = s.replace("import { VISEME_BLENDSHAPES } from './visemeShapes.js'", "import { VISEME_BLENDSHAPES, VISEME_V15_ENABLED } from './visemeShapes.js'")
    s = s.replace("export const TALKERS = Object.freeze([", "export const TALKERS_V1 = Object.freeze([", 1)
    i = s.index("].map((t) => Object.freeze(t)))") + len("].map((t) => Object.freeze(t)))")
    s = s[:i] + '\n\n' + new_block + s[i:]
else:
    s = re.sub(r'// V5\(docs/viseme-calibration.*?export const TALKERS = VISEME_V15_ENABLED \? TALKERS_V15 : TALKERS_V1', new_block, s, flags=re.S)
open(P, 'w', encoding='utf-8').write(s)
print('PATCHED talkers')
