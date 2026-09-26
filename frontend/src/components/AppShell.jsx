import { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import useStore from '../store/useStore'
import { authAPI, reviewAPI, learningAPI } from '../api'
import Logo from './Logo'
import { levelProgress } from '../lib/level'

/**
 * 앱 셸 (핸드오프 §3.3, Figma 58:12 사이드바 · 59:12 오른쪽 패널 · 232:36 모바일 상단 바 · 232:52 하단 탭).
 * 데스크톱(lg+): 좌측 사이드바 6탭 + 본문 + 오른쪽 패널(xl 이상 — lg~xl에서는 본문 폭이 모자라 숨긴다).
 * 모바일(lg 미만): 상단 바(로고 + 불꽃·별·프로필) + 본문 + 하단 탭 5개. 페이지 배경은 surface/background라
 * 상단 바가 흰 띠 없이 본문과 이어진다.
 * 발화 트랙(/learn/path?track=speak)이면 루트에 data-track="speak"를 달아 셸과 본문의 트랙색
 * (text-track·bg-track·.btn-primary·사이드바 활성·하단 탭 활성)을 분홍으로 바꾼다(§3.1).
 *
 * props
 *   active       사이드바·하단 탭 활성 key(learn·practice·task·review·analysis·profile). 없으면 경로로 찾는다.
 *   title        탭 제목(모바일 25px / lg 30px).
 *   description  제목 아래 부제. 9/26 Figma에서 연습 기능 화면의 부제가 모두 빠져 지금은 넘기는 곳이 없다.
 *   closeTo      주면 제목 줄 오른쪽 끝에 나가기 X(40px 원, 453:83)를 두고 누르면 그 경로로 간다(연습 기능 화면 → /practice/hub,
 *                변경 내역 §4-4).
 *   rail         오른쪽 패널 구성: 'default'(스탯 + 오늘의 과제 + 복습할 항목, 59:12)
 *                | 'tasks'(스탯 + 레벨 진행 + 복습할 항목, 137:151) | 'review'(스탯 + 오늘의 과제 + 이번 주 복습, 100:113)
 *   rightRail    직접 만든 패널 노드(rail보다 우선). 아래 Rail* 조각을 조합해 쓸 수 있다.
 * data: 스탯은 useStore.user(셸이 뜰 때 /auth/me로 새로 고침), 패널 카드는 reviewAPI·learningAPI(분석 요약·활동 날짜).
 */
const NAV = [
  { key: 'learn', label: '학습', to: '/learn/path', icon: '/ui/nav-learn.svg' },
  { key: 'practice', label: '연습', to: '/practice/hub', icon: '/ui/nav-practice.svg' },
  { key: 'task', label: '과제', to: '/tasks', icon: '/ui/nav-task.svg' },
  { key: 'review', label: '복습', to: '/review', icon: '/ui/nav-review.svg' },
  { key: 'analysis', label: '분석', to: '/analysis', icon: '/ui/nav-analytics.svg' },
  { key: 'profile', label: '프로필', to: '/profile', icon: '/ui/nav-profile.svg' },
]

/** 발화 트랙(학습 경로 ?track=speak)일 때만 셸을 분홍으로 테마링. */
function useSpeakLearn() {
  const location = useLocation()
  return location.pathname.startsWith('/learn/path') && new URLSearchParams(location.search).get('track') === 'speak'
}

function useMinWidth(px) {
  const query = `(min-width: ${px}px)`
  const [ok, setOk] = useState(() => typeof window !== 'undefined' && window.matchMedia(query).matches)
  useEffect(() => {
    const m = window.matchMedia(query)
    const sync = () => setOk(m.matches)
    sync()
    m.addEventListener('change', sync)
    return () => m.removeEventListener('change', sync)
  }, [query])
  return ok
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

/** 마스크 아이콘 — 글자색(currentColor)으로 칠한다(활성·트랙색). index.css .mask-icon */
function MaskIcon({ src, className = '' }) {
  return <span aria-hidden className={`mask-icon ${className}`} style={{ '--icon': `url(${src})` }} />
}

/** 아바타 — 프로필 사진 기능이 없어(220:202 사진 변경 미구현) 이름 첫 글자로 대신한다. */
function Avatar({ className = '' }) {
  const user = useStore((s) => s.user)
  return (
    <span className={`flex shrink-0 items-center justify-center rounded-full border-2 border-primary-200 bg-primary-100 font-black text-primary-600 ${className}`}>
      {(user?.username || '게')[0]}
    </span>
  )
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

/** 오른쪽 패널 스탯 줄(59:13) — 아바타 34 │ 불꽃 21 · 별 18 · 레벨 18, 15px. */
export function RailStats() {
  const { level, xp, streak } = useStats()
  return (
    <div className="flex items-center justify-center gap-[18px] pb-2">
      <Avatar className="size-[34px] text-[14px]" />
      <span className="h-[22px] w-[1.5px] shrink-0 bg-line" />
      <Stat icon="/ui/stat-streak.svg" box={21} value={streak} className="gap-1.5 text-[15px] text-stat-streak" />
      <Stat icon="/ui/stat-xp.svg" box={18} w={17.12} h={16.28} value={xp.toLocaleString()} className="gap-1.5 text-[15px] text-stat-xp" />
      <Stat icon="/ui/stat-level.svg" box={18} w={15.59} h={18} value={`Lv.${level}`} className="gap-1.5 text-[15px] text-stat-level" />
    </div>
  )
}

function TaskItem({ label, cur, total }) {
  const done = cur >= total
  return (
    <div className="flex items-center gap-3">
      {done
        ? <img src="/ui/lp-318-33-checkbox-on.svg" alt="" className="size-[22px] shrink-0" />
        : <span className="size-[22px] shrink-0 rounded-[7px] border-2 border-line" />}
      <span className="min-w-0 flex-1 text-[15px] font-medium leading-figma text-ink-muted">{label}</span>
      <span className="shrink-0 text-[13px] font-bold leading-figma text-ink-muted">{cur}/{total}</span>
    </div>
  )
}

/** 오늘의 과제(59:23) — 진행은 과제 탭과 같은 출처: 복습 대기 수 + /api/analysis/overview(오늘 독화·회차). */
export function RailTasksCard({ due, overview }) {
  const navigate = useNavigate()
  return (
    <div className="card-flat flex flex-col gap-4">
      <div className="flex items-center justify-between font-bold leading-figma">
        <p className="text-[17px] text-ink">오늘의 과제</p>
        <button type="button" onClick={() => navigate('/tasks')} className="text-[14px] text-track">모두 보기</button>
      </div>
      <TaskItem label="오늘의 복습 정리" cur={due === 0 ? 1 : 0} total={1} />
      <TaskItem label="독화 학습 1회" cur={Math.min(1, overview?.today_read ?? 0)} total={1} />
      <TaskItem label="학습 2회 채우기" cur={Math.min(2, overview?.today_sessions ?? 0)} total={2} />
    </div>
  )
}

/** 복습할 항목(59:39·296:32) — 오답 N개 │ 북마크 N개(숫자만 크게, 오답 보라·북마크 파랑) + 복습하기 → /review. */
export function RailReviewCard({ due, marks }) {
  const navigate = useNavigate()
  return (
    <div className="card-flat flex flex-col items-center gap-3.5">
      <div className="flex items-baseline gap-3 font-bold leading-figma">
        <p className="text-[17px] text-ink">오답 <span className="text-[22px] text-primary-500">{due ?? '…'}</span><span className="text-primary-500">개</span></p>
        <span className="h-[18px] w-[1.5px] shrink-0 rounded-[1px] bg-line" />
        <p className="text-[17px] text-ink">북마크 <span className="text-[22px] text-bookmark">{marks ?? '…'}</span><span className="text-bookmark">개</span></p>
      </div>
      <button type="button" onClick={() => navigate('/review')} className="btn-primary btn-md w-full">복습하기</button>
    </div>
  )
}

/** 레벨 진행(137:163) — 과제 탭 패널. 남은 XP는 백엔드 레벨 공식(lib/level.js). */
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
          <p className="text-track">{p.remaining.toLocaleString()} XP 남음</p>
        </div>
        <div className="h-[12px] overflow-hidden rounded-full bg-fill">
          <div className="h-full rounded-full bg-track" style={{ width: `${p.pct}%` }} />
        </div>
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
        <p className="text-[17px] text-ink">이번 주 복습</p>
        {count > 0 && <p className="text-[14px] text-track">{count}일째</p>}
      </div>
      <div className="flex items-start justify-between">
        {days.map((d) => (
          <div key={d.label} className="flex flex-col items-center gap-2">
            {d.done
              ? <img src="/ui/review-daydone.svg" alt="" className="size-[30px]" />
              : <span className="size-[30px] rounded-full bg-fill" />}
            <span className={`text-[12px] font-bold leading-figma ${d.done ? 'text-track' : 'text-ink-muted opacity-60'}`}>{d.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

/** 패널 카드가 쓰는 데이터 — 구성(variant)에 필요한 것만 부른다. 실패하면 null(표시는 '…'·미완료). */
function useRailData(variant) {
  const [due, setDue] = useState(null)
  const [marks, setMarks] = useState(null)
  const [overview, setOverview] = useState(null)
  const [activeDays, setActiveDays] = useState(null)
  useEffect(() => {
    let on = true
    reviewAPI.getDue().then((d) => { if (on) setDue((d.items || []).length) }).catch(() => { if (on) setDue(null) })
    if (variant !== 'review') {
      // 복습 탭 목록과 같게 두 트랙(독화·발화) 북마크를 모두 센다
      learningAPI.getBookmarks().then((b) => { if (on) setMarks((Array.isArray(b) ? b : b.items || []).length) }).catch(() => { if (on) setMarks(null) })
    }
    if (variant !== 'tasks') {
      learningAPI.getAnalysisOverview().then((d) => { if (on) setOverview(d) }).catch(() => { if (on) setOverview(null) })
    }
    if (variant === 'review') {
      learningAPI.getCalendarActivities().then((d) => { if (on) setActiveDays(new Set(Object.keys(d || {}))) }).catch(() => { if (on) setActiveDays(new Set()) })
    }
    return () => { on = false }
  }, [variant])
  return { due, marks, overview, activeDays }
}

/** 오른쪽 패널(368px, p24 gap16). */
function Rail({ variant = 'default' }) {
  const { due, marks, overview, activeDays } = useRailData(variant)
  return (
    <div className="flex h-full w-[368px] shrink-0 flex-col gap-4 bg-white p-6">
      <RailStats />
      {variant === 'tasks' ? <RailLevelCard /> : <RailTasksCard due={due} overview={overview} />}
      {variant === 'review' ? <RailWeekCard activeDays={activeDays} /> : <RailReviewCard due={due} marks={marks} />}
    </div>
  )
}

/** 모바일 상단 바(232:36) — 로고 + 불꽃·별·아바타(→ /profile). 배경은 페이지색이라 본문과 이어진다. */
function MobileTopBar({ pink }) {
  const navigate = useNavigate()
  const { xp, streak } = useStats()
  return (
    <header className="sticky top-0 z-20 flex items-center justify-between bg-page px-[18px] pb-[14px] pt-4 lg:hidden">
      <Logo size={20} pink={pink} />
      <div className="flex items-center gap-3">
        <Stat icon="/ui/stat-flame.svg" box={17} value={streak} className="gap-1 text-[14px] text-stat-streak" />
        <Stat icon="/ui/lp-232-48-star.svg" box={15} w={14.27} h={13.57} value={xp.toLocaleString()} className="gap-1 text-[14px] text-stat-xp" />
        <button type="button" onClick={() => navigate('/profile')} aria-label="프로필" className="shrink-0 rounded-full">
          <Avatar className="size-[30px] text-[13px]" />
        </button>
      </div>
    </header>
  )
}

/** 모바일 하단 탭 바(232:52) — 프로필을 뺀 5탭. 활성은 트랙색, 비활성은 text/secondary. */
function MobileTabBar({ activeKey }) {
  const navigate = useNavigate()
  const tabs = NAV.filter((n) => n.key !== 'profile')
  return (
    <nav className="fixed inset-x-0 bottom-0 z-30 flex min-h-[78px] items-center border-t-1.5 border-line bg-white px-2 pb-[env(safe-area-inset-bottom)] pt-2.5 lg:hidden" aria-label="주 메뉴">
      {tabs.map((n) => {
        const on = activeKey === n.key
        return (
          <button key={n.key} type="button" onClick={() => navigate(n.to)}
            aria-current={on ? 'page' : undefined}
            className={`flex min-w-0 flex-1 flex-col items-center gap-[5px] py-1.5 text-[11px] font-bold leading-figma ${on ? 'text-track' : 'text-ink-muted'}`}>
            <MaskIcon src={n.icon} className="size-[23px]" />
            {n.label}
          </button>
        )
      })}
    </nav>
  )
}

export default function AppShell({ children, active, rail = 'default', rightRail, title, description, closeTo }) {
  const navigate = useNavigate()
  const location = useLocation()
  const speak = useSpeakLearn()
  const showRail = useMinWidth(1280)
  useUserSync()
  const activeKey = active || NAV.find((n) => location.pathname.startsWith(n.to))?.key

  return (
    <div data-track={speak ? 'speak' : undefined}
      className="flex min-h-[100dvh] flex-col bg-page lg:flex-row lg:items-stretch lg:bg-white">
      {/* 상단 바 (모바일) */}
      <MobileTopBar pink={speak} />

      {/* 좌측 사이드바 (데스크톱, 58:12) */}
      <nav className="hidden w-[256px] shrink-0 flex-col gap-2 border-r border-line bg-white px-4 pb-6 pt-7 lg:flex" aria-label="주 메뉴">
        <Logo size={30} pink={speak} />
        <div className="h-5" />
        {NAV.map((n) => {
          const on = activeKey === n.key
          return (
            <button key={n.key} type="button" onClick={() => navigate(n.to)}
              aria-current={on ? 'page' : undefined}
              className={`side-item ${on ? 'side-item-active' : ''}`}>
              <MaskIcon src={n.icon} className="size-6" />
              {n.label}
            </button>
          )
        })}
      </nav>

      {/* 본문 — 모바일 232:51(좌우 18 · 간격 14), 데스크톱 58:11(32 · 20). 모바일 하단은 탭 바 높이만큼 비운다. */}
      <main className="flex min-w-0 flex-1 flex-col gap-3.5 px-[18px] pb-[calc(var(--tabbar-h)+18px+env(safe-area-inset-bottom))] pt-5 lg:gap-5 lg:px-8 lg:pb-10 lg:pt-8">
        {(title || description) && (
          <header className="flex flex-col gap-2 leading-figma">
            {/* 제목 줄(453:82 Page head): 제목 + 오른쪽 끝 나가기 X */}
            <div className="flex items-center justify-between gap-3">
              {title && <h1 className="text-[25px] font-bold tracking-[-0.625px] text-ink lg:text-[30px] lg:tracking-[-0.75px]">{title}</h1>}
              {closeTo && (
                <button type="button" onClick={() => navigate(closeTo)} aria-label="나가기"
                  className="size-10 shrink-0 rounded-full transition-opacity hover:opacity-80">
                  <img src="/ui/lp-453-83-page-close.svg" alt="" className="size-10" />
                </button>
              )}
            </div>
            {description && <p className="text-[15px] text-ink-muted">{description}</p>}
          </header>
        )}
        {children}
      </main>

      {/* 오른쪽 패널 (xl 이상) */}
      {showRail && <aside className="flex shrink-0">{rightRail || <Rail variant={rail} />}</aside>}

      {/* 하단 탭 바 (모바일) */}
      <MobileTabBar activeKey={activeKey} />
    </div>
  )
}
