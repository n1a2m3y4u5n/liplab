import { test } from 'node:test'
import assert from 'node:assert/strict'
import { pickDistractors, visualLevel } from './wordOptions.js'

test('pickDistractors: 서버가 준 오답 3개를 그대로 쓰고, 없으면 은행에서 무작위', () => {
  const byWord = new Map([['물통', { word: '물통', distractors: ['목수', '사자', '바퀴', '여분'] }]])
  assert.deepEqual(pickDistractors('물통', byWord, ['물통', '목수']), ['목수', '사자', '바퀴'])
  const bank = ['가', '나', '다', '라', '마']
  const r = pickDistractors('가', new Map(), bank)
  assert.equal(r.length, 3)
  assert.ok(!r.includes('가') && r.every((w) => bank.includes(w)))
})

test('visualLevel: 분위 0~1을 입모양 난이도 1~5로, 분위가 없으면 null', () => {
  assert.equal(visualLevel(0), 1)
  assert.equal(visualLevel(0.19), 1)
  assert.equal(visualLevel(0.2), 2)
  assert.equal(visualLevel(0.7), 4)
  assert.equal(visualLevel(0.99), 5)
  assert.equal(visualLevel(1), 5)
  assert.equal(visualLevel(undefined), null)
  assert.equal(visualLevel(NaN), null)
})
