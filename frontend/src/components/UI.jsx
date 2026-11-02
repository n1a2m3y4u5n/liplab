import { useSyncExternalStore } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import { entranceMotion, UI_MOTION } from '../lib/uiMotion'
export { default as Button } from './Button'

const subscribe = (notify) => {
  const observer = new MutationObserver(notify)
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
  return () => observer.disconnect()
}
const snapshot = () => document.documentElement.classList.contains('a11y-reduce-motion')

export function useUIMotion() {
  const os = useReducedMotion()
  const app = useSyncExternalStore(subscribe, snapshot, () => false)
  return !!(os || app)
}

/** 새 경로·완료·답 공개 뒤에만 사용한다. 레슨 문항 전체를 감싸지 않는다. */
export function MotionPanel({ children, kind = 'card', className = '', ...props }) {
  const reduced = useUIMotion()
  return <motion.div {...props} {...entranceMotion(reduced, kind)} className={className}>{children}</motion.div>
}

/** 답 공개 뒤 다시 듣기처럼 검사 자극과 분리된 재생 표시 전용. */
export function PlaybackIndicator({ active, children }) {
  const reduced = useUIMotion()
  return <motion.span className="inline-flex shrink-0" initial={false}
    animate={{ opacity: active && !reduced ? [1, 0.55, 1] : 1 }}
    transition={{ duration: active && !reduced ? 0.9 : 0, repeat: active && !reduced ? Infinity : 0, ease: UI_MOTION.ease }}>
    {children}
  </motion.span>
}

export function Card({ children, className = '', as: Tag = 'div', ...props }) {
  return <Tag {...props} className={`ui-card ${className}`}>{children}</Tag>
}

/** 좁은 기기에서도 표의 열을 숨기지 않고 키보드·터치로 이동한다. */
export function TableRegion({ label, children, className = '' }) {
  return <div role="region" aria-label={label} tabIndex={0}
    className={`min-w-0 max-w-full overflow-x-auto rounded-14 border-2 border-line focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-track ${className}`}>
    {children}
  </div>
}

export function Chip({ children, className = '', ...props }) {
  return <span {...props} className={`ui-chip ${className}`}>{children}</span>
}

/** 진행 막대만 움직인다. 검사에서는 animated=false로 즉시 갱신한다. */
export function Progress({ value = 0, label, valueText, animated = false, className = '' }) {
  const reduced = useUIMotion()
  const pct = Math.max(0, Math.min(100, Number(value) || 0))
  return <div className={`ui-progress ${className}`} role="progressbar" aria-label={label}
    aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pct)} aria-valuetext={valueText}>
    <motion.div className="h-full rounded-full bg-track" initial={false} animate={{ width: `${pct}%` }}
      transition={{ duration: animated && !reduced ? UI_MOTION.duration : 0, ease: UI_MOTION.ease }} />
  </div>
}

export function EmptyState({ title, body, children, className = '' }) {
  return <Card className={`flex flex-col items-center gap-3 py-8 text-center ${className}`}>
    <p role="status" className="text-[17px] font-bold leading-snug text-ink">{title}</p>
    {body && <p className="max-w-[420px] break-keep text-[14px] leading-relaxed text-ink-muted">{body}</p>}
    {children}
  </Card>
}
