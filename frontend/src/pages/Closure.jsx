import { useState, useEffect, useMemo, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { curriculumAPI, learningAPI } from '../api'
import MouthAvatar from '../components/MouthAvatar'
import BookmarkButton from '../components/BookmarkButton'
import LoadingScreen from '../components/LoadingScreen'
import LessonComplete from '../components/LessonComplete'
import useChoiceKeys from '../lib/useChoiceKeys'
import useBookmark from '../lib/useBookmark'

/**
 * 문맥 추론(Closure) — 독화 레슨 공통 템플릿(핸드오프 §4-03, WordStage와 같은 틀).
 * 입모양이 거의 같은 단어들(밥/맘/밤) 중 정답을 '문맥'으로 고른다. 시각 정보만으론 애매하니 문장 의미로 메꾸는 훈련.
 * 흐름: 보기 선택(클릭 또는 숫자 키 1~3) → 확인 → 정답/오답 하단 바 → 계속하기 → … 12문항 → 레슨 완료.
 * 문항 순서는 서버가 정한다 — 약한 입모양이 든 문항부터, 표준검사 문항 단어는 빠진다(/api/curriculum/closure, 축 G-6).
 * 채점은 서버가 다시 한다(/api/curriculum/closure-answer — 3단계 숙달·취약 입모양·복습·XP).
 * 시각증강 기호는 넣지 않는다 — 보기끼리 다른 자질이 기호로 드러나 문맥 훈련이 되지 않는다.
 */
const shuffle = (a) => [...a].sort(() => Math.random() - 0.5)
const QUIZ_LEN = 12
const INTRO_MS = 1000

const ENDLESS_POS_KEY = 'liplab.closure.endlessPos'

export default function Closure() {
  const [items, setItems] = useState(null)
  const [loading, setLoading] = useState(true)
  const [introDone, setIntroDone] = useState(false)
  useEffect(() => {
    curriculumAPI.getClosure().then((d) => setItems(d.items)).catch(() => setItems(null)).finally(() => setLoading(false))
    const t = setTimeout(() => setIntroDone(true), INTRO_MS)
    return () => clearTimeout(t)
  }, [])
  if (loading || !introDone) return <LoadingScreen variant="brand" track="perception" />
  if (!items || !items.length) return <div className="flex min-h-[100dvh] items-center justify-center bg-page text-[15px] text-ink-muted">불러오지 못했어요.</div>
  return (
    <div className="min-h-[100dvh] bg-page">
      <ClosureQuiz items={items} />
    </div>
  )
}

function ClosureQuiz({ items }) {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const endless = params.get('endless') === '1'   // 엔드리스 혼합 세션: 끝나면 단어 레슨으로(G-6)
  // items 안의 위치(레슨이 이어져도 계속 다음 문항). 엔드리스에서는 단어 레슨을 다녀와도 이어지게 탭 세션에 둔다.
  const [i, setI] = useState(() => {
    if (!endless) return 0
    try { return parseInt(sessionStorage.getItem(ENDLESS_POS_KEY) || '0', 10) || 0 } catch { return 0 }
  })
  const [qNum, setQNum] = useState(1)
  const [frames, setFrames] = useState([])
  const [selected, setSelected] = useState(null)
  const [result, setResult] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [hint, setHint] = useState(false)
  const [tally, setTally] = useState({ n: 0, correct: 0 })
  const [xpEarned, setXpEarned] = useState(0)
  const [done, setDone] = useState(false)
  const startRef = useRef(Date.now())
  const [elapsedSec, setElapsedSec] = useState(0)

  const item = items[i % items.length]
  const choices = useMemo(() => shuffle(item.options), [item])
  const full = item.display.replace('___', item.answer)
  // 문항 북마크 — 빈칸을 채운 문장을 저장해 '저장한 문장'에서 입모양을 다시 본다
  const [saved, toggleSaved] = useBookmark(full, { situation: '문맥 추론' })

  useEffect(() => {
    setResult(null); setSelected(null); setHint(false); setFrames([])
    learningAPI.getVisemes(full).then(setFrames).catch(() => {})
  }, [full])

  useChoiceKeys(choices, (w) => setSelected(w), !result && !submitting && !done)

  const confirm = async () => {
    if (result || submitting || selected == null) return
    setSubmitting(true)
    let correct = selected === item.answer
    let confusions = []
    try {
      const r = await curriculumAPI.submitClosure(item.id, selected)
      correct = !!r.correct
      confusions = r.confusions || []
      setXpEarned((x) => x + (r.xp_gained || 0))
    } catch { /* 기록 실패해도 진행 */ } finally { setSubmitting(false) }
    setResult({ correct, chosen: selected, confusions })
    setTally((t) => ({ n: t.n + 1, correct: t.correct + (correct ? 1 : 0) }))
  }
  const next = () => {
    if (qNum >= QUIZ_LEN) {
      setElapsedSec(Math.floor((Date.now() - startRef.current) / 1000))
      setDone(true)
      return
    }
    setQNum((n) => n + 1)
    setI((k) => k + 1)
  }
  const restart = () => {
    setDone(false); setQNum(1); setTally({ n: 0, correct: 0 }); setXpEarned(0)
    startRef.current = Date.now()
    setI((k) => k + 1)
  }
  // 나가기 — 들어온 곳(엔드리스·분석 히스토리 등)으로. 기록이 없으면 연습 탭으로.
  const exit = () => (window.history.length > 1 ? navigate(-1) : navigate('/practice/hub'))

  if (done) {
    const accuracy = tally.n ? Math.round((tally.correct / tally.n) * 100) : null
    return (
      <LessonComplete accuracy={accuracy} xp={xpEarned} elapsedSec={elapsedSec}
        onNext={endless ? () => {
          try { sessionStorage.setItem(ENDLESS_POS_KEY, String(i + 1)) } catch { /* 저장 못 해도 진행 */ }
          navigate('/learn/word?endless=1')
        } : restart}
        onHome={() => navigate(endless ? '/learn/endless' : '/practice/hub')}
        homeLabel={endless ? '엔드리스 학습으로' : '연습으로 돌아가기'} />
    )
  }

  const answered = qNum - 1 + (result ? 1 : 0)
  const pct = Math.round((answered / QUIZ_LEN) * 100)
  const optionState = (w) => {
    if (!result) return selected === w ? 'selected' : 'idle'
    if (w === item.answer) return result.chosen === w ? 'correct' : 'target'
    return result.chosen === w ? 'wrong' : 'idle'
  }
  const [before, after] = item.display.split('___')

  return (
    <>
      <div className="mx-auto flex w-full max-w-[676px] flex-col px-[18px] pb-[200px] pt-[18px] lg:pb-[150px] lg:pt-7">
        {/* 진행 헤더 — 나가기 X + 트랙 + n / 12 */}
        <div className="flex items-center gap-3 lg:gap-[18px]">
          <button type="button" onClick={exit} aria-label="나가기" className="shrink-0">
            <img src="/ui/lp-91-12-close.svg" alt="" className="size-8 lg:size-9" />
          </button>
          <div className="h-3 flex-1 overflow-hidden rounded-full bg-fill-strong lg:h-[14px]">
            <div className="h-full rounded-full bg-track transition-all duration-500" style={{ width: `${pct}%` }} />
          </div>
          <span className="shrink-0 text-[13px] font-bold leading-figma text-ink-muted lg:text-[15px]">{qNum} / {QUIZ_LEN}</span>
        </div>

        <div className="mt-6 flex flex-col gap-4 lg:mt-5 lg:gap-5">
          <div className="relative flex flex-col gap-1.5 pr-12 leading-figma lg:gap-2 lg:pr-[52px]">
            <p className="text-[12px] font-bold text-track lg:text-[13px]">문맥 추론</p>
            <h1 className="text-[21px] font-bold tracking-[-0.525px] text-ink lg:text-[30px] lg:tracking-[-0.75px]">빈칸에 들어갈 말은?</h1>
            <BookmarkButton active={saved} onToggle={toggleSaved} className="absolute right-0 top-[14px] lg:top-[21px]" />
          </div>

          {/* 입모양 카드 — 문장 전체를 말한다. 보기는 입모양이 같아 문맥으로 골라야 한다 */}
          <div className="mx-auto h-[214px] w-full max-w-[560px] rounded-18 border-2 border-line bg-white p-4 lg:h-[370px] lg:rounded-22">
            <MouthAvatar key={item.id} frames={frames} height={null} className="h-full" />
          </div>

          {/* 빈칸 문장 + 힌트 */}
          <div className="flex flex-col items-center gap-2.5 rounded-18 border-2 border-line bg-white px-4 py-4 lg:rounded-22">
            <p className="text-center text-[21px] font-bold leading-figma tracking-[-0.3px] text-ink lg:text-[24px]">
              {result
                ? full
                : <>{before}<span className="mx-1 inline-block min-w-[2.2em] border-b-[3px] border-track align-baseline text-transparent">빈칸</span>{after}</>}
            </p>
            {!result && (hint
              ? <p className="text-center text-[14px] font-bold leading-figma text-warn-text">{item.hint}</p>
              : <button type="button" onClick={() => setHint(true)} className="rounded-full bg-warn-tint px-3 py-1 text-[12px] font-bold text-warn-text hover:brightness-95">힌트 보기</button>)}
          </div>

          {/* 3지선다 — 선택 → 확인 */}
          <div className="flex flex-col gap-2.5 lg:gap-3">
            {choices.map((w, k) => (
              <button key={w} type="button" disabled={!!result || submitting} onClick={() => setSelected(w)}
                aria-pressed={!result ? selected === w : undefined} className={OPTION_CLASS[optionState(w)]}>
                <span className="flex size-6 shrink-0 items-center justify-center rounded-[7px] bg-fill text-[12px] font-bold leading-figma text-ink-muted lg:size-7 lg:rounded-lg lg:text-[13px]">{k + 1}</span>
                <span className="flex-1 text-[18px] font-bold leading-figma lg:text-[20px]">{w}</span>
              </button>
            ))}
          </div>

          <AnimatePresence>
            {result && !result.correct && result.confusions?.length > 0 && (
              <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                className="space-y-1.5 rounded-16 border-2 border-warn/40 bg-warn-tint p-4">
                <p className="text-xs font-bold text-warn-text">왜 헷갈렸나요?</p>
                {result.confusions.map((cf, k) => (
                  <p key={k} className="text-[13px] leading-snug text-warn-text">
                    {cf.position} <b>‘{cf.target}’</b>↔<b>‘{cf.read}’</b>{' '}
                    {cf.same_viseme
                      ? <>둘 다 <b>{cf.viseme_name_ko}</b>이라 입모양만으로는 구별되지 않아요. 문장의 뜻으로 골라야 해요.</>
                      : <>정답은 <b>{cf.viseme_name_ko}</b> 입모양이에요.</>}
                  </p>
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* 하단 고정 바 — 문제 · 정답 · 오답(WordStage와 같은 규격) */}
      <div className={`fixed inset-x-0 bottom-0 z-40 border-t-2 ${!result ? 'border-line bg-white' : result.correct ? 'border-good bg-good-tint lg:border-good/35' : 'border-bad bg-bad-tint lg:border-bad/35'}`}>
        <div className="mx-auto flex max-w-[676px] flex-col items-stretch gap-3 px-[18px] pb-[calc(22px+env(safe-area-inset-bottom))] pt-4 lg:h-[110px] lg:flex-row lg:items-center lg:justify-between lg:gap-4 lg:py-0">
          {result ? (
            <div role="status" aria-live="polite" className={`flex min-w-0 flex-col gap-[3px] leading-figma lg:gap-1 ${result.correct ? 'text-good-text' : 'text-bad-text'}`}>
              <p className="text-[19px] font-bold tracking-[-0.38px] lg:text-[22px] lg:tracking-[-0.44px]">{result.correct ? '정답이에요!' : '아쉬워요'}</p>
              <p className="truncate text-[13px] font-bold opacity-80 lg:text-[14px]">정답은 「{item.answer}」예요</p>
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
