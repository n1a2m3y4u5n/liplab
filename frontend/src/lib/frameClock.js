// 입모양 프레임을 넘기는 시계(계획 V20). 예전에는 프레임마다 setTimeout(길이)을 이어 붙여, 시스템이 바쁘면 늦은 만큼이 계속 쌓여
// 문장이 늘어지고 프레임 길이가 고르지 않았다. 이제는 프레임이 '시작했어야 할 시각'(due)을 들고 다니며 다음 프레임의 대기 시간을
// 그 시각 기준으로 정한다. 늦었으면 다음 대기를 줄여 따라잡되, 한 프레임이 원래 길이의 절반보다 짧아지지는 않게 한다
// (입모양을 읽을 시간이 지나치게 줄지 않도록). 늦은 정도는 기록해 두었다가 기기 점검에 쓴다.

export const MIN_FRAME_FRACTION = 0.5

/** 다음 프레임까지의 대기(ms)와 다음 프레임의 due 시각. due가 없으면(처음) now에서 시작한다. */
export function nextDelay({ dueAt, durationMs, speed = 1, now }) {
  const start = Number.isFinite(dueAt) ? dueAt : now
  const len = Math.max(0, Number(durationMs) || 0) / (speed > 0 ? speed : 1)
  const nextDue = start + len
  const delay = Math.max(len * MIN_FRAME_FRACTION, nextDue - now)
  return { delay, nextDue: Math.max(nextDue, now + delay) }
}

// 재생 지연 기록: 프레임이 due보다 얼마나 늦게 시작했는지. 같은 탭 안에서만 모은다(서버 전송 없음).
const stats = { n: 0, sumMs: 0, maxMs: 0, over20: 0, over50: 0 }

export function recordLateness(lateMs) {
  const v = Math.max(0, Number(lateMs) || 0)
  stats.n += 1
  stats.sumMs += v
  if (v > stats.maxMs) stats.maxMs = v
  if (v > 20) stats.over20 += 1
  if (v > 50) stats.over50 += 1
}

// 화면 주사율 추정: 보이는 동안 requestAnimationFrame 간격 30개의 중앙값. 숨은 탭은 브라우저가 늦추므로 보일 때만 잰다.
let screenHzEst = null
export function hzFromIntervals(intervals) {
  const d = (intervals || []).filter((x) => x > 0 && x < 1000).sort((a, b) => a - b)
  if (d.length < 10) return null
  const med = d[Math.floor(d.length / 2)]
  return Math.round(1000 / med)
}
function startScreenHzEstimate() {
  if (typeof window === 'undefined' || typeof requestAnimationFrame !== 'function' || screenHzEst != null) return
  if (typeof document !== 'undefined' && document.visibilityState === 'hidden') {
    document.addEventListener('visibilitychange', startScreenHzEstimate, { once: true })
    return
  }
  const t = []
  const step = (now) => {
    t.push(now)
    if (t.length < 31) requestAnimationFrame(step)
    else screenHzEst = hzFromIntervals(t.slice(1).map((x, i) => x - t[i]))
  }
  requestAnimationFrame(step)
}
startScreenHzEstimate()

/** 지금까지의 요약. 파일럿 기기 점검(V20)과 끊김 진단에 쓴다. */
export function renderTimingSummary() {
  const { n, sumMs, maxMs, over20, over50 } = stats
  return {
    screenHzEst,
    frames: n,
    meanLateMs: n ? Math.round((sumMs / n) * 10) / 10 : 0,
    maxLateMs: Math.round(maxMs),
    over20Rate: n ? Math.round((over20 / n) * 1000) / 1000 : 0,
    over50Rate: n ? Math.round((over50 / n) * 1000) / 1000 : 0,
  }
}

export function resetRenderTiming() {
  Object.assign(stats, { n: 0, sumMs: 0, maxMs: 0, over20: 0, over50: 0 })
}

// 기기 점검·끊김 진단용: 브라우저 콘솔에서 window.__liplabRenderTiming()으로 요약을 본다(값만 읽음, 전송 없음)
if (typeof window !== 'undefined') window.__liplabRenderTiming = renderTimingSummary
