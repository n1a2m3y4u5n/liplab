import { useEffect, useRef } from 'react'
import { useListenKeys } from './usePlayer'
import { NOTICE, OVERFLOW, releaseClickFocus } from './ui'

/**
 * 묶음 끝 화면(독화 레슨 완료 93:12와 같은 결): 소리 듣기 DOKA + 스탯 칸 + 버튼 2개. 화면 전체를 덮는다.
 * stats: [{label, value, note, main}], main은 트랙색 값. Enter = 주 버튼.
 */
const GRID = { 1: 'grid-cols-1', 2: 'grid-cols-2', 3: 'grid-cols-3' }
export default function ListenComplete({ title, sub, stats = [], notes = [], primary, secondary, children }) {
  const h = useRef(null)
  useEffect(() => { h.current?.focus() }, [])
  useListenKeys({ onEnter: primary?.onClick })
  return (
    <div data-track="listen" className="fixed inset-0 z-50 overflow-y-auto bg-page" onClick={releaseClickFocus}>
      <div className="mx-auto flex min-h-full w-full max-w-[640px] animate-fade-in flex-col items-center justify-center gap-6 px-[18px] py-12">
        <span className="relative size-[112px] shrink-0 lg:size-[132px]">
          <img src="/ui/listen-node-current.svg" alt="" className="absolute max-w-none" style={OVERFLOW} />
        </span>
        <div className="flex flex-col items-center gap-2 text-center">
          <h1 ref={h} tabIndex={-1} className="break-keep text-[28px] font-bold leading-figma tracking-[-0.7px] text-ink outline-none lg:text-[36px] lg:tracking-[-0.9px]">{title}</h1>
          {sub && <p className="break-keep text-[15px] leading-[1.6] text-ink-muted">{sub}</p>}
        </div>
        {stats.length > 0 && (
          <div className={`grid w-full gap-2.5 lg:gap-3.5 ${GRID[stats.length] || 'grid-cols-3'}`}>
            {stats.map((s) => (
              <div key={s.label} className="flex min-w-0 flex-col gap-1.5 rounded-18 border-2 border-line bg-white p-3.5 lg:gap-2 lg:p-5">
                <p className="text-[13px] font-bold leading-figma text-ink-soft">{s.label}</p>
                <p className={`break-keep text-[19px] font-bold leading-figma tracking-[-0.4px] lg:text-[26px] ${s.main ? 'text-track-dark' : 'text-ink'}`}>{s.value}</p>
                {s.note && <p className="break-keep text-[12px] leading-snug text-ink-faint">{s.note}</p>}
              </div>
            ))}
          </div>
        )}
        {children}
        {notes.filter(Boolean).map((n, i) => (
          <p key={i} className="w-full break-keep rounded-14 bg-surface-sunken px-4 py-3 text-[14px] leading-[1.6] text-ink">{n}</p>
        ))}
        <div className="flex w-full flex-col gap-2.5 lg:gap-3">
          {primary && <button type="button" onClick={primary.onClick} className="btn-primary btn-lg w-full max-lg:rounded-14 max-lg:border-b-5 max-lg:py-4 max-lg:text-[16px]">{primary.label}</button>}
          {secondary && <button type="button" onClick={secondary.onClick} className="btn-secondary btn-lg w-full text-track-dark max-lg:rounded-14 max-lg:border-b-5 max-lg:py-4 max-lg:text-[16px]">{secondary.label}</button>}
        </div>
        <p className="break-keep text-center text-[12px] leading-[1.6] text-ink-faint">{NOTICE}</p>
      </div>
    </div>
  )
}

/**
 * 과제의 묶음 끝. 들어온 곳이 끝 처리(finish)를 정한다:
 *  - finish.onDone(result): 화면을 그리지 않고 결과만 넘긴다(오늘의 듣기·복습 블록, 엔드리스 연습이 다음 묶음으로 잇는다).
 *  - finish.actions(result): 완료 화면의 버튼 {primary, secondary}(단계 레슨은 lib/listenFlow.completeActions, 연습은 practiceActions).
 * result: {stage, n, c, skipped, mastered, elapsed, ...과제별 값}
 */
export function TaskEnd({ finish, result, ...complete }) {
  const sent = useRef(false)
  const onDone = finish?.onDone
  useEffect(() => {
    if (onDone && !sent.current) { sent.current = true; onDone(result) }
  }, [onDone, result])
  if (onDone) return null
  const acts = finish?.actions ? finish.actions(result) : {}
  return <ListenComplete {...complete} {...acts} />
}
