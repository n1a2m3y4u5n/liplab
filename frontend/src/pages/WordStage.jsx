import { useState, useEffect, useMemo, useCallback, lazy, Suspense } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { curriculumAPI, learningAPI } from '../api'
import MouthAvatar from '../components/MouthAvatar'
import LearnHeader from '../components/LearnHeader'
import useFocusTrap from '../hooks/useFocusTrap'
import CueBadges, { CueLegend } from '../components/CueBadges'

// 트랙B(언어+독화) 앵커링: 단어의 뜻을 수어로 확인. 무거우니 열 때만 로드.
const SignPanel = lazy(() => import('../components/SignPanel'))

/**
 * 2단계 · 음절·단어 (Word Stage)
 * 입모양만 보고 어떤 단어인지 4지선다로 맞힌다. 오답 보기는 '비슷하게 보이는'
 * 최소대립 단어를 우선 배치해 변별을 훈련한다. 오답은 SRS 복습 큐에 예약된다.
 */

const shuffle = (a) => [...a].sort(() => Math.random() - 0.5)

function partnersOf(word, pairs, bankSet) {
  const out = new Set()
  for (const m of pairs) {
    if (m.a === word && bankSet.has(m.b)) out.add(m.b)
    if (m.b === word && bankSet.has(m.a)) out.add(m.a)
  }
  return [...out]
}

export default function WordStage() {
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [targetPool, setTargetPool] = useState(null) // 지식추적 개인화 표적 단어(취약 입모양)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    curriculumAPI.getWords().then(setData).catch(() => setData(null)).finally(() => setLoading(false))
    // 개인화 추천 — 취약 입모양을 포함하고 난이도가 맞는 단어를 표적 풀로 (실패해도 전체 은행으로 폴백)
    curriculumAPI.getNext()
      .then((n) => setTargetPool((n?.words || []).map((w) => w.word)))
      .catch(() => {})
  }, [])

  if (loading) return <div className="min-h-screen flex items-center justify-center text-gray-500">불러오는 중…</div>
  if (!data) return <div className="min-h-screen flex items-center justify-center text-gray-500">불러오지 못했어요.</div>

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-primary-50">
      <LearnHeader
        accent="reading"
        title="단어 학습"
        description="입모양만 보고 어떤 단어인지 맞혀보세요"
        onExit={() => navigate('/dashboard')}
      />
      <main className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
        <WordQuiz data={data} targetPool={targetPool} />
      </main>
    </div>
  )
}

function WordQuiz({ data, targetPool }) {
  const words = useMemo(() => data.words.map((w) => w.word), [data])
  const tierOf = useMemo(() => Object.fromEntries(data.words.map((w) => [w.word, w.tier || 1])), [data])
  const bankSet = useMemo(() => new Set(words), [words])
  const [q, setQ] = useState(null)
  const [frames, setFrames] = useState([])
  const [result, setResult] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [stat, setStat] = useState({ attempts: 0, mastery: 0, mastered: false })
  const [signOpen, setSignOpen] = useState(false)
  const closeSign = useCallback(() => setSignOpen(false), [])
  const signRef = useFocusTrap(signOpen, closeSign)          // 수어 모달 포커스 트랩·Esc

  const newQ = useCallback(async () => {
    // 표적은 개인화 풀(취약 입모양·난이도 반영)에서, 오답 보기는 전체 은행에서(혼동쌍 우선).
    // 예전엔 195개에서 균등 랜덤이라 초급자가 희귀·고난도어를 동일 확률로 만났다.
    const pool = (targetPool && targetPool.length) ? targetPool : words
    const target = pool[Math.floor(Math.random() * pool.length)]
    const partners = partnersOf(target, data.minimal_pairs, bankSet)
    const rest = shuffle(words.filter((w) => w !== target && !partners.includes(w)))
    const distractors = shuffle([...partners, ...rest]).slice(0, 3)
    setResult(null)
    setQ({ target, choices: shuffle([target, ...distractors]) })
    setFrames([])
    try { setFrames(await learningAPI.getVisemes(target)) } catch { /* ignore */ }
  }, [data, words, bankSet, targetPool])

  useEffect(() => { newQ() }, [newQ])

  const choose = async (word) => {
    if (result || submitting) return
    setSubmitting(true)
    const correct = word === q.target
    try {
      const r = await curriculumAPI.submitWord(q.target, correct)
      setStat({ attempts: r.attempts, mastery: r.mastery_score, mastered: r.mastered })
    } catch { /* 기록 실패해도 진행 */ } finally { setSubmitting(false) }
    setResult({ correct, chosen: word })
  }

  if (!q) return null

  return (
    <div className="space-y-5">
      <div className="card">
        <div className="flex justify-between text-sm mb-1.5">
          <span className="text-gray-600">숙달도 (정확도)</span>
          <span className="font-semibold text-primary-600">{stat.mastery}% · {stat.attempts}회</span>
        </div>
        <div className="bg-gray-200 rounded-full h-2 overflow-hidden">
          <div className="bg-primary-500 h-full rounded-full transition-all duration-500" style={{ width: `${Math.min(stat.mastery, 100)}%` }} />
        </div>
        {stat.mastered && <p className="mt-2 text-sm font-semibold text-green-600">🎉 2단계 숙달! 단어 독화에 익숙해졌어요.</p>}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <p className="text-sm text-gray-500 mb-3">이 입모양은 어떤 단어일까요?</p>
          <MouthAvatar frames={frames} />
        </div>
        <div className="card">
          <div className="grid grid-cols-2 gap-3">
            {q.choices.map((w) => {
              const isTarget = w === q.target
              const isChosen = result?.chosen === w
              let cls = 'px-4 py-4 rounded-xl border-2 font-bold text-base transition-all '
              if (!result) cls += 'border-gray-200 bg-white hover:border-primary-400 hover:bg-primary-50 text-gray-800'
              else if (isTarget) cls += 'border-green-500 bg-green-50 text-green-800'
              else if (isChosen) cls += 'border-red-400 bg-red-50 text-red-700'
              else cls += 'border-gray-200 bg-gray-50 text-gray-400'
              return (
                <button key={w} disabled={!!result || submitting} onClick={() => choose(w)} className={cls}>{w}</button>
              )
            })}
          </div>
          <AnimatePresence>
            {result && (
              <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mt-4 space-y-2">
                <div role="status" aria-live="polite"
                  className={`p-3 rounded-lg text-sm ${result.correct ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'}`}>
                  {result.correct ? '정답! 🎉' : `오답 — 정답은 "${q.target}"`}
                </div>
                <div className="rounded-lg border border-gray-100 bg-gray-50 p-2.5">
                  <div className="flex items-center gap-2">
                    <CueBadges text={q.target} />
                    <span className="text-[11px] text-gray-400">난이도 {tierOf[q.target] || 1}</span>
                  </div>
                  <div className="mt-1.5"><CueLegend /></div>
                </div>
                <button onClick={() => setSignOpen(true)}
                  className="w-full py-2 rounded-lg border border-primary-300 text-primary-600 text-sm font-medium hover:bg-primary-50 transition-colors">
                  🤟 "{q.target}" 수어로 뜻 보기
                </button>
                <button onClick={newQ} className="btn-primary w-full py-2 text-sm">다음 문제 →</button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      <AnimatePresence>
        {signOpen && (
          <motion.div className="fixed inset-0 z-50 bg-black/40 flex justify-end"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            onClick={() => setSignOpen(false)}>
            <motion.div ref={signRef} role="dialog" aria-modal="true"
              aria-label={`${q?.target || ''} 수어 번역`} tabIndex={-1}
              className="w-full max-w-2xl h-full bg-white shadow-2xl overflow-y-auto outline-none"
              initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }}
              transition={{ type: 'tween', duration: 0.25 }}
              onClick={(e) => e.stopPropagation()}>
              <div className="sticky top-0 bg-white border-b border-gray-200 px-5 py-3 flex items-center justify-between">
                <p className="font-bold text-gray-900">"{q.target}" 수어</p>
                <button onClick={() => setSignOpen(false)} className="px-3 py-1.5 text-sm text-gray-500 hover:text-gray-900 border border-gray-200 rounded-lg">닫기 ✕</button>
              </div>
              <div className="p-5">
                <Suspense fallback={<div className="py-10 text-center text-gray-400 text-sm">불러오는 중…</div>}>
                  <SignPanel text={q.target} />
                </Suspense>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
