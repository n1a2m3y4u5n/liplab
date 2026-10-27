import test from 'node:test'
import assert from 'node:assert/strict'
import { authErrorMessage } from './authMessage.js'

test('응답이 없으면 연결 안내, 비밀번호를 의심하지 않는다', () => {
  assert.match(authErrorMessage(undefined, 'login', { code: 'ERR_NETWORK' }), /인터넷 연결/)
  assert.match(authErrorMessage(undefined, 'login', { code: 'ECONNABORTED' }), /너무 늦어요/)
})
test('서버 오류·요청 과다는 입력 오류와 구분한다', () => {
  assert.match(authErrorMessage(undefined, 'login', { response: { status: 502 } }), /서버에 문제/)
  assert.match(authErrorMessage(undefined, 'signup', { response: { status: 429 } }), /너무 많아요/)
})
test('로그인 실패·중복·검증 오류 문구', () => {
  const e = (status) => ({ response: { status } })
  assert.equal(authErrorMessage('Incorrect email or password', 'login', e(401)), '이메일·비밀번호를 확인해 주세요.')
  assert.equal(authErrorMessage('Email already registered', 'signup', e(400)), '이미 가입된 이메일이에요.')
  const long = [{ loc: ['body', 'password'], msg: 'Value error, 비밀번호는 72바이트(한글 약 24자, 영문 72자)까지 쓸 수 있어요.' }]
  assert.match(authErrorMessage(long, 'signup', e(422)), /72바이트/)
  const short = [{ loc: ['body', 'password'], msg: 'String should have at least 6 characters' }]
  assert.equal(authErrorMessage(short, 'signup', e(422)), '비밀번호는 6자 이상 입력해주세요.')
})
