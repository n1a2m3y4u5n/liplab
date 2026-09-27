import { test } from 'node:test'
import assert from 'node:assert/strict'
import { autoCorrelate } from './pitch.js'

// 성문 펄스 비슷한 배음 신호(기본 주파수 f0)
const tone = (f0, sr = 48000, n = 2048) => {
  const b = new Float32Array(n)
  for (let i = 0; i < n; i++) {
    const t = i / sr
    b[i] = 0.3 * Math.sin(2 * Math.PI * f0 * t) + 0.15 * Math.sin(2 * Math.PI * 2 * f0 * t) + 0.08 * Math.sin(2 * Math.PI * 3 * f0 * t)
  }
  return b
}

test('남성·여성·아동 음높이를 1% 안으로 찾는다', () => {
  for (const f0 of [90, 120, 180, 220, 300, 400]) {
    const hz = autoCorrelate(tone(f0), 48000)
    assert.ok(Math.abs(hz - f0) / f0 < 0.01, `${f0} → ${hz}`)
  }
})

test('조용하면 -1', () => {
  assert.equal(autoCorrelate(new Float32Array(2048), 48000), -1)
})
