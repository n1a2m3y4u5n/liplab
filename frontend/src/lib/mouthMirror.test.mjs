// 웹캠→아바타 미러링(축 F) 순수 함수 검증. 실행: node --test
import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  MIRROR_KEYS, DEFAULT_MIRROR_OPTIONS, mirrorWeights, hasFaceSignal, mirrorActivity,
} from './mouthMirror.js'
import { ACTIVE_MORPH_KEYS } from './visemeShapes.js'

// GLB(realistic_face.glb) base 메시 targetNames를 직접 파싱해 얻은 목록에서
// 입·턱·볼·코 영역만 추린 것. 미러 키가 모델에 실제로 존재하는지 지키는 회귀 테스트다.
// (모델을 교체하면 이 목록도 함께 갱신해야 한다.)
const GLB_BASE_TARGETS = new Set([
  'browDownRight', 'viseme_RR', 'mouthShrugLower', 'browDownLeft', 'jawRight', 'mouthFunnel',
  'eyeSquintRight', 'mouthPressRight', 'eyeLookOutLeft', 'mouthFrownLeft', 'eyeWideLeft',
  'mouthDimpleRight', 'jawForward', 'viseme_FF', 'tongueOut', 'cheekPuff', 'jawLeft',
  'noseSneerLeft', 'eyeLookOutRight', 'viseme_PP', 'browInnerUp', 'viseme_DD', 'viseme_aa',
  'mouthShrugUpper', 'noseSneerRight', 'mouthLowerDownRight', 'viseme_kk', 'viseme_nn',
  'mouthStretchLeft', 'mouthLowerDownLeft', 'mouthClose', 'cheekSquintLeft', 'eyeBlinkLeft',
  'mouthPressLeft', 'eyeLookUpLeft', 'eyeSquintLeft', 'mouthPucker', 'viseme_TH', 'viseme_SS',
  'eyeLookDownRight', 'mouthSmileRight', 'eyeWideRight', 'viseme_E', 'mouthDimpleLeft',
  'eyeBlinkRight', 'viseme_I', 'eyeLookInRight', 'mouthLeft', 'mouthRollUpper', 'mouthFrownRight',
  'eyeLookDownLeft', 'jawOpen', 'viseme_U', 'mouthUpperUpRight', 'mouthSmileLeft',
  'browOuterUpLeft', 'mouthRollLower', 'mouthUpperUpLeft', 'mouthStretchRight', 'eyeLookUpRight',
  'mouthRight', 'viseme_O', 'eyeLookInLeft', 'browOuterUpRight', 'viseme_CH', 'cheekSquintRight',
])

test('MIRROR_KEYS: 전 키가 GLB 모프타깃에 실제로 존재한다', () => {
  const missing = MIRROR_KEYS.filter((k) => !GLB_BASE_TARGETS.has(k))
  assert.deepEqual(missing, [], `모델에 없는 키는 쓰지 않는다: ${missing.join(', ')}`)
})

test('MIRROR_KEYS: 눈·눈썹은 미러링하지 않는다(독화와 무관, 입 클로즈업 카메라)', () => {
  const offTopic = MIRROR_KEYS.filter((k) => k.startsWith('eye') || k.startsWith('brow'))
  assert.deepEqual(offTopic, [])
})

test('MIRROR_KEYS는 ACTIVE_MORPH_KEYS의 상위집합이어야 한다', () => {
  // AvatarVRM은 거울 모드를 받은 인스턴스에서 MIRROR_KEYS만 보간한다. 이 집합이 viseme
  // 매핑이 쓰는 키를 하나라도 빠뜨리면, 거울을 끈 뒤 그 키가 직전 값에 얼어붙어 얼굴에
  // 남는다(개발일지 3절에 기록된 '0으로 복귀하지 않는 모프' 함정).
  const mirror = new Set(MIRROR_KEYS)
  const uncovered = ACTIVE_MORPH_KEYS.filter((k) => !mirror.has(k))
  assert.deepEqual(uncovered, [], `거울이 덮지 못하는 viseme 모프: ${uncovered.join(', ')}`)
})

test('mirrorWeights: 첫 프레임은 평활 없이 목표값에 바로 도달', () => {
  // prev가 없으면 이전값=목표값으로 두므로 EMA가 그대로 목표를 반환해야 한다
  // (첫 프레임에 0에서 서서히 올라오는 지연이 생기지 않게).
  const w = mirrorWeights({ jawOpen: 0.5 }, null, { gain: 1, deadzone: 0 })
  assert.equal(w.jawOpen, 0.5)
})

test('mirrorWeights: 평활이 이전 프레임과 목표 사이를 보간한다', () => {
  const prev = { jawOpen: 0 }
  const w = mirrorWeights({ jawOpen: 1 }, prev, { smoothing: 0.5, gain: 1, deadzone: 0 })
  assert.equal(w.jawOpen, 0.5, 'smoothing 0.5면 절반만 이동')

  const slow = mirrorWeights({ jawOpen: 1 }, prev, { smoothing: 0.1, gain: 1, deadzone: 0 })
  assert.ok(slow.jawOpen < w.jawOpen, 'smoothing이 작을수록 더 천천히 따라간다')
})

test('mirrorWeights: 데드존 이하 잡음은 0으로 눌린다', () => {
  const w = mirrorWeights({ jawOpen: 0.01, mouthPucker: 0.5 }, null, { deadzone: 0.02, gain: 1 })
  assert.equal(w.jawOpen, 0, '데드존 미만은 0')
  assert.ok(w.mouthPucker > 0, '데드존 이상은 살아남음')
})

test('mirrorWeights: 데드존이 증폭보다 먼저 적용된다(잡음 증폭 방지)', () => {
  // gain을 크게 줘도 데드존 미만 잡음은 0이어야 한다. 순서가 뒤바뀌면 0.01*10=0.1이 살아난다.
  const w = mirrorWeights({ jawOpen: 0.01 }, null, { deadzone: 0.02, gain: 10 })
  assert.equal(w.jawOpen, 0)
})

test('mirrorWeights: 증폭해도 1을 넘지 않는다', () => {
  const w = mirrorWeights({ jawOpen: 0.9 }, null, { gain: 3, deadzone: 0 })
  assert.equal(w.jawOpen, 1, 'clamp 상한')
  assert.ok(w.jawOpen <= 1)
})

test('mirrorWeights: 결과는 항상 MIRROR_KEYS 전 키를 채운다(없던 키는 0)', () => {
  const w = mirrorWeights({ jawOpen: 0.4 }, null)
  for (const k of MIRROR_KEYS) {
    assert.equal(typeof w[k], 'number', `${k} 누락`)
    assert.ok(w[k] >= 0 && w[k] <= 1, `${k} 범위 이탈: ${w[k]}`)
  }
})

test('mirrorWeights: 빈 입력이면 전부 0(얼굴 놓쳤을 때 중립)', () => {
  const w = mirrorWeights({}, null)
  assert.ok(MIRROR_KEYS.every((k) => w[k] === 0))
})

test('mirrorWeights: 기본 옵션은 실제로 증폭·평활·데드존을 켜 둔다', () => {
  assert.ok(DEFAULT_MIRROR_OPTIONS.gain >= 1, '축소는 하지 않는다')
  assert.ok(DEFAULT_MIRROR_OPTIONS.gain <= 1.5, '과장은 오해를 부르므로 절제')
  assert.ok(DEFAULT_MIRROR_OPTIONS.smoothing > 0 && DEFAULT_MIRROR_OPTIONS.smoothing < 1)
  assert.ok(DEFAULT_MIRROR_OPTIONS.deadzone > 0)
})

test('hasFaceSignal: 빈 맵/누락은 얼굴 없음', () => {
  assert.equal(hasFaceSignal({ jawOpen: 0.1 }), true)
  assert.equal(hasFaceSignal({}), false)
  assert.equal(hasFaceSignal(null), false)
  assert.equal(hasFaceSignal(undefined), false)
})

test('mirrorActivity: 입을 많이 움직일수록 커지고 0~1을 벗어나지 않는다', () => {
  const still = mirrorWeights({}, null)
  const moving = mirrorWeights({ jawOpen: 0.8, mouthFunnel: 0.6, mouthPucker: 0.5 }, null)
  assert.equal(mirrorActivity(still), 0)
  assert.ok(mirrorActivity(moving) > 0)
  assert.ok(mirrorActivity(moving) <= 1)

  // 전 키가 만점이어도 상한을 넘지 않아야 한다
  const maxed = Object.fromEntries(MIRROR_KEYS.map((k) => [k, 1]))
  assert.equal(mirrorActivity(maxed), 1)
  assert.equal(mirrorActivity(null), 0)
})
