import { test } from 'node:test'
import assert from 'node:assert/strict'
import { easeInOutCubic, transitionTime, transitionProgress, MIN_TRANSITION_MS, slowWeakFrames, pickSlowVisemes, effectiveSpeed } from './visemeTiming.js'

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

test('약한 입모양 프레임만 느리게(duration·transition ×1.35), 약점이 없으면 그대로', () => {
  const frames = [{ viseme: 1, duration_ms: 100, transition_ms: 40 }, { viseme: 5, duration_ms: 200, transition_ms: 60 }]
  const out = slowWeakFrames(frames, new Set([1]))
  assert.deepEqual(out[0], { viseme: 1, duration_ms: 135, transition_ms: 54, slowed: true })
  assert.equal(out[1], frames[1])
  assert.equal(slowWeakFrames(frames, new Set()), frames)
  const pick = pickSlowVisemes([{ viseme_id: 1, attempts: 9, mastery: 0.4 }, { viseme_id: 2, attempts: 3, mastery: 0.2 },
    { viseme_id: 3, attempts: 8, mastery: 0.9 }, { viseme_id: 4, attempts: 6, mastery: 0.6 }])
  assert.deepEqual([...pick], [1, 4])
})

test('effectiveSpeed: 적응 감속과 학습자 속도를 곱한 실제 재생 속도', () => {
  const orig = [{ viseme: 1, duration_ms: 100 }, { viseme: 2, duration_ms: 100 }]
  assert.equal(effectiveSpeed(orig, orig), 1)
  const slowed = slowWeakFrames(orig, new Set([1]))
  assert.ok(effectiveSpeed(orig, slowed) < 1)
  assert.equal(effectiveSpeed(orig, slowed), Math.round((200 / 235) * 1000) / 1000)
  assert.equal(effectiveSpeed(orig, orig, 1.25), 1.25)
  assert.equal(effectiveSpeed([], [], 1), 1)
})
