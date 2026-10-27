import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { SUS_QUESTIONS, susScore } from './feedback.js'

test('SUS 문구가 지정 문서의 한국어 1차안과 같다', () => {
  const text = fs.readFileSync(new URL('../../../docs/pilot/sus-positive-ko.md', import.meta.url), 'utf8')
  const rows = text.split('\n').filter(line => /^\| S\d+ \|/.test(line)).map(line => line.split('|')[3].trim())
  assert.deepEqual(SUS_QUESTIONS, rows)
  assert.equal(rows.length, 10)
})
test('긍정판 전체 문항을 같은 방향으로 채점한다', () => {
  assert.equal(susScore(Array(10).fill(1)), 0)
  assert.equal(susScore(Array(10).fill(5)), 100)
  assert.equal(susScore(Array(10).fill(3)), 50)
  assert.equal(susScore([1, 2]), null)
  assert.equal(susScore(Array(10).fill(6)), null)
})
