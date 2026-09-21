import { Link, useNavigate } from 'react-router-dom'
import useTrackLessons from './useTrackLessons'
import { pickContinueLesson, summarizeProgress } from './trackProgress'

/**
 * TrackHub — 트랙 허브(리디자인 스펙 2.3). 트랙 소개 + 진행도 요약 + "이어하기".
 * props.track: 'lipreading' | 'speaking'. 레슨 URL 방식·단계 API 차이는 useTrackLessons가 흡수하므로
 * 이어하기는 레슨의 완성된 링크(to)로 이동만 한다. 비주얼은 Figma 확정 전까지 최소 스타일.
 */
export default function TrackHub({ track: trackId }) {
  const navigate = useNavigate()
  const { track, loading, failed, lessons } = useTrackLessons(trackId)
  if (!track) return <p className="p-10 text-center text-sm text-slate-500">알 수 없는 학습 트랙이에요.</p>

  const summary = summarizeProgress(lessons)
  const next = loading ? null : pickContinueLesson(lessons)

  return (
    <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      <section className="rounded-2xl border border-slate-200 bg-white p-6">
        <p className="text-xs font-black tracking-[0.14em] text-slate-500">{track.label} 트랙</p>
        <h1 className="mt-1 text-2xl font-black text-slate-900">
          <span aria-hidden="true">{track.icon}</span> {track.hubTitle}
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-slate-600">{track.description}</p>

        <div className="mt-6">
          <div className="flex items-center justify-between text-xs font-bold text-slate-500">
            <span>진행도</span>
            <span>
              {loading ? '불러오는 중…'
                : failed ? '진행도를 불러오지 못했어요'
                  : `${summary.mastered} / ${summary.total} 단계 완료`}
            </span>
          </div>
          <div
            className="mt-1.5 h-2 overflow-hidden rounded-full bg-slate-100"
            role="progressbar"
            aria-label={`${track.label} 진행도`}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={summary.percent}
          >
            <div className="h-full rounded-full bg-slate-900" style={{ width: `${summary.percent}%` }} />
          </div>
        </div>

        <div className="mt-6 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={!next}
            onClick={() => navigate(next.to)}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-bold text-white disabled:cursor-wait disabled:bg-slate-300"
          >
            {next ? `이어하기 · ${next.title}` : '불러오는 중…'}
          </button>
          <Link
            to={`${track.basePath}/lessons`}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-bold text-slate-700 hover:bg-slate-50"
          >
            레슨 목록 보기
          </Link>
        </div>
      </section>
    </main>
  )
}
