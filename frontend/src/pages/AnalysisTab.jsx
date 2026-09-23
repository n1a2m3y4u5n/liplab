import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'
import Modal from '../components/Modal'
import useStore from '../store/useStore'
import { learningAPI } from '../api'

/**
 * 분석 탭 (Figma 리디자인) — 요약 통계 + 학습시간 막대차트 + 정확도 선차트 + 상세 링크.
 * 차트는 데이터 배열로 직접 렌더(막대=CSS 높이, 선=인라인 SVG). 상세는 모달로 연다.
 * 주간 추이는 요약용 표본이며, 상세 수치는 '전체 통계'(FullStats)에서 확인한다.
 * 회차 히스토리는 GET /api/calendar/activities(날짜×주제)로 그리고, 행을 누르면 그 학습 화면으로 간다.
 */
function StatCol({ icon, label, value, delta, color }) {
  return (
    <div className="flex flex-1 flex-col items-center gap-[7px] py-1.5">
      <div className="flex items-center gap-1.5">
        <img src={icon} alt="" className="h-[18px] w-[18px]" />
        <span className="text-[13px] font-bold text-[#7a7a8c]">{label}</span>
      </div>
      <span className="text-[27px] font-bold tracking-[-0.675px]" style={{ color }}>{value}</span>
      {delta && <span className="text-[12px] font-bold text-[#8a8a9b]">{delta}</span>}
    </div>
  )
}

const HOURS = [
  { w: '1주', m: 100 }, { w: '2주', m: 130 }, { w: '3주', m: 110 }, { w: '4주', m: 160 },
  { w: '5주', m: 140 }, { w: '6주', m: 190 }, { w: '7주', m: 230 },
]
const ACC = [46, 52, 58, 55, 66, 72, 78]

/** 학습시간 추이 막대 — Figma: 150px 플롯, 그리드 3줄, 막대(상단 8px·하단 2px 라운드), 값은 막대 아래. */
function BarChart() {
  const max = Math.max(...HOURS.map((h) => h.m))
  const fmt = (m) => `${Math.floor(m / 60)}h ${m % 60}m`
  return (
    <div className="relative h-[150px] w-full">
      {[38, 75, 113].map((t) => (
        <div key={t} className="absolute left-0 right-0 h-px bg-[#ededf3]" style={{ top: `${t}px` }} />
      ))}
      <div className="absolute inset-x-0 bottom-[22px] top-0 flex items-end gap-2">
        {HOURS.map((h, i) => {
          const last = i === HOURS.length - 1
          return (
            <div key={h.w} className="flex flex-1 justify-center">
              <div className={`w-[46%] rounded-b-[2px] rounded-t-[8px] ${last ? 'bg-primary-500' : 'bg-primary-300'}`}
                style={{ height: `${(h.m / max) * 114}px` }} />
            </div>
          )
        })}
      </div>
      <div className="absolute inset-x-0 bottom-0 flex h-[18px] items-center gap-2">
        {HOURS.map((h, i) => {
          const last = i === HOURS.length - 1
          return (
            <span key={h.w} className={`flex-1 text-center font-bold ${last ? 'text-[11.5px] text-primary-700' : 'text-[10.5px] text-[#a8a8b8]'}`}>
              {fmt(h.m)}
            </span>
          )
        })}
      </div>
    </div>
  )
}

/** 정확도 추이 선 — Figma: emerald(#10b981) 라인, 각 포인트 emerald 채움+흰 테두리, 마지막 포인트 강조. */
function LineChart() {
  const W = 700, H = 130, pad = 8
  const min = 40, max = 82
  const pts = ACC.map((v, i) => {
    const x = pad + (i * (W - pad * 2)) / (ACC.length - 1)
    const y = pad + (1 - (v - min) / (max - min)) * (H - pad * 2)
    return [x, y]
  })
  const d = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ')
  return (
    <div className="relative w-full">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-[150px] w-full" preserveAspectRatio="none">
        {[0.25, 0.5, 0.75].map((g) => <line key={g} x1="0" x2={W} y1={H * g} y2={H * g} stroke="#ededf3" strokeWidth="1" />)}
        <path d={d} fill="none" stroke="#10b981" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
        {pts.map((p, i) => (
          <circle key={i} cx={p[0]} cy={p[1]} r={i === pts.length - 1 ? 6 : 4}
            fill="#10b981" stroke="#fff" strokeWidth="2.5" />
        ))}
      </svg>
      <div className="mt-1 flex justify-between px-1 text-[11.5px] font-bold text-[#7a9a8c]">
        {ACC.map((v, i) => <span key={i} className={i === ACC.length - 1 ? 'text-[13px] text-emerald-700' : ''}>{v}</span>)}
      </div>
    </div>
  )
}

/** 상세 링크 — Figma: 3D 하단테두리(2/2/2/5) 카드형 버튼. */
function DetailLink({ label, onClick }) {
  return (
    <button type="button" onClick={onClick}
      className="flex flex-1 items-center justify-between rounded-[16px] border-2 border-b-[5px] border-line bg-white py-[18px] pl-5 pr-[18px] text-[15px] font-bold text-ink transition-all active:translate-y-[1px] active:border-b-2">
      {label}
      <img src="/ui/menu-arrow.svg" alt="" className="h-3.5 w-[7px]" />
    </button>
  )
}

export default function AnalysisTab() {
  const user = useStore((s) => s.user)
  const statistics = useStore((s) => s.statistics)
  const streak = Math.max(0, user?.streak_count || 7)
  const navigate = useNavigate()
  const [modal, setModal] = useState(null)   // 'calendar' | 'history' | 'stats'
  const [cal, setCal] = useState(null)
  const [acts, setActs] = useState(null)   // 날짜별 학습 내용(회차 히스토리)
  useEffect(() => {
    learningAPI.getCalendar().then(setCal).catch(() => setCal({}))
    learningAPI.getCalendarActivities().then(setActs).catch(() => setActs({}))
  }, [])

  return (
    <AppShell active="analysis" title="분석" description="얼마나 늘었는지 기록으로 확인해보세요.">
      <section className="flex w-full items-center py-2">
        <StatCol icon="/ui/stat-clock.svg" label="총 학습" value="18시간" delta="지난주 +2시간" color="#5f3ab8" />
        <span className="h-[58px] w-[1.5px] bg-line" />
        <StatCol icon="/ui/stat-percent.svg" label="평균 정확도" value="78%" delta="지난주 +6%p" color="#047857" />
        <span className="h-[58px] w-[1.5px] bg-line" />
        <StatCol icon="/ui/stat-flame.svg" label="연속 학습" value={`${streak}일`} delta="최고 기록 12일" color="#b45309" />
      </section>

      <section className="card-flat w-full !p-[22px]">
        <div className="flex items-center justify-between">
          <p className="text-[17px] font-bold text-ink">학습시간 추이</p>
          <span className="text-[13px] text-ink-muted">최근 7주</span>
        </div>
        <div className="mt-[18px]"><BarChart /></div>
      </section>

      <section className="card-flat w-full !p-[22px]">
        <div className="flex items-center justify-between">
          <p className="text-[17px] font-bold text-ink">정확도 추이</p>
          <span className="text-[13px] text-ink-muted">최근 7주</span>
        </div>
        <div className="mt-[18px]"><LineChart /></div>
      </section>

      <div className="flex w-full flex-col gap-3 sm:flex-row">
        <DetailLink label="활동 캘린더" onClick={() => setModal('calendar')} />
        <DetailLink label="회차 히스토리" onClick={() => setModal('history')} />
        <DetailLink label="전체 통계" onClick={() => setModal('stats')} />
      </div>

      <Modal open={modal === 'calendar'} onClose={() => setModal(null)} title="활동 캘린더"
        subtitle={calSubtitle(cal)} maxW="max-w-3xl">
        <ActivityCalendar cal={cal} />
      </Modal>
      <Modal open={modal === 'history'} onClose={() => setModal(null)} title="회차 히스토리"
        subtitle={historySubtitle(cal, acts)} maxW="max-w-2xl">
        <HistoryList cal={cal} acts={acts} onGo={(to) => { setModal(null); navigate(to) }} />
      </Modal>
      <Modal open={modal === 'stats'} onClose={() => setModal(null)} title="전체 통계"
        subtitle="가입 후 누적 기록" maxW="max-w-2xl">
        <FullStats statistics={statistics} streak={streak} />
      </Modal>
    </AppShell>
  )
}

/* ── 캘린더 데이터/레벨 ── */
const CAL_WEEKS = 20
const CAL_LEVELS = ['#ededf3', '#ddd3f7', '#b49bec', '#8b5cf6', '#5f3ab8']
const calLevel = (c) => (c <= 0 ? 0 : c === 1 ? 1 : c === 2 ? 2 : c === 3 ? 3 : 4)

function buildCalDays(cal) {
  const days = []
  const today = new Date()
  const start = new Date(today); start.setDate(start.getDate() - (CAL_WEEKS * 7 - 1))
  for (let d = new Date(start); d <= today; d.setDate(d.getDate() + 1)) {
    const key = d.toISOString().slice(0, 10)
    days.push({ key, count: (cal && cal[key]) || 0 })
  }
  return days
}
function calSubtitle(cal) {
  const days = buildCalDays(cal)
  const total = days.filter((d) => d.count > 0).length
  let best = 0, run = 0
  for (const d of days) { if (d.count > 0) { run += 1; best = Math.max(best, run) } else run = 0 }
  return `최근 ${CAL_WEEKS}주 · 총 ${total}회 학습 · 최장 연속 ${best}일`
}
function historySubtitle(cal, acts) {
  return `최근 학습 기록 · 총 ${historyDates(cal, acts).length}일`
}

/** 활동 캘린더 — Figma 5단계 히트맵(요일×주). 요일 라벨(월·수·금·일)·주 라벨·범례. */
function ActivityCalendar({ cal }) {
  const days = buildCalDays(cal)
  const cols = []
  for (let i = 0; i < days.length; i += 7) cols.push(days.slice(i, i + 7))
  const dayLabels = ['월', '', '수', '', '금', '', '일']
  return (
    <div>
      <div className="overflow-x-auto pb-1">
        <div className="flex gap-[6px]" style={{ minWidth: 'max-content' }}>
          <div className="flex flex-col gap-[6px] pr-1 pt-[18px]">
            {dayLabels.map((d, i) => (
              <span key={i} className="flex h-[26px] items-center text-[11px] text-[#a8a8b8]">{d}</span>
            ))}
          </div>
          {cols.map((week, i) => (
            <div key={i} className="flex flex-col gap-[6px]">
              <span className="h-[14px] text-[11px] text-[#a8a8b8]">{i % 4 === 0 ? `${i + 1}주` : ''}</span>
              {week.map((d) => (
                <span key={d.key} title={`${d.key} · ${d.count}회`}
                  className="h-[26px] w-[26px] rounded-[7px]" style={{ backgroundColor: CAL_LEVELS[calLevel(d.count)] }} />
              ))}
            </div>
          ))}
        </div>
      </div>
      <div className="mt-3 flex items-center justify-end gap-[6px] text-[11.5px] text-[#a8a8b8]">
        적음
        {CAL_LEVELS.map((c) => <span key={c} className="h-4 w-4 rounded-[5px]" style={{ backgroundColor: c }} />)}
        많음
      </div>
    </div>
  )
}

/* ── 회차 히스토리 데이터 ── */
/** 히스토리에 올릴 날짜(최근순). /api/calendar는 문장 연습(Progress)만 세므로 활동 요약(acts)의 날짜도 합친다. */
function historyDates(cal, acts) {
  const days = new Set(Object.entries(cal || {}).filter(([, c]) => c > 0).map(([d]) => d))
  for (const [d, rows] of Object.entries(acts || {})) if (rows?.length) days.add(d)
  return [...days].sort((a, b) => (a < b ? 1 : -1))
}
// 트랙 칩(Figma 색 = 트랙) — 말하기만 발화, 나머지(검사·입모양·단어·문맥·문장)는 독화
const TRACK_CHIP = {
  read: { label: '독화', bg: '#efe9fc', fg: '#5f3ab8' },
  speak: { label: '발화', bg: '#ffe4e9', fg: '#be185d' },
}
// 날짜 칸 — Figma 209:22의 '오늘·어제·N일 전'. 원래 날짜는 툴팁으로 둔다.
function relDay(iso) {
  const [y, m, d] = iso.split('-').map(Number)
  const today = new Date(); today.setHours(0, 0, 0, 0)
  const diff = Math.round((today - new Date(y, m - 1, d)) / 86400000)
  return diff <= 0 ? '오늘' : diff === 1 ? '어제' : `${diff}일 전`
}

/** 회차 히스토리 — Figma 행 레이아웃(날짜·트랙칩·레슨·횟수·화살표).
 *  행은 날짜×주제 하나씩이다(/api/calendar/activities: 문장 연습은 상황별, 말하기는 모드별, 검사는 종류별).
 *  활동 요약이 아직 안 왔거나 그날 항목이 없으면 /api/calendar의 문장 연습 건수 한 행으로 대신한다.
 *  행을 누르면 서버가 준 route(해당 학습 화면)로 이동한다. */
function HistoryList({ cal, acts, onGo }) {
  const rows = historyDates(cal, acts).slice(0, 30).flatMap((date) => (
    acts?.[date]?.length
      ? acts[date]
      : [{ kind: 'sentence', topic_label: '문장 연습', label: '문장 연습', n: cal?.[date] || 0, route: '/learn/scenario' }]
  ).map((r) => ({ ...r, date })))
  if (rows.length === 0) return <p className="py-8 text-center text-sm text-ink-muted">아직 학습 기록이 없어요.</p>
  return (
    <div className="flex flex-col">
      {rows.map((r, i) => {
        const chip = TRACK_CHIP[r.kind === 'speak' ? 'speak' : 'read']
        // 레슨 칸 — 주제 이름. 문장 연습은 상황 이름만으론 뜻이 약해 서버 label('문장 연습 · 카페')을 쓴다.
        const lesson = r.kind === 'sentence' ? (r.label || r.topic_label) : r.topic_label
        const day = relDay(r.date)
        return (
          <button key={`${r.date}-${r.kind}-${r.topic ?? i}`} type="button" onClick={() => onGo(r.route)}
            aria-label={`${day} ${chip.label} ${lesson} 학습으로 이동`}
            className={`flex w-full items-center gap-3 py-[15px] text-left hover:bg-gray-50 ${i ? 'border-t-[1.5px] border-line' : ''}`}>
            <span className="w-[92px] shrink-0 text-[12.5px] text-ink-muted" title={r.date}>{day}</span>
            <span className="flex w-[54px] shrink-0 items-center justify-center rounded-[8px] py-[5px] text-[11.5px] font-bold"
              style={{ backgroundColor: chip.bg, color: chip.fg }}>{chip.label}</span>
            <span className="min-w-0 flex-1 truncate text-[15px] font-bold text-ink">{lesson}</span>
            <span className="w-[56px] shrink-0 text-right text-[12.5px] text-ink-muted">{r.n}회</span>
            <img src="/ui/menu-arrow.svg" alt="" className="h-3.5 w-[7px] shrink-0" />
          </button>
        )
      })}
    </div>
  )
}

/** 전체 통계 — Figma: 3지표 요약행 + 트랙별(독화·발화) 진행 카드.
 *  회차/문항/배지·트랙 진도는 getCalendar/statistics에 없으면 Figma 표본값으로 대체한다. */
function FullStats({ statistics, streak }) {
  const s = statistics || {}
  const num = (v) => (typeof v === 'number' ? v.toLocaleString() : v)
  const metrics = [
    { label: '총 학습 회차', value: num(s.total_sessions ?? s.sessions ?? 142), unit: '회', color: '#7d53de' },
    { label: '푼 문제', value: num(s.total_questions ?? s.questions_answered ?? 1684), unit: '개', color: '#7d53de' },
    { label: '획득 배지', value: num(s.badges ?? s.badge_count ?? 7), unit: '개', color: '#ec4899' },
  ]
  const acc = s.avg_accuracy != null ? Math.round(s.avg_accuracy * 100) : 81
  const tracks = [
    { name: '독화', acc, done: 4, total: 6, bg: '#efe9fc', fg: '#5f3ab8', fill: '#7d53de' },
    { name: '발화', acc: 72, done: 2, total: 6, bg: '#ffe4e9', fg: '#be185d', fill: '#ec4899' },
  ]
  return (
    <div className="flex flex-col gap-[22px]">
      <div className="flex items-center">
        {metrics.map((m, i) => (
          <div key={m.label} className="flex flex-1 items-center">
            {i > 0 && <span className="h-[48px] w-[1.5px] shrink-0 bg-line" />}
            <div className="flex flex-1 flex-col items-center gap-1.5 py-2.5">
              <span className="text-[12.5px] font-bold text-[#8a8a9b]">{m.label}</span>
              <span className="flex items-baseline gap-[3px] font-bold" style={{ color: m.color }}>
                <span className="text-[28px] tracking-[-0.7px]">{m.value}</span>
                <span className="text-[14px] opacity-70">{m.unit}</span>
              </span>
            </div>
          </div>
        ))}
      </div>
      <div className="flex flex-col gap-[14px] sm:flex-row">
        {tracks.map((t) => (
          <div key={t.name} className="flex flex-1 flex-col gap-[10px] rounded-[16px] p-[18px]" style={{ backgroundColor: t.bg }}>
            <div className="flex items-center justify-between font-bold" style={{ color: t.fg }}>
              <span className="text-[16px]">{t.name}</span>
              <span className="text-[13px] opacity-80">정확도 {t.acc}%</span>
            </div>
            <span className="text-[13px] opacity-75" style={{ color: t.fg }}>{t.done} / {t.total}단계 완료</span>
            <div className="h-[10px] overflow-hidden rounded-full bg-white/60">
              <div className="h-full rounded-full" style={{ width: `${(t.done / t.total) * 100}%`, backgroundColor: t.fill }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
