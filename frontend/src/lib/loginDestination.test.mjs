import test from 'node:test'
import assert from 'node:assert/strict'
import { loginDestination } from './loginDestination.js'
test('공유 주소의 검색 조건과 위치를 유지한다', () => {
 assert.equal(loginDestination({pathname:'/learn/path',search:'?track=speak',hash:'#practice'}), '/learn/path?track=speak#practice')
})
test('로그인과 가입을 오가도 처음 주소를 유지한다', () => {
 assert.equal(loginDestination({pathname:'/signup',search:'',hash:'',state:{loginReturnTo:'/records?track=listen'}}), '/records?track=listen')
})
test('로그인 자체와 외부 주소를 이동 대상으로 쓰지 않는다', () => {
 for (const target of ['/login','/signup','//example.com','https://example.com','/\\example.com']) {
  assert.equal(loginDestination({state:{loginReturnTo:target}}), '/')
 }
})
