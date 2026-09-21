import { Link, useLocation, useNavigate } from 'react-router-dom'
import useStore from '../../../store/useStore'
import useTrackLessons from './useTrackLessons'
import { pickNextLesson } from './trackProgress'

/**
 * LessonComplete — 레슨 완료 요약(리디자인 스펙 2.3). 정답률 · 획득 XP · 연속 학습 · 다음 추천 레슨.
 * 레슨별 결과를 주는 API가 없으므로 결과는 result prop 또는 navigate state({ result })로 받는다
 * (진행 화면이 넘겨주도록 연결하는 건 9.2 4단계). 결과가 없어도 다음 추천·트랙 복귀는 보여준다.
 * 스트릭은 useStore의 user에서만 읽는다(새 API 호출 없음).
 *
 * props
 * - track: 'lipreading' | 'speaking'
 * - lessonId: 방금 끝낸 레슨 id(config/tracks.js)
 * - result: { correct, total, xpGained }
 */
export default function LessonComplete({ track: trackId, lessonId, result: resultProp }) {
  const navigate = useNavigate()
  const location = useLocation()
  const streak = useStore((state) => state.user?.streak_count ?? 0)
  const { track, loading, lessons } = useTrackLessons(trackId)
  if (!track) return <p className="p-10 text-center text-sm text-slate-500">알 수 없는 학습 트랙이에요.</p>

  const result = resultProp ?? location.state?.result ?? null
  const accuracy = result?.total > 0 ? Math.round((result.correct / result.total) * 100) : null
  const current = lessons.find((lesson) => lesson.id === lessonId)
  const next = loading ? null : pickNextLesson(lessons, lessonId)

  const stats = [
    ['정답률', accuracy != null ? `${accuracy}%` : '—', result?.total > 0 ? `${result.correct} / ${result.total}` : ''],
    ['획득 XP', typeof result?.xpGained === 'number' ? `+${result.xpGained}` : '—', ''],
    ['연속 학습', `${streak}일`, ''],
  ]

  return (
    <main className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
      <section className="rounded-2xl border border-slate-200 bg-white p-6 text-center">
        <p className="text-4xl" aria-hidden="true">🎉</p>
        <h1 className="mt-2 text-2xl font-black text-slate-900">레슨 완료!</h1>
        <p className="mt-1 text-sm text-slate-500">{track.label} · {current?.title || '레슨'}</p>

        <dl className="mt-6 grid grid-cols-3 gap-2">
          {stats.map(([label, value, sub]) => (
            <div key={label} className="rounded-xl bg-slate-50 p-3">
              <dt className="text-xs font-bold text-slate-500">{label}</dt>
              <dd className="mt-1 text-xl font-black text-slate-900">{value}</dd>
              {sub && <dd className="text-[11px] text-slate-400">{sub}</dd>}
            </div>
          ))}
        </dl>
        {!result && <p className="mt-3 text-xs text-slate-400">이번 레슨의 결과 정보가 없어요.</p>}

        <div className="mt-6 flex flex-wrap justify-center gap-2">
          {next && (
            <button
              type="button"
              onClick={() => navigate(next.to)}
              className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-bold text-white"
            >
              다음 추천 · {next.title}
            </button>
          )}
          <Link
            to={track.basePath}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-bold text-slate-700 hover:bg-slate-50"
          >
            {track.label} 트랙으로
          </Link>
        </div>
      </section>
    </main>
  )
}
