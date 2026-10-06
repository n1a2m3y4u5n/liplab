import { test } from 'node:test'
import assert from 'node:assert/strict'
import { nextDelay, recordLateness, renderTimingSummary, resetRenderTiming } from './frameClock.js'

test('제때면 프레임 길이만큼, 재생 속도를 나눈다', () => {
  assert.deepEqual(nextDelay({ dueAt: 1000, durationMs: 100, speed: 1, now: 1000 }), { delay: 100, nextDue: 1100 })
  assert.deepEqual(nextDelay({ dueAt: 1000, durationMs: 100, speed: 2, now: 1000 }), { delay: 50, nextDue: 1050 })
})

test('늦으면 다음 대기를 줄여 따라잡되 절반 아래로는 줄이지 않는다', () => {
  // 30ms 늦게 시작: 70ms만 기다려 원래 시각(1100)에 맞춘다
  assert.deepEqual(nextDelay({ dueAt: 1000, durationMs: 100, now: 1030 }), { delay: 70, nextDue: 1100 })
  // 80ms 늦음: 최소 50ms는 보여 주고 그 뒤로 due를 민다
  assert.deepEqual(nextDelay({ dueAt: 1000, durationMs: 100, now: 1080 }), { delay: 50, nextDue: 1130 })
})

test('처음(due 없음)은 지금부터', () => {
  assert.deepEqual(nextDelay({ dueAt: undefined, durationMs: 80, now: 500 }), { delay: 80, nextDue: 580 })
})

test('지연 기록 요약', () => {
  resetRenderTiming()
  ;[0, 10, 30, 60].forEach(recordLateness)
  assert.deepEqual(renderTimingSummary(), { frames: 4, meanLateMs: 25, maxLateMs: 60, over20Rate: 0.5, over50Rate: 0.25 })
})
