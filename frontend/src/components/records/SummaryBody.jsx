import usePageLoad from '../../hooks/usePageLoad'
import { dayCounts, historyRows, calSubtitle, ActivityCalendar, HistoryList, SessionDetail, FullStats } from './RecordDetails'
import { RailLevelCard, RailWeekCard } from './ProgressCards'
import Badges from '../today/Badges'
import TrackSummary from './TrackSummary'
import ErrorScreen from '../../components/ErrorScreen'
import LoadingScreen from '../../components/LoadingScreen'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Modal from '../../components/Modal'
import { learningAPI, listenAPI } from '../../api'
import { listenOverview } from '../../lib/listenFlow'
import { fmtDb } from '../../lib/listenView'
import { speakTrendView } from '../../lib/speakTrend'

/**
 * 분석 탭 (Figma 104:15 · 모바일 240:34) — 워터마크 스탯 3칸 + 학습시간 막대차트 + 정확도 선차트 + 상세 링크.
 * 차트는 데이터 배열로 직접 렌더(막대=CSS 높이, 선=인라인 SVG + HTML 점). 상세는 모달로 연다(§4-07).
 * 요약·주간 추이·전체 통계는 GET /api/analysis/overview(backend/analytics.py)의 실측값이다.
 * 기록이 없으면 0·'–'로 보이고, 표본값으로 채우지 않는다.
 * 활동 캘린더·회차 히스토리는 GET /api/calendar/activities(날짜×주제, 독화·발화·검사 모두)로 그린다.
 * 회차 히스토리 행을 누르면 그 학습 화면으로 간다 — 회차 상세 모달(212:24)은 문항별 기록 API가 없어 아직 없다.
 * 크기는 lg 미만이 모바일 프레임 값, lg 이상이 데스크톱 프레임 값이다.
 * 10월: 차트 아래 '소리 듣기' 칸(최근 역치 · 이번 주 듣기 분 · 소리 구별 정답률)과 결과 화면(/analysis/listening) 진입을 더했다.
 * 값은 overview의 listen 칸을 쓰고, 그 칸이 아직 없으면 /api/listen/summary에서 계산한다(lib/listenFlow.listenOverview).
 * 듣기 기록이 하나도 없으면 칸을 그리지 않는다(독화·발화만 하는 학습자 화면을 늘리지 않게).
 * 10/9: 말하기 문장 점수 주 평균 줄을 더했고, 10/28에 '문장 점수 주 평균 변화(참고, 기계 전사 기준)' 카드로 바꿨다. 값은 overview의 speak_trend(lib/speakTrend), 합격·숙달에는 쓰지 않는다.
 * 10/15: 소리 듣기 칸 아래 '함께 하면 좋은 연습'(TrackLinks, 소리 듣기 ↔ 독화)을 더했다.
 */

/** 스탯 한 칸 — 라벨 위 · 값 아래(+ 데스크톱만 증감 줄), 왼쪽 정렬. 11/03부터 세 칸을 한 카드에 세로 줄로 나눠 담는다. */
function StatCard({ label, value, delta }) {
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-1 px-3.5 py-3.5 leading-figma lg:gap-1.5 lg:px-6 lg:py-5 lg:[@media(max-height:860px)]:py-4">
      <span className="text-[12px] font-medium text-ink-muted lg:text-[13px]">{label}</span>
      <span className="break-keep text-[19px] font-bold tabular-nums tracking-[-0.38px] text-ink lg:text-[26px] lg:tracking-[-0.52px]">{value}</span>
      {delta && <span className="hidden text-[12px] font-medium text-ink-muted lg:block">{delta}</span>}
    </div>
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

/** 소리 듣기 칸: 최근 역치 · 이번 주 듣기 · 소리 구별 정답률 + 결과 보기. 기록이 없으면 그리지 않는다. */
function ListenSummary({ ov, onOpen }) {
  const [summary, setSummary] = useState(null)
  // overview에 listen 칸이 있으면(시작 안 했으면 null) 그것만 쓴다. 칸이 아예 없는 예전 서버일 때만 결과 요약에서 계산한다
  const needSummary = !!ov && !('listen' in ov)
  useEffect(() => {
    if (!needSummary) return undefined
    let on = true
    listenAPI.summary().then((d) => { if (on) setSummary(d) }).catch(() => {})
    return () => { on = false }
  }, [needSummary])
  const l = listenOverview(ov, summary)
  if (!l.has) return null
  const cells = [
    { label: '최근 역치', value: fmtDb(l.srt), note: '낮을수록 시끄러운 곳에서 잘 들어요' },
    { label: '이번 주 듣기', value: l.weekMinutes == null ? '–' : `${Math.round(l.weekMinutes)}분`, note: '권장 하루 15분, 주 5일' },
    { label: '소리 구별 정답률', value: l.axAccuracy == null ? '–' : `${Math.round(l.axAccuracy * 100)}%`, note: '같다·다르다 문제' },
  ]
  return (
    <section data-track="listen" className="flex w-full flex-col gap-3.5 rounded-16 border border-line bg-white p-[18px] lg:gap-[18px] lg:p-[22px] lg:[@media(max-height:860px)]:gap-3.5 lg:[@media(max-height:860px)]:p-[18px]">
      <div className="flex items-center justify-between font-bold leading-figma">
        <p className="text-[16px] text-ink lg:text-[17px]">소리 듣기</p>
        <button type="button" onClick={onOpen} className="flex min-h-[32px] items-center gap-2 text-[12px] text-listen-dark hover:underline lg:text-[13px]">
          결과 보기 <img src="/ui/review-arrow.svg" alt="" aria-hidden className="max-w-none" />
        </button>
      </div>
      <div className="grid grid-cols-3 gap-2 lg:gap-3">
        {cells.map((c) => (
          <div key={c.label} className="flex min-w-0 flex-col gap-1 rounded-14 bg-surface-sunken px-3 py-3 leading-figma lg:gap-1.5 lg:px-4">
            <span className="break-keep text-[11.5px] font-bold text-ink-faint lg:text-[13px] lg:text-ink-soft">{c.label}</span>
            <span className="text-[18px] font-bold tracking-[-0.36px] text-listen-dark lg:text-[22px]">{c.value}</span>
            <span className="hidden break-keep text-[12px] text-ink-faint lg:block">{c.note}</span>
          </div>
        ))}
      </div>
    </section>
  )
}

/**
 * 함께 하면 좋은 연습(트랙 잇기, GET /api/listen/links, docs/listen-cross-track-2026-10.md). 소리 듣기에서 자주 헷갈린 소리 짝은 입모양이 다르면
 * 입모양 보기와 소리 짝 연습을, 같으면 소리 짝 연습을 권한다. 독화에서 입모양이 같아 헷갈린 짝은 소리 짝 연습을 권한다.
 * 소리 듣기를 시작한 학습자에게만 그리고(listen_started), 권할 것이 없으면 그리지 않는다.
 */
export function TrackLinks({ enabled, navigate }) {
  const [d, setD] = useState(null)
  useEffect(() => {
    if (!enabled) return undefined
    let on = true
    listenAPI.links().then((x) => { if (on) setD(x) }).catch(() => {})
    return () => { on = false }
  }, [enabled])
  const groups = [
    { key: 'listen', title: '소리 듣기에서 헷갈린 소리', items: d?.from_listen || [] },
    { key: 'read', title: '입모양 읽기에서 헷갈린 입모양', items: d?.from_lipread || [] },
  ].filter((g) => g.items.length)
  if (!enabled || !d?.listen_started || !groups.length) return null
  return (
    <section data-track="listen" aria-label="함께 하면 좋은 연습" className="flex w-full flex-col gap-3.5 rounded-16 border border-line bg-white p-[18px] lg:gap-[18px] lg:p-[22px]">
      <div className="flex flex-col gap-1 leading-figma">
        <p className="text-[16px] font-bold text-ink lg:text-[17px]">함께 하면 좋은 연습</p>
        <p className="break-keep text-[12px] text-ink-muted lg:text-[13px]">입모양으로 알기 어려운 소리는 듣기로 연습해요. 듣기로 알기 어려운 소리는 입모양으로 연습해요.</p>
      </div>
      {groups.map((g) => (
        <div key={g.key} className="flex flex-col gap-2">
          <p className="text-[13px] font-bold text-ink-muted">{g.title}</p>
          {g.items.map((r) => (
            <div key={`${g.key}${r.slot}${r.pair.join('')}`} className="flex flex-col gap-2.5 rounded-14 bg-surface-sunken p-4">
              <p className="break-keep text-[14px] leading-[1.6] text-ink">{r.text}</p>
              <div className="flex flex-wrap gap-2">
                {(r.routes || []).map((x) => (
                  <button key={x.to} type="button" onClick={() => navigate(x.to)}
                    className={`btn-secondary min-h-[44px] px-3.5 py-2 text-[13px] ${x.track === 'perception' ? 'text-primary-700' : 'text-listen-dark'}`}>{x.label}</button>
                ))}
              </div>
            </div>
          ))}
        </div>
      ))}
    </section>
  )
}

/** 차트 카드(197:21 / 240:133) — 머리(제목·'최근 7주') + 플롯. tag는 제목 옆 작은 글(문장 점수 추세 카드의 '참고, 기계 전사 기준'). */
function ChartCard({ title, tag = null, track = null, children }) {
  return (
    <section data-track={track || undefined} className="flex w-full flex-col gap-3.5 rounded-16 border border-line bg-white p-[18px] lg:gap-[18px] lg:p-[22px] lg:[@media(max-height:860px)]:gap-3.5 lg:[@media(max-height:860px)]:p-[18px]">
      <div className="flex items-center justify-between gap-3 font-bold leading-figma">
        <p className="flex min-w-0 flex-wrap items-baseline gap-x-2 text-[16px] text-ink lg:text-[17px]">
          {title}{tag && <span className="text-[12px] font-bold text-track-dark lg:text-[13px]">{tag}</span>}
        </p>
        <span className="shrink-0 text-[12px] text-ink-muted lg:text-[13px]">최근 7주</span>
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

/** 학습시간 추이 막대. 데스크톱 150px 플롯(막대 46 · 위 8/아래 2 라운드 · 값은 막대 아래), 모바일 96px(막대 26 · 값·그리드 없음).
 *  모바일 플롯은 Figma 110px에서 줄였다(390×844에서 상세 링크까지 한 화면에 들어오게). */
function BarChart({ weeks }) {
  const max = Math.max(1, ...weeks.map((w) => w.minutes))
  // 막대 아래 값: 1시간 미만은 '27분', 넘으면 '1시간 5분'(예전 '0h 27m' 영어 표기를 바꿨다)
  const fmt = (m) => (m < 60 ? `${m}분` : `${Math.floor(m / 60)}시간${m % 60 ? ` ${m % 60}분` : ''}`)
  return (
    <div className="relative h-[96px] w-full lg:h-[150px]">
      <GridLines />
      <div className="absolute inset-x-0 bottom-4 top-0 flex items-end lg:bottom-[22px]">
        {weeks.map((w, i) => {
          const last = i === weeks.length - 1
          return (
            <div key={i} className="flex flex-1 justify-center">
              <div className={`h-[calc(var(--r)*66px)] w-[26px] rounded-b-[2px] rounded-t-[6px] lg:h-[calc(var(--r)*114px)] lg:w-[46px] lg:rounded-t-[8px] ${last ? 'bg-primary-500' : 'bg-primary-300'}`}
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
 * 가로: 첫 점 중심 10px(모바일 8) ~ 마지막 점 중심 오른쪽에서 6px(4). 세로: 최저값 123px(모바일 76) ~ 최고값 30px(28), 모바일 플롯 96px.
 * 선은 preserveAspectRatio="none" SVG(가로만 늘어남)라 점은 찌그러지지 않게 HTML로 따로 찍는다.
 * 채점 기록이 없는 주는 점·수치를 두지 않고 선을 끊는다.
 */
function LineChart({ weeks, empty = '아직 채점된 기록이 없어요', tone = 'accuracy' }) {
  // tone 'track'은 감싼 칸의 트랙 색(말하기 분홍)으로 그린다. 기본은 정확도 에메랄드
  const c = tone === 'track'
    ? { stroke: 'stroke-track', dot: 'bg-track', last: 'text-track-dark', label: 'text-chart-label' }
    : { stroke: 'stroke-chart-accuracy', dot: 'bg-chart-accuracy', last: 'text-stat-accuracy', label: 'text-chart-label' }
  const vals = weeks.map((w) => (w.accuracy == null ? null : Math.round(w.accuracy * 100)))
  const known = vals.filter((v) => v != null)
  if (!known.length) {
    return <p className="flex h-[96px] items-center justify-center break-keep px-4 text-center text-[14px] text-ink-muted lg:h-[150px]">{empty}</p>
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
    <div className="relative h-[96px] w-full [--x0:8px] [--xs:12px] [--yb:76px] [--yt:28px] lg:h-[150px] lg:[--x0:10px] lg:[--xs:16px] lg:[--yb:123px] lg:[--yt:30px]">
      <GridLines />
      {/* SVG는 대체 요소라 left/right만으로 늘어나지 않는다 — 폭을 점 중심 사이 거리로 직접 준다 */}
      <svg aria-hidden viewBox={`0 0 ${Math.max(1, n - 1)} 96`} preserveAspectRatio="none" className="absolute left-2 top-0 h-[96px] w-[calc(100%-12px)] overflow-visible lg:hidden">
        <path d={path(28, 76)} fill="none" className={c.stroke} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
      </svg>
      <svg aria-hidden viewBox={`0 0 ${Math.max(1, n - 1)} 150`} preserveAspectRatio="none" className="absolute left-2.5 top-0 hidden h-[150px] w-[calc(100%-16px)] overflow-visible lg:block">
        <path d={path(30, 123)} fill="none" className={c.stroke} strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
      </svg>
      {vals.map((v, i) => v != null && (
        <span key={`p${i}`} aria-hidden
          className={`absolute -translate-x-1/2 -translate-y-1/2 rounded-full border-white ${c.dot} ${i === lastIdx ? 'size-3 border-[2.5px] lg:size-4 lg:border-[3px]' : 'size-2 border-[2.5px] lg:size-[11px] lg:border-[3px]'}`}
          style={{ left: posX(i), top: posY(v) }} />
      ))}
      {vals.map((v, i) => v != null && (
        <span key={`v${i}`}
          className={`absolute hidden -translate-x-1/2 font-bold leading-figma lg:block ${i === lastIdx ? `text-[13px] ${c.last}` : `text-[11.5px] ${c.label}`}`}
          style={{ left: posX(i), top: posY(v, i === lastIdx ? 31.2 : 26.67) }}>
          {v}
        </span>
      ))}
    </div>
  )
}

/**
 * 문장 점수 주 평균 변화 카드(10/9 줄 → 10/28 카드, S20 채택안). 이미 있는 말하기 문장 점수의 주 평균만 보이고 새 지수는 없다.
 * 합격·숙달에는 쓰지 않고, 문장이 5개보다 적은 주는 점을 두지 않는다. 평균이 있는 주가 2주보다 적으면 짧은 빈 상태만 보인다. 안내줄은 두지 않는다.
 */
export function SpeakTrend({ ov }) {
  const v = speakTrendView(ov)
  if (!v.show) return null
  return (
    <ChartCard title="문장 점수 주 평균 변화" tag="참고, 기계 전사 기준" track="speak">
      <LineChart weeks={v.enough ? v.weeks : []} tone="track" empty="아직 변화를 보일 기록이 없어요" />
    </ChartCard>
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

/** 상세 링크(198:29 / 240:159) — 1px 테두리 카드형 버튼. */
function DetailLink({ label, onClick }) {
  return (
    <button type="button" onClick={onClick}
      className="flex flex-1 items-center justify-between rounded-14 border border-line bg-white py-3 pl-[18px] pr-4 text-[14.5px] font-semibold leading-figma text-ink transition-colors hover:bg-surface-muted lg:rounded-16 lg:py-[18px] lg:[@media(max-height:860px)]:py-[15px] lg:pl-5 lg:pr-[18px] lg:text-[15px]">
      {label}
      <Chevron />
    </button>
  )
}

export default function SummaryBody({ track = 'all' }) {
  const navigate = useNavigate()
  const [modal, setModal] = useState(null)   // 'calendar' | 'history' | 'stats'
  const [detailRow, setDetailRow] = useState(null)   // 회차 상세(212:24)로 연 히스토리 행
  const [cal, setCal] = useState(null)
  const [acts, setActs] = useState(null)   // 날짜별 학습 내용(활동 캘린더·회차 히스토리)
  const [ov, setOv] = useState(null)       // 요약·주별 추이·배지(/api/analysis/overview)
  const { loadState, retry: retryLoad } = usePageLoad(() => Promise.all([
      learningAPI.getCalendarActivities().then((activities) => ({ activities }))
        .catch(() => learningAPI.getCalendar().then((calendar) => ({ calendar }))),
      learningAPI.getAnalysisOverview(),
    ]), ([data, overview]) => {
      setActs(data.activities || null)
      setCal(data.calendar || null)
      setOv(overview)
  })

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

  if (loadState !== 'ready') return (
    <>
      {loadState === 'error'
        ? <ErrorScreen onRetry={retryLoad} onHome={() => navigate('/learn/path')} />
        : <LoadingScreen variant="inline" />}
    </>
  )

  if (track !== 'all') return <TrackSummary track={track} overview={ov} />

  return (
    <>
      <section className="flex w-full divide-x divide-line rounded-16 border border-line bg-white">
        <StatCard label="총 학습" value={ov ? fmtDur(ov.total_minutes) : '–'} delta={minDelta} />
        <StatCard label="평균 정답률"
          value={ov?.accuracy != null ? `${Math.round(ov.accuracy * 100)}%` : '–'} delta={accDelta} />
        <StatCard label="연속 학습" value={`${ov?.streak_current ?? 0}일`}
          delta={ov ? `최고 기록 ${ov.streak_best}일` : null} />
      </section>

      <Badges data={ov?.badges} />
      <div className="records-charts contents">
      <ChartCard title="학습 시간 변화"><BarChart weeks={weeks} /></ChartCard>
      <ChartCard title="정답률 변화"><LineChart weeks={weeks} /></ChartCard>
      </div>
      <SpeakTrend ov={ov} />
      <ListenSummary ov={ov} onOpen={() => navigate('/records?track=listen')} />
      <TrackLinks enabled={!!ov?.listen} navigate={navigate} />

      <div className="flex w-full flex-col gap-[9px] lg:flex-row lg:gap-3">
        <DetailLink label="활동 캘린더" onClick={() => setModal('calendar')} />
        <DetailLink label="학습 내역" onClick={() => setModal('history')} />
        <DetailLink label="전체 통계" onClick={() => setModal('stats')} />
      </div>

      <RailLevelCard /><RailWeekCard activeDays={new Set(Object.keys(acts || cal || {}))} />
      <Modal open={modal === 'calendar'} onClose={() => setModal(null)} title="활동 캘린더"
        subtitle={calSubtitle(counts, ov?.session_days)} maxW="max-w-[900px]">
        <ActivityCalendar counts={counts} />
      </Modal>
      <Modal open={modal === 'history'} onClose={() => setModal(null)} title="학습 내역"
        subtitle={`최근 학습 기록 · 총 ${(ov?.sessions ?? history.length).toLocaleString()}회`} maxW="max-w-[820px]">
        <HistoryList rows={history} onOpen={(r) => { setModal(null); setDetailRow(r) }} />
      </Modal>
      <SessionDetail row={detailRow} onClose={() => setDetailRow(null)}
        onGo={(to) => { setDetailRow(null); navigate(to) }} />
      <Modal open={modal === 'stats'} onClose={() => setModal(null)} title="전체 통계" maxW="max-w-[880px]">
        <FullStats ov={ov} onGo={(to) => { setModal(null); navigate(to) }} />
      </Modal>
    </>
  )
}

/* ── 날짜 유틸 ── */
