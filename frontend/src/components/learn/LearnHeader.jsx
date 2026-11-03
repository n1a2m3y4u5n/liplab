import { useSearchParams } from 'react-router-dom'
import { TRACK_LABEL } from '../../lib/iaLabels'
// 학습 탭 맨 위 트랙 스위처. 11/03부터 '단계·자유 연습·자료' 하위 탭은 없애고 한 화면에 차례로 둔다(?section=은 그 자리로 스크롤).
export default function LearnHeader() {
  const [params, setParams] = useSearchParams()
  const track = ['speak', 'listen'].includes(params.get('track')) ? params.get('track') : 'read'
  const change = (value) => {
    const next = new URLSearchParams(params)
    next.delete('stage')
    next.delete('section')
    if (value === 'read') next.delete('track')
    else next.set('track', value)
    setParams(next, { replace: true })
  }
  return <div aria-label="학습 종류" className="flex w-full gap-1 rounded-13 bg-surface-sunken p-1">{Object.entries(TRACK_LABEL).map(([key, label]) => <button key={key} aria-pressed={track === key} onClick={() => change(key)} className={`min-h-11 min-w-0 flex-1 rounded-10 px-1 text-[14px] sm:text-[15px] ${track === key ? 'bg-white font-semibold text-ink shadow-seg' : 'font-medium text-ink-muted hover:text-ink'}`}>{label}</button>)}</div>
}
