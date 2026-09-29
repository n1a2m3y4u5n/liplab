/**
 * 웹캠 입모양 '익힘 기록'에 남길 점수(축 D → WeakViseme). 순수 함수.
 *
 * 화면의 큰 점수는 최근 약 1초의 최고점이라 발음 정점을 잘 보여 주지만, 기록까지 한 프레임 최고점으로 남기면
 * 검출 잡음 한 번이 합격(60점)을 만든다. 예전에는 세션 전체 한 프레임 최고점을 보냈고, 얼굴을 잡기 전에 누르면 0점이 기록됐다.
 *
 * 기록 점수는 최근 ATTEMPT_MS(5초) 동안 얼굴을 잡은 프레임의 순간 점수 중 상위 k개의 중앙값이다.
 * k는 창 프레임 수의 20%(최소 5개)라, 30 fps에서 5초 창이면 약 0.5초 동안 그 점수 이상을 만들어야 한다.
 * 창이 짧아도 최소 3프레임(0.1초)은 그 점수를 넘어야 해서 한두 프레임 튐은 기록되지 않는다.
 * 얼굴을 잡은 프레임이 MIN_FACE_FRAMES(15, 30 fps에서 약 0.5초) 미만이면 null을 돌려 기록하지 않는다.
 */
export const ATTEMPT_MS = 5000
export const MIN_FACE_FRAMES = 15
const TOP_FRAC = 0.2
const TOP_MIN = 5

/** ATTEMPT_MS보다 오래된 표본을 버린다. 얼굴을 놓친 동안에도 불러 옛 표본이 기록되지 않게 한다. */
export function pruneAttempt(win, now) {
  while (win.length && now - win[0].t > ATTEMPT_MS) win.shift()
  return win
}

/** 얼굴을 잡은 프레임의 순간 점수를 창에 넣고 오래된 표본을 버린다. */
export function pushAttemptSample(win, t, score) {
  win.push({ t, s: score })
  return pruneAttempt(win, t)
}

/** 창의 기록 점수(0~100 정수). 표본이 모자라면 null. */
export function attemptScore(win) {
  if (!win || win.length < MIN_FACE_FRAMES) return null
  const s = win.map((w) => w.s).filter((x) => Number.isFinite(x)).sort((a, b) => b - a)
  if (s.length < MIN_FACE_FRAMES) return null
  const k = Math.min(s.length, Math.max(TOP_MIN, Math.ceil(s.length * TOP_FRAC)))
  const top = s.slice(0, k)
  const m = k % 2 ? top[(k - 1) / 2] : (top[k / 2 - 1] + top[k / 2]) / 2
  return Math.round(Math.max(0, Math.min(100, m)))
}
