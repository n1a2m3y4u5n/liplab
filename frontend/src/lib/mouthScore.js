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
// v1은 자음 음절(마·다·가·하·자)에서도 활성도 정점을 뽑아 자음 기준이 모두 ㅏ 벌림으로 저장됐다. 그 기준으로는
// 입술을 닫은 얼굴이 양순음 5점, 입을 벌린 얼굴이 100점이 되어 채점이 뒤집혔다. v2부터 자음 자세를 따로 뽑고(pickCalibrationFrame)
// v1 저장값은 읽지 않고 지운다. 사용자는 다시 본떠야 개인 기준이 적용된다.
const CALIB_KEY = 'liplab_mouth_calibration_v2'
const OLD_CALIB_KEYS = ['liplab_mouth_calibration_v1']

export function loadCalibration() {
  try {
    for (const k of OLD_CALIB_KEYS) localStorage.removeItem(k)
    return JSON.parse(localStorage.getItem(CALIB_KEY)) || null
  } catch { return null }
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

/** 입 '활성도'(중립 대비 움직임 총량). 발음 정점을 찾는 데 쓴다. */
function mouthActivity(f) {
  let a = 0
  for (const k of MOUTH_KEYS) a += Math.abs(f[k] || 0)
  return a
}

/**
 * 발음하는 동안 모은 프레임에서 '정점(peak)'을 뽑는다. 마지막 정지 모습이 아니라
 * 입이 가장 크게 벌어진/닫힌 순간(활성도 상위 30%)을 평균내 노이즈를 줄인다.
 * 모음 음절(아·이·우·어·와)은 정점이 그 음소의 대표 입모양이다. 자음+ㅏ 음절에서는 정점이 ㅏ라서
 * 자음 기준에는 쓰지 않는다(pickCalibrationFrame).
 */
export function pickPeakFrame(frames) {
  if (!frames || !frames.length) return {}
  const scored = frames.map((f) => ({ f, act: mouthActivity(f) }))
  scored.sort((a, b) => b.act - a.act)
  const topN = Math.max(1, Math.ceil(scored.length * 0.3))
  return averageBlendshapes(scored.slice(0, topN).map((x) => x.f))
}

// 자음 비심. 본뜨기 음절이 자음+ㅏ(마·다·가·하·자)라 활성도 정점은 늘 뒤따르는 ㅏ 벌림이다. 자음 기준은 정점이 아니라
// 자음 자세에서 뽑는다(pickCalibrationFrame).
export const CONSONANT_VISEMES = new Set([1, 6, 7, 8, 10])
const CLOSURE_TOP = 0.1      // 양순음: 입술 닫힘 정도 상위 10% 프레임을 평균
const VOWEL_RISE = 0.2       // 턱 벌림이 이만큼 올라가야 모음(ㅏ)을 발음한 것으로 본다. 못 미치면 자음 자세를 멈춘 채 둔 것
const PRE_VOWEL_FRAMES = 6   // 모음이 열리기 직전 창(30 fps 카메라에서 약 0.2초)

/** 프레임별 입 관련 blendshape의 차원별 중앙값. 자세를 멈춘 채 둔 구간에서 깜박임·흔들림 같은 튀는 값을 무시한다. */
export function medianBlendshapes(frames) {
  const out = {}
  const n = frames.length
  for (const k of MOUTH_KEYS) {
    if (!n) { out[k] = 0; continue }
    const v = frames.map((f) => f[k] || 0).sort((a, b) => a - b)
    const m = n % 2 ? v[(n - 1) / 2] : (v[n / 2 - 1] + v[n / 2]) / 2
    out[k] = Number(m.toFixed(3))
  }
  return out
}

/**
 * 양순음(ㅁㅂㅍ) 기준: 입술이 가장 꽉 닫힌 순간. 닫힘 정도는 mouthClose에서 jawOpen을 뺀 값으로 잰다(ㅏ로 턱이 내려간
 * 프레임은 뒤로 밀린다). 상위 10%를 평균내 한 프레임의 노이즈를 줄인다.
 */
export function pickClosureFrame(frames) {
  if (!frames || !frames.length) return {}
  const scored = frames.map((f) => ({ f, c: (f.mouthClose || 0) - (f.jawOpen || 0) }))
  scored.sort((a, b) => b.c - a.c)
  const topN = Math.max(1, Math.ceil(scored.length * CLOSURE_TOP))
  return averageBlendshapes(scored.slice(0, topN).map((x) => x.f))
}

/**
 * 양순음 밖의 자음(ㄷ·ㄱ·ㅎ·ㅈ) 기준: 모음이 열리기 직전의 자세.
 * 턱 벌림(jawOpen)이 가장 큰 프레임을 모음 정점으로 보고, 정점 앞에서 턱이 정점까지 오르는 폭의 절반에 아직 못 미친
 * 마지막 프레임을 개방 시작으로 잡는다. 그 프레임까지의 직전 창(약 0.2초)을 평균낸다.
 * 턱이 크게 오르지 않았으면(모음 없이 자음 자세를 멈춘 채 둔 경우) 전체 구간의 중앙값을 쓴다.
 */
export function pickConsonantFrame(frames) {
  if (!frames || !frames.length) return {}
  const jaw = frames.map((f) => f.jawOpen || 0)
  let p = 0
  for (let i = 1; i < jaw.length; i++) if (jaw[i] > jaw[p]) p = i
  let base = jaw[p]
  for (let i = 0; i <= p; i++) if (jaw[i] < base) base = jaw[i]
  const rise = jaw[p] - base
  if (rise < VOWEL_RISE) return medianBlendshapes(frames)
  const thr = base + rise / 2
  let onset = p - 1
  while (onset >= 0 && jaw[onset] >= thr) onset--
  if (onset < 0) {
    // 벌린 채로 수집이 시작됐다. 정점 앞에 자음 구간이 없으니 턱이 절반 아래인 프레임(모음 뒤 닫힘)으로 대신한다
    const low = frames.filter((f, i) => jaw[i] < thr)
    return medianBlendshapes(low.length ? low : frames)
  }
  return averageBlendshapes(frames.slice(Math.max(0, onset - PRE_VOWEL_FRAMES + 1), onset + 1))
}

/** 본뜨기 한 번의 궤적에서 viseme에 맞는 기준 자세를 뽑는다. 모음은 정점, 자음은 자음 자세. */
export function pickCalibrationFrame(frames, visemeId) {
  if (visemeId === 1) return pickClosureFrame(frames)
  if (CONSONANT_VISEMES.has(visemeId)) return pickConsonantFrame(frames)
  return pickPeakFrame(frames)
}

/** 목표 viseme 대비 코사인 유사도(0~1). profiles로 개인 캘리브레이션을 넘길 수 있다(null 허용). */
export function cosineScore(blendshapeMap, visemeId, profiles) {
  const prof = (profiles && profiles[visemeId]) || VISEME_PROFILES[visemeId]
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

/**
 * 목표 대비 '크기(활성도) 정합' 0~1. 코사인은 방향만 보고 크기(얼마나 벌렸는지)를 무시하므로,
 * 목표 벡터와 실측 벡터의 L2 크기 차이를 벌점화한다. 이게 없으면 jawOpen만 살짝 켜도 개방모음이
 * 100점이 되고, 단일 축(jawOpen) 프로파일들(개방·중설·연구개·성문)이 서로 구별되지 않는다.
 */
export function magnitudeMatch(blendshapeMap, visemeId, profiles) {
  const prof = (profiles && profiles[visemeId]) || VISEME_PROFILES[visemeId]
  if (!prof) return 0
  let na = 0, nb = 0
  for (const k of MOUTH_KEYS) {
    const a = prof[k] || 0
    const b = blendshapeMap[k] || 0
    na += a * a
    nb += b * b
  }
  const magA = Math.sqrt(na)
  const magB = Math.sqrt(nb)
  if (magA === 0 && magB === 0) return 1
  const denom = Math.max(magA, magB)
  if (denom === 0) return 0
  return Math.max(0, 1 - Math.abs(magA - magB) / denom)
}

/** 0~100 점수 — 방향(코사인) × 크기 정합. profiles로 개인 캘리브레이션을 넘길 수 있다(null 허용). */
export function scorePercent(blendshapeMap, visemeId, profiles) {
  const cos = cosineScore(blendshapeMap, visemeId, profiles)
  const mag = magnitudeMatch(blendshapeMap, visemeId, profiles)
  return Math.round(cos * mag * 100)
}

/** 목표 대비 가장 부족/과한 차원을 한 줄 코칭으로. */
export function coachHint(blendshapeMap, visemeId, profiles) {
  const prof = (profiles && profiles[visemeId]) || VISEME_PROFILES[visemeId]
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
