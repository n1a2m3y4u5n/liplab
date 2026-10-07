/**
 * 소리 듣기 결과 화면(pages/ListeningReport.jsx)의 순수 계산. 서버 GET /api/listen/summary 응답을 화면용 줄로 바꾼다.
 */

// 두 검사 차이의 최소 감지 변화(MDC95). 문장 단위(낱말 절반 이상) 1-up-1-down 20문장의 개인 내 SD 약 1.1 dB(Jansen 2012) × 2.77 ≈ 3 dB.
// 검사 절차를 낱말 점수 규칙으로 바꾸면 이 값도 바꾼다(docs/listen-advance-evidence-2026-10.md Q9). 시뮬레이션 2차도 3.0.
export const MDC_DB = 3.0

/** 검사 회차를 주 검사(잡담 잡음)와 그 밖(훈련에 안 쓴 잡음)으로 나눈다. 시간순은 그대로. */
export function splitTests(tests) {
  const all = (tests || []).filter((t) => t && t.srt_db != null)
  return {
    main: all.filter((t) => (t.noise || 'babble') === 'babble'),
    other: all.filter((t) => t.noise && t.noise !== 'babble'),
  }
}

/**
 * 첫 검사와 마지막 검사의 차이. 낮아질수록 좋다. 두 번 미만이면 null.
 * 반환: {change(dB, 양수 = 낮아짐), text, withinError}
 */
export function srtChange(main, mdc = MDC_DB) {
  if (!main || main.length < 2) return null
  const change = Math.round((main[0].srt_db - main[main.length - 1].srt_db) * 10) / 10
  const text = change > 0 ? `처음보다 ${change} dB 낮아졌어요` : change < 0 ? `처음보다 ${-change} dB 높아졌어요` : '처음과 같아요'
  return { change, text, withinError: change !== 0 && Math.abs(change) < mdc }
}

/**
 * 표에 보일 줄. 많으면 최근 limit개만 보이고(가장 최근이 위), 처음 검사는 기준이라 늘 남긴다.
 * 반환: {rows: [{...t, order(1부터), first}], hidden(숨긴 수)}
 */
export function testRows(main, limit = 5, showAll = false) {
  const numbered = (main || []).map((t, i) => ({ ...t, order: i + 1, first: i === 0 }))
  const newest = [...numbered].reverse()
  if (showAll || newest.length <= limit) return { rows: newest, hidden: 0 }
  const head = newest.slice(0, limit - 1)
  return { rows: [...head, numbered[0]], hidden: newest.length - head.length - 1 }
}

/** 소리 구별 종류별 정답률 막대. 적게 푼 종류(minN 미만)는 few로 표시한다. 정답률 낮은 순. */
export function axKindRows(kinds, minN = 5) {
  return (kinds || []).filter((k) => k && k.n > 0).map((k) => ({
    kind: k.kind, label: k.label, n: k.n, pct: Math.round((k.correct / k.n) * 100), few: k.n < minN,
  })).sort((a, b) => a.pct - b.pct || b.n - a.n)
}

/** 헷갈린 소리 짝 표(많은 순, limit줄). slot → 자리 이름. */
export function confusionRows(confusions, limit = 5) {
  const where = { onset: '첫소리', vowel: '모음', coda: '받침' }
  const show = (x) => (x === '-' ? '없음' : x)
  return (confusions || []).slice(0, limit).map((c) => ({
    where: where[c.slot] || c.slot, target: show(c.target), heard: show(c.heard), n: c.n,
  }))
}

/**
 * 최근 7일 막대. 반환: {bars: [{date, label, n, pct, today}], total, activeDays}.
 * pct는 가장 많이 한 날 대비 높이(0~100). today는 마지막 날.
 */
export function dayBars(days) {
  const list = days || []
  const max = Math.max(1, ...list.map((d) => d.n || 0))
  const bars = list.map((d, i) => ({
    date: d.date, n: d.n || 0, pct: Math.round(((d.n || 0) / max) * 100), today: i === list.length - 1,
    label: i === list.length - 1 ? '오늘' : String(d.date || '').slice(5).replace('-', '/'),
  }))
  return { bars, total: bars.reduce((a, b) => a + b.n, 0), activeDays: bars.filter((b) => b.n > 0).length }
}
