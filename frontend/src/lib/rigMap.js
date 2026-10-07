/**
 * 음성 구동·거울 경로의 리그 보정(V15 5절, docs/viseme-calibration-2026-10.md).
 *
 * 음성 구동(A4)과 웹캠 거울은 MediaPipe가 사람 얼굴에서 잰 ARKit 계수를 그대로 CC 두상 모프에 넣어 왔다. V13 왕복 검사(538 실제 화자
 * 계수 → 아바타 렌더 → 같은 MediaPipe로 재측정)에서 mouthClose는 r 0.25, 기울기 0.06으로 거의 전달되지 않았다. 리그 측정(정지 자세
 * 스윕) 결과 원인은 두 가지다.
 *   1) 이 두상은 턱 뼈를 약 0.15(4.5°)까지 돌려도 입술이 붙어 있다(사각 지대). 사람 계수의 작은 jawOpen은 입술을 거의 벌리지 못한다.
 *   2) MediaPipe의 mouthClose는 '턱이 열린 채 입술이 닫힌' 모양에서만 오른다. CC의 mouthClose 모프는 턱을 연 만큼(가중치 ≈ 턱)
 *      걸어야 입술을 붙이는데, 사람 계수의 mouthClose는 0.02~0.1로 작아 모프로는 효과가 없다.
 * CC 전용 입술 모프(Mouth_Lips_Jaw_Adjust, V_Explosive, Mouth_Plosive, Mouth_Lips_Tight 등)도 재 보았지만 MediaPipe mouthClose를
 * 올리지 못해 쓰지 않는다.
 *
 * 그래서 원본 계수(좌우는 평균)의 선형 결합으로 아바타 모프 13축을 다시 정한다. 계수는 탐색 절반 V13 클립 74개에서, 아바타 렌더가
 * 원본 계수와 같은 MediaPipe 값을 내도록 순방향 사상(모프 → MediaPipe, 정지 자세 3,798개와 렌더로 학습)을 거꾸로 푼 자세에 능선
 * 회귀로 맞췄다. 같은 클립을 다시 렌더해 재면 mouthClose r 중앙값이 0.345 → 0.541, jawOpen 0.784 → 0.816, 돌출 0.835 → 0.825,
 * 폭 0.710 → 0.714였다(채택 기준: mouthClose +0.10 이상, 다른 채널 −0.02 이내).
 *
 * 이 사상에 들지 않는 계수(눈·눈썹·볼·턱 좌우 등)는 그대로 넘긴다. 결과는 0~1로 자른다. 텍스트 입모양(규칙 엔진)에는 쓰지 않는다.
 */

// 입력: 좌우가 있는 계수는 (왼쪽 + 오른쪽)/2
export const RIG_MAP_INPUTS = ['jawOpen', 'mouthClose', 'mouthFunnel', 'mouthPucker', 'mouthSmile', 'mouthStretch', 'mouthUpperUp',
  'mouthLowerDown', 'mouthPress', 'mouthRollLower', 'mouthRollUpper', 'mouthShrugLower', 'mouthShrugUpper']

// 출력 축 → [절편, 입력별 계수(RIG_MAP_INPUTS 순서)]. 좌우 축은 왼쪽·오른쪽 모프에 같은 값을 넣는다.
export const RIG_MAP = {
  jawOpen: [0.047, [0.896, 0.568, -0.006, 0.097, -0.001, -0.045, 0.016, -0.091, 0.026, 0.051, 0.078, -0.129, -0.107]],
  mouthClose: [0.035, [0.001, 0.972, -0.497, 0.19, -0.002, -0.019, -0.017, -0.08, -0.045, 0.251, 0.038, 0.033, -0.223]],
  mouthPress: [0.027, [-0.149, -0.028, -0.019, 0.016, 0.148, -0.008, 0.059, 0.074, 0.584, 0.342, 0.169, 0.185, -0.02]],
  mouthRollLower: [-0.018, [0.183, 0.675, -0.265, 0.054, 0.057, 0.003, 0.093, 0.187, 0.293, 0.355, 0.037, 0.349, 0.19]],
  mouthRollUpper: [0.133, [-0.043, 0.047, 0.089, -0.165, 0, -0.093, -0.237, 0.187, 0.338, -0.138, 0.917, -0.159, -0.231]],
  mouthFunnel: [0.059, [0.098, -0.301, 0.162, -0.011, -0.088, -0.124, 0.363, 0.367, -0.204, 0.13, 0.148, -0.02, 0.225]],
  mouthPucker: [0.101, [-0.311, -0.047, 0.663, 0.483, -0.042, -0.066, -0.135, 0.032, -0.205, -0.352, -0.21, -0.01, -0.01]],
  mouthSmile: [0.054, [-0.141, 0.281, -0.064, -0.004, 0.536, -0.006, 0.027, -0.077, 0.178, -0.069, -0.104, -0.049, -0.156]],
  mouthStretch: [0.046, [0.055, -0.045, -0.173, -0.038, 0.282, 0.3, -0.238, 0.257, 0.352, 0.243, -0.001, 0.206, 0.431]],
  mouthUpperUp: [0.013, [-0.051, 0.103, -0.009, 0.002, 0.07, 0.039, 0.677, 0.102, 0.043, -0.039, -0.022, 0.05, 0.149]],
  mouthLowerDown: [0.084, [-0.037, 0.279, 0.032, -0.068, 0.321, 0.242, 0.043, 0.574, -0.125, -0.002, -0.076, -0.117, -0.016]],
  mouthShrugUpper: [0.015, [-0.027, -0.028, -0.069, 0.055, 0.073, 0.094, 0.237, 0.347, -0.023, 0.049, -0.098, 0.107, 0.254]],
  mouthShrugLower: [0, [-0.021, -0.008, 0.026, 0.021, 0.095, 0.033, -0.071, -0.031, 0.203, 0.196, 0.193, 0.345, 0.126]],
}

const PAIRED = new Set(['mouthSmile', 'mouthStretch', 'mouthUpperUp', 'mouthLowerDown', 'mouthPress'])
const clamp01 = (x) => (x < 0 ? 0 : x > 1 ? 1 : x)
const val = (f, k) => (PAIRED.has(k) ? ((f[`${k}Left`] || 0) + (f[`${k}Right`] || 0)) / 2 : (f[k] || 0))

/** 원본 계수 프레임(이름 → 값) → 아바타 모프 목표. 같은 원본 객체를 다시 받으면 앞서 만든 결과를 돌려준다(화면마다 새로 계산하지 않게). */
const CACHE = new WeakMap()
export function mapRawFrame(frame) {
  if (!frame || typeof frame !== 'object') return frame
  const hit = CACHE.get(frame)
  if (hit) return hit
  const x = RIG_MAP_INPUTS.map((k) => val(frame, k))
  const out = {}
  for (const [k, v] of Object.entries(frame)) out[k] = clamp01(Number(v) || 0)
  for (const [k, [b, w]] of Object.entries(RIG_MAP)) {
    let y = b
    for (let i = 0; i < w.length; i++) y += w[i] * x[i]
    y = clamp01(y)
    if (PAIRED.has(k)) { out[`${k}Left`] = y; out[`${k}Right`] = y } else out[k] = y
  }
  CACHE.set(frame, out)
  return out
}
