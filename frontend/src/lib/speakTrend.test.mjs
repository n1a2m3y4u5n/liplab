import { test } from 'node:test'
import assert from 'node:assert/strict'
import { speakTrendView, SPEAK_TREND_MIN_N } from './speakTrend.js'

const wk = (n, mean = null) => ({ start: '2026-10-03', n, mean })

test('기록이 없거나 예전 서버면 줄을 그리지 않는다', () => {
  assert.equal(speakTrendView(null).show, false)
  assert.equal(speakTrendView({}).show, false)
  assert.equal(speakTrendView({ speak_trend: null }).show, false)
  assert.equal(speakTrendView({ speak_trend: { weeks: [wk(0), wk(0)], min_n: 5, n: 0 } }).show, false)
})

test('주 평균을 0~1로 바꾸고, 5문장 미만인 주는 비운다', () => {
  const v = speakTrendView({ speak_trend: { min_n: 5, n: 16, weeks: [wk(0), wk(4), wk(5, 61.4), wk(7, 72.6)] } })
  assert.equal(v.show, true)
  assert.deepEqual(v.weeks.map((w) => w.accuracy), [null, null, 0.614, 0.726])
  assert.equal(v.shown, 2)
  assert.equal(v.last, 73)
  assert.equal(v.lastN, 7)
})

test('평균이 없는 주만 있어도 줄은 보이고(안내 글), 서버가 평균을 잘못 보내도 n이 모자라면 비운다', () => {
  const v = speakTrendView({ speak_trend: { min_n: 5, n: 3, weeks: [wk(0), wk(3, 80)] } })
  assert.equal(v.show, true)
  assert.equal(v.shown, 0)
  assert.equal(v.last, null)
  assert.equal(v.minN, 5)
  assert.equal(SPEAK_TREND_MIN_N, 5)
  const c = speakTrendView({ speak_trend: { weeks: [wk(9, 130)] } })
  assert.equal(c.weeks[0].accuracy, 1, '0~100으로 자른다')
})
