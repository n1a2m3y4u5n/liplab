// viseme→모프타깃 매핑 무결성 검증. 실행: node --test
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { VISEME_BLENDSHAPES, VISEME_TONGUE, ACTIVE_MORPH_KEYS } from './visemeShapes.js'

const SRC = readFileSync(fileURLToPath(new URL('./visemeShapes.js', import.meta.url)), 'utf8')

/**
 * 소스에서 객체 리터럴의 최상위 숫자 키를 순서대로 뽑는다.
 * 런타임 객체로는 중복을 볼 수 없다(JS가 이미 뒤엣것으로 덮어버림) — 그래서 소스를 읽는다.
 */
function topLevelKeys(exportName) {
  const start = SRC.indexOf(`export const ${exportName} = {`)
  assert.ok(start >= 0, `${exportName} 선언을 찾지 못함`)
  const body = SRC.slice(start)
  const end = body.indexOf('\n}')
  assert.ok(end > 0, `${exportName} 본문 끝을 찾지 못함`)
  // 들여쓰기 2칸의 `숫자:` 만 최상위 키다(중첩된 모프 키는 한 줄 안에 있어 걸리지 않는다).
  return [...body.slice(0, end).matchAll(/^ {2}(\d+):/gm)].map((m) => Number(m[1]))
}

function duplicates(list) {
  const seen = new Set()
  const dup = new Set()
  for (const k of list) (seen.has(k) ? dup : seen).add(k)
  return [...dup]
}

test('VISEME_BLENDSHAPES: 중복 정의된 viseme이 없다', () => {
  // 과거 깨진 머지로 1·2·4·6·7·10이 두 번씩 정의돼, 앞의 정의(육안 검증본)가 조용히
  // 덮인 적이 있다. JS는 이를 오류로 알리지 않으므로 테스트가 유일한 방어선이다.
  const dup = duplicates(topLevelKeys('VISEME_BLENDSHAPES'))
  assert.deepEqual(dup, [], `중복 정의된 viseme: ${dup.join(', ')} — 뒤엣것이 앞엣것을 덮는다`)
})

test('VISEME_TONGUE: 중복 정의된 viseme이 없다', () => {
  const dup = duplicates(topLevelKeys('VISEME_TONGUE'))
  assert.deepEqual(dup, [], `중복 정의된 viseme: ${dup.join(', ')}`)
})

test('개발일지 6절의 육안 검증값이 실제로 적용된다', () => {
  // 브라우저 스크린샷으로 확정한 값들. 중복 키에 덮이면 여기서 먼저 깨진다.
  assert.deepEqual(VISEME_BLENDSHAPES[4], { mouthFunnel: 0.62, mouthPucker: 0.48, jawOpen: 0.05 },
    '원순모음(4) — jaw 최소·funnel 강화로 치아 노출 없이 둥근 내밈')
  assert.deepEqual(VISEME_BLENDSHAPES[9], { jawOpen: 0.16, mouthFunnel: 0.38, mouthPucker: 0.32 },
    '이중모음(9) — v4와 v2의 중간')
})

test('개발일지 2절의 ARKit 감사 결과가 실제로 적용된다', () => {
  // 감사에서 "모델에 있는데도 안 쓰이고 있던" 셰이프를 넣은 결과들.
  assert.equal(VISEME_BLENDSHAPES[1].mouthClose, 0.35, '양순음(1) — 두 입술 확실히 폐쇄')
  assert.ok(VISEME_BLENDSHAPES[2].mouthUpperUpLeft > 0, '개방모음(2) — 윗입술도 살짝 올림')
  assert.ok(VISEME_BLENDSHAPES[6].mouthUpperUpLeft > 0, '치경음(6) — 윗니 노출(tongueOut 대체)')
  assert.ok(VISEME_BLENDSHAPES[3].mouthUpperUpLeft > 0, '전설모음(3) — 윗니 노출')
})

test('혀 모프가 있는 viseme은 혀가 보일 만큼 턱이 열려 있다', () => {
  // 혀 렌더링[YMJ] 작업의 의도: 6·7·10은 혀(VISEME_TONGUE)가 보여야 하므로 턱을 더 연다.
  // 중복 키 정리 때 입술값만 살리고 이 턱 열림을 잃으면 혀가 입 안에 가려진다.
  for (const v of [6, 7, 10]) {
    assert.ok(VISEME_TONGUE[v], `viseme ${v}는 혀 모프를 가져야 함`)
    assert.ok(VISEME_BLENDSHAPES[v].jawOpen >= 0.18,
      `viseme ${v}의 jawOpen(${VISEME_BLENDSHAPES[v].jawOpen})이 너무 작아 혀가 안 보인다`)
  }
})

test('모든 가중치는 0~1 범위', () => {
  for (const [vid, shape] of Object.entries(VISEME_BLENDSHAPES)) {
    for (const [key, w] of Object.entries(shape)) {
      assert.ok(w >= 0 && w <= 1, `viseme ${vid}의 ${key}=${w}가 범위를 벗어남`)
    }
  }
})

test('ACTIVE_MORPH_KEYS는 실제 쓰이는 키의 합집합이다', () => {
  const used = new Set(Object.values(VISEME_BLENDSHAPES).flatMap((s) => Object.keys(s)))
  assert.deepEqual([...ACTIVE_MORPH_KEYS].sort(), [...used].sort())
})
