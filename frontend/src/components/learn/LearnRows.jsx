// 학습 탭의 목록 모양(11/03). 단계 목록과 자유 연습·자료가 같은 행 모양을 쓴다: 흰 카드 하나 안에 1px 줄로 나눈 행.
export function RowList({ label, children }) {
  return <ul aria-label={label} className="divide-y divide-line overflow-hidden rounded-16 border border-line bg-white">{children}</ul>
}

export function Chevron({ className = '' }) {
  return (
    <svg aria-hidden viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={`size-4 shrink-0 text-ink-faint ${className}`}>
      <path d="m6 3.5 4.5 4.5L6 12.5" />
    </svg>
  )
}

// 단계 표시 동그라미: 숙달 ✓(트랙색) · 지금 단계 번호(트랙 테두리) · 열린 단계 번호 · 건너뛸 수 있음 번호(점선) · 잠김 자물쇠
export function StageMark({ status, no }) {
  const base = 'flex size-9 shrink-0 items-center justify-center rounded-full text-[14px] font-bold tabular-nums lg:size-10'
  if (status === 'mastered') {
    return (
      <span className={`${base} bg-track text-white`}>
        <svg aria-hidden viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" className="size-4"><path d="M3.5 8.5l3 3 6-7" /></svg>
      </span>
    )
  }
  if (status === 'current') return <span className={`${base} border-2 border-track bg-track-tint text-track-dark`}>{no}</span>
  if (status === 'open') return <span className={`${base} border border-line-strong bg-white text-ink`}>{no}</span>
  if (status === 'skip') return <span className={`${base} border border-dashed border-line-strong bg-white text-ink-muted`}>{no}</span>
  return (
    <span className={`${base} bg-surface-sunken text-ink-faint`}>
      <svg aria-hidden viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className="size-4"><rect x="3.5" y="7" width="9" height="6.5" rx="1.5" /><path d="M5.5 7V5.5a2.5 2.5 0 0 1 5 0V7" /></svg>
    </span>
  )
}

// 행 하나: 왼쪽 표시, 제목·설명, 오른쪽 상태 글자와 화살표. onClick이 없으면 누를 수 없는 행(잠김).
export function Row({ lead, title, desc, meta, metaClass = 'text-ink-muted', onClick, current = false, children }) {
  const body = (
    <>
      {lead}
      <span className="flex min-w-0 flex-1 flex-col gap-0.5 leading-figma">
        <span className={`break-keep text-[16px] ${current ? 'font-bold' : 'font-semibold'} ${onClick ? 'text-ink' : 'text-ink-muted'}`}>{title}</span>
        {desc && <span className="break-keep text-[13px] text-ink-muted lg:text-[14px]">{desc}</span>}
      </span>
      {meta && <span className={`shrink-0 text-right text-[13px] font-semibold tabular-nums ${metaClass}`}>{meta}</span>}
      {onClick && <Chevron />}
    </>
  )
  return (
    <li>
      {onClick
        ? <button type="button" onClick={onClick} className="flex min-h-[64px] w-full items-center gap-3.5 px-4 py-3 text-left transition-colors hover:bg-surface-muted lg:px-5">{body}</button>
        : <div className="flex min-h-[64px] w-full items-center gap-3.5 px-4 py-3 lg:px-5">{body}</div>}
      {children}
    </li>
  )
}

// 섹션 제목(학습 탭 안 '전체 단계'·'자유 연습'·'자료')
export function SectionTitle({ id, children, aside }) {
  return (
    <div className="flex items-end justify-between gap-3 px-1">
      <h2 id={id} className="text-[17px] font-bold tracking-[-0.2px] text-ink lg:text-[18px]">{children}</h2>
      {aside}
    </div>
  )
}
