// relDay 검사. 실행: npm test (node --test)
import test from 'node:test'
import assert from 'node:assert/strict'
import { relDay } from './relDay.js'

const now = new Date(2026, 8, 24, 10, 0)   // 현지 9/24 10:00

test('relDay: 달력 날짜 차이로 오늘·어제·N일 전·N주 전', () => {
  assert.equal(relDay('2026-09-24', now), '오늘')
  assert.equal(relDay('2026-09-23', now), '어제')
  assert.equal(relDay('2026-09-21', now), '3일 전')
  assert.equal(relDay('2026-09-18', now), '6일 전')
  assert.equal(relDay('2026-09-17', now), '1주 전')
  assert.equal(relDay('2026-09-03', now), '3주 전')
})

test('relDay: 시각이 있으면 현지 날짜로 본다(어젯밤 늦게 한 것은 어제)', () => {
  assert.equal(relDay(new Date(2026, 8, 23, 23, 50).toISOString(), now), '어제')
  assert.equal(relDay(new Date(2026, 8, 24, 0, 5).toISOString(), now), '오늘')
})

test('relDay: 비었거나 읽을 수 없으면 빈 문자열, 미래 시각은 오늘', () => {
  assert.equal(relDay(null, now), '')
  assert.equal(relDay('아님', now), '')
  assert.equal(relDay('2026-09-25', now), '오늘')
})
