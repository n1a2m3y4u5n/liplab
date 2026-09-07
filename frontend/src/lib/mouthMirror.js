/**
 * 웹캠 입모양 → 아바타 미러링 (고도화 축 F) — 순수 함수, 서버 불필요.
 *
 * 계획서 3.6: "아바타가 표준 얼굴 계수 규격을 따르므로, 웹캠에서 읽은 사용자의 입모양을
 * 아바타에 그대로 비추는 거울 기능이 자연스럽게 구현된다."
 *
 * 실제로 두 규격 모두 ARKit 표준 블렌드셰이프 이름을 쓴다:
 *   · MediaPipe FaceLandmarker 출력 52계수 = ARKit 이름(jawOpen, mouthPucker …)
 *   · realistic_face.glb 의 모프타깃 = 같은 ARKit 이름
 * 따라서 이 모듈은 '변환 매핑'이 아니라 **이름 일치 + 신호 정리**를 한다.
 *
 * MIRROR_KEYS는 GLB의 targetNames를 직접 파싱해 **존재가 확인된 키만** 담았다
 * (visemeShapes.js가 세운 "실제 있는 모프만 쓴다" 원칙과 동일). 없는 키는 렌더러가
 * 건너뛰지만, 애초에 넣지 않아 매 프레임 헛도는 계산을 없앤다.
 *
 * 영상·계수는 기기 밖으로 나가지 않는다(축 D와 동일 — 서버 전송 없음).
 */

/**
 * 미러링할 모프타깃 키. realistic_face.glb `base` 메시(66개 타깃)에 존재를 확인한
 * 입·턱·볼·코 영역만 담는다. 눈·눈썹은 독화 학습과 무관하고 아바타 카메라가 입
 * 클로즈업이라 제외한다.
 *
 * jawOpen·jawForward·jawLeft·jawRight는 base뿐 아니라 teeth_base·tongue01에도 있어,
 * 이름으로 일괄 적용하면 턱을 따라 치아·혀가 함께 움직인다(기존 렌더러와 동일 동작).
 */
export const MIRROR_KEYS = [
  // 턱
  'jawOpen', 'jawForward', 'jawLeft', 'jawRight',
  // 입술 — 열림/오므림/내밈
  'mouthClose', 'mouthFunnel', 'mouthPucker',
  // 입술 — 좌우 이동·당김
  'mouthLeft', 'mouthRight',
  'mouthSmileLeft', 'mouthSmileRight',
  'mouthFrownLeft', 'mouthFrownRight',
  'mouthDimpleLeft', 'mouthDimpleRight',
  'mouthStretchLeft', 'mouthStretchRight',
  // 입술 — 말림/압착
  'mouthRollLower', 'mouthRollUpper',
  'mouthShrugLower', 'mouthShrugUpper',
  'mouthPressLeft', 'mouthPressRight',
  // 입술 — 상하 노출(치아 드러남)
  'mouthLowerDownLeft', 'mouthLowerDownRight',
  'mouthUpperUpLeft', 'mouthUpperUpRight',
  // 입술 너머 — 볼·코 (축 K가 다루는 조음 단서와 같은 신호)
  'cheekPuff', 'cheekSquintLeft', 'cheekSquintRight',
  'noseSneerLeft', 'noseSneerRight',
]

export const DEFAULT_MIRROR_OPTIONS = {
  // 지수이동평균 계수(0~1). 클수록 새 프레임을 빨리 따라가고, 작을수록 부드럽지만 느리다.
  // 웹캠 계수는 프레임마다 미세하게 떨리므로 기본값은 반응성과 안정 사이에서 잡는다.
  smoothing: 0.5,
  // 표시 증폭. MediaPipe 계수는 실제 조음보다 작게 나오는 경향이 있어, 학습자가 자기
  // 입모양 변화를 눈으로 알아보게 하려면 약간의 증폭이 필요하다. 과장은 오해를 부르므로
  // 기본은 절제된 값으로 두고 clamp(0~1)로 상한을 지킨다.
  gain: 1.15,
  // 이보다 작은 값은 0으로 — 무표정일 때 아바타가 미세하게 떠는 것을 막는다.
  deadzone: 0.02,
}

/** 0~1로 자르기. */
function clamp01(v) {
  return v < 0 ? 0 : v > 1 ? 1 : v
}

/**
 * 웹캠 blendshape 맵 → 아바타 모프 목표값 맵.
 *
 * @param {Object} blendshapeMap  MediaPipe 계수 {name: 0~1} (mouthScore.toBlendshapeMap 결과)
 * @param {Object|null} prev      직전 프레임의 결과(지수이동평균용). 없으면 첫 프레임으로 본다.
 * @param {Object} options        {smoothing, gain, deadzone}
 * @returns {Object} MIRROR_KEYS 전 키에 대한 0~1 목표값 (없던 키는 0)
 */
export function mirrorWeights(blendshapeMap, prev, options) {
  const { smoothing, gain, deadzone } = { ...DEFAULT_MIRROR_OPTIONS, ...(options || {}) }
  const out = {}
  const src = blendshapeMap || {}
  for (const key of MIRROR_KEYS) {
    const raw = src[key] || 0
    // 데드존 → 증폭 → 클램프 순. 데드존을 먼저 적용해야 잡음이 증폭되지 않는다.
    const gated = raw < deadzone ? 0 : raw
    const target = clamp01(gated * gain)
    const before = prev ? (prev[key] || 0) : target
    out[key] = before + (target - before) * smoothing
  }
  return out
}

/**
 * 미러가 실제로 얼굴을 잡고 있는지(= 아바타를 움직일 근거가 있는지) 판정.
 * 얼굴을 놓치면 blendshape 맵이 비므로, 그 상태로 아바타를 0으로 밀어버리기보다
 * 호출부가 "얼굴이 안 보인다"를 안내하도록 신호만 준다.
 */
export function hasFaceSignal(blendshapeMap) {
  return !!blendshapeMap && Object.keys(blendshapeMap).length > 0
}

/**
 * 미러링 활성도(0~1 근사) — 사용자가 입을 얼마나 움직이고 있는지의 요약값.
 * UI에서 "지금 잡히고 있음"을 보여주는 용도이지 채점이 아니다(채점은 축 D의 mouthScore).
 */
export function mirrorActivity(weights) {
  if (!weights) return 0
  let sum = 0
  for (const key of MIRROR_KEYS) sum += weights[key] || 0
  // 실사용에서 동시에 크게 켜지는 키는 대여섯 개 남짓이라 그 정도를 만점으로 정규화한다.
  return clamp01(sum / 6)
}
