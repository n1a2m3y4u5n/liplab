// 학습 트랙 공통 계산(trackProgress.js) 검증. 실행: node --test
import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  isLockedStatus, mergeLessonStatus, pickContinueLesson, summarizeProgress, pickNextLesson, lockHint,
} from './trackProgress.js'
import { TRACKS } from '../../../config/tracks.js'

const lessons = TRACKS.lipreading.lessons
const withStatus = (...statuses) => mergeLessonStatus(lessons, statuses.map((status, stage) => ({ stage, status })))

test('잠금 규칙은 StageGate와 같다 — locked·coming_soon만, 모르는 상태는 막지 않음', () => {
  assert.equal(isLockedStatus('locked'), true)
  assert.equal(isLockedStatus('coming_soon'), true)
  for (const s of ['unlocked', 'in_progress', 'mastered', null, undefined]) assert.equal(isLockedStatus(s), false)
})

test('단계 API 응답을 stage 번호로 레슨에 합친다', () => {
  const merged = mergeLessonStatus(lessons, [{ stage: 2, status: 'in_progress', mastery_score: 62.5, attempts: 4 }])
  const word = merged.find((l) => l.id === 'word')
  assert.deepEqual([word.status, word.masteryScore, word.attempts], ['in_progress', 62.5, 4])
  assert.equal(merged.find((l) => l.id === 'viseme').status, null, '응답에 없는 단계는 null')
  assert.ok(mergeLessonStatus(lessons, null).every((l) => l.status === null), '불러오는 중엔 전부 null')
})

test('이어하기: 진행 중 → 시작 가능 → 마지막 숙달 → 첫 레슨', () => {
  assert.equal(pickContinueLesson(withStatus('mastered', 'mastered', 'in_progress', 'locked', 'locked')).id, 'word')
  assert.equal(pickContinueLesson(withStatus('mastered', 'mastered', 'mastered', 'unlocked', 'locked')).id, 'sentence')
  assert.equal(pickContinueLesson(withStatus('mastered', 'mastered', 'mastered', 'mastered', 'mastered')).id, 'conversation')
  assert.equal(pickContinueLesson(mergeLessonStatus(lessons, null)).id, 'placement', '상태를 모르면 첫 레슨')
  assert.equal(pickContinueLesson([]), null)
})

test('진행도 요약은 숙달한 단계 수를 센다', () => {
  assert.deepEqual(summarizeProgress(withStatus('mastered', 'mastered', 'in_progress', 'locked', 'locked')), { total: 5, mastered: 2, percent: 40 })
  assert.deepEqual(summarizeProgress([]), { total: 0, mastered: 0, percent: 0 })
})

test('다음 추천: 현재 다음의 잠기지 않은 레슨, 없으면 이어하기 대상', () => {
  const ls = withStatus('mastered', 'mastered', 'mastered', 'in_progress', 'locked')
  assert.equal(pickNextLesson(ls, 'viseme').id, 'word')
  assert.equal(pickNextLesson(ls, 'sentence'), null, '다음 단계가 잠겼고 이어하기 대상이 자기 자신이면 추천 없음')
})

test('다음 추천: 모르는 레슨 id면 이어하기 대상, 마지막 레슨이면 이어하기로 되돌림', () => {
  const ls = withStatus('mastered', 'in_progress', 'locked', 'locked', 'locked')
  assert.equal(pickNextLesson(ls, 'nope').id, 'viseme')
  assert.equal(pickNextLesson(ls, 'conversation').id, 'viseme')
  assert.equal(pickNextLesson(ls, 'viseme'), null, '이어하기 대상이 현재 레슨이면 추천하지 않음')
})

test('잠금 안내는 직전 단계 번호·제목을 알려준다', () => {
  const conversation = lessons.find((l) => l.id === 'conversation')
  assert.equal(lockHint(lessons, conversation), '직전 단계(3단계 · 문장 학습)를 먼저 완료해주세요.')
  assert.equal(lockHint(lessons, { stage: 0 }), '직전 단계를 먼저 완료해주세요.')
})
