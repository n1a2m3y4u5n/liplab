/**
 * 틀린 문장 복습 세션(ReviewLanding, scenario_id mistake_review_*). 문장마다 원래 난이도를 levels에 담는다.
 * 예전에는 세션 난이도를 1로 고정해, 원래 4·5단계 문장의 복습 답도 난이도 1로 저장됐고 추천 난이도가 1~2단계로 떨어졌다.
 * items는 /api/review-sentences 응답({sentence, situation, difficulty_level, ...}). 문장이 빈 항목은 뺀다.
 */
export function mistakeReviewScenario(items, qTypesFor, now = Date.now()) {
  const picked = (items || []).filter((item) => item?.sentence)
  const sentences = picked.map((item) => item.sentence)
  const levels = picked.map((item) => clampLevel(item.difficulty_level))
  return {
    situation: '틀린 문장 복습',
    level: levels[0] || 1,
    levels,
    sentences,
    qTypes: qTypesFor ? qTypesFor(sentences.length) : undefined,
    scenario_id: `mistake_review_${now}`,
  }
}

/** index번째 문장의 난이도. 문장별 levels가 있으면 그 값, 없으면 세션 level(일반 레슨·북마크). */
export function sentenceLevel(scenario, index) {
  const own = Number(scenario?.levels?.[index])
  if (Number.isFinite(own) && own >= 1) return clampLevel(own)
  return clampLevel(scenario?.level)
}

function clampLevel(value) {
  const n = Math.round(Number(value))
  return Number.isFinite(n) && n >= 1 ? Math.min(n, 5) : 1
}
