import { CONTACT_EMAIL } from '../config/team'

export default function ContactLine({ className = '', label = '대표 연락처' }) {
  return (
    <p className={`flex flex-wrap items-center gap-x-[10px] gap-y-1 font-bold leading-figma ${className}`}>
      <span className="text-[13px] text-ink-faint">{label}</span>
      <a href={`mailto:${CONTACT_EMAIL}`} className="text-[14px] text-primary-500 hover:underline">{CONTACT_EMAIL}</a>
    </p>
  )
}
