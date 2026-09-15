import { useNavigate } from 'react-router-dom'
import LearnHeader from '../../../components/LearnHeader'
import { getTrack } from '../../../config/tracks'

/**
 * LessonRunner — 레슨 진행 공통 뼈대(리디자인 스펙 2.3·6.2). 헤더 · 진행바 · 본문 슬롯 · 하단 슬롯.
 * 트랙·레슨별 실제 연습 화면은 children(본문 슬롯)으로, 답변 버튼 등은 footer 슬롯으로 주입한다.
 * 어떤 연습 컴포넌트를 어떤 레슨에 끼울지(스펙의 TRACK_INTERACTIONS 매핑)는 다음 단계(9.2 4단계)에서 정한다.
 *
 * props
 * - track: 'lipreading' | 'speaking'
 * - title, description: 헤더 문구(없으면 트랙 이름·허브 제목)
 * - progress: { current, total } — 있으면 진행바 표시
 * - onExit: 나가기 동작(없으면 트랙 허브로)
 */
export default function LessonRunner({ track: trackId, title, description, progress, onExit, footer, children }) {
  const navigate = useNavigate()
  const track = getTrack(trackId)
  if (!track) return <p className="p-10 text-center text-sm text-slate-500">알 수 없는 학습 트랙이에요.</p>

  const percent = progress?.total > 0
    ? Math.min(100, Math.max(0, Math.round((progress.current / progress.total) * 100)))
    : null

  return (
    <div className="lesson-runner min-h-screen bg-slate-50">
      <LearnHeader
        accent={track.accent}
        title={title || `${track.label} 레슨`}
        description={description || track.hubTitle}
        onExit={onExit || (() => navigate(track.basePath))}
      />
      <main className="mx-auto max-w-5xl px-4 py-6 sm:px-6">
        {percent != null && (
          <div className="mb-5">
            <div className="flex items-center justify-between text-xs font-bold text-slate-500">
              <span>{progress.current} / {progress.total}</span>
              <span>{percent}%</span>
            </div>
            <div
              className="mt-1.5 h-2 overflow-hidden rounded-full bg-slate-200"
              role="progressbar"
              aria-label="레슨 진행"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={percent}
            >
              <div className="h-full rounded-full bg-slate-900" style={{ width: `${percent}%` }} />
            </div>
          </div>
        )}

        <section aria-label="레슨 내용">
          {children ?? (
            <p className="rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center text-sm text-slate-400">
              레슨 콘텐츠가 들어갈 자리예요.
            </p>
          )}
        </section>

        {footer && <div className="mt-6">{footer}</div>}
      </main>
    </div>
  )
}
