import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import useTrackLessons from './useTrackLessons'
import { isLockedStatus, lockHint } from './trackProgress'

const STATUS_BADGE = {
  mastered: { label: '숙달', cls: 'bg-good-tint text-good-dark' },
  in_progress: { label: '진행 중', cls: 'bg-bookmark-tint text-bookmark-dark' },
  unlocked: { label: '시작 가능', cls: 'bg-pastel-sky text-stat-level' },
  available: { label: '연습', cls: 'bg-surface-sunken text-ink-muted' },
  locked: { label: '잠김', cls: 'bg-surface-sunken text-ink-caption' },
  coming_soon: { label: '준비 중', cls: 'bg-surface-sunken text-ink-caption' },
}

/**
 * LessonList — 트랙의 레슨 목록(리디자인 스펙 2.3). 커리큘럼 단계는 잠금 상태를 표시하고,
 * 단계 밖 활동(practice)은 '자유 연습'으로 잠금 없이 보여준다.
 * 잠금 표시·안내만 한다 — 실제 진입 차단은 라우트의 StageGate가 계속 맡는다.
 */
export default function LessonList({ track: trackId }) {
  const navigate = useNavigate()
  const { track, loading, failed, lessons, practice } = useTrackLessons(trackId)
  const [notice, setNotice] = useState('')

  useEffect(() => {
    if (!notice) return undefined
    const timer = window.setTimeout(() => setNotice(''), 5000)
    return () => window.clearTimeout(timer)
  }, [notice])

  if (!track) return <p className="p-10 text-center text-sm text-ink-muted">찾을 수 없는 학습이에요.</p>

  const open = (lesson) => {
    if (isLockedStatus(lesson.status)) { setNotice(lockHint(lessons, lesson)); return }
    navigate(lesson.to)
  }

  return (
    <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      <Link to={track.basePath} className="text-sm font-bold text-ink-muted hover:text-ink">← {track.label} 트랙</Link>
      <h1 className="mt-2 text-2xl font-black text-ink">{track.label} 레슨</h1>

      {failed && <p className="mt-2 text-xs text-ink-muted">진행도를 가져오지 못해 잠금 표시 없이 보여드려요.</p>}
      {notice && (
        <p role="status" aria-live="polite" className="mt-3 rounded-lg bg-warn-tint px-3 py-2 text-sm font-medium text-warn-text">
          🔒 {notice}
        </p>
      )}

      <section className="mt-5" aria-labelledby="lesson-list-curriculum">
        <h2 id="lesson-list-curriculum" className="text-sm font-black text-ink">커리큘럼</h2>
        <ol className="mt-2 space-y-2">
          {lessons.map((lesson) => {
            const locked = isLockedStatus(lesson.status)
            const badge = STATUS_BADGE[lesson.status]
            return (
              <li key={lesson.id}>
                <button
                  type="button"
                  onClick={() => open(lesson)}
                  aria-disabled={locked || undefined}
                  className={`flex w-full items-center gap-3 rounded-xl border border-line bg-white p-3 text-left hover:border-ink-faint ${locked ? 'opacity-60' : ''}`}
                >
                  <span aria-hidden="true" className="text-xl">{lesson.icon}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-bold text-ink">{lesson.stage}단계 · {lesson.title}</span>
                    <span className="block text-xs text-ink-muted">{lesson.desc}</span>
                  </span>
                  {loading ? (
                    <span className="text-xs text-ink-inverse-muted">…</span>
                  ) : badge && (
                    <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-bold ${badge.cls}`}>
                      {badge.label}
                      {lesson.attempts > 0 && lesson.masteryScore != null && ` · ${Math.round(lesson.masteryScore)}%`}
                    </span>
                  )}
                </button>
              </li>
            )
          })}
        </ol>
      </section>

      {practice.length > 0 && (
        <section className="mt-6" aria-labelledby="lesson-list-practice">
          <h2 id="lesson-list-practice" className="text-sm font-black text-ink">자유 연습·복습</h2>
          <ul className="mt-2 grid gap-2 sm:grid-cols-2">
            {practice.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => navigate(item.to)}
                  className="flex w-full items-center gap-3 rounded-xl border border-line bg-white p-3 text-left hover:border-ink-faint"
                >
                  <span aria-hidden="true" className="text-xl">{item.icon}</span>
                  <span className="min-w-0">
                    <span className="block text-sm font-bold text-ink">{item.title}</span>
                    <span className="block text-xs text-ink-muted">{item.desc}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  )
}
