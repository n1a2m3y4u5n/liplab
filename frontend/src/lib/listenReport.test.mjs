import { test } from 'node:test'
import assert from 'node:assert/strict'
import { MDC_DB, splitTests, srtChange, srtMeaning, testRows, axKindRows, confusionRows, dayBars } from './listenReport.js'

const t = (srt, noise = 'babble', i = 0) => ({ session: `s${i}`, srt_db: srt, noise, form: 'A' })

test('검사는 잡담 잡음끼리만 비교하고, 역치가 없는 회차는 뺀다', () => {
  const { main, other } = splitTests([t(8, 'babble', 1), t(6, 'talker2', 2), t(null, 'babble', 3), t(5, undefined, 4)])
  assert.deepEqual(main.map((x) => x.session), ['s1', 's4'])
  assert.deepEqual(other.map((x) => x.session), ['s2'])
})

test('변화는 처음 − 마지막(낮아지면 양수), 3 dB 안쪽은 오차 범위', () => {
  assert.equal(MDC_DB, 3.0)
  assert.equal(srtChange([t(8)]), null)
  assert.deepEqual(srtChange([t(8), t(6)]), { change: 2, text: '처음보다 2 dB 낮아졌어요', withinError: true, mixedRule: false })
  assert.deepEqual(srtChange([t(8), t(4.5)]), { change: 3.5, text: '처음보다 3.5 dB 낮아졌어요', withinError: false, mixedRule: false })
  assert.deepEqual(srtChange([t(4), t(5)]), { change: -1, text: '처음보다 1 dB 높아졌어요', withinError: true, mixedRule: false })
  assert.equal(srtChange([t(4), t(4)]).withinError, false)
})

test('검사 계단 규칙: 새 회차(절반 규칙)는 설명이 바뀌고, 첫 검사와 규칙이 다르면 표시한다', () => {
  const half = (srt) => ({ ...t(srt), rule: 'half' })
  assert.equal(srtMeaning(half(5)), '낱말을 절반쯤 알아듣는')
  assert.equal(srtMeaning(t(5)), '낱말을 열에 넷쯤 알아듣는')
  assert.equal(srtMeaning(undefined), '낱말을 열에 넷쯤 알아듣는')
  assert.equal(srtChange([t(8), half(6)]).mixedRule, true)
  assert.equal(srtChange([half(8), half(6)]).mixedRule, false)
})

test('검사가 많으면 최근 몇 개와 처음 검사만 보인다', () => {
  const many = [...Array(9)].map((_, i) => t(10 - i, 'babble', i))
  const { rows, hidden } = testRows(many, 5)
  assert.deepEqual(rows.map((r) => r.order), [9, 8, 7, 6, 1])
  assert.equal(hidden, 4)
  assert.equal(rows[rows.length - 1].first, true)
  assert.equal(testRows(many, 5, true).rows.length, 9)
  assert.deepEqual(testRows(many.slice(0, 3), 5).rows.map((r) => r.order), [3, 2, 1])
  assert.deepEqual(testRows([], 5), { rows: [], hidden: 0 })
})

test('소리 구별 막대는 정답률 낮은 순, 적게 푼 종류 표시', () => {
  const rows = axKindRows([{ kind: 'a', label: '길이', n: 10, correct: 9 }, { kind: 'b', label: '모음', n: 3, correct: 1 }, { kind: 'c', label: 'x', n: 0, correct: 0 }])
  assert.deepEqual(rows.map((r) => [r.label, r.pct, r.few]), [['모음', 33, true], ['길이', 90, false]])
})

test('헷갈린 짝 표', () => {
  const rows = confusionRows([{ slot: 'onset', target: 'ㅅ', heard: 'ㄷ', n: 4 }, { slot: 'coda', target: 'ㄱ', heard: '-', n: 2 }])
  assert.deepEqual(rows, [{ where: '첫소리', target: 'ㅅ', heard: 'ㄷ', n: 4 }, { where: '받침', target: 'ㄱ', heard: '없음', n: 2 }])
})

test('7일 막대: 마지막 날은 오늘, 비면 total 0', () => {
  const days = ['2026-10-01', '2026-10-02', '2026-10-03'].map((date, i) => ({ date, n: [0, 4, 8][i] }))
  const r = dayBars(days)
  assert.deepEqual(r.bars.map((b) => [b.label, b.pct, b.today]), [['10/01', 0, false], ['10/02', 50, false], ['오늘', 100, true]])
  assert.equal(r.total, 12)
  assert.equal(r.activeDays, 2)
  assert.equal(dayBars([{ date: '2026-10-01', n: 0 }]).total, 0)
  assert.equal(dayBars(null).total, 0)
  assert.equal(dayBars(null).bars.length, 0)
  // 서버가 분을 주면 분으로 그리고 15분 목표를 넘긴 날을 센다
  const m = dayBars([{ date: '2026-10-06', n: 30, minutes: 18.4 }, { date: '2026-10-07', n: 5, minutes: 4 }])
  assert.equal(m.unit, '분')
  assert.equal(m.totalMin, 22)
  assert.equal(m.goalDays, 1)
  assert.equal(m.bars[0].pct, 90)          // 18분 ÷ 기준 최대 20분
  assert.equal(m.goalPct, 75)
})
