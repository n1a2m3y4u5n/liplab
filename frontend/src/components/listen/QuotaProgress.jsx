import { quotaView } from '../../lib/listenQuota'

export function QuotaBar({ quota }) {
  const q = quotaView(quota)
  return <div className="flex flex-1 gap-1" role="img" aria-label={`오늘 몫 ${q.total}묶음 중 ${q.done}묶음 채움`}>
    {Array.from({ length: q.total }, (_, i) => <span key={i} className={`h-2.5 flex-1 rounded-full ${i < q.filled ? 'bg-track' : 'bg-fill-strong'}`} />)}
  </div>
}

export function QuotaRing({ quota, className = '' }) {
  const q = quotaView(quota)
  const circumference = 2 * Math.PI * 37
  const segment = circumference / q.total
  return <svg viewBox="0 0 80 80" className={className} aria-hidden="true">
    {Array.from({ length: q.total }, (_, i) => <circle key={i} cx="40" cy="40" r="37" fill="none" stroke={i < q.filled ? 'var(--track)' : 'var(--fill-strong, #e4e4ec)'} strokeWidth="4"
      strokeDasharray={`${segment - 2} ${circumference - segment + 2}`} transform={`rotate(${-89 + i * 360 / q.total} 40 40)`} />)}
  </svg>
}
