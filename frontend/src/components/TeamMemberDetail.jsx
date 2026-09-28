import Modal from './Modal'
import TeamAvatar from './TeamAvatar'
import { CONTACT_EMAIL, TEAM_ORG } from '../config/team'

// 팀원 상세(9/28 사용자 요청: 개발자 프로필을 누르면 상세 정보). 랜딩은 모달(TeamMemberModal), 사용법 가이드 11번 탭은
// 이미 모달 안이라 겹치지 않게 그 자리에서 펼친다(TeamMemberDetail). 내용은 config/team.js의 detail. 연락처는 맨 위에 둔다.

function AwardIcon({ school }) {
  return (
    <svg aria-hidden viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
      className={`mt-[3px] size-[15px] shrink-0 ${school ? 'text-ink-faint' : 'text-primary-500'}`}>
      <circle cx="12" cy="9" r="6" />
      <path d="M8.5 14.5 7 22l5-3 5 3-1.5-7.5" />
    </svg>
  )
}

function AwardList({ title, items, school }) {
  if (!items.length) return null
  return (
    <div className="flex flex-col gap-2">
      <p className="text-[13px] font-bold text-ink-faint">{title} <span className="font-normal">({items.length})</span></p>
      <ul className="flex flex-col gap-2.5">
        {items.map((a) => (
          <li key={a.title} className="flex gap-2">
            <AwardIcon school={school} />
            <div className="flex min-w-0 flex-col gap-0.5">
              <p className="break-keep text-[14px] font-bold leading-[1.45] text-ink">{a.title}</p>
              {a.by && <p className="break-keep text-[12.5px] text-ink-muted">{a.by}</p>}
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function ContactLine({ className = '' }) {
  return (
    <p className={`flex flex-wrap items-center gap-x-[10px] gap-y-1 font-bold leading-figma ${className}`}>
      <span className="text-[13px] text-ink-faint">연락처</span>
      <a href={`mailto:${CONTACT_EMAIL}`} className="text-[14px] text-primary-500 hover:underline">{CONTACT_EMAIL}</a>
    </p>
  )
}

export function TeamMemberDetail({ m }) {
  const d = m.detail || {}
  const awards = d.awards || []
  const external = awards.filter((a) => a.scope !== 'school')
  const school = awards.filter((a) => a.scope === 'school')
  return (
    <div className="flex flex-col gap-5 leading-figma">
      <div className="flex flex-col gap-1.5 rounded-14 bg-primary-50 px-4 py-3">
        <p className="text-[13px] font-bold text-primary-700">소속: {d.affiliation || TEAM_ORG}</p>
        <ContactLine />
      </div>
      {d.intro && <p className="break-keep text-[15px] leading-[1.6] text-ink">{d.intro}</p>}
      {d.work?.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="text-[13px] font-bold text-ink-faint">맡은 일</p>
          <ul className="flex flex-wrap gap-2">
            {d.work.map((w) => (
              <li key={w} className="rounded-full bg-primary-100 px-3 py-1 text-[13px] font-bold text-primary-700">{w}</li>
            ))}
          </ul>
        </div>
      )}
      <AwardList title="수상 · 선발" items={external} />
      <AwardList title="교내 수상" items={school} school />
      {!d.intro && !d.work?.length && !awards.length && (
        <p className="text-[14px] text-ink-muted">{m.note || '자세한 소개는 준비 중이에요.'}</p>
      )}
    </div>
  )
}

export default function TeamMemberModal({ m, onClose }) {
  return (
    <Modal open={!!m} onClose={onClose} maxW="max-w-[560px]"
      title={m && (
        <span className="flex items-center gap-4">
          <TeamAvatar m={m} size={72} />
          <span className="flex flex-col gap-1">
            <span>{m.name}</span>
            <span className="text-[13.5px] font-normal tracking-normal text-ink-muted">
              {m.role}{m.handle && <span className="ml-2 font-bold text-primary-500">{m.handle}</span>}
            </span>
          </span>
        </span>
      )}>
      {m && <TeamMemberDetail m={m} />}
    </Modal>
  )
}
