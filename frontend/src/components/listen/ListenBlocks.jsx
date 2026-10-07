import { useEffect, useState } from 'react'
import { josa, lingNotes, pct } from '../../lib/listenFlow'
import BottomBar from './BottomBar'
import { useListenKeys } from './usePlayer'
import { Card, Heading } from './ui'

/**
 * 블록을 차례로 잇는 회기(오늘의 듣기 15분, 듣기 복습). 블록 하나가 끝나면(과제의 finish.onDone) 짧은 전환 화면을 보이고,
 * 마지막 블록 뒤나 '여기까지 하기'를 누르면 요약(renderSummary)을 그린다.
 *  - blocks: [{key, title, minutes?, why?, run: ({onDone}) => 과제 노드}]
 *  - intro: 시작 전 화면(없으면 첫 블록부터). intro(start)로 부르고 시작 버튼이 start를 부른다.
 *  - onStep({idx, phase}): 위 제목 줄을 바꾸려고 알린다. phase: 'intro' | 'run' | 'break' | 'end'
 *  - active: 틀의 설정 화면이 열려 있으면 false(키보드·하단 바를 멈춘다)
 *  - endNow: 참이 되면 지금 블록을 멈추고 요약으로 간다(나가기를 눌렀는데 마친 블록이 있을 때). onResults(n)로 마친 블록 수를 알린다
 *  - onProgress: 틀의 진행바. 블록 안에서는 과제가 쓰고, 시작 전·전환·끝에서는 마친 블록 수를 보인다
 * 결과는 [{block, result}]이고, 블록을 건너뛰었으면 result가 null이다.
 */
export default function ListenBlocks({ blocks, intro = null, renderSummary, onStep, onProgress, onResults, endNow = false, active = true }) {
  const [idx, setIdx] = useState(0)
  const [phase, setPhase] = useState(intro ? 'intro' : 'run')
  const [results, setResults] = useState([])
  const n = blocks.length
  useEffect(() => { onStep?.({ idx, phase }) }, [idx, phase, onStep])
  useEffect(() => { onResults?.(results.length) }, [results.length, onResults])
  useEffect(() => { if (endNow) setPhase('end') }, [endNow])
  useEffect(() => {
    if (phase === 'intro') onProgress?.(0, 0)
    else if (phase === 'break') onProgress?.(idx + 1, n, `${idx + 1} / ${n} 마침`)
    else if (phase === 'end') onProgress?.(results.length, n, `${results.length} / ${n} 마침`)
  }, [phase, idx, n, onProgress, results.length])
  const last = idx >= blocks.length - 1
  const done = (result) => {
    setResults((rs) => [...rs, { block: blocks[idx], result: result || null }])
    setPhase(last ? 'end' : 'break')
  }
  const next = () => { setIdx((i) => i + 1); setPhase('run') }
  const stop = () => setPhase('end')

  if (phase === 'intro') return intro(() => setPhase('run'))
  if (phase === 'end') return renderSummary(results)
  if (phase === 'break') {
    return <BlockBreak done={results[results.length - 1]} no={idx + 1} total={blocks.length} next={blocks[idx + 1]} onNext={next} onStop={stop} active={active} />
  }
  const b = blocks[idx]
  return <div key={b.key} className="flex flex-col gap-4 lg:gap-5">{b.run({ onDone: done })}</div>
}

/** 블록 사이 전환: 마친 블록 결과 한 줄(+소리 확인 안내) · 다음 블록 · 다음 연습 시작 / 여기까지 하기. Enter = 다음. */
function BlockBreak({ done, no, total, next, onNext, onStop, active }) {
  useListenKeys({ active, onEnter: onNext })
  const r = done?.result
  const line = !r ? '이 연습은 건너뛰었어요'
    : r.summary ? lingNotes(r.summary).sub
      : r.n ? `${r.n}문항 중 ${r.c}문항 · 정답률 ${pct(r.c, r.n)}` : '소리를 받지 못해 세지 않고 넘겼어요'
  const notes = r?.summary ? lingNotes(r.summary).notes.filter(Boolean) : []
  return (
    <div className="flex animate-fade-in flex-col gap-4 lg:gap-5">
      <Heading title={`${josa(done?.block?.title || '연습', '을', '를')} 마쳤어요`} meta={`${no} / ${total} 마침`} sub={line} />
      {notes.map((n) => (
        <p key={n} className="break-keep rounded-14 bg-surface-sunken px-4 py-3 text-[14px] leading-[1.6] text-ink">{n}</p>
      ))}
      {next && (
        <Card className="flex items-center gap-4">
          <span aria-hidden className="flex size-10 shrink-0 items-center justify-center rounded-full bg-track-tint text-[15px] font-bold text-track-dark">{no + 1}</span>
          <div className="flex min-w-0 flex-1 flex-col gap-0.5 leading-figma">
            <p className="text-[12px] font-bold text-ink-muted">다음</p>
            <p className="text-[17px] font-bold text-ink">{next.title}</p>
            {(next.minutes || next.why) && (
              <p className="break-keep text-[13px] text-ink-muted">{[next.minutes ? `약 ${Math.max(1, Math.round(next.minutes))}분` : null, next.why !== next.title && next.why].filter(Boolean).join(' · ')}</p>
            )}
          </div>
        </Card>
      )}
      <BottomBar active={active} hint="잠깐 쉬어도 돼요" primary={{ label: '다음 연습 시작', onClick: onNext }} secondary={{ label: '여기까지 하기', onClick: onStop }} />
    </div>
  )
}
