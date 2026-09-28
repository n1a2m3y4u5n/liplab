import Modal from './Modal'
import TeamAvatar from './TeamAvatar'
import { CONTACT_EMAIL } from '../config/team'

// 팀원 상세(9/28 사용자 요청: 개발자 프로필을 누르면 상세 정보). 랜딩은 모달(TeamMemberModal), 사용법 가이드 11번 탭은
// 이미 모달 안이라 겹치지 않게 그 자리에서 펼친다(TeamMemberDetail). 내용은 config/team.js의 detail.
// 레이아웃(9/28 2차): 전문 프로필(LinkedIn '수상 경력', GitHub 프로필 사이드바)처럼 모든 구역이 같은 왼쪽 기준선에서 시작한다.
// 소속·핸들은 라벨 칸 폭이 고정된 정의 목록이고(개인 연락처는 넣지 않고 목록 위 '대표 연락처'만 둔다), 구역마다 작은 제목 + 구분선, 수상은 제목 한 줄 + 시상 명의 한 줄.

function AwardIcon({ school }) {
  return (
    <span aria-hidden className={`mt-[1px] flex size-7 shrink-0 items-center justify-center rounded-full ${school ? 'bg-fill text-ink-faint' : 'bg-primary-100 text-primary-600'}`}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="size-[15px]">
        <circle cx="12" cy="9" r="5.5" />
        <path d="M8.8 14 7.5 21l4.5-2.6 4.5 2.6-1.3-7" />
      </svg>
    </span>
  )
}

function Section({ title, count, children }) {
  return (
    <section className="flex flex-col gap-3 border-t border-line pt-4">
      <h3 className="flex items-baseline gap-1.5 text-[13px] font-bold tracking-[-0.01em] text-ink">
        {title}{count != null && <span className="text-[12px] font-medium text-ink-faint">{count}</span>}
      </h3>
      {children}
    </section>
  )
}

function AwardList({ items, school }) {
  return (
    <ul className="flex flex-col gap-3">
      {items.map((a) => (
        <li key={a.title} className="flex gap-3">
          <AwardIcon school={school} />
          <div className="flex min-w-0 flex-col gap-0.5 pt-[3px]">
            <p className="break-keep text-[14px] font-bold leading-[1.45] text-ink">{a.title}</p>
            {a.by && <p className="break-keep text-[12.5px] leading-[1.4] text-ink-muted">{a.by}</p>}
          </div>
        </li>
      ))}
    </ul>
  )
}

/** 연락처 한 줄. 목록 위(랜딩 패널·가이드 개발자 소개)는 '대표 연락처', 개인 상세 안은 정의 목록을 쓴다. */
export function ContactLine({ className = '', label = '대표 연락처' }) {
  return (
    <p className={`flex flex-wrap items-center gap-x-[10px] gap-y-1 font-bold leading-figma ${className}`}>
      <span className="text-[13px] text-ink-faint">{label}</span>
      <a href={`mailto:${CONTACT_EMAIL}`} className="text-[14px] text-primary-500 hover:underline">{CONTACT_EMAIL}</a>
    </p>
  )
}

export function TeamMemberDetail({ m }) {
  const d = m.detail || {}
  const awards = d.awards || []
  const external = awards.filter((a) => a.scope !== 'school')
  const school = awards.filter((a) => a.scope === 'school')
  const facts = [
    d.affiliation && ['소속', d.affiliation],
    d.email && ['연락처', <a key="e" href={`mailto:${d.email}`} className="font-bold text-primary-500 hover:underline">{d.email}</a>],
    m.handle && ['핸들', m.handle],
  ].filter(Boolean)
  return (
    <div className="flex flex-col gap-4 leading-figma">
      <dl className="grid grid-cols-[56px_1fr] items-baseline gap-x-4 gap-y-2">
        {facts.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-[13px] font-medium text-ink-faint">{k}</dt>
            <dd className="min-w-0 break-keep text-[14px] font-medium text-ink">{v}</dd>
          </div>
        ))}
      </dl>
      {d.work?.length > 0 && (
        <Section title="맡은 일">
          <ul className="flex flex-wrap gap-2">
            {d.work.map((w) => (
              <li key={w} className="rounded-full border border-primary-200 bg-primary-50 px-3 py-1 text-[13px] font-bold text-primary-700">{w}</li>
            ))}
          </ul>
        </Section>
      )}
      {external.length > 0 && <Section title="수상 · 선발" count={external.length}><AwardList items={external} /></Section>}
      {school.length > 0 && <Section title="교내 수상" count={school.length}><AwardList items={school} school /></Section>}
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
            <span className="text-[13.5px] font-medium tracking-normal text-ink-muted">{m.role}</span>
          </span>
        </span>
      )}>
      {m && <TeamMemberDetail m={m} />}
    </Modal>
  )
}
