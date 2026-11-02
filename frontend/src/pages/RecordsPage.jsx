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
    <div className="flex flex-wrap gap-1" aria-label="기록 구역">{[['summary', '요약'], ['wrong', '틀린 문장'], ['saved', '저장한 문장']].map(([key, label]) => <button key={key} className={`min-h-11 flex-1 rounded-10 px-2 text-sm font-bold ${view === key ? 'bg-primary-100 text-primary-700' : 'text-ink-muted'}`} aria-pressed={view === key} onClick={() => choose('view', key, 'summary')}>{label}</button>)}</div>
    <div className="flex flex-wrap gap-2" aria-label="기록 트랙">{[['all', '전체'], ...Object.entries(TRACK_LABEL)].filter(([key]) => key !== 'listen' || started || track === 'listen').map(([key, label]) => <button key={key} className={`min-h-11 rounded-full px-3 text-sm font-bold ${track === key ? 'bg-primary-500 text-white' : 'bg-surface-sunken text-ink-muted'}`} aria-pressed={track === key} onClick={() => choose('track', key, 'all')}>{label}</button>)}</div>
    {view !== 'summary' ? <ReviewItems key={view + track} view={view} track={track} /> : track === 'listen' ? <ListenReportBody /> : <SummaryBody track={track} />}
  </AppShell>
}
