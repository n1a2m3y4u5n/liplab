import { test } from 'node:test'
import assert from 'node:assert/strict'
import { SOFT_BAND, loudnessRms, metricVerdict, volumeCurveNote, volumeFeedback } from './speakFeedback.js'

test("'작게' 합격 구간은 서버(_score_prosody soft)와 같은 12~45", () => {
  assert.deepEqual(SOFT_BAND, [12, 45])
})

test('크기 → RMS 역변환: 40이면 예전 적정선 0.062', () => {
  assert.ok(Math.abs(loudnessRms(40) - 0.062) < 1e-9)
  assert.ok(Math.abs(loudnessRms(0) - 0.01) < 1e-9)
})

test("'작게' 연습은 12~45 전 구간에서 '더 크게'를 내지 않는다", () => {
  for (let v = 12; v <= 45; v++) {
    const r = volumeFeedback(v, 0.05, 'soft')
    assert.equal(r.volOk, true, `크기 ${v}`)
    assert.ok(!r.volMsg.includes('더 크게'), `크기 ${v}: ${r.volMsg}`)
  }
  assert.equal(volumeFeedback(46, 0.05, 'soft').volOk, false)
  assert.match(volumeFeedback(46, 0.05, 'soft').volMsg, /더 작게/)
  assert.equal(volumeFeedback(11, 0.05, 'soft').volOk, false)
  assert.ok(!volumeFeedback(11, 0.05, 'soft').volMsg.includes('더 크게'))
})

test('다른 연습은 예전 기준 그대로(40 미만 더 크게, 92 초과도 적정)', () => {
  for (const d of [null, 'loud', 'long', 'rise', 'fall']) {
    assert.equal(volumeFeedback(39, 0.05, d).volOk, false)
    assert.match(volumeFeedback(39, 0.05, d).volMsg, /더 크게/)
    assert.equal(volumeFeedback(40, 0.05, d).volOk, true)
    assert.equal(volumeFeedback(95, 0.05, d).volOk, true)
  }
})

test('피크 0.008 미만은 드릴과 상관없이 마이크 문제', () => {
  for (const d of [null, 'soft']) {
    const r = volumeFeedback(30, 0.005, d)
    assert.equal(r.micIssue, true); assert.equal(r.volOk, false)
  }
})

const soft30 = { loudness: 30, ...volumeFeedback(30, 0.05, 'soft') }
const plain30 = { loudness: 30, ...volumeFeedback(30, 0.05, null) }

test('서버 판정이 오면 합격 여부와 note를 그대로 쓴다', () => {
  const r = metricVerdict({ assessment: { score: 100, passed: true, note: '적당히 작게 잘 냈어요!' }, assessing: false, summary: plain30, localGood: false })
  assert.deepEqual(r, { good: true, title: '잘했어요!', sub: '적당히 작게 잘 냈어요!' })
  // '크게' 50: 화면 크기로는 적정이어도 서버 불합격을 따른다
  const loud = metricVerdict({ assessment: { score: 83.3, passed: false, note: '조금 더 크게 (지금 50/100, 목표 60↑).' }, assessing: false, summary: { loudness: 50, ...volumeFeedback(50, 0.05, 'loud') }, localGood: true })
  assert.equal(loud.good, false); assert.match(loud.sub, /목표 60/)
})

test('note가 비면 합격 여부에 맞는 기본 문구, passed가 없으면 65점 기준', () => {
  assert.equal(metricVerdict({ assessment: { score: 70, note: '' }, summary: plain30 }).good, true)
  assert.equal(metricVerdict({ assessment: { score: 60 }, summary: plain30 }).sub, '소리가 잘 전달되지 않았어요')
})

test('응답 전에는 판정하지 않고 분석 중', () => {
  const r = metricVerdict({ assessment: null, assessing: true, summary: plain30, localGood: true })
  assert.equal(r.good, null); assert.match(r.title, /분석 중/)
})

test('서버 결과가 없거나 실패하면 화면에서 잰 값으로 보인다', () => {
  const ok = metricVerdict({ assessment: null, assessing: false, summary: soft30, localGood: true })
  assert.equal(ok.good, true); assert.ok(!ok.sub.includes('더 크게'))
  const bad = metricVerdict({ assessment: { error: '실패' }, assessing: false, summary: plain30, localGood: false })
  assert.equal(bad.good, false); assert.match(bad.sub, /더 크게/)
  // 억양만 놓친 경우(크기는 적정)는 일반 문구
  const tone = metricVerdict({ assessment: null, assessing: false, summary: { loudness: 60, ...volumeFeedback(60, 0.05, 'rise') }, localGood: false })
  assert.equal(tone.sub, '소리가 잘 전달되지 않았어요')
  assert.deepEqual(metricVerdict({ assessment: null, assessing: false, summary: null }), { good: null, title: '', sub: '' })
})

test("그래프 크기 안내: '작게'는 목표 구간 기준, 다른 연습은 적정선 기준", () => {
  assert.equal(volumeCurveNote(soft30, 'soft'), null)
  assert.equal(volumeCurveNote(plain30, null), '크기 곡선이 적정선 아래로 자주 내려갔어요 → 배에 힘을 주고 더 크게.')
  const hi = { loudness: 60, ...volumeFeedback(60, 0.05, 'soft') }
  assert.match(volumeCurveNote(hi, 'soft'), /더 작게/)
  const lo = { loudness: 5, ...volumeFeedback(5, 0.05, 'soft') }
  assert.ok(!volumeCurveNote(lo, 'soft').includes('더 크게'))
  assert.equal(volumeCurveNote({ loudness: 0, ...volumeFeedback(0, 0.001, null) }, null), null)   // 마이크 문제는 따로 안내
  assert.equal(volumeCurveNote(null, 'soft'), null)
})
