// 화면은 서버의 완료 묶음만 사용한다. 부분 답·연습 답을 묶음으로 올려 세지 않는다.
export function quotaView(quota) {
  const total = Math.max(1, Number(quota?.quota_n) || 2)
  const done = Math.max(0, Number(quota?.today_n) || 0)
  return { total, done, filled: Math.min(total, done), met: done >= total, batch: Number(quota?.batch_n) || 8 }
}

export function pathDays(quota, today) {
  return (quota?.days || []).filter((d) => d.date < today && d.met).slice(-2)
}

export function kstDate(now = new Date()) {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit' }).format(now)
}

export function recommendedStage(data) {
  if (Number.isInteger(data?.recommended)) return data.recommended
  return (data?.stages || []).find((s) => s.status !== 'locked' && s.status !== 'mastered')?.stage ?? 0
}
