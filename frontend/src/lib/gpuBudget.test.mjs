import test from 'node:test'
import assert from 'node:assert/strict'
import { isWeakDevice, markContextLost, contextLost, _resetGpuBudget } from './gpuBudget.js'

test('메모리 4GB 이하 또는 코어 4개 이하면 약한 기기', () => {
  assert.equal(isWeakDevice({ deviceMemory: 4, hardwareConcurrency: 8 }), true)
  assert.equal(isWeakDevice({ deviceMemory: 8, hardwareConcurrency: 4 }), true)
  assert.equal(isWeakDevice({ deviceMemory: 8, hardwareConcurrency: 8 }), false)
})

test('값을 알려 주지 않으면(사파리의 deviceMemory 등) 약한 기기로 보지 않는다', () => {
  assert.equal(isWeakDevice({ hardwareConcurrency: 8 }), false)
  assert.equal(isWeakDevice({}), false)
  assert.equal(isWeakDevice(null), false)
})

test('컨텍스트 손실은 한 번 표시되면 유지된다', () => {
  _resetGpuBudget()
  assert.equal(contextLost(), false)
  markContextLost()
  markContextLost()
  assert.equal(contextLost(), true)
  _resetGpuBudget()
})
