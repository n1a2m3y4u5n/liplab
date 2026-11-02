import SentenceLessonView from '../components/practice/SentenceLessonView'
import { CORRECT_SCORE, INTRO_MS, LessonComplete } from '../components/practice/SentencePresentation'
import useLessonCheckpoint from '../hooks/useLessonCheckpoint'
import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import useStore from '../store/useStore'
import { curriculumAPI, learningAPI } from '../api'
import LipSyncPlayer3D from '../components/LipSyncPlayer3D'
import LoadingScreen from '../components/LoadingScreen'
import MasteryProbeBlock from '../components/MasteryProbeBlock'
import useMasteryProbes from '../hooks/useMasteryProbes'
import useFocusTrap from '../hooks/useFocusTrap'
import useChoiceKeys from '../lib/useChoiceKeys'
import { sentenceLevel } from '../lib/reviewScenario'
import useSlowWeak from '../hooks/useSlowWeak'
import useLessonTalker from '../hooks/useLessonTalker'
import { trialMeta } from '../lib/measurement'
import { effectiveSpeed } from '../lib/visemeTiming'
import useSoundCondition from '../hooks/useSoundCondition'
import useSoundReplay from '../hooks/useSoundReplay'
import { soundAPI } from '../api'

/**
 * 힌트 시스템: 단계별로 문장 정보를 공개
 * Level 0: 힌트 없음
 * Level 1: 음절 수 (● ● ● ●)
 * Level 2: 자음 골격 — 음절마다 첫 자음만 (ㅇ ㄴ ㅎ ㅅ ㅇ). 예전 '첫 글자'는 낱말 첫 음절을 통째로 보여 입모양 대신 글자로
 *          맞히게 했다. 자음 골격은 모음·받침을 입모양으로 읽게 남긴다(계획 C10, idea-sweep 다2)
 * Level 3: 발음 타이밍에 맞춰 전체 공개
 */
export default function Practice() {
  const navigate = useNavigate()
  const user = useStore((state) => state.user)
  const currentScenario = useStore((state) => state.currentScenario)
  const currentSentence = useStore((state) => state.currentSentence)
  const [checkpoint, saveCheckpoint, clearCheckpoint, submission] = useLessonCheckpoint('sentence')
  const sessionCheckpoint = checkpoint?.scenarioId === currentScenario?.scenario_id ? checkpoint : null
  const resumed = sessionCheckpoint?.sentence === currentSentence ? sessionCheckpoint : null
  const currentSentenceIndex = useStore((state) => state.currentSentenceIndex)
  const nextSentence = useStore((state) => state.nextSentence)
  const resetPractice = useStore((state) => state.resetPractice)
  const updateUser = useStore((state) => state.updateUser)
  const practiceMode = useStore((state) => state.practiceMode) // 'study' | 'test'

  // 테스트는 문장마다 유형이 다르다: 주관식(test) · 4지선다(test-multiple) · 서술형(essay)
  const qType = currentScenario?.qTypes?.[currentSentenceIndex]
  const effectiveMode = practiceMode === 'study' ? 'study' : (qType || 'test')
  // 복습에서 넘어온 세션인지는 심어 둔 scenario_id로 판별한다. 틀린 문장 다시 풀기(ReviewLanding, mistake_review_*)와
  // 북마크 다시 연습(Bookmarks, bookmark_*). 나가기와 완료 뒤 '다음 레슨으로'는 학습 경로 대신 그 목록으로 돌아간다.
  const scenarioId = String(currentScenario?.scenario_id || '')
  const reviewReturn = scenarioId.startsWith('mistake_review_') ? '/review/mistakes'
    : scenarioId.startsWith('bookmark_') ? '/review/saved' : null

  const loadedRef = useRef(resumed ? currentSentence : null)
  const [visemes, setVisemes] = useState([])
  const shownVisemes = useSlowWeak(visemes)   // 약한 입모양은 조금 천천히(연습 화면)
  const [lesson] = useLessonTalker('sentence', sessionCheckpoint?.lesson)   // 상황(레슨)마다 가상 화자 한 명(계획 2-2)
  // 숙달 지연 탐침(계획 C16): 레슨 가운데 문장 뒤에 한 번 끼운다. 틀린 문장 복습·북마크 연습 세션에는 내지 않는다(길이 0)
  const probes = useMasteryProbes(reviewReturn ? 0 : (currentScenario?.sentences?.length || 0))
  const [isPlaying, setIsPlaying] = useState(false)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState(() => resumed && Object.hasOwn(resumed, 'result') ? resumed.result : (null))
  const [draft, setDraft] = useState(resumed?.draft || '')
  // 소리 조건(C17): 답을 채점한 뒤에만 문장을 소리와 함께 다시 보기(소리 → 소리 없이 한 번 더)
  const sound = useSoundCondition()
  const replay = useSoundReplay({ texts: currentSentence ? [currentSentence] : [], answered: !!result, enabled: sound.enabled,
    onPlayed: () => soundAPI.logReplay('sentence', currentSentence).catch(() => {}) })
  const [startTime, setStartTime] = useState(null)
  const [hintLevel, setHintLevel] = useState(() => resumed && Object.hasOwn(resumed, 'hintLevel') ? resumed.hintLevel : (0))
  const [revealedTextIndex, setRevealedTextIndex] = useState(-1)
  const [subtitleRestartKey, setSubtitleRestartKey] = useState(0)
  const [selectedChoice, setSelectedChoice] = useState(() => resumed && Object.hasOwn(resumed, 'selectedChoice') ? resumed.selectedChoice : (null)) // 4지선다에서 고른 보기(확인 전)
  const [signOpen, setSignOpen] = useState(false)            // 수어 보기 모달
  const [bookmarks, setBookmarks] = useState({})             // 문장 텍스트 → 북마크 id (저장)
  const [booted, setBooted] = useState(false)                // 첫 문장 입모양을 받았는지(레슨 시작 전 로딩)
  const [introDone, setIntroDone] = useState(false)          // 레슨 시작 전 로딩 최소 표시 시간
  const [tally, setTally] = useState(() => sessionCheckpoint && Object.hasOwn(sessionCheckpoint, 'tally') ? sessionCheckpoint.tally : ({ n: 0, correct: 0 }))   // 이번 레슨의 채점 문항·정답 수 → 완료 정답률
  const [xpEarned, setXpEarned] = useState(() => sessionCheckpoint && Object.hasOwn(sessionCheckpoint, 'xpEarned') ? sessionCheckpoint.xpEarned : (0))                // 이번 레슨에서 서버가 준 XP 합(xp_gained)
  const lessonStartRef = useRef(sessionCheckpoint?.lessonStartRef ?? (Date.now()))
  const [elapsedSec, setElapsedSec] = useState(() => sessionCheckpoint && Object.hasOwn(sessionCheckpoint, 'elapsedSec') ? sessionCheckpoint.elapsedSec : (0))
  const [visemeError, setVisemeError] = useState(false)      // 입모양을 받지 못함 → 다시 받기 안내
  const visemeReqRef = useRef(0)                             // 입모양 요청 순번(늦게 온 이전 문장의 응답은 버린다)
  const answerShownRef = useRef(resumed?.answerShownRef ?? (false))                       // 이 문장의 정답을 이미 보였는지(채점 결과에 정답이 나온다)
  // 자음 피드백 단계(계획 C9): 주관식 첫 답이 합격선 아래면 정답 대신 낱말별 단서를 보이고 한 번 더 답하게 한다.
  // { feedback, first }: 서버 word_feedback과 첫 답의 채점 결과. 두 번째 답은 연습(practice_only)으로만 채점한다
  const [retry, setRetry] = useState(() => resumed && Object.hasOwn(resumed, 'retry') ? resumed.retry : (null))
  const [revealedAnswer, setRevealedAnswer] = useState(() => resumed && Object.hasOwn(resumed, 'revealedAnswer') ? resumed.revealedAnswer : (null))   // '정답 보기'로 끝낸 경우 결과 화면에 보일 첫 답
  // 이 문장을 보는 동안 학습자가 고른 가장 느린 재생 속도(플레이어 onSpeedChange). 4지선다 카드는 속도 조절이 없어 1.0배다.
  // 답과 함께 유효 속도(학습자 속도 × 적응 감속)를 기록만 한다. 숙달에는 넣지 않는다(시뮬레이션 사전 기준 미달, docs/mastery-ewma.md 9절)
  const learnerSpeedRef = useRef(Infinity)
  const onPlayerSpeed = useCallback((s) => { learnerSpeedRef.current = Math.min(learnerSpeedRef.current, s) }, [])
  const closeSign = useCallback(() => setSignOpen(false), [])
  const signRef = useFocusTrap(signOpen, closeSign)          // 수어 모달 포커스 트랩·Esc

  // 4지선다 보기 — 정답 + 서버가 고른 레슨 밖 문장 3개(음절 수가 가까운 것), 랜덤 순서. 예전 보기는 같은 레슨의 다른
  // 문장이라 뒤에 주관식으로 나올 문장이 먼저 보였고(그런 문항의 40~56%), 이미 푼 문장은 지울 수 있었고, 길이 차이로도
  // 골랐다(backend/sentence_options.py). 서버 보기를 못 받으면 예전 방식으로 낸다.
  const [choices, setChoices] = useState(() => resumed && Object.hasOwn(resumed, 'choices') ? resumed.choices : ([]))
  useEffect(() => {
    if (resumed?.sentence === currentSentence && resumed?.choices?.length) return undefined
    if (!currentScenario || !currentSentence || effectiveMode !== 'test-multiple') { setChoices([]); return undefined }
    let alive = true
    const local = () => currentScenario.sentences.filter((s) => s !== currentSentence).sort(() => Math.random() - 0.5).slice(0, 3)
    setChoices([])
    curriculumAPI.getSentenceOptions(currentSentence, currentScenario.sentences)
      .then((r) => (Array.isArray(r?.options) && r.options.length >= 3 ? r.options.slice(0, 3) : local()))
      .catch(local)
      .then((others) => { if (alive) setChoices([...others, currentSentence].sort(() => Math.random() - 0.5)) })
    return () => { alive = false }
  }, [currentSentence, effectiveMode])

  useEffect(() => {
    if (!currentScenario) {
      navigate('/learn/scenario', { replace: true })   // 상황 없이 들어오면 상황 선택으로(예전 /dashboard는 학습 경로로 되돌아갔다)
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

  // 지금 문장의 입모양을 받는다. 받기 전에 이전 문장 입모양을 비워, 실패해도 이전 문장의 입모양이 새 문장 문제로
  // 재생되지 않게 한다. 실패하면 다시 받기 안내를 띄운다(다시 받기는 문항 상태를 그대로 두고 입모양만 받는다).
  const fetchVisemes = async () => {
    const req = ++visemeReqRef.current
    setVisemes([])
    setIsPlaying(false)
    setVisemeError(false)
    setLoading(true)
    try {
      const visemeData = await learningAPI.getVisemes(currentSentence)
      if (req !== visemeReqRef.current) return
      if (!Array.isArray(visemeData) || visemeData.length === 0) { setVisemeError(true); return }
      setVisemes(visemeData)
      setIsPlaying(true)
    } catch (error) {
      if (req !== visemeReqRef.current) return
      console.error('Failed to load visemes:', error)
      setVisemeError(true)
    } finally {
      if (req === visemeReqRef.current) {
        setLoading(false)
        setBooted(true)
      }
    }
  }

  const loadVisemes = async () => {
    if (!currentSentence) {
      visemeReqRef.current += 1   // 마지막 문장의 늦은 응답은 완료 화면 뒤에 쓰지 않는다
      setLoading(false)
      setBooted(true)
      return
    }

    if (loadedRef.current === currentSentence) {
      await fetchVisemes()
      return
    }
    loadedRef.current = currentSentence
    setDraft('')
    setResult(null)
    setRetry(null)
    setRevealedAnswer(null)
    setHintLevel(0)
    setRevealedTextIndex(-1)
    setStartTime(Date.now())
    answerShownRef.current = false
    learnerSpeedRef.current = Infinity
    await fetchVisemes()
  }

  const handleSubmitAnswer = async (userAnswer) => {
    if (submitting || !submission.begin(userAnswer)) return
    setSubmitting(true)
    const timeSpent = startTime ? Math.floor((Date.now() - startTime) / 1000) : 0
    // 정답을 이미 본 뒤의 제출(같은 문장 다시 도전)과 힌트 3(발음 자막)으로 문장을 본 뒤의 제출은 연습으로만 채점한다.
    // 서버는 practice_only면 점수만 주고 3단계 숙달·XP에는 넣지 않는다. 이 레슨의 정답률에도 넣지 않는다.
    // 자음 피드백 뒤의 두 번째 답도 연습으로만 채점한다(숙달에는 첫 답만)
    const practiceOnly = answerShownRef.current || hintLevel >= 3 || !!retry
    const learnerSpeed = effectiveMode === 'test-multiple' || !Number.isFinite(learnerSpeedRef.current) ? 1 : learnerSpeedRef.current
    const speed = effectiveSpeed(visemes, shownVisemes, learnerSpeed)

    try {
      const response = await learningAPI.submitProgress({
        scenario_id: currentScenario.scenario_id,
        sentence: currentSentence,
        user_answer: userAnswer,
        time_spent_seconds: timeSpent,
        situation: currentScenario.situation,
        // 틀린 문장 복습은 문장마다 원래 난이도(levels)를 보낸다. 예전에는 세션 난이도 1이 저장돼 추천 난이도가 떨어졌다
        difficulty_level: sentenceLevel(currentScenario, currentSentenceIndex),
        // 연습 답의 사유(분석용 sentence_practice_logs). 자음 피드백 뒤 두 번째 답 > 발음 자막 > 정답을 본 뒤
        ...(practiceOnly ? { practice_only: true,
          practice_reason: retry ? 'consonant_retry' : hintLevel >= 3 ? 'hint3' : 'answer_shown' } : {}),
        // 4지선다는 보기를 고른 것이라 서버가 채점식 대신 정확 일치(100 또는 0)로 준다(비슷한 오답 보기가 통과하지 않게).
        // 주관식·서술형은 'typed'. 서버는 답 방식을 progress.answer_mode에 남기고, 4지선다는 3단계 숙달에 우연 보정(정답 1,
        // 오답 −1/3)으로 넣는다(docs/mastery-ewma.md 10절)
        answer_mode: effectiveMode === 'test-multiple' ? 'choice' : 'typed',
        ...(Number.isFinite(speed) && speed > 0 ? { speed } : {}),
        // 파일럿 로그(P0, 기록만): 문장을 연 때부터 답까지 ms, 레슨 가상 화자, 연 힌트 단계(0~3), 4지선다 보기(보인 순서)
        ...trialMeta({ onsetAt: startTime, talker: lesson.talker || 'default', soundCondition: sound.enabled }),
        hint_level: hintLevel,
        ...(effectiveMode === 'test-multiple' && choices.length ? { options: choices } : {}),
      })

      // 주관식 첫 답이 합격선 아래이고 틀린 낱말이 있으면, 정답 문장을 보이지 않고 자음 단서를 보인 뒤 입모양을 다시 재생한다
      submission.finish()
      const wf = response.word_feedback
      const needsRetry = effectiveMode !== 'test-multiple' && !practiceOnly && response.passed === false
        && Array.isArray(wf?.words) && wf.words.some((w) => !w.correct)
      if (needsRetry) {
        setDraft('')
        setRetry({ feedback: wf, first: response, answer: userAnswer })
        setIsPlaying(true)
        setStartTime(Date.now())
      } else {
        setRetry(null)
        setResult(response)
        answerShownRef.current = true   // 채점 결과와 함께 정답 문장이 보인다
        setIsPlaying(false)
      }
      // 4지선다는 answer_mode 'choice'로 보내 서버도 같은 문장인지(정확 일치)로 채점한다(화면의 정오와 같다).
      // 레슨 집계의 맞힘은 서버의 합격 판정(3단계 합격선, response.passed)을 따른다. 예전에는 80점 기준이라 숙달(60점)과
      // 오답 목록(60점 미만)과 어긋났다. 옛 서버 응답에 passed가 없으면 예전 기준으로 둔다.
      const correct = effectiveMode === 'test-multiple' ? userAnswer === currentSentence : (response.passed ?? ((response.score ?? 0) >= CORRECT_SCORE))
      if (!practiceOnly) setTally((t) => ({ n: t.n + 1, correct: t.correct + (correct ? 1 : 0) }))
      setXpEarned((x) => x + (response.xp_gained || 0))

      const updates = {}
      if (response.new_level) updates.current_level = response.new_level
      if (response.streak_count != null) updates.streak_count = response.streak_count
      if (response.xp_gained != null) updates.total_xp = (user?.total_xp || 0) + response.xp_gained
      if (Object.keys(updates).length > 0) updateUser(updates)
    } catch (error) {
      advance()
      console.error('Failed to submit answer:', error)
    } finally {
      setSubmitting(false)
    }
  }

  // 다음 문장 — 마지막 문장 뒤에는 currentSentence가 비어 레슨 완료(93:12)가 뜬다(걸린 시간은 이 순간으로 고정).
  const advance = () => {
    setDraft('')
    if (isLastSentence) setElapsedSec(Math.floor((Date.now() - lessonStartRef.current) / 1000))
    nextSentence()
    setResult(null)
    setRetry(null)
    setRevealedAnswer(null)
    setSelectedChoice(null)
    setHintLevel(0)
    setRevealedTextIndex(-1)
  }

  // 다음 문장: 가운데 문장을 마친 뒤 탐침이 있으면 먼저 연다(탐침을 마치면 advance)
  const handleNext = () => { if (!probes.take(currentSentenceIndex + 1)) advance() }

  const handleRetry = () => {
    setDraft('')
    setResult(null)
    setRetry(null)
    setRevealedAnswer(null)
    setHintLevel(0)
    setRevealedTextIndex(-1)
    setSelectedChoice(null)
    setIsPlaying(true)
    setStartTime(Date.now())
  }

  // 자음 단서를 보고도 모르겠으면 첫 답의 결과와 정답 문장을 보인다(두 번째 답 없이)
  const revealAfterRetry = () => {
    if (!retry) return
    setResult(retry.first)
    setRevealedAnswer(retry.answer || '')
    setRetry(null)
    answerShownRef.current = true
    setIsPlaying(false)
  }

  const handleFinish = () => {
    resetPractice()
    navigate(reviewReturn || '/learn/path')
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

  const recoveredRef = useRef(false)
  useEffect(() => {
    if (submission.sent && !recoveredRef.current) {
      recoveredRef.current = true; submission.finish()
      if (!result && !retry && submission.sent.question === currentSentence) advance()
    }
  }, [])

  if (currentScenario) saveCheckpoint({ scenarioId: currentScenario.scenario_id, sentence: currentSentence, draft, result, hintLevel, selectedChoice, tally, xpEarned, elapsedSec, retry, revealedAnswer, choices, lesson, answerShownRef: answerShownRef.current, lessonStartRef: lessonStartRef.current })
  if (!currentScenario) return null

  // 레슨 시작 전 = 독화 트랙 로딩(223:30 / 모바일 243:81)
  if (!booted || !introDone) return <LoadingScreen variant="brand" track="perception" />

  if (probes.open) return <MasteryProbeBlock items={probes.items} onDone={() => { probes.finish(); advance() }} />

  // 마지막 문장까지 마치면 레슨 완료(93:12). 다음 레슨 = 다른 상황 고르기(복습 세션이면 복습 목록).
  if (!currentSentence) {
    const accuracy = tally.n ? Math.round((tally.correct / tally.n) * 100) : null
    return (
      <LessonComplete accuracy={accuracy} xp={xpEarned} elapsedSec={elapsedSec}
        effort={{ lessonKind: reviewReturn ? 'review' : 'sentence', stage: 3, nItems: tally.n,
          accuracy: tally.n ? tally.correct / tally.n : null }}   // 노력 문항은 정답률을 0~1로 받는다(화면 표시는 백분율)
        onNext={() => { resetPractice(); navigate(reviewReturn || '/learn/scenario') }}
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
        const r = await learningAPI.addBookmark(currentSentence, currentScenario.situation, sentenceLevel(currentScenario, currentSentenceIndex), 'read')
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
          <p className="text-sm text-ink-muted">입모양을 만들고 있어요…</p>
        </div>
      ) : (
        <LipSyncPlayer3D visemes={shownVisemes} isPlaying={isPlaying} onComplete={() => setIsPlaying(false)}
          talker={lesson.talker} talkerSeed={lesson.seed} onSpeedChange={onPlayerSpeed} override={replay.frame} {...extra} />
      )}
    </div>
  )

  return <SentenceLessonView {...{ multiple, handleFinish, answered, total, currentSentenceIndex, currentScenario, questionTitle, isBookmarked, toggleBookmark, visemeError, fetchVisemes, shownVisemes, result, currentSentence, lesson, replay, choices, submitting, setSelectedChoice, selectedChoice, optionState, sound, effectiveMode, player, setSignOpen, handleNext, isLastSentence, handleSubtitleFrame, subtitleRestartKey, hintLevel, showNextHint, retry, revealedTextIndex, revealedAnswer, draft, setDraft, handleSubmitAnswer, handleRetry, revealAfterRetry, mcCorrect, signOpen, signRef }} />
}
