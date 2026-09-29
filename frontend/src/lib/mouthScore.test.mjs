// 웹캠 입모양 채점(축 D) 순수 함수 검증. 실행: node --test
import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  scorePercent, cosineScore, magnitudeMatch, toBlendshapeMap,
  averageBlendshapes, pickPeakFrame, pickCalibrationFrame, pickClosureFrame, pickConsonantFrame,
  medianBlendshapes, VISEME_PROFILES, MOUTH_KEYS,
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

// ── 본뜨기(개인 캘리브레이션) 자세 선택 ─────────────────────────────────────────
// 합성 궤적: 한 음절을 1.5초(30 fps 약 45프레임) 동안 한 번 발음한다. 중립 → 자음 자세 → ㅏ 벌림 → 중립,
// 자세 사이는 몇 프레임에 걸쳐 선형으로 옮겨 가고 결정론적 잔떨림을 더한다.
const NEUTRAL = { jawOpen: 0.03, mouthClose: 0.02 }
function lerp(a, b, t) {
  const o = {}
  for (const k of MOUTH_KEYS) o[k] = (a[k] || 0) * (1 - t) + (b[k] || 0) * t
  return o
}
function trajectory(segments, jitter = 0.01) {
  // segments: [[자세, 머무는 프레임 수, 다음 자세로 옮겨 가는 프레임 수], ...]
  const out = []
  let seed = 7
  const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647 - 0.5 }
  segments.forEach(([pose, hold, ramp], i) => {
    for (let h = 0; h < hold; h++) out.push({ ...pose })
    const next = segments[i + 1]?.[0]
    if (next) for (let r = 1; r <= ramp; r++) out.push(lerp(pose, next, r / (ramp + 1)))
  })
  return out.map((f) => {
    const g = {}
    for (const k of MOUTH_KEYS) g[k] = Math.max(0, (f[k] || 0) + (f[k] ? rnd() * jitter : 0))
    return g
  })
}
function dist(a, b) {
  let s = 0
  for (const k of MOUTH_KEYS) s += ((a[k] || 0) - (b[k] || 0)) ** 2
  return Math.sqrt(s)
}
// 자음+ㅏ 한 번(자음 자세는 짧게 3프레임, 약 0.1초)
const saySyllable = (cons, vowel) => trajectory([[NEUTRAL, 10, 3], [cons, 3, 3], [vowel, 14, 3], [NEUTRAL, 9, 0]])
const sayVowel = (vowel) => trajectory([[NEUTRAL, 10, 3], [vowel, 18, 3], [NEUTRAL, 11, 0]])

test('본뜨기: 「마」 뒤 양순음 채점에서 입술을 닫은 얼굴이 입을 벌린 얼굴보다 높다', () => {
  // 탐색 메모(explore2/bugs/calib.mjs) 재현: 웹캠에서 흔히 나오는 약한 mouthClose
  const closure = { jawOpen: 0.03, mouthClose: 0.25, mouthRollLower: 0.2, mouthRollUpper: 0.15 }
  const openA = { jawOpen: 0.55, mouthStretchLeft: 0.05, mouthStretchRight: 0.05 }
  const cal = {
    1: pickCalibrationFrame(saySyllable(closure, openA), 1),
    2: pickCalibrationFrame(sayVowel(openA), 2),
  }
  const closedScore = scorePercent(closure, 1, cal)
  const openScore = scorePercent(openA, 1, cal)
  assert.ok(closedScore > openScore, `닫힘 ${closedScore} > 벌림 ${openScore}`)
  assert.ok(closedScore >= 80, `닫은 얼굴은 양순음 기준에 잘 맞아야 함: ${closedScore}`)
  assert.ok(openScore < 30, `벌린 얼굴은 양순음으로 낮아야 함: ${openScore}`)
  // 예전 방식(활성도 정점)은 ㅏ를 기준으로 저장해 채점이 뒤집혔다
  const old = { 1: pickPeakFrame(saySyllable(closure, openA)) }
  assert.ok(scorePercent(closure, 1, old) < scorePercent(openA, 1, old), '회귀 재현: 정점 방식은 뒤집힘')
})

test('본뜨기: 자음 기준과 ㅏ 기준의 거리가 규칙 프로파일 거리의 절반 이상', () => {
  const a = VISEME_PROFILES[2]
  const calA = pickCalibrationFrame(sayVowel(a), 2)
  for (const v of [1, 6, 7, 8, 10]) {
    const cons = VISEME_PROFILES[v]
    const ref = pickCalibrationFrame(saySyllable(cons, a), v)
    const got = dist(ref, calA)
    const rule = dist(cons, a)
    assert.ok(got >= 0.5 * rule, `viseme ${v}: 본뜬 거리 ${got.toFixed(3)} < 규칙 거리 절반 ${(0.5 * rule).toFixed(3)}`)
    // 자음 기준은 ㅏ보다 자기 자음 자세에 가깝다
    assert.ok(dist(ref, cons) < dist(ref, a), `viseme ${v}: 기준이 ㅏ 쪽으로 쏠림`)
  }
})

test('본뜨기: 자음 자세를 멈춘 채 두면(모음 없음) 그 자세의 중앙값을 기준으로', () => {
  const hold = VISEME_PROFILES[10]
  const frames = trajectory([[NEUTRAL, 3, 3], [hold, 39, 0]])
  const ref = pickConsonantFrame(frames)
  assert.ok(dist(ref, hold) < 0.05, `멈춘 자세와 거의 같아야 함: ${dist(ref, hold).toFixed(3)}`)
})

test('본뜨기: 모음 단계는 예전처럼 정점을 쓰고, 빈 입력은 빈 기준', () => {
  const u = VISEME_PROFILES[4]
  const frames = sayVowel(u)
  assert.deepEqual(pickCalibrationFrame(frames, 4), pickPeakFrame(frames))
  assert.deepEqual(pickClosureFrame([]), {})
  assert.deepEqual(pickConsonantFrame([]), {})
  assert.equal(medianBlendshapes([{ jawOpen: 0.1 }, { jawOpen: 0.9 }, { jawOpen: 0.2 }]).jawOpen, 0.2)
})
