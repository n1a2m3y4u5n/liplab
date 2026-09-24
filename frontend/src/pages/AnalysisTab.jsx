import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'
import Modal from '../components/Modal'
import WatermarkCard from '../components/WatermarkCard'
import { learningAPI } from '../api'
import { mergeBadges } from '../lib/badges'
import { scoreLevel, scoreTone } from '../lib/scoreTone'

/**
 * 분석 탭 (Figma 104:15 · 모바일 240:34) — 워터마크 스탯 3칸 + 학습시간 막대차트 + 정확도 선차트 + 상세 링크.
 * 차트는 데이터 배열로 직접 렌더(막대=CSS 높이, 선=인라인 SVG + HTML 점). 상세는 모달로 연다(§4-07).
 * 요약·주간 추이·전체 통계는 GET /api/analysis/overview(backend/analytics.py)의 실측값이다.
 * 기록이 없으면 0·'–'로 보이고, 표본값으로 채우지 않는다.
 * 활동 캘린더·회차 히스토리는 GET /api/calendar/activities(날짜×주제, 독화·발화·검사 모두)로 그린다.
 * 회차 히스토리 행을 누르면 그 학습 화면으로 간다 — 회차 상세 모달(212:24)은 문항별 기록 API가 없어 아직 없다.
 * 크기는 lg 미만이 모바일 프레임 값, lg 이상이 데스크톱 프레임 값이다.
 */

// 스탯 워터마크(326:33/36/41 · 모바일 326:83/86/91) — 회전 -20°, 오른쪽 위로 걸쳐 잘림
const STAT_DECO = {
  clock: { src: '/ui/lp-104-15-deco-clock.svg', size: 70, top: -32.86, right: -34.86, lg: { size: 124, top: -49.47, right: -47.47 } },
  percent: { src: '/ui/lp-104-15-deco-percent.svg', size: 70, top: -32.86, right: -34.86, lg: { size: 124, top: -49.47, right: -47.47 } },
  flame: { src: '/ui/lp-104-15-deco-flame.svg', size: 95, top: -48.88, right: -50.88, lg: { size: 167, top: -77.02, right: -75.03 } },
}

/** 스탯 카드(135:17 / 240:122) — 라벨·값(+ 데스크톱만 증감 줄), 왼쪽 정렬. */
function StatCard({ deco, label, value, delta, color }) {
  return (
    <WatermarkCard deco={STAT_DECO[deco]}
      className="flex min-w-0 flex-1 flex-col gap-1 rounded-14 border-2 border-line bg-white p-3.5 leading-figma lg:gap-[7px] lg:rounded-18 lg:p-5">
      <span className="text-[11.5px] font-bold text-ink-faint lg:text-[13px] lg:text-ink-soft">{label}</span>
      <span className={`text-[19px] font-bold tracking-[-0.38px] lg:text-[27px] lg:tracking-[-0.675px] ${color}`}>{value}</span>
      {delta && <span className="hidden text-[12px] font-bold text-ink-faint lg:block">{delta}</span>}
    </WatermarkCard>
  )
}

/* 주별 추이는 GET /api/analysis/overview 의 weekly(오늘로 끝나는 7일 창 7개, 오래된 순).
   학습 시간은 활동 시각으로 회차를 나눠 추정한 값이다(backend/analytics.py). */
const EMPTY_WEEKS = Array.from({ length: 7 }, () => ({ minutes: 0, accuracy: null }))

/** 분 → '3시간 20분' 식 표기(요약 행용). */
function fmtDur(m) {
  const v = Math.max(0, Math.round(m || 0))
  if (v < 60) return `${v}분`
  if (v >= 600) return `${Math.round(v / 60)}시간`
  return v % 60 ? `${Math.floor(v / 60)}시간 ${v % 60}분` : `${v / 60}시간`
}

/** 차트 카드(197:21 / 240:133) — 머리(제목·'최근 7주') + 플롯. */
function ChartCard({ title, children }) {
  return (
    <section className="flex w-full flex-col gap-3.5 rounded-16 border-2 border-line bg-white p-[18px] lg:gap-[18px] lg:rounded-18 lg:p-[22px]">
      <div className="flex items-center justify-between font-bold leading-figma">
        <p className="text-[16px] text-ink lg:text-[17px]">{title}</p>
        <span className="text-[12px] text-ink-muted lg:text-[13px]">최근 7주</span>
      </div>
      {children}
    </section>
  )
}

// 데스크톱 플롯 그리드 3줄(197:26~28) — 모바일(240:137)에는 없다
function GridLines() {
  return [38, 75, 113].map((t) => (
    <div key={t} className="absolute left-0 right-[-4px] hidden h-px bg-fill lg:block" style={{ top: t }} />
  ))
}

/** 학습시간 추이 막대 — 데스크톱 150px 플롯(막대 46 · 위 8/아래 2 라운드 · 값은 막대 아래), 모바일 110px(막대 26 · 값·그리드 없음). */
function BarChart({ weeks }) {
  const max = Math.max(1, ...weeks.map((w) => w.minutes))
  const fmt = (m) => `${Math.floor(m / 60)}h ${m % 60}m`
  return (
    <div className="relative h-[110px] w-full lg:h-[150px]">
      <GridLines />
      <div className="absolute inset-x-0 bottom-4 top-0 flex items-end lg:bottom-[22px]">
        {weeks.map((w, i) => {
          const last = i === weeks.length - 1
          return (
            <div key={i} className="flex flex-1 justify-center">
              <div className={`h-[calc(var(--r)*76px)] w-[26px] rounded-b-[2px] rounded-t-[6px] lg:h-[calc(var(--r)*114px)] lg:w-[46px] lg:rounded-t-[8px] ${last ? 'bg-primary-500' : 'bg-primary-300'}`}
                style={{ '--r': w.minutes / max }} />
            </div>
          )
        })}
      </div>
      <div className="absolute inset-x-0 bottom-0 hidden h-[18px] items-start lg:flex">
        {weeks.map((w, i) => {
          const last = i === weeks.length - 1
          return (
            <span key={i} className={`flex-1 text-center font-bold leading-figma ${last ? 'text-[11.5px] text-primary-700' : 'text-[10.5px] text-ink-ghost'}`}>
              {fmt(w.minutes)}
            </span>
          )
        })}
      </div>
    </div>
  )
}

/**
 * 정확도 추이 선(104:152 / 240:149) — 에메랄드 선(데스크톱 4 · 모바일 3), 흰 테두리 점(11·마지막 16 / 8·마지막 12).
 * 데스크톱은 점마다 위에 수치(198:21~27, 마지막은 크게 강조), 모바일은 수치·그리드가 없다.
 * 가로: 첫 점 중심 10px(모바일 8) ~ 마지막 점 중심 오른쪽에서 6px(4). 세로: 최저값 123px(89) ~ 최고값 30px(32).
 * 선은 preserveAspectRatio="none" SVG(가로만 늘어남)라 점은 찌그러지지 않게 HTML로 따로 찍는다.
 * 채점 기록이 없는 주는 점·수치를 두지 않고 선을 끊는다.
 */
function LineChart({ weeks }) {
  const vals = weeks.map((w) => (w.accuracy == null ? null : Math.round(w.accuracy * 100)))
  const known = vals.filter((v) => v != null)
  if (!known.length) {
    return <p className="flex h-[110px] items-center justify-center text-[14px] text-ink-muted lg:h-[150px]">아직 채점된 기록이 없어요</p>
  }
  let lo = Math.min(...known)
  let hi = Math.max(...known)
  if (hi - lo < 10) { const mid = (lo + hi) / 2; lo = mid - 5; hi = mid + 5 }   // 작은 차이를 과장하지 않게 최소 10%p 폭
  const t = (v) => (v - lo) / (hi - lo)                                           // 0 = 아래, 1 = 위
  const n = vals.length
  const lastIdx = n - 1
  const path = (yTop, yBottom) => vals
    .map((v, i) => (v == null ? null : [i, yBottom - t(v) * (yBottom - yTop)]))
    .map((p, i, a) => (p ? `${i && a[i - 1] ? 'L' : 'M'}${p[0]} ${p[1].toFixed(1)}` : ''))
    .join(' ')
  // 점·수치 위치 — 가로는 점 사이 등간격, 세로는 브레이크포인트별 CSS 변수(--yt 위 · --yb 아래)
  const posX = (i) => `calc(var(--x0) + ${i} * (100% - var(--xs)) / ${Math.max(1, n - 1)})`
  const posY = (v, off = 0) => `calc(var(--yb) - ${t(v).toFixed(4)} * (var(--yb) - var(--yt)) - ${off}px)`
  return (
    <div className="relative h-[110px] w-full [--x0:8px] [--xs:12px] [--yb:89px] [--yt:32px] lg:h-[150px] lg:[--x0:10px] lg:[--xs:16px] lg:[--yb:123px] lg:[--yt:30px]">
      <GridLines />
      {/* SVG는 대체 요소라 left/right만으로 늘어나지 않는다 — 폭을 점 중심 사이 거리로 직접 준다 */}
      <svg aria-hidden viewBox={`0 0 ${Math.max(1, n - 1)} 110`} preserveAspectRatio="none" className="absolute left-2 top-0 h-[110px] w-[calc(100%-12px)] overflow-visible lg:hidden">
        <path d={path(32, 89)} fill="none" stroke="#10b981" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
      </svg>
      <svg aria-hidden viewBox={`0 0 ${Math.max(1, n - 1)} 150`} preserveAspectRatio="none" className="absolute left-2.5 top-0 hidden h-[150px] w-[calc(100%-16px)] overflow-visible lg:block">
        <path d={path(30, 123)} fill="none" stroke="#10b981" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
      </svg>
      {vals.map((v, i) => v != null && (
        <span key={`p${i}`} aria-hidden
          className={`absolute -translate-x-1/2 -translate-y-1/2 rounded-full border-white bg-emerald-500 ${i === lastIdx ? 'size-3 border-[2.5px] lg:size-4 lg:border-[3px]' : 'size-2 border-[2.5px] lg:size-[11px] lg:border-[3px]'}`}
          style={{ left: posX(i), top: posY(v) }} />
      ))}
      {vals.map((v, i) => v != null && (
        <span key={`v${i}`}
          className={`absolute hidden -translate-x-1/2 font-bold leading-figma lg:block ${i === lastIdx ? 'text-[13px] text-stat-accuracy' : 'text-[11.5px] text-[#7a9a8c]'}`}
          style={{ left: posX(i), top: posY(v, i === lastIdx ? 31.2 : 26.67) }}>
          {v}
        </span>
      ))}
    </div>
  )
}

/** 오른쪽 화살표 — 모바일 6×12 칸(240:161, 8.2×14.2 에셋) · 데스크톱 7×14 칸(198:31 = menu-arrow). */
function Chevron() {
  return (
    <span aria-hidden className="relative h-3 w-1.5 shrink-0 lg:h-3.5 lg:w-[7px]">
      <img src="/ui/lp-240-34-arrow.svg" alt="" className="absolute left-1/2 top-1/2 max-w-none -translate-x-1/2 -translate-y-1/2 lg:hidden" />
      <img src="/ui/menu-arrow.svg" alt="" className="absolute left-1/2 top-1/2 hidden max-w-none -translate-x-1/2 -translate-y-1/2 lg:block" />
    </span>
  )
}

/** 상세 링크(198:29 / 240:159) — 3D 하단테두리(2/2/2/5) 카드형 버튼. */
function DetailLink({ label, onClick }) {
  return (
    <button type="button" onClick={onClick}
      className="flex flex-1 items-center justify-between rounded-14 border-2 border-b-5 border-line bg-white py-[15px] pl-[18px] pr-4 text-[14.5px] font-bold leading-figma text-ink transition-all active:translate-y-[1px] active:border-b-2 lg:rounded-16 lg:py-[18px] lg:pl-5 lg:pr-[18px] lg:text-[15px]">
      {label}
      <Chevron />
    </button>
  )
}

export default function AnalysisTab() {
  const navigate = useNavigate()
  const [modal, setModal] = useState(null)   // 'calendar' | 'history' | 'stats'
  const [detailRow, setDetailRow] = useState(null)   // 회차 상세(212:24)로 연 히스토리 행
  const [cal, setCal] = useState(null)
  const [acts, setActs] = useState(null)   // 날짜별 학습 내용(활동 캘린더·회차 히스토리)
  const [ov, setOv] = useState(null)       // 요약·주별 추이·배지(/api/analysis/overview)
  useEffect(() => {
    learningAPI.getCalendar().then(setCal).catch(() => setCal({}))
    learningAPI.getCalendarActivities().then(setActs).catch(() => setActs(null))   // 실패하면 /api/calendar로 대신
    learningAPI.getAnalysisOverview().then(setOv).catch(() => setOv(null))
  }, [])

  const weeks = ov?.weekly?.length ? ov.weekly : EMPTY_WEEKS
  const sign = (v) => (v > 0 ? '+' : v < 0 ? '−' : '±')
  const minDelta = ov?.has_data
    ? (ov.week_minutes_delta === 0 ? '지난주와 같음' : `지난주 ${sign(ov.week_minutes_delta)}${fmtDur(Math.abs(ov.week_minutes_delta))}`)
    : null
  const accDelta = ov?.week_accuracy_delta != null
    ? `지난주 ${sign(ov.week_accuracy_delta)}${Math.abs(Math.round(ov.week_accuracy_delta * 100))}%p`
    : null
  const counts = dayCounts(cal, acts)
  const history = historyRows(cal, acts)

  return (
    <AppShell active="analysis" title="분석">
      <section className="flex w-full gap-2.5 lg:gap-3.5">
        <StatCard deco="clock" label="총 학습" value={ov ? fmtDur(ov.total_minutes) : '–'} delta={minDelta} color="text-stat-xp" />
        <StatCard deco="percent" label="평균 정확도"
          value={ov?.accuracy != null ? `${Math.round(ov.accuracy * 100)}%` : '–'} delta={accDelta} color="text-stat-accuracy" />
        <StatCard deco="flame" label="연속 학습" value={`${ov?.streak_current ?? 0}일`}
          delta={ov ? `최고 기록 ${ov.streak_best}일` : null} color="text-stat-streak" />
      </section>

      <ChartCard title="학습시간 추이"><BarChart weeks={weeks} /></ChartCard>
      <ChartCard title="정확도 추이"><LineChart weeks={weeks} /></ChartCard>

      <div className="flex w-full flex-col gap-[9px] lg:flex-row lg:gap-3">
        <DetailLink label="활동 캘린더" onClick={() => setModal('calendar')} />
        <DetailLink label="회차 히스토리" onClick={() => setModal('history')} />
        <DetailLink label="전체 통계" onClick={() => setModal('stats')} />
      </div>

      <Modal open={modal === 'calendar'} onClose={() => setModal(null)} title="활동 캘린더"
        subtitle={calSubtitle(counts)} maxW="max-w-[900px]">
        <ActivityCalendar counts={counts} />
      </Modal>
      <Modal open={modal === 'history'} onClose={() => setModal(null)} title="회차 히스토리"
        subtitle={`최근 학습 기록 · 총 ${history.length}회`} maxW="max-w-[820px]">
        <HistoryList rows={history} onOpen={(r) => { setModal(null); setDetailRow(r) }} />
      </Modal>
      <SessionDetail row={detailRow} onClose={() => setDetailRow(null)}
        onGo={(to) => { setDetailRow(null); navigate(to) }} />
      <Modal open={modal === 'stats'} onClose={() => setModal(null)} title="전체 통계" maxW="max-w-[880px]">
        <FullStats ov={ov} onGo={(to) => { setModal(null); navigate(to) }} />
      </Modal>
    </AppShell>
  )
}

/* ── 날짜 유틸 ── */
const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

/** 날짜별 활동 수 — 활동 요약(문장·입모양/단어/문맥·말하기·검사, 현지 날짜)을 합친다.
 *  요약을 불러왔으면 그것만 쓴다 — /api/calendar는 UTC 날짜로 묶어 섞으면 새벽 학습이 전날로 한 번 더 잡힌다.
 *  요약을 못 불러왔을 때만 /api/calendar(문장 연습 수)로 대신한다. */
function dayCounts(cal, acts) {
  if (acts) {
    const out = {}
    for (const [d, rows] of Object.entries(acts)) out[d] = (rows || []).reduce((s, r) => s + (Number(r.n) || 0), 0)
    return out
  }
  return cal || {}
}

/* ── 캘린더 데이터/레벨 ── */
const CAL_WEEKS = 20
const CAL_LEVELS = ['#ededf3', '#ddd3f7', '#b49bec', '#8b5cf6', '#5f3ab8']
const calLevel = (c) => (c <= 0 ? 0 : c === 1 ? 1 : c === 2 ? 2 : c === 3 ? 3 : 4)

/** 20주 × 7일 격자 — 열은 월요일에 맞춰 시작한다(행 라벨 월·수·금·일과 실제 요일이 같다). 날짜 키는 현지 날짜. */
function buildCalWeeks(counts) {
  const today = new Date(); today.setHours(0, 0, 0, 0)
  const monday = new Date(today); monday.setDate(today.getDate() - ((today.getDay() + 6) % 7))
  const start = new Date(monday); start.setDate(monday.getDate() - (CAL_WEEKS - 1) * 7)
  return Array.from({ length: CAL_WEEKS }, (_, w) => Array.from({ length: 7 }, (_, d) => {
    const day = new Date(start); day.setDate(start.getDate() + w * 7 + d)
    const key = ymd(day)
    return { key, count: Number(counts?.[key]) || 0, future: day > today }
  }))
}
/** 모달 부제(207:26) — 최근 20주 · 총 N회 학습(활동 수 합) · 최장 연속 N일. */
function calSubtitle(counts) {
  const days = buildCalWeeks(counts).flat().filter((d) => !d.future)
  const total = days.reduce((s, d) => s + d.count, 0)
  let best = 0, run = 0
  for (const d of days) { if (d.count > 0) { run += 1; best = Math.max(best, run) } else run = 0 }
  return `최근 ${CAL_WEEKS}주 · 총 ${total.toLocaleString()}회 학습 · 최장 연속 ${best}일`
}

/** 활동 캘린더(207:29) — 5단계 보라 히트맵(요일×주, 32px 칸·6px 간격), 요일 라벨(월·수·금·일)·4주마다 주 라벨·범례. */
function ActivityCalendar({ counts }) {
  const cols = buildCalWeeks(counts)
  const dayLabels = ['월', '', '수', '', '금', '', '일']
  return (
    <div className="flex flex-col gap-[22px]">
      <div className="overflow-x-auto pb-1">
        <div className="flex gap-1.5" style={{ minWidth: 'max-content' }}>
          <div className="flex w-[38px] flex-col gap-1.5 pt-[22px]">
            {dayLabels.map((d, i) => (
              <span key={i} className="flex h-8 items-center text-[11px] leading-figma text-ink-ghost">{d}</span>
            ))}
          </div>
          {cols.map((week, i) => (
            <div key={i} className="flex flex-col gap-1.5">
              <span className="h-4 whitespace-nowrap text-[11px] leading-figma text-ink-ghost">{i % 4 === 0 ? `${i + 1}주` : ''}</span>
              {week.map((d) => (
                <span key={d.key} title={d.future ? undefined : `${d.key} · ${d.count}회`}
                  className="size-8 rounded-lg" style={{ backgroundColor: d.future ? 'transparent' : CAL_LEVELS[calLevel(d.count)] }} />
              ))}
            </div>
          ))}
        </div>
      </div>
      <div className="flex items-center justify-end gap-1.5 text-[11.5px] leading-figma text-ink-ghost">
        적음
        {CAL_LEVELS.map((c) => <span key={c} className="size-4 rounded-[5px]" style={{ backgroundColor: c }} />)}
        많음
      </div>
    </div>
  )
}

/* ── 회차 히스토리 데이터 ── */
/** 히스토리에 올릴 날짜(최근순). 활동 요약(acts, 현지 날짜)을 불러왔으면 그것만 쓴다 — /api/calendar는 UTC 날짜라
 *  섞으면 빈 날짜 행이 생긴다. 요약을 못 불러왔을 때만 /api/calendar의 날짜로 대신한다. */
function historyDates(cal, acts) {
  const days = new Set()
  if (acts) {
    for (const [d, rows] of Object.entries(acts)) if (rows?.length) days.add(d)
  } else {
    for (const [d, c] of Object.entries(cal || {})) if (c > 0) days.add(d)
  }
  return [...days].sort((a, b) => (a < b ? 1 : -1))
}
/** 회차 = 날짜 × 주제 한 행(§7-1: 회차 묶음 id가 없어 날짜·레슨 단위로 묶는다). 활동 요약이 없는 날은 문장 연습 한 행. */
function historyRows(cal, acts) {
  return historyDates(cal, acts).slice(0, 30).flatMap((date) => (
    acts?.[date]?.length
      ? acts[date]
      : [{ kind: 'sentence', topic_label: '문장 연습', label: '문장 연습', n: cal?.[date] || 0, route: '/learn/scenario' }]
  ).map((r) => ({ ...r, date })))
}
// 트랙 칩(209:356 · 209:363 · 209:377) — 독화 보라 · 발화 분홍 · 복습 파랑
const TRACK_CHIP = {
  read: { label: '독화', cls: 'bg-primary-100 text-primary-700' },
  speak: { label: '발화', cls: 'bg-speak-tint text-speak-dark' },
  review: { label: '복습', cls: 'bg-blue-100 text-bookmark-dark' },
}
const isReview = (r) => r.kind === 'sentence' && /복습/.test(r.topic || '')
// 정답률 색(§3.2 정답률 85/65 — lib/scoreTone의 판정) — 막대(329:58·60·66)와 % 글자(209:360·367·388)
const ACC_BAR = { good: 'bg-green-500', warn: 'bg-warn', bad: 'bg-red-500' }
const ACC_TEXT = { good: 'text-good-text', warn: 'text-warn-text', bad: 'text-bad-text' }
// 날짜 칸 — Figma 209:22의 '오늘·어제·N일 전'. 원래 날짜는 툴팁으로 둔다.
function relDay(iso) {
  const [y, m, d] = iso.split('-').map(Number)
  const today = new Date(); today.setHours(0, 0, 0, 0)
  const diff = Math.round((today - new Date(y, m - 1, d)) / 86400000)
  return diff <= 0 ? '오늘' : diff === 1 ? '어제' : `${diff}일 전`
}

/**
 * 회차 히스토리(209:353) — 행: 날짜 · 트랙 칩 · 레슨 · [정답률 막대 · 정답률] · N문제 · >.
 * 정답률은 행의 accuracy(0~1, 채점된 시도 평균)로 그린다 — 채점 기록이 없는 행(null)은 막대를 비운다.
 * 행을 누르면 회차 상세(212:24)를 연다. 거기서 그 학습 화면으로 다시 갈 수 있다(오답 복습 행은 /review/mistakes).
 */
function HistoryList({ rows, onOpen }) {
  if (rows.length === 0) return <p className="py-8 text-center text-sm text-ink-muted">아직 학습 기록이 없어요.</p>
  return (
    <div className="flex flex-col">
      {rows.map((r, i) => {
        const chip = TRACK_CHIP[isReview(r) ? 'review' : r.kind === 'speak' ? 'speak' : 'read']
        // 레슨 칸 — 주제 이름. 문장 연습은 상황 이름만으론 뜻이 약해 서버 label('문장 연습 · 카페')을 쓴다.
        const lesson = r.kind === 'sentence' ? (r.label || r.topic_label) : r.topic_label
        const day = relDay(r.date)
        const acc = r.accuracy == null ? null : Math.round(Number(r.accuracy) * 100)
        const level = acc == null ? null : scoreLevel(acc, 'accuracy')
        return (
          <button key={`${r.date}-${r.kind}-${r.topic ?? i}`} type="button" onClick={() => onOpen(r)}
            aria-label={`${day} ${chip.label} ${lesson} 회차 상세 보기`}
            className={`flex w-full items-center gap-3 py-[15px] pr-0.5 text-left leading-figma hover:bg-surface-muted lg:gap-4 ${i ? 'border-t-1.5 border-line' : ''}`}>
            <span className="w-12 shrink-0 text-[12.5px] text-ink-muted lg:w-[70px]" title={r.date}>{day}</span>
            <span className={`flex w-[54px] shrink-0 items-center justify-center rounded-lg py-[5px] text-[11.5px] font-bold ${chip.cls}`}>{chip.label}</span>
            <span className={`min-w-0 truncate text-[15px] font-bold text-ink ${level ? 'flex-1 sm:w-[150px] sm:flex-none sm:shrink-0' : 'flex-1'}`}>{lesson}</span>
            {level && (
              <span className="hidden h-2 min-w-0 flex-1 overflow-hidden rounded-full bg-fill sm:block">
                <span className={`block h-full rounded-full ${ACC_BAR[level]}`} style={{ width: `${Math.min(100, Math.max(0, acc))}%` }} />
              </span>
            )}
            <span className="shrink-0 text-right text-[12.5px] text-ink-muted lg:w-14">{r.kind === 'assessment' ? `${r.n}회` : `${r.n}문제`}</span>
            {level && <span className={`w-12 shrink-0 text-right text-[15px] font-bold ${ACC_TEXT[level]}`}>{acc}%</span>}
            <span aria-hidden className="relative h-3.5 w-[7px] shrink-0">
              <img src="/ui/lp-209-22-arrow.svg" alt="" className="absolute left-1/2 top-1/2 max-w-none -translate-x-1/2 -translate-y-1/2" />
            </span>
          </button>
        )
      })}
    </div>
  )
}

/* ── 회차 상세(212:24 · 모달 212:190) ── */
const DOKA_ICON = '/ui/lp-303-32-doka.svg'
const MORE_ICON = '/ui/lp-318-33-scroll-more.svg'
const OVERFLOW = { top: '-7%', left: '-12%', width: '124%', height: '124%' }   // DOKA SVG 그림자 여백(Figma inset)
const PEEK = 4   // 처음에는 문제 4개만 — 나머지는 More(213:28)로 펼친다

/** 들린 발음에서 목표와 다른 글자를 표시한다(최장 공통 부분열 밖의 글자 = 빨강, 333:65). */
function heardMarks(target, heard) {
  const a = [...(target || '')], b = [...(heard || '')]
  const dp = Array.from({ length: a.length + 1 }, () => new Array(b.length + 1).fill(0))
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1])
  }
  const keep = new Set()
  let i = 0, j = 0
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) { keep.add(j); i += 1; j += 1 } else if (dp[i + 1][j] >= dp[i][j + 1]) i += 1; else j += 1
  }
  return b.map((ch, k) => ({ ch, bad: !keep.has(k) && ch.trim() !== '' }))
}

function Metric({ label, value, cls }) {
  return (
    <div className="flex min-w-0 flex-1 flex-col items-center gap-1 whitespace-nowrap font-bold leading-figma">
      <p className="text-[12px] text-ink-faint">{label}</p>
      <p className={`text-[23px] tracking-[-0.46px] ${cls}`}>{value ?? '–'}</p>
    </div>
  )
}
const Divider = () => <span aria-hidden className="h-[38px] w-[1.5px] shrink-0 bg-line" />

/** 문제 한 줄(212:264) — 번호 · 목표 · 음소 칩 · 들림 · 점수. 독화는 음소 칩 대신 고른 답·정오. */
function DetailItem({ it, i, kind }) {
  const first = i === 0 ? '' : 'border-t-1.5 border-line'
  if (kind === 'speak') {
    const tone = scoreTone(it.score, 'accuracy')   // 문제 점수는 정답률 기준색(212:280 81=주황·58=빨강), 음소 칩은 음소 기준색
    return (
      <div className={`flex flex-wrap items-center gap-x-4 gap-y-2 py-4 leading-figma ${first}`}>
        <p className="w-5 shrink-0 text-[13px] font-bold text-ink-ghost">{i + 1}</p>
        <p className="w-[68px] shrink-0 truncate text-[17px] font-bold text-ink">{it.target}</p>
        {it.phones?.length > 0 && (
          <div className="order-last flex w-full flex-wrap gap-1.5 font-bold sm:order-none sm:w-[204px] sm:flex-nowrap sm:overflow-hidden">
            {it.phones.slice(0, 6).map((p, k) => {
              const v = Math.round((p.dgop ?? 0) * 100)
              return (
                <div key={k} className={`flex shrink-0 flex-col items-center gap-px rounded-lg border-1.5 px-2.5 py-1.5 ${scoreTone(v, 'phone').chip}`}>
                  <span className="text-[14px]">{p.label}</span>
                  <span className="text-[10px] opacity-80">{v}</span>
                </div>
              )
            })}
          </div>
        )}
        <div className="flex min-w-0 flex-1 items-center gap-[7px] whitespace-nowrap sm:pl-3.5">
          <span className="text-[12px] text-ink-muted">들림</span>
          <span className="truncate text-[15px] font-bold text-ink">
            {it.heard ? <>"{heardMarks(it.target, it.heard).map((m, k) => <span key={k} className={m.bad ? 'text-bad' : ''}>{m.ch}</span>)}"</> : '–'}
          </span>
        </div>
        <p className={`w-[52px] shrink-0 text-right text-[16px] font-bold ${tone.text}`}>{Math.round(it.score)}점</p>
      </div>
    )
  }
  if (kind === 'assessment') {
    const acc = Math.round((it.accuracy ?? 0) * 100)
    return (
      <div className={`flex items-center gap-4 py-4 leading-figma ${first}`}>
        <p className="w-5 shrink-0 text-[13px] font-bold text-ink-ghost">{i + 1}</p>
        <p className="flex-1 text-[15px] font-bold text-ink">{it.total}문항 중 {it.correct}문항 · Lv.{it.level}</p>
        <p className={`w-[52px] shrink-0 text-right text-[16px] font-bold ${scoreTone(acc, 'accuracy').text}`}>{acc}%</p>
      </div>
    )
  }
  // 독화(입모양·단어·문맥) — 고른 답과 정오, 문장 연습 — 내 답과 점수
  const sentence = kind === 'sentence'
  const ok = sentence ? scoreLevel(it.score, 'accuracy') : (it.correct ? 'good' : 'bad')
  return (
    <div className={`flex flex-wrap items-center gap-x-4 gap-y-1.5 py-4 leading-figma ${first}`}>
      <p className="w-5 shrink-0 text-[13px] font-bold text-ink-ghost">{i + 1}</p>
      <p className={`${sentence ? 'w-full sm:w-auto sm:flex-1' : 'w-[68px]'} min-w-0 shrink-0 truncate text-[17px] font-bold text-ink`}>{it.target}</p>
      <div className="flex min-w-0 flex-1 items-center gap-[7px] whitespace-nowrap sm:pl-3.5">
        <span className="text-[12px] text-ink-muted">{sentence ? '내 답' : '고른 답'}</span>
        <span className="truncate text-[15px] font-bold text-ink">{it.chosen || '–'}</span>
      </div>
      <p className={`w-[52px] shrink-0 text-right text-[16px] font-bold ${ok === 'good' ? 'text-good-text' : ok === 'warn' ? 'text-warn-text' : 'text-bad-text'}`}>
        {sentence ? `${Math.round(it.score)}점` : it.correct ? '정답' : '오답'}
      </p>
    </div>
  )
}

/**
 * 회차 상세 모달(212:190) — 히스토리 행 하나(현지 날짜 × 활동 종류 × 주제)의 문제별 기록.
 * 말하기는 요약(212:246: 소리·입모양·융합·불확실성) + 문제별 분석(음소 칩·들림·점수) + DOKA의 한마디(212:335).
 * 소리 = 채점 점수(음향), 입모양 = 웹캠 점수(웹캠을 켠 시도만, 채점에 섞지 않음), 융합 = 연구용 융합 기록만,
 * 불확실성 = D-GOP 불확실성.
 * 독화·문장·검사 행은 같은 틀에서 정답률 요약과 고른 답을 보여 준다(Figma에 따로 프레임이 없다).
 * 데이터: GET /api/analysis/activity-detail.
 */
function SessionDetail({ row, onClose, onGo }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(false)
  const [expanded, setExpanded] = useState(false)
  useEffect(() => {
    if (!row) return undefined
    let on = true
    setData(null); setErr(false); setExpanded(false)
    learningAPI.getActivityDetail(row.date, row.kind, row.topic || '')
      .then((d) => { if (on) setData(d) }).catch(() => { if (on) setErr(true) })
    return () => { on = false }
  }, [row])
  if (!row) return null
  const speak = row.kind === 'speak'
  const lesson = row.kind === 'sentence' ? (row.label || row.topic_label) : row.topic_label
  const title = speak ? `${lesson} 발음 연습` : lesson
  const acc = row.accuracy == null ? null : Math.round(Number(row.accuracy) * 100)
  const trackLabel = isReview(row) ? '복습' : speak ? '발화' : '독화'
  const subtitle = `${relDay(row.date)} · ${trackLabel} · ${row.kind === 'assessment' ? `${row.n}회` : `${row.n}문제`}${acc != null ? ` · 정답률 ${acc}%` : ''}`
  const sm = data?.summary || {}
  const items = data?.items || []
  const shown = expanded ? items : items.slice(0, PEEK)
  const to = isReview(row) ? '/review/mistakes' : row.route
  return (
    <Modal open={!!row} onClose={onClose} title={title} subtitle={subtitle} gap="gap-[18px]" maxW="max-w-[640px]">
      {err ? (
        <p className="py-8 text-center text-sm text-ink-muted">기록을 불러오지 못했어요.</p>
      ) : !data ? (
        <p role="status" className="py-8 text-center text-sm text-ink-muted">불러오는 중…</p>
      ) : (
        <>
          <div className="flex w-full items-center rounded-14 border-1.5 border-line bg-surface-muted py-4">
            {speak ? (
              <>
                <Metric label="소리 점수" value={sm.sound != null ? Math.round(sm.sound) : null} cls="text-primary-500" />
                <Divider />
                <Metric label="입모양 점수" value={sm.mouth != null ? Math.round(sm.mouth) : null} cls="text-sky-500" />
                <Divider />
                {/* 융합 점수는 연구용 융합을 켠 기록에만 있다(9/24부터 입모양은 소리와 따로 보임) */}
                {sm.fused != null && (
                  <>
                    <Metric label="융합 점수" value={Math.round(sm.fused)} cls="text-speak-dark" />
                    <Divider />
                  </>
                )}
                <Metric label="불확실성" value={sm.uncertainty != null ? `${Math.round(sm.uncertainty * 100)}%` : null} cls="text-warn-text" />
              </>
            ) : (
              <>
                <Metric label="문제" value={sm.n != null ? `${sm.n}` : null} cls="text-ink" />
                <Divider />
                <Metric label={row.kind === 'sentence' ? '평균 점수' : '정답률'}
                  value={row.kind === 'sentence' ? (sm.score != null ? Math.round(sm.score) : null) : (sm.accuracy != null ? `${Math.round(sm.accuracy * 100)}%` : null)}
                  cls="text-primary-500" />
              </>
            )}
          </div>
          <p className="text-[14px] font-bold leading-figma text-ink">문제별 분석</p>
          <div className="flex w-full flex-col">
            {items.length === 0
              ? <p className="py-6 text-center text-sm text-ink-muted">이 회차의 문제 기록이 없어요.</p>
              : shown.map((it, i) => <DetailItem key={i} it={it} i={i} kind={row.kind} />)}
            {!expanded && items.length > PEEK && (
              <div className="relative h-14 w-full bg-gradient-to-b from-white/0 to-white to-[55%]">
                <button type="button" onClick={() => setExpanded(true)} aria-label={`나머지 ${items.length - PEEK}문제 더 보기`}
                  className="absolute left-1/2 top-3 size-9 -translate-x-1/2">
                  <img src={MORE_ICON} alt="" className="absolute max-w-none" style={{ top: '-11.11%', left: '-19.44%', width: '138.88%', height: '138.89%' }} />
                </button>
              </div>
            )}
          </div>
          {data.coaching && (
            <div className="flex items-center gap-2.5 rounded-14 bg-speak-tint px-4 py-3.5">
              <span className="relative size-[34px] shrink-0">
                <img src={DOKA_ICON} alt="" className="absolute max-w-none" style={OVERFLOW} />
              </span>
              <p className="shrink-0 whitespace-nowrap text-[14px] font-bold leading-figma text-speak-dark">DOKA의 한마디</p>
              <span aria-hidden className="h-4 w-[1.5px] shrink-0 rounded-[1px] bg-speak-dark/30" />
              <p className="min-w-0 flex-1 text-[13.5px] leading-[1.65] text-speak-dark">{data.coaching}</p>
            </div>
          )}
          {to && (
            <button type="button" onClick={() => onGo(to)} className="btn-secondary w-full py-3 text-[15px]">이 학습 다시 하기</button>
          )}
        </>
      )}
    </Modal>
  )
}

/** 전체 통계(210:189) — 3지표 요약행(214:25) + 트랙별(독화·발화) 진행 카드(210:276).
 *  값은 /api/analysis/overview. 회차는 활동 시각을 30분 공백으로 나눈 추정 회차, 푼 문제는 채점된 시행 수,
 *  단계 진도는 숙달한 단계 수다. 불러오기 전·실패 시엔 '–'. */
function FullStats({ ov, onGo }) {
  const num = (v) => (typeof v === 'number' ? v.toLocaleString() : '–')
  const badgeCount = ov ? mergeBadges(ov.badges).filter((b) => b.earned).length : null
  const metrics = [
    { label: '총 학습 회차', value: num(ov?.sessions), unit: '회', color: 'text-primary-500' },
    { label: '푼 문제', value: num(ov?.questions), unit: '개', color: 'text-primary-500' },
    { label: '획득 배지', value: num(badgeCount), unit: '개', color: 'text-speak' },
  ]
  const pct = (a) => (a == null ? '–' : Math.round(a * 100))
  const tr = ov?.tracks || {}
  const tracks = [
    { name: '독화', acc: pct(tr.read?.accuracy), done: tr.read?.done ?? 0, total: tr.read?.total || 5, card: 'bg-primary-100 text-primary-700', fill: 'bg-primary-500' },
    { name: '발화', acc: pct(tr.speak?.accuracy), done: tr.speak?.done ?? 0, total: tr.speak?.total || 6, card: 'bg-speak-tint text-speak-dark', fill: 'bg-speak' },
  ]
  return (
    <div className="flex flex-col gap-[22px]">
      <div className="flex items-center">
        {metrics.map((m, i) => (
          <div key={m.label} className="flex flex-1 items-center">
            {i > 0 && <span className="h-12 w-[1.5px] shrink-0 bg-line" />}
            <div className="flex flex-1 flex-col items-center gap-1.5 py-2.5 font-bold leading-figma">
              <span className="text-[12.5px] text-ink-faint">{m.label}</span>
              <span className={`flex items-baseline gap-[3px] ${m.color}`}>
                <span className="text-[28px] tracking-[-0.7px]">{m.value}</span>
                <span className="text-[14px] opacity-70">{m.unit}</span>
              </span>
            </div>
          </div>
        ))}
      </div>
      <div className="flex flex-col gap-3.5 sm:flex-row">
        {tracks.map((t) => (
          <div key={t.name} className={`flex flex-1 flex-col gap-2.5 rounded-16 p-[18px] leading-figma ${t.card}`}>
            <div className="flex items-center justify-between font-bold">
              <span className="text-[16px]">{t.name}</span>
              <span className="text-[13px] opacity-80">{t.acc === '–' ? '정확도 –' : `정확도 ${t.acc}%`}</span>
            </div>
            <span className="text-[13px] opacity-75">{t.done} / {t.total}단계 완료</span>
            <div className="h-2.5 overflow-hidden rounded-full bg-white/60">
              <div className={`h-full rounded-full ${t.fill}`} style={{ width: `${(t.done / t.total) * 100}%` }} />
            </div>
          </div>
        ))}
      </div>
      {/* 상세 화면 진입 — Figma 210:23 밖의 추가 링크. 약점 입모양·혼동 지도(/analysis/visemes)와
          학습 효과 리포트(/analysis/eval, 사전·사후 검사 시작 포함)는 다른 진입점이 없어 여기 둔다. */}
      {onGo && (
        <div className="flex flex-col gap-2 border-t-1.5 border-line pt-4 sm:flex-row">
          <button type="button" onClick={() => onGo('/analysis/visemes')}
            className="flex flex-1 items-center justify-between rounded-[12px] px-3 py-2.5 text-[14px] font-bold text-ink hover:bg-surface-sunken">
            약점 입모양·혼동 지도 <img src="/ui/review-arrow.svg" alt="" className="max-w-none" />
          </button>
          <button type="button" onClick={() => onGo('/analysis/eval')}
            className="flex flex-1 items-center justify-between rounded-[12px] px-3 py-2.5 text-[14px] font-bold text-ink hover:bg-surface-sunken">
            학습 효과 리포트(사전·사후 검사) <img src="/ui/review-arrow.svg" alt="" className="max-w-none" />
          </button>
        </div>
      )}
    </div>
  )
}
