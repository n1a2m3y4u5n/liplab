import test from 'node:test'
import assert from 'node:assert/strict'
import { resampleFrames } from './frameRate.js'

const cam = (fps, durMs, offset = 0) =>
  Array.from({ length: Math.floor((durMs * fps) / 1000) }, (_, i) => ({ t: offset + (i * 1000) / fps, bs: { i } }))

test('30 fps 카메라는 60 Hz 격자에서 프레임마다 두 번(벤치 dup2)', () => {
  const out = resampleFrames(cam(30, 2500), 0, 2500, 60)
  assert.equal(out.length, 150)
  for (let k = 0; k < out.length; k++) assert.equal(out[k].i, Math.floor(k / 2))
})

test('60 fps 카메라는 한 번씩', () => {
  const out = resampleFrames(cam(60, 2500), 0, 2500, 60)
  assert.equal(out.length, 150)
  out.forEach((bs, k) => assert.equal(bs.i, k))
})

test('화면 주사율과 무관: 같은 카메라 프레임이면 결과가 같다', () => {
  // 새 프레임일 때만 모으므로 120 Hz 화면이어도 입력은 카메라 프레임 목록 그대로다
  const a = resampleFrames(cam(30, 2500), 0, 2500, 60).map((b) => b.i)
  const b = resampleFrames(cam(30, 2500, 0.4), 0, 2500, 60).map((x) => x.i)
  assert.equal(a.length, 150)
  assert.ok(b.length >= 149 && b.length <= 150)
})

test('첫 프레임 전 칸은 버리고, 빈 입력은 빈 배열', () => {
  const out = resampleFrames([{ t: 100, bs: { i: 0 } }, { t: 133, bs: { i: 1 } }], 0, 200, 60)
  assert.deepEqual(out.map((b) => b.i), [0, 0, 1, 1, 1, 1])
  assert.deepEqual(resampleFrames([], 0, 2500), [])
  assert.deepEqual(resampleFrames(null, 0, 2500), [])
})
