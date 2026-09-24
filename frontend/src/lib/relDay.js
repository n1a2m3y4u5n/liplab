/**
 * 목록의 상대 날짜(복습 탭 189:35 '3일 전 · 2회 틀렸어요'). 오늘 · 어제 · N일 전(6일까지) · N주 전.
 * 서버 시각은 UTC ISO('2026-09-24T08:00:00Z')로 오므로 현지 날짜로 바꿔 달력 날짜 차이로 센다
 * (밤 11시에 한 것은 다음 날 아침에 '어제'). 'YYYY-MM-DD'만 오면 그 현지 날짜로 본다. 읽을 수 없으면 ''.
 */
export function relDay(value, now = new Date()) {
  if (!value) return ''
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  const t = m ? new Date(+m[1], +m[2] - 1, +m[3]) : new Date(value)
  if (Number.isNaN(t.getTime())) return ''
  const day = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate())
  const diff = Math.round((day(now) - day(t)) / 86400000)
  if (diff <= 0) return '오늘'
  if (diff === 1) return '어제'
  if (diff < 7) return `${diff}일 전`
  return `${Math.floor(diff / 7)}주 전`
}
