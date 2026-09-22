import { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import useStore from '../store/useStore'
import { reviewAPI, learningAPI } from '../api'

/**
 * 앱 셸 (Figma 리디자인 05 기타탭 공통 골격) — 좌측 아이콘 내비 + 본문 + 우측 스탯 레일.
 * 데스크톱(lg+)에서 3열, 모바일에서는 본문만(내비/레일 숨김).
 * data: 좌측 내비는 라우트 이동, 우측 레일은 useStore(user/statistics)+reviewAPI에서 스탯을 읽는다.
 */
const NAV = [
  { key: 'learn', label: '학습', to: '/learn/path', icon: '/ui/nav-learn.svg' },
  { key: 'practice', label: '연습', to: '/practice/hub', icon: '/ui/nav-practice.svg' },
  { key: 'task', label: '과제', to: '/tasks', icon: '/ui/nav-task.svg' },
  { key: 'review', label: '복습', to: '/review', icon: '/ui/nav-review.svg' },
  { key: 'analysis', label: '분석', to: '/analysis', icon: '/ui/nav-analytics.svg' },
  { key: 'profile', label: '프로필', to: '/profile', icon: '/ui/nav-profile.svg' },
]

function Logo({ pink }) {
  return (
    <div className="flex items-center gap-2 px-2">
      <span className="flex h-8 w-8 items-center justify-center rounded-full" style={{ background: pink ? '#ffe4e9' : '#efe9fc' }}>
        <img src="/ui/mascot.svg" alt="" className="h-6 w-6" />
      </span>
      <span className="font-display text-[30px] leading-none tracking-[-1.5px]" style={{ color: pink ? '#ec4899' : '#7d53de' }}>LIPLAB</span>
    </div>
  )
}

/** 발화 트랙(학습 경로 ?track=speak)일 때만 셸을 분홍으로 테마링. */
function useSpeakLearn() {
  const location = useLocation()
  return location.pathname.startsWith('/learn/path') && new URLSearchParams(location.search).get('track') === 'speak'
}

function StatPill({ icon, value, color, size = 18 }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <img src={icon} alt="" style={{ width: size, height: size }} />
      <span className="text-[15px] font-bold" style={{ color }}>{value}</span>
    </span>
  )
}

// Figma "Button / Primary" — 3D 하단테두리 스타일(index.css btn-primary는 flat이라 인라인 적용).
const BTN_3D =
  'flex w-full items-center justify-center rounded-[16px] border-2 border-b-[6px] border-primary-700 bg-primary-500 py-[18px] text-[20px] font-bold tracking-[-0.2px] text-white transition hover:bg-primary-600 active:translate-y-[2px] active:border-b-2 disabled:opacity-50'

function TaskItem({ label, cur, total }) {
  const done = cur >= total
  return (
    <div className="flex items-center gap-3">
      <span className={`flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-[7px] border-2 ${done ? 'border-primary-500 bg-primary-500' : 'border-line'}`}>
        {done && <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="#fff" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 13l4 4L19 7" /></svg>}
      </span>
      <span className="flex-1 text-[15px] font-medium text-ink-muted">{label}</span>
      <span className="text-[13px] font-bold text-ink-muted">{cur}/{total}</span>
    </div>
  )
}

/** 기본 우측 레일 (Figma) — 스탯 + 오늘의 과제 + 복습할 항목. */
function DefaultRail({ pink }) {
  const navigate = useNavigate()
  const user = useStore((s) => s.user)
  const statistics = useStore((s) => s.statistics)
  const [due, setDue] = useState(null)
  const [marks, setMarks] = useState(null)
  useEffect(() => {
    let on = true
    reviewAPI.getDue().then((d) => { if (on) setDue((d.items || []).length) }).catch(() => { if (on) setDue(0) })
    learningAPI.getBookmarks('read').then((b) => { if (on) setMarks((Array.isArray(b) ? b : b.items || []).length) }).catch(() => { if (on) setMarks(0) })
    return () => { on = false }
  }, [])
  const level = Math.max(1, statistics?.current_level || user?.current_level || 1)
  const xp = Math.max(0, statistics?.total_xp ?? user?.total_xp ?? 0)
  const streak = Math.max(0, user?.streak_count || 0)
  return (
    <div className="flex h-full w-[368px] shrink-0 flex-col gap-4 bg-white p-6">
      <div className="flex items-center justify-center gap-[18px] pb-2">
        <div className="flex h-[34px] w-[34px] items-center justify-center rounded-full border-2 border-primary-200 bg-primary-100 text-sm font-black text-primary-600">
          {(user?.username || '게')[0]}
        </div>
        <span className="h-[22px] w-[1.5px] bg-line" />
        <StatPill icon="/ui/stat-streak.svg" value={streak} color="#b45309" size={21} />
        <StatPill icon="/ui/stat-xp.svg" value={xp.toLocaleString()} color="#5f3ab8" />
        <StatPill icon="/ui/stat-level.svg" value={`Lv.${level}`} color="#0369a1" />
      </div>
      <div className="card-flat !border-2">
        <div className="flex items-center justify-between">
          <p className="text-[17px] font-bold text-ink">오늘의 과제</p>
          <button type="button" onClick={() => navigate('/tasks')} className="text-[14px] font-bold" style={{ color: pink ? '#ec4899' : '#7d53de' }}>모두 보기</button>
        </div>
        <div className="mt-4 flex flex-col gap-4">
          <TaskItem label="오늘의 복습 정리" cur={due === 0 ? 1 : 0} total={1} />
          <TaskItem label="독화 학습 1회" cur={0} total={1} />
          <TaskItem label="학습 2회 채우기" cur={1} total={2} />
        </div>
      </div>
      {/* 복습할 항목 (Figma 59:39 / 296:32) — 오답 N개 │ 북마크 N개 + 복습하기 */}
      <div className="card-flat flex flex-col items-center gap-3.5 !border-2 !p-5">
        <div className="flex items-baseline gap-3">
          <p className="text-[17px] font-bold text-ink">오답 <span className="text-[22px] text-primary-500">{due ?? '…'}</span><span className="text-primary-500">개</span></p>
          <span className="h-[18px] w-[1.5px] rounded-sm bg-line" />
          <p className="text-[17px] font-bold text-ink">북마크 <span className="text-[22px] text-[#2563eb]">{marks ?? '…'}</span><span className="text-[#2563eb]">개</span></p>
        </div>
        <button type="button" onClick={() => navigate('/review')} className={`${BTN_3D} !py-[14px] !text-[17px]`}
          style={pink ? { background: '#ec4899', borderColor: '#be185d' } : undefined}>
          복습하기
        </button>
      </div>
    </div>
  )
}

/** 모바일 상단 바 (Figma 10) — 로고 + 컴팩트 스탯 + 아바타(프로필). lg 미만에서만. */
function MobileTopBar({ pink }) {
  const navigate = useNavigate()
  const user = useStore((s) => s.user)
  const statistics = useStore((s) => s.statistics)
  const level = Math.max(1, statistics?.current_level || user?.current_level || 1)
  const xp = Math.max(0, statistics?.total_xp ?? user?.total_xp ?? 0)
  const streak = Math.max(0, user?.streak_count || 0)
  return (
    <header className="sticky top-0 z-20 flex items-center justify-between border-b border-line bg-white/95 px-4 py-3 backdrop-blur lg:hidden">
      <Logo pink={pink} />
      <div className="flex items-center gap-2.5">
        <StatPill icon="/ui/stat-streak.svg" value={streak} color="#b45309" />
        <StatPill icon="/ui/stat-xp.svg" value={xp.toLocaleString()} color="#5f3ab8" />
        <StatPill icon="/ui/stat-level.svg" value={`Lv.${level}`} color="#0369a1" />
        <button type="button" onClick={() => navigate('/profile')} aria-label="프로필"
          className="flex h-8 w-8 items-center justify-center rounded-full border-2 border-primary-200 bg-primary-100 text-[13px] font-black text-primary-600">
          {(user?.username || '게')[0]}
        </button>
      </div>
    </header>
  )
}

/** 모바일 하단 탭 바 (Figma 10) — 5개 주 탭. lg 미만에서만, 고정. */
function MobileTabBar({ activeKey }) {
  const navigate = useNavigate()
  const tabs = NAV.filter((n) => n.key !== 'profile')
  return (
    <nav className="fixed inset-x-0 bottom-0 z-30 flex items-stretch border-t border-line bg-white pb-[env(safe-area-inset-bottom)] shadow-[0_-2px_12px_-4px_rgba(26,13,64,0.08)] lg:hidden" aria-label="주 메뉴">
      {tabs.map((n) => {
        const on = activeKey === n.key
        return (
          <button key={n.key} type="button" onClick={() => navigate(n.to)}
            aria-current={on ? 'page' : undefined}
            className="flex flex-1 flex-col items-center gap-1 py-2">
            <span className="h-[22px] w-[22px]" aria-hidden="true"
              style={{ backgroundColor: on ? '#7d53de' : '#b3b3c2',
                WebkitMaskImage: `url(${n.icon})`, maskImage: `url(${n.icon})`,
                WebkitMaskRepeat: 'no-repeat', maskRepeat: 'no-repeat',
                WebkitMaskSize: 'contain', maskSize: 'contain',
                WebkitMaskPosition: 'center', maskPosition: 'center' }} />
            <span className={`text-[11px] font-bold ${on ? 'text-primary-500' : 'text-gray-400'}`}>{n.label}</span>
          </button>
        )
      })}
    </nav>
  )
}

export default function AppShell({ children, active, rightRail, title, description }) {
  const navigate = useNavigate()
  const location = useLocation()
  const speak = useSpeakLearn()
  const activeKey = active || NAV.find((n) => location.pathname.startsWith(n.to))?.key

  return (
    <div className="flex min-h-[100dvh] flex-col bg-white lg:flex-row lg:items-stretch">
      {/* 상단 바 (모바일) */}
      <MobileTopBar pink={speak} />

      {/* 좌측 내비 (데스크톱) */}
      <nav className="hidden w-[256px] shrink-0 flex-col gap-2 border-r border-line bg-white px-4 pb-6 pt-7 lg:flex" aria-label="주 메뉴">
        <Logo pink={speak} />
        <div className="h-5" />
        {NAV.map((n) => {
          const on = activeKey === n.key
          return (
            <button
              key={n.key}
              type="button"
              onClick={() => navigate(n.to)}
              aria-current={on ? 'page' : undefined}
              className={`side-item border-2 border-transparent ${on ? 'side-item-active !border-primary-500 !text-primary-500' : ''}`}
              style={on && speak ? { background: '#ffe4e9', borderColor: '#ec4899', color: '#ec4899' } : undefined}
            >
              <img src={n.icon} alt="" className="h-6 w-6" />
              {n.label}
            </button>
          )
        })}
      </nav>

      {/* 본문 */}
      <main className="flex min-w-0 flex-1 flex-col gap-5 px-5 pb-24 pt-6 sm:px-8 lg:pb-10 lg:pt-7">
        {(title || description) && (
          <header className="flex flex-col gap-2">
            {title && <h1 className="text-[24px] font-bold tracking-[-0.75px] text-ink sm:text-[30px]">{title}</h1>}
            {description && <p className="text-[15px] text-ink-muted">{description}</p>}
          </header>
        )}
        {children}
      </main>

      {/* 우측 레일 (데스크톱) */}
      <aside className="hidden xl:flex">{rightRail || <DefaultRail pink={speak} />}</aside>

      {/* 하단 탭 바 (모바일) */}
      <MobileTabBar activeKey={activeKey} />
    </div>
  )
}
