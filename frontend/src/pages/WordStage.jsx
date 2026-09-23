import { useState, useEffect, useMemo, useCallback, useRef, lazy, Suspense } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { curriculumAPI, learningAPI } from '../api'
import MouthAvatar from '../components/MouthAvatar'
import BookmarkButton from '../components/BookmarkButton'
import WatermarkCard from '../components/WatermarkCard'
import LoadingScreen from '../components/LoadingScreen'
import { ModalClose } from '../components/Modal'
import useFocusTrap from '../hooks/useFocusTrap'
import useChoiceKeys from '../lib/useChoiceKeys'
import useBookmark from '../lib/useBookmark'
import CueBadges, { CueLegend } from '../components/CueBadges'

// 트랙B(언어+독화) 앵커링: 단어의 뜻을 수어로 확인. 무거우니 열 때만 로드.
const SignPanel = lazy(() => import('../components/SignPanel'))
// 축 D 자체 립리딩(MediaPipe+onnx로 무거움) — 정답 후에만 로드.
const LipReadCheck = lazy(() => import('../components/LipReadCheck'))

/**
 * 2단계 · 음절·단어 (Word Stage) — 독화 레슨 공통 템플릿(핸드오프 §4-03).
 * Figma: 문제 91:12 · 정답 94:98 · 오답 94:140 · 완료 93:12, 모바일 235:34 · 235:71(lg 미만).
 * 입모양만 보고 어떤 단어인지 4지선다로 맞힌다. 오답 보기는 최소대립 단어 우선.
 * 흐름: 보기 선택(클릭 또는 숫자 키 1~4) → 확인 → 정답/오답 하단 바 → 계속하기 → … 12문항 → 레슨 완료.
 * 채점·혼동진단·립리딩·수어·숙달 로직은 그대로다(숙달은 서버가 문항마다 rolling으로 판정).
 */
const shuffle = (a) => [...a].sort(() => Math.random() - 0.5)
const QUIZ_LEN = 12  // 레슨 1회 문항 수(진행바 분모) — 숙달 판정과 별개
// 레슨 시작 전 트랙 로딩(§4-10 223:30)을 최소 이만큼은 보인다 — 데이터가 빨리 와도 한 번 번쩍이고 끝나지 않게.
const INTRO_MS = 1000
const OVERFLOW = { top: '-7%', left: '-12%', width: '124%', height: '124%' }   // 마스코트 SVG 그림자 여백(Figma inset)

function partnersOf(word, pairs, bankSet) {
  const out = new Set()
  for (const m of pairs) {
    if (m.a === word && bankSet.has(m.b)) out.add(m.b)
    if (m.b === word && bankSet.has(m.a)) out.add(m.a)
  }
  return [...out]
}

const fmtDuration = (sec) => `${Math.floor(sec / 60)}분 ${sec % 60}초`

// 레슨 완료 스탯 카드(93:22) — 모바일은 카드 폭이 좁아 여백·값 글자를 줄인다(모바일 프레임 없음).
const STAT_CARD = 'flex min-w-0 flex-1 flex-col gap-2 rounded-18 border-2 border-line bg-white p-3.5 lg:p-5'
const STAT_LABEL = 'text-[13px] font-bold leading-figma text-ink-soft'
const STAT_VALUE = 'text-[20px] font-bold leading-figma tracking-[-0.5px] lg:text-[28px] lg:tracking-[-0.7px]'
// 완료 버튼 — 데스크톱 75:23(btn-lg), lg 미만은 모바일 버튼 규격(r14·b5, py16, 16px)
const DONE_BTN = 'w-full max-lg:rounded-14 max-lg:border-b-5 max-lg:py-4 max-lg:text-[16px]'

// Figma "Lesson / 4. 완료"(93:12) — 레슨 컴포넌트의 마지막 상태. DOKA + 워터마크 스탯 3칸 + 버튼 2개.
function LessonComplete({ accuracy, xp, elapsedSec, onNext, onHome }) {
  return (
    <div className="flex min-h-[100dvh] w-full flex-col items-center justify-center gap-[26px] bg-page px-[18px] py-12">
      <span className="relative size-[140px] shrink-0">
        <img src="/ui/lp-93-12-mascot.svg" alt="" className="absolute max-w-none" style={OVERFLOW} />
      </span>
      <h1 className="text-center text-[38px] font-bold leading-figma tracking-[-0.95px] text-ink">레슨 완료!</h1>

      <div className="flex w-full max-w-[640px] gap-3.5 py-2">
        <WatermarkCard className={STAT_CARD} deco={{ src: '/ui/lp-93-12-deco-percent.svg', size: 115.2, top: -45.83, right: -43.82 }}>
          <p className={STAT_LABEL}>정답률</p>
          <p className={`${STAT_VALUE} text-primary-700`}>{accuracy}%</p>
        </WatermarkCard>
        <WatermarkCard className={STAT_CARD} deco={{ src: '/ui/lp-93-12-deco-xp.svg', size: 157.945, top: -76, right: -71.44 }}>
          <p className={STAT_LABEL}>획득 XP</p>
          <p className={`${STAT_VALUE} text-warn-text`}>+{xp}</p>
        </WatermarkCard>
        <WatermarkCard className={STAT_CARD} deco={{ src: '/ui/lp-93-12-deco-clock.svg', size: 115.2, top: -45.83, right: -43.82 }}>
          <p className={STAT_LABEL}>걸린 시간</p>
          <p className={`${STAT_VALUE} text-stat-level`}>{fmtDuration(elapsedSec)}</p>
        </WatermarkCard>
      </div>

      <div className="flex w-full max-w-[640px] flex-col gap-2.5 lg:gap-3">
        <button type="button" onClick={onNext} className={`btn-primary btn-lg ${DONE_BTN}`}>다음 레슨으로</button>
        <button type="button" onClick={onHome} className={`btn-secondary btn-lg text-track ${DONE_BTN}`}>커리큘럼으로 돌아가기</button>
      </div>
    </div>
  )
}

export default function WordStage() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [introDone, setIntroDone] = useState(false)
  useEffect(() => {
    curriculumAPI.getWords().then(setData).catch(() => setData(null)).finally(() => setLoading(false))
    const t = setTimeout(() => setIntroDone(true), INTRO_MS)
    return () => clearTimeout(t)
  }, [])
  // 레슨 시작 전 = 독화 트랙 로딩(223:30 / 모바일 243:81)
  if (loading || !introDone) return <LoadingScreen variant="brand" track="perception" />
  if (!data) return <div className="flex min-h-[100dvh] items-center justify-center bg-page text-[15px] text-ink-muted">불러오지 못했어요.</div>
  return (
    <div className="min-h-[100dvh] bg-page">
      <WordQuiz data={data} />
    </div>
  )
}

function WordQuiz({ data }) {
  const navigate = useNavigate()
  const words = useMemo(() => data.words.map((w) => w.word), [data])
  const tierOf = useMemo(() => Object.fromEntries(data.words.map((w) => [w.word, w.tier || 1])), [data])
  const bankSet = useMemo(() => new Set(words), [words])
  const [q, setQ] = useState(null)
  // 문항 북마크 — 서버에 저장돼 복습 탭·저장한 문장에 나온다
  const [saved, toggleSaved] = useBookmark(q?.target, { situation: '단어 독화' })
  const [frames, setFrames] = useState([])
  const [selected, setSelected] = useState(null)   // 확인 전 선택(선택→확인 2단계)
  const [result, setResult] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [stat, setStat] = useState({ attempts: 0, mastery: 0, mastered: false })
  const [qNum, setQNum] = useState(1)              // 레슨 내 문항 번호(진행바)
  const [tally, setTally] = useState({ n: 0, correct: 0 })   // 이번 레슨에서 푼 문항·정답 수 → 완료 뷰 정답률
  const [done, setDone] = useState(false)          // 12문항을 마치면 완료 뷰(93:12)
  const [signOpen, setSignOpen] = useState(false)
  const closeSign = useCallback(() => setSignOpen(false), [])
  const signRef = useFocusTrap(signOpen, closeSign)          // 수어 모달 포커스 트랩·Esc
  const [xpEarned, setXpEarned] = useState(0)      // 레슨 동안 서버가 준 XP 합(응답 xp_gained) → 완료 뷰
  const startRef = useRef(Date.now())              // 레슨 시작 시각 → 걸린 시간
  const [elapsedSec, setElapsedSec] = useState(0)

  const newQ = useCallback(async () => {
    const pool = data.words
    const total = pool.reduce((s, w) => s + (w.priority || 1), 0)
    let r = Math.random() * total
    let target = pool[pool.length - 1].word
    for (const w of pool) { r -= (w.priority || 1); if (r <= 0) { target = w.word; break } }
    const partners = partnersOf(target, data.minimal_pairs, bankSet)
    const rest = shuffle(words.filter((w) => w !== target && !partners.includes(w)))
    const distractors = [...shuffle(partners), ...rest].slice(0, 3)
    setResult(null)
    setSelected(null)
    setQ({ target, choices: shuffle([target, ...distractors]) })
    setFrames([])
    try { setFrames(await learningAPI.getVisemes(target)) } catch { /* ignore */ }
  }, [data, words, bankSet])

  useEffect(() => { newQ() }, [newQ])

  // 보기 숫자 키 1~4(§4-03) — 채점 중·결과 표시 중·수어 창이 열려 있으면 받지 않는다.
  useChoiceKeys(q?.choices, (w) => setSelected(w), !!q && !result && !submitting && !signOpen && !done)

  const confirm = async () => {
    if (result || submitting || selected == null) return
    setSubmitting(true)
    const correct = selected === q.target
    let confusions = []
    try {
      const rr = await curriculumAPI.submitWord(q.target, correct, selected)
      setStat({ attempts: rr.attempts, mastery: rr.mastery_score, mastered: rr.mastered })
      confusions = rr.confusions || []
      setXpEarned((x) => x + (rr.xp_gained || 0))
    } catch { /* 기록 실패해도 진행 */ } finally { setSubmitting(false) }
    setResult({ correct, chosen: selected, confusions })
    setTally((t) => ({ n: t.n + 1, correct: t.correct + (correct ? 1 : 0) }))
  }
  // 계속하기 — 12번째 문항 뒤에는 완료 뷰로(걸린 시간은 이 순간으로 고정).
  const next = () => {
    if (qNum >= QUIZ_LEN) {
      setElapsedSec(Math.floor((Date.now() - startRef.current) / 1000))
      setDone(true)
      return
    }
    setQNum((n) => n + 1)
    newQ()
  }
  // 새 레슨(12문항) — 단계를 아직 숙달하지 못했을 때 '다음 레슨으로'가 같은 단계의 다음 세트를 연다.
  const restart = () => {
    setDone(false); setQNum(1); setTally({ n: 0, correct: 0 }); setXpEarned(0)
    startRef.current = Date.now()
    newQ()
  }

  if (!q) return null

  if (done) {
    const accuracy = tally.n ? Math.round((tally.correct / tally.n) * 100) : 0
    return (
      // 다음 레슨: 단계를 숙달했으면 3단계 문장(시나리오 선택 ScenarioHub → /practice. CurriculumPath READ_ROUTE와
      // 같은 진입점), 아니면 이 단계의 다음 12문항.
      <LessonComplete accuracy={accuracy} xp={xpEarned} elapsedSec={elapsedSec}
        onNext={() => (stat.mastered ? navigate('/learn/scenario') : restart())}
        onHome={() => navigate('/learn/path')} />
    )
  }

  const answered = qNum - 1 + (result ? 1 : 0)
  const pct = Math.round((answered / QUIZ_LEN) * 100)

  const optionState = (w) => {
    if (!result) return selected === w ? 'selected' : 'idle'
    if (w === q.target) return result.chosen === w ? 'correct' : 'target'
    return result.chosen === w ? 'wrong' : 'idle'
  }

  return (
    <>
      <div className="mx-auto flex w-full max-w-[676px] flex-col px-[18px] pb-[200px] pt-[18px] lg:pb-[150px] lg:pt-7">
        {/* 진행 헤더(91:13 / 모바일 235:35) — 나가기 X + 트랙 + n / 12 */}
        <div className="flex items-center gap-3 lg:gap-[18px]">
          <button type="button" onClick={() => navigate('/learn/path')} aria-label="나가기" className="shrink-0">
            <img src="/ui/lp-91-12-close.svg" alt="" className="size-8 lg:size-9" />
          </button>
          <div className="h-3 flex-1 overflow-hidden rounded-full bg-fill-strong lg:h-[14px]">
            <div className="h-full rounded-full bg-track transition-all duration-500" style={{ width: `${pct}%` }} />
          </div>
          <span className="shrink-0 text-[13px] font-bold leading-figma text-ink-muted lg:text-[15px]">{qNum} / {QUIZ_LEN}</span>
        </div>

        <div className="mt-6 flex flex-col gap-4 lg:mt-5 lg:gap-5">
          {/* 질문 + 북마크(91:19 · 328:40 / 모바일 235:42 · 328:64) */}
          <div className="relative flex flex-col gap-1.5 pr-12 leading-figma lg:gap-2 lg:pr-[52px]">
            <p className="text-[12px] font-bold text-track lg:text-[13px]">단어 독화</p>
            <h1 className="text-[21px] font-bold tracking-[-0.525px] text-ink lg:text-[30px] lg:tracking-[-0.75px]">이 입모양은 어떤 단어일까요?</h1>
            <BookmarkButton active={saved} onToggle={toggleSaved} className="absolute right-0 top-[14px] lg:top-[21px]" />
          </div>

          {/* 입모양 카드(91:22 560×370 / 모바일 235:45 전체 폭×214) — 아바타만, 무한 반복(다시 보기 없음) */}
          <div className="mx-auto h-[214px] w-full max-w-[560px] rounded-18 border-2 border-line bg-white p-4 lg:h-[370px] lg:rounded-22">
            {/* 시각증강 기호(축 J-3)는 답을 확인한 뒤에만 — 보기가 최소대립 짝이라 문제 중에 보이면 기호만으로 답이 드러난다.
                확인 뒤에는 약한 표적 입모양 음절에만 입꼬리 옆에 겹쳐 무엇이 달랐는지 보여 준다(숙달되면 흐려짐). */}
            <MouthAvatar key={q.target} frames={frames} height={null} className="h-full" cueText={result ? q.target : null} cueFocus />
          </div>

          {/* 4지선다(91:28 / 모바일 235:51) — 선택 → 확인 */}
          <div className="flex flex-col gap-2.5 lg:gap-3">
            {q.choices.map((w, i) => (
              <button key={w} type="button" disabled={!!result || submitting} onClick={() => setSelected(w)}
                aria-pressed={!result ? selected === w : undefined} className={OPTION_CLASS[optionState(w)]}>
                <span className="flex size-6 shrink-0 items-center justify-center rounded-[7px] bg-fill text-[12px] font-bold leading-figma text-ink-muted lg:size-7 lg:rounded-lg lg:text-[13px]">{i + 1}</span>
                <span className="flex-1 text-[18px] font-bold leading-figma lg:text-[20px]">{w}</span>
              </button>
            ))}
          </div>

          {/* 결과 피드백(혼동 진단·큐·수어·립리딩) — 핵심 교육 패널이라 유지, 고정 바 위 스크롤 영역 */}
          <AnimatePresence>
            {result && (
              <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-3">
                {!result.correct && result.confusions?.length > 0 && (
                  <div className="space-y-1.5 rounded-16 border-2 border-warn/40 bg-warn-tint p-4">
                    <p className="text-xs font-bold text-warn-text">어디서 헷갈렸나요?</p>
                    {result.confusions.map((cf, i) => (
                      <p key={i} className="text-[13px] leading-snug text-warn-text">
                        {cf.position} <b>‘{cf.target}’</b>을(를) <b>‘{cf.read}’</b>로 읽으셨어요 —{' '}
                        {cf.same_viseme
                          ? <>둘 다 <b>{cf.viseme_name_ko}</b>이라 입모양만으론 똑같이 보여요. 문맥·자막으로 구분하는 연습이 필요합니다.</>
                          : <>정답은 <b>{cf.viseme_name_ko}</b> 입모양입니다. 그 차이를 눈에 익혀보세요.</>}
                      </p>
                    ))}
                  </div>
                )}
                <div className="rounded-16 border-2 border-line bg-white p-3">
                  <div className="flex items-center gap-2">
                    <CueBadges text={q.target} />
                    <span className="text-[11px] text-ink-faint">난이도 {tierOf[q.target] || 1}</span>
                  </div>
                  <div className="mt-1.5"><CueLegend /></div>
                </div>
                <button type="button" onClick={() => setSignOpen(true)}
                  className="btn-secondary w-full py-2.5 text-[14px] text-track">
                  "{q.target}" 수어로 뜻 보기
                </button>
                <Suspense fallback={null}>
                  <LipReadCheck target={q.target} candidates={q.choices} />
                </Suspense>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* 하단 고정 바 — 문제(130:17) · 정답(94:133) · 오답(94:175). lg 미만(235:68 · 235:105)은 힌트 없이
          메시지 위·전체 폭 버튼 아래로 쌓는다(§4-12 "모바일 레슨의 하단 버튼은 전체 폭"). */}
      <div className={`fixed inset-x-0 bottom-0 z-40 border-t-2 ${!result ? 'border-line bg-white' : result.correct ? 'border-good bg-good-tint lg:border-good/35' : 'border-bad bg-bad-tint lg:border-bad/35'}`}>
        <div className="mx-auto flex max-w-[676px] flex-col items-stretch gap-3 px-[18px] pb-[calc(22px+env(safe-area-inset-bottom))] pt-4 lg:h-[110px] lg:flex-row lg:items-center lg:justify-between lg:gap-4 lg:py-0">
          {result ? (
            // 정오 피드백은 스크린리더에 알린다(role=status·aria-live) — 잔존청력·저시력 사용자 대상(c92fdc3, 병합 복원)
            <div role="status" aria-live="polite" className={`flex min-w-0 flex-col gap-[3px] leading-figma lg:gap-1 ${result.correct ? 'text-good-text' : 'text-bad-text'}`}>
              <p className="text-[19px] font-bold tracking-[-0.38px] lg:text-[22px] lg:tracking-[-0.44px]">{result.correct ? '정답이에요!' : '아쉬워요'}</p>
              <p className="truncate text-[13px] font-bold opacity-80 lg:text-[14px]">정답은 「{q.target}」예요</p>
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

      <AnimatePresence>
        {signOpen && (
          <motion.div className="fixed inset-0 z-50 flex justify-end bg-overlay/50"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            onClick={() => setSignOpen(false)}>
            <motion.div ref={signRef} role="dialog" aria-modal="true"
              aria-label={`${q?.target || ''} 수어 번역`} tabIndex={-1}
              className="h-full w-full max-w-2xl overflow-y-auto bg-white shadow-modal outline-none"
              initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }}
              transition={{ type: 'tween', duration: 0.25 }}
              onClick={(e) => e.stopPropagation()}>
              <div className="sticky top-0 z-10 flex items-center justify-between border-b-1.5 border-line bg-white px-5 py-3">
                <p className="font-bold text-ink">"{q.target}" 수어</p>
                <ModalClose onClose={() => setSignOpen(false)} />
              </div>
              <div className="p-5">
                <Suspense fallback={<div className="py-10 text-center text-sm text-ink-faint">불러오는 중…</div>}>
                  <SignPanel text={q.target} />
                </Suspense>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}

// 하단 바 버튼 — 데스크톱 .btn-bar(40/15, 17px) 오른쪽, lg 미만 전체 폭 py16·16px(235:69 · 235:109)
const BAR_BTN = 'w-full shrink-0 max-lg:py-4 max-lg:text-[16px] lg:w-auto'

// 보기 한 줄(91:29 / 모바일 235:52) — 기본 3D 하단테두리. 정답·오답 공개(94:119 · 94:161 · 94:169)는 2.5px 테두리.
const OPTION_BASE = 'flex w-full items-center gap-3.5 rounded-14 px-[18px] py-[15px] text-left transition-colors lg:gap-4 lg:rounded-16 lg:px-5 lg:py-4'
const OPTION_CLASS = {
  idle: `${OPTION_BASE} border-2 border-b-5 border-line bg-white text-ink enabled:hover:border-primary-300 enabled:active:scale-[0.99]`,
  selected: `${OPTION_BASE} border-2 border-b-5 border-track bg-track-tint text-ink`,
  correct: `${OPTION_BASE} border-[2.5px] border-good bg-good-tint text-good-text`,   // 고른 답이 정답
  target: `${OPTION_BASE} border-[2.5px] border-good bg-white text-ink`,              // 오답일 때 정답 표시
  wrong: `${OPTION_BASE} border-[2.5px] border-bad bg-bad-tint text-bad-text`,        // 고른 오답
}
