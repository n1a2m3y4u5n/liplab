// 조음 교정 세션 처음·끝 오차(축 E-9) 검증. 실행: node --test
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { errorEnds } from './correctionTrend.js'

test('errorEnds: 표본 4개 미만이면 null', () => {
  assert.equal(errorEnds([]), null)
  assert.equal(errorEnds([0.5, 0.4, 0.3]), null)
})

test('errorEnds: 절반까지(최대 5개)씩 처음·끝 평균', () => {
  assert.deepEqual(errorEnds([0.6, 0.4, 0.2, 0.1]), { start: 0.5, end: 0.15 })
  const long = [0.5, 0.5, 0.5, 0.5, 0.5, 0.3, 0.3, 0.2, 0.2, 0.2, 0.2, 0.2]
  assert.deepEqual(errorEnds(long), { start: 0.5, end: 0.2 })
})
