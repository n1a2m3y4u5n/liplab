import { test } from 'node:test'
import assert from 'node:assert/strict'
import { onsetOf, wordSkeleton, sentenceSkeleton } from './consonantSkeleton.js'

test('음절은 첫소리 자음만, 첫소리 없음은 ㅇ', () => {
  assert.equal(onsetOf('밥'), 'ㅂ')
  assert.equal(onsetOf('아'), 'ㅇ')
  assert.equal(onsetOf('뜨'), 'ㄸ')
  assert.equal(onsetOf('3'), '3')
})

test('문장 부호는 빼고 낱말마다 나눈다(서버 skeleton과 같은 규칙)', () => {
  assert.deepEqual(wordSkeleton('주세요?'), ['ㅈ', 'ㅅ', 'ㅇ'])
  assert.deepEqual(sentenceSkeleton('물 좀 주세요.'), [['ㅁ'], ['ㅈ'], ['ㅈ', 'ㅅ', 'ㅇ']])
  assert.deepEqual(sentenceSkeleton('  3시 , 가요 '), [['3', 'ㅅ'], ['ㄱ', 'ㅇ']])
})
