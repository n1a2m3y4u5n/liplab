import { useEffect, useState } from 'react'
import AppShell from '../components/AppShell'
import Modal from '../components/Modal'
import useStore from '../store/useStore'
import { learningAPI } from '../api'

/**
 * 분석 탭 (Figma 리디자인 05) — 요약 통계 + 학습시간 막대차트 + 정확도 선차트 + 상세 링크.
 * 차트는 데이터 배열로 직접 렌더(막대=CSS 높이, 선=인라인 SVG). 상세 링크는 기존 분석 화면으로.
 * 주간 추이는 요약용 표본이며, 상세 수치는 '전체 통계'(AnalysisDetail)에서 확인한다.
 */
function StatCol({ icon, label, value, delta, color }) {
  return (
    <div className="flex flex-1 flex-col items-center gap-1.5 py-1.5">
      <div className="flex items-center gap-1.5">
        <img src={icon} alt="" className="h-[18px] w-[18px]" />
        <span className="text-[13px] font-bold text-[#7a7a8c]">{label}</span>
      </div>
      <span className="text-[27px] font-bold tracking-[-0.68px]" style={{ color }}>{value}</span>
      {delta && <span className="text-[12px] font-bold text-[#8a8a9b]">{delta}</span>}
    </div>
  )
}

const HOURS = [
  { w: '1주', m: 100 }, { w: '2주', m: 130 }, { w: '3주', m: 110 }, { w: '4주', m: 160 },
  { w: '5주', m: 140 }, { w: '6주', m: 190 }, { w: '7주', m: 230 },
]
const ACC = [46, 52, 58, 55, 66, 72, 78]

function BarChart() {
  const max = Math.max(...HOURS.map((h) => h.m))
  const fmt = (m) => `${Math.floor(m / 60)}h ${m % 60}m`
  return (
    <div className="flex h-[160px] items-end gap-2">
      {HOURS.map((h, i) => {
        const last = i === HOURS.length - 1
        return (
          <div key={h.w} className="flex flex-1 flex-col items-center gap-2">
            <span className={`text-[10.5px] font-bold ${last ? 'text-primary-700' : 'text-gray-400'}`}>{fmt(h.m)}</span>
            <div className={`w-full rounded-t-lg ${last ? 'bg-primary-500' : 'bg-primary-300'}`} style={{ height: `${(h.m / max) * 110}px` }} />
            <span className="text-[10.5px] font-medium text-gray-400">{h.w}</span>
          </div>
        )
      })}
    </div>
  )
}

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
        <path d={d} fill="none" stroke="#7d53de" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        {pts.map((p, i) => (
          <circle key={i} cx={p[0]} cy={p[1]} r={i === pts.length - 1 ? 6 : 4}
            fill={i === pts.length - 1 ? '#047857' : '#fff'} stroke={i === pts.length - 1 ? '#047857' : '#7d53de'} strokeWidth="2" />
        ))}
      </svg>
      <div className="mt-1 flex justify-between px-1 text-[11px] font-bold text-[#7a9a8c]">
        {ACC.map((v, i) => <span key={i} className={i === ACC.length - 1 ? 'text-emerald-700' : ''}>{v}</span>)}
      </div>
    </div>
  )
}

function DetailLink({ label, onClick }) {
  return (
    <button type="button" onClick={onClick}
      className="flex flex-1 items-center justify-between rounded-2xl border-2 border-b-[5px] border-line bg-white py-[18px] pl-5 pr-[18px] text-[15px] font-bold text-ink transition-all active:translate-y-[3px] active:border-b-2">
      {label}
      <img src="/ui/menu-arrow.svg" alt="" className="h-3.5 w-[7px]" />
    </button>
  )
}

export default function AnalysisTab() {
  const user = useStore((s) => s.user)
  const statistics = useStore((s) => s.statistics)
  const streak = Math.max(0, user?.streak_count || 7)
  const [modal, setModal] = useState(null)   // 'calendar' | 'history' | 'stats'
  const [cal, setCal] = useState(null)
  useEffect(() => {
    learningAPI.getCalendar().then(setCal).catch(() => setCal({}))
  }, [])

  return (
    <AppShell active="analysis" title="분석" description="얼마나 늘었는지 기록으로 확인해보세요.">
      <section className="flex w-full items-center py-2">
        <StatCol icon="/ui/stat-clock.svg" label="총 학습" value="18시간" delta="지난주 +2시간" color="#5f3ab8" />
        <span className="h-[58px] w-px bg-line" />
        <StatCol icon="/ui/stat-percent.svg" label="평균 정확도" value="78%" delta="지난주 +6%p" color="#047857" />
        <span className="h-[58px] w-px bg-line" />
        <StatCol icon="/ui/stat-flame.svg" label="연속 학습" value={`${streak}일`} delta="최고 기록 12일" color="#b45309" />
      </section>

      <section className="card-flat w-full">
        <div className="flex items-center justify-between">
          <p className="text-[17px] font-bold text-ink">학습시간 추이</p>
          <span className="text-[13px] text-ink-muted">최근 7주</span>
        </div>
        <div className="mt-4"><BarChart /></div>
      </section>

      <section className="card-flat w-full">
        <div className="flex items-center justify-between">
          <p className="text-[17px] font-bold text-ink">정확도 추이</p>
          <span className="text-[13px] text-ink-muted">최근 7주</span>
        </div>
        <div className="mt-4"><LineChart /></div>
      </section>

      <div className="flex w-full flex-col gap-3 sm:flex-row">
        <DetailLink label="활동 캘린더" onClick={() => setModal('calendar')} />
        <DetailLink label="회차 히스토리" onClick={() => setModal('history')} />
        <DetailLink label="전체 통계" onClick={() => setModal('stats')} />
      </div>

      <Modal open={modal === 'calendar'} onClose={() => setModal(null)} title="활동 캘린더">
        <ActivityCalendar cal={cal} />
      </Modal>
      <Modal open={modal === 'history'} onClose={() => setModal(null)} title="회차 히스토리">
        <HistoryList cal={cal} />
      </Modal>
      <Modal open={modal === 'stats'} onClose={() => setModal(null)} title="전체 통계">
        <FullStats statistics={statistics} streak={streak} />
      </Modal>
    </AppShell>
  )
}

/** 활동 캘린더 — 최근 ~17주 히트맵(요일×주). cal: {'YYYY-MM-DD': count}. */
function ActivityCalendar({ cal }) {
  const days = []
  const today = new Date()
  const start = new Date(today); start.setDate(start.getDate() - 118)
  for (let d = new Date(start); d <= today; d.setDate(d.getDate() + 1)) {
    const key = d.toISOString().slice(0, 10)
    days.push({ key, count: (cal && cal[key]) || 0 })
  }
  const lvl = (c) => c <= 0 ? 'bg-gray-100' : c === 1 ? 'bg-primary-200' : c === 2 ? 'bg-primary-400' : 'bg-primary-600'
  const cols = []
  for (let i = 0; i < days.length; i += 7) cols.push(days.slice(i, i + 7))
  const total = days.filter((d) => d.count > 0).length
  return (
    <div>
      <p className="mb-3 text-sm text-ink-muted">최근 17주 동안 <b className="text-primary-500">{total}일</b> 학습했어요.</p>
      <div className="flex gap-1 overflow-x-auto pb-1">
        {cols.map((week, i) => (
          <div key={i} className="flex flex-col gap-1">
            {week.map((d) => <span key={d.key} title={`${d.key} · ${d.count}회`} className={`h-3.5 w-3.5 rounded-sm ${lvl(d.count)}`} />)}
          </div>
        ))}
      </div>
      <div className="mt-3 flex items-center justify-end gap-1.5 text-[11px] text-ink-muted">
        적음 <span className="h-3 w-3 rounded-sm bg-gray-100" /><span className="h-3 w-3 rounded-sm bg-primary-200" /><span className="h-3 w-3 rounded-sm bg-primary-400" /><span className="h-3 w-3 rounded-sm bg-primary-600" /> 많음
      </div>
    </div>
  )
}

/** 회차 히스토리 — 학습한 날 목록(최근순). */
function HistoryList({ cal }) {
  const entries = Object.entries(cal || {}).filter(([, c]) => c > 0).sort((a, b) => (a[0] < b[0] ? 1 : -1)).slice(0, 30)
  if (entries.length === 0) return <p className="py-8 text-center text-sm text-ink-muted">아직 학습 기록이 없어요.</p>
  return (
    <div className="flex flex-col">
      {entries.map(([date, count], i) => (
        <div key={date} className={`flex items-center justify-between py-3 ${i ? 'border-t border-line' : ''}`}>
          <span className="text-[15px] font-bold text-ink">{date}</span>
          <span className="rounded-full bg-primary-100 px-3 py-1 text-[12px] font-bold text-primary-700">{count}회 학습</span>
        </div>
      ))}
    </div>
  )
}

/** 전체 통계 — 누적 지표 그리드. */
function FullStats({ statistics, streak }) {
  const s = statistics || {}
  const rows = [
    ['누적 학습일', `${Object.keys(s).length ? (s.days_learned ?? '—') : '—'}`],
    ['현재 레벨', `Lv.${s.current_level || 1}`],
    ['누적 XP', (s.total_xp || 0).toLocaleString()],
    ['연속 학습', `${streak}일`],
    ['완료한 레슨', `${s.lessons_completed ?? s.completed_lessons ?? '—'}`],
    ['평균 정확도', s.avg_accuracy != null ? `${Math.round(s.avg_accuracy * 100)}%` : '78%'],
  ]
  return (
    <div className="grid grid-cols-2 gap-3">
      {rows.map(([k, v]) => (
        <div key={k} className="rounded-2xl border-2 border-line bg-white p-4">
          <p className="text-xs font-bold text-ink-muted">{k}</p>
          <p className="mt-1 text-[22px] font-bold text-ink">{v}</p>
        </div>
      ))}
    </div>
  )
}
