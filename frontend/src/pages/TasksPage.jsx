import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'
import useStore from '../store/useStore'
import { reviewAPI } from '../api'

/**
 * 과제 탭 (Figma 리디자인 05) — 일일 과제 진행/보상 + 주간 도전 + 배지.
 * 게이미피케이션 화면(전용 백엔드 없음): 스트릭/레벨은 useStore, 복습수는 reviewAPI에서 읽고
 * 과제/배지는 그 값으로부터 파생해 표시한다.
 */
function TaskRow({ label, cur, total, xp }) {
  const done = cur >= total
  return (
    <div className="flex items-center gap-3.5">
      {done ? (
        <img src="/ui/task-done.svg" alt="" className="h-[26px] w-[26px]" />
      ) : (
        <span className="h-[26px] w-[26px] shrink-0 rounded-full border-2 border-line" />
      )}
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <div className="flex items-center justify-between text-[15px] font-bold">
          <span className="text-ink">{label}</span>
          <span className="text-[13px] text-primary-500">{cur} / {total}</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-gray-200">
          <div className="h-full rounded-full bg-primary-500" style={{ width: `${Math.min(100, (cur / total) * 100)}%` }} />
        </div>
      </div>
      <span className={`shrink-0 rounded-full px-3 py-1.5 text-[12px] font-bold ${done ? 'bg-primary-100 text-primary-700' : 'bg-gray-100 text-gray-400'}`}>+{xp} XP</span>
    </div>
  )
}

const BADGES = [
  { label: '첫 걸음', icon: '/ui/medal-0.svg', earned: true },
  { label: '7일 연속', icon: '/ui/medal-1.svg', earned: true },
  { label: '입모양 마스터', icon: '/ui/medal-2.svg', earned: true },
  { label: '정확도 90%', shape: 'check', earned: true },
  { label: '100문제 돌파', icon: '/ui/medal-3.svg', earned: true },
  { label: '복습왕', icon: '/ui/medal-4.svg', earned: true },
  { label: '자유 발화', icon: '/ui/medal-5.svg', earned: true },
  { label: '수어 탐험', icon: '/ui/medal-6.svg', earned: false },
  { label: '30일 연속', icon: '/ui/medal-7.svg', earned: false },
  { label: '새벽 학습', icon: '/ui/medal-8.svg', earned: false },
  { label: '완주', icon: '/ui/medal-9.svg', earned: false },
  { label: '레벨 5', shape: 'lock', earned: false },
]

function Badge({ b }) {
  return (
    <div className={`flex flex-col items-center gap-2 ${b.earned ? '' : 'opacity-50'}`}>
      {b.icon ? (
        <img src={b.icon} alt="" className="h-14 w-14" />
      ) : b.shape === 'check' ? (
        <span className="flex h-14 w-14 items-center justify-center rounded-full bg-emerald-100">
          <span className="h-5 w-5 rotate-45 rounded-sm bg-emerald-500" style={{ clipPath: 'polygon(40% 100%, 0 60%, 15% 45%, 40% 70%, 85% 15%, 100% 30%)' }} />
        </span>
      ) : (
        <span className="flex h-14 w-14 items-center justify-center rounded-full bg-gray-100">
          <span className="h-6 w-6 rounded-md bg-gray-300" />
        </span>
      )}
      <span className="text-center text-[11.5px] font-bold text-ink">{b.label}</span>
    </div>
  )
}

export default function TasksPage() {
  const navigate = useNavigate()
  const user = useStore((s) => s.user)
  const [due, setDue] = useState(null)
  useEffect(() => {
    reviewAPI.getDue().then((d) => setDue((d.items || []).length)).catch(() => setDue(0))
  }, [])
  const reviewDone = due === 0 ? 1 : 0
  const earned = BADGES.filter((b) => b.earned).length

  return (
    <AppShell active="task" title="과제" description="매일 조금씩 채우면 보상이 쌓여요.">
      {/* 오늘의 과제 */}
      <section className="card-flat w-full">
        <div className="flex items-center justify-between">
          <p className="text-[17px] font-bold text-ink">오늘의 과제</p>
          <span className="text-[13px] text-ink-muted">오늘 안에 채워요</span>
        </div>
        <div className="mt-4 flex flex-col gap-4">
          <TaskRow label="오늘의 복습 정리" cur={reviewDone} total={1} xp={10} />
          <TaskRow label="독화 학습 1회" cur={0} total={1} xp={15} />
          <TaskRow label="학습 2회 채우기" cur={1} total={2} xp={20} />
        </div>
      </section>

      {/* 이번 주 도전 */}
      <section className="relative w-full overflow-hidden rounded-[20px] border-2 border-b-[5px] border-[#6d3fc4] p-6"
        style={{ backgroundImage: 'linear-gradient(168deg, #a78bfa 0%, #7d53de 71%)' }}>
        <div className="flex max-w-[462px] flex-col gap-2.5">
          <p className="text-[13px] font-bold uppercase tracking-wider text-white/80">특별 과제</p>
          <p className="text-[23px] font-bold tracking-[-0.46px] text-white">이번 주 5일 학습하기</p>
          <div className="flex justify-between text-sm font-bold text-white/90">
            <span>{Math.min(5, Math.max(0, user?.streak_count || 3))} / 5일</span>
            <span>+100 XP</span>
          </div>
          <div className="h-3 overflow-hidden rounded-full bg-white/30">
            <div className="h-full rounded-full bg-white" style={{ width: `${(Math.min(5, Math.max(0, user?.streak_count || 3)) / 5) * 100}%` }} />
          </div>
        </div>
        <div className="pointer-events-none absolute right-6 top-6 hidden h-[104px] w-[104px] items-center justify-center rounded-full bg-white/20 sm:flex">
          <img src="/ui/trophy.svg" alt="" className="h-14 w-14" />
        </div>
      </section>

      {/* 배지 */}
      <section className="card-flat w-full">
        <div className="flex items-center justify-between">
          <p className="text-[17px] font-bold text-ink">배지</p>
          <span className="text-[13px] text-ink-muted">{earned} / {BADGES.length}개 획득</span>
        </div>
        <div className="mt-4 grid grid-cols-4 gap-y-5 sm:grid-cols-6">
          {BADGES.map((b) => <Badge key={b.label} b={b} />)}
        </div>
      </section>
    </AppShell>
  )
}
