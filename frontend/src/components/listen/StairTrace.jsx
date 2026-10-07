import { fmtDb } from '../../lib/listenView'
import { stairPoints } from '../../lib/listenFlow'

/**
 * 소음 계단 흐름(소음 속 듣기 연습). 지난 문장마다 말과 소음의 차이(SNR)를 점으로 잇고, 통과는 초록·놓침은 빨강으로 찍는다.
 * 위로 갈수록 소음이 작다(쉬움). 연습 계단이라 검사 역치·단계 숙달에는 들어가지 않는다는 것을 함께 적는다.
 */
const W = 160
const H = 36

export default function StairTrace({ trace = [], now = null }) {
  const pts = stairPoints(trace, W, H)
  return (
    <div className="flex items-center justify-between gap-4 rounded-14 bg-surface-sunken px-4 py-2.5">
      <div className="flex min-w-0 flex-col gap-0.5 leading-figma">
        <p className="text-[13px] font-bold text-ink">지금 소음 차이 <span className="text-track-dark">{fmtDb(now)}</span></p>
        <p className="break-keep text-[12px] text-ink-muted">연습용 계단이라 검사와 숙달에는 들어가지 않아요</p>
      </div>
      <svg aria-hidden width={W} height={H} viewBox={`-4 -4 ${W + 8} ${H + 8}`} className="shrink-0">
        {pts.length > 1 && (
          <polyline points={pts.map((p) => `${p.x},${p.y}`).join(' ')} fill="none" stroke="var(--track)" strokeWidth="1.5" strokeLinejoin="round" opacity="0.6" />
        )}
        {pts.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r={i === pts.length - 1 ? 3.5 : 2.5} className={p.correct ? 'fill-good' : 'fill-bad'} />
        ))}
        {pts.length === 0 && <line x1="0" y1={H / 2} x2={W} y2={H / 2} stroke="var(--line)" strokeWidth="1.5" strokeDasharray="3 4" />}
      </svg>
    </div>
  )
}
