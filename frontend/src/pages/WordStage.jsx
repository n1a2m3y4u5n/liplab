import { useState, useEffect, useMemo, useCallback, useRef, lazy, Suspense } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { curriculumAPI, learningAPI } from '../api'
import MouthAvatar from '../components/MouthAvatar'
import useFocusTrap from '../hooks/useFocusTrap'
import CueBadges, { CueLegend } from '../components/CueBadges'

// 트랙B(언어+독화) 앵커링: 단어의 뜻을 수어로 확인. 무거우니 열 때만 로드.
const SignPanel = lazy(() => import('../components/SignPanel'))
// 축 D 자체 립리딩(MediaPipe+onnx로 무거움) — 정답 후에만 로드.
const LipReadCheck = lazy(() => import('../components/LipReadCheck'))

/**
 * 2단계 · 음절·단어 (Word Stage) — Figma 리디자인 03(독화 레슨) 집중 레이아웃.
 * 입모양만 보고 어떤 단어인지 4지선다로 맞힌다. 오답 보기는 최소대립 단어 우선.
 * 레이아웃만 Figma로 교체하고 채점·혼동진단·립리딩·수어·숙달 로직은 그대로 보존한다.
 */
const shuffle = (a) => [...a].sort(() => Math.random() - 0.5)
const QUIZ_LEN = 12  // 세션당 문항 수(진행바 분모) — 숙달 판정과 별개인 표시용

function partnersOf(word, pairs, bankSet) {
  const out = new Set()
  for (const m of pairs) {
    if (m.a === word && bankSet.has(m.b)) out.add(m.b)
    if (m.b === word && bankSet.has(m.a)) out.add(m.a)
  }
  return [...out]
}

const fmtDuration = (sec) => `${Math.floor(sec / 60)}분 ${sec % 60}초`

// Figma "Lesson / 4. 완료"(93:12) — 세션 숙달 시 퀴즈 UI를 대체하는 전용 완료 뷰.
// 마스코트 + 스탯 3장(정답률·획득 XP·걸린 시간) + 3D 버튼 2개(다음 레슨 / 커리큘럼).
function LessonComplete({ mastery, xp, elapsedSec, onNext, onHome }) {
  return (
    <div className="flex min-h-[100dvh] w-full flex-col items-center justify-center gap-[26px] bg-[#f3f3f3] px-4 py-12">
      <img src="/ui/lp-93-12-mascot.svg" alt="" className="h-[140px] w-[140px]" />
      <p className="text-[38px] font-bold tracking-[-0.95px] text-[#1a1a2e]">레슨 완료!</p>

      <div className="flex w-full max-w-[640px] gap-[14px]">
        <div className="relative flex-1 overflow-hidden rounded-[18px] border-2 border-[#e2e2e8] bg-white p-5">
          <img src="/ui/lp-93-12-deco-percent.svg" alt="" className="pointer-events-none absolute -top-6 -right-6 w-[115px] -rotate-[20deg] opacity-20" />
          <p className="relative text-[13px] font-bold text-[#7a7a8c]">정답률</p>
          <p className="relative mt-1 text-[28px] font-bold text-[#5f3ab8]">{mastery}%</p>
        </div>
        <div className="relative flex-1 overflow-hidden rounded-[18px] border-2 border-[#e2e2e8] bg-white p-5">
          <img src="/ui/lp-93-12-deco-xp.svg" alt="" className="pointer-events-none absolute -top-6 -right-6 w-[158px] opacity-20" />
          <p className="relative text-[13px] font-bold text-[#7a7a8c]">획득 XP</p>
          <p className="relative mt-1 text-[28px] font-bold text-[#b45309]">+{xp}</p>
        </div>
        <div className="relative flex-1 overflow-hidden rounded-[18px] border-2 border-[#e2e2e8] bg-white p-5">
          <img src="/ui/lp-93-12-deco-clock.svg" alt="" className="pointer-events-none absolute -top-6 -right-6 w-[115px] opacity-20" />
          <p className="relative text-[13px] font-bold text-[#7a7a8c]">걸린 시간</p>
          <p className="relative mt-1 text-[28px] font-bold text-[#0369a1]">{fmtDuration(elapsedSec)}</p>
        </div>
      </div>

      <div className="flex w-full max-w-[640px] flex-col gap-[12px]">
        <button type="button" onClick={onNext}
          className="w-full rounded-[16px] border-2 border-b-[6px] border-[#5f3ab8] bg-[#7d53de] py-[18px] text-[20px] font-bold text-white transition-all active:translate-y-[2px] active:border-b-2">다음 레슨으로</button>
        <button type="button" onClick={onHome}
          className="w-full rounded-[16px] border-2 border-b-[6px] border-[#e2e2e8] bg-white py-[18px] text-[20px] font-bold text-primary-500 transition-all active:translate-y-[1px] active:border-b-2">커리큘럼으로 돌아가기</button>
      </div>
    </div>
  )
}

export default function WordStage() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    curriculumAPI.getWords().then(setData).catch(() => setData(null)).finally(() => setLoading(false))
  }, [])
  if (loading) return <div className="flex min-h-[100dvh] items-center justify-center text-gray-500">불러오는 중…</div>
  if (!data) return <div className="flex min-h-[100dvh] items-center justify-center text-gray-500">불러오지 못했어요.</div>
  return (
    <div className="min-h-[100dvh] bg-[#f3f3f3]">
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
  const [frames, setFrames] = useState([])
  const [selected, setSelected] = useState(null)   // 확인 전 선택(선택→확인 2단계)
  const [result, setResult] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [stat, setStat] = useState({ attempts: 0, mastery: 0, mastered: false })
  const [qNum, setQNum] = useState(1)              // 세션 내 문항 번호(진행바)
  const [signOpen, setSignOpen] = useState(false)
  const closeSign = useCallback(() => setSignOpen(false), [])
  const signRef = useFocusTrap(signOpen, closeSign)          // 수어 모달 포커스 트랩·Esc
  const [saved, setSaved] = useState(false)        // 문항별 북마크(로컬 시각 토글 — 백엔드 API 없음)
  const [xpEarned, setXpEarned] = useState(0)      // 세션에 서버가 준 XP 합(응답 xp_gained) → 완료 뷰
  const startRef = useRef(Date.now())              // 마운트 시각 → 걸린 시간
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
    setSaved(false)
    setQ({ target, choices: shuffle([target, ...distractors]) })
    setFrames([])
    try { setFrames(await learningAPI.getVisemes(target)) } catch { /* ignore */ }
  }, [data, words, bankSet])

  useEffect(() => { newQ() }, [newQ])

  // 숙달 도달 시점의 경과 시간을 고정 캡처(완료 뷰가 다시 렌더돼도 시간이 흐르지 않게).
  useEffect(() => {
    if (stat.mastered) setElapsedSec(Math.floor((Date.now() - startRef.current) / 1000))
  }, [stat.mastered])

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
  }
  const next = () => { setQNum((n) => (n >= QUIZ_LEN ? 1 : n + 1)); newQ() }

  if (!q) return null

  // 세션 숙달 → 전용 완료 뷰(93:12)로 교체. XP는 서버가 실제로 준 값(정답 15·오답 3 × 스트릭 배수)의 합.
  if (stat.mastered) {
    return (
      // 다음 레슨 = 3단계 문장. 시나리오 선택(ScenarioHub)을 거쳐야 /practice가 뜬다 — 바로 /practice로 가면
      // currentScenario가 없어 되돌려 보내진다(CurriculumPath READ_ROUTE·Placement STAGE_ROUTE와 같은 진입점).
      <LessonComplete mastery={stat.mastery} xp={xpEarned} elapsedSec={elapsedSec}
        onNext={() => navigate('/learn/scenario')} onHome={() => navigate('/learn/path')} />
    )
  }

  const pct = Math.round((Math.min(qNum, QUIZ_LEN) / QUIZ_LEN) * 100)

  return (
    <>
      <div className="mx-auto flex max-w-[640px] flex-col px-4 pb-[160px] pt-6 sm:px-6">
        {/* 진행 헤더 — Figma Progress header (나가기 X + track 14px #e4e4ec + count 15px) */}
        <div className="flex items-center gap-[18px]">
          <button type="button" onClick={() => navigate('/learn/path')} aria-label="나가기" className="shrink-0">
            <img src="/ui/speak-close.svg" alt="나가기" className="size-9" />
          </button>
          <div className="h-[14px] flex-1 overflow-hidden rounded-full bg-[#e4e4ec]">
            <div className="h-full rounded-full bg-primary-500 transition-all duration-500" style={{ width: `${pct}%` }} />
          </div>
          <span className="shrink-0 text-[15px] font-bold text-ink-muted">{Math.min(qNum, QUIZ_LEN)} / {QUIZ_LEN}</span>
        </div>

        {/* 질문 + 북마크 — Figma Question (라벨 13px primary / 제목 30px, tracking -0.75 / Bookmark 42px) */}
        <div className="mt-7 flex items-start gap-3">
          <div className="flex-1">
            <p className="text-[13px] font-bold text-primary-500">단어 독화 · 숙달도 {stat.mastery}%</p>
            <p className="mt-2 text-[26px] font-bold tracking-[-0.75px] text-ink sm:text-[30px]">이 입모양은 어떤 단어일까요?</p>
          </div>
          <button type="button" onClick={() => setSaved((s) => !s)} aria-label="북마크" aria-pressed={saved}
            className={`flex size-[42px] shrink-0 items-center justify-center rounded-full border-2 transition-colors ${saved ? 'border-primary-500 bg-primary-100' : 'border-line bg-white'}`}>
            <img src={saved ? '/ui/lp-328-8-bookmark-active.svg' : '/ui/lp-328-8-bookmark-default.svg'} alt="" className="h-[18px] w-[18px]" />
          </button>
        </div>

        {/* 입모양 카드 — Figma Mouth card (아바타만, 다시보기 버튼 제거 · 자동재생 유지) */}
        <div className="relative mt-6 overflow-hidden rounded-[22px] border-2 border-line bg-white p-4">
          <MouthAvatar key={q.target} frames={frames} />
        </div>

        {/* 4지선다 (선택 → 확인) */}
        <div className="mt-6 flex flex-col gap-3">
          {q.choices.map((w, i) => {
            const isTarget = w === q.target
            const isChosen = (result ? result.chosen : selected) === w
            let cls = 'flex items-center gap-4 rounded-2xl px-5 py-4 text-left font-bold text-[20px] transition-all '
            if (!result) {
              if (isChosen) cls += 'border-2 border-b-[5px] border-primary-500 bg-primary-50 text-ink'
              else cls += 'border-2 border-b-[5px] border-line bg-white text-ink hover:border-primary-300 active:scale-[0.99]'
            }
            else if (isTarget) cls += 'border-[2.5px] border-[#16a34a] bg-[#e7f8ef] text-[#15803d]'
            else if (isChosen) cls += 'border-[2.5px] border-[#dc2626] bg-[#feecec] text-[#b91c1c]'
            else cls += 'border-2 border-b-[5px] border-line bg-white text-ink'
            return (
              <button key={w} type="button" disabled={!!result || submitting} onClick={() => setSelected(w)} className={cls}>
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-[#ededf3] text-[13px] text-ink-muted">{i + 1}</span>
                <span className="flex-1">{w}</span>
              </button>
            )
          })}
        </div>

        {/* 결과 피드백(혼동 진단·큐·수어·립리딩) — 핵심 교육 패널이라 유지, 고정 바 위 스크롤 영역 */}
        <AnimatePresence>
          {result && (
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mt-5 space-y-3">
              {!result.correct && result.confusions?.length > 0 && (
                <div className="space-y-1.5 rounded-2xl border-2 border-amber-200 bg-amber-50 p-4">
                  <p className="text-xs font-bold text-amber-800">어디서 헷갈렸나요?</p>
                  {result.confusions.map((cf, i) => (
                    <p key={i} className="text-[13px] leading-snug text-amber-900">
                      {cf.position} <b>‘{cf.target}’</b>을(를) <b>‘{cf.read}’</b>로 읽으셨어요 —{' '}
                      {cf.same_viseme
                        ? <>둘 다 <b>{cf.viseme_name_ko}</b>이라 입모양만으론 똑같이 보여요. 문맥·자막으로 구분하는 연습이 필요합니다.</>
                        : <>정답은 <b>{cf.viseme_name_ko}</b> 입모양입니다. 그 차이를 눈에 익혀보세요.</>}
                    </p>
                  ))}
                </div>
              )}
              <div className="rounded-2xl border-2 border-line bg-white p-3">
                <div className="flex items-center gap-2">
                  <CueBadges text={q.target} />
                  <span className="text-[11px] text-gray-400">난이도 {tierOf[q.target] || 1}</span>
                </div>
                <div className="mt-1.5"><CueLegend /></div>
              </div>
              <button type="button" onClick={() => setSignOpen(true)}
                className="w-full rounded-2xl border-2 border-primary-200 py-2.5 text-sm font-bold text-primary-600 hover:bg-primary-50">
                🤟 "{q.target}" 수어로 뜻 보기
              </button>
              <Suspense fallback={null}>
                <LipReadCheck target={q.target} candidates={q.choices} />
              </Suspense>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* 하단 고정 액션/피드백 바 — Figma Action bar(130:17) + Feedback(94:133/175) */}
      <div className={`fixed inset-x-0 bottom-0 z-40 border-t-2 ${result ? (result.correct ? 'border-[rgba(22,163,74,0.35)] bg-[#e7f8ef]' : 'border-[rgba(220,38,38,0.35)] bg-[#feecec]') : 'border-[#e2e2e8] bg-white'}`}>
        <div className="mx-auto flex max-w-[640px] items-center justify-between gap-4 px-4 py-6 sm:px-6">
          {result ? (
            // 정오 피드백은 스크린리더에 알린다(role=status·aria-live) — 잔존청력·저시력 사용자 대상(c92fdc3, 병합 복원)
            <div role="status" aria-live="polite" className="flex min-w-0 flex-col gap-1">
              <p className={`text-[22px] font-bold tracking-[-0.44px] ${result.correct ? 'text-[#15803d]' : 'text-[#b91c1c]'}`}>{result.correct ? '정답이에요!' : '아쉬워요'}</p>
              <p className={`truncate text-[14px] font-bold opacity-80 ${result.correct ? 'text-[#15803d]' : 'text-[#b91c1c]'}`}>정답은 「{q.target}」예요</p>
            </div>
          ) : (
            <span className="text-[15px] text-[#8a8a9b]">{selected == null ? '보기를 선택해주세요' : '정답을 확인해보세요'}</span>
          )}
          {result ? (
            <button type="button" onClick={next} className={`shrink-0 rounded-[14px] border-2 border-b-[5px] px-10 py-[15px] text-[17px] font-bold text-white transition-all active:translate-y-[2px] active:border-b-2 ${result.correct ? 'border-[#0f7a36] bg-[#16a34a] hover:bg-[#15903a]' : 'border-[#991b1b] bg-[#dc2626] hover:bg-[#c81f1f]'}`}>계속하기</button>
          ) : selected == null ? (
            <button type="button" disabled className="shrink-0 rounded-[14px] border-2 border-b-[5px] border-[#d2d2de] bg-[#e4e4ec] px-10 py-[15px] text-[17px] font-bold text-[#a0a0b0]">확인</button>
          ) : (
            <button type="button" onClick={confirm} disabled={submitting} className="shrink-0 rounded-[14px] border-2 border-b-[5px] border-primary-700 bg-primary-500 px-10 py-[15px] text-[17px] font-bold text-white transition-all hover:bg-primary-600 active:translate-y-[2px] active:border-b-2 disabled:opacity-50 disabled:cursor-not-allowed">확인</button>
          )}
        </div>
      </div>

      <AnimatePresence>
        {signOpen && (
          <motion.div className="fixed inset-0 z-50 flex justify-end bg-black/40"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            onClick={() => setSignOpen(false)}>
            <motion.div ref={signRef} role="dialog" aria-modal="true"
              aria-label={`${q?.target || ''} 수어 번역`} tabIndex={-1}
              className="h-full w-full max-w-2xl overflow-y-auto bg-white shadow-2xl outline-none"
              initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }}
              transition={{ type: 'tween', duration: 0.25 }}
              onClick={(e) => e.stopPropagation()}>
              <div className="sticky top-0 flex items-center justify-between border-b border-gray-200 bg-white px-5 py-3">
                <p className="font-bold text-gray-900">"{q.target}" 수어</p>
                <button onClick={() => setSignOpen(false)} className="rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-500 hover:text-gray-900">닫기 ✕</button>
              </div>
              <div className="p-5">
                <Suspense fallback={<div className="py-10 text-center text-sm text-gray-400">불러오는 중…</div>}>
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
