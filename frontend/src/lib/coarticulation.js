/**
 * 선행 동시조음(CLAUDE.md 3D 모션 E, docs/coarticulation-e.md).
 *
 * 입 안쪽에서 조음하는 자음(치경 6·연구개 7·성문 8·경구개 10)과 그 전환 프레임(12·13)은 입술이 할 일이 없어, 실제 화자는
 * 입술을 이웃 모음 모양으로 미리 만들어 둔다(수술: ㅅ을 내는 동안에도 입술이 둥글다). 예전 아바타는 이 프레임들의 입술 모양이
 * 모음과 상관없이 고정이라 '수술'에서 입술이 다섯 번 벌어졌다 오므라들었다. 실제 화자에게 없는 단서를 가르치는 셈이다.
 *
 * 여기서는 그런 프레임의 입술 둥글림·당김 모프(LIP_KEYS)만 같은 단어 안의 다음 모음 쪽으로 w만큼 섞는다. 다음 모음이 없으면
 * (단어 끝 받침) 앞 모음을 이어 쓴다. 섞을 때 자음 자기 입술 모양(경구개 10의 살짝 내밂·당김)은 줄이지 않고, 모음이 더 크게 쓰는
 * 모프만 그 차이의 w만큼 더한다. 그냥 섞으면 '자'의 ㅈ이 입술 모양을 잃어 중설모음(5)과 가장 가까워진다(판별 기준 (d),
 * talkers.test.mjs). 턱(jawOpen)·양순 폐쇄(mouthClose·Press·Roll)·혀는 그대로 둔다. 프레임의 viseme은 바꾸지 않고
 * coart_v(섞을 모음 입모양)만 붙이므로 입모양 열 서명(content_rules.word_visemes)과 채점은 달라지지 않는다.
 *
 * 파드 검증(538 실제 화자 입술 궤적과의 상관)이 확인되기 전까지는 꺼 둔다. 켜려면 빌드 환경 변수 VITE_COART_E=1.
 * 같은 표·규칙을 파드 스크립트(scripts/coart_pod_eval.py)가 scripts/viseme_shapes.json으로 읽는다(생성: scripts/export_viseme_shapes.mjs).
 */

// 빌드 시 Vite가 import.meta.env를 채운다. node 테스트에서는 비어 있어 꺼진다.
const ENV = (typeof import.meta !== 'undefined' && import.meta.env) || {}
export const COART_E_ENABLED = ENV.VITE_COART_E === '1'

// 섞는 대상: 입 안쪽 자음과 그 전환 프레임. 양순(1)·양순 전환(11)은 입술을 닫아야 해서 뺀다.
export const COART_TARGETS = new Set([6, 7, 8, 10, 12, 13])
// 섞을 모음 입모양. 이중모음은 엔진이 활음 프레임(원순 4 등)부터 내므로 w계 앞 자음은 원순을 미리 만든다. 정지 모양 9는 엔진이
// 더 내지 않지만, 들어오면 활음 시작인 원순(4)으로 섞는다(이중모음 7개 가운데 6개가 원순 활음으로 시작한다).
export const COART_VOWELS = new Set([2, 3, 4, 5, 9])
const LIP_OF = { 9: 4 }
// 단어 경계(쉼·중립)는 넘지 않는다.
export const COART_STOPS = new Set([14, 15])
// 섞는 모프: 입술 둥글림(돌출)과 좌우 당김. 벌림(jawOpen·UpperUp·LowerDown)과 닫힘은 자음 자기 값을 둔다.
export const LIP_KEYS = ['mouthFunnel', 'mouthPucker', 'mouthSmileLeft', 'mouthSmileRight', 'mouthStretchLeft', 'mouthStretchRight']
// 기본 섞는 비율(0.5~0.7 가운데 잠정값, 파드 탐색 절반에서 고른 값으로 바꾼다)과 가상 화자 동시조음 배율을 곱했을 때의 상한
export const COART_W = 0.6
export const COART_W_MAX = 0.85

/** 가상 화자(lib/talkers)의 동시조음 강도(coart)를 곱한 섞는 비율. 화자가 없으면 기본값. */
export function coartWeight(talker) {
  const c = talker && Number.isFinite(talker.coart) ? talker.coart : 1
  return Math.max(0, Math.min(COART_W_MAX, COART_W * c))
}

/**
 * 프레임 배열에 섞을 모음(coart_v)을 붙인 새 배열. 꺼져 있거나 붙일 프레임이 없으면 frames를 그대로 돌려준다.
 * 같은 단어 안의 다음 모음을 먼저 보고(선행), 없으면 앞 모음을 쓴다(단어 끝 받침의 잔류). 프레임을 받을 때 한 번만 돈다.
 */
export function applyCoarticulation(frames, enabled = COART_E_ENABLED) {
  if (!enabled || !Array.isArray(frames) || frames.length === 0) return frames
  const n = frames.length
  const next = new Array(n)
  let nv = null
  for (let i = n - 1; i >= 0; i--) {
    const v = frames[i]?.viseme
    if (COART_STOPS.has(v)) nv = null
    else if (COART_VOWELS.has(v)) nv = v
    next[i] = nv
  }
  let pv = null
  let changed = false
  const out = frames.map((f, i) => {
    const v = f?.viseme
    if (COART_STOPS.has(v)) pv = null
    else if (COART_VOWELS.has(v)) pv = v
    if (!f || !COART_TARGETS.has(v)) return f
    const lv = next[i] ?? pv
    if (lv == null) return f
    changed = true
    return { ...f, coart_v: LIP_OF[lv] ?? lv }
  })
  return changed ? out : frames
}

/**
 * 자음 모양 base의 LIP_KEYS를 모음 모양 vowel 쪽으로 w만큼 섞은 새 모양: max(자음 값, (1 − w)·자음 값 + w·모음 값).
 * 모음이 더 크게 쓰는 모프만 늘고, 자음 자기 입술 모양은 줄지 않는다. 순수 함수(파드 스크립트가 같은 식을 쓴다).
 */
export function blendLip(base, vowel, w) {
  const out = { ...(base || {}) }
  for (const k of LIP_KEYS) {
    const b = (base && base[k]) || 0
    const x = Math.max(b, (1 - w) * b + w * ((vowel && vowel[k]) || 0))
    if (x > 0) out[k] = x
  }
  return out
}

// 표(가상 화자별 모양 표)마다 섞은 모양을 한 번만 만든다. 렌더러는 입모양이 바뀔 때 한 번 읽고, 화면마다 새로 계산하지 않는다.
const CACHE = new WeakMap()
/** 목표 모양: 섞을 모음이 없거나 대상이 아니면 table[visemeId] 그대로, 있으면 섞은 모양(캐시). */
export function coartShape(table, visemeId, lipVowel, w = COART_W) {
  const base = table[visemeId]
  if (lipVowel == null || !COART_TARGETS.has(visemeId) || !(w > 0)) return base
  let m = CACHE.get(table)
  if (!m) { m = new Map(); CACHE.set(table, m) }
  const key = `${visemeId}|${lipVowel}|${w}`
  let s = m.get(key)
  if (!s) { s = blendLip(base, table[lipVowel], w); m.set(key, s) }
  return s
}
