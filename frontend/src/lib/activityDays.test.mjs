// activityDays 검사. 실행: npm test (node --test)
import test from 'node:test'
import assert from 'node:assert/strict'
import { activityCounts, recentDays, ymd } from './activityDays.js'

test('activityCounts: 모든 활동 종류의 n을 날마다 더한다(문장 연습이 없어도 센다)', () => {
  const acts = {
    '2026-09-26': [{ kind: 'viseme', n: 48 }, { kind: 'word', n: 36 }],
    '2026-09-27': [{ kind: 'speak', n: 5 }, { kind: 'sentence', n: 2 }, { kind: 'assessment', n: null }],
    '2026-09-20': [],
  }
  assert.deepEqual(activityCounts(acts), { '2026-09-26': 84, '2026-09-27': 7, '2026-09-20': 0 })
  assert.deepEqual(activityCounts(null), {})
})

test('ymd: 현지 날짜(오전 7시 학습이 전날로 가지 않는다)', () => {
  assert.equal(ymd(new Date(2026, 8, 27, 7, 0)), '2026-09-27')
  assert.equal(ymd(new Date(2026, 0, 5, 0, 30)), '2026-01-05')
})

test('recentDays: 오늘로 끝나는 90칸, 현지 날짜 키, 월 경계', () => {
  const today = new Date(2026, 8, 27, 8, 30)
  const days = recentDays({ '2026-09-27': 3, '2026-06-30': 1, '2026-06-29': 9 }, 90, today)
  assert.equal(days.length, 90)
  assert.equal(days[89].key, '2026-09-27')
  assert.equal(days[89].count, 3)
  assert.equal(days[0].key, '2026-06-30')
  assert.equal(days[0].count, 1)
  assert.ok(!days.some((d) => d.key === '2026-06-29'), '90일 밖은 뺀다')
  assert.equal(new Set(days.map((d) => d.key)).size, 90)
})
