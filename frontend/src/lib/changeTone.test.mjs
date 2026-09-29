// changeTone 검사. 실행: npm test (node --test)
import test from 'node:test'
import assert from 'node:assert/strict'
import { changeTone, ciText } from './changeTone.js'

test('changeTone: 구간이 0을 벗어날 때만 색, 아니면 중립', () => {
  assert.equal(changeTone(true, 0.2), 'bg-good-tint text-good-text')
  assert.equal(changeTone(true, -12.5), 'bg-bad-tint text-bad-text')
  assert.equal(changeTone(false, -0.3), 'bg-fill text-ink-muted')
  assert.equal(changeTone(undefined, 0.3), 'bg-fill text-ink-muted')   // 구간이 없는 옛 응답
  assert.equal(changeTone(true, 0), 'bg-fill text-ink-muted')
  assert.equal(changeTone(true, null), 'bg-fill text-ink-muted')
})

test('ciText: 정답률(0~1)과 %p 모두', () => {
  assert.equal(ciText([-0.214, 0.126]), '95% 구간 −21~+13%p')
  assert.equal(ciText([-8.4, 15.2], 1), '95% 구간 −8~+15%p')
  assert.equal(ciText(null), '')
  assert.equal(ciText([0.1]), '')
})
