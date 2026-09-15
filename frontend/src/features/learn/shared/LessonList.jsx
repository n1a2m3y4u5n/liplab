import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import useTrackLessons from './useTrackLessons'
import { isLockedStatus, lockHint } from './trackProgress'

const STATUS_BADGE = {
  mastered: { label: '완료', cls: 'bg-green-100 text-green-700' },
  in_progress: { label: '진행 중', cls: 'bg-blue-100 text-blue-700' },
  unlocked: { label: '시작 가능', cls: 'bg-sky-100 text-sky-700' },
  available: { label: '연습', cls: 'bg-gray-100 text-gray-600' },
  locked: { label: '잠김', cls: 'bg-gray-100 text-gray-400' },
  coming_soon: { label: '준비 중', cls: 'bg-gray-100 text-gray-400' },
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

  if (!track) return <p className="p-10 text-center text-sm text-slate-500">알 수 없는 학습 트랙이에요.</p>

  const open = (lesson) => {
    if (isLockedStatus(lesson.status)) { setNotice(lockHint(lessons, lesson)); return }
    navigate(lesson.to)
  }

  return (
    <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      <Link to={track.basePath} className="text-sm font-bold text-slate-500 hover:text-slate-800">← {track.label} 트랙</Link>
      <h1 className="mt-2 text-2xl font-black text-slate-900">{track.label} 레슨</h1>

      {failed && <p className="mt-2 text-xs text-slate-500">진행도를 불러오지 못해 잠금 표시 없이 보여드려요.</p>}
      {notice && (
        <p role="status" aria-live="polite" className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-sm font-medium text-amber-900">
          🔒 {notice}
        </p>
      )}

      <section className="mt-5" aria-labelledby="lesson-list-curriculum">
        <h2 id="lesson-list-curriculum" className="text-sm font-black text-slate-700">커리큘럼</h2>
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
                  className={`flex w-full items-center gap-3 rounded-xl border border-slate-200 bg-white p-3 text-left hover:border-slate-400 ${locked ? 'opacity-60' : ''}`}
                >
                  <span aria-hidden="true" className="text-xl">{lesson.icon}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-bold text-slate-900">{lesson.stage}단계 · {lesson.title}</span>
                    <span className="block text-xs text-slate-500">{lesson.desc}</span>
                  </span>
                  {loading ? (
                    <span className="text-xs text-slate-300">…</span>
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
          <h2 id="lesson-list-practice" className="text-sm font-black text-slate-700">자유 연습·복습</h2>
          <ul className="mt-2 grid gap-2 sm:grid-cols-2">
            {practice.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => navigate(item.to)}
                  className="flex w-full items-center gap-3 rounded-xl border border-slate-200 bg-white p-3 text-left hover:border-slate-400"
                >
                  <span aria-hidden="true" className="text-xl">{item.icon}</span>
                  <span className="min-w-0">
                    <span className="block text-sm font-bold text-slate-900">{item.title}</span>
                    <span className="block text-xs text-slate-500">{item.desc}</span>
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
