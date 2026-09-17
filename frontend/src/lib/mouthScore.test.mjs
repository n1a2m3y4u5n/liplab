// 웹캠 입모양 채점(축 D) 순수 함수 검증. 실행: node --test
import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  scorePercent, cosineScore, magnitudeMatch, toBlendshapeMap,
  averageBlendshapes, pickPeakFrame,
} from './mouthScore.js'

test('scorePercent: 크기(활성도)를 반영해 살짝만 벌리면 낮은 점수', () => {
  // 개방모음(viseme 2, jawOpen 0.75 목표)
  assert.ok(scorePercent({ jawOpen: 0.08 }, 2) < 30, '살짝만 벌리면 낮아야 함')
  assert.ok(scorePercent({ jawOpen: 0.72 }, 2) > 85, '제대로 벌리면 높아야 함')
  assert.equal(scorePercent({ jawOpen: 0.75 }, 2), 100, '정확히 맞으면 만점')
})

test('scorePercent: 과하게 벌린 중립모음은 감점(크기 초과)', () => {
  // 중설(viseme 5, jawOpen 0.3 목표)
  assert.ok(scorePercent({ jawOpen: 0.9 }, 5) < 60, '과하게 벌리면 감점')
  assert.equal(scorePercent({ jawOpen: 0.3 }, 5), 100, '정확히 맞으면 만점')
})

test('scorePercent: 단일 축(jawOpen) 프로파일들이 서로 구별된다', () => {
  // 예전 순수 코사인에선 개방(2)·중설(5)·연구개(7)가 jawOpen>0이면 모두 100으로 뭉갰다
  const asOpen = scorePercent({ jawOpen: 0.3 }, 2)   // 개방 목표에 중립 크기 → 낮아야
  const asMid = scorePercent({ jawOpen: 0.3 }, 5)    // 중설 목표에 딱 맞음 → 높아야
  assert.ok(asMid > asOpen, '같은 입력이라도 목표 크기에 따라 점수가 달라야 함')
})

test('cosineScore: 방향(0~1), 빈 입력은 0', () => {
  assert.equal(cosineScore({}, 2), 0, '빈 blendshape는 0')
  assert.ok(cosineScore({ jawOpen: 0.5 }, 2) > 0.99, '같은 방향(jawOpen)이면 코사인 ~1')
  assert.equal(cosineScore({ jawOpen: 0.5 }, 999), 0, '없는 viseme은 0')
})

test('magnitudeMatch: 크기 차이를 0~1로 벌점화', () => {
  assert.equal(magnitudeMatch({ jawOpen: 0.75 }, 2), 1, '크기 같으면 1')
  assert.ok(magnitudeMatch({ jawOpen: 0.08 }, 2) < 0.2, '크기 많이 작으면 낮음')
})

test('toBlendshapeMap: 카테고리 배열 → 맵', () => {
  const m = toBlendshapeMap([{ categoryName: 'jawOpen', score: 0.4 }, { categoryName: 'mouthPucker', score: 0.1 }])
  assert.equal(m.jawOpen, 0.4)
  assert.equal(m.mouthPucker, 0.1)
  assert.deepEqual(toBlendshapeMap(null), {}, 'null이면 빈 맵')
})

test('pickPeakFrame: 활성도 높은 프레임을 대표로 뽑는다', () => {
  const frames = [{ jawOpen: 0.0 }, { jawOpen: 0.1 }, { jawOpen: 0.8 }, { jawOpen: 0.9 }]
  const peak = pickPeakFrame(frames)
  assert.ok(peak.jawOpen > 0.5, '정지(0)가 아니라 크게 벌린 순간을 대표로')
  assert.deepEqual(pickPeakFrame([]), {}, '빈 입력 방어')
})

test('averageBlendshapes: 프레임 평균', () => {
  const avg = averageBlendshapes([{ jawOpen: 0.2 }, { jawOpen: 0.4 }])
  assert.equal(avg.jawOpen, 0.3)
})
