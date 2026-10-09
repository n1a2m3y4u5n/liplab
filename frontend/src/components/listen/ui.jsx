import { useEffect, useState } from 'react'

/**
 * 소리 듣기 화면의 작은 조각(카드·질문·보기·재생 막대·불러오는 중). 레슨 틀은 독화·말하기 레슨과 같다(핸드오프 §3.4).
 * 색은 트랙 청록(--track, data-track="listen") + 정오 초록·빨강 + 회색만 쓴다.
 */

export const IC = { close: '/ui/lp-91-12-close.svg' }
export const NOTICE = '청력을 진단하거나 치료하지 않아요. 보청기·인공와우 조절은 청능사나 병원에서 해요. 귀가 아프거나 울리면 바로 멈추세요.'
export const SYNTH = '소리는 기계로 미리 만든 합성 음성이에요.'
export const OVERFLOW = { top: '-7%', left: '-12%', width: '124%', height: '124%' }   // DOKA SVG 그림자 여백(Figma inset)

// 마우스·터치로 누른 버튼은 초점을 내려놓는다. 그래야 다음 Enter·스페이스가 그 버튼을 다시 누르지 않고 '확인'·'듣기'가 된다.
// 키보드로 누른 것(detail 0)은 초점을 그대로 둬 Tab 이동이 끊기지 않는다.
export const releaseClickFocus = (e) => {
  if (e.detail > 0) e.target.closest?.('button')?.blur()
}
export const isDesktop = () => { try { return window.matchMedia('(min-width: 1024px)').matches } catch { return false } }

export function Card({ children, className = '' }) {
  return <div className={`rounded-18 border-2 border-line bg-white p-5 lg:rounded-22 lg:p-6 ${className}`}>{children}</div>
}

/** 문항 질문(독화 레슨 91:19와 같은 크기). meta는 질문 아래 작은 줄(수준·보기 수 등). */
export function Heading({ title, meta, sub }) {
  return (
    <div className="flex flex-col gap-1.5 leading-figma lg:gap-2">
      <h1 className="text-[21px] font-bold tracking-[-0.525px] text-ink lg:text-[28px] lg:tracking-[-0.7px]">{title}</h1>
      {meta && <p className="text-[13px] font-bold text-track-dark">{meta}</p>}
      {sub && <p className="text-[14px] leading-[1.6] text-ink-muted">{sub}</p>}
    </div>
  )
}

export function SpeakerIcon({ playing, size = 30 }) {
  return (
    <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      {playing ? (
        <>
          <path d="M11 5 6 9H3v6h3l5 4V5z" fill="currentColor" />
          <path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13" />
        </>
      ) : <path d="M8 5.5v13l11-6.5z" fill="currentColor" />}
    </svg>
  )
}

/** 재생 진행 막대. 시간만 보인다(소리 모양은 그리지 않는다). 재생이 시작되면 예상 길이 동안 차고, 끝나면 가득 찬 채로 둔다. */
export function ProgressLine({ phase, run, totalMs }) {
  const [w, setW] = useState(0)
  useEffect(() => {
    if (phase !== 'playing') { setW(phase === 'done' ? 100 : 0); return undefined }
    setW(0)
    let alive = true
    const id = requestAnimationFrame(() => requestAnimationFrame(() => { if (alive) setW(100) }))
    return () => { alive = false; cancelAnimationFrame(id) }
  }, [phase, run])
  return (
    <div aria-hidden className="h-1.5 w-full overflow-hidden rounded-full bg-fill">
      <div className={`h-full rounded-full bg-track ${phase === 'done' ? 'opacity-50' : ''}`}
        style={{ width: `${w}%`, transition: phase === 'playing' && w === 100 ? `width ${totalMs}ms linear` : 'none' }} />
    </div>
  )
}

// 보기(독화 레슨 91:29와 같은 결). 정답·오답 공개는 2.5px 테두리(높이를 맞추려고 위 패딩 2px 더함).
const OPTION_BASE = 'flex min-h-[56px] w-full items-center gap-3.5 rounded-14 px-[18px] py-[13px] text-left transition-colors lg:gap-4 lg:rounded-16 lg:px-5 lg:py-4'
const OPTION_CLASS = {
  idle: `${OPTION_BASE} border-2 border-b-5 border-line bg-white text-ink enabled:hover:border-track enabled:active:scale-[0.99] disabled:cursor-not-allowed`,
  selected: `${OPTION_BASE} border-2 border-b-5 border-track bg-track-tint text-ink`,
  correct: `${OPTION_BASE} pt-[15px] lg:pt-[18px] border-[2.5px] border-good bg-good-tint text-good-text`,
  target: `${OPTION_BASE} pt-[15px] lg:pt-[18px] border-[2.5px] border-good bg-white text-ink`,
  wrong: `${OPTION_BASE} pt-[15px] lg:pt-[18px] border-[2.5px] border-bad bg-bad-tint text-bad-text`,
}
const OPTION_SR = { correct: ', 정답, 고른 답', target: ', 정답', wrong: ', 고른 답, 틀린 답' }

export function Option({ index, label, state = 'idle', disabled, waiting, onClick, big = false }) {
  return (
    <button type="button" disabled={disabled} onClick={onClick} aria-pressed={state === 'selected' || state === 'idle' ? state === 'selected' : undefined}
      aria-label={`${index + 1}번 ${label}${OPTION_SR[state] || ''}`}
      className={`${OPTION_CLASS[state]} ${waiting ? 'opacity-50' : ''}`}>
      <span aria-hidden className="flex size-6 shrink-0 items-center justify-center rounded-[7px] bg-fill text-[12px] font-bold leading-figma text-ink-muted lg:size-7 lg:rounded-lg lg:text-[13px]">{index + 1}</span>
      <span className={`min-w-0 flex-1 break-keep font-bold leading-snug ${big ? 'text-[19px] lg:text-[21px]' : 'text-[16px] lg:text-[17px]'}`}>{label}</span>
    </button>
  )
}

/** 보기 공개 상태: 결과 전에는 고른 것만, 결과 뒤에는 정답·고른 오답. */
export function optionState(i, { picked, result, answer }) {
  if (!result) return picked === i ? 'selected' : 'idle'
  if (i === answer) return picked === i ? 'correct' : 'target'
  return picked === i ? 'wrong' : 'idle'
}

/** 불러오는 중: 화면 모양만 흐리게(질문 · 소리 카드 · 보기). */
export function Skeleton() {
  return (
    <div role="status" aria-label="가져오는 중" className="flex animate-pulse-slow flex-col gap-4 lg:gap-5">
      <div className="h-7 w-3/4 rounded-10 bg-fill lg:h-9" />
      <div className="h-[104px] rounded-18 border-2 border-line bg-white lg:h-[124px] lg:rounded-22" />
      <div className="grid grid-cols-2 gap-2.5 lg:gap-3">
        {[0, 1, 2, 3].map((i) => <div key={i} className="h-[56px] rounded-14 bg-fill lg:h-[60px]" />)}
      </div>
      <span className="sr-only">가져오는 중이에요</span>
    </div>
  )
}

/** 하나 고르기(라디오 카드). 소리 크기 맞추기·듣기 조건 고르기에서 쓴다. */
export function ChoiceGroup({ legend, options, value, onChange, cols }) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-2 text-[15px] font-bold text-ink">{legend}</legend>
      <div role="radiogroup" aria-label={legend} className={`grid gap-2 ${cols}`}>
        {options.map((o) => {
          const on = value === o.key
          return (
            <button key={o.key} type="button" role="radio" aria-checked={on} onClick={() => onChange(o.key)}
              className={`flex min-h-[48px] items-center gap-2.5 rounded-13 border-2 px-3.5 py-2.5 text-left text-[15px] font-bold leading-snug transition-colors ${on ? 'border-track bg-track-tint text-track-dark' : 'border-line bg-white text-ink hover:border-track'}`}>
              <span aria-hidden className={`flex size-[18px] shrink-0 items-center justify-center rounded-full border-2 ${on ? 'border-track-dark' : 'border-line-strong'}`}>
                {on && <span className="size-2 rounded-full bg-track-dark" />}
              </span>
              <span className="flex min-w-0 flex-col gap-0.5">
                <span className="break-keep">{o.label}</span>
                {o.desc && <span className={`break-keep text-[13px] font-normal ${on ? 'text-track-dark' : 'text-ink-muted'}`}>{o.desc}</span>}
              </span>
            </button>
          )
        })}
      </div>
    </fieldset>
  )
}

export const inputClass = 'w-full rounded-14 border-2 border-line bg-white px-4 py-3.5 text-[17px] text-ink outline-none focus:border-track disabled:bg-surface-sunken disabled:text-ink-faint lg:rounded-16 lg:text-[18px]'
