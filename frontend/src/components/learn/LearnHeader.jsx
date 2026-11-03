import { useSearchParams } from 'react-router-dom'
import { TRACK_LABEL } from '../../lib/iaLabels'
export default function LearnHeader() {
  const [params, setParams] = useSearchParams()
  const track = ['speak', 'listen'].includes(params.get('track')) ? params.get('track') : 'read'
  const section = ['free', 'res'].includes(params.get('section')) ? params.get('section') : 'path'
  const change = (key, value) => {
    const next = new URLSearchParams(params)
    next.delete('stage')
    if ((key === 'track' && value === 'read') || (key === 'section' && value === 'path')) next.delete(key)
    else next.set(key, value)
    setParams(next, { replace: true })
  }
  return <div className="flex w-full flex-col gap-2">
    <div aria-label="학습 종류" className="flex w-full gap-1 rounded-13 bg-surface-sunken p-1">{Object.entries(TRACK_LABEL).map(([key, label]) => <button key={key} aria-pressed={track === key} onClick={() => change('track', key)} className={`min-h-11 min-w-0 flex-1 rounded-10 px-1 text-[14px] sm:text-[15px] ${track === key ? 'bg-white font-semibold text-ink shadow-seg' : 'font-medium text-ink-muted'}`}>{label}</button>)}</div>
    <div aria-label="학습 구역" className="flex gap-1 border-b border-line">{[['path', '단계'], ['free', '자유 연습'], ['res', '자료']].map(([key, label]) => <button key={key} aria-pressed={section === key} onClick={() => change('section', key)} className={`-mb-px min-h-11 flex-1 border-b-2 px-2 text-[14px] ${section === key ? 'border-track font-semibold text-ink' : 'border-transparent font-medium text-ink-muted hover:text-ink'}`}>{label}</button>)}</div>
  </div>
}
