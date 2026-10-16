import { test } from 'node:test'
import assert from 'node:assert/strict'
import { pathNodeState } from './pathNodes.js'

const states = (statuses, track) => {
  const list = statuses.map((status, stage) => ({ stage, status }))
  const { nodeStatus } = pathNodeState(list, track)
  return list.map(nodeStatus)
}

test('보통 경로: 마지막 열린 단계가 현재, 다음 잠긴 단계는 건너뛰기 후보', () => {
  assert.deepEqual(states(['mastered', 'in_progress', 'locked', 'locked'], 'listen'), ['mastered', 'current', 'skip', 'locked'])
})

test('소리 듣기 배치검사 적용 뒤: 진행 중인 1·2단계는 ✓가 아니라 열린 단계, 3단계가 현재', () => {
  const st = ['mastered', 'in_progress', 'in_progress', 'unlocked', 'locked', 'locked']
  assert.deepEqual(states(st, 'listen'), ['mastered', 'current', 'current', 'current', 'skip', 'locked'])
  assert.equal(pathNodeState(st.map((status, stage) => ({ stage, status })), 'listen').currentIdx, 3)
})

test('독화·발화의 건너뛰기는 예전처럼 지나온 단계(✓)로 보인다', () => {
  assert.deepEqual(states(['mastered', 'in_progress', 'unlocked', 'locked'], 'read'), ['mastered', 'mastered', 'current', 'skip'])
  assert.deepEqual(states(['in_progress', 'unlocked', 'locked'], 'speak'), ['mastered', 'current', 'skip'])
})

test('소리 듣기 배치검사로 5단계까지 열면: 열렸지만 연습 안 한 3·4단계도 ✓ 없이 열린 단계', () => {
  const st = ['mastered', 'in_progress', 'in_progress', 'unlocked', 'unlocked', 'unlocked']
  assert.deepEqual(states(st, 'listen'), ['mastered', 'current', 'current', 'current', 'current', 'current'])
})

test('열린 단계가 없으면 첫 잠긴 단계가 건너뛰기 후보', () => {
  assert.deepEqual(states(['mastered', 'locked', 'locked'], 'listen'), ['mastered', 'skip', 'locked'])
})
