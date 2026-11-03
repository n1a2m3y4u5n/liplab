import test from 'node:test'
import assert from 'node:assert/strict'
import { fetchVisemeFrames, createLatest, createResubmit } from './visemeLoad.js'

test('프레임이 오면 ok', async () => {
  const r = await fetchVisemeFrames(async () => [{ viseme: 1 }], '가')
  assert.deepEqual(r, { ok: true, frames: [{ viseme: 1 }] })
})
test('오류·빈 응답·배열 아님은 실패', async () => {
  assert.equal((await fetchVisemeFrames(async () => { throw new Error('x') }, '가')).ok, false)
  assert.equal((await fetchVisemeFrames(async () => [], '가')).ok, false)
  assert.equal((await fetchVisemeFrames(async () => ({}), '가')).ok, false)
})
test('늦은 응답은 버린다', () => {
  const l = createLatest()
  const a = l.next(); const b = l.next()
  assert.equal(l.isCurrent(a), false); assert.equal(l.isCurrent(b), true)
  l.cancel(); assert.equal(l.isCurrent(b), false)
})
test('다시 보내기는 한 번에 하나만', async () => {
  const r = createResubmit()
  let calls = 0
  let release
  const p = r.run(() => { calls++; return new Promise((res) => { release = res }) })
  assert.equal(await r.run(async () => { calls++ }), null)   // 보내는 중이면 무시
  release(); assert.equal(await p, true); assert.equal(calls, 1)
  assert.equal(await r.run(async () => { throw new Error('x') }), false)
  assert.equal(r.busy, false)
  assert.equal(await r.run(async () => {}), true)             // 실패 뒤에도 다시 보낼 수 있다
})
