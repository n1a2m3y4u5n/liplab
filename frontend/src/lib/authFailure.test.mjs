import test from 'node:test'
import assert from 'node:assert/strict'
import { AxiosHeaders } from 'axios'
import { handleUnauthorized } from './authFailure.js'

function setup() {
  const calls = []
  const session = { token: 'old-token', logout() { calls.push('logout'); this.token = null } }
  const fail = (url = '/auth/me', token = 'old-token', status = 401, headers) => {
    handleUnauthorized({ response: { status }, config: { url, headers: headers ?? { Authorization: `Bearer ${token}` } } },
      session, () => calls.push('reload'))
  }
  return { calls, session, fail }
}

test('현재 토큰 만료는 로그아웃·새로고침을 한 번만 실행한다', () => {
  const { fail, calls } = setup()
  fail(); fail()
  assert.deepEqual(calls, ['logout', 'reload'])
})

test('계정 전환 전 요청의 늦은 401은 새 계정과 학습 화면을 유지한다', () => {
  const { session, fail, calls } = setup()
  session.token = 'new-token'
  fail()
  assert.equal(session.token, 'new-token')
  assert.deepEqual(calls, [])
})

test('로그인·가입·데모 실패는 입력 오류 안내를 위해 화면을 유지한다', () => {
  const { fail, calls, session } = setup()
  for (const url of ['/auth/login', '/auth/login?next=learn', '/auth/register', '/auth/demo']) fail(url)
  assert.equal(session.token, 'old-token')
  assert.deepEqual(calls, [])
})

test('토큰 없이 시작한 공개 요청은 로그인 뒤 실패해도 세션을 유지한다', () => {
  const { fail, calls } = setup()
  fail('/auth/me', null, 401, {})
  handleUnauthorized({ response: { status: 401 } }, { token: 'new-token' }, () => calls.push('reload'))
  assert.deepEqual(calls, [])
})

test('네트워크·서버 오류는 현재 세션을 유지한다', () => {
  const { fail, calls } = setup()
  for (const status of [null, 400, 403, 500, 504]) fail('/auth/me', 'old-token', status)
  assert.deepEqual(calls, [])
})

test('AxiosHeaders와 소문자 헤더도 현재 토큰 만료를 처리한다', () => {
  for (const headers of [new AxiosHeaders({ authorization: 'Bearer old-token' }), { authorization: 'Bearer old-token' }]) {
    const { fail, calls } = setup()
    fail('/auth/me', 'old-token', 401, headers)
    assert.deepEqual(calls, ['logout', 'reload'])
  }
})
