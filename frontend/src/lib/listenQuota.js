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

export function batchReward(previous, response) {
  return {
    xp: (previous?.xp || 0) + (response?.xp_gained || 0),
    quota: response?.quota || previous?.quota,
    streak: response?.streak_count ?? previous?.streak,
  }
}

export function batchNext({ quota, mastered, stage }) {
  const q = quotaView(quota)
  if (mastered && stage < 5) return { kind: 'stage', stage: stage + 1, label: `${stage + 2}단계 보러 가기` }
  if (q.met) return { kind: 'exit', label: '학습 화면으로' }
  return { kind: 'more', label: `다음 묶음 듣기 (${q.filled + 1}/${q.total})` }
}
