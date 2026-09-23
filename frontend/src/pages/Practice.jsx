import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import useStore from '../store/useStore'
import { learningAPI } from '../api'
import LipSyncPlayer3D from '../components/LipSyncPlayer3D'
import MouthAvatar from '../components/MouthAvatar'
import QuizForm from '../components/QuizForm'
import SignPanel from '../components/SignPanel'
import BookmarkButton from '../components/BookmarkButton'
import WatermarkCard from '../components/WatermarkCard'
import LoadingScreen from '../components/LoadingScreen'
import { ModalClose } from '../components/Modal'
import CueBadges, { CueLegend } from '../components/CueBadges'
import useFocusTrap from '../hooks/useFocusTrap'
import useChoiceKeys from '../lib/useChoiceKeys'

/**
 * 힌트 시스템: 단계별로 문장 정보를 공개
 * Level 0: 힌트 없음
 * Level 1: 음절 수 (● ● ● ●)
 * Level 2: 첫 글자 공개 (안● ● ●)
 * Level 3: 발음 타이밍에 맞춰 전체 공개
 */
function HintDisplay({ sentence, hintLevel, revealedTextIndex = -1 }) {
  if (!sentence) return null

  const chars = sentence.replace(/ /g, '')
  const words = sentence.split(' ')

  if (hintLevel === 0) return null

  if (hintLevel === 1) {
    // 음절 수만 표시
    return (
      <div className="mt-3 p-3 bg-amber-50 border border-amber-200 rounded-lg">
        <p className="text-xs text-amber-600 font-medium mb-1">힌트 1 — 글자 수</p>
        <div className="flex flex-wrap gap-2">
          {words.map((word, wi) => (
            <div key={wi} className="flex gap-1">
              {word.split('').map((_, ci) => (
                <span key={ci} className="w-7 h-7 rounded-full bg-amber-300 flex items-center justify-center text-amber-800 font-bold text-sm">
                  ●
                </span>
              ))}
            </div>
          ))}
        </div>
        <p className="text-xs text-amber-500 mt-1">{chars.length}글자</p>
      </div>
    )
  }

  if (hintLevel === 2) {
    // 첫 글자 + 나머지 빈칸
    return (
      <div className="mt-3 p-3 bg-blue-50 border border-blue-200 rounded-lg">
        <p className="text-xs text-blue-600 font-medium mb-1">힌트 2 — 첫 글자</p>
        <div className="flex flex-wrap gap-2">
          {words.map((word, wi) => (
            <div key={wi} className="flex gap-1">
              {word.split('').map((char, ci) => (
                <span key={ci} className={`w-7 h-7 rounded border-2 flex items-center justify-center text-sm font-bold ${
                  ci === 0
                    ? 'bg-blue-100 border-blue-400 text-blue-800'
                    : 'bg-white border-gray-300 text-gray-400'
                }`}>
                  {ci === 0 ? char : '_'}
                </span>
              ))}
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (hintLevel >= 3) {
    // 입모양 프레임의 원문 위치에 맞춰 음절별로 공개
    const sentenceChars = Array.from(sentence)

    return (
      <div className="mt-3 p-3 bg-green-50 border border-green-200 rounded-lg">
        <p className="text-xs text-green-600 font-medium mb-1">힌트 3 — 발음 자막</p>
        <p className="sr-only">{sentence}</p>
        <p aria-hidden="true" className="text-lg font-bold text-green-800 tracking-wide">
          {sentenceChars.map((char, index) => (
            <motion.span
              key={`${index}-${char}`}
              className="inline-block whitespace-pre"
              initial={false}
              animate={index <= revealedTextIndex
                ? { opacity: 1, y: 0, filter: 'blur(0px)' }
                : { opacity: 0, y: 4, filter: 'blur(3px)' }}
              transition={{ duration: 0.28, ease: 'easeOut' }}
            >
              {char}
            </motion.span>
          ))}
        </p>
        <p className="text-xs text-green-600/80 mt-1.5">
          입모양 재생에 맞춰 자막이 나타납니다.
        </p>
      </div>
    )
  }

  return null
}

// 4지선다 정답 판정(94:98/94:140) — 고른 문장이 정답 문장과 같으면 정답. 주관식·서술형은 기존 화면의 '정답' 기준(80점).
const CORRECT_SCORE = 80
// 레슨 시작 전 트랙 로딩(§4-10 223:30)을 최소 이만큼은 보인다 — 첫 문장 입모양이 빨리 와도 한 번 번쩍이고 끝나지 않게.
const INTRO_MS = 1000
const OVERFLOW = { top: '-7%', left: '-12%', width: '124%', height: '124%' }   // 마스코트 SVG 그림자 여백(Figma inset)
const fmtDuration = (sec) => `${Math.floor(sec / 60)}분 ${sec % 60}초`

// 레슨 완료 스탯 카드(93:22) — 모바일은 카드 폭이 좁아 여백·값 글자를 줄인다(모바일 프레임 없음).
const STAT_CARD = 'flex min-w-0 flex-1 flex-col gap-2 rounded-18 border-2 border-line bg-white p-3.5 lg:p-5'
const STAT_LABEL = 'text-[13px] font-bold leading-figma text-ink-soft'
const STAT_VALUE = 'text-[20px] font-bold leading-figma tracking-[-0.5px] lg:text-[28px] lg:tracking-[-0.7px]'
const DONE_BTN = 'w-full max-lg:rounded-14 max-lg:border-b-5 max-lg:py-4 max-lg:text-[16px]'

// Figma "Lesson / 4. 완료"(93:12) — 마지막 문장 뒤 레슨 컴포넌트의 마지막 상태.
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
          <p className={`${STAT_VALUE} text-primary-700`}>{accuracy == null ? '-' : `${accuracy}%`}</p>
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

// 하단 바 버튼 — 데스크톱 .btn-bar(40/15, 17px) 오른쪽, lg 미만 전체 폭 py16·16px(235:69 · 235:109)
const BAR_BTN = 'w-full shrink-0 max-lg:py-4 max-lg:text-[16px] lg:w-auto'
// 보기 한 줄(91:29 / 모바일 235:52) — 기본 3D 하단테두리. 정답·오답 공개(94:119 · 94:161 · 94:169)는 2.5px 테두리.
const OPTION_BASE = 'flex w-full items-center gap-3.5 rounded-14 px-[18px] py-[15px] text-left transition-colors lg:gap-4 lg:rounded-16 lg:px-5 lg:py-4'
const OPTION_CLASS = {
  idle: `${OPTION_BASE} border-2 border-b-5 border-line bg-white text-ink enabled:hover:border-primary-300 enabled:active:scale-[0.99]`,
  selected: `${OPTION_BASE} border-2 border-b-5 border-track bg-track-tint text-ink`,
  correct: `${OPTION_BASE} border-[2.5px] border-good bg-good-tint text-good-text`,
  target: `${OPTION_BASE} border-[2.5px] border-good bg-white text-ink`,
  wrong: `${OPTION_BASE} border-[2.5px] border-bad bg-bad-tint text-bad-text`,
}

/**
 * 3단계 · 문장 (상황별) — 레슨 집중 모드(핸드오프 §3.4): AppShell 없이 전체 화면, 상단 X + 진행률 + n / 전체.
 * 문장마다 유형이 다르다(주관식 · 4지선다 · 서술형, 학습 모드는 문장 보기). 4지선다는 독화 레슨 공통 템플릿
 * (§4-03 — 91:12 · 94:98 · 94:140, 모바일 235:34 · 235:71)으로 그리고, 마지막 문장 뒤에 레슨 완료(93:12)를 띄운다.
 * 채점(submitProgress)·힌트·수어·북마크 저장 로직은 그대로다.
 */
export default function Practice() {
  const navigate = useNavigate()
  const user = useStore((state) => state.user)
  const currentScenario = useStore((state) => state.currentScenario)
  const currentSentence = useStore((state) => state.currentSentence)
  const currentSentenceIndex = useStore((state) => state.currentSentenceIndex)
  const nextSentence = useStore((state) => state.nextSentence)
  const resetPractice = useStore((state) => state.resetPractice)
  const updateUser = useStore((state) => state.updateUser)
  const practiceMode = useStore((state) => state.practiceMode) // 'study' | 'test'

  // 테스트는 문장마다 유형이 다르다: 주관식(test) · 4지선다(test-multiple) · 서술형(essay)
  const qType = currentScenario?.qTypes?.[currentSentenceIndex]
  const effectiveMode = practiceMode === 'study' ? 'study' : (qType || 'test')
  // 독화 복습(틀린 문장 다시 풀기)에서 넘어온 세션인지 — ReviewLanding이 심어둔 scenario_id로 판별
  const isReviewSession = !!currentScenario?.scenario_id?.startsWith('mistake_review_')

  const [visemes, setVisemes] = useState([])
  const [isPlaying, setIsPlaying] = useState(false)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState(null)
  const [startTime, setStartTime] = useState(null)
  const [hintLevel, setHintLevel] = useState(0)
  const [revealedTextIndex, setRevealedTextIndex] = useState(-1)
  const [subtitleRestartKey, setSubtitleRestartKey] = useState(0)
  const [selectedChoice, setSelectedChoice] = useState(null) // 4지선다에서 고른 보기(확인 전)
  const [signOpen, setSignOpen] = useState(false)            // 수어 보기 모달
  const [bookmarks, setBookmarks] = useState({})             // 문장 텍스트 → 북마크 id (저장)
  const [booted, setBooted] = useState(false)                // 첫 문장 입모양을 받았는지(레슨 시작 전 로딩)
  const [introDone, setIntroDone] = useState(false)          // 레슨 시작 전 로딩 최소 표시 시간
  const [tally, setTally] = useState({ n: 0, correct: 0 })   // 이번 레슨의 채점 문항·정답 수 → 완료 정답률
  const [xpEarned, setXpEarned] = useState(0)                // 이번 레슨에서 서버가 준 XP 합(xp_gained)
  const lessonStartRef = useRef(Date.now())
  const [elapsedSec, setElapsedSec] = useState(0)
  const closeSign = useCallback(() => setSignOpen(false), [])
  const signRef = useFocusTrap(signOpen, closeSign)          // 수어 모달 포커스 트랩·Esc

  // 4지선다 보기 생성 — 정답 1개 + 다른 문장 3개, 랜덤 순서
  const choices = useMemo(() => {
    if (!currentScenario || !currentSentence) return []
    const others = currentScenario.sentences
      .filter((s) => s !== currentSentence)
      .sort(() => Math.random() - 0.5)
      .slice(0, 3)
    return [...others, currentSentence].sort(() => Math.random() - 0.5)
  }, [currentSentence])

  useEffect(() => {
    if (!currentScenario) {
      navigate('/dashboard')
      return
    }
    loadVisemes()
  }, [currentSentence])

  useEffect(() => {
    const t = setTimeout(() => setIntroDone(true), INTRO_MS)
    return () => clearTimeout(t)
  }, [])

  // 보기 숫자 키 1~4(§4-03) — 4지선다 문항에서 채점 전에만, 수어 창이 열려 있으면 받지 않는다.
  useChoiceKeys(choices, (c) => setSelectedChoice(c),
    effectiveMode === 'test-multiple' && !!currentSentence && !result && !submitting && !signOpen)

  const loadVisemes = async () => {
    if (!currentSentence) {
      setLoading(false)
      setBooted(true)
      return
    }

    setLoading(true)
    setResult(null)
    setHintLevel(0)
    setRevealedTextIndex(-1)
    setStartTime(Date.now())

    try {
      const visemeData = await learningAPI.getVisemes(currentSentence)
      setVisemes(visemeData)
      setIsPlaying(true)
    } catch (error) {
      console.error('Failed to load visemes:', error)
    } finally {
      setLoading(false)
      setBooted(true)
    }
  }

  const handleSubmitAnswer = async (userAnswer) => {
    setSubmitting(true)
    const timeSpent = startTime ? Math.floor((Date.now() - startTime) / 1000) : 0

    try {
      const response = await learningAPI.submitProgress({
        scenario_id: currentScenario.scenario_id,
        sentence: currentSentence,
        user_answer: userAnswer,
        time_spent_seconds: timeSpent,
        situation: currentScenario.situation,
        difficulty_level: currentScenario.level,
      })

      setResult(response)
      setIsPlaying(false)
      const correct = effectiveMode === 'test-multiple' ? userAnswer === currentSentence : (response.score ?? 0) >= CORRECT_SCORE
      setTally((t) => ({ n: t.n + 1, correct: t.correct + (correct ? 1 : 0) }))
      setXpEarned((x) => x + (response.xp_gained || 0))

      const updates = {}
      if (response.new_level) updates.current_level = response.new_level
      if (response.streak_count != null) updates.streak_count = response.streak_count
      if (response.xp_gained != null) updates.total_xp = (user?.total_xp || 0) + response.xp_gained
      if (Object.keys(updates).length > 0) updateUser(updates)
    } catch (error) {
      console.error('Failed to submit answer:', error)
    } finally {
      setSubmitting(false)
    }
  }

  // 다음 문장 — 마지막 문장 뒤에는 currentSentence가 비어 레슨 완료(93:12)가 뜬다(걸린 시간은 이 순간으로 고정).
  const handleNext = () => {
    if (isLastSentence) setElapsedSec(Math.floor((Date.now() - lessonStartRef.current) / 1000))
    nextSentence()
    setResult(null)
    setSelectedChoice(null)
    setHintLevel(0)
    setRevealedTextIndex(-1)
  }

  const handleRetry = () => {
    setResult(null)
    setHintLevel(0)
    setRevealedTextIndex(-1)
    setSelectedChoice(null)
    setIsPlaying(true)
    setStartTime(Date.now())
  }

  const handleFinish = () => {
    resetPractice()
    navigate(isReviewSession ? '/review/mistakes' : '/learn/path')
  }

  const showNextHint = () => {
    if (hintLevel >= 3) return

    const nextHintLevel = hintLevel + 1
    setHintLevel(nextHintLevel)

    if (nextHintLevel === 3) {
      setRevealedTextIndex(-1)
      setSubtitleRestartKey((key) => key + 1)
      setIsPlaying(true)
    }
  }

  const handleSubtitleFrame = useCallback(({ textIndex, progress, completed, cycleComplete }) => {
    if (hintLevel < 3 || result) return

    if (cycleComplete) {
      setRevealedTextIndex(-1)
      return
    }

    const sentenceLength = Array.from(currentSentence || '').length
    const fallbackIndex = Math.max(0, Math.ceil(progress * sentenceLength) - 1)
    setRevealedTextIndex(
      completed
        ? sentenceLength - 1
        : Number.isInteger(textIndex) ? textIndex : fallbackIndex
    )
  }, [currentSentence, hintLevel, result])

  const isLastSentence =
    currentSentenceIndex >= (currentScenario?.sentences?.length || 0) - 1

  if (!currentScenario) return null

  // 레슨 시작 전 = 독화 트랙 로딩(223:30 / 모바일 243:81)
  if (!booted || !introDone) return <LoadingScreen variant="brand" track="perception" />

  // 마지막 문장까지 마치면 레슨 완료(93:12). 다음 레슨 = 다른 상황 고르기(복습 세션이면 복습 목록).
  if (!currentSentence) {
    const accuracy = tally.n ? Math.round((tally.correct / tally.n) * 100) : null
    return (
      <LessonComplete accuracy={accuracy} xp={xpEarned} elapsedSec={elapsedSec}
        onNext={() => { resetPractice(); navigate(isReviewSession ? '/review/mistakes' : '/learn/scenario') }}
        onHome={() => { resetPractice(); navigate('/learn/path') }} />
    )
  }

  // 북마크 토글 — 독화 문장에도 저장 버튼을 달아 Bookmarks 페이지·복습 큐가 실제로 채워지게 함
  const isBookmarked = !!bookmarks[currentSentence]
  const toggleBookmark = async () => {
    if (!currentSentence) return
    try {
      if (bookmarks[currentSentence]) {
        await learningAPI.removeBookmark(bookmarks[currentSentence])
        setBookmarks((m) => { const n = { ...m }; delete n[currentSentence]; return n })
      } else {
        const r = await learningAPI.addBookmark(currentSentence, currentScenario.situation, currentScenario.level, 'read')
        setBookmarks((m) => ({ ...m, [currentSentence]: r.id }))
      }
    } catch { /* 저장 실패는 조용히 무시 */ }
  }

  const total = currentScenario.sentences.length
  const multiple = effectiveMode === 'test-multiple'
  const answered = currentSentenceIndex + (result ? 1 : 0)
  const mcCorrect = multiple && result ? selectedChoice === currentSentence : false
  const questionTitle = multiple ? '어떤 문장인가요?'
    : effectiveMode === 'essay' ? '문장 전체를 서술하세요'
      : effectiveMode === 'study' ? '학습 모드 — 문장 보기'
        : '무슨 말인가요?'
  const optionState = (c) => {
    if (!result) return selectedChoice === c ? 'selected' : 'idle'
    if (c === currentSentence) return selectedChoice === c ? 'correct' : 'target'
    return selectedChoice === c ? 'wrong' : 'idle'
  }

  // 입모양 재생(주관식·서술형·학습) — 흰 카드 안 3D 플레이어. 로딩 중에는 스피너.
  const player = (extra = {}) => (
    <div className="rounded-18 border-2 border-line bg-white p-4 lg:rounded-22">
      {loading ? (
        <div className="flex flex-col items-center justify-center gap-3 py-16">
          <div className="spinner size-10 rounded-full border-4 border-primary-200 border-t-primary-600" />
          <p className="text-sm text-ink-muted">Viseme 생성 중...</p>
        </div>
      ) : (
        <LipSyncPlayer3D visemes={visemes} isPlaying={isPlaying} onComplete={() => setIsPlaying(false)} {...extra} />
      )}
    </div>
  )

  return (
    <div className="min-h-[100dvh] bg-page">
      <div className={`mx-auto flex w-full max-w-[676px] flex-col px-[18px] pt-[18px] lg:pt-7 ${multiple ? 'pb-[200px] lg:pb-[150px]' : 'pb-12'}`}>
        {/* 진행 헤더(91:13 / 모바일 235:35) — 나가기 X + 트랙 + n / 전체 */}
        <div className="flex items-center gap-3 lg:gap-[18px]">
          <button type="button" onClick={handleFinish} aria-label="나가기" className="shrink-0">
            <img src="/ui/lp-91-12-close.svg" alt="" className="size-8 lg:size-9" />
          </button>
          <div className="h-3 flex-1 overflow-hidden rounded-full bg-fill-strong lg:h-[14px]">
            <div className="h-full rounded-full bg-track transition-all duration-500" style={{ width: `${(answered / total) * 100}%` }} />
          </div>
          <span className="shrink-0 text-[13px] font-bold leading-figma text-ink-muted lg:text-[15px]">{currentSentenceIndex + 1} / {total}</span>
        </div>

        <div className="mt-6 flex flex-col gap-4 lg:mt-5 lg:gap-5">
          {/* 질문 + 북마크(91:19 · 328:40 / 모바일 235:42 · 328:64) — 북마크는 기존대로 서버에 저장 */}
          <div className="relative flex flex-col gap-1.5 pr-12 leading-figma lg:gap-2 lg:pr-[52px]">
            <p className="text-[12px] font-bold text-track lg:text-[13px]">{currentScenario.situation}</p>
            <h1 className="text-[21px] font-bold tracking-[-0.525px] text-ink lg:text-[30px] lg:tracking-[-0.75px]">{questionTitle}</h1>
            <BookmarkButton active={isBookmarked} onToggle={toggleBookmark}
              label={isBookmarked ? '이 문장 북마크 해제' : '이 문장 북마크 저장'}
              className="absolute right-0 top-[14px] lg:top-[21px]" />
          </div>

          {multiple ? (
            <>
              {/* 입모양 카드(91:22 / 모바일 235:45) — 아바타만, 무한 반복(다시 보기·속도·프레임 조작 없음) */}
              <div className="mx-auto h-[214px] w-full max-w-[560px] rounded-18 border-2 border-line bg-white p-4 lg:h-[370px] lg:rounded-22">
                <MouthAvatar key={currentSentence} frames={visemes} height={null} className="h-full" />
              </div>

              {/* 4지선다(91:28 / 모바일 235:51) — 선택 → 확인 */}
              <div className="flex flex-col gap-2.5 lg:gap-3">
                {choices.map((c, i) => (
                  <button key={c} type="button" disabled={!!result || submitting} onClick={() => setSelectedChoice(c)}
                    aria-pressed={!result ? selectedChoice === c : undefined} className={OPTION_CLASS[optionState(c)]}>
                    <span className="flex size-6 shrink-0 items-center justify-center rounded-[7px] bg-fill text-[12px] font-bold leading-figma text-ink-muted lg:size-7 lg:rounded-lg lg:text-[13px]">{i + 1}</span>
                    <span className="flex-1 text-[18px] font-bold leading-figma lg:text-[20px]">{c}</span>
                  </button>
                ))}
              </div>

              {/* 결과 뒤 음절 기호(시각증강) — 교육 패널이라 유지, 고정 바 위 스크롤 영역 */}
              {result && (
                <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                  className="overflow-x-auto rounded-16 border-2 border-line bg-white p-3">
                  <CueBadges text={currentSentence} showControls />
                  <div className="mt-1.5"><CueLegend /></div>
                </motion.div>
              )}
            </>
          ) : effectiveMode === 'study' ? (
            <>
              {player({ loop: true })}
              <div className="card flex flex-col gap-4">
                <div className="rounded-14 border-2 border-good-line bg-good-tint p-4">
                  <p className="text-2xl font-bold leading-relaxed tracking-wide text-good-text">{currentSentence}</p>
                </div>
                <button type="button" onClick={() => setSignOpen(true)} className="btn-secondary w-full py-2.5 text-[14px] text-track">
                  이 문장 수어로 보기
                </button>
                <div className="space-y-1 rounded-lg bg-surface-muted p-3 text-sm text-ink-muted">
                  <p className="font-bold text-ink">학습 방법</p>
                  <p>1. 위 문장을 읽으면서 입모양 애니메이션을 반복해서 보세요.</p>
                  <p>2. 각 음절이 어떤 입모양인지 연결해보세요.</p>
                  <p>3. 충분히 익혔으면 다음 문장으로 넘어가세요.</p>
                </div>
                <button type="button" onClick={handleNext} className="btn-primary w-full">
                  {isLastSentence ? '학습 완료' : '익혔어요, 다음 문장 →'}
                </button>
              </div>
            </>
          ) : (
            /* 주관식 / 서술형 */
            <>
              {player({ onFrameChange: handleSubtitleFrame, loop: !result, restartKey: subtitleRestartKey })}
              <div className="card">
                {!result && hintLevel < 3 && (
                  <button type="button" onClick={showNextHint}
                    className="mb-2 rounded-full bg-warn-tint px-3 py-1.5 text-xs font-bold text-warn-text transition-colors hover:brightness-95">
                    힌트 보기 {hintLevel > 0 ? `(${hintLevel}/3)` : ''}
                  </button>
                )}

                <AnimatePresence>
                  {hintLevel > 0 && (
                    <motion.div key={hintLevel} initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                      <HintDisplay sentence={currentSentence} hintLevel={hintLevel} revealedTextIndex={revealedTextIndex} />
                    </motion.div>
                  )}
                </AnimatePresence>

                <div className="mt-4">
                  <QuizForm
                    key={currentSentenceIndex}
                    onSubmit={handleSubmitAnswer}
                    onRetry={handleRetry}
                    loading={submitting}
                    result={result}
                    correctAnswer={currentSentence}
                    label={effectiveMode === 'essay'
                      ? '입모양을 보고 문장 전체를 서술해서 입력하세요'
                      : '입모양을 보고 문장을 입력하세요'}
                    placeholder={effectiveMode === 'essay'
                      ? '읽은 내용을 문장으로 자세히 적어보세요...'
                      : '여기에 읽은 문장을 입력하세요...'}
                  />
                </div>

                {result && (
                  <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }} className="mt-4">
                    {result.streak_count > 1 && (
                      <p className="mb-2 text-center text-sm font-bold text-stat-streak">
                        {result.streak_count}일째 연속 학습 중! +{Math.round((result.streak_multiplier - 1) * 100)}% 보너스 XP
                      </p>
                    )}
                    <button type="button" onClick={handleNext} className="btn-primary w-full">
                      {isLastSentence ? '완료' : '다음 문장 →'}
                    </button>
                  </motion.div>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      {/* 4지선다 하단 고정 바 — 문제(130:17) · 정답(94:133) · 오답(94:175). lg 미만(235:68 · 235:105)은
          힌트 없이 메시지 위·전체 폭 버튼 아래로 쌓는다(§4-12). */}
      {multiple && (
        <div className={`fixed inset-x-0 bottom-0 z-40 border-t-2 ${!result ? 'border-line bg-white' : mcCorrect ? 'border-good bg-good-tint lg:border-good/35' : 'border-bad bg-bad-tint lg:border-bad/35'}`}>
          <div className="mx-auto flex max-w-[676px] flex-col items-stretch gap-3 px-[18px] pb-[calc(22px+env(safe-area-inset-bottom))] pt-4 lg:h-[110px] lg:flex-row lg:items-center lg:justify-between lg:gap-4 lg:py-0">
            {result ? (
              <div role="status" aria-live="polite" className={`flex min-w-0 flex-col gap-[3px] leading-figma lg:gap-1 ${mcCorrect ? 'text-good-text' : 'text-bad-text'}`}>
                <p className="text-[19px] font-bold tracking-[-0.38px] lg:text-[22px] lg:tracking-[-0.44px]">{mcCorrect ? '정답이에요!' : '아쉬워요'}</p>
                <p className="line-clamp-2 text-[13px] font-bold opacity-80 lg:text-[14px]">정답은 「{currentSentence}」예요</p>
              </div>
            ) : (
              <span className="hidden text-[15px] leading-figma text-ink-faint lg:inline">{selectedChoice == null ? '보기를 선택해주세요' : '정답을 확인해보세요'}</span>
            )}
            {result ? (
              <button type="button" onClick={handleNext} className={`${mcCorrect ? 'btn-good' : 'btn-bad'} btn-bar ${BAR_BTN}`}>계속하기</button>
            ) : (
              <button type="button" onClick={() => handleSubmitAnswer(selectedChoice)} disabled={selectedChoice == null || submitting}
                className={`btn-primary btn-bar ${BAR_BTN}`}>확인</button>
            )}
          </div>
        </div>
      )}

      {/* 수어 보기 — 학습 화면을 벗어나지 않는 슬라이드오버 모달 */}
      <AnimatePresence>
        {signOpen && (
          <motion.div
            className="fixed inset-0 z-50 flex justify-end bg-overlay/50"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            onClick={() => setSignOpen(false)}
          >
            <motion.div
              ref={signRef}
              role="dialog"
              aria-modal="true"
              aria-label={`${currentSentence} 수어 번역`}
              tabIndex={-1}
              className="h-full w-full max-w-2xl overflow-y-auto bg-white shadow-modal outline-none"
              initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }}
              transition={{ type: 'tween', duration: 0.25 }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="sticky top-0 z-10 flex items-center justify-between border-b-1.5 border-line bg-white px-5 py-3">
                <div>
                  <p className="text-xs text-ink-faint">이 문장을 수어로</p>
                  <p className="font-bold text-ink">{currentSentence}</p>
                </div>
                <ModalClose onClose={() => setSignOpen(false)} />
              </div>
              <div className="p-5">
                {signOpen && <SignPanel text={currentSentence} />}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
