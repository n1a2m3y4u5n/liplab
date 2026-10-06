import { useEffect, useRef, useState } from 'react'
import { curriculumAPI, learningAPI } from '../api'
import MouthAvatar from './MouthAvatar'
import useChoiceKeys from '../lib/useChoiceKeys'
import { LESSON_COL, LESSON_STACK, LESSON_AVATAR, LESSON_AVATAR_VISEME, LESSON_OPTIONS, lessonPad } from '../lib/lessonLayout'
import { probeOptionLabel } from '../lib/measurement'

/**
 * 숙달 지연 탐침(C16) 문항 묶음 — 레슨 가운데 끼워 내는 확인 문항(hooks/useMasteryProbes).
 * 숙달한 단계의 처음 보는 문항을 보조 없이 낸다: 1.0배 자연 속도, 기본 얼굴(가상 화자 없음), 감속·힌트·기호 없음, 정답 공개 없음.
 * 답은 서버의 탐침 기록에만 남고 숙달·복습·XP에는 들어가지 않는다(backend/mastery_probe.py). 보내지 못해도 다음 문항으로 넘어간다.
 * 화면 틀은 배치검사 문항(Placement)과 같은 독화 레슨 템플릿이다.
 */
export default function MasteryProbeBlock({ items, onDone }) {
  const [idx, setIdx] = useState(0)
  const [frames, setFrames] = useState([])
  const [selected, setSelected] = useState(null)
  const [sending, setSending] = useState(false)
  const seqRef = useRef(0)
  const it = items?.[idx]

  useEffect(() => {
    if (!it) return
    setFrames([])
    setSelected(null)
    const seq = ++seqRef.current
    learningAPI.getVisemes(it.stimulus).then((f) => { if (seq === seqRef.current) setFrames(f) }).catch(() => {})
  }, [it])

  const options = it?.options || []
  useChoiceKeys(options, (o) => setSelected(o.value), !!it && !sending)

  const confirm = async () => {
    if (!it || selected == null || sending) return
    setSending(true)
    try { await curriculumAPI.answerMasteryProbe(it.id, selected) } catch { /* 기록 실패해도 진행 */ }
    setSending(false)
    if (idx + 1 >= items.length) onDone?.()
    else setIdx(idx + 1)
  }

  if (!it) return null
  return (
    <div className="min-h-[100dvh] bg-page">
      <div className={`${LESSON_COL} ${lessonPad(false)}`}>
        <div className="flex items-center gap-3 lg:gap-[18px]">
          <div className="h-3 flex-1 overflow-hidden rounded-full bg-fill-strong lg:h-[14px]">
            <div className="h-full rounded-full bg-track transition-all" style={{ width: `${((idx + 1) / items.length) * 100}%` }} />
          </div>
          <span className="shrink-0 text-[13px] font-bold leading-figma text-ink-muted lg:text-[15px]">{idx + 1} / {items.length}</span>
        </div>

        <div className={LESSON_STACK}>
          <div className="flex flex-col gap-1.5 font-bold leading-figma lg:gap-2">
            <p className="text-[12px] text-track lg:text-[13px]">확인 문항 · 보통 빠르기, 도움 없이</p>
            <h1 className="text-[21px] tracking-[-0.525px] text-ink lg:text-[30px] lg:tracking-[-0.75px]">
              {it.kind === 'viseme' ? '이 입모양은 어떤 모양일까요?' : it.kind === 'sentence' ? '어떤 문장일까요?' : '어떤 단어일까요?'}
            </h1>
          </div>

          <div className={it.kind === 'viseme' ? LESSON_AVATAR_VISEME : LESSON_AVATAR}>
            <MouthAvatar frames={frames} height={null} className="h-full" speed={1} showTalker={false} />
          </div>

          <div className={LESSON_OPTIONS}>
            {options.map((o, i) => {
              const on = selected === o.value
              return (
                <button key={o.value} type="button" disabled={sending} onClick={() => setSelected(o.value)} aria-pressed={on}
                  className={`flex w-full items-center gap-3.5 rounded-14 border-2 border-b-5 px-[18px] py-[15px] text-left transition-colors disabled:opacity-60 enabled:active:scale-[0.99] lg:gap-4 lg:rounded-16 lg:px-5 lg:py-4 ${on ? 'border-track bg-track-tint' : 'border-line bg-white enabled:hover:border-primary-300'}`}>
                  <span className="flex size-6 shrink-0 items-center justify-center rounded-[7px] bg-fill text-[12px] font-bold leading-figma text-ink-muted lg:size-7 lg:rounded-lg lg:text-[13px]">{i + 1}</span>
                  <span className={`flex-1 font-bold leading-figma text-ink ${it.kind === 'sentence' ? 'text-[16px] lg:text-[18px]' : 'text-[18px] lg:text-[20px]'}`}>{probeOptionLabel(it, o)}</span>
                </button>
              )
            })}
          </div>
        </div>
      </div>

      <div className="fixed inset-x-0 bottom-0 z-40 border-t-2 border-line bg-white">
        <div className="mx-auto flex max-w-[676px] flex-col items-stretch px-[18px] pb-[calc(22px+env(safe-area-inset-bottom))] pt-4 lg:h-[110px] lg:flex-row lg:items-center lg:justify-between lg:py-0">
          <p className="hidden text-[15px] leading-figma text-ink-faint lg:block">점수에 들어가지 않아요. 정답은 따로 알려 주지 않아요</p>
          <button type="button" onClick={confirm} disabled={selected == null || sending}
            className="btn-primary btn-bar w-full shrink-0 max-lg:py-4 max-lg:text-[16px] lg:w-auto">
            다음
          </button>
        </div>
      </div>
    </div>
  )
}
