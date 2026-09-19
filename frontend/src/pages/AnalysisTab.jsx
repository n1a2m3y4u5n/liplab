import { useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'
import useStore from '../store/useStore'

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
  const navigate = useNavigate()
  const user = useStore((s) => s.user)
  const streak = Math.max(0, user?.streak_count || 7)

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
        <DetailLink label="활동 캘린더" onClick={() => navigate('/analysis/activity')} />
        <DetailLink label="회차 히스토리" onClick={() => navigate('/analysis/history')} />
        <DetailLink label="전체 통계" onClick={() => navigate('/analysis/overview')} />
      </div>
    </AppShell>
  )
}
