import { useState, useEffect, useMemo, useCallback, useRef, lazy, Suspense } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { curriculumAPI, learningAPI } from '../api'
import MouthAvatar from '../components/MouthAvatar'
import BookmarkButton from '../components/BookmarkButton'
import WatermarkCard from '../components/WatermarkCard'
import LoadingScreen from '../components/LoadingScreen'
import { LoadFailed } from '../components/ErrorScreen'
import { ModalClose } from '../components/Modal'
import useFocusTrap from '../hooks/useFocusTrap'
import useChoiceKeys from '../lib/useChoiceKeys'
import useBookmark from '../lib/useBookmark'
import CueBadges, { CueLegend } from '../components/CueBadges'
import { pickDistractors, visualLevel } from '../lib/wordOptions'
import { LESSON_COL, LESSON_STACK, LESSON_AVATAR, LESSON_OPTIONS, lessonPad } from '../lib/lessonLayout'
import useSlowWeak from '../hooks/useSlowWeak'
import useLessonTalker from '../hooks/useLessonTalker'
import useMasteryProbes from '../hooks/useMasteryProbes'
import MasteryProbeBlock from '../components/MasteryProbeBlock'
import EffortCheck from '../components/EffortCheck'
import { effectiveSpeed, FAST_SPEECH_SPEED } from '../lib/visemeTiming'
import { typedSlots, contextSlots, probeSlot, pickProbe } from '../lib/openSet'
import MouthCompare from '../components/MouthCompare'

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

const fmtDuration = (sec) => `${Math.floor(sec / 60)}분 ${sec % 60}초`

// 레슨 완료 스탯 카드(93:22) — 모바일은 카드 폭이 좁아 여백·값 글자를 줄인다(모바일 프레임 없음).
const STAT_CARD = 'flex min-w-0 flex-1 flex-col gap-2 rounded-18 border-2 border-line bg-white p-3.5 lg:p-5'
const STAT_LABEL = 'text-[13px] font-bold leading-figma text-ink-soft'
const STAT_VALUE = 'text-[20px] font-bold leading-figma tracking-[-0.5px] lg:text-[28px] lg:tracking-[-0.7px]'
// 완료 버튼 — 데스크톱 75:23(btn-lg), lg 미만은 모바일 버튼 규격(r14·b5, py16, 16px)
const DONE_BTN = 'w-full max-lg:rounded-14 max-lg:border-b-5 max-lg:py-4 max-lg:text-[16px]'

// Figma "Lesson / 4. 완료"(93:12) — 레슨 컴포넌트의 마지막 상태. DOKA + 워터마크 스탯 3칸 + 버튼 2개.
function LessonComplete({ accuracy, xp, elapsedSec, onNext, onHome, homeLabel = '커리큘럼으로 돌아가기', effort }) {
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

      {/* 레슨별 정신적 노력 한 문항(C14, Paas 9점) — 답하지 않아도 된다. 기록만 하고 다음 레슨에는 쓰지 않는다 */}
      {effort && <EffortCheck {...effort} />}

      <div className="flex w-full max-w-[640px] flex-col gap-2.5 lg:gap-3">
        <button type="button" onClick={onNext} className={`btn-primary btn-lg ${DONE_BTN}`}>다음 레슨으로</button>
        <button type="button" onClick={onHome} className={`btn-secondary btn-lg text-track ${DONE_BTN}`}>{homeLabel}</button>
      </div>
    </div>
  )
}

export default function WordStage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [introDone, setIntroDone] = useState(false)
  const load = useCallback(() => {
    setLoading(true)
    curriculumAPI.getWords().then(setData).catch(() => setData(null)).finally(() => setLoading(false))
  }, [])
  useEffect(() => {
    load()
    const t = setTimeout(() => setIntroDone(true), INTRO_MS)
    return () => clearTimeout(t)
  }, [load])
  // 레슨 시작 전 = 독화 트랙 로딩(223:30 / 모바일 243:81)
  if (loading || !introDone) return <LoadingScreen variant="brand" track="perception" />
  // 불러오기 실패: 다시 시도, 나가기는 레슨의 X와 같은 곳(엔드리스면 엔드리스 화면, 아니면 학습 경로)
  if (!data) {
    return <LoadFailed onRetry={load}
      onExit={() => navigate(params.get('endless') === '1' ? '/learn/endless' : '/learn/path')} />
  }
  return (
    <div className="min-h-[100dvh] bg-page">
      <WordQuiz data={data} reload={load} />
    </div>
  )
}

function WordQuiz({ data, reload }) {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const endless = params.get('endless') === '1'   // 엔드리스 혼합 세션(단어 ↔ 문맥, G-6)
  const words = useMemo(() => data.words.map((w) => w.word), [data])
  // 입모양 난이도(1~5) — 서버가 준 시각 난이도 분위(visual_difficulty)로 매긴다. 예전에는 빈도 등급(tier)을 '난이도'로 보여 줬는데,
  // 자주 쓰는 짧은 말(등급 1)이 입모양으로는 가장 어려워 표시가 거꾸로였다(9/27, 등급과 시각 난이도 순위상관 −0.35).
  const levelOf = useMemo(() => Object.fromEntries(data.words.map((w) => [w.word, visualLevel(w.quantile)])), [data])
  const byWord = useMemo(() => new Map(data.words.map((w) => [w.word, w])), [data])
  const [q, setQ] = useState(null)
  // 문항 북마크 — 서버에 저장돼 복습 탭·저장한 문장에 나온다
  const [saved, toggleSaved] = useBookmark(q?.kind === 'context' ? q.full : q?.target, { situation: q?.kind === 'context' ? '문맥 추론' : '단어 독화' })
  const [frames, setFrames] = useState([])
  const visemeSeqRef = useRef(0)   // 입모양 요청 순번: 이전 문항의 늦은 응답이 새 문항 화면을 덮지 않게
  const [stat, setStat] = useState({ attempts: 0, mastery: 0, mastered: false })
  // 약한 입모양은 조금 천천히(연습 화면). 숙달 추정값이 문턱(서버 natural_speed_gate, 70) 이상이면 감속을 끄고 자연 속도로
  // 낸다. 감속해 본 정답은 숙달에 0.5만 들어가서, 끄지 않으면 자연 속도로 잘 읽어도 숙달에 닿지 못할 수 있다(docs/mastery-ewma.md 7절).
  const estimate = stat.attempts > 0 ? stat.mastery : (data.mastery_score ?? 0)
  // 숙달한 뒤 엔드리스에서는 '빠른 말' 속도 단계를 고를 수 있다(1.0배 이상이라 숙달에는 정답 1로 들어간다). 서버가 연 단계
  // (speed_levels: 1.25 → 1.6 → 2.0배, 한 단계에서 최근 12문항 중 10문항을 맞히면 다음 단계). 엔진 1.0배는 실제 말의 약 절반 빠르기다.
  const [fast, setFast] = useState(1)
  const speedLevels = endless && (data.mastered || stat.mastered)
    ? (data.speed_levels?.length ? data.speed_levels : [FAST_SPEECH_SPEED]) : []
  const fastOk = speedLevels.length > 0
  const playSpeed = fastOk && speedLevels.includes(fast) ? fast : 1
  // 빠른 말을 고른 동안은 약점 감속을 끈다(켜 두면 고른 속도보다 느리게 보이고 기록돼 속도 단계에 세지 않았다, 9/28 검토)
  const shownFrames = useSlowWeak(frames, estimate < (data.natural_speed_gate ?? 70) && playSpeed <= 1)
  // 레슨마다 가상 화자 한 명(계획 2-2, 엔드리스는 단어·문맥 레슨을 한 줄로 센다). 화자의 말 속도는 숙달에 싣는 재생 속도
  // (effectiveSpeed)에 넣지 않는다. 사람마다 다른 자연 속도라 감속이 아니다(docs/talker-variation.md 3절).
  const [lesson, nextLesson] = useLessonTalker(endless ? 'endless' : 'word')
  // 숙달 지연 탐침(C16): 숙달한 단계가 있으면 레슨 가운데에 확인 문항을 끼운다(비율 상한은 서버, 숙달·XP에는 들어가지 않음)
  const probes = useMasteryProbes(QUIZ_LEN)
  const [selected, setSelected] = useState(null)   // 확인 전 선택(선택→확인 2단계)
  const [result, setResult] = useState(null)
  const [compareOpen, setCompareOpen] = useState(false)   // 오답 뒤 정답·고른 말 입모양 나란히 비교(누를 때만 WebGL 둘 추가)
  const [submitting, setSubmitting] = useState(false)
  const [qNum, setQNum] = useState(1)              // 레슨 내 문항 번호(진행바)
  const [tally, setTally] = useState({ n: 0, correct: 0 })   // 이번 레슨에서 푼 문항·정답 수 → 완료 뷰 정답률
  const [done, setDone] = useState(false)          // 12문항을 마치면 완료 뷰(93:12)
  const [signOpen, setSignOpen] = useState(false)
  const closeSign = useCallback(() => setSignOpen(false), [])
  const signRef = useFocusTrap(signOpen, closeSign)          // 수어 모달 포커스 트랩·Esc
  const [xpEarned, setXpEarned] = useState(0)      // 레슨 동안 서버가 준 XP 합(응답 xp_gained) → 완료 뷰
  const startRef = useRef(Date.now())              // 레슨 시작 시각 → 걸린 시간
  const [elapsedSec, setElapsedSec] = useState(0)

  // 이번 레슨에서 이미 낸 단어. 예전에는 가중 복원추출이라 12문항 레슨의 33~39%에서 같은 단어가 다시 나와(앞에서 정답을 봤으니)
  // 기억으로 맞힌 답이 숙달에 들어갔다. 레슨 안에서는 뺀 채 가중 추출한다(새 레슨에서 초기화).
  const askedRef = useRef(new Set())
  // 레슨 문항 구성(lib/openSet), 레슨을 시작할 때 자리를 정한다.
  //  - 12문항 중 2문항은 문맥 문항(문장 속 빈칸, 보기는 입모양이 비슷한 단어, 계획 1-3). 이 답은 숙달에 넣지 않는다.
  //  - 숙달한 뒤에는 30%를 주관식(단어 입력)으로 낸다(계획 1-2).
  //  - 선다형 1문항(첫 문항 제외)은 짝 탐색 문항이다: 서버가 고른 짝의 target 자모 단어 + 대비 단어가 든 보기(혼동 짝 5.4-2).
  //    보통 단어 문항이라 숙달에 똑같이 들어가고, 시행 기록에 탐색 표시(probe)가 남는다.
  const masteredRef = useRef(false)
  masteredRef.current = !!(data.mastered || stat.mastered)
  const slotRef = useRef({ typed: new Set(), context: new Set(), probe: -1, pos: -1, ctx: 0 })
  const [typedText, setTypedText] = useState('')
  const newQ = useCallback(async (fresh = false) => {
    const ctxItems = data.context_items || []
    if (fresh) {
      askedRef.current = new Set()
      const context = contextSlots(QUIZ_LEN, Math.min(2, ctxItems.length))
      const typedSet = typedSlots(QUIZ_LEN, masteredRef.current, Math.random, context)
      const probe = probeSlot(QUIZ_LEN, new Set([...context, ...typedSet]))
      slotRef.current = { typed: typedSet, context, probe, pos: -1, ctx: 0 }
    }
    slotRef.current.pos += 1
    setResult(null)
    setCompareOpen(false)
    setSelected(null)
    setTypedText('')
    if (slotRef.current.context.has(slotRef.current.pos) && ctxItems.length) {
      const item = ctxItems[slotRef.current.ctx++ % ctxItems.length]
      const full = item.display.replace('___', item.answer)
      setQ({ kind: 'context', item, full, target: item.answer, choices: shuffle(item.options) })
      setFrames([])
      const seq = ++visemeSeqRef.current
      try { const f = await learningAPI.getVisemes(full); if (seq === visemeSeqRef.current) setFrames(f) } catch { /* ignore */ }
      return
    }
    const kind = slotRef.current.typed.has(slotRef.current.pos) ? 'typed' : 'choice'
    const probe = slotRef.current.pos === slotRef.current.probe ? pickProbe(data.probes, askedRef.current) : null
    if (probe) {
      askedRef.current.add(probe.word)
      setQ({ target: probe.word, choices: shuffle([probe.word, ...probe.distractors.slice(0, 3)]), kind: 'choice', probe: probe.probe })
      setFrames([])
      const seq = ++visemeSeqRef.current
      try { const f = await learningAPI.getVisemes(probe.word); if (seq === visemeSeqRef.current) setFrames(f) } catch { /* ignore */ }
      return
    }
    const left = data.words.filter((w) => !askedRef.current.has(w.word))
    const pool = left.length ? left : data.words
    const total = pool.reduce((s, w) => s + (w.priority || 1), 0)
    let r = Math.random() * total
    let target = pool[pool.length - 1].word
    for (const w of pool) { r -= (w.priority || 1); if (r <= 0) { target = w.word; break } }
    askedRef.current.add(target)
    const distractors = pickDistractors(target, byWord, words)
    setQ({ target, choices: shuffle([target, ...distractors]), kind })
    setFrames([])
    const seq = ++visemeSeqRef.current
    try { const f = await learningAPI.getVisemes(target); if (seq === visemeSeqRef.current) setFrames(f) } catch { /* ignore */ }
  }, [data, words, byWord])

  useEffect(() => { newQ(true) }, [newQ])

  // 보기 숫자 키 1~4(§4-03) — 채점 중·결과 표시 중·수어 창이 열려 있으면 받지 않는다.
  const typed = q?.kind === 'typed'
  const isContext = q?.kind === 'context'
  useChoiceKeys(q?.choices, (w) => setSelected(w), !!q && !typed && !result && !submitting && !signOpen && !done)

  // 주관식은 서버가 채점한다(visual_difficulty.typed_word_verdict): 정답, '입모양은 맞음'(입모양이 똑같은 다른 말, 숙달에 0.5), 오답.
  const answer = typed ? typedText.trim() : selected
  const confirm = async () => {
    if (result || submitting || !answer) return
    setSubmitting(true)
    let correct = typed ? answer.replace(/\s+/g, '') === q.target : answer === q.target
    let verdict = correct ? 'correct' : 'wrong'
    let confusions = []
    if (isContext) {
      // 문맥 문항: 숙달(stat)은 그대로, 시행 기록·취약 입모양에만 남는다(/api/curriculum/context-answer)
      try {
        const rc = await curriculumAPI.submitContext(q.item.id, answer, q.choices)
        correct = !!rc.correct
        confusions = rc.confusions || []
        setXpEarned((x) => x + (rc.xp_gained || 0))
      } catch { /* 기록 실패해도 진행 */ } finally { setSubmitting(false) }
      setResult({ correct, verdict: correct ? 'correct' : 'wrong', chosen: answer, confusions })
      setTally((t) => ({ n: t.n + 1, correct: t.correct + (correct ? 1 : 0) }))
      return
    }
    try {
      // 선다형은 보여 준 보기도 보낸다(시행 기록, 기회로 나눈 혼동률). 주관식은 보기가 없다
      const rr = await curriculumAPI.submitWord(q.target, correct, answer, effectiveSpeed(frames, shownFrames, playSpeed),
        typed ? 'typed' : undefined, typed ? undefined : q.choices, q.probe)
      setStat({ attempts: rr.attempts, mastery: rr.mastery_score, mastered: rr.mastered })
      confusions = rr.confusions || []
      if (typed && rr.verdict) { verdict = rr.verdict; correct = verdict === 'correct' }
      setXpEarned((x) => x + (rr.xp_gained || 0))
    } catch { /* 기록 실패해도 진행 */ } finally { setSubmitting(false) }
    setResult({ correct, verdict, chosen: answer, confusions })
    setTally((t) => ({ n: t.n + 1, correct: t.correct + (correct ? 1 : 0) }))
  }
  // 계속하기 — 12번째 문항 뒤에는 완료 뷰로(걸린 시간은 이 순간으로 고정).
  const advance = () => {
    if (qNum >= QUIZ_LEN) {
      setElapsedSec(Math.floor((Date.now() - startRef.current) / 1000))
      setDone(true)
      return
    }
    setQNum((n) => n + 1)
    newQ()
  }
  // 레슨 가운데 문항 뒤에는 오늘 낼 지연 탐침이 있으면 먼저 낸다(끝나면 advance로 이어 간다)
  const next = () => { if (!probes.take(qNum)) advance() }
  // 새 레슨(12문항) — 단계를 아직 숙달하지 못했을 때 '다음 레슨으로'가 같은 단계의 다음 세트를 연다.
  const restart = () => {
    setDone(false); setQNum(1); setTally({ n: 0, correct: 0 }); setXpEarned(0)
    startRef.current = Date.now()
    nextLesson()
    probes.reload()
    newQ(true)
  }

  if (!q) return null

  if (probes.open) return <MasteryProbeBlock items={probes.items} onDone={() => { probes.finish(); advance() }} />

  if (done) {
    const accuracy = tally.n ? Math.round((tally.correct / tally.n) * 100) : 0
    return (
      // 다음 레슨: 단계를 숙달했으면 3단계 문장(시나리오 선택 ScenarioHub → /practice. CurriculumPath READ_ROUTE와
      // 같은 진입점), 아니면 이 단계의 다음 12문항. 엔드리스(?endless=1)에서는 문맥 레슨과 번갈아 이어진다(G-6).
      <LessonComplete accuracy={accuracy} xp={xpEarned} elapsedSec={elapsedSec}
        onNext={() => (endless ? navigate('/learn/closure?endless=1') : stat.mastered ? navigate('/learn/scenario') : (reload ? reload() : restart()))}
        onHome={() => navigate(endless ? '/learn/endless' : '/learn/path')}
        homeLabel={endless ? '엔드리스 학습으로' : undefined}
        effort={{ lessonKind: 'word', stage: 2, nItems: tally.n, accuracy: tally.n ? tally.correct / tally.n : null }} />
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
      <div className={`${LESSON_COL} ${lessonPad(!!result)}`}>
        {/* 진행 헤더(91:13 / 모바일 235:35) — 나가기 X + 트랙 + n / 12 */}
        <div className="flex items-center gap-3 lg:gap-[18px]">
          <button type="button" onClick={() => navigate(endless ? '/learn/endless' : '/learn/path')} aria-label="나가기" className="shrink-0">
            <img src="/ui/lp-91-12-close.svg" alt="" className="size-8 lg:size-9" />
          </button>
          <div className="h-3 flex-1 overflow-hidden rounded-full bg-fill-strong lg:h-[14px]">
            <div className="h-full rounded-full bg-track transition-all duration-500" style={{ width: `${pct}%` }} />
          </div>
          <span className="shrink-0 text-[13px] font-bold leading-figma text-ink-muted lg:text-[15px]">{qNum} / {QUIZ_LEN}</span>
        </div>

        <div className={LESSON_STACK}>
          {/* 질문 + 북마크(91:19 · 328:40 / 모바일 235:42 · 328:64) */}
          <div className="relative flex flex-col gap-1.5 pr-12 leading-figma lg:gap-2 lg:pr-[52px]">
            <p className="text-[12px] font-bold text-track lg:text-[13px]">단어 독화{typed ? ' · 주관식' : isContext ? ' · 문맥' : ''}</p>
            <h1 className="text-[21px] font-bold tracking-[-0.525px] text-ink lg:text-[30px] lg:tracking-[-0.75px]">
              {typed ? '이 입모양은 어떤 단어일까요? 직접 적어 보세요' : isContext ? '빈칸에 들어갈 단어는 무엇일까요?' : '이 입모양은 어떤 단어일까요?'}
            </h1>
            {/* 문맥 문항: 아바타는 문장 전체를 말하고, 화면에는 빈칸 문장을 보인다. 보기는 입모양이 비슷해 문장 흐름으로 고른다 */}
            {isContext && (
              <p className="text-[16px] font-bold text-ink-soft lg:text-[18px]">
                {q.item.display.split('___').map((part, i, arr) => (
                  <span key={i}>{part}{i < arr.length - 1 && (
                    <span className="mx-0.5 inline-block min-w-[2.5em] border-b-2 border-track text-center text-track">
                      {result ? q.target : '\u00a0'}
                    </span>)}</span>
                ))}
              </p>
            )}
            <BookmarkButton active={saved} onToggle={toggleSaved} className="absolute right-0 top-[14px] lg:top-[21px]" />
          </div>

          {/* 입모양 카드(91:22 560×370 / 모바일 235:45 전체 폭×214) — 아바타만, 무한 반복(다시 보기 없음) */}
          <div className={LESSON_AVATAR}>
            {/* 시각증강 기호(축 J-3)는 답을 확인한 뒤에만 — 보기가 최소대립 짝이라 문제 중에 보이면 기호만으로 답이 드러난다.
                확인 뒤에는 약한 표적 입모양 음절에만 입꼬리 옆에 겹쳐 무엇이 달랐는지 보여 준다(숙달되면 흐려짐). */}
            <MouthAvatar frames={shownFrames} height={null} className="h-full" cueText={result && !isContext ? q.target : null} cueFocus speed={playSpeed}
              talker={lesson.talker} talkerSeed={lesson.seed} />
          </div>
          {fastOk && (
            <div className="flex flex-wrap items-center justify-center gap-1.5 text-xs" role="group" aria-label="빠른 말 속도">
              <span className="text-ink-faint">빠른 말</span>
              {[1, ...speedLevels].map((v) => (
                <button key={v} type="button" onClick={() => setFast(v)} aria-pressed={playSpeed === v}
                  className={`min-h-[36px] rounded-lg border px-3 py-1.5 transition-colors ${playSpeed === v ? 'border-primary-500 bg-primary-500 font-semibold text-white' : 'border-line bg-white text-ink hover:bg-fill'}`}>
                  {v === 2 ? '2x·실제' : `${v}x`}
                </button>
              ))}
              {speedLevels.length < 3 && <span className="text-ink-faint">다음 속도: 지금 가장 빠른 속도에서 12문항 중 10개</span>}
            </div>
          )}

          {/* 주관식(계획 1-2): 단어를 적고 Enter 또는 확인. 띄어쓰기·문장부호는 채점에서 보지 않는다 */}
          {typed ? (
            <form onSubmit={(e) => { e.preventDefault(); confirm() }} className={LESSON_OPTIONS}>
              <input type="text" value={typedText} onChange={(e) => setTypedText(e.target.value)} disabled={!!result || submitting}
                maxLength={20} autoComplete="off" aria-label="읽은 단어 입력" placeholder="읽은 단어를 적어 주세요"
                className={`w-full rounded-14 border-2 px-[18px] py-[15px] text-[18px] font-bold text-ink outline-none lg:rounded-16 lg:px-5 lg:py-4 lg:text-[20px] ${
                  !result ? 'border-line bg-white focus:border-track'
                    : result.verdict === 'correct' ? 'border-good bg-good-tint text-good-text'
                      : result.verdict === 'homophene' ? 'border-warn bg-warn-tint text-warn-text' : 'border-bad bg-bad-tint text-bad-text'}`} />
            </form>
          ) : (
          /* 4지선다(91:28 / 모바일 235:51) — 선택 → 확인 */
          <div className={LESSON_OPTIONS}>
            {q.choices.map((w, i) => (
              <button key={w} type="button" disabled={!!result || submitting} onClick={() => setSelected(w)}
                aria-pressed={!result ? selected === w : undefined} className={OPTION_CLASS[optionState(w)]}>
                <span className="flex size-6 shrink-0 items-center justify-center rounded-[7px] bg-fill text-[12px] font-bold leading-figma text-ink-muted lg:size-7 lg:rounded-lg lg:text-[13px]">{i + 1}</span>
                <span className="flex-1 text-[18px] font-bold leading-figma lg:text-[20px]">{w}</span>
              </button>
            ))}
          </div>
          )}

          {/* 결과 피드백(혼동 진단·큐·수어·립리딩) — 핵심 교육 패널이라 유지, 고정 바 위 스크롤 영역 */}
          <AnimatePresence>
            {result && (
              <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-3">
                {result.verdict === 'homophene' && (
                  <div className="rounded-16 border-2 border-warn/40 bg-warn-tint p-4 text-[13px] leading-snug text-warn-text">
                    <p className="text-xs font-bold">입모양은 맞았어요</p>
                    <p className="mt-1">「{result.chosen}」와 「{q.target}」는 입모양이 똑같아요. 입만 보고는 가를 수 없는 차이라 오답으로 보지 않고
                      절반만 인정해요. 실제 대화에서는 앞뒤 문맥으로 가려요.</p>
                  </div>
                )}
                {!result.correct && result.verdict !== 'homophene' && result.confusions?.length > 0 && (
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
                {isContext && (
                  <div className="rounded-16 border-2 border-line bg-white p-4 text-[13px] leading-snug text-ink-muted">
                    <p className="text-xs font-bold text-ink">문장으로 고르는 문항이에요</p>
                    <p className="mt-1">보기는 모두 입모양이 비슷해서 눈만으로는 가르기 어려워요. 앞뒤 말의 흐름으로 고르는 연습이에요.
                      이 문항은 단어 단계 숙달에는 들어가지 않아요.</p>
                    {q.item.hint && <p className="mt-1">힌트: {q.item.hint}</p>}
                  </div>
                )}
                {!isContext && !result.correct && result.chosen && (compareOpen
                  ? <MouthCompare target={q.target} chosen={result.chosen}
                      sameLooking={result.verdict === 'homophene' || (result.confusions?.length > 0 && result.confusions.every((cf) => cf.same_viseme))} />
                  : <button type="button" onClick={() => setCompareOpen(true)} className="btn-secondary w-full py-2.5 text-[14px] text-track">
                      「{q.target}」과 「{result.chosen}」 입모양 나란히 비교
                    </button>)}
                {!isContext && (<>
                <div className="rounded-16 border-2 border-line bg-white p-3">
                  <div className="flex items-center gap-2">
                    <CueBadges text={q.target} />
                    {levelOf[q.target] && <span className="text-[11px] text-ink-faint">입모양 난이도 {levelOf[q.target]}/5</span>}
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
                </>)}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* 하단 고정 바 — 문제(130:17) · 정답(94:133) · 오답(94:175). lg 미만(235:68 · 235:105)은 힌트 없이
          메시지 위·전체 폭 버튼 아래로 쌓는다(§4-12 "모바일 레슨의 하단 버튼은 전체 폭"). */}
      <div className={`fixed inset-x-0 bottom-0 z-40 border-t-2 ${!result ? 'border-line bg-white' : result.correct ? 'border-good bg-good-tint lg:border-good/35' : result.verdict === 'homophene' ? 'border-warn bg-warn-tint lg:border-warn/35' : 'border-bad bg-bad-tint lg:border-bad/35'}`}>
        <div className="mx-auto flex max-w-[676px] flex-col items-stretch gap-3 px-[18px] pb-[calc(22px+env(safe-area-inset-bottom))] pt-4 lg:h-[110px] lg:flex-row lg:items-center lg:justify-between lg:gap-4 lg:py-0">
          {result ? (
            // 정오 피드백은 스크린리더에 알린다(role=status·aria-live) — 잔존청력·저시력 사용자 대상(c92fdc3, 병합 복원)
            <div role="status" aria-live="polite" className={`flex min-w-0 flex-col gap-[3px] leading-figma lg:gap-1 ${result.correct ? 'text-good-text' : result.verdict === 'homophene' ? 'text-warn-text' : 'text-bad-text'}`}>
              <p className="text-[19px] font-bold tracking-[-0.38px] lg:text-[22px] lg:tracking-[-0.44px]">
                {result.correct ? '정답이에요!' : result.verdict === 'homophene' ? '입모양은 맞았어요' : '아쉬워요'}
              </p>
              <p className="truncate text-[13px] font-bold opacity-80 lg:text-[14px]">정답은 「{q.target}」예요</p>
            </div>
          ) : (
            <span className="hidden text-[15px] leading-figma text-ink-faint lg:inline">
              {typed ? (answer ? '정답을 확인해보세요' : '읽은 단어를 적어 주세요') : selected == null ? '보기를 선택해주세요' : '정답을 확인해보세요'}
            </span>
          )}
          {result ? (
            <button type="button" onClick={next} className={`${result.correct || result.verdict === 'homophene' ? 'btn-good' : 'btn-bad'} btn-bar ${BAR_BTN}`}>계속하기</button>
          ) : (
            <button type="button" onClick={confirm} disabled={!answer || submitting} className={`btn-primary btn-bar ${BAR_BTN}`}>확인</button>
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
// 정답·오답 공개(2.5px 테두리)는 하단 테두리가 5 → 2.5px로 얇아지므로 위 패딩을 2px 더해 보기 높이를 맞춘다(변경 내역 §0-4).
const OPTION_CLASS = {
  idle: `${OPTION_BASE} border-2 border-b-5 border-line bg-white text-ink enabled:hover:border-primary-300 enabled:active:scale-[0.99]`,
  selected: `${OPTION_BASE} border-2 border-b-5 border-track bg-track-tint text-ink`,
  correct: `${OPTION_BASE} pt-[17px] lg:pt-[18px] border-[2.5px] border-good bg-good-tint text-good-text`,   // 고른 답이 정답
  target: `${OPTION_BASE} pt-[17px] lg:pt-[18px] border-[2.5px] border-good bg-white text-ink`,              // 오답일 때 정답 표시
  wrong: `${OPTION_BASE} pt-[17px] lg:pt-[18px] border-[2.5px] border-bad bg-bad-tint text-bad-text`,        // 고른 오답
}
