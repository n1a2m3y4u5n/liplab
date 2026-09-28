import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { curriculumAPI, reviewAPI, learningAPI } from '../api'
import MouthAvatar from '../components/MouthAvatar'
import LoadingScreen from '../components/LoadingScreen'
import LessonComplete from '../components/LessonComplete'
import { LoadFailed } from '../components/ErrorScreen'
import useChoiceKeys from '../lib/useChoiceKeys'
import { pickDistractors } from '../lib/wordOptions'
import { pickVisemeDistractors } from '../lib/visemeOptions'
import { FAST_SPEECH_SPEED } from '../lib/visemeTiming'
import useLessonTalker from '../hooks/useLessonTalker'
import { sentenceReviewSubmission } from '../lib/reviewScenario'

/**
 * 오늘의 복습(간격 반복 SRS) — 독화 레슨 공통 템플릿(핸드오프 §4-03, WordStage·Closure와 같은 틀).
 * 틀렸던 항목(입모양 그룹·단어)이 예정일에 다시 나온다. 정답이면 다음 등장이 더 멀어지고(SM-2),
 * 오답이면 내일 다시 만난다(/api/review/answer). 진행바 분모는 오늘 예정 항목 수다.
 * 단어 보기는 최소대립 짝을 먼저 넣는다(단어 레슨과 같은 규칙) — 입모양이 비슷한 단어끼리 다시 가려 보게.
 * 문장(kind 'sentence', 3단계에서 합격선 아래였던 문장, 하루 5개까지)은 입모양을 보고 문장을 입력한다. 채점은 3단계와 같은
 * /api/progress(srs_review_ 세션)라 점수 등급으로 다음 등장일이 정해지고, 3단계 숙달에는 들어가지 않는다.
 */
const shuffle = (a) => [...a].sort(() => Math.random() - 0.5)

export default function Review() {
  const navigate = useNavigate()
  const [state, setState] = useState('loading') // loading | empty | active | error
  const [items, setItems] = useState([])
  const [lessons, setLessons] = useState([])
  const [bank, setBank] = useState({ words: [], byWord: new Map() })
  const [masteredStages, setMasteredStages] = useState(new Set())   // 숙달한 단계(1 입모양, 2 단어) → '빠른 말' 열기

  const load = useCallback(() => {
    setState('loading')
    const stages = curriculumAPI.getStages().catch(() => null)   // 못 받으면 빠른 말만 닫아 둔다
    Promise.all([reviewAPI.getDue(), curriculumAPI.getVisemeLessons(), curriculumAPI.getWords(), stages])
      .then(([due, vl, wd, st]) => {
        setMasteredStages(new Set((st?.stages || []).filter((x) => x.status === 'mastered').map((x) => x.stage)))
        setLessons(vl.lessons)
        setBank({ words: wd.words.map((w) => w.word), byWord: new Map(wd.words.map((w) => [w.word, w])) })
        if (!due.items.length) { setState('empty'); return }
        setItems(due.items)
        setState('active')
      })
      .catch(() => setState('error'))
  }, [])
  useEffect(() => { load() }, [load])

  if (state === 'loading') return <LoadingScreen variant="brand" track="perception" />
  if (state === 'error') return <LoadFailed onRetry={load} onExit={() => navigate('/review')} />
  if (state === 'empty') {
    return (
      <div className="flex min-h-[100dvh] flex-col items-center justify-center gap-4 bg-page px-6 text-center">
        <h1 className="text-[24px] font-bold leading-figma text-ink">오늘 복습할 항목이 없어요</h1>
        <p className="text-[15px] text-ink-muted">틀린 입모양·단어·문장은 다음 날부터 여기서 다시 만나요.</p>
        <button type="button" onClick={() => navigate('/review')} className="btn-primary px-6 py-3 text-[15px]">복습으로 돌아가기</button>
      </div>
    )
  }
  return (
    <div className="min-h-[100dvh] bg-page">
      <ReviewSession items={items} lessons={lessons} bank={bank} masteredStages={masteredStages} />
    </div>
  )
}

function ReviewSession({ items, lessons, bank, masteredStages }) {
  const navigate = useNavigate()
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
  const sessionRef = useRef(`srs_review_${Date.now()}`)   // 문장 복습 답의 scenario_id(숙달 제외 표시)
  const [typed, setTyped] = useState('')                   // 문장 문항에 입력한 답
  const itemStartRef = useRef(Date.now())

  const item = items[idx]
  const isViseme = item.kind === 'viseme'
  const isSentence = item.kind === 'sentence'
  // 숙달한 단계의 항목은 1.25배 '빠른 말'로 볼 수 있다(docs/curriculum-roadmap.md 1-1). 복습 답은 숙달에 넣지 않는다.
  const [fast, setFast] = useState(false)
  // 복습 한 번에 가상 화자 한 명(커리큘럼 계획 2-2). 복습도 한 얼굴만 보지 않게
  const [talkerLesson] = useLessonTalker('review')
  const fastOk = masteredStages?.has(isViseme ? 1 : isSentence ? 3 : 2)
  const { targetKey, choices } = useMemo(() => {
    if (isSentence) return { targetKey: item.ref, choices: [] }   // 문장은 보기 없이 입력한다
    if (isViseme) {
      const vid = parseInt(item.ref, 10)
      const t = lessons.find((l) => l.viseme_id === vid)
      // 화면에서 가를 수 있는 무리만(lib/visemeOptions). 후보는 1단계 퀴즈와 같이 정답 모집단(quizzable)만 쓴다.
      // 전체 10개에서 뽑으면 정답이 될 수 없는 무리가 보기에 섞여 보기 구성만으로 답이 좁혀졌다(최적 추측 0.554 → 0.250).
      const others = pickVisemeDistractors(vid, lessons.filter((l) => l.quizzable))
      return { targetKey: String(vid), choices: shuffle([t, ...others].filter(Boolean)).map((l) => ({ key: String(l.viseme_id), label: l.name })) }
    }
    const distractors = pickDistractors(item.ref, bank.byWord, bank.words)
    return { targetKey: item.ref, choices: shuffle([item.ref, ...distractors]).map((w) => ({ key: w, label: w })) }
  }, [item, lessons, bank, isViseme, isSentence])

  useEffect(() => {
    setResult(null); setSelected(null); setFrames([]); setTyped('')
    itemStartRef.current = Date.now()
    if (!isViseme) learningAPI.getVisemes(item.ref).then(setFrames).catch(() => {})
  }, [item, isViseme])

  useChoiceKeys(choices, (c) => setSelected(c.key), !result && !submitting && !done)

  // 문장: 3단계와 같은 채점(/api/progress). 합격(60점 이상)이면 다음 등장이 멀어지고, 아니면 내일 다시 나온다(서버 _sr_touch)
  const confirmSentence = async () => {
    const answer = typed.trim()
    if (result || submitting || !answer) return
    setSubmitting(true)
    let res
    try {
      const secs = (Date.now() - itemStartRef.current) / 1000
      const r = await learningAPI.submitProgress(sentenceReviewSubmission(item, answer, secs, sessionRef.current))
      setXpEarned((x) => x + (r?.xp_gained || 0))
      res = { correct: r?.passed ?? (r?.score ?? 0) >= 60, score: Math.round(r?.score ?? 0), chosen: answer }
    } catch {
      res = { correct: false, score: null, chosen: answer, failed: true }   // 채점을 못 받음: 집계에서 빼고 넘어가게 한다
    } finally { setSubmitting(false) }
    setResult(res)
    if (!res.failed) setTally((t) => ({ n: t.n + 1, correct: t.correct + (res.correct ? 1 : 0) }))
  }

  const confirm = async () => {
    if (isSentence) return confirmSentence()
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
            <p className="text-[12px] font-bold text-track lg:text-[13px]">
              오늘의 복습 · {isViseme ? '입모양' : isSentence ? `문장${item.situation ? ` · ${item.situation}` : ''}` : '단어'}
            </p>
            <h1 className="text-[21px] font-bold tracking-[-0.525px] text-ink lg:text-[30px] lg:tracking-[-0.75px]">
              {isViseme ? '이 입모양은 어느 그룹일까요?' : isSentence ? '무슨 말인가요?' : '이 입모양은 어떤 단어일까요?'}
            </h1>
          </div>

          <div className="mx-auto h-[214px] w-full max-w-[560px] rounded-18 border-2 border-line bg-white p-4 lg:h-[370px] lg:rounded-22">
            <MouthAvatar height={null} className="h-full" speed={fastOk && fast ? FAST_SPEECH_SPEED : 1}
              talker={talkerLesson.talker} talkerSeed={talkerLesson.seed}
              frames={isViseme ? undefined : frames} visemeId={isViseme ? parseInt(item.ref, 10) : undefined} />
          </div>
          {fastOk && (
            <button type="button" onClick={() => setFast((v) => !v)} aria-pressed={fast}
              className={`self-center rounded px-3 py-1 text-xs transition-colors ${fast ? 'bg-primary-500 font-semibold text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}>
              빠른 말 {FAST_SPEECH_SPEED}x
            </button>
          )}

          {isSentence ? (
            <form onSubmit={(e) => { e.preventDefault(); confirm() }} className="flex flex-col gap-2">
              <label htmlFor="review-sentence" className="text-[13px] font-bold text-ink-muted">입모양을 보고 문장을 입력하세요</label>
              <input id="review-sentence" type="text" value={typed} onChange={(e) => setTyped(e.target.value)}
                disabled={!!result || submitting} autoComplete="off" placeholder="여기에 읽은 문장을 입력하세요"
                className="w-full rounded-14 border-2 border-line bg-white px-4 py-3.5 text-[17px] font-bold text-ink outline-none focus:border-track disabled:bg-surface-muted" />
            </form>
          ) : (
            <div className="flex flex-col gap-2.5 lg:gap-3">
              {choices.map((c, k) => (
                <button key={c.key} type="button" disabled={!!result || submitting} onClick={() => setSelected(c.key)}
                  aria-pressed={!result ? selected === c.key : undefined} className={OPTION_CLASS[optionState(c.key)]}>
                  <span className="flex size-6 shrink-0 items-center justify-center rounded-[7px] bg-fill text-[12px] font-bold leading-figma text-ink-muted lg:size-7 lg:rounded-lg lg:text-[13px]">{k + 1}</span>
                  <span className="flex-1 text-[18px] font-bold leading-figma lg:text-[20px]">{c.label}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className={`fixed inset-x-0 bottom-0 z-40 border-t-2 ${!result ? 'border-line bg-white' : result.correct ? 'border-good bg-good-tint lg:border-good/35' : 'border-bad bg-bad-tint lg:border-bad/35'}`}>
        <div className="mx-auto flex max-w-[676px] flex-col items-stretch gap-3 px-[18px] pb-[calc(22px+env(safe-area-inset-bottom))] pt-4 lg:h-[110px] lg:flex-row lg:items-center lg:justify-between lg:gap-4 lg:py-0">
          {result ? (
            <div role="status" aria-live="polite" className={`flex min-w-0 flex-col gap-[3px] leading-figma lg:gap-1 ${result.correct ? 'text-good-text' : 'text-bad-text'}`}>
              <p className="text-[19px] font-bold tracking-[-0.38px] lg:text-[22px] lg:tracking-[-0.44px]">
                {result.failed ? '채점하지 못했어요' : result.correct ? '정답이에요!' : '아쉬워요'}{result.score != null ? ` · ${result.score}점` : ''}
              </p>
              <p className={`${isSentence ? 'line-clamp-2' : 'truncate'} text-[13px] font-bold opacity-80 lg:text-[14px]`}>
                {result.failed ? `정답은 「${targetLabel}」 · 연결을 확인해 주세요`
                  : result.correct ? `${isSentence ? `정답은 「${targetLabel}」 · ` : ''}다음 복습은 더 나중에 나와요`
                    : `정답은 「${targetLabel}」 · 내일 다시 만나요`}
              </p>
            </div>
          ) : (
            <span className="hidden text-[15px] leading-figma text-ink-faint lg:inline">
              {isSentence ? (typed.trim() ? '정답을 확인해보세요' : '읽은 문장을 입력해주세요') : selected == null ? '보기를 선택해주세요' : '정답을 확인해보세요'}
            </span>
          )}
          {result ? (
            <button type="button" onClick={next} className={`${result.correct ? 'btn-good' : 'btn-bad'} btn-bar ${BAR_BTN}`}>계속하기</button>
          ) : (
            <button type="button" onClick={confirm} disabled={(isSentence ? !typed.trim() : selected == null) || submitting} className={`btn-primary btn-bar ${BAR_BTN}`}>확인</button>
          )}
        </div>
      </div>
    </>
  )
}

const BAR_BTN = 'w-full shrink-0 max-lg:py-4 max-lg:text-[16px] lg:w-auto'
const OPTION_BASE = 'flex w-full items-center gap-3.5 rounded-14 px-[18px] py-[15px] text-left transition-colors lg:gap-4 lg:rounded-16 lg:px-5 lg:py-4'
// 정답·오답 공개(2.5px 테두리)는 하단 테두리가 5 → 2.5px로 얇아지므로 위 패딩을 2px 더해 보기 높이를 맞춘다(변경 내역 §0-4).
const OPTION_CLASS = {
  idle: `${OPTION_BASE} border-2 border-b-5 border-line bg-white text-ink enabled:hover:border-primary-300 enabled:active:scale-[0.99]`,
  selected: `${OPTION_BASE} border-2 border-b-5 border-track bg-track-tint text-ink`,
  correct: `${OPTION_BASE} pt-[17px] lg:pt-[18px] border-[2.5px] border-good bg-good-tint text-good-text`,
  target: `${OPTION_BASE} pt-[17px] lg:pt-[18px] border-[2.5px] border-good bg-white text-ink`,
  wrong: `${OPTION_BASE} pt-[17px] lg:pt-[18px] border-[2.5px] border-bad bg-bad-tint text-bad-text`,
}
