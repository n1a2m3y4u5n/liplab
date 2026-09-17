// 학습 트랙 공통 계산(순수 함수) — 단계 API 응답을 레슨 정의(config/tracks.js)에 합치고
// 잠금 · 이어하기 · 진행도 요약 · 다음 추천을 계산한다. React·API 의존이 없어 node --test로 검증한다.

// StageGate와 같은 규칙: locked·coming_soon만 잠김. 상태를 모르면(조회 실패) 막지 않는다(가용성 우선).
export const isLockedStatus = (status) => status === 'locked' || status === 'coming_soon'

// 레슨 정의 + 단계 API의 stages → 레슨별 status·masteryScore·attempts.
// stages가 null이면(불러오는 중·실패) status는 null로 둔다.
export function mergeLessonStatus(lessons, stages) {
  const byStage = new Map((stages || []).map((s) => [s.stage, s]))
  return lessons.map((lesson) => {
    const s = byStage.get(lesson.stage)
    return {
      ...lesson,
      status: s?.status ?? null,
      masteryScore: s?.mastery_score ?? null,
      attempts: s?.attempts ?? 0,
    }
  })
}

// 이어하기 대상: 진행 중 → 시작 가능 → (더 할 게 없으면) 마지막으로 숙달한 레슨 → 첫 레슨.
// 상태를 모르면(전부 null) 첫 레슨.
export function pickContinueLesson(lessons) {
  if (!lessons.length) return null
  return lessons.find((l) => l.status === 'in_progress')
    || lessons.find((l) => l.status === 'unlocked' || l.status === 'available')
    || [...lessons].reverse().find((l) => l.status === 'mastered')
    || lessons[0]
}

// 진행도 요약 — 숙달한 단계 수 / 전체 단계 수.
export function summarizeProgress(lessons) {
  const total = lessons.length
  const mastered = lessons.filter((l) => l.status === 'mastered').length
  return { total, mastered, percent: total ? Math.round((mastered / total) * 100) : 0 }
}

// 다음 추천: 현재 레슨 다음 순서 중 잠기지 않은 첫 레슨. 없으면 이어하기 대상(현재 레슨이 아니면).
export function pickNextLesson(lessons, currentId) {
  const index = lessons.findIndex((l) => l.id === currentId)
  const after = index >= 0 ? lessons.slice(index + 1) : []
  const next = after.find((l) => !isLockedStatus(l.status))
  if (next) return next
  const fallback = pickContinueLesson(lessons)
  return fallback && fallback.id !== currentId ? fallback : null
}

// 잠긴 레슨을 눌렀을 때 안내 — 직전 단계 번호·제목을 알려준다.
export function lockHint(lessons, lesson) {
  const prev = lessons.find((l) => l.stage === lesson.stage - 1)
  return prev
    ? `직전 단계(${prev.stage}단계 · ${prev.title})를 먼저 완료해주세요.`
    : '직전 단계를 먼저 완료해주세요.'
}
