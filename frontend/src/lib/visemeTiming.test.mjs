import { test } from 'node:test'
import assert from 'node:assert/strict'
import { easeInOutCubic, transitionTime, transitionProgress, MIN_TRANSITION_MS } from './visemeTiming.js'

test('easeInOutCubic: 끝점 고정, 가운데 0.5, 단조 증가', () => {
  assert.equal(easeInOutCubic(0), 0)
  assert.equal(easeInOutCubic(1), 1)
  assert.equal(easeInOutCubic(0.5), 0.5)
  assert.equal(easeInOutCubic(-1), 0)
  assert.equal(easeInOutCubic(2), 1)
  let prev = -1
  for (let i = 0; i <= 20; i++) { const v = easeInOutCubic(i / 20); assert.ok(v >= prev); prev = v }
})

test('transitionTime: 프레임 길이의 60%를 넘지 않고 재생 속도로 나눈다', () => {
  assert.equal(transitionTime(30, 120, 1), 30)        // 30ms < 72ms
  assert.equal(transitionTime(80, 100, 1), 60)        // 60%로 잘림
  assert.equal(transitionTime(40, 200, 2), 20)        // 2배속이면 절반
  assert.equal(transitionTime(0, 120, 1), MIN_TRANSITION_MS)   // 0이어도 한 화면은 옮긴다
  assert.equal(transitionTime(undefined, 120, 1), null)        // 값이 없으면 예전 방식
})

test('transitionProgress: 전환 시간이 지나면 목표에 닿는다(빠른 재생에서도)', () => {
  // 2배속, 프레임 80ms·전환 40ms → 20ms 안에 목표. 예전 고정 비율 방식은 40ms 동안 약 59%까지만 갔다.
  assert.equal(transitionProgress(20, 40, 80, 2), 1)
  assert.ok(transitionProgress(10, 40, 80, 2) > 0 && transitionProgress(10, 40, 80, 2) < 1)
  assert.equal(transitionProgress(0, 30, 120, 1), 0)
})
