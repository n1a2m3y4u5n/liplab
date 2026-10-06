import { test } from 'node:test'
import assert from 'node:assert/strict'
import { guardRendererFactory } from './safeRenderer.js'

test('생성이 성공하면 렌더러를 그대로 돌려주고 onFail을 부르지 않는다', () => {
  const fake = { isWebGLRenderer: true }
  let failed = 0
  let seen = null
  const make = guardRendererFactory((p) => { seen = p; return fake }, () => { failed += 1 })
  const props = { canvas: {}, alpha: true }
  assert.equal(make(props), fake)
  assert.equal(seen, props)
  assert.equal(failed, 0)
})

test('컨텍스트 생성이 던지면 onFail에 같은 오류를 넘기고 다시 던진다', () => {
  const err = new Error('Error creating WebGL context.')
  const got = []
  const make = guardRendererFactory(() => { throw err }, (e) => got.push(e))
  assert.throws(() => make({}), (e) => e === err)
  assert.deepEqual(got, [err])
})

test('생성기가 빈 값을 돌려줘도 실패로 본다', () => {
  let failed = 0
  const make = guardRendererFactory(() => null, () => { failed += 1 })
  assert.throws(() => make({}))
  assert.equal(failed, 1)
})

test('onFail이 던져도 원래 생성 오류가 나간다', () => {
  const err = new Error('Error creating WebGL context.')
  const make = guardRendererFactory(() => { throw err }, () => { throw new Error('알림 실패') })
  assert.throws(() => make({}), (e) => e === err)
})
