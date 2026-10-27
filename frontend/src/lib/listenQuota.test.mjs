import test from 'node:test'
import assert from 'node:assert/strict'
import { quotaView, pathDays, kstDate, recommendedStage, batchReward, batchNext } from './listenQuota.js'

test('partial answers never fill a segment; extra batches clamp only the drawing', () => {
  assert.equal(quotaView({ today_n: 0, partial_n: 11, quota_n: 2 }).filled, 0)
  assert.deepEqual(quotaView({ today_n: 3, quota_n: 2, batch_n: 12 }), { total: 2, done: 3, filled: 2, met: true, batch: 12 })
})

test('only returned XP is accumulated, zero streak is not replaced by stale state', () => {
  const first = batchReward({ xp: 0 }, { xp_gained: 0, quota: { today_n: 0 } })
  const boundary = batchReward(first, { xp_gained: 16, streak_count: 4, quota: { today_n: 1 } })
  assert.equal(boundary.xp, 16)
  assert.equal(batchReward(boundary, { xp_gained: 0 }).xp, 16)
  assert.equal(batchReward(boundary, { streak_count: 0 }).streak, 0)
  assert.deepEqual(batchReward(boundary, {}).quota, { today_n: 1 })
})

test('remaining quota, met quota, and mastery choose distinct next actions', () => {
  assert.deepEqual(batchNext({ quota: { today_n: 1 }, stage: 1 }), { kind: 'more', label: '다음 묶음 듣기 (2/2)' })
  assert.equal(batchNext({ quota: { today_n: 2 }, stage: 1 }).kind, 'exit')
  assert.deepEqual(batchNext({ quota: { today_n: 2 }, stage: 1, mastered: true }), { kind: 'stage', stage: 2, label: '3단계 보러 가기' })
  assert.equal(batchNext({ quota: { today_n: 2 }, stage: 5, mastered: true }).kind, 'exit')
})
test('path shows two completed prior dates, excluding incomplete and today', () => {
  assert.deepEqual(pathDays({ days: [1, 2, 3, 4].map((n) => ({ date: `2026-10-0${n}`, met: n !== 2 })) }, '2026-10-04').map((d) => d.date), ['2026-10-01', '2026-10-03'])
})
test('KST midnight and server recommendation do not follow the last unlocked stage', () => {
  assert.equal(kstDate(new Date('2026-10-26T15:00:00Z')), '2026-10-27')
  assert.equal(recommendedStage({ recommended: 1, stages: [{ stage: 5, status: 'unlocked' }] }), 1)
  assert.equal(recommendedStage({ stages: [{ stage: 0, status: 'mastered' }, { stage: 1, status: 'unlocked' }, { stage: 5, status: 'unlocked' }] }), 1)
})
