import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import AppShell from '../components/AppShell'
import SummaryBody from '../components/records/SummaryBody'
import ListenReportBody from '../components/records/ListenReportBody'
import ReviewItems from '../components/records/ReviewItems'
import { listenAPI } from '../api'
import { TRACK_LABEL } from '../lib/iaLabels'
export default function RecordsPage() {
  const [params, setParams] = useSearchParams()
  const view = ['wrong', 'saved'].includes(params.get('view')) ? params.get('view') : 'summary'
  const track = ['read', 'speak', 'listen'].includes(params.get('track')) ? params.get('track') : 'all'
  const [started, setStarted] = useState(false)
  useEffect(() => { let on = true; listenAPI.links().then((d) => { if (on) setStarted(!!d.listen_started) }).catch(() => {}); return () => { on = false } }, [])
  const choose = (key, value, fallback) => { const next = new URLSearchParams(params); if (value === fallback) next.delete(key); else next.set(key, value); setParams(next, { replace: true }) }
  return <AppShell active="records" title="기록">
    <p className="records-print-context hidden">{track === 'all' ? '전체' : TRACK_LABEL[track]} · {view === 'wrong' ? '틀린 문장' : view === 'saved' ? '저장한 문장' : '요약'}</p>
    <div className="records-controls flex gap-1 border-b border-line" aria-label="기록 구역">{[['summary', '요약'], ['wrong', '틀린 문장'], ['saved', '저장한 문장']].map(([key, label]) => <button key={key} className={`-mb-px min-h-11 flex-1 border-b-2 px-2 text-[14px] ${view === key ? 'border-primary-500 font-semibold text-ink' : 'border-transparent font-medium text-ink-muted hover:text-ink'}`} aria-pressed={view === key} onClick={() => choose('view', key, 'summary')}>{label}</button>)}</div>
    <div className="records-controls flex flex-wrap gap-2" aria-label="학습 종류">{[['all', '전체'], ...Object.entries(TRACK_LABEL)].filter(([key]) => key !== 'listen' || started || track === 'listen').map(([key, label]) => <button key={key} className={`min-h-11 rounded-full px-4 text-[14px] ${track === key ? 'bg-surface-inverse font-semibold text-white' : 'bg-surface-sunken font-medium text-ink-muted hover:bg-surface-hover'}`} aria-pressed={track === key} onClick={() => choose('track', key, 'all')}>{label}</button>)}</div>
    {view !== 'summary' ? <ReviewItems key={view + track} view={view} track={track} /> : track === 'listen' ? <ListenReportBody /> : <SummaryBody track={track} />}
  </AppShell>
}
