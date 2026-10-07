import { test } from 'node:test'
import assert from 'node:assert/strict'
import { retimeFrames, frameAt, overrideFor, joinSegments, pickSource, nextPhase, shouldSuggest, EDGE_MS } from './soundSync.js'

// '밥 먹어'의 엔진 프레임 모양(음절 자리 0, 2, 3, 공백 1은 쉼 프레임)
const frames = [
  { viseme: 1, duration_ms: 80, transition_ms: 30, text_index: 0 },
  { viseme: 2, duration_ms: 160, transition_ms: 40, text_index: 0 },
  { viseme: 1, duration_ms: 60, transition_ms: 30, text_index: 0 },
  { viseme: 14, duration_ms: 120, transition_ms: 0, text_index: 1 },
  { viseme: 1, duration_ms: 80, transition_ms: 30, text_index: 2 },
  { viseme: 5, duration_ms: 160, transition_ms: 30, text_index: 2 },
  { viseme: 7, duration_ms: 80, transition_ms: 30, text_index: 3 },
  { viseme: 5, duration_ms: 160, transition_ms: 30, text_index: 3 },
]
const syl = [{ i: 0, t0: 100, t1: 400 }, { i: 2, t0: 500, t1: 620 }, { i: 3, t0: 620, t1: 800 }]

test('음절 시각에 맞춰 같은 음절 프레임이 엔진 길이 비율로 나눠 갖는다', () => {
  const s = retimeFrames(frames, syl, 900)
  assert.equal(s.length, 7)                     // 공백의 쉼 프레임은 빠진다
  assert.deepEqual(s.slice(0, 3).map((x) => [x.start, Math.round(x.end)]), [[100, 180], [180, 340], [340, 400]])
  assert.equal(s[3].start, 500)
  assert.equal(s[3].end, 540)                   // 80/(80+160) × 120
  assert.equal(s[6].end, 800)
})

test('틈(어절 사이 쉼)은 중립으로 보인다', () => {
  const s = retimeFrames(frames, syl, 900)
  assert.equal(frameAt(s, 450), null)
  assert.equal(overrideFor(frameAt(s, 450)).viseme, 15)
  assert.equal(frameAt(s, 200).frame.viseme, 2)
  assert.equal(frameAt(s, 799).frame.viseme, 5)
  assert.equal(frameAt(s, 800), null)
  assert.equal(frameAt([], 10), null)
})

test('시각이 없으면 엔진 길이를 소리 길이에 비례로', () => {
  const s = retimeFrames(frames, null, 1100)
  assert.equal(s.length, frames.length)
  assert.equal(s[0].start, EDGE_MS)
  assert.ok(Math.abs(s[s.length - 1].end - (1100 - EDGE_MS)) < 1e-6)
  // 맞는 음절이 하나도 없어도 비례로
  const s2 = retimeFrames(frames, [{ i: 9, t0: 1, t1: 2 }], 1100)
  assert.equal(s2.length, frames.length)
  assert.deepEqual(retimeFrames([], syl, 900), [])
})

test('아바타 프레임: 전환은 머무는 시간의 절반을 넘지 않는다', () => {
  const o = overrideFor({ start: 0, end: 50, frame: { viseme: 2, transition_ms: 40, text_index: 0 } })
  assert.deepEqual([o.viseme, o.transition_ms, o.duration_ms, o.text_index], [2, 25, 50, 0])
})

test('AX 짝처럼 두 조각을 쉼을 두고 잇는다', () => {
  const a = { schedule: [{ start: 100, end: 300, frame: { viseme: 2 } }], durationMs: 400 }
  const b = { schedule: [{ start: 100, end: 250, frame: { viseme: 1 } }], durationMs: 350 }
  const j = joinSegments([a, b], 600)
  assert.deepEqual(j.segments, [{ offset: 0, durationMs: 400 }, { offset: 1000, durationMs: 350 }])
  assert.equal(j.total, 1350)
  assert.deepEqual(j.schedule.map((s) => [s.start, s.end]), [[100, 300], [1100, 1250]])
})

test('브라우저가 푸는 첫 형식(ogg 못 풀면 m4a)', () => {
  const src = [{ url: '/a.ogg', type: 'audio/ogg; codecs=opus' }, { url: '/a.m4a', type: 'audio/mp4' }]
  assert.equal(pickSource(src, (t) => (t.startsWith('audio/ogg') ? 'probably' : 'maybe')), '/a.ogg')
  assert.equal(pickSource(src, (t) => (t.startsWith('audio/ogg') ? '' : 'maybe')), '/a.m4a')
  assert.equal(pickSource(src, () => ''), null)
  assert.equal(pickSource(null, () => 'maybe'), null)
})

test('순서: 소리와 함께 → 소리 없이 한 번 더 → 끝', () => {
  assert.equal(nextPhase('sound'), 'silent')
  assert.equal(nextPhase('silent'), 'idle')
})

test('권하기는 보청기·인공와우 답이 있고 꺼져 있고 닫지 않았을 때만', () => {
  assert.equal(shouldSuggest({ enabled: false, recommended: true, dismissed: false }), true)
  assert.equal(shouldSuggest({ enabled: true, recommended: true, dismissed: false }), false)
  assert.equal(shouldSuggest({ enabled: false, recommended: false, dismissed: false }), false)
  assert.equal(shouldSuggest({ enabled: false, recommended: true, dismissed: true }), false)
})
