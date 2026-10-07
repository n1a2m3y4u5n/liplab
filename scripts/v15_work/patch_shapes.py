"""visemeShapes.js: 지금 표를 VISEME_BLENDSHAPES_V1로, V15 표를 나란히 두고 플래그로 고른다. 다시 돌려도 V15 표만 바꾼다."""
import subprocess, sys, re
P = '/Users/namyunsu/Downloads/liplab/.claude/worktrees/agent-add8fe1d30054f08d/frontend/src/lib/visemeShapes.js'
table_js = subprocess.run(['/tmp/v15sp/venv/bin/python', '/tmp/v15sp/work/js_table.py', sys.argv[1], sys.argv[2]],
                          capture_output=True, text=True, check=True).stdout.strip()
default_on = len(sys.argv) > 3 and sys.argv[3] == 'on'
s = open(P, encoding='utf-8').read()
if 'VISEME_BLENDSHAPES_V15' not in s:
    s = s.replace("export const VISEME_BLENDSHAPES = {", "export const VISEME_BLENDSHAPES_V1 = {", 1)
    head = '''
// ── V15(docs/viseme-calibration-2026-10.md): 538 탐색 절반 분포로 다시 맞춘 표 ──
// 오늘 아침 V2 감사(docs/avatar-validity-2026-10.md 10절)에서 위의 표(V1)는 실제 화자와의 거리 구조(RSA)와 진폭 범위 두 기준을 모두
// 넘지 못했다(ㅏ 턱 과다, ㅣ 입꼬리 당김 과다, ㅗㅜ 돌출 과다, 비원순 무리의 돌출 부족, 쉼·전환의 턱 부족). 아래 표는 같은 MediaPipe
// 측정기에서 538 탐색 절반 화자 37명의 무리별 중앙값을 목표로, 모프 → MediaPipe 순방향 사상(정지 자세 3,798개·렌더로 학습)과 앱
// 렌더 궤적 시뮬레이션으로 맞춘 뒤 탐색 문장을 실제로 렌더해 확인했다. 비원순 무리에도 사람처럼 약한 기본 돌출이 있고, 입꼬리 당김은
// 거의 없다(538 화자의 폭 진폭은 0에 가깝다). 확인 절반 판정과 쓰는 방식은 문서 6·10절.
'''
    flag = '''
// 빌드 시 Vite가 import.meta.env를 채운다. node 테스트에서는 비어 있어 기본값을 쓴다.
const ENV = (typeof import.meta !== 'undefined' && import.meta.env) || {}
/** V15 표를 쓰는가. 확인 절반 판정(문서 6절) 결과에 따라 기본값을 정한다. */
export const VISEME_V15_ENABLED = __V15_DEFAULT__

/** 앱이 쓰는 표(V1 또는 V15). 아바타·퀴즈 보기·가상 화자가 모두 이 표를 읽는다. */
export const VISEME_BLENDSHAPES = VISEME_V15_ENABLED ? VISEME_BLENDSHAPES_V15 : VISEME_BLENDSHAPES_V1
'''
    i = s.index('/**\n * 위 매핑에서 실제 사용하는 모프타깃 키의 합집합.')
    s = s[:i] + head.lstrip('\n') + '__V15_TABLE__\n' + flag + '\n' + s[i:]
    s = s.replace('''/**
 * 위 매핑에서 실제 사용하는 모프타깃 키의 합집합.
 * 매 프레임 이 키들만 목표값으로 보간(lerp)하고 나머지는 건드리지 않는다.
 */
export const ACTIVE_MORPH_KEYS = Array.from(
  new Set(Object.values(VISEME_BLENDSHAPES).flatMap((shape) => Object.keys(shape)))
)''', '''/**
 * 두 표(V1·V15)에서 쓰는 모프타깃 키의 합집합.
 * 매 프레임 이 키들만 목표값으로 보간(lerp)하고 나머지는 건드리지 않는다. 어느 표를 쓰든 같은 키 집합이라, 표를 바꿔도 다른 표에서만
 * 쓰던 모프가 얼굴에 남지 않는다(목표에 없는 키는 0으로 돌아간다).
 */
export const ACTIVE_MORPH_KEYS = Array.from(
  new Set([...Object.values(VISEME_BLENDSHAPES_V1), ...Object.values(VISEME_BLENDSHAPES_V15)].flatMap((shape) => Object.keys(shape)))
)''')
else:
    s = re.sub(r'export const VISEME_BLENDSHAPES_V15 = \{.*?\n\}', '__V15_TABLE__', s, flags=re.S)
    s = re.sub(r'export const VISEME_V15_ENABLED = .*', 'export const VISEME_V15_ENABLED = __V15_DEFAULT__', s)
s = s.replace('__V15_TABLE__', table_js)
s = s.replace('__V15_DEFAULT__', "ENV.VITE_VISEME_V15 !== '0'" if default_on else "ENV.VITE_VISEME_V15 === '1'")
open(P, 'w', encoding='utf-8').write(s)
print('PATCHED', 'default_on' if default_on else 'flag_only')
