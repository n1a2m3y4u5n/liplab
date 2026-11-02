import test from 'node:test'
import assert from 'node:assert/strict'
import { entranceMotion, UI_MOTION } from './uiMotion.js'

test('동작 최소화에서는 등장 위치·크기 변화와 지연이 없다', () => {
  for (const kind of ['page', 'card', 'complete']) {
    const m = entranceMotion(true, kind)
    assert.equal(m.initial, false)
    assert.deepEqual(m.animate, { opacity: 1, y: 0, scale: 1 })
    assert.equal(m.transition.duration, 0)
    assert.equal(m.transition.delay, undefined)
  }
})
test('표현 모션은 짧고 공통 곡선을 사용하며 응답 지연을 넣지 않는다', () => {
  for (const kind of ['page', 'card', 'complete']) {
    const m = entranceMotion(false, kind)
    assert.ok(m.transition.duration <= 0.3)
    assert.deepEqual(m.transition.ease, UI_MOTION.ease)
    assert.equal(m.transition.delay, undefined)
    assert.ok(m.initial.y <= 6)
  }
})
