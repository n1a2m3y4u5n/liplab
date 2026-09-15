// 학습 트랙 정의(config/tracks.js) 정합성 검증. 실행: node --test
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { TRACKS, TRACK_IDS, getTrack } from './tracks.js'

test('트랙은 독화·말하기 2개뿐 (촉각 트랙 없음)', () => {
  assert.deepEqual(TRACK_IDS, ['lipreading', 'speaking'])
  assert.equal(getTrack('tactile'), null)
})

test('단계 번호가 백엔드 단계 API와 맞다 — 독화 0~4, 말하기 0~5', () => {
  assert.deepEqual(TRACKS.lipreading.lessons.map((l) => l.stage), [0, 1, 2, 3, 4])
  assert.deepEqual(TRACKS.speaking.lessons.map((l) => l.stage), [0, 1, 2, 3, 4, 5])
})

test('단계 API 이름은 api.js의 실제 객체·메서드', () => {
  assert.equal(TRACKS.lipreading.apiNamespace, 'curriculumAPI')
  assert.equal(TRACKS.lipreading.stagesMethod, 'getStages')
  assert.equal(TRACKS.speaking.apiNamespace, 'speakAPI')
  assert.equal(TRACKS.speaking.stagesMethod, 'getCurriculum')
})

test('모든 레슨·연습 항목은 완성된 링크와 고유 id를 갖는다', () => {
  for (const track of Object.values(TRACKS)) {
    const items = [...track.lessons, ...track.practice]
    for (const item of items) {
      assert.ok(item.to.startsWith('/'), `${track.id}/${item.id}: to가 절대 경로여야 함`)
      assert.ok(item.title, `${track.id}/${item.id}: title 필요`)
    }
    assert.equal(new Set(items.map((i) => i.id)).size, items.length, `${track.id}: id 중복`)
  }
})

test('URL 방식 차이는 링크에 그대로 담긴다 — 독화는 경로, 말하기는 ?stage 쿼리', () => {
  assert.equal(TRACKS.lipreading.lessons.find((l) => l.id === 'word').to, '/learn/lipreading/lesson/word')
  for (const lesson of TRACKS.speaking.lessons) {
    assert.equal(lesson.to, `/learn/speaking?stage=${lesson.stage}`)
  }
})
