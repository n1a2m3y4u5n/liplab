/**
 * 분석 상세(활동·기록)의 날짜별 활동 수. /api/calendar/activities({ 'YYYY-MM-DD': [{kind, n, ...}] }, 브라우저 현지 날짜)의
 * 행별 n을 날마다 더한다. 예전에는 /api/calendar(문장 연습만, UTC 날짜)를 써서 입모양·단어·문맥·말하기만 한 학습자는
 * 활동 0으로 나왔고, 한국 오전 9시 전 학습은 전날 칸에 들어갔다. 분석 탭 활동 캘린더(AnalysisTab dayCounts)와 같은 셈이다.
 */
export function activityCounts(acts) {
  const out = {}
  for (const [day, rows] of Object.entries(acts || {})) {
    out[day] = (rows || []).reduce((sum, row) => sum + (Number(row?.n) || 0), 0)
  }
  return out
}

/** 현지 날짜 키 'YYYY-MM-DD'(toISOString은 UTC라 새벽 학습이 전날이 된다). */
export const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

/** 오늘로 끝나는 최근 length일(오래된 순)의 { key, count }. 키는 현지 날짜다. */
export function recentDays(counts, length = 90, today = new Date()) {
  return Array.from({ length }, (_, index) => {
    const date = new Date(today.getFullYear(), today.getMonth(), today.getDate() - (length - 1 - index))
    const key = ymd(date)
    return { key, count: Number(counts?.[key]) || 0 }
  })
}
