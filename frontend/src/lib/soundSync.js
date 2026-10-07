// 소리 조건(C17, docs/sound-condition.md)의 화면 쪽 순수 함수: 입모양 프레임을 소리의 실제 음절 시각에 맞추기, 재생 시각의 프레임 찾기,
// 브라우저가 풀 수 있는 소리 형식 고르기, 레슨 단계 순서(소리 → 소리 없이 한 번 더).
// 음절 시각은 서버(/api/sound)가 합성한 소리를 앱의 D-GOP 정렬기로 강제정렬해 준다. 시각이 없으면(정렬 실패, 음절 수 불일치) 엔진 길이를
// 소리 길이에 비례로 맞춘다.

// 눈에 보이는 입 움직임은 소리보다 조금 먼저 시작한다(입술이 닫혔다 열려야 ㅂ 소리가 난다). 재생 시각보다 이만큼 앞의 프레임을 보인다.
export const VISUAL_LEAD_MS = 40
// 시각이 없을 때 소리 앞뒤에 남은 무음(서버가 합성 뒤 앞뒤 무음을 100ms만 남기고 자른다)
export const EDGE_MS = 100
export const NEUTRAL = Object.freeze({ viseme: 15, duration_ms: 200, transition_ms: 120 })

/**
 * 프레임을 소리 시각으로 다시 깐다. 반환: [{start, end, frame}] (ms, 시작 순).
 *  - syllables: [{i, t0, t1}] (i = 프레임의 text_index). 같은 음절의 프레임들은 엔진 길이 비율대로 [t0, t1]을 나눠 갖는다.
 *    시각이 없는 음절 자리의 프레임(공백·문장부호의 쉼 프레임)은 넣지 않는다. 그 틈은 중립 입모양으로 보인다.
 *  - syllables가 없거나 어떤 음절도 맞지 않으면 전체 엔진 길이를 [EDGE, 길이 − EDGE]에 비례로 맞춘다.
 */
export function retimeFrames(frames, syllables, durationMs) {
  const fs = Array.isArray(frames) ? frames.filter((f) => f && Number.isFinite(f.duration_ms)) : []
  if (!fs.length) return []
  const byIdx = new Map()
  for (const s of Array.isArray(syllables) ? syllables : []) {
    if (Number.isInteger(s?.i) && Number.isFinite(s?.t0) && Number.isFinite(s?.t1) && s.t1 > s.t0) byIdx.set(s.i, s)
  }
  const out = []
  if (byIdx.size) {
    const groups = new Map()
    for (const f of fs) {
      if (!byIdx.has(f.text_index)) continue
      if (!groups.has(f.text_index)) groups.set(f.text_index, [])
      groups.get(f.text_index).push(f)
    }
    if (groups.size) {
      for (const [i, g] of groups) {
        const { t0, t1 } = byIdx.get(i)
        const total = g.reduce((a, f) => a + Math.max(1, f.duration_ms), 0)
        let t = t0
        g.forEach((f, k) => {
          const end = k === g.length - 1 ? t1 : t + (t1 - t0) * Math.max(1, f.duration_ms) / total
          out.push({ start: t, end, frame: f })
          t = end
        })
      }
      return out.sort((a, b) => a.start - b.start)
    }
  }
  const dur = Number(durationMs) || 0
  const total = fs.reduce((a, f) => a + Math.max(1, f.duration_ms), 0)
  const a0 = dur > 4 * EDGE_MS ? EDGE_MS : 0
  const span = Math.max(1, (dur > 4 * EDGE_MS ? dur - 2 * EDGE_MS : dur) || total)
  let t = a0
  for (const f of fs) {
    const len = span * Math.max(1, f.duration_ms) / total
    out.push({ start: t, end: t + len, frame: f })
    t += len
  }
  return out
}

/** 시각 ms에 보일 항목(없으면 null = 중립). 이분 탐색. */
export function frameAt(schedule, ms) {
  let lo = 0
  let hi = (schedule?.length || 0) - 1
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    const s = schedule[mid]
    if (ms < s.start) hi = mid - 1
    else if (ms >= s.end) lo = mid + 1
    else return s
  }
  return null
}

/** 아바타에 넘길 프레임(전환·머무는 시간은 소리 시각의 길이로). 틈이면 중립. */
export function overrideFor(entry) {
  if (!entry) return { ...NEUTRAL }
  const d = Math.max(1, entry.end - entry.start)
  const tr = Number.isFinite(entry.frame.transition_ms) ? Math.min(entry.frame.transition_ms, d * 0.5) : Math.min(40, d * 0.5)
  return { viseme: entry.frame.viseme ?? 15, transition_ms: tr, duration_ms: d, text_index: entry.frame.text_index,
    coart_v: entry.frame.coart_v }
}

/** 여러 조각(AX 짝처럼 소리 두 개를 쉼을 두고)을 한 줄로 잇는다. 반환 {schedule, segments: [{offset, durationMs}], total}. */
export function joinSegments(parts, gapMs = 600) {
  const schedule = []
  const segments = []
  let off = 0
  parts.forEach((p, k) => {
    if (k > 0) off += gapMs
    for (const s of p.schedule) schedule.push({ start: s.start + off, end: s.end + off, frame: s.frame })
    segments.push({ offset: off, durationMs: p.durationMs })
    off += p.durationMs
  })
  return { schedule, segments, total: off }
}

/** 서버가 준 소리 형식 가운데 브라우저가 재생할 수 있는 첫 주소. canPlay(type) → '' | 'maybe' | 'probably'. 없으면 null. */
export function pickSource(sources, canPlay) {
  for (const s of Array.isArray(sources) ? sources : []) {
    try {
      if (s?.url && canPlay(s.type)) return s.url
    } catch { /* 모르는 형식 */ }
  }
  return null
}

/** 다시 보기 순서: 'sound'(소리와 함께) → 'silent'(소리 없이 한 번 더) → 'idle'. 소리를 못 받으면 'unavailable'. */
export function nextPhase(phase) {
  return phase === 'sound' ? 'silent' : 'idle'
}

/** 소리 조건 권하기(계획 C6): 보청기·인공와우를 답한 학습자에게만 권한다. 켜는 것은 학습자가 한다(기본 끔). */
export function shouldSuggest({ enabled, recommended, dismissed }) {
  return !enabled && !!recommended && !dismissed
}
