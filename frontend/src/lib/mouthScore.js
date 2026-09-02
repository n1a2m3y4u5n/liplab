/**
 * 웹캠 입모양 채점 (고도화 축 D) — 순수 함수, 서버 불필요.
 *
 * MediaPipe Face Landmarker가 브라우저에서 뽑은 얼굴 blendshape(ARKit 계열 52계수) 중
 * 입 관련 차원만 골라, 목표 비심(viseme)의 기준 프로파일과 코사인 유사도로 채점한다.
 * 영상·계수는 기기 밖으로 나가지 않는다(프라이버시).
 *
 * 기준 프로파일은 조음 음성학에 근거한 규칙값이다(데이터 없이 착수). 실제 정합은
 * 웹캠 실측으로 보정하는 것을 전제로 한 프로토타입 초기값이다.
 */

// 입 모양을 특징짓는 blendshape 공통 차원(MediaPipe FaceLandmarker 카테고리명)
export const MOUTH_KEYS = [
  'jawOpen', 'mouthClose', 'mouthPucker', 'mouthFunnel',
  'mouthStretchLeft', 'mouthStretchRight', 'mouthSmileLeft', 'mouthSmileRight',
  'mouthUpperUpLeft', 'mouthUpperUpRight', 'mouthRollLower', 'mouthRollUpper',
]

// viseme(1~10) → 목표 blendshape 값(0~1). 명시 안 한 키는 0.
export const VISEME_PROFILES = {
  1: { mouthClose: 0.8, jawOpen: 0.05, mouthRollLower: 0.3, mouthRollUpper: 0.3 }, // 양순(입술 닫힘)
  2: { jawOpen: 0.75 },                                                            // 개방모음(ㅏ)
  3: { jawOpen: 0.15, mouthStretchLeft: 0.5, mouthStretchRight: 0.5, mouthSmileLeft: 0.3, mouthSmileRight: 0.3 }, // 전설(ㅣ)
  4: { jawOpen: 0.25, mouthPucker: 0.7, mouthFunnel: 0.5 },                         // 원순(ㅗㅜ)
  5: { jawOpen: 0.3 },                                                              // 중설(ㅓㅡ)
  6: { jawOpen: 0.15, mouthClose: 0.1 },                                            // 치경(ㄷㄴㄹㅅ)
  7: { jawOpen: 0.12 },                                                             // 연구개(ㄱㅋ)
  8: { jawOpen: 0.25 },                                                             // 성문(ㅎ)
  9: { jawOpen: 0.3, mouthPucker: 0.3, mouthFunnel: 0.2 },                          // 이중모음
  10: { jawOpen: 0.15, mouthPucker: 0.15, mouthUpperUpLeft: 0.1, mouthUpperUpRight: 0.1 }, // 경구개(ㅈㅊ)
}

/** blendshape 배열/객체를 {name: score} 맵으로 정규화. */
export function toBlendshapeMap(categories) {
  const map = {}
  if (!categories) return map
  const list = Array.isArray(categories) ? categories : (categories.categories || [])
  for (const c of list) {
    const name = c.categoryName || c.displayName || c.name
    if (name) map[name] = c.score ?? c.value ?? 0
  }
  return map
}

// ── 개인 캘리브레이션 ───────────────────────────────────────────────────────
// 사람마다 얼굴이 달라 규칙 기준값과 오차가 있다. 사용자가 각 입모양을 직접 '본뜨면'
// 그 실측 blendshape 평균을 개인 기준으로 저장한다. localStorage에만 두어 기기 밖으로
// 나가지 않는다(프라이버시). 저장이 없으면 규칙 기준값(VISEME_PROFILES)으로 폴백한다.
const CALIB_KEY = 'liplab_mouth_calibration_v1'

export function loadCalibration() {
  try { return JSON.parse(localStorage.getItem(CALIB_KEY)) || null } catch { return null }
}
export function saveCalibration(profiles) {
  try { localStorage.setItem(CALIB_KEY, JSON.stringify(profiles)); return true } catch { return false }
}
export function clearCalibration() {
  try { localStorage.removeItem(CALIB_KEY) } catch { /* noop */ }
}

/** 여러 프레임의 입 관련 blendshape를 평균내 한 viseme의 기준 프로파일로. */
export function averageBlendshapes(frames) {
  const n = frames.length
  const avg = {}
  for (const k of MOUTH_KEYS) {
    let s = 0
    for (const f of frames) s += f[k] || 0
    avg[k] = n ? Number((s / n).toFixed(3) ) : 0
  }
  return avg
}

/** 목표 viseme 대비 코사인 유사도(0~1). profiles로 개인 캘리브레이션을 넘길 수 있다. */
export function cosineScore(blendshapeMap, visemeId, profiles = VISEME_PROFILES) {
  const prof = profiles[visemeId] || VISEME_PROFILES[visemeId]
  if (!prof) return 0
  let dot = 0, na = 0, nb = 0
  for (const k of MOUTH_KEYS) {
    const a = prof[k] || 0
    const b = blendshapeMap[k] || 0
    dot += a * b
    na += a * a
    nb += b * b
  }
  if (na === 0 || nb === 0) return 0
  return dot / (Math.sqrt(na) * Math.sqrt(nb))
}

/** 0~100 점수. profiles로 개인 캘리브레이션을 넘길 수 있다. */
export function scorePercent(blendshapeMap, visemeId, profiles = VISEME_PROFILES) {
  return Math.round(cosineScore(blendshapeMap, visemeId, profiles) * 100)
}

/** 목표 대비 가장 부족/과한 차원을 한 줄 코칭으로. */
export function coachHint(blendshapeMap, visemeId, profiles = VISEME_PROFILES) {
  const prof = profiles[visemeId] || VISEME_PROFILES[visemeId]
  if (!prof) return ''
  const labels = {
    jawOpen: '입을 더 벌려', mouthClose: '입술을 더 붙여', mouthPucker: '입술을 더 오므려',
    mouthFunnel: '입술을 앞으로 내밀어', mouthStretchLeft: '입을 옆으로 당겨',
    mouthStretchRight: '입을 옆으로 당겨',
  }
  let worstKey = null, worstGap = 0.15
  for (const k of Object.keys(prof)) {
    const gap = (prof[k] || 0) - (blendshapeMap[k] || 0)
    if (gap > worstGap) { worstGap = gap; worstKey = k }
  }
  return worstKey ? (labels[worstKey] || '입모양을 조정해') + '보세요' : '좋아요, 그대로 유지!'
}
