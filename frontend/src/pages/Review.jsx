import { useState, useEffect, useMemo, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { curriculumAPI, reviewAPI, learningAPI } from '../api'
import MouthAvatar from '../components/MouthAvatar'
import LoadingScreen from '../components/LoadingScreen'
import LessonComplete from '../components/LessonComplete'
import useChoiceKeys from '../lib/useChoiceKeys'

/**
 * 오늘의 복습(간격 반복 SRS) — 독화 레슨 공통 템플릿(핸드오프 §4-03, WordStage·Closure와 같은 틀).
 * 틀렸던 항목(입모양 그룹·단어)이 예정일에 다시 나온다. 정답이면 다음 등장이 더 멀어지고(SM-2),
 * 오답이면 내일 다시 만난다(/api/review/answer). 진행바 분모는 오늘 예정 항목 수다.
 * 단어 보기는 최소대립 짝을 먼저 넣는다(단어 레슨과 같은 규칙) — 입모양이 비슷한 단어끼리 다시 가려 보게.
 */
const shuffle = (a) => [...a].sort(() => Math.random() - 0.5)

function partnersOf(word, pairs, bankSet) {
  const out = new Set()
  for (const m of pairs || []) {
    if (m.a === word && bankSet.has(m.b)) out.add(m.b)
    if (m.b === word && bankSet.has(m.a)) out.add(m.a)
  }
  return [...out]
}

export default function Review() {
  const navigate = useNavigate()
  const [state, setState] = useState('loading') // loading | empty | active | error
  const [items, setItems] = useState([])
  const [lessons, setLessons] = useState([])
  const [bank, setBank] = useState({ words: [], pairs: [] })

  useEffect(() => {
    Promise.all([reviewAPI.getDue(), curriculumAPI.getVisemeLessons(), curriculumAPI.getWords()])
      .then(([due, vl, wd]) => {
        setLessons(vl.lessons)
        setBank({ words: wd.words.map((w) => w.word), pairs: wd.minimal_pairs || [] })
        if (!due.items.length) { setState('empty'); return }
        setItems(due.items)
        setState('active')
      })
      .catch(() => setState('error'))
  }, [])

  if (state === 'loading') return <LoadingScreen variant="brand" track="perception" />
  if (state === 'error') return <div className="flex min-h-[100dvh] items-center justify-center bg-page text-[15px] text-ink-muted">불러오지 못했어요.</div>
  if (state === 'empty') {
    return (
      <div className="flex min-h-[100dvh] flex-col items-center justify-center gap-4 bg-page px-6 text-center">
        <h1 className="text-[24px] font-bold leading-figma text-ink">오늘 복습할 항목이 없어요</h1>
        <p className="text-[15px] text-ink-muted">틀린 입모양·단어는 다음 날부터 여기서 다시 만나요.</p>
        <button type="button" onClick={() => navigate('/review')} className="btn-primary px-6 py-3 text-[15px]">복습으로 돌아가기</button>
      </div>
    )
  }
  return (
    <div className="min-h-[100dvh] bg-page">
      <ReviewSession items={items} lessons={lessons} bank={bank} />
    </div>
  )
}

function ReviewSession({ items, lessons, bank }) {
  const navigate = useNavigate()
  const bankSet = useMemo(() => new Set(bank.words), [bank])
  const [idx, setIdx] = useState(0)
  const [frames, setFrames] = useState([])
  const [selected, setSelected] = useState(null)
  const [result, setResult] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [tally, setTally] = useState({ n: 0, correct: 0 })
  const [xpEarned, setXpEarned] = useState(0)      // 서버가 준 XP 합(응답 xp_gained) → 완료 화면
  const [done, setDone] = useState(false)
  const startRef = useRef(Date.now())
  const [elapsedSec, setElapsedSec] = useState(0)

  const item = items[idx]
  const isViseme = item.kind === 'viseme'
  const { targetKey, choices } = useMemo(() => {
    if (isViseme) {
      const vid = parseInt(item.ref, 10)
      const t = lessons.find((l) => l.viseme_id === vid)
      const others = shuffle(lessons.filter((l) => l.viseme_id !== vid)).slice(0, 3)
      return { targetKey: String(vid), choices: shuffle([t, ...others].filter(Boolean)).map((l) => ({ key: String(l.viseme_id), label: l.name })) }
    }
    const partners = partnersOf(item.ref, bank.pairs, bankSet)
    const rest = shuffle(bank.words.filter((w) => w !== item.ref && !partners.includes(w)))
    const distractors = [...shuffle(partners), ...rest].slice(0, 3)
    return { targetKey: item.ref, choices: shuffle([item.ref, ...distractors]).map((w) => ({ key: w, label: w })) }
  }, [item, lessons, bank, bankSet, isViseme])

  useEffect(() => {
    setResult(null); setSelected(null); setFrames([])
    if (!isViseme) learningAPI.getVisemes(item.ref).then(setFrames).catch(() => {})
  }, [item, isViseme])

  useChoiceKeys(choices, (c) => setSelected(c.key), !result && !submitting && !done)

  const confirm = async () => {
    if (result || submitting || selected == null) return
    setSubmitting(true)
    const correct = selected === targetKey
    try {
      const r = await reviewAPI.answer(item.kind, item.ref, correct)
      setXpEarned((x) => x + (r?.xp_gained || 0))
    } catch { /* 기록 실패해도 진행 */ } finally { setSubmitting(false) }
    setResult({ correct, chosen: selected })
    setTally((t) => ({ n: t.n + 1, correct: t.correct + (correct ? 1 : 0) }))
  }
  const next = () => {
    if (idx + 1 >= items.length) {
      setElapsedSec(Math.floor((Date.now() - startRef.current) / 1000))
      setDone(true)
      return
    }
    setIdx((k) => k + 1)
  }

  if (done) {
    const accuracy = tally.n ? Math.round((tally.correct / tally.n) * 100) : null
    return (
      <LessonComplete accuracy={accuracy} xp={xpEarned} elapsedSec={elapsedSec}
        onNext={() => navigate('/learn/path')} onHome={() => navigate('/review')} homeLabel="복습으로 돌아가기" />
    )
  }

  const answered = idx + (result ? 1 : 0)
  const pct = Math.round((answered / items.length) * 100)
  const targetLabel = choices.find((c) => c.key === targetKey)?.label || item.ref
  const optionState = (key) => {
    if (!result) return selected === key ? 'selected' : 'idle'
    if (key === targetKey) return result.chosen === key ? 'correct' : 'target'
    return result.chosen === key ? 'wrong' : 'idle'
  }

  return (
    <>
      <div className="mx-auto flex w-full max-w-[676px] flex-col px-[18px] pb-[200px] pt-[18px] lg:pb-[150px] lg:pt-7">
        <div className="flex items-center gap-3 lg:gap-[18px]">
          <button type="button" onClick={() => navigate('/review')} aria-label="나가기" className="shrink-0">
            <img src="/ui/lp-91-12-close.svg" alt="" className="size-8 lg:size-9" />
          </button>
          <div className="h-3 flex-1 overflow-hidden rounded-full bg-fill-strong lg:h-[14px]">
            <div className="h-full rounded-full bg-track transition-all duration-500" style={{ width: `${pct}%` }} />
          </div>
          <span className="shrink-0 text-[13px] font-bold leading-figma text-ink-muted lg:text-[15px]">{idx + 1} / {items.length}</span>
        </div>

        <div className="mt-6 flex flex-col gap-4 lg:mt-5 lg:gap-5">
          <div className="flex flex-col gap-1.5 leading-figma lg:gap-2">
            <p className="text-[12px] font-bold text-track lg:text-[13px]">오늘의 복습 · {isViseme ? '입모양' : '단어'}</p>
            <h1 className="text-[21px] font-bold tracking-[-0.525px] text-ink lg:text-[30px] lg:tracking-[-0.75px]">
              {isViseme ? '이 입모양은 어느 그룹일까요?' : '이 입모양은 어떤 단어일까요?'}
            </h1>
          </div>

          <div className="mx-auto h-[214px] w-full max-w-[560px] rounded-18 border-2 border-line bg-white p-4 lg:h-[370px] lg:rounded-22">
            <MouthAvatar key={`${item.kind}-${item.ref}`} height={null} className="h-full"
              frames={isViseme ? undefined : frames} visemeId={isViseme ? parseInt(item.ref, 10) : undefined} />
          </div>

          <div className="flex flex-col gap-2.5 lg:gap-3">
            {choices.map((c, k) => (
              <button key={c.key} type="button" disabled={!!result || submitting} onClick={() => setSelected(c.key)}
                aria-pressed={!result ? selected === c.key : undefined} className={OPTION_CLASS[optionState(c.key)]}>
                <span className="flex size-6 shrink-0 items-center justify-center rounded-[7px] bg-fill text-[12px] font-bold leading-figma text-ink-muted lg:size-7 lg:rounded-lg lg:text-[13px]">{k + 1}</span>
                <span className="flex-1 text-[18px] font-bold leading-figma lg:text-[20px]">{c.label}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className={`fixed inset-x-0 bottom-0 z-40 border-t-2 ${!result ? 'border-line bg-white' : result.correct ? 'border-good bg-good-tint lg:border-good/35' : 'border-bad bg-bad-tint lg:border-bad/35'}`}>
        <div className="mx-auto flex max-w-[676px] flex-col items-stretch gap-3 px-[18px] pb-[calc(22px+env(safe-area-inset-bottom))] pt-4 lg:h-[110px] lg:flex-row lg:items-center lg:justify-between lg:gap-4 lg:py-0">
          {result ? (
            <div role="status" aria-live="polite" className={`flex min-w-0 flex-col gap-[3px] leading-figma lg:gap-1 ${result.correct ? 'text-good-text' : 'text-bad-text'}`}>
              <p className="text-[19px] font-bold tracking-[-0.38px] lg:text-[22px] lg:tracking-[-0.44px]">{result.correct ? '정답이에요!' : '아쉬워요'}</p>
              <p className="truncate text-[13px] font-bold opacity-80 lg:text-[14px]">
                {result.correct ? '다음 복습은 더 나중에 나와요' : `정답은 「${targetLabel}」 · 내일 다시 만나요`}
              </p>
            </div>
          ) : (
            <span className="hidden text-[15px] leading-figma text-ink-faint lg:inline">{selected == null ? '보기를 선택해주세요' : '정답을 확인해보세요'}</span>
          )}
          {result ? (
            <button type="button" onClick={next} className={`${result.correct ? 'btn-good' : 'btn-bad'} btn-bar ${BAR_BTN}`}>계속하기</button>
          ) : (
            <button type="button" onClick={confirm} disabled={selected == null || submitting} className={`btn-primary btn-bar ${BAR_BTN}`}>확인</button>
          )}
        </div>
      </div>
    </>
  )
}

const BAR_BTN = 'w-full shrink-0 max-lg:py-4 max-lg:text-[16px] lg:w-auto'
const OPTION_BASE = 'flex w-full items-center gap-3.5 rounded-14 px-[18px] py-[15px] text-left transition-colors lg:gap-4 lg:rounded-16 lg:px-5 lg:py-4'
const OPTION_CLASS = {
  idle: `${OPTION_BASE} border-2 border-b-5 border-line bg-white text-ink enabled:hover:border-primary-300 enabled:active:scale-[0.99]`,
  selected: `${OPTION_BASE} border-2 border-b-5 border-track bg-track-tint text-ink`,
  correct: `${OPTION_BASE} border-[2.5px] border-good bg-good-tint text-good-text`,
  target: `${OPTION_BASE} border-[2.5px] border-good bg-white text-ink`,
  wrong: `${OPTION_BASE} border-[2.5px] border-bad bg-bad-tint text-bad-text`,
}
