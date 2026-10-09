import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { curriculumAPI, learningAPI } from '../api'
import MouthAvatar from '../components/MouthAvatar'
import LoadingScreen from '../components/LoadingScreen'
import { LoadFailed } from '../components/ErrorScreen'
import useChoiceKeys from '../lib/useChoiceKeys'
import { consonantFrame } from '../lib/consonantSkeleton'
import { SHAPES } from '../lib/nonsenseShapes'
import { HINT_MS, trialOrder, gridOrder, usedToday, saveUsedToday, timeUp, blockSummary } from '../lib/nonsensePairing'
import { LESSON_COL, LESSON_STACK, LESSON_AVATAR, lessonPad } from '../lib/lessonLayout'
import { trialMeta } from '../lib/measurement'

/**
 * 뜻 없는 말 짝 맞추기(/learn/nonsense, 계획 C10, docs/nonsense-pairing.md). 1·2단계 사이의 하루 10분 이하 과제다.
 * 아바타가 뜻 없는 두 음절 낱말(예: 허벱)을 말하고, 학습자는 그 낱말과 짝인 도형을 고른다. 목록 하나(낱말 6개)를 기준까지 되풀이한다.
 *  - 목록을 처음 열면 짝 6개를 하나씩 보여 준다(도형 + 자음 골격 + 아바타).
 *  - 홀수 블록은 '골격 보고': 시행마다 자음 골격(ㅎ_ㅂ_ㅂ)을 먼저 1.5초 보여 주고, 아바타가 말하는 동안에도 남겨 둔다.
 *    짝수 블록은 '확인': 골격 없이 입모양만 본다. 확인 블록을 모두 맞히면(90% 이상) 그 목록을 마치고 그날 회차를 끝낸다.
 *  - 철자 전체는 보이지 않는다(Bernstein 2023에서 낱말 전체를 미리 본 집단은 짝을 기억하지 못했고, 자음만 본 집단이 향상했다).
 *  - 답은 시행 기록에만 남는다. 단계 숙달·복습·XP·연속 학습 보상은 없다.
 */

function Shape({ id, className = '' }) {
  const s = SHAPES[id]
  if (!s) return null
  return (
    <svg viewBox="0 0 100 100" className={className} aria-hidden>
      {s.kind === 'stroke'
        ? <path d={s.d} fill="none" stroke="currentColor" strokeWidth="14" strokeLinecap="round" strokeLinejoin="round" />
        : <path d={s.d} fill="currentColor" />}
    </svg>
  )
}

function Skeleton({ word, className = '' }) {
  return (
    <p className={`font-bold tracking-[0.18em] text-ink ${className}`} aria-label={`자음 골격 ${consonantFrame(word)}`}>
      {consonantFrame(word).split('').join(' ')}
    </p>
  )
}

const OPTION_BASE = 'relative flex h-[76px] w-full items-center justify-center rounded-16 transition-colors lg:h-[92px] lg:rounded-18'
const OPTION_CLASS = {
  idle: `${OPTION_BASE} border-2 border-b-5 border-line bg-white text-ink enabled:hover:border-primary-300 enabled:active:scale-[0.99]`,
  correct: `${OPTION_BASE} border-[2.5px] border-good bg-good-tint text-good-text`,
  target: `${OPTION_BASE} border-[2.5px] border-good bg-white text-ink`,
  wrong: `${OPTION_BASE} border-[2.5px] border-bad bg-bad-tint text-bad-text`,
}
const BAR_BTN = 'w-full shrink-0 max-lg:py-4 max-lg:text-[16px] lg:w-auto'

const storage = () => { try { return window.localStorage } catch { return null } }

export default function NonsensePairing() {
  const navigate = useNavigate()
  const [view, setView] = useState(null)          // 서버 회차 상태(set, block, today …)
  const [frames, setFrames] = useState({})        // 낱말 → 입모양 프레임
  const [phase, setPhase] = useState('loading')   // loading | error | intro | trial | between | end
  const [endReason, setEndReason] = useState(null) // finished | today | time | set
  const [introIdx, setIntroIdx] = useState(0)
  const [order, setOrder] = useState([])          // 이번 블록에서 남은 시행 순서
  const [step, setStep] = useState(0)
  const [grid, setGrid] = useState([])            // 도형 자리(낱말, 보인 순서)
  const [hinting, setHinting] = useState(false)   // 골격만 먼저 보이는 1.5초
  const [result, setResult] = useState(null)      // { correct, chosen, answer } + 서버 응답
  const [submitting, setSubmitting] = useState(false)
  const [doneBlock, setDoneBlock] = useState(null) // 막 끝난 블록 { hint, correct, size }
  const baseUsed = useRef(0)
  const startedAt = useRef(Date.now())
  const hintTimer = useRef(null)

  const usedMs = () => baseUsed.current + (Date.now() - startedAt.current)
  const saveTime = useCallback(() => saveUsedToday(storage(), baseUsed.current + (Date.now() - startedAt.current)), [])
  useEffect(() => () => { saveTime(); clearTimeout(hintTimer.current) }, [saveTime])

  const showTrial = useCallback((hint) => {
    clearTimeout(hintTimer.current)
    if (!hint) { setHinting(false); return }
    setHinting(true)
    hintTimer.current = setTimeout(() => setHinting(false), HINT_MS)
  }, [])

  const startBlock = useCallback((v) => {
    const words = v.set.words.map((w) => w.word)
    const o = trialOrder(words, v.block.remaining, v.set.id, v.block.index)
    setOrder(o)
    setStep(0)
    setGrid(gridOrder(words, v.set.id, v.block.index))
    setResult(null)
    setPhase('trial')
    showTrial(v.block.hint)
  }, [showTrial])

  const end = (reason) => { saveTime(); setEndReason(reason); setPhase('end') }

  const load = useCallback(async () => {
    setPhase('loading')
    try {
      const v = await curriculumAPI.getNonsenseSession()
      setView(v)
      baseUsed.current = usedToday(storage())
      startedAt.current = Date.now()
      if (v.finished) { setEndReason('finished'); setPhase('end'); return }
      if (v.today.done) { setEndReason('today'); setPhase('end'); return }
      if (timeUp(baseUsed.current, v.today.minutes)) { setEndReason('time'); setPhase('end'); return }
      const pairs = await Promise.all(v.set.words.map(async (w) => [w.word, await learningAPI.getVisemes(w.word)]))
      setFrames(Object.fromEntries(pairs))
      if (!v.block.started) { setIntroIdx(0); setPhase('intro') } else startBlock(v)
    } catch {
      setPhase('error')
    }
  }, [startBlock])
  useEffect(() => { load() }, [load])

  const cur = order[step] || null
  // 반응 시간 기준(파일럿 로그 P0): 골격 보기가 끝나고 이 시행의 낱말 재생을 시작한 때
  const onsetRef = useRef(null)
  useEffect(() => { onsetRef.current = cur && phase === 'trial' && !hinting ? Date.now() : null }, [cur, phase, hinting])
  const shapeOf = useMemo(() => Object.fromEntries((view?.set?.words || []).map((w) => [w.word, w.shape])), [view])

  const pick = async (chosen) => {
    if (phase !== 'trial' || hinting || result || submitting || !cur) return
    setSubmitting(true)
    try {
      const r = await curriculumAPI.submitNonsense(view.set.id, view.block.index, cur, chosen, grid,
        trialMeta({ onsetAt: onsetRef.current, talker: 'default', hintUsed: !!view.block.hint }))
      setResult({ ...r, chosen })
      saveTime()
    } catch (e) {
      if (e?.response?.status === 409) load()   // 다른 탭에서 진행했거나 오늘 분량을 마쳤으면 서버 상태로 다시
    } finally {
      setSubmitting(false)
    }
  }
  useChoiceKeys(grid, (w) => pick(w), phase === 'trial' && !hinting && !result && !submitting)

  // 계속하기: 블록이 끝났으면 안내, 오늘 분량·시간을 다 썼으면 끝, 아니면 다음 시행
  const next = () => {
    const r = result
    if (!r) return
    const finishedHint = view.block.hint
    setView(r)   // 응답에 다음 목록·블록·오늘 수가 실려 온다
    if (r.set_done) { end('set'); return }
    if (r.finished) { end('finished'); return }
    if (r.today.done) { end('today'); return }
    if (timeUp(usedMs(), r.today.minutes)) { end('time'); return }
    if (r.block_done) {
      setDoneBlock({ hint: finishedHint, correct: r.block_correct, size: r.block_size })
      setPhase('between')
      return
    }
    setResult(null)
    setStep((s) => s + 1)
    showTrial(r.block.hint)
  }

  if (phase === 'loading') return <LoadingScreen />
  if (phase === 'error') return <LoadFailed message="짝 맞추기를 가져오지 못했어요." onRetry={load} onExit={() => navigate('/learn/path')} />

  const exitBtn = (
    <button type="button" onClick={() => navigate('/learn/path')} aria-label="나가기" className="shrink-0">
      <img src="/ui/lp-91-12-close.svg" alt="" className="size-8 lg:size-9" />
    </button>
  )

  if (phase === 'end') {
    const title = { finished: '모든 목록을 마쳤어요', today: '오늘 분량을 마쳤어요', time: '오늘은 10분을 채웠어요', set: '이 목록을 마쳤어요' }[endReason]
    const body = {
      finished: `목록 ${view?.n_sets ?? ''}개를 모두 익혔어요. 지금은 더 할 목록이 없어요.`,
      today: '하루에 하는 양을 정해 두었어요. 내일 이어서 해요.',
      time: '하루 10분까지만 해요. 내일 이어서 해요.',
      set: '다음 목록은 내일 이어서 해요.',
    }[endReason]
    return (
      <div className="min-h-[100dvh] bg-page">
        <div className={LESSON_COL}>
          {exitBtn}
          <div className="mt-10 flex flex-col items-center gap-4 rounded-20 border-2 border-line bg-white px-6 py-10 text-center">
            <p className="text-[21px] font-bold leading-figma text-ink lg:text-[26px]">{title}</p>
            <p className="text-[15px] leading-relaxed text-ink-muted">{body}</p>
            {view?.today && <p className="text-[13px] text-ink-faint">오늘 {view.today.n}번 골랐어요</p>}
            <button type="button" onClick={() => navigate('/learn/path')} className="btn-primary mt-2 px-8 py-3 text-[16px]">학습 화면으로</button>
          </div>
        </div>
      </div>
    )
  }

  const words = view.set.words
  const label = (
    <p className="text-[12px] font-bold text-track lg:text-[13px]">
      뜻 없는 말 짝 맞추기 · 목록 {view.set.index} / {view.n_sets}
    </p>
  )

  if (phase === 'intro') {
    const w = words[introIdx]
    const last = introIdx >= words.length - 1
    return (
      <div className="min-h-[100dvh] bg-page">
        <div className={`${LESSON_COL} ${lessonPad(false)}`}>
          <div className="flex items-center gap-3 lg:gap-[18px]">
            {exitBtn}
            <div className="h-3 flex-1 overflow-hidden rounded-full bg-fill-strong lg:h-[14px]">
              <div className="h-full rounded-full bg-track transition-all duration-500" style={{ width: `${((introIdx + 1) / words.length) * 100}%` }} />
            </div>
            <span className="shrink-0 text-[13px] font-bold leading-figma text-ink-muted lg:text-[15px]">{introIdx + 1} / {words.length}</span>
          </div>
          <div className={LESSON_STACK}>
            <div className="flex flex-col gap-1.5 leading-figma lg:gap-2">
              {label}
              <h1 className="text-[21px] font-bold tracking-[-0.525px] text-ink lg:text-[30px] lg:tracking-[-0.75px]">이 말과 도형을 짝지어 기억해요</h1>
              <p className="text-[14px] text-ink-muted">뜻이 없는 말이에요. 입모양과 자음만 보고 도형과 짝지어요.</p>
            </div>
            <div className="flex items-stretch gap-3">
              <div className="flex w-[36%] shrink-0 flex-col items-center justify-center gap-3 rounded-18 border-2 border-line bg-white p-4 lg:rounded-22">
                <Shape id={w.shape} className="size-20 text-ink lg:size-28" />
                <Skeleton word={w.word} className="text-[20px] lg:text-[26px]" />
              </div>
              <div className="h-[clamp(150px,calc(100dvh_-_420px),300px)] min-w-0 flex-1 rounded-18 border-2 border-line bg-white p-3 lg:rounded-22">
                <MouthAvatar frames={frames[w.word]} height={null} className="h-full" />
              </div>
            </div>
          </div>
        </div>
        <div className="fixed inset-x-0 bottom-0 z-40 border-t-2 border-line bg-white">
          <div className="mx-auto flex max-w-[676px] flex-col items-stretch gap-3 px-[18px] pb-[calc(22px+env(safe-area-inset-bottom))] pt-4 lg:h-[110px] lg:flex-row lg:items-center lg:justify-between lg:gap-4 lg:py-0">
            <span className="text-[15px] leading-figma text-ink-faint">입모양이 되풀이돼요. 충분히 보고 넘어가요.</span>
            <div className="flex gap-2.5">
              {introIdx > 0 && <button type="button" onClick={() => setIntroIdx(introIdx - 1)} className={`btn-secondary btn-bar ${BAR_BTN}`}>이전</button>}
              <button type="button" onClick={() => (last ? startBlock(view) : setIntroIdx(introIdx + 1))} className={`btn-primary btn-bar ${BAR_BTN}`}>
                {last ? '시작하기' : '다음'}
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (phase === 'between') {
    return (
      <div className="min-h-[100dvh] bg-page">
        <div className={LESSON_COL}>
          {exitBtn}
          <div className="mt-10 flex flex-col items-center gap-4 rounded-20 border-2 border-line bg-white px-6 py-10 text-center">
            <p className="text-[19px] font-bold leading-figma text-ink lg:text-[22px]">{doneBlock.correct} / {doneBlock.size}</p>
            <p role="status" className="text-[15px] leading-relaxed text-ink-muted">{blockSummary(doneBlock)}</p>
            <button type="button" onClick={() => startBlock(view)} className="btn-primary mt-2 px-8 py-3 text-[16px]">계속하기</button>
          </div>
        </div>
      </div>
    )
  }

  // 시행
  const hint = view.block.hint
  const answered = words.length - order.length + step + (result ? 1 : 0)
  const state = (w) => {
    if (!result) return 'idle'
    if (w === result.answer) return result.chosen === w ? 'correct' : 'target'
    return result.chosen === w ? 'wrong' : 'idle'
  }
  return (
    <div className="min-h-[100dvh] bg-page">
      <div className={`${LESSON_COL} ${lessonPad(!!result)}`}>
        <div className="flex items-center gap-3 lg:gap-[18px]">
          {exitBtn}
          <div className="h-3 flex-1 overflow-hidden rounded-full bg-fill-strong lg:h-[14px]">
            <div className="h-full rounded-full bg-track transition-all duration-500" style={{ width: `${(answered / words.length) * 100}%` }} />
          </div>
          <span className="shrink-0 text-[13px] font-bold leading-figma text-ink-muted lg:text-[15px]">{Math.min(answered + (result ? 0 : 1), words.length)} / {words.length}</span>
        </div>

        <div className={LESSON_STACK}>
          <div className="flex items-end justify-between gap-3">
            <div className="flex min-w-0 flex-col gap-1.5 leading-figma lg:gap-2">
              {label}
              <h1 className="text-[21px] font-bold tracking-[-0.525px] text-ink lg:text-[30px] lg:tracking-[-0.75px]">
                {hint ? '자음을 보고 도형을 골라요' : '입모양만 보고 도형을 골라요'}
              </h1>
            </div>
            {/* 골격 보고 블록은 아바타가 말하는 동안에도, 확인 블록은 답한 뒤에만 정답 낱말의 골격을 보인다 */}
            {!hinting && cur && (hint || result) && (
              <div className="shrink-0 rounded-13 border-2 border-line bg-white px-3 py-1.5">
                <Skeleton word={result ? result.answer : cur} className="text-[16px] lg:text-[19px]" />
              </div>
            )}
          </div>

          <div className={LESSON_AVATAR}>
            {hinting ? (
              <div className="flex h-full flex-col items-center justify-center gap-2">
                <span className="text-[13px] font-bold text-ink-faint">자음 골격</span>
                <Skeleton word={cur} className="text-[34px] lg:text-[46px]" />
              </div>
            ) : (
              <MouthAvatar frames={cur ? frames[cur] : null} visemeId={cur ? null : 15} height={null} className="h-full" />
            )}
          </div>

          <div className="grid grid-cols-3 gap-2.5 lg:gap-3">
            {grid.map((w, i) => (
              <button key={w} type="button" disabled={hinting || !!result || submitting} onClick={() => pick(w)}
                aria-label={`도형 ${i + 1}`} className={`${OPTION_CLASS[state(w)]} disabled:cursor-default`}>
                <Shape id={shapeOf[w]} className="size-11 lg:size-14" />
                <span className="absolute left-2 top-2 flex size-6 items-center justify-center rounded-[7px] bg-fill text-[12px] font-bold text-ink-muted" aria-hidden>{i + 1}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className={`fixed inset-x-0 bottom-0 z-40 border-t-2 ${!result ? 'border-line bg-white' : result.correct ? 'border-good bg-good-tint lg:border-good/35' : 'border-bad bg-bad-tint lg:border-bad/35'}`}>
        <div className="mx-auto flex max-w-[676px] flex-col items-stretch gap-3 px-[18px] pb-[calc(22px+env(safe-area-inset-bottom))] pt-4 lg:h-[110px] lg:flex-row lg:items-center lg:justify-between lg:gap-4 lg:py-0">
          {result ? (
            <div role="status" aria-live="polite" className={`flex min-w-0 flex-col gap-[3px] leading-figma lg:gap-1 ${result.correct ? 'text-good-text' : 'text-bad-text'}`}>
              <p className="text-[19px] font-bold tracking-[-0.38px] lg:text-[22px]">{result.correct ? '맞았어요' : '아쉬워요'}</p>
              <p className="text-[13px] font-bold opacity-80 lg:text-[14px]">
                {result.correct ? '입모양을 한 번 더 보고 넘어가요' : '초록 테두리가 짝인 도형이에요. 입모양을 다시 보고 넘어가요'}
              </p>
            </div>
          ) : (
            <span className="text-[15px] leading-figma text-ink-faint">{hinting ? '자음을 먼저 봐요' : <>도형을 눌러 골라요<span className="hidden lg:inline"> · 숫자 키 1~6</span></>}</span>
          )}
          {result && <button type="button" onClick={next} className={`${result.correct ? 'btn-good' : 'btn-bad'} btn-bar ${BAR_BTN}`}>계속하기</button>}
        </div>
      </div>
    </div>
  )
}
