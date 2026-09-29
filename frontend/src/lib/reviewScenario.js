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

/**
 * 오늘의 복습 문장 문항(/api/review/due의 kind 'sentence')을 /api/progress 제출 본문으로 바꾼다. scenario_id가 srs_review_로
 * 시작해 서버가 3단계 숙달·추천 난이도에는 넣지 않고 복습 간격만 조정한다(main._SENTENCE_REVIEW_PREFIX). 상황·난이도는 서버가
 * 그 문장의 레슨 기록에서 실어 준 값이고, 없으면 '문장 복습'·1로 보낸다. 문장 복습은 입력형이라 answer_mode는 'typed'이고,
 * speed(재생 배속, 빠른 말 1.25 등)가 유효한 값이면 함께 보낸다(progress.speed 기록).
 */
export function sentenceReviewSubmission(item, answer, seconds, sessionId, speed) {
  return {
    scenario_id: String(sessionId || '').startsWith('srs_review_') ? sessionId : `srs_review_${sessionId || Date.now()}`,
    sentence: item?.ref || '',
    user_answer: String(answer || '').trim(),
    time_spent_seconds: Math.max(0, Math.round(Number(seconds) || 0)),
    situation: item?.situation || '문장 복습',
    difficulty_level: clampLevel(item?.difficulty_level),
    answer_mode: 'typed',
    ...(Number.isFinite(speed) && speed > 0 ? { speed } : {}),
  }
}
