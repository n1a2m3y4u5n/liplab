// sharedRequest 검사. 실행: npm test (node --test)
import test from 'node:test'
import assert from 'node:assert/strict'
import { createInflight } from './sharedRequest.js'

// 부를 때마다 수를 세고, 끝낼 때를 테스트가 정하는 가짜 요청
function fakeFetch() {
  const calls = []
  const fetcher = () => new Promise((resolve, reject) => { calls.push({ resolve, reject }) })
  return { calls, fetcher }
}

test('페이지와 패널이 같은 순간 부르면 요청은 한 번이고 같은 응답을 나눠 받는다', async () => {
  const share = createInflight()
  const { calls, fetcher } = fakeFetch()
  const page = share('overview', fetcher)
  const rail = share('overview', fetcher)
  assert.equal(calls.length, 1)
  assert.equal(page, rail)
  const body = { total_minutes: 3 }
  calls[0].resolve(body)
  assert.equal(await page, body)
  assert.equal(await rail, body)
})

test('응답이 끝나면 바로 지워, 다음 호출은 새로 보낸다(끝난 값을 다시 쓰지 않음)', async () => {
  const share = createInflight()
  const { calls, fetcher } = fakeFetch()
  const first = share('due', fetcher)
  calls[0].resolve({ items: [1, 2] })
  await first
  assert.equal(share.size(), 0)
  const second = share('due', fetcher)
  assert.equal(calls.length, 2)
  calls[1].resolve({ items: [] })
  assert.deepEqual(await second, { items: [] })
})

test('실패도 함께 받고, 끝나면 지워 다시 부를 수 있다', async () => {
  const share = createInflight()
  const { calls, fetcher } = fakeFetch()
  const a = share('due', fetcher)
  const b = share('due', fetcher)
  calls[0].reject(new Error('503'))
  await assert.rejects(a, /503/)
  await assert.rejects(b, /503/)
  assert.equal(share.size(), 0)
  share('due', fetcher)
  assert.equal(calls.length, 2)
})

test('키가 다르면 따로 보낸다(사용자·시간대가 다른 요청을 섞지 않음)', () => {
  const share = createInflight()
  const { calls, fetcher } = fakeFetch()
  share('overview:tokA:-540', fetcher)
  share('overview:tokB:-540', fetcher)
  share('overview:tokA:0', fetcher)
  assert.equal(calls.length, 3)
})

test('clear() 뒤에 부르면 진행 중인 요청과 섞지 않고 새로 보낸다(기록을 바꾸는 요청 뒤)', async () => {
  const share = createInflight()
  const { calls, fetcher } = fakeFetch()
  const before = share('due', fetcher)
  share.clear()
  const after = share('due', fetcher)
  assert.equal(calls.length, 2)
  assert.notEqual(before, after)
  // 먼저 보낸 요청이 늦게 끝나도 새 약속을 지우지 않는다
  calls[0].resolve('old')
  await before
  assert.equal(share.size(), 1)
  calls[1].resolve('new')
  assert.equal(await after, 'new')
})

test('fetcher가 동기로 던져도 거부된 약속을 돌려주고 남기지 않는다', async () => {
  const share = createInflight()
  const p = share('x', () => { throw new Error('boom') })
  await assert.rejects(p, /boom/)
  assert.equal(share.size(), 0)
})
