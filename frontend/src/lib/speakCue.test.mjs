import { test } from 'node:test'
import assert from 'node:assert/strict'
import { RATE_AXIS, rateCueView } from './speakCue.js'

const cue = (value, slow) => ({ kind: 'rate', label: '말 빠르기', value, unit: '음절/초', range: [4.08, 6.82], typical: 5.27, slow,
  message: slow ? '말 빠르기가 보통 낭독보다 느린 편이에요. 낱말 사이에서 쉬지 말고 한 숨에 이어 말해 보세요.' : null, reference: true })

test('느린 쪽이면 안내 문구를 보이고 제목에 참고를 붙인다', () => {
  const v = rateCueView(cue(3.1, true))
  assert.equal(v.title, '말 빠르기 · 참고')
  assert.equal(v.valueText, '초당 3.1음절')
  assert.equal(v.slow, true)
  assert.match(v.message, /느린 편/)
})

test('범위 안이면 문구가 없다', () => {
  const v = rateCueView(cue(5.3, false))
  assert.equal(v.message, null)
  assert.equal(v.slow, false)
})

test('막대 위치는 눈금 안으로 자르고 띠는 538 범위', () => {
  assert.equal(rateCueView(cue(20, false)).markerPct, 100)
  assert.equal(rateCueView(cue(-1, true)).markerPct, 0)
  const v = rateCueView(cue(4.5, false))
  assert.ok(Math.abs(v.bandLeftPct - (4.08 / RATE_AXIS[1]) * 100) < 1e-9)
  assert.ok(Math.abs(v.bandLeftPct + v.bandWidthPct - (6.82 / RATE_AXIS[1]) * 100) < 1e-9)
  assert.match(v.note, /4\.1~6\.8/)
})

test('단서가 없거나 다른 종류면 그리지 않는다', () => {
  assert.equal(rateCueView(null), null)
  assert.equal(rateCueView({ kind: 'fricative', value: 1, range: [0, 1] }), null)
  assert.equal(rateCueView({ kind: 'rate', value: null, range: [4, 7] }), null)
})

test('문구에 줄표(—)를 쓰지 않는다', () => {
  const v = rateCueView(cue(3.0, true))
  for (const s of [v.title, v.valueText, v.message, v.note]) assert.ok(!s.includes('—'), s)
})
