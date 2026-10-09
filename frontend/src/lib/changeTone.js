/**
 * 한 사람의 전후 차이(사전·사후 정답률, 초기 대비 최근, 재검사) 색 — 서버가 준 Newcombe 95% 구간이 0을 벗어났을 때(clear)만
 * 좋아짐(초록)·나빠짐(빨강)으로 칠하고, 아니면 중립 회색으로 둔다(docs/eval-metrics.md 6절). 예전에는 부호만 보고 칠해
 * 학습 효과가 없어도 사전·사후 비교의 35~46%가 빨강이었다. 구간 정보가 없는 옛 응답도 중립이다.
 */
export const CHANGE_NOISE_NOTE = '문제가 적어 한 사람의 차이는 잡음이 커요. 95% 구간이 0을 벗어날 때만 색으로 표시해요.'

const GOOD = 'bg-good-tint text-good-text'
const BAD = 'bg-bad-tint text-bad-text'
const NEUTRAL = 'bg-fill text-ink-muted'

/** clear(구간이 0을 벗어남)이고 차이가 있으면 좋아짐·나빠짐 클래스, 그 밖은 중립. */
export function changeTone(clear, delta) {
  if (clear !== true || delta == null || Number.isNaN(Number(delta)) || Number(delta) === 0) return NEUTRAL
  return Number(delta) > 0 ? GOOD : BAD
}

const pp = (x) => { const r = Math.round(x); return `${r > 0 ? '+' : r < 0 ? '−' : ''}${Math.abs(r)}` }

/** 95% 구간 문구. ci는 [lo, hi], scale은 %p로 바꿀 배수(정답률 0~1이면 100, 이미 %p면 1). 구간이 없으면 빈 문자열. */
export function ciText(ci, scale = 100) {
  if (!Array.isArray(ci) || ci.length !== 2 || ci.some((v) => v == null)) return ''
  return `95% 구간 ${pp(ci[0] * scale)}~${pp(ci[1] * scale)}%p`
}
