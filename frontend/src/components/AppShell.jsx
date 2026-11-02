import { learnHref, loadLastTrack } from '../lib/lastTrack'
import { useEffect } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import useStore from '../store/useStore'
import { authAPI } from '../api'
import Logo from './Logo'
import NavIcon from './NavIcon'
import { Button } from './UI'

/** 폰·아이패드·컴퓨터 공통 4탭. 1024px부터 왼쪽 메뉴, 그 아래는 하단 메뉴. */
const NAV = [
  { key: 'today', label: '오늘', to: '/today', icon: '/ui/nav-learn.svg' },
  { key: 'learn', label: '학습', to: '/learn/path', icon: '/ui/nav-practice.svg' },
  { key: 'records', label: '기록', to: '/records', icon: '/ui/nav-analytics.svg' },
  { key: 'me', label: '내 정보', to: '/profile', icon: '/ui/nav-profile.svg' },
]

/** 학습 경로의 트랙(?track=speak·listen)이면 셸을 그 트랙색으로 테마링(발화 분홍, 소리 듣기 청록). 아니면 null. */
function useLearnTrack() {
  const location = useLocation()
  if (!location.pathname.startsWith('/learn/path')) return null
  const t = new URLSearchParams(location.search).get('track')
  return t === 'speak' || t === 'listen' ? t : null
}

// 스탯(불꽃·XP·레벨)은 user에서 읽는다. 레슨에서 XP가 바뀌어도 스토어는 모르므로, 셸이 뜰 때
// /auth/me로 새로 고친다(탭을 빠르게 오갈 때 요청이 몰리지 않게 15초 간격). 부팅 직후는 AuthGate가 이미 불렀다.
let lastUserSync = Date.now()
function useUserSync() {
  useEffect(() => {
    if (Date.now() - lastUserSync < 15000) return
    lastUserSync = Date.now()
    authAPI.getMe().then((u) => { if (u) useStore.getState().updateUser(u) }).catch(() => {})
  }, [])
}

function useStats() {
  const user = useStore((s) => s.user)
  const statistics = useStore((s) => s.statistics)
  return {
    user,
    level: Math.max(1, statistics?.current_level || user?.current_level || 1),
    xp: Math.max(0, statistics?.total_xp ?? user?.total_xp ?? 0),
    streak: Math.max(0, user?.streak_count || 0),
  }
}


/** 스탯 한 칸 — 아이콘 상자(box) 안에 SVG를 원래 비율(w×h)로 위·가운데 정렬(Figma 인셋 그대로). */
function Stat({ icon, box, w = box, h = box, value, className }) {
  return (
    <span className={`inline-flex shrink-0 items-center font-bold leading-figma ${className}`}>
      <span className="flex shrink-0 items-start justify-center" style={{ width: box, height: box }}>
        <img src={icon} alt="" className="max-w-none" style={{ width: w, height: h }} />
      </span>
      {value}
    </span>
  )
}

/** 모바일 상단 바(232:36) — 로고 + 불꽃·별·아바타(→ /profile). 배경은 페이지색이라 본문과 이어진다. */
function MobileTopBar({ pink }) {
  const navigate = useNavigate()
  const { xp, streak } = useStats()
  return (
    <header className="sticky top-0 z-20 flex flex-wrap items-center justify-between gap-x-2 bg-page pl-[max(18px,env(safe-area-inset-left))] pr-[max(18px,env(safe-area-inset-right))] pb-[14px] pt-[max(16px,env(safe-area-inset-top))] lg:hidden">
      <Link to="/about" aria-label="LIPLAB 소개" className="inline-flex min-h-11 shrink-0 items-center"><Logo size={20} pink={pink} /></Link>
      <div className="ml-auto flex items-center gap-1 sm:gap-3">
        <Stat icon="/ui/stat-flame.svg" box={17} value={streak} className="gap-1 text-[14px] text-stat-streak" />
        <Stat icon="/ui/lp-232-48-star.svg" box={15} w={14.27} h={13.57} value={xp.toLocaleString()} className="gap-1 text-[14px] text-stat-xp" />
        <Button variant="secondary" onClick={() => window.dispatchEvent(new Event('liplab:a11y-toggle'))} aria-label="접근성 설정"
          className="grid size-11 shrink-0 place-items-center rounded-full border-0 bg-surface-inverse p-0 text-[12px] font-bold tracking-tight text-white">
          Aa
        </Button>

      </div>
    </header>
  )
}

/** 모바일 하단 탭 바(232:52) — 프로필을 뺀 5탭. 활성은 트랙색, 비활성은 text/secondary. */
function MobileTabBar({ activeKey }) {
  const navigate = useNavigate()
  const tabs = NAV
  return (
    <nav data-mobile-tabbar className="fixed inset-x-0 bottom-0 z-30 flex h-[calc(var(--tabbar-h)+env(safe-area-inset-bottom))] items-center border-t-1.5 border-line bg-white pl-[max(8px,env(safe-area-inset-left))] pr-[max(8px,env(safe-area-inset-right))] pb-[env(safe-area-inset-bottom)] pt-2.5 lg:hidden" aria-label="주 메뉴">
      {tabs.map((n) => {
        const on = activeKey === n.key
        return (
          <button key={n.key} type="button" onClick={() => navigate(n.key === 'learn' ? learnHref(loadLastTrack(useStore.getState().user?.id)) : n.to)}
            aria-current={on ? 'page' : undefined}
            className={`flex min-w-0 flex-1 flex-col items-center gap-[5px] py-1.5 text-[11px] font-bold leading-figma ${on ? 'text-track' : 'text-ink-muted'}`}>
            <NavIcon name={n.key} className="size-[23px]" />
            {n.label}
          </button>
        )
      })}
    </nav>
  )
}

export default function AppShell({ children, active, title, description, closeTo, backTo, backLabel = '돌아가기' }) {
  const navigate = useNavigate()
  const location = useLocation()
  const learnTrack = useLearnTrack()
  const stats = useStats()
  const speak = learnTrack === 'speak'
  useUserSync()
  // 셸 안에서는 모바일 접근성 버튼을 상단 바로 옮긴다(A11ySettings가 이 표시를 본다)
  useEffect(() => {
    document.documentElement.dataset.shell = '1'
    return () => { delete document.documentElement.dataset.shell }
  }, [])
  const activeKey = ({ practice: 'learn', task: 'today', review: 'today', analysis: 'records', profile: 'me' }[active] || active) || NAV.find((n) => location.pathname.startsWith(n.to))?.key

  return (
    <div data-track={learnTrack || undefined}
      className="flex min-h-[100dvh] flex-col bg-page lg:flex-row lg:items-stretch lg:bg-white">
      {/* 상단 바 (모바일) */}
      <MobileTopBar pink={speak} />

      {/* 좌측 사이드바 (데스크톱, 58:12) */}
      <nav className="hidden w-[256px] shrink-0 flex-col gap-2 border-r border-line bg-white px-4 pb-6 pt-7 lg:flex" aria-label="주 메뉴">
        <Link to="/about" aria-label="LIPLAB 소개" className="inline-flex min-h-11 self-start items-center"><Logo size={30} pink={speak} /></Link>
        <div className="h-5" />
        {NAV.map((n) => {
          const on = activeKey === n.key
          return (
            <button key={n.key} type="button" onClick={() => navigate(n.key === 'learn' ? learnHref(loadLastTrack(useStore.getState().user?.id)) : n.to)}
              aria-current={on ? 'page' : undefined}
              className={`side-item ${on ? 'side-item-active' : ''}`}>
              <NavIcon name={n.key} className="size-6" />
              {n.label}
            </button>
          )
        })}
        <div className="mt-auto flex flex-wrap gap-3 pt-8 text-sm">
          <Stat icon="/ui/stat-streak.svg" box={18} value={stats.streak} className="gap-1 text-stat-streak" />
          <Stat icon="/ui/stat-xp.svg" box={18} value={stats.xp.toLocaleString()} className="gap-1 text-stat-xp" />
          <Stat icon="/ui/stat-level.svg" box={18} value={`Lv.${stats.level}`} className="gap-1 text-stat-level" />
        </div>
      </nav>

      {/* 본문: 모바일 232:51(좌우 18 · 간격 14), 데스크톱 58:11(32 · 20). 모바일 하단은 탭 바 높이만큼 비운다.
          세로 860px 이하 데스크톱(1366×768 등)은 위아래 여백·간격을 줄여 분석·과제가 한 화면에 들어오게 한다. */}
      {/* id="main-content"는 '본문으로 건너뛰기'(App.jsx SkipLink)의 대상이다. */}
      <main id="main-content" className="mx-auto flex w-full min-w-0 max-w-[816px] flex-1 flex-col gap-3.5 pl-[max(18px,env(safe-area-inset-left))] pr-[max(18px,env(safe-area-inset-right))] pb-[calc(var(--tabbar-h)+18px+env(safe-area-inset-bottom))] pt-5 lg:gap-5 lg:px-8 lg:pb-10 lg:pt-8 lg:[@media(max-height:860px)]:gap-4 lg:[@media(max-height:860px)]:pb-5 lg:[@media(max-height:860px)]:pt-6">
        {(backTo || closeTo) && <Link to={backTo || closeTo} className="inline-flex min-h-11 items-center gap-2 self-start font-bold text-track">‹ {backLabel}</Link>}
        {(title || description) && (
          <header className="flex flex-col gap-2 leading-figma">
            {/* 제목 줄(453:82 Page head): 제목 + 오른쪽 끝 나가기 X */}
            <div className="flex items-center justify-between gap-3">
              {title && <h1 className="text-[25px] font-bold tracking-[-0.625px] text-ink lg:text-[30px] lg:tracking-[-0.75px]">{title}</h1>}

            </div>
            {description && <p className="text-[15px] text-ink-muted">{description}</p>}
          </header>
        )}
        {children}
      </main>

      {/* 오른쪽 패널 (xl 이상) */}


      {/* 하단 탭 바 (모바일) */}
      <MobileTabBar activeKey={activeKey} />
    </div>
  )
}
