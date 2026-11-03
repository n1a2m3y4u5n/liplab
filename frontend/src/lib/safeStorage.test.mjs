import test from 'node:test'
import assert from 'node:assert/strict'
import { lsGet, lsSet } from './safeStorage.js'

const blocked = { getItem() { throw new Error('blocked') }, setItem() { throw new Error('blocked') } }
test('막힌 저장소에서도 던지지 않는다', () => {
  assert.equal(lsGet('k', blocked), null)
  assert.equal(lsSet('k', '1', blocked), false)
  assert.equal(lsGet('k', undefined), null)
})
test('정상 저장소는 읽고 쓴다', () => {
  const m = new Map()
  const s = { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => m.set(k, v) }
  assert.equal(lsSet('k', '1', s), true)
  assert.equal(lsGet('k', s), '1')
})
