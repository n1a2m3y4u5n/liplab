import test from 'node:test'
import assert from 'node:assert/strict'
import { loadCoachingResult } from './speakCoaching.js'

const initial = () => ({ coaching_id: 'job', coaching_pending: true, score: 83, phones: [{ value: 70 }] })
function harness(request) {
  let state = initial(), current = true
  return {
    get state() { return state },
    change() { current = false; state = { coaching_id: 'next', score: 91 } },
    run: () => loadCoachingResult({ id: 'job', request, isCurrent: () => current, update: (fn) => { state = fn(state) } }),
  }
}
test('연결 실패 뒤 같은 작업 재조회: 점수·소리 결과는 유지', async () => {
  const ids = []
  const h = harness(async (id) => { ids.push(id); if (ids.length === 1) throw Error('offline'); return { coaching: '잘했어요.' } })
  await h.run()
  assert.equal(h.state.coaching_retry, true)
  assert.equal(h.state.coaching_error, '수신 지연')
  assert.equal(h.state.coaching_pending, false)
  assert.equal(h.state.score, 83)
  assert.deepEqual(h.state.phones, initial().phones)
  await h.run()
  assert.deepEqual(ids, ['job', 'job'])
  assert.equal(h.state.coaching, '잘했어요.')
  assert.equal(h.state.coaching_error, null)
})
for (const status of [404, 500]) test(`${status}: 짧은 실패 상태, 재조회 버튼 없음`, async () => {
  const h = harness(async () => { throw { response: { status } } })
  await h.run()
  assert.equal(h.state.coaching_retry, false)
  assert.equal(h.state.coaching_error, status === 404 ? '코칭 만료' : '코칭 실패')
  assert.equal(h.state.score, 83)
})
test('시간 초과는 재조회 가능', async () => {
  const h = harness(async () => { throw { response: { status: 504 } } })
  await h.run()
  assert.equal(h.state.coaching_retry, true)
})
test('빈 코칭도 사라지지 않고 안내', async () => {
  const h = harness(async () => ({ coaching: null }))
  await h.run()
  assert.equal(h.state.coaching_error, '코칭 없음')
})
for (const failed of [false, true]) test(`다음 시도 뒤 늦은 ${failed ? '실패' : '성공'}는 무시`, async () => {
  let resolve, reject
  const h = harness(() => new Promise((a, b) => { resolve = a; reject = b }))
  const running = h.run()
  h.change()
  if (failed) reject(Error('offline')); else resolve({ coaching: '이전 코칭' })
  await running
  assert.deepEqual(h.state, { coaching_id: 'next', score: 91 })
})
