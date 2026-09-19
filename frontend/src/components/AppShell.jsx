import { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import useStore from '../store/useStore'
import { reviewAPI } from '../api'

/**
 * 앱 셸 (Figma 리디자인 05 기타탭 공통 골격) — 좌측 아이콘 내비 + 본문 + 우측 스탯 레일.
 * 데스크톱(lg+)에서 3열, 모바일에서는 본문만(내비/레일 숨김).
 * data: 좌측 내비는 라우트 이동, 우측 레일은 useStore(user/statistics)+reviewAPI에서 스탯을 읽는다.
 */
const NAV = [
  { key: 'learn', label: '학습', to: '/dashboard', icon: '/ui/nav-learn.svg' },
  { key: 'practice', label: '연습', to: '/practice/hub', icon: '/ui/nav-practice.svg' },
  { key: 'task', label: '과제', to: '/tasks', icon: '/ui/nav-task.svg' },
  { key: 'review', label: '복습', to: '/review/today', icon: '/ui/nav-review.svg' },
  { key: 'analysis', label: '분석', to: '/analysis/overview', icon: '/ui/nav-analytics.svg' },
  { key: 'profile', label: '프로필', to: '/profile', icon: '/ui/nav-profile.svg' },
]

function Logo() {
  return (
    <div className="flex items-center gap-2 px-2">
      <img src="/ui/logo.png" alt="" className="h-7 w-auto" />
      <span className="font-display text-[26px] leading-none tracking-[-1px] text-primary-500">LIPLAB</span>
    </div>
  )
}

function StatPill({ icon, value, color }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <img src={icon} alt="" className="h-[18px] w-[18px]" />
      <span className="text-[15px] font-bold" style={{ color }}>{value}</span>
    </span>
  )
}

/** 기본 우측 레일 — 스탯 + 복습할 항목. 페이지가 rightRail prop으로 대체 가능. */
function DefaultRail() {
  const user = useStore((s) => s.user)
  const statistics = useStore((s) => s.statistics)
  const [due, setDue] = useState(null)
  useEffect(() => {
    let on = true
    reviewAPI.getDue().then((d) => { if (on) setDue((d.items || []).length) }).catch(() => { if (on) setDue(0) })
    return () => { on = false }
  }, [])
  const level = Math.max(1, statistics?.current_level || user?.current_level || 1)
  const xp = Math.max(0, statistics?.total_xp ?? user?.total_xp ?? 0)
  const streak = Math.max(0, user?.streak_count || 0)
  return (
    <div className="flex h-full w-[300px] shrink-0 flex-col gap-4 border-l-2 border-line bg-white p-6">
      <div className="flex items-center justify-center gap-4 pb-1">
        <div className="flex h-[34px] w-[34px] items-center justify-center rounded-full border-2 border-primary-200 bg-primary-100 text-sm font-black text-primary-600">
          {(user?.username || '게')[0]}
        </div>
        <span className="h-[22px] w-px bg-line" />
        <StatPill icon="/ui/stat-streak.svg" value={streak} color="#b45309" />
        <StatPill icon="/ui/stat-xp.svg" value={xp.toLocaleString()} color="#5f3ab8" />
        <StatPill icon="/ui/stat-level.svg" value={`Lv.${level}`} color="#0369a1" />
      </div>
      <div className="card-flat">
        <p className="text-[17px] font-bold text-ink">복습할 항목</p>
        <p className="mt-3 text-sm leading-relaxed text-ink-muted">
          오늘 다시 볼 항목이 <b className="text-[16px] text-primary-500">{due ?? '…'}개</b> 있어요.
        </p>
      </div>
      <ReviewCta />
    </div>
  )
}

function ReviewCta() {
  const navigate = useNavigate()
  return (
    <button type="button" onClick={() => navigate('/review/today')} className="btn-primary w-full !py-4 text-[18px]">
      복습 시작하기
    </button>
  )
}

export default function AppShell({ children, active, rightRail, title, description }) {
  const navigate = useNavigate()
  const location = useLocation()
  const activeKey = active || NAV.find((n) => location.pathname.startsWith(n.to))?.key

  return (
    <div className="flex min-h-[100dvh] items-stretch bg-white">
      {/* 좌측 내비 (데스크톱) */}
      <nav className="hidden w-[240px] shrink-0 flex-col gap-2 border-r-2 border-line bg-white px-4 pb-6 pt-7 lg:flex" aria-label="주 메뉴">
        <Logo />
        <div className="h-5" />
        {NAV.map((n) => (
          <button
            key={n.key}
            type="button"
            onClick={() => navigate(n.to)}
            aria-current={activeKey === n.key ? 'page' : undefined}
            className={`side-item ${activeKey === n.key ? 'side-item-active' : ''}`}
          >
            <img src={n.icon} alt="" className="h-6 w-6" />
            {n.label}
          </button>
        ))}
      </nav>

      {/* 본문 */}
      <main className="flex min-w-0 flex-1 flex-col gap-5 px-5 pb-10 pt-7 sm:px-8">
        {(title || description) && (
          <header className="flex flex-col gap-2">
            {title && <h1 className="text-[26px] font-bold tracking-[-0.75px] text-ink sm:text-[30px]">{title}</h1>}
            {description && <p className="text-[15px] text-ink-muted">{description}</p>}
          </header>
        )}
        {children}
      </main>

      {/* 우측 레일 (데스크톱) */}
      <aside className="hidden xl:flex">{rightRail || <DefaultRail />}</aside>
    </div>
  )
}
