// openSet 검사. 실행: npm test (node --test)
import test from 'node:test'
import assert from 'node:assert/strict'
import { typedSlots, sentenceQuestionTypes } from './openSet.js'

const count = (arr, t) => arr.filter((x) => x === t).length

test('typedSlots: 숙달 전에는 없고, 숙달 뒤 12문항 중 4문항(30%)', () => {
  assert.equal(typedSlots(12, false).size, 0)
  const s = typedSlots(12, true)
  assert.equal(s.size, 4)
  for (const i of s) assert.ok(i >= 0 && i < 12)
})

test('typedSlots: 문맥 문항 자리는 고르지 않는다', () => {
  const skip = new Set([3, 8])
  for (let k = 0; k < 50; k += 1) {
    const s = typedSlots(12, true, Math.random, skip)
    assert.equal(s.size, 4)
    assert.ok(!s.has(3) && !s.has(8))
  }
})

test('sentenceQuestionTypes: 숙달 추정값이 오를수록 선다형이 준다', () => {
  const low = sentenceQuestionTypes(6, 30)
  const mid = sentenceQuestionTypes(6, 60)
  const high = sentenceQuestionTypes(6, 75)
  const none = sentenceQuestionTypes(6, null)
  assert.equal(count(low, 'test-multiple'), 2)   // 지금과 같다(1/3)
  assert.equal(count(none, 'test-multiple'), 2)
  assert.equal(count(mid, 'test-multiple'), 1)
  assert.equal(count(high, 'test-multiple'), 0)
  for (const arr of [low, mid, high]) assert.equal(arr.length, 6)
  assert.equal(count(high, 'test') + count(high, 'essay'), 6)
  assert.equal(count(sentenceQuestionTypes(5, 69.9), 'test-multiple'), 1)
  assert.equal(count(sentenceQuestionTypes(5, 70), 'test-multiple'), 0)
})
