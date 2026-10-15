/**
 * V3 간이판: 538 문맥 평균 궤적 표(docs/avatar-v3-2026-10.md). 빌드 플래그 VITE_VISEME_V3=1일 때만 단어·문장 재생에 쓴다.
 *
 * 규칙 엔진의 입모양 프레임과 타이밍(duration_ms / 재생 속도)을 그대로 받아, 30fps 사람 MediaPipe 계수(좌우 같은 값)를 만든다.
 * 아바타에는 음성 구동(A4)과 같은 bsFrameRef 경로로 입힌다(lib/rigMap 사상, LERP 34/s).
 *   - 엔진 프레임 하나를 구간 하나로 보고 시간으로 세 칸(앞·가운데·뒤)으로 나눈다.
 *   - 칸마다 (무리, 칸, 앞 모음 갈래, 뒤 모음 갈래) 열쇠로 표 값을 찾는다. 모음 갈래는 같은 어절(쉼 14·중립 15를 넘지 않음) 안의 가장 가까운
 *     앞·뒤 모음 무리(2 개방, 3 ㅣ, 4 원순(9 포함), 5 중설, 없으면 0)다. 표 값은 538 실제 구간 칸 계수의 평균(칸마다 20구간·5명 이상)이다.
 *   - 칸 가운데 시각에 값을 놓고 선형으로 잇는다. 발화 앞뒤는 쉼 구간이고, 그 칸은 발화에 붙은 쪽 1초 안에 둔다.
 *   - 표 평균 μ를 중심으로 채널 무리별 이득을 곱하고 0~1로 자른다.
 * scripts/v3_avatar.py의 같은 함수와 값이 같아야 한다(visemeV3.test.mjs가 기준 출력과 비교한다).
 */
import TABLE from './visemeV3Table.js'

const ENV = (typeof import.meta !== 'undefined' && import.meta.env) || {}
export const VISEME_V3_ENABLED = ENV.VITE_VISEME_V3 === '1'
export const V3_TABLE = TABLE

export const V3_CHANNELS = ['jawOpen', 'mouthClose', 'mouthFunnel', 'mouthPucker', 'smile', 'stretch', 'upperUp', 'lowerDown', 'press',
  'mouthRollLower', 'mouthRollUpper', 'mouthShrugLower', 'mouthShrugUpper']
const PAIR_OUT = { smile: 'mouthSmile', stretch: 'mouthStretch', upperUp: 'mouthUpperUp', lowerDown: 'mouthLowerDown', press: 'mouthPress' }
const GAIN_GROUPS = {
  open: ['jawOpen', 'upperUp', 'lowerDown'], round: ['mouthFunnel', 'mouthPucker'], width: ['smile', 'stretch'],
  close: ['mouthClose', 'press', 'mouthRollLower', 'mouthRollUpper', 'mouthShrugLower', 'mouthShrugUpper'],
}
const CH_GROUP = V3_CHANNELS.map((c) => Object.keys(GAIN_GROUPS).find((g) => GAIN_GROUPS[g].includes(c)))
const VOWEL_CLASS = { 2: 2, 3: 3, 4: 4, 5: 5, 9: 4 }
const NB = 3
const REST_SPAN = 1.0
const BILABIAL = new Set([1, 11])

function padSegments(segs) {
  const s = segs.map(([v, a, b]) => [v === 15 ? 14 : v, a, b])
  return [[14, s[0][1] - 1e3, s[0][1]], ...s, [14, s[s.length - 1][2], s[s.length - 1][2] + 1e3]]
}

function contexts(vs) {
  const out = []
  for (let i = 0; i < vs.length; i++) {
    let p = 0
    let n = 0
    for (let j = i - 1; j >= 0; j--) {
      if (vs[j] === 14 || vs[j] === 15) break
      if (VOWEL_CLASS[vs[j]]) { p = VOWEL_CLASS[vs[j]]; break }
    }
    for (let j = i + 1; j < vs.length; j++) {
      if (vs[j] === 14 || vs[j] === 15) break
      if (VOWEL_CLASS[vs[j]]) { n = VOWEL_CLASS[vs[j]]; break }
    }
    out.push([p, n])
  }
  return out
}

function segWindow(i, n, t0, t1) {
  if (i === 0) return [t1 - REST_SPAN, t1]
  if (i === n - 1) return [t0, t0 + REST_SPAN]
  return [t0, t1]
}

function lookup(cells, g, b, p, n, mode) {
  let base = cells[`${g}|${b}|*|*`]
  if (base == null) base = cells[`14|${b}|*|*`] || cells['14|1|*|*']
  if (mode === 'base') return base
  const full = cells[`${g}|${b}|${p}|${n}`]
  if (mode === 'full' && full != null) return full
  const a = cells[`${g}|${b}|*|${n}`]
  const c = cells[`${g}|${b}|${p}|*`]
  if (a != null && c != null) return a.map((x, k) => x + c[k] - base[k])
  return a != null ? a : (c != null ? c : base)
}

/** 구간(초) → 시각순 [시각, 13채널 값, 양순 표시] */
function anchors(segs, model) {
  const vs = segs.map((s) => s[0])
  const cx = contexts(vs)
  const out = []
  segs.forEach(([v, t0, t1], i) => {
    const [a, b2] = segWindow(i, segs.length, t0, t1)
    for (let b = 0; b < NB; b++) {
      out.push([a + ((b + 0.5) / NB) * (b2 - a), lookup(model.cells, v, b, cx[i][0], cx[i][1], model.mode), BILABIAL.has(v) ? 1 : 0])
    }
  })
  return out.map((x, k) => [...x, k]).sort((x, y) => (x[0] - y[0]) || (x[3] - y[3]))
}

function interp(at, vals, t) {
  // numpy.interp와 같음: 범위 밖은 끝 값
  const n = at.length
  if (t <= at[0]) return vals[0]
  if (t >= at[n - 1]) return vals[n - 1]
  let lo = 0
  let hi = n - 1
  while (hi - lo > 1) {
    const m = (lo + hi) >> 1
    if (at[m] <= t) lo = m; else hi = m
  }
  const w = (t - at[lo]) / (at[hi] - at[lo])
  return vals[lo] + (vals[hi] - vals[lo]) * w
}

/** 재생 일정(초): 앞 쉼 leadMs 뒤에 프레임을 duration_ms / speed씩 놓는다(LipSyncPlayer3D·하네스 renderText와 같은 길이). */
export function scheduleSegments(frames, speed = 1, leadMs = 400) {
  const segs = []
  let t = leadMs
  for (const f of frames || []) {
    const len = (Number(f.duration_ms) || 0) / speed
    segs.push([f.viseme, t / 1000, (t + len) / 1000])
    t += len
  }
  return { segs, start: leadMs / 1000, end: t / 1000 }
}

/**
 * 엔진 프레임 → 30fps 계수 목록(이름 → 값). 0번은 재생 시각 0(앞 쉼 시작). model.seal이 있으면 양순 구간 표시 _seal(0~1)을 붙인다
 * (rigMap이 아바타 mouthClose를 턱 각도까지 올려 입술을 붙인다).
 */
export function framesToV3Coeffs(frames, { speed = 1, leadMs = 400, tailMs = 400, fps = 30, model = TABLE } = {}) {
  const sch = scheduleSegments(frames, speed, leadMs)
  const segs = sch.segs.filter((s) => s[2] > s[1])
  if (!segs.length) return []
  const A = anchors(padSegments(segs), model)
  const at = A.map((x) => x[0])
  const cols = V3_CHANNELS.map((_, j) => A.map((x) => x[1][j]))
  const sealCol = A.map((x) => x[2])
  const n = Math.ceil((sch.end + tailMs / 1000) * fps)
  const mu = model.mu
  const gain = CH_GROUP.map((g) => (model.gain && model.gain[g]) ?? 1)
  const out = new Array(n)
  for (let k = 0; k < n; k++) {
    const t = k / fps
    const o = {}
    for (let j = 0; j < V3_CHANNELS.length; j++) {
      let y = interp(at, cols[j], t)
      y = mu[j] + (y - mu[j]) * gain[j]
      y = y < 0 ? 0 : y > 1 ? 1 : y
      const c = V3_CHANNELS[j]
      if (PAIR_OUT[c]) { o[`${PAIR_OUT[c]}Left`] = y; o[`${PAIR_OUT[c]}Right`] = y } else o[c] = y
    }
    if (model.seal) {
      const s = interp(at, sealCol, t)
      if (s > 0) o._seal = Math.min(1, s * model.seal)
    }
    out[k] = o
  }
  return out
}

/** 가상 화자 배율(talkers.js의 amp·width·protrusion)을 표 평균 μ에서의 차이에 곱한다. 기본 얼굴은 그대로. (확인 렌더는 기본 얼굴만 쟀다) */
export function scaleV3ForTalker(coeffs, talker, model = TABLE) {
  if (!talker || (talker.amp === 1 && talker.width === 1 && talker.protrusion === 1)) return coeffs
  const mu = Object.fromEntries(V3_CHANNELS.map((c, j) => [c, model.mu[j]]))
  const fac = { open: talker.amp ?? 1, width: talker.width ?? 1, round: talker.protrusion ?? 1, close: 1 }
  const keyOf = {}
  V3_CHANNELS.forEach((c, j) => {
    const keys = PAIR_OUT[c] ? [`${PAIR_OUT[c]}Left`, `${PAIR_OUT[c]}Right`] : [c]
    for (const k of keys) keyOf[k] = [mu[c], fac[CH_GROUP[j]]]
  })
  return coeffs.map((o) => {
    const r = { ...o }
    for (const [k, [m, f]] of Object.entries(keyOf)) {
      if (r[k] == null) continue
      const y = m + (r[k] - m) * f
      r[k] = y < 0 ? 0 : y > 1 ? 1 : y
    }
    return r
  })
}
