/**
 * 예정 복습 수와 진입 경로(복습 탭·오른쪽 패널·과제 탭이 같은 정의를 쓴다).
 * GET /api/review/due: count·items = 독화(입모양·단어·문장, 문장은 하루 5개까지) 예정, speak_count·speak = 말하기 예정(말하기에서 틀린 문항).
 * 독화 예정은 간격 반복 세션(/review/scheduled), 말하기 예정은 말하기 복습(/review/speaking)에서 푼다.
 */
export function dueCounts(res) {
  const read = res?.count ?? res?.items?.length ?? 0
  const speak = res?.speak_count ?? res?.speak?.length ?? 0
  return { read, speak, total: read + speak }
}

/** 예정 복습이 남아 있으면 그 세션 경로(독화 먼저), 없으면 fallback. */
export function dueStartPath(counts, fallback) {
  if (counts?.read > 0) return '/review/scheduled'
  if (counts?.speak > 0) return '/review/speaking'
  return fallback
}

/** '오답' 수 = 틀린 문장 + 독화 예정 + 말하기 예정(복습 탭 '복습할 오답'과 패널 '오답'이 같게). */
export function mistakeCount(wrong, counts) {
  return (wrong || 0) + (counts?.read || 0) + (counts?.speak || 0)
}

/** 과제 보상 토스트 문구. claimed = POST /api/tasks/claim의 claimed. 받은 것이 없으면 ''. */
export function rewardMessage(claimed) {
  const list = claimed || []
  if (!list.length) return ''
  const xp = list.reduce((s, c) => s + (c.xp || 0), 0)
  return list.length === 1 ? `'${list[0].label}' 완료 +${xp} XP` : `과제 ${list.length}개 완료 +${xp} XP`
}
