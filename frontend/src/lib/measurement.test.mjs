// measurement 검사. 실행: npm test (node --test)
import test from 'node:test'
import assert from 'node:assert/strict'
import {
  probeInsertAfter, shouldOpenProbes, probeOptionLabel, newSessionId, EFFORT_POINTS, EFFORT_ANCHORS,
  retentionPromptVisible, localDay,
} from './measurement.js'

test('probeInsertAfter: 레슨 가운데(12문항이면 6번 뒤), 짧아도 1 이상', () => {
  assert.equal(probeInsertAfter(12), 6)
  assert.equal(probeInsertAfter(5), 2)
  assert.equal(probeInsertAfter(1), 1)
  assert.equal(probeInsertAfter(0), 1)
})

test('shouldOpenProbes: 그 자리에서 한 번만, 탐침이 있을 때만', () => {
  assert.equal(shouldOpenProbes({ qNum: 6, insertAfter: 6, count: 3, shown: false }), true)
  assert.equal(shouldOpenProbes({ qNum: 6, insertAfter: 6, count: 3, shown: true }), false)
  assert.equal(shouldOpenProbes({ qNum: 6, insertAfter: 6, count: 0, shown: false }), false)
  assert.equal(shouldOpenProbes({ qNum: 5, insertAfter: 6, count: 3, shown: false }), false)
})

test('probeOptionLabel: 입모양 무리는 쉬운 이름, 나머지는 서버 글', () => {
  assert.equal(probeOptionLabel({ kind: 'viseme' }, { viseme_id: 1, label: '양순음' }), '입술 닫힘 (바·마)')
  assert.equal(probeOptionLabel({ kind: 'viseme' }, { viseme_id: 99, label: '모름' }), '모름')
  assert.equal(probeOptionLabel({ kind: 'word' }, { label: '나무' }), '나무')
})

test('newSessionId: 서버 형식에 맞고 매번 다르다', () => {
  const a = newSessionId()
  const b = newSessionId()
  assert.match(a, /^[A-Za-z0-9_-]{6,40}$/)
  assert.notEqual(a, b)
})

test('정신적 노력 척도: 1~9, 양 끝·가운데 기준점', () => {
  assert.deepEqual(EFFORT_POINTS, [1, 2, 3, 4, 5, 6, 7, 8, 9])
  assert.ok(EFFORT_ANCHORS[1] && EFFORT_ANCHORS[5] && EFFORT_ANCHORS[9])
})

test('retentionPromptVisible: 볼 때만, 오늘 미룬 날은 숨김', () => {
  assert.equal(retentionPromptVisible({ state: 'due' }, null, '2026-10-06'), true)
  assert.equal(retentionPromptVisible({ state: 'due' }, '2026-10-06', '2026-10-06'), false)
  assert.equal(retentionPromptVisible({ state: 'due' }, '2026-10-05', '2026-10-06'), true)
  assert.equal(retentionPromptVisible({ state: 'waiting' }, null, '2026-10-06'), false)
  assert.equal(retentionPromptVisible(null, null, '2026-10-06'), false)
})

test('localDay: YYYY-MM-DD', () => {
  assert.equal(localDay(new Date(2026, 9, 6)), '2026-10-06')
})
