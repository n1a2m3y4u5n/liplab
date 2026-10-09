/**
 * 가상 화자(커리큘럼 계획 2-2, docs/talker-variation.md): 한 얼굴 안에서 화자 차이를 흉내 낸다.
 *
 * 같은 화자 한 명만 보고 익힌 입모양은 새 화자로 잘 옮겨 가지 않는다(고변이 훈련). 얼굴을 더 만들 수 없어서, 말 속도·입 벌림·
 * 입술 폭·입술 돌출·동시조음 강도·타이밍 흔들림을 묶은 가상 화자 6명을 둔다. 훈련용 4명('화자 1'~'화자 4')은 레슨마다 돌아가며
 * 나오고, 검사 전용 2명('화자 5'·'화자 6')은 사후 검사(B형)의 새 가상 화자 조건(계획 2-3)에만 나온다.
 *
 * 값은 문헌 보고를 따른 잠정값이다. 실제 화자 입술 통계로 보정해야 하는데, 그 통계를 AI Hub 영상에서 뽑을지는 사용자 결정을
 * 기다리는 중이라 AI Hub 자료는 쓰지 않았다. 입모양 무리 판별 기준은 talkers.test.mjs(문서 7절)가 확인한다.
 */
import { VISEME_BLENDSHAPES, VISEME_V15_ENABLED } from './visemeShapes.js'

// 새 가상 화자 조건 점수 옆에 보이는 안내(9/29). 문항 12개씩이라 개인 차이는 판정하지 않고 집단 평균으로 읽는다
// (docs/talker-variation.md 6절). 학습 효과 리포트·인쇄 결과지·검사 결과 화면이 같은 문구를 쓴다.
export const TRANSFER_NOISE_NOTE = '문제 12개씩이라 한 사람 점수 차는 잡음이 커요. 여러 사람의 평균으로 읽어요.'

// 매개변수별로 곱하는 모프. 입을 닫는 모프(mouthClose·Press·Roll)와 혀는 바꾸지 않는다(양순 폐쇄는 화자와 무관하게 보여야 한다).
export const AMP_KEYS = ['jawOpen', 'mouthLowerDownLeft', 'mouthLowerDownRight', 'mouthUpperUpLeft', 'mouthUpperUpRight']
export const WIDTH_KEYS = ['mouthSmileLeft', 'mouthSmileRight', 'mouthStretchLeft', 'mouthStretchRight']
export const PROTRUSION_KEYS = ['mouthFunnel', 'mouthPucker']
// 동시조음 전환 프레임(engine.get_transition_viseme: 11 양순·12 치경·13 연구개로 가는 약한 중간 상태)
export const TRANSITION_VISEMES = new Set([11, 12, 13])

// 지시 범위(docs/talker-variation.md 2절)
export const RANGES_V1 = {
  rate: [0.85, 1.25], amp: [0.8, 1.2], width: [0.85, 1.15], protrusion: [0.85, 1.15], coart: [0.7, 1.3], jitter: [0, 0.15],
}
// V15 표와 쓰는 범위(docs/viseme-calibration-2026-10.md 7절): 538 탐색 화자 배율 10~90백분위를 모프 배율로 옮긴 값. 폭·동시조음·흔들림은
// 538 자료로 잴 수 없어 V1 범위 그대로다.
export const RANGES_V15 = {
  rate: [0.79, 1.18], amp: [0.69, 1.19], width: [0.85, 1.15], protrusion: [0.6, 1.23], coart: [0.7, 1.3], jitter: [0, 0.15],
}

export const DEFAULT_TALKER = Object.freeze({
  id: 'default', label: '기본 화자', heldOut: false, rate: 1, amp: 1, width: 1, protrusion: 1, coart: 1, jitter: 0,
})

// 가상 화자 6명. 숫자는 레슨·검사 기록에 남는 id와 화면 표시만 다르다(성별·나이 같은 속성은 붙이지 않는다).
// 입 벌림(amp)·동시조음(coart)은 처음 4절 기준에서 한때 ±4~8%로 줄였다가, 앱이 요구하는 구별에 맞춘 기준(7절: 퀴즈 무리는 자기
// 목표에, 입 안쪽 무리 6·7·8·10은 입 안쪽 무리 안에, 전환 11~13은 자기나 잇는 무리에)으로 바꾼 뒤 지시 범위의 처음 값으로 되돌렸다.
export const TALKERS_V1 = Object.freeze([
  { id: 't1', label: '화자 1', heldOut: false, rate: 1.10, amp: 1.15, width: 1.10, protrusion: 0.95, coart: 1.15, jitter: 0.10 },
  { id: 't2', label: '화자 2', heldOut: false, rate: 0.90, amp: 0.85, width: 0.90, protrusion: 1.10, coart: 0.85, jitter: 0.08 },
  { id: 't3', label: '화자 3', heldOut: false, rate: 1.20, amp: 0.90, width: 1.05, protrusion: 0.90, coart: 1.25, jitter: 0.15 },
  { id: 't4', label: '화자 4', heldOut: false, rate: 0.95, amp: 1.10, width: 0.88, protrusion: 1.12, coart: 0.75, jitter: 0.12 },
  { id: 'h1', label: '화자 5', heldOut: true, rate: 1.05, amp: 1.20, width: 0.95, protrusion: 1.15, coart: 1.30, jitter: 0.12 },
  { id: 'h2', label: '화자 6', heldOut: true, rate: 0.88, amp: 0.80, width: 1.15, protrusion: 0.85, coart: 0.70, jitter: 0.15 },
].map((t) => Object.freeze(t)))

// V5(docs/viseme-calibration-2026-10.md 7절): V15 표와 함께 쓰는 값. 538 탐색 절반 화자 37명의 화자별 배율(무리별 진폭 / 무리 중앙값의
// 무리 사이 중앙값: 벌림 J, 돌출 R)과 음절 속도 배율의 10~90백분위 안에서 정한 분위수(화자 1~4는 25~75 사이, 검사 화자 5·6은 15·85)를
// 고르고, 앱 렌더 시뮬레이션의 반응 곡선(모프 배율 → MediaPipe 진폭 배율)을 거꾸로 따라 모프 배율로 옮겼다. 말 속도는 기본 얼굴 2.0배가
// 538 중앙값에 가깝다는 점(V2 10.5절)을 기준으로 한 배율이다. 입술 폭은 538 화자의 폭 진폭이 0에 가까워 사람 분포로 정할 수 없어
// 예전 값에서 출발하고, 동시조음·흔들림도 이 자료로 잴 수 없어 예전 값에서 출발한다. 그 뒤 판별 기준 (a)~(d)를 V15 표로 걸어 어긋난
// 화자 3·5·6은 talker-variation.md 4절 규칙(위반 쌍에 관여하는 매개변수만 1에서 벗어난 폭을 5%씩)으로 줄였다(scripts/v15_talker_shrink.mjs).
export const TALKERS_V15 = Object.freeze([
  { id: 't1', label: '화자 1', heldOut: false, rate: 1.03, amp: 1.08, width: 1.10, protrusion: 0.87, coart: 1.15, jitter: 0.10 },
  { id: 't2', label: '화자 2', heldOut: false, rate: 0.94, amp: 0.94, width: 0.90, protrusion: 1.10, coart: 0.85, jitter: 0.08 },
  { id: 't3', label: '화자 3', heldOut: false, rate: 1.07, amp: 0.99, width: 1.034, protrusion: 0.78, coart: 1.154, jitter: 0.15 },
  { id: 't4', label: '화자 4', heldOut: false, rate: 0.96, amp: 1.03, width: 0.88, protrusion: 1.07, coart: 0.75, jitter: 0.12 },
  { id: 'h1', label: '화자 5', heldOut: true, rate: 1.02, amp: 1.074, width: 0.974, protrusion: 1.08, coart: 1.12, jitter: 0.12 },
  { id: 'h2', label: '화자 6', heldOut: true, rate: 0.87, amp: 0.879, width: 1.083, protrusion: 0.78, coart: 0.835, jitter: 0.15 },
].map((t) => Object.freeze(t)))

/** 앱이 쓰는 가상 화자 6명(입모양 표와 같은 플래그로 고른다). */
export const TALKERS = VISEME_V15_ENABLED ? TALKERS_V15 : TALKERS_V1
export const RANGES = VISEME_V15_ENABLED ? RANGES_V15 : RANGES_V1

export const TRAINING_TALKERS = TALKERS.filter((t) => !t.heldOut)
export const HELD_OUT_TALKERS = TALKERS.filter((t) => t.heldOut)

const BY_ID = new Map([[DEFAULT_TALKER.id, DEFAULT_TALKER], ...TALKERS.map((t) => [t.id, t])])
/** id → 가상 화자. 모르는 id나 빈 값이면 기본 화자. */
export function talkerById(id) {
  return BY_ID.get(id) || DEFAULT_TALKER
}

const isDefault = (t) => !t || t === DEFAULT_TALKER ||
  (t.amp === 1 && t.width === 1 && t.protrusion === 1 && t.coart === 1 && t.rate === 1 && !t.jitter)

// 사후 검사의 새 가상 화자 조건은 1.0배로 낸다(계획 2-3): 말 속도만 기본으로 되돌린 같은 화자. 객체를 한 번만 만들어 모양 표 캐시가 맞게 한다.
const NATURAL = new Map()
export function atNaturalRate(talker) {
  if (!talker || talker.rate === 1) return talker || DEFAULT_TALKER
  if (!NATURAL.has(talker.id)) NATURAL.set(talker.id, Object.freeze({ ...talker, rate: 1 }))
  return NATURAL.get(talker.id)
}

/** 한 입모양의 기본 목표에 화자 배율을 곱한 목표(0~1로 자름). 순수 함수, 검증 테스트와 렌더러가 같이 쓴다. */
export function scaleShape(shape, talker, visemeId) {
  const out = {}
  const coart = TRANSITION_VISEMES.has(visemeId) ? talker.coart : 1
  for (const [k, w] of Object.entries(shape || {})) {
    let s = coart
    if (AMP_KEYS.includes(k)) s *= talker.amp
    else if (WIDTH_KEYS.includes(k)) s *= talker.width
    else if (PROTRUSION_KEYS.includes(k)) s *= talker.protrusion
    out[k] = Math.max(0, Math.min(1, w * s))
  }
  return out
}

// 화자별 목표 표는 한 번만 만든다. 아바타는 화면마다 이 표에서 목표를 읽기만 한다(3D 성능은 그대로).
const SHAPES = new WeakMap()
/** VISEME_BLENDSHAPES와 같은 모양의 표. 기본 화자면 원본을 그대로 돌려준다. */
export function talkerShapes(talker) {
  if (!talker || (talker.amp === 1 && talker.width === 1 && talker.protrusion === 1 && talker.coart === 1)) return VISEME_BLENDSHAPES
  let table = SHAPES.get(talker)
  if (!table) {
    table = {}
    for (const [v, shape] of Object.entries(VISEME_BLENDSHAPES)) table[v] = scaleShape(shape, talker, Number(v))
    SHAPES.set(talker, table)
  }
  return table
}

/** 문자열 → 32비트 씨앗(FNV-1a). */
export function hashSeed(str) {
  let h = 0x811c9dc5
  const s = String(str)
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 0x01000193) }
  return h >>> 0
}

/** 씨앗과 번호로 정한 −1~1 값(같은 씨앗·번호면 늘 같다). */
export function unitNoise(seed, i) {
  let x = (seed ^ Math.imul(i + 1, 0x9e3779b1)) >>> 0
  x = Math.imul(x ^ (x >>> 16), 0x85ebca6b) >>> 0
  x = Math.imul(x ^ (x >>> 13), 0xc2b2ae35) >>> 0
  x = (x ^ (x >>> 16)) >>> 0
  return (x / 0xffffffff) * 2 - 1
}

/**
 * 화자의 말 속도·타이밍 흔들림·동시조음 강도를 프레임에 입힌 새 배열. 기본 화자면 frames를 그대로 돌려준다.
 * 흔들림은 씨앗과 발화(입모양 순서)로 정해져, 같은 레슨의 같은 단어는 늘 같은 모양으로 움직인다.
 * 학습자 속도와 적응 감속은 이 위에 곱해진다(호출부가 따로 나눈다).
 */
export function applyTalkerTiming(frames, talker, seed = 0) {
  if (!Array.isArray(frames) || frames.length === 0 || isDefault(talker)) return frames
  const rate = talker.rate > 0 ? talker.rate : 1
  const s = hashSeed(`${seed}|${talker.id}|${frames.map((f) => f?.viseme).join(',')}`)
  return frames.map((f, i) => {
    if (!f) return f
    const out = { ...f }
    if (Number.isFinite(f.duration_ms)) {
      out.duration_ms = Math.max(16, Math.round((f.duration_ms / rate) * (1 + (talker.jitter || 0) * unitNoise(s, i))))
    }
    if (Number.isFinite(f.transition_ms)) out.transition_ms = Math.round((f.transition_ms * talker.coart) / rate)
    return out
  })
}

/** 1단계 입모양 반복(lib/visemeCycle의 {v, ms, t})에 같은 타이밍 변환을 입힌다. */
export function applyTalkerCycle(steps, talker, seed = 0) {
  if (isDefault(talker)) return steps
  const frames = applyTalkerTiming(steps.map((s) => ({ viseme: s.v, duration_ms: s.ms, transition_ms: s.t })), talker, seed)
  return frames.map((f, i) => ({ ...steps[i], ms: f.duration_ms, t: Number.isFinite(steps[i].t) ? f.transition_ms : steps[i].t }))
}

// ── 레슨별 화자 고르기 ──
// 다섯 레슨 묶음마다 첫 레슨은 기본 화자(사전·사후 검사의 얼굴을 계속 보게), 나머지 넷은 훈련용 화자 네 명을 사용자·단계·묶음으로
// 정한 순서로 낸다. 결정론적이라 같은 사용자의 같은 레슨 번호는 늘 같은 화자다. 검사 전용 화자는 나오지 않는다.
export const TALKER_BLOCK = TRAINING_TALKERS.length + 1

export function lessonTalker(userKey, stage, lessonIndex) {
  const n = Math.max(0, Math.floor(Number(lessonIndex) || 0))
  const pos = n % TALKER_BLOCK
  if (pos === 0) return DEFAULT_TALKER
  const block = Math.floor(n / TALKER_BLOCK)
  const seed = hashSeed(`${userKey}|${stage}|${block}`)
  // 씨앗으로 섞은 순서(Fisher-Yates, unitNoise로 결정)
  const order = [...TRAINING_TALKERS]
  for (let i = order.length - 1; i > 0; i--) {
    const j = Math.floor(((unitNoise(seed, i) + 1) / 2) * (i + 1)) % (i + 1)
    ;[order[i], order[j]] = [order[j], order[i]]
  }
  return order[pos - 1]
}

/** 레슨 흔들림 씨앗(사용자·단계·레슨 번호). */
export function lessonSeed(userKey, stage, lessonIndex) {
  return hashSeed(`${userKey}|${stage}|lesson${lessonIndex}`)
}
