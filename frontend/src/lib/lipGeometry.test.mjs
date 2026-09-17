// 입술 기하 지표(계획서 그림8) 검증. 실행: node --test
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { lipGeometry } from './lipGeometry.js'

function synthetic() {
  const L = Array.from({ length: 478 }, () => ({ x: 0.5, y: 0.5, z: 0 }))
  L[33] = { x: 0.3, y: 0.4 }; L[263] = { x: 0.7, y: 0.4 }   // 양안 거리 0.4
  L[61] = { x: 0.42, y: 0.6 }; L[291] = { x: 0.58, y: 0.6 } // 입 가로 0.16
  L[0] = { x: 0.5, y: 0.55 }; L[17] = { x: 0.5, y: 0.65 }   // 세로 0.10
  L[13] = { x: 0.5, y: 0.585 }; L[14] = { x: 0.5, y: 0.615 } // 개구도 0.03
  return L
}

test('lipGeometry: 양안 거리로 정규화한 지표', () => {
  const g = lipGeometry(synthetic())
  assert.ok(Math.abs(g.width - 0.4) < 1e-6, 'width = 0.16/0.4')
  assert.ok(Math.abs(g.height - 0.25) < 1e-6, 'height = 0.10/0.4')
  assert.ok(Math.abs(g.inner - 0.075) < 1e-6, 'inner = 0.03/0.4')
  assert.ok(Math.abs(g.aspect - 0.625) < 1e-3, 'aspect = height/width')
  assert.ok(g.perimeter > 0, '둘레는 양수')
})

test('lipGeometry: 잘못된 입력은 null', () => {
  assert.equal(lipGeometry([]), null, '빈 배열')
  assert.equal(lipGeometry(null), null, 'null')
  assert.equal(lipGeometry(new Array(10).fill({ x: 0, y: 0 })), null, '랜드마크 부족')
})

test('lipGeometry: 양안 거리 0이면 null(0 나눗셈 방지)', () => {
  const L = Array.from({ length: 478 }, () => ({ x: 0.5, y: 0.5 }))
  assert.equal(lipGeometry(L), null, '모든 점이 같으면 iod=0 → null')
})
