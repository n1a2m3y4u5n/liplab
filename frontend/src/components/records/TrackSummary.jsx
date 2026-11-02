import { useNavigate } from 'react-router-dom'
import { TRACK_LABEL } from '../../lib/iaLabels'
export default function TrackSummary({ track, overview }) {
  const navigate = useNavigate()
  const data = overview?.tracks?.[track]
  return <section className="card-flat flex flex-col gap-4"><h2 className="text-lg font-bold">{TRACK_LABEL[track]}</h2>
    <dl className="grid grid-cols-3 gap-3">{[['정답률', data?.accuracy != null ? `${Math.round(data.accuracy * 100)}%` : '–'], ['숙달 단계', data?.done ?? '–'], ['문항 수', data?.attempts ?? data?.n ?? '–']].map(([label, value]) => <div key={label}><dt className="text-sm text-ink-muted">{label}</dt><dd className="mt-2 text-xl font-bold">{value}</dd></div>)}</dl>
    {track === 'read' && <div className="flex flex-wrap gap-2"><button className="btn-secondary min-h-11 px-4" onClick={() => navigate('/analysis/visemes')}>약한 입모양</button><button className="btn-secondary min-h-11 px-4" onClick={() => navigate('/analysis/eval')}>학습 효과 리포트</button></div>}
  </section>
}
