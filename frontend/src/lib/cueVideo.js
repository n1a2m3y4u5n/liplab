/**
 * 실제 영상 위 기호(J-9) 보조 함수. 강제정렬로 얻은 음절 시각에 J 기호를 붙인 묶음(pack.json)을 읽고,
 * 재생 시각마다 어느 음절의 기호를 입 옆에 띄울지 정한다. DOM·React 의존이 없어 node --test로 확인한다.
 *
 * 묶음은 liplab-lab/tools/cue_video.py pack이 만든다. 음절마다 t0(정렬 토큰 시작), cues(J 기호),
 * 입 위치 mouth [[t, cx, cy, w]](정규화 영상 좌표), K 비음 확률 nasal [[t, p]]가 들어 있다.
 */

export const PACK_KIND = 'liplab-cue-video-pack'
export const LEAD_S = 0.05   // 정렬 토큰보다 조금 먼저 띄운다(자음 폐쇄가 토큰 스파이크보다 앞선다)
export const HOLD_S = 0.35   // 다음 음절이 늦게 오면 이만큼만 보여 준다(쉼에서 기호가 남지 않게)

/** pack.json 검사. 잘못되면 Error(한국어 문구). 영상 파일 이름 목록도 돌려준다. */
export function parsePack(json) {
  if (!json || json.kind !== PACK_KIND || !Array.isArray(json.clips)) {
    throw new Error('LIPLAB 기호 영상 묶음(pack.json)이 아니에요.')
  }
  const clips = json.clips.filter((c) => c && c.video && Array.isArray(c.syllables) && c.syllables.length)
  if (!clips.length) throw new Error('묶음에 재생할 클립이 없어요.')
  return { ...json, clips }
}

/** 음절마다 기호를 보여 줄 구간 [start, end). 시각 순서가 어긋난 음절은 뒤 음절 시작에서 끊는다. */
export function syllableWindows(syllables, lead = LEAD_S, hold = HOLD_S) {
  const out = []
  for (let i = 0; i < syllables.length; i++) {
    const s = syllables[i]
    const start = Math.max(0, s.t0 - lead)
    const next = syllables[i + 1]
    let end = s.t0 + hold
    if (next && next.t0 - lead < end) end = next.t0 - lead
    out.push({ start, end: Math.max(start, end) })
  }
  return out
}

/** 시각 t에 보이는 음절 번호, 없으면 -1. windows는 syllableWindows 결과(시작 시각 오름차순). */
export function activeIndex(windows, t) {
  let lo = 0
  let hi = windows.length - 1
  let found = -1
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    if (windows[mid].start <= t) { found = mid; lo = mid + 1 } else hi = mid - 1
  }
  if (found < 0) return -1
  return t < windows[found].end ? found : -1
}

/** [[t, …], …]에서 t에 가장 가까운 행(시각 오름차순). 비어 있으면 null. */
export function nearestSample(series, t) {
  if (!series?.length) return null
  let lo = 0
  let hi = series.length - 1
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    if (series[mid][0] <= t) lo = mid; else hi = mid
  }
  return Math.abs(series[hi][0] - t) < Math.abs(series[lo][0] - t) ? series[hi] : series[lo]
}

/** 입 옆 기호 위치(정규화 좌표 0~1). 입 너비의 0.6배만큼 화자 기준 왼쪽(화면 오른쪽)으로 비켜 입을 가리지 않는다. */
export function cueAnchor(mouthRow) {
  if (!mouthRow) return { x: 0.62, y: 0.6 }
  const [, cx, cy, w] = mouthRow
  return { x: Math.min(0.94, cx + 0.6 * (w || 0.08)), y: cy }
}

/** K 비음 곡선을 SVG 폴리라인 점 문자열로. 가로는 [0, duration] → [0, width], 세로는 확률 0~1 → [height, 0]. */
export function nasalPolyline(nasal, duration, width, height) {
  if (!nasal?.length || !(duration > 0)) return ''
  return nasal
    .map(([t, p]) => `${((t / duration) * width).toFixed(1)},${((1 - p) * height).toFixed(1)}`)
    .join(' ')
}
