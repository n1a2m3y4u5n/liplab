// reviewDue 검사. 실행: npm test (node --test)
import test from 'node:test'
import assert from 'node:assert/strict'
import { dueCounts, dueStartPath, mistakeCount, rewardMessage } from './reviewDue.js'

test('dueCounts: 독화·말하기 예정을 나눠 센다(옛 응답은 items만)', () => {
  assert.deepEqual(dueCounts({ count: 2, items: [{}, {}], speak_count: 3, speak: [{}, {}, {}] }), { read: 2, speak: 3, total: 5 })
  assert.deepEqual(dueCounts({ items: [{}] }), { read: 1, speak: 0, total: 1 })
  assert.deepEqual(dueCounts(null), { read: 0, speak: 0, total: 0 })
})

test('dueStartPath: 독화 예정 먼저, 말하기 예정만 있으면 말하기 복습, 없으면 fallback', () => {
  assert.equal(dueStartPath({ read: 1, speak: 2 }, '/review'), '/review/scheduled')
  assert.equal(dueStartPath({ read: 0, speak: 2 }, '/review'), '/review/speaking')
  assert.equal(dueStartPath({ read: 0, speak: 0 }, '/review/mistakes'), '/review/mistakes')
})

test('mistakeCount: 틀린 문장 + 독화 예정 + 말하기 예정', () => {
  assert.equal(mistakeCount(2, { read: 1, speak: 3 }), 6)
  assert.equal(mistakeCount(0, null), 0)
})

test('rewardMessage: 하나면 과제 이름, 여럿이면 개수와 합계', () => {
  assert.equal(rewardMessage([]), '')
  assert.equal(rewardMessage([{ label: '독화 학습 1회', xp: 15 }]), "'독화 학습 1회' 완료 +15 XP")
  assert.equal(rewardMessage([{ label: 'a', xp: 10 }, { label: 'b', xp: 15 }]), '과제 2개 완료 +25 XP')
})
