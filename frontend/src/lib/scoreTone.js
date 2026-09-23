/**
 * 점수 색 (핸드오프 §3.2) — 한 곳에서 판정하고 토큰으로만 칠한다.
 *   음소별 점수(kind='phone'):   70 이상 초록 · 45~69 주황 · 45 미만 빨강
 *   정답률(kind='accuracy'):     85 이상 초록 · 65~84 주황 · 65 미만 빨강
 * 반환값의 클래스는 tailwind.config.js의 good/warn/bad 토큰, color는 index.css의 CSS 변수다.
 * (Figma: 음소 칩 182:92 · 178:24, 큰 점수 178:22 / 186:38, 하단 바 94:133 / 94:175)
 */
export const SCORE_CUTS = { phone: [70, 45], accuracy: [85, 65] }

/** 'good' | 'warn' | 'bad' — 값이 없으면 null. value는 0~100. */
export function scoreLevel(value, kind = 'phone') {
  if (value == null || Number.isNaN(Number(value))) return null
  const [hi, lo] = SCORE_CUTS[kind] || SCORE_CUTS.phone
  const v = Number(value)
  return v >= hi ? 'good' : v >= lo ? 'warn' : 'bad'
}

// text  = 큰 점수 숫자·강조 글자,  chip = 음소 칩(테두리+연한 바탕+진한 글자),
// bar   = 정답/오답 하단 바 바탕,  color = 인라인 style·SVG용 CSS 변수
const TONES = {
  good: { text: 'text-good', chip: 'border-good bg-good-tint text-good-text', bar: 'border-good/35 bg-good-tint text-good-text', color: 'var(--good)' },
  warn: { text: 'text-warn-strong', chip: 'border-warn bg-warn-tint text-warn-text', bar: 'border-warn/35 bg-warn-tint text-warn-text', color: 'var(--warn-strong)' },
  bad: { text: 'text-bad', chip: 'border-bad bg-bad-tint text-bad-text', bar: 'border-bad/35 bg-bad-tint text-bad-text', color: 'var(--bad)' },
}
const NEUTRAL = { text: 'text-ink-faint', chip: 'border-line bg-surface-muted text-ink-muted', bar: 'border-line bg-white text-ink-muted', color: 'var(--ink-faint)' }

/** 점수 → { level, text, chip, bar, color }. 값이 없으면 level null + 중립 회색. */
export function scoreTone(value, kind = 'phone') {
  const level = scoreLevel(value, kind)
  return { level, ...(level ? TONES[level] : NEUTRAL) }
}
