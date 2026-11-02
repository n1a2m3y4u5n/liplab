import useStore from '../../store/useStore'
import { Progress } from '../UI'
import { levelProgress } from '../../lib/level'
function useStats() { const user = useStore((s) => s.user); const statistics = useStore((s) => s.statistics); return { level: statistics?.current_level || user?.current_level || 1, xp: statistics?.total_xp ?? user?.total_xp ?? 0 } }
export function RailLevelCard() {
  const { level, xp } = useStats()
  const p = levelProgress(level, xp)
  return (
    <div className="card-flat flex flex-col gap-4">
      <div className="flex items-center justify-between font-bold leading-figma">
        <p className="text-[17px] text-ink">레벨 진행</p>
        <p className="text-[14px] text-track">Lv.{p.level}</p>
      </div>
      <div className="flex flex-col gap-2">
        <div className="flex items-start justify-between text-[13px] font-bold leading-figma">
          <p className="text-ink-muted">다음 레벨까지</p>
          <p className="text-track">{p.remaining.toLocaleString()} 경험치 남음</p>
        </div>
        <Progress value={p.pct} label="레벨 진행" animated className="flex-none" />
      </div>
    </div>
  )
}

const WEEK = ['월', '화', '수', '목', '금', '토', '일']
const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

/**
 * 이번 주 복습(100:140 · 102:19) — 월~일 원 7개(한 날 = 체크, 빈 날 = 회색) + 머리 오른쪽 "N일째"(= 이번 주에 한 날 수).
 * activeDays: 학습한 날 'YYYY-MM-DD' 집합(/api/calendar/activities의 키). 복습만 따로 남는 기록이 없어
 * 그날의 학습 활동 전체로 표시한다. N이 0이면 머리 오른쪽을 비운다.
 */
export function RailWeekCard({ activeDays }) {
  const today = new Date()
  const monday = new Date(today.getFullYear(), today.getMonth(), today.getDate() - ((today.getDay() + 6) % 7))
  const days = WEEK.map((label, i) => {
    const d = new Date(monday.getFullYear(), monday.getMonth(), monday.getDate() + i)
    return { label, done: !!activeDays?.has(ymd(d)) }
  })
  const count = days.filter((d) => d.done).length
  return (
    <div className="card-flat flex flex-col gap-4">
      <div className="flex items-center justify-between font-bold leading-figma">
        <p className="text-[17px] text-ink">이번 주 학습</p>
        {count > 0 && <p className="text-[14px] text-track">{count}일째</p>}
      </div>
      <div className="flex items-start justify-between">
        {days.map((d) => (
          <div key={d.label} className="flex flex-col items-center gap-2">
            {d.done
              ? <img src="/ui/review-daydone.svg" alt="" className="size-[30px]" />
              : <span className="size-[30px] rounded-full bg-fill" />}
            <span className={`text-[12px] font-bold leading-figma ${d.done ? 'text-track' : 'text-ink-muted'}`}>{d.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

