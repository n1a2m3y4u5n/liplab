import LessonA11yButton from '../LessonA11yButton'
import useLessonCheckpoint from '../../hooks/useLessonCheckpoint'
import { Progress } from '../UI'
import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { curriculumAPI, learningAPI } from '../../api'
import MouthAvatar from '../MouthAvatar'
import BookmarkButton from '../BookmarkButton'
import useBookmark from '../../lib/useBookmark'
import WatermarkCard from '../WatermarkCard'
import useChoiceKeys from '../../lib/useChoiceKeys'
import { pickVisemeDistractors, balancedTargets } from '../../lib/visemeOptions'
import ShortText from '../ShortText'
import useLearnerInfo from '../../hooks/useLearnerInfo'
import { splitFirstSentence } from '../../lib/learnerProfile'
import { lessonPlainLabel } from '../../lib/visemeLabels'
import { pickAxItems, axSlots, axExplain, axFrames } from '../../lib/visemeAx'
import useLessonTalker from '../../hooks/useLessonTalker'
import useMasteryProbes from '../../hooks/useMasteryProbes'
import MasteryProbeBlock from '../MasteryProbeBlock'
import EffortCheck from '../EffortCheck'
import { LESSON_COL, LESSON_STACK, LESSON_AVATAR_VISEME, LESSON_OPTIONS, lessonPad } from '../../lib/lessonLayout'
import { trialMeta } from '../../lib/measurement'
import useSoundCondition from '../../hooks/useSoundCondition'
import useSoundReplay from '../../hooks/useSoundReplay'
import SoundReplayBar from '../SoundReplayBar'
import { soundAPI } from '../../api'
import { lessonLabel, shuffle } from './VisemeParts'
const QUIZ_LEN = 12  // 레슨 1회 문항 수(진행바 분모) — 숙달 판정과 별개

const fmtDuration = (sec) => `${Math.floor(sec / 60)}분 ${sec % 60}초`
const OVERFLOW = { top: '-7%', left: '-12%', width: '124%', height: '124%' }   // 마스코트 SVG 그림자 여백(Figma inset)

// 레슨 완료 스탯 카드(93:22) — 모바일은 카드 폭이 좁아 여백·값 글자를 줄인다(모바일 프레임 없음).
const STAT_CARD = 'flex min-w-0 flex-1 flex-col gap-2 rounded-16 border border-line bg-white p-3.5 lg:p-5'
const STAT_LABEL = 'text-[13px] font-bold leading-figma text-ink-soft'
const STAT_VALUE = 'text-[20px] font-bold leading-figma tracking-[-0.5px] lg:text-[28px] lg:tracking-[-0.7px]'
const DONE_BTN = 'w-full max-lg:rounded-14 max-lg:py-4 max-lg:text-[16px]'

// Figma "Lesson / 4. 완료"(93:12) — 레슨 컴포넌트의 마지막 상태. DOKA + 워터마크 스탯 3칸 + 버튼 2개.
function LessonComplete({ accuracy, xp, elapsedSec, onNext, onHome, effort }) {
  return (
    <div className="flex min-h-[100dvh] w-full flex-col items-center justify-center gap-[26px] bg-page px-[18px] py-12">
      <span className="relative size-[140px] shrink-0">
        <img src="/ui/lp-93-12-mascot.svg" alt="" className="absolute max-w-none" style={OVERFLOW} />
      </span>
      <h1 className="text-center text-[38px] font-bold leading-figma tracking-[-0.95px] text-ink">레슨을 마쳤어요!</h1>

      <div className="flex w-full max-w-[640px] gap-3.5 py-2">
        <WatermarkCard className={STAT_CARD} deco={{ src: '/ui/lp-93-12-deco-percent.svg', size: 115.2, top: -45.83, right: -43.82 }}>
          <p className={STAT_LABEL}>정답률</p>
          <p className={`${STAT_VALUE} text-primary-700`}>{accuracy}%</p>
        </WatermarkCard>
        <WatermarkCard className={STAT_CARD} deco={{ src: '/ui/lp-93-12-deco-xp.svg', size: 157.945, top: -76, right: -71.44 }}>
          <p className={STAT_LABEL}>받은 경험치</p>
          <p className={`${STAT_VALUE} text-warn-text`}>+{xp}</p>
        </WatermarkCard>
        <WatermarkCard className={STAT_CARD} deco={{ src: '/ui/lp-93-12-deco-clock.svg', size: 115.2, top: -45.83, right: -43.82 }}>
          <p className={STAT_LABEL}>걸린 시간</p>
          <p className={`${STAT_VALUE} text-stat-level`}>{fmtDuration(elapsedSec)}</p>
        </WatermarkCard>
      </div>

      {/* 레슨별 정신적 노력 한 문항(C14, Paas 9점) — 답하지 않아도 된다. 기록만 하고 다음 레슨에는 쓰지 않는다 */}
      {effort && <EffortCheck {...effort} />}

      <div className="flex w-full max-w-[640px] flex-col gap-2.5 lg:gap-3">
        <button type="button" onClick={onNext} className={`btn-primary btn-lg ${DONE_BTN}`}>다음 레슨으로</button>
        <button type="button" onClick={onHome} className={`btn-secondary btn-lg text-track ${DONE_BTN}`}>학습 화면으로 돌아가기</button>
      </div>
    </div>
  )
}

// '같은지 다른지'(AX) 답 버튼 둘(lib/visemeAx). 글을 읽지 않아도 되게 크게 기호(= / ≠)를 보이고, 숫자 키 1·2로도 누른다.
const AX_CHOICES = [
  { key: 'same', mark: '=', label: '같아요' },
  { key: 'different', mark: '≠', label: '달라요' },
]

function QuizPanel({ data: incomingData }) {
  const navigate = useNavigate()
  const [checkpoint, saveCheckpoint, clearCheckpoint, submission] = useLessonCheckpoint('viseme')
  const data = checkpoint?.data || incomingData
  const { lessons } = data
  const quizzable = useMemo(() => lessons.filter((l) => l.quizzable), [lessons])
  const [q, setQ] = useState(() => checkpoint && Object.hasOwn(checkpoint, 'q') ? checkpoint.q : (null)) // 고르기 {kind:'pick', target, choices} | AX {kind:'ax', pair, frames}
  // 반응 시간 기준(파일럿 로그 P0): 문항을 보인 때(AX는 두 음절 입모양을 받은 때 다시 잰다)
  const onsetRef = useRef(null)
  useEffect(() => { onsetRef.current = q ? Date.now() : null }, [q])
  const [selected, setSelected] = useState(() => checkpoint && Object.hasOwn(checkpoint, 'selected') ? checkpoint.selected : (null)) // 확인 전 선택(선택→확인 2단계, 고르기 문항)
  const [result, setResult] = useState(() => checkpoint && Object.hasOwn(checkpoint, 'result') ? checkpoint.result : (null))
  const continueRef = useRef(null)
  const firstChoiceRef = useRef(null)
  // 답 공개 때 비활성화된 보기에서 다음 행동으로 초점을 옮긴다.
  useEffect(() => { if (result) continueRef.current?.focus({ preventScroll: true }) }, [result])
  useEffect(() => { if (q) firstChoiceRef.current?.focus({ preventScroll: true }) }, [q])
  // 소리 조건(C17): 답한 뒤에만 소리와 함께 다시 보기. 고르기는 그 무리의 대표 음절, AX는 두 음절(문항과 같은 600ms 쉼)
  const sound = useSoundCondition()
  const replay = useSoundReplay({
    texts: !q ? [] : q.kind === 'ax' ? [q.pair.a, q.pair.b] : [q.target.demo_syllable].filter(Boolean),
    answered: !!result, enabled: sound.enabled,
    onPlayed: () => q && (q.kind === 'ax'
      ? soundAPI.logReplay('trial', `${q.pair.a}/${q.pair.b}`, 'viseme_ax')
      : soundAPI.logReplay('trial', String(q.target.viseme_id), 'viseme')).catch(() => {}),
  })
  const [submitting, setSubmitting] = useState(false)
  const [stat, setStat] = useState(() => checkpoint && Object.hasOwn(checkpoint, 'stat') ? checkpoint.stat : ({ attempts: 0, mastery: 0, mastered: false }))
  const [qNum, setQNum] = useState(() => checkpoint && Object.hasOwn(checkpoint, 'qNum') ? checkpoint.qNum : (1)) // 레슨 내 문항 번호(진행바)
  const [tally, setTally] = useState(() => checkpoint && Object.hasOwn(checkpoint, 'tally') ? checkpoint.tally : ({ n: 0, correct: 0 })) // 이번 레슨에서 푼 문항·정답 수 → 완료 뷰 정답률
  const [done, setDone] = useState(() => checkpoint && Object.hasOwn(checkpoint, 'done') ? checkpoint.done : (false)) // 12문항을 마치면 완료 뷰(93:12)
  const [xpEarned, setXpEarned] = useState(() => checkpoint && Object.hasOwn(checkpoint, 'xpEarned') ? checkpoint.xpEarned : (0)) // 레슨 동안 서버가 준 XP 합(응답 xp_gained) → 완료 뷰
  const isAx = q?.kind === 'ax'
  // 문항 북마크 — 입모양 그룹의 대표 음절(없으면 이름)을 저장한다. 저장한 문장 화면에서 그 음절 입모양을 다시 본다.
  // AX 문항은 저장하지 않는다.
  const [saved, toggleSaved] = useBookmark(q && !isAx ? (q.target.demo_syllable || lessonLabel(q.target)) : null,
    { situation: q && !isAx ? `입모양 · ${q.target.name}` : '' })
  const startRef = useRef(checkpoint?.startRef ?? (Date.now()))              // 레슨 시작 시각 → 걸린 시간
  const [elapsedSec, setElapsedSec] = useState(() => checkpoint && Object.hasOwn(checkpoint, 'elapsedSec') ? checkpoint.elapsedSec : (0))
  // 레슨마다 가상 화자 한 명(계획 2-2). 다섯 레슨마다 첫 레슨은 기본 화자다.
  const [lesson, nextLesson] = useLessonTalker('viseme', checkpoint?.lesson)
  // 숙달 지연 탐침(C16): 숙달한 단계가 있으면 레슨 가운데에 확인 문항을 끼운다(비율 상한은 서버, 숙달·XP에는 들어가지 않음)
  const probes = useMasteryProbes(QUIZ_LEN)
  const { defaults: learner } = useLearnerInfo()   // 짧은 힌트(계획 2-6): 독화 포인트를 첫 문장만 먼저

  // 레슨(12문항)의 정답 무리 순서: 무리마다 두 번씩, 연달아 같은 무리 없이(lib/visemeOptions.balancedTargets).
  // 예전 매 문항 무작위는 한 레슨에서 무리 하나 이상이 빠질 확률이 56%였다.
  // 첫 바퀴(1~6번, 무리 여섯이 한 번씩) 뒤 7~12번 가운데 두 자리는 AX 문항(입 안쪽 짝 1, 보이는 짝 1)이다. AX 답은 1단계 숙달에
  // 넣지 않는다(docs/mastery-ewma.md 11.9절: 오답 −1로 넣는 설계는 거짓 숙달을 늘려 탈락, 숙달에서 뺀 설계가 확인을 통과).
  const deckRef = useRef(checkpoint?.deckRef ?? ({ list: [], i: 0, axAt: new Set(), axItems: [], axI: 0 }))
  const pickQ = useCallback(() => {
    const target = deckRef.current.list[deckRef.current.i++] || quizzable[0]
    // 오답은 화면에서 가를 수 있는 무리만(정답이 중설모음이면 입 안쪽 무리 제외, lib/visemeOptions).
    // 후보는 정답과 같은 모집단(quizzable)으로 한다. 10개 무리 전체에서 뽑으면 정답이 될 수 없는 6·7·8·10이 보기에 섞여,
    // 입을 보지 않고 보기 구성만으로 맞히는 최적 추측이 0.554였다(지금 0.250 = 4지선다 찬스).
    const others = pickVisemeDistractors(target.viseme_id, quizzable)
    // 보기는 쉬운 이름('입술 닫힘 (바·마)', lib/visemeLabels). 예전 '양순음(ㅂ, ㅃ, ㅍ, ㅁ)'은 이름표를 외우고 긴 글을 읽어야 했다
    const choices = shuffle([target, ...others]).map((l) => ({ viseme_id: l.viseme_id, name: lessonPlainLabel(l) }))
    return { kind: 'pick', target, choices }
  }, [quizzable])
  const newQ = useCallback((fresh = false, n = 1) => {
    if (fresh || deckRef.current.i >= deckRef.current.list.length) {
      deckRef.current = { list: balancedTargets(quizzable, QUIZ_LEN), i: 0, axAt: axSlots(QUIZ_LEN, quizzable.length),
        axItems: pickAxItems(), axI: 0 }
    }
    setSelected(null)
    setResult(null)
    const deck = deckRef.current
    if (!deck.axAt.has(n) || deck.axI >= deck.axItems.length) {
      setQ(pickQ())
      return
    }
    const pair = deck.axItems[deck.axI++]
    const axQ = { kind: 'ax', pair, frames: null }
    setQ(axQ)
    // 두 음절의 입모양 프레임은 엔진(/api/viseme)에서 받는다. 받지 못하면 이 자리는 고르기 문항으로 낸다
    Promise.all([learningAPI.getVisemes(pair.a), learningAPI.getVisemes(pair.b)])
      .then(([fa, fb]) => setQ((cur) => (cur === axQ ? { ...axQ, frames: axFrames(fa, fb) } : cur)))
      .catch(() => setQ((cur) => (cur === axQ ? pickQ() : cur)))
  }, [quizzable, pickQ])

  useEffect(() => { if (!checkpoint?.q) newQ(true) }, [newQ])
  useEffect(() => {
    if (checkpoint?.q?.kind !== 'ax' || checkpoint.q.frames) return
    let alive = true
    const { a, b } = checkpoint.q.pair
    Promise.all([learningAPI.getVisemes(a), learningAPI.getVisemes(b)])
      .then(([fa, fb]) => { if (alive) setQ(cur => ({ ...cur, frames: axFrames(fa, fb) })) })
      .catch(() => { if (alive) setQ(pickQ()) })
    return () => { alive = false }
  }, [])

  const answerAx = async (choice) => {
    if (!isAx || !q.frames || result || submitting) return
    if (!submission.begin(choice)) return
    setSubmitting(true)
    try {
      const r = await curriculumAPI.submitRecognitionAx(q.pair.a, q.pair.b, choice, AX_CHOICES.map((c) => c.key),
        trialMeta({ onsetAt: onsetRef.current, talker: lesson.talker || 'default', soundCondition: sound.enabled }))
      submission.finish()
      setResult({ ...r, chosenKey: choice })
      setXpEarned((x) => x + (r.xp_gained || 0))
      setTally((t) => ({ n: t.n + 1, correct: t.correct + (r.correct ? 1 : 0) }))
    } catch {
      advance()
      /* 네트워크 실패는 조용히 무시 — 다시 시도 가능 */
    } finally {
      setSubmitting(false)
    }
  }

  // 보기 숫자 키 1~4(§4-03), AX는 1·2. 채점 중·결과 표시 중에는 받지 않는다.
  useChoiceKeys(isAx ? AX_CHOICES : q?.choices, (c) => (isAx ? answerAx(c.key) : setSelected(c.viseme_id)),
    !!q && !result && !submitting && !done && (!isAx || !!q.frames))

  const confirm = async () => {
    if (result || submitting || selected == null || isAx) return
    if (!submission.begin(selected)) return
    setSubmitting(true)
    try {
      const r = await curriculumAPI.submitRecognition(q.target.viseme_id, selected, q.choices.map((c) => c.viseme_id),
        trialMeta({ onsetAt: onsetRef.current, talker: lesson.talker || 'default', soundCondition: sound.enabled }))
      submission.finish()
      setResult({ ...r, chosenId: selected })
      setStat({ attempts: r.attempts, mastery: r.mastery_score, mastered: r.mastered })
      setXpEarned((x) => x + (r.xp_gained || 0))
      setTally((t) => ({ n: t.n + 1, correct: t.correct + (r.correct ? 1 : 0) }))
    } catch {
      advance()
      /* 네트워크 실패는 조용히 무시 — 다시 시도 가능 */
    } finally {
      setSubmitting(false)
    }
  }
  // 계속하기 — 12번째 문항 뒤에는 완료 뷰로(걸린 시간은 이 순간으로 고정).
  const advance = () => {
    if (qNum >= QUIZ_LEN) {
      setElapsedSec(Math.floor((Date.now() - startRef.current) / 1000))
      setDone(true)
      return
    }
    setQNum(qNum + 1)
    newQ(false, qNum + 1)
  }
  // 레슨 가운데 문항 뒤에는 오늘 낼 지연 탐침이 있으면 먼저 낸다(끝나면 advance로 이어 간다)
  const next = () => { if (!probes.take(qNum)) advance() }
  // 새 레슨(12문항) — 단계를 아직 숙달하지 못했을 때 '다음 레슨으로'가 같은 단계의 다음 세트를 연다.
  const restart = () => {
    setDone(false); setQNum(1); setTally({ n: 0, correct: 0 }); setXpEarned(0)
    startRef.current = Date.now()
    nextLesson()
    probes.reload()
    newQ(true, 1)
  }

  const recoveredRef = useRef(false)
  useEffect(() => {
    if (submission.sent && !recoveredRef.current) {
      recoveredRef.current = true
      submission.finish()
      if (!result && submission.sent.question === qNum) advance()
    }
  }, [])

  if (q) saveCheckpoint({ data, q, selected, result, stat, qNum, tally, done, xpEarned, elapsedSec, lesson, deckRef: deckRef.current, startRef: startRef.current })

  if (!q) return null

  if (probes.open) return <MasteryProbeBlock items={probes.items} onDone={() => { probes.finish(); advance() }} />

  if (done) {
    const accuracy = tally.n ? Math.round((tally.correct / tally.n) * 100) : 0
    return (
      <LessonComplete accuracy={accuracy} xp={xpEarned} elapsedSec={elapsedSec}
        onNext={() => (stat.mastered ? navigate('/learn/word') : restart())}
        onHome={() => { clearCheckpoint(); navigate('/learn/path') }}
        effort={{ lessonKind: 'viseme', stage: 1, nItems: tally.n, accuracy: tally.n ? tally.correct / tally.n : null }} />
    )
  }

  const answered = qNum - 1 + (result ? 1 : 0)
  const pct = Math.round((answered / QUIZ_LEN) * 100)

  const optionState = (c) => {
    if (!result) return selected === c.viseme_id ? 'selected' : 'idle'
    if (c.viseme_id === q.target.viseme_id) return result.chosenId === c.viseme_id ? 'correct' : 'target'
    return result.chosenId === c.viseme_id ? 'wrong' : 'idle'
  }
  const axState = (c) => {
    if (!result) return 'idle'
    if (c.key === result.answer) return result.chosenKey === c.key ? 'correct' : 'target'
    return result.chosenKey === c.key ? 'wrong' : 'idle'
  }
  // AX 결과 설명. 입 안쪽 '같음' 짝은 1단계가 가르치는 '같아 보이는 무리'를 짚는 안내라 경고색으로 강조한다
  const axSameLooking = isAx && q.pair.inside && q.pair.same

  return (
    <>
      <div className={`${LESSON_COL} ${lessonPad(!!result)}`}>
        {/* 진행 헤더(91:13 / 모바일 235:35) — 나가기 X + 트랙 + n / 12 */}
        <div className="flex items-center gap-3 lg:gap-[18px]">
          <button type="button" onClick={() => navigate('/learn/path')} aria-label="나가기" className="shrink-0">
            <img src="/ui/lp-91-12-close.svg" alt="" className="size-8 lg:size-9" />
          </button>
          <Progress value={pct} label="레슨 진행률" animated className="lg:h-[14px]" />
          <LessonA11yButton />
          <span className="shrink-0 text-[13px] font-bold leading-figma text-ink-muted lg:text-[15px]">{qNum} / {QUIZ_LEN}</span>
        </div>

        <div className={LESSON_STACK}>
          {/* 질문 + 북마크(91:19 · 328:40 / 모바일 235:42 · 328:64) */}
          <div className="relative flex flex-col gap-1.5 pr-12 leading-figma lg:gap-2 lg:pr-[52px]">
            <p className="text-[12px] font-bold text-track lg:text-[13px]">입모양 인지</p>
            <h1 className="text-[21px] font-bold tracking-[-0.525px] text-ink lg:text-[30px] lg:tracking-[-0.75px]">
              {isAx ? '두 입모양이 같을까요?' : '이 입모양은 어느 그룹일까요?'}
            </h1>
            {!isAx && <BookmarkButton active={saved} onToggle={toggleSaved} className="absolute right-0 top-[14px] lg:top-[21px]" />}
          </div>

          {/* 입모양 카드(91:22 560×370 / 모바일 235:45 전체 폭×214) — 아바타만, 무한 반복(다시 보기 없음).
              고르기는 입모양 하나를 되풀이하고, AX는 음절 둘을 쉼을 두고 차례로 되풀이한다(프레임을 받기 전에는 중립) */}
          <div className={LESSON_AVATAR_VISEME}>
            <MouthAvatar loadingHint frames={isAx ? q.frames : null} visemeId={isAx ? (q.frames ? null : 15) : q.target.viseme_id}
              height={null} className="h-full" talker={lesson.talker} talkerSeed={lesson.seed} override={replay.frame} />
          </div>

          {isAx ? (
            // AX(같은지 다른지): 큰 버튼 둘, 누르면 바로 채점
            <div className="grid grid-cols-2 gap-2.5 lg:gap-3">
              {AX_CHOICES.map((c, i) => (
                <button ref={i === 0 ? firstChoiceRef : undefined} key={c.key} type="button" disabled={!!result || submitting || !q.frames} onClick={() => answerAx(c.key)}
                  aria-label={c.label} className={`${AX_BTN_CLASS[axState(c)]} disabled:cursor-default`}>
                  <span className="text-[44px] font-bold leading-none lg:text-[52px]" aria-hidden>{c.mark}</span>
                  <span className="text-[17px] font-bold leading-figma lg:text-[19px]">{c.label}</span>
                  <span className="absolute left-3 top-3 flex size-6 items-center justify-center rounded-[7px] bg-fill text-[12px] font-bold text-ink-muted" aria-hidden>{i + 1}</span>
                </button>
              ))}
            </div>
          ) : (
            // 4지선다(91:28 / 모바일 235:51) — 선택 → 확인
            <div className={LESSON_OPTIONS}>
              {q.choices.map((c, i) => (
                <button ref={i === 0 ? firstChoiceRef : undefined} key={c.viseme_id} type="button" disabled={!!result || submitting} onClick={() => setSelected(c.viseme_id)}
                  aria-pressed={!result ? selected === c.viseme_id : undefined} className={OPTION_CLASS[optionState(c)]}>
                  <span className="flex size-6 shrink-0 items-center justify-center rounded-[7px] bg-fill text-[12px] font-bold leading-figma text-ink-muted lg:size-7 lg:rounded-lg lg:text-[13px]">{i + 1}</span>
                  <span className="flex-1 text-[18px] font-bold leading-figma lg:text-[20px]">{c.name}</span>
                </button>
              ))}
            </div>
          )}

          {/* 결과 상세(독화 포인트 · 같아 보이는 무리 안내) — 핵심 교육 패널이라 유지, 고정 바 위 스크롤 영역 */}
          <AnimatePresence>
            {result && (
              <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-3">
                <SoundReplayBar sound={sound} replay={replay} />
                {isAx ? (
                  <div className={axSameLooking
                    ? 'rounded-16 border border-warn/40 bg-warn-tint px-4 py-3 text-[13px] text-warn-text'
                    : 'rounded-16 border border-line bg-white p-3 text-[13px] text-ink-muted'}>
                    <b>「{q.pair.a}」·「{q.pair.b}」</b> {axExplain(q.pair)}
                  </div>
                ) : (
                  <div className="rounded-16 border border-line bg-white p-3 text-[13px] text-ink-muted">
                    <ShortText key={result.target.viseme_id} text={result.target.teach} short={learner.shortHints} />
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* 하단 고정 바 — 문제(130:17) · 정답(94:133) · 오답(94:175). lg 미만(235:68 · 235:105)은 힌트 없이
          메시지 위·전체 폭 버튼 아래로 쌓는다(§4-12 "모바일 레슨의 하단 버튼은 전체 폭"). AX는 버튼을 누르면 바로 채점해 확인 버튼이 없다. */}
      <div className={`fixed inset-x-0 bottom-0 z-40 border-t-2 ${!result ? 'border-line bg-white' : result.correct ? 'border-good bg-good-tint lg:border-good/35' : 'border-bad bg-bad-tint lg:border-bad/35'}`}>
        <div className="mx-auto flex max-w-[676px] flex-col items-stretch gap-3 px-[18px] pb-[calc(22px+env(safe-area-inset-bottom))] pt-4 lg:h-[110px] lg:flex-row lg:items-center lg:justify-between lg:gap-4 lg:py-0">
          {result ? (
            // 정오 피드백은 스크린리더에 알린다(role=status·aria-live) — 잔존청력·저시력 사용자 대상(c92fdc3, 병합 복원)
            <div role="status" aria-live="polite" className={`flex min-w-0 flex-col gap-[3px] leading-figma lg:gap-1 ${result.correct ? 'text-good-text' : 'text-bad-text'}`}>
              <p className="text-[19px] font-bold tracking-[-0.38px] lg:text-[22px] lg:tracking-[-0.44px]">{result.correct ? '정답이에요!' : '아쉬워요'}</p>
              <p className="line-clamp-2 text-[13px] font-bold opacity-80 lg:text-[14px]">
                {isAx ? `두 입모양은 ${result.answer === 'same' ? '같아요' : '달라요'}`
                  : result.correct ? (learner.shortHints ? splitFirstSentence(result.target.teach).first : result.target.teach)
                  : `정답은 「${lessonPlainLabel(q.target)}」예요`}
              </p>
            </div>
          ) : isAx ? (
            <span className="text-[15px] leading-figma text-ink-faint">{q.frames ? '같으면 =, 다르면 ≠' : '입모양을 가져오는 중'}</span>
          ) : (
            <span className="hidden text-[15px] leading-figma text-ink-faint lg:inline">{selected == null ? '보기를 선택해주세요' : '정답을 확인해보세요'}</span>
          )}
          {result ? (
            <button ref={continueRef} type="button" onClick={next} className={`${result.correct ? 'btn-good' : 'btn-bad'} btn-bar ${BAR_BTN}`}>계속하기</button>
          ) : !isAx && (
            <button type="button" onClick={confirm} disabled={selected == null || submitting} className={`btn-primary btn-bar ${BAR_BTN}`}>확인</button>
          )}
        </div>
      </div>
    </>
  )
}

// 하단 바 버튼 — 데스크톱 .btn-bar(40/15, 17px) 오른쪽, lg 미만 전체 폭 py16·16px(235:69 · 235:109)
const BAR_BTN = 'w-full shrink-0 max-lg:py-4 max-lg:text-[16px] lg:w-auto'

// 보기 한 줄(91:29 / 모바일 235:52) — 1px 테두리. 정답·오답 공개(94:119 · 94:161 · 94:169)는 같은 색 안쪽 링을 더한다.
const OPTION_BASE = 'flex w-full items-center gap-3.5 rounded-14 px-[18px] py-[15px] text-left transition-colors lg:gap-4 lg:rounded-16 lg:px-5 lg:py-4'
// 11/03: 고름·정답·오답은 1px 테두리 안쪽에 1px 링을 더해 2px처럼 보이게 한다(box-shadow라 보기 높이가 바뀌지 않는다).
const OPTION_CLASS = {
  idle: `${OPTION_BASE} border border-line bg-white text-ink enabled:hover:border-primary-300 enabled:active:scale-[0.99]`,
  selected: `${OPTION_BASE} border border-track ring-1 ring-inset ring-track bg-track-tint text-ink`,
  correct: `${OPTION_BASE} border border-good ring-1 ring-inset ring-good bg-good-tint text-good-text`,   // 고른 답이 정답
  target: `${OPTION_BASE} border border-good ring-1 ring-inset ring-good bg-white text-ink`,              // 오답일 때 정답 표시
  wrong: `${OPTION_BASE} border border-bad ring-1 ring-inset ring-bad bg-bad-tint text-bad-text`,        // 고른 오답
}

// AX 답 버튼(같아요 · 달라요). 보기와 같은 테두리·공개 색을 쓰고, 글 대신 큰 기호가 눈에 먼저 들어오게 세로로 쌓는다.
const AX_BTN_BASE = 'relative flex h-[112px] w-full flex-col items-center justify-center gap-1.5 rounded-16 transition-colors lg:h-[132px]'
const AX_BTN_CLASS = {
  idle: `${AX_BTN_BASE} border border-line bg-white text-ink enabled:hover:border-primary-300 enabled:active:scale-[0.99]`,
  correct: `${AX_BTN_BASE} border border-good ring-1 ring-inset ring-good bg-good-tint text-good-text`,
  target: `${AX_BTN_BASE} border border-good ring-1 ring-inset ring-good bg-white text-ink`,
  wrong: `${AX_BTN_BASE} border border-bad ring-1 ring-inset ring-bad bg-bad-tint text-bad-text`,
}

export default QuizPanel
