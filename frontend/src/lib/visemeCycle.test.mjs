import { test } from 'node:test'
import assert from 'node:assert/strict'
import { visemeCycleSteps } from './visemeCycle.js'

test('이중모음(9)은 원순 → 개방으로 움직이고, 나머지는 목표 ↔ 중립', () => {
  assert.deepEqual(visemeCycleSteps(9).map((s) => s.v), [4, 2, 15])
  assert.deepEqual(visemeCycleSteps(3).map((s) => s.v), [3, 15])
  assert.ok(visemeCycleSteps(1).every((s) => s.ms > 0 && s.t > 0))
})
