import { test } from 'node:test'
import assert from 'node:assert/strict'
import { longestVoicedRun } from './voicing.js'

const track = (segs, dt = 0.067, total = 3) => {
  const out = []
  for (let t = 0; t <= total; t += dt) out.push({ t, rms: segs.some(([a, b]) => t >= a && t < b) ? 0.05 : 0.002 })
  return out
}

test('짧게 내고 기다렸다 멈추면 녹음 길이가 아니라 소리 낸 길이', () => {
  assert.ok(longestVoicedRun(track([[0.2, 0.6]])) <= 0.5)
})

test('2초 넘게 이어 내면 그 길이, 짧은 끊김은 이어진 것으로', () => {
  assert.ok(longestVoicedRun(track([[0.2, 2.6]])) >= 2.3)
  assert.ok(longestVoicedRun(track([[0.2, 1.2], [1.3, 2.5]])) >= 2.2)
})

test('긴 쉼으로 나뉘면 가장 긴 한 구간', () => {
  const v = longestVoicedRun(track([[0.1, 0.9], [1.5, 2.3]]))
  assert.ok(v >= 0.7 && v <= 0.9, String(v))
  assert.equal(longestVoicedRun([]), 0)
})
