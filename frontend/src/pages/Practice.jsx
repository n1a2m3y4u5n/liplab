import { useState, useEffect, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import useStore from '../store/useStore'
import { learningAPI } from '../api'
import LipSyncPlayer3D from '../components/LipSyncPlayer3D'
import QuizForm from '../components/QuizForm'
import SignPanel from '../components/SignPanel'

function BookmarkButton({ sentence, situation, level }) {
  const [bookmarkId, setBookmarkId] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setBookmarkId(null)  // immediately clear stale state when sentence changes
    let cancelled = false
    learningAPI.getBookmarks().then((list) => {
      if (!cancelled) {
        const found = list.find((b) => b.sentence === sentence)
        setBookmarkId(found?.id ?? null)
      }
    }).catch(() => {})
    return () => { cancelled = true }
  }, [sentence])

  const toggle = async () => {
    if (loading) return
    setLoading(true)
    try {
      if (bookmarkId) {
        await learningAPI.removeBookmark(bookmarkId)
        setBookmarkId(null)
      } else {
        const created = await learningAPI.addBookmark(sentence, situation, level)
        setBookmarkId(created.id)
      }
    } catch (e) {
      // On error, re-fetch to sync UI with server state
      learningAPI.getBookmarks().then((list) => {
        const found = list.find((b) => b.sentence === sentence)
        setBookmarkId(found?.id ?? null)
      }).catch(() => {})
    } finally {
      setLoading(false)
    }
  }

  return (
    <button
      onClick={toggle}
      disabled={loading}
      title={bookmarkId ? '북마크 해제' : '북마크 추가'}
      className={`flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-full border transition-colors ${
        bookmarkId
          ? 'bg-yellow-100 border-yellow-400 text-yellow-700'
          : 'bg-white border-gray-200 text-gray-400 hover:border-yellow-300 hover:text-yellow-500'
      }`}
    >
      {bookmarkId ? '★ 북마크됨' : '☆ 북마크'}
    </button>
  )
}

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

  const [visemes, setVisemes] = useState([])
  const [isPlaying, setIsPlaying] = useState(false)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState(null)
  const [startTime, setStartTime] = useState(null)
  const [hintLevel, setHintLevel] = useState(0)
  const [revealedTextIndex, setRevealedTextIndex] = useState(-1)
  const [subtitleRestartKey, setSubtitleRestartKey] = useState(0)
  const [selectedChoice, setSelectedChoice] = useState(null) // 4지선다에서 선택한 보기
  const [signOpen, setSignOpen] = useState(false)            // 수어 보기 모달

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

  const loadVisemes = async () => {
    if (!currentSentence) {
      setLoading(false)
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

  const handleNext = () => {
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
    navigate('/dashboard')
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

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-primary-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex justify-between items-center">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">독화 연습</h1>
              <p className="text-sm text-gray-600">
                {currentScenario.situation} · 레벨 {currentScenario.level}
                <span className={`ml-2 text-xs px-2 py-0.5 rounded-full font-medium ${
                  effectiveMode === 'study' ? 'bg-green-100 text-green-700'
                  : effectiveMode === 'test-multiple' ? 'bg-purple-100 text-purple-700'
                  : effectiveMode === 'essay' ? 'bg-indigo-100 text-indigo-700'
                  : 'bg-blue-100 text-blue-700'
                }`}>
                  {effectiveMode === 'study' ? '학습'
                    : effectiveMode === 'test-multiple' ? '4지선다'
                    : effectiveMode === 'essay' ? '서술형'
                    : '주관식'}
                </span>
              </p>
            </div>
            <div className="flex items-center gap-3">
              {currentSentence && practiceMode !== 'study' && (
                <BookmarkButton
                  sentence={currentSentence}
                  situation={currentScenario.situation}
                  level={currentScenario.level}
                />
              )}
              <button
                onClick={() => {
                  if (confirm('연습을 종료하시겠습니까?')) handleFinish()
                }}
                className="text-gray-500 hover:text-gray-800 text-sm"
              >
                ✕ 종료
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Progress */}
        <div className="mb-6">
          <div className="flex justify-between text-sm text-gray-600 mb-2">
            <span>문장 {currentSentenceIndex + 1} / {currentScenario.sentences.length}</span>
            <span>{Math.round(((currentSentenceIndex + 1) / currentScenario.sentences.length) * 100)}% 완료</span>
          </div>
          <div className="bg-gray-200 rounded-full h-2 overflow-hidden">
            <motion.div
              className="bg-primary-500 h-full"
              animate={{ width: `${((currentSentenceIndex + 1) / currentScenario.sentences.length) * 100}%` }}
              transition={{ duration: 0.5 }}
            />
          </div>
        </div>

        {currentSentence ? (
          effectiveMode === 'study' ? (
            /* ── 학습 모드 ── */
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} className="card">
                <h3 className="text-lg font-semibold mb-4 text-gray-900">입모양 애니메이션</h3>
                {loading ? (
                  <div className="flex flex-col items-center justify-center py-16 gap-3">
                    <div className="w-10 h-10 border-4 border-primary-200 border-t-primary-600 rounded-full animate-spin" />
                    <p className="text-gray-500 text-sm">Viseme 생성 중...</p>
                  </div>
                ) : (
                  <LipSyncPlayer3D
                    visemes={visemes}
                    isPlaying={isPlaying}
                    onComplete={() => setIsPlaying(false)}
                    loop={true}
                  />
                )}
              </motion.div>

              <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} className="card flex flex-col gap-4">
                <div>
                  <p className="text-xs font-semibold text-green-600 uppercase tracking-wide mb-2">학습 모드 — 문장 보기</p>
                  <div className="p-4 bg-green-50 border-2 border-green-200 rounded-xl">
                    <p className="text-2xl font-bold text-green-900 tracking-wide leading-relaxed">
                      {currentSentence}
                    </p>
                  </div>
                  <button
                    onClick={() => setSignOpen(true)}
                    className="mt-2 w-full py-2 rounded-lg border border-primary-300 text-primary-600 text-sm font-medium hover:bg-primary-50 transition-colors"
                  >
                    🤟 이 문장 수어로 보기
                  </button>
                </div>

                <div className="p-3 bg-gray-50 rounded-lg text-sm text-gray-600 space-y-1">
                  <p className="font-medium text-gray-700">학습 방법</p>
                  <p>1. 위 문장을 읽으면서 입모양 애니메이션을 반복해서 보세요.</p>
                  <p>2. 각 음절이 어떤 입모양인지 연결해보세요.</p>
                  <p>3. 충분히 익혔으면 다음 문장으로 넘어가세요.</p>
                </div>

                <div className="mt-auto space-y-2">
                  {isLastSentence ? (
                    <button onClick={handleFinish} className="btn-primary w-full">
                      학습 완료, 대시보드로
                    </button>
                  ) : (
                    <button onClick={handleNext} className="btn-primary w-full">
                      익혔어요, 다음 문장 →
                    </button>
                  )}
                </div>
              </motion.div>
            </div>
          ) : effectiveMode === 'test-multiple' ? (
            /* ── 4지선다 모드 ── */
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} className="card">
                <h3 className="text-lg font-semibold mb-4 text-gray-900">입모양 애니메이션</h3>
                {loading ? (
                  <div className="flex flex-col items-center justify-center py-16 gap-3">
                    <div className="w-10 h-10 border-4 border-primary-200 border-t-primary-600 rounded-full animate-spin" />
                    <p className="text-gray-500 text-sm">Viseme 생성 중...</p>
                  </div>
                ) : (
                  <LipSyncPlayer3D
                    visemes={visemes}
                    isPlaying={isPlaying}
                    onComplete={() => setIsPlaying(false)}
                    loop={!result}
                  />
                )}
              </motion.div>

              <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} className="card">
                <h3 className="text-lg font-semibold mb-5 text-gray-900">
                  {result ? '결과' : '어떤 문장인가요?'}
                </h3>

                {/* 4개 보기 버튼 */}
                <div className="space-y-3">
                  {choices.map((choice, i) => {
                    const isSelected = selectedChoice === choice
                    const isCorrect = choice === currentSentence
                    let btnClass = 'w-full text-left px-4 py-3 rounded-xl border-2 font-medium text-sm transition-all '
                    if (!result) {
                      btnClass += 'border-gray-200 bg-white hover:border-primary-400 hover:bg-primary-50 text-gray-800'
                    } else if (isCorrect) {
                      btnClass += 'border-green-500 bg-green-50 text-green-800'
                    } else if (isSelected && !isCorrect) {
                      btnClass += 'border-red-400 bg-red-50 text-red-700'
                    } else {
                      btnClass += 'border-gray-200 bg-gray-50 text-gray-400'
                    }
                    return (
                      <button
                        key={i}
                        disabled={!!result || submitting}
                        onClick={() => {
                          setSelectedChoice(choice)
                          handleSubmitAnswer(choice)
                        }}
                        className={btnClass}
                      >
                        <span className="inline-flex items-center gap-2">
                          <span className="w-6 h-6 rounded-full bg-gray-200 text-gray-600 text-xs flex items-center justify-center font-bold shrink-0">
                            {String.fromCharCode(65 + i)}
                          </span>
                          {choice}
                          {result && isCorrect && <span className="ml-auto text-green-600">✓</span>}
                          {result && isSelected && !isCorrect && <span className="ml-auto text-red-500">✗</span>}
                        </span>
                      </button>
                    )
                  })}
                </div>

                {/* 결과 후 다음/재도전 */}
                {result && (
                  <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.2 }}
                    className="mt-5 space-y-2"
                  >
                    <div className={`p-3 rounded-lg text-sm font-medium ${
                      result.score >= 80 ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
                    }`}>
                      {result.score >= 80 ? '정답! 🎉' : `오답 — 정답: ${currentSentence}`}
                      {result.streak_count > 1 && (
                        <span className="ml-2 text-orange-500">🔥 {result.streak_count}일 스트릭!</span>
                      )}
                    </div>
                    <div className="flex gap-2">
                      <button onClick={handleRetry} className="flex-1 py-2 rounded-lg border border-gray-200 text-sm text-gray-600 hover:bg-gray-50">
                        ↩ 다시 도전
                      </button>
                      {isLastSentence ? (
                        <button onClick={handleFinish} className="flex-1 btn-primary py-2 text-sm">
                          완료
                        </button>
                      ) : (
                        <button onClick={handleNext} className="flex-1 btn-primary py-2 text-sm">
                          다음 문장 →
                        </button>
                      )}
                    </div>
                  </motion.div>
                )}
              </motion.div>
            </div>
          ) : (
            /* ── 주관식 / 서술형 테스트 모드 ── */
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <motion.div
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                className="card"
              >
                <h3 className="text-lg font-semibold mb-4 text-gray-900">입모양 애니메이션</h3>
                {loading ? (
                  <div className="flex flex-col items-center justify-center py-16 gap-3">
                    <div className="w-10 h-10 border-4 border-primary-200 border-t-primary-600 rounded-full animate-spin" />
                    <p className="text-gray-500 text-sm">Viseme 생성 중...</p>
                  </div>
                ) : (
                  <LipSyncPlayer3D
                    visemes={visemes}
                    isPlaying={isPlaying}
                    onComplete={() => setIsPlaying(false)}
                    onFrameChange={handleSubtitleFrame}
                    loop={!result}
                    restartKey={subtitleRestartKey}
                  />
                )}
              </motion.div>

              <motion.div
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                className="card"
              >
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold text-gray-900">
                    {effectiveMode === 'essay' ? '문장 전체를 서술하세요' : '무슨 말인가요?'}
                  </h3>
                  {!result && hintLevel < 3 && (
                    <button
                      onClick={showNextHint}
                      className="text-xs px-3 py-1.5 rounded-full bg-amber-100 text-amber-700 hover:bg-amber-200 transition-colors font-medium"
                    >
                      힌트 보기 {hintLevel > 0 ? `(${hintLevel}/3)` : ''}
                    </button>
                  )}
                </div>

                <AnimatePresence>
                  {hintLevel > 0 && (
                    <motion.div
                      key={hintLevel}
                      initial={{ opacity: 0, y: -8 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0 }}
                    >
                      <HintDisplay
                        sentence={currentSentence}
                        hintLevel={hintLevel}
                        revealedTextIndex={revealedTextIndex}
                      />
                    </motion.div>
                  )}
                </AnimatePresence>

                <div className="mt-4">
                  <QuizForm
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
                  <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.3 }}
                    className="mt-4"
                  >
                    {result.streak_count > 1 && (
                      <p className="text-center text-orange-500 text-sm font-medium mb-2">
                        🔥 {result.streak_count}일째 연속 학습 중! +{Math.round((result.streak_multiplier - 1) * 100)}% 보너스 XP
                      </p>
                    )}
                    {isLastSentence ? (
                      <button onClick={handleFinish} className="btn-primary w-full">
                        완료하고 대시보드로
                      </button>
                    ) : (
                      <button onClick={handleNext} className="btn-primary w-full">
                        다음 문장 →
                      </button>
                    )}
                  </motion.div>
                )}
              </motion.div>
            </div>
          )
        ) : (
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="card text-center py-12"
          >
            <div className="text-6xl mb-4">완료</div>
            <h2 className="text-3xl font-bold text-gray-900 mb-2">연습 완료!</h2>
            <p className="text-gray-600 mb-6">모든 문장을 완료했습니다. 수고하셨습니다!</p>
            <button onClick={handleFinish} className="btn-primary">
              대시보드로 돌아가기
            </button>
          </motion.div>
        )}
      </main>

      {/* 수어 보기 — 학습 화면을 벗어나지 않는 슬라이드오버 모달 */}
      <AnimatePresence>
        {signOpen && (
          <motion.div
            className="fixed inset-0 z-50 bg-black/40 flex justify-end"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            onClick={() => setSignOpen(false)}
          >
            <motion.div
              className="w-full max-w-2xl h-full bg-white shadow-2xl overflow-y-auto"
              initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }}
              transition={{ type: 'tween', duration: 0.25 }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="sticky top-0 bg-white border-b border-gray-200 px-5 py-3 flex items-center justify-between">
                <div>
                  <p className="text-xs text-gray-400">이 문장을 수어로</p>
                  <p className="font-bold text-gray-900">{currentSentence}</p>
                </div>
                <button onClick={() => setSignOpen(false)}
                  className="px-3 py-1.5 text-sm text-gray-500 hover:text-gray-900 border border-gray-200 rounded-lg">
                  닫기 ✕
                </button>
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
