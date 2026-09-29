// 웹캠 입모양 익힘 기록 점수(창 안 상위 k개 중앙값) 검증. 실행: node --test
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { attemptScore, pushAttemptSample, pruneAttempt, ATTEMPT_MS, MIN_FACE_FRAMES } from './mouthAttempt.js'

const frames = (scores, dt = 33) => {
  const win = []
  scores.forEach((s, i) => pushAttemptSample(win, i * dt, s))
  return win
}

test('attemptScore: 얼굴을 잡은 프레임이 모자라면 기록하지 않는다(null)', () => {
  assert.equal(attemptScore([]), null, '얼굴을 잡기 전(표본 없음)은 0점이 아니라 null')
  assert.equal(attemptScore(frames(Array(MIN_FACE_FRAMES - 1).fill(90))), null)
  assert.equal(attemptScore(frames(Array(MIN_FACE_FRAMES).fill(90))), 90)
})

test('attemptScore: 한두 프레임 튐은 합격선을 만들지 못한다', () => {
  // 0.5초 대부분 30점, 한 프레임·두 프레임만 100점: 예전 한 프레임 최고점이면 100점(합격)
  const one = frames([...Array(14).fill(30), 100])
  const two = frames([...Array(13).fill(30), 100, 100])
  assert.equal(attemptScore(one), 30)
  assert.equal(attemptScore(two), 30)
  assert.ok(attemptScore(two) < 60)
})

test('attemptScore: 목표 입모양을 잠깐이라도 유지하면 그 점수가 남는다', () => {
  // 1.5초 동안 '마마마'처럼 닫힘(85점)을 여러 번 만들었다. 닫힘 프레임이 창의 20% 이상이면 85
  const scores = []
  for (let r = 0; r < 3; r++) scores.push(...Array(10).fill(20), ...Array(5).fill(85))
  assert.equal(attemptScore(frames(scores)), 85)
})

test('pushAttemptSample: ATTEMPT_MS보다 오래된 표본은 버린다', () => {
  const win = []
  pushAttemptSample(win, 0, 100)
  for (let t = 1000; t <= ATTEMPT_MS + 1000; t += 100) pushAttemptSample(win, t, 20)
  assert.ok(win.every((w) => w.s === 20), '5초 넘은 옛 최고점은 창에서 빠진다')
  assert.equal(attemptScore(win), 20)
})

test('pruneAttempt: 얼굴을 놓친 채 5초가 지나면 창이 비어 기록하지 않는다', () => {
  const win = frames(Array(30).fill(90))
  pruneAttempt(win, 30 * 33 + ATTEMPT_MS + 1)
  assert.equal(win.length, 0)
  assert.equal(attemptScore(win), null)
})
