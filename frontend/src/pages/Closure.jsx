import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { curriculumAPI, learningAPI } from '../api'
import MouthAvatar from '../components/MouthAvatar'
import LearnHeader from '../components/LearnHeader'

/**
 * 3단계 · 문맥 추론 (Closure)
 * 입모양이 거의 똑같은 단어들(밥/맘/발) 중 정답을 '문맥'으로 고른다.
 * 독화의 핵심 기술 — 시각 정보만으론 애매하니 문장 의미로 메꾸는 훈련.
 */

const shuffle = (a) => [...a].sort(() => Math.random() - 0.5)

export default function Closure() {
  const navigate = useNavigate()
  const [items, setItems] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    curriculumAPI.getClosure().then((d) => setItems(d.items)).catch(() => setItems(null)).finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="min-h-screen flex items-center justify-center text-gray-500">불러오는 중…</div>
  if (!items || !items.length) return <div className="min-h-screen flex items-center justify-center text-gray-500">불러오지 못했어요.</div>

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-primary-50">
      <LearnHeader
        accent="reading"
        title="문맥 추론"
        description="입모양만으론 헷갈리는 단어, 문맥으로 골라보세요"
        onExit={() => navigate('/dashboard')}
      />
      <main className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
        <ClosureQuiz items={items} />
      </main>
    </div>
  )
}

function ClosureQuiz({ items }) {
  const [i, setI] = useState(0)
  const [frames, setFrames] = useState([])
  const [result, setResult] = useState(null)
  const [hint, setHint] = useState(false)
  const [stat, setStat] = useState({ n: 0, correct: 0 })

  const item = items[i % items.length]
  const choices = useMemo(() => shuffle(item.options), [item])
  const full = item.display.replace('___', item.answer)

  useEffect(() => {
    setResult(null)
    setHint(false)
    setFrames([])
    learningAPI.getVisemes(full).then(setFrames).catch(() => {})
  }, [i])

  const choose = (opt) => {
    if (result) return
    const correct = opt === item.answer
    setResult({ correct, chosen: opt })
    setStat((s) => ({ n: s.n + 1, correct: s.correct + (correct ? 1 : 0) }))
    // 결과를 서버에 기록 — 3단계 숙달·SRS·취약 입모양·XP에 반영(예전엔 저장 안 됨)
    curriculumAPI.submitClosure(item.answer, correct).catch(() => {})
  }

  return (
    <div className="space-y-5">
      <div className="card flex items-center justify-between text-sm">
        <span className="text-gray-600">이번 세션 정확도</span>
        <span className="font-semibold text-primary-600">{stat.n ? Math.round((stat.correct / stat.n) * 100) : 0}% · {stat.n}문제</span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <p className="text-sm text-gray-500 mb-3">이 입모양은 무슨 말일까요? <span className="text-gray-400">(같아 보이는 단어라 문맥이 열쇠!)</span></p>
          <MouthAvatar frames={frames} />
        </div>

        <div className="card flex flex-col">
          <div className="p-4 bg-gray-50 rounded-xl text-center mb-4">
            <p className="text-2xl font-bold text-gray-900 tracking-wide">
              {result ? full : item.display.replace('___', '◯◯')}
            </p>
          </div>

          {!result && (
            <button onClick={() => setHint(true)} className="text-xs self-start mb-2 px-3 py-1 rounded-full bg-amber-100 text-amber-700 hover:bg-amber-200">
              힌트{hint ? '' : ' 보기'}
            </button>
          )}
          {hint && !result && <p className="text-sm text-amber-700 mb-3">💡 {item.hint}</p>}

          <div className="grid grid-cols-3 gap-3">
            {choices.map((opt) => {
              const isT = opt === item.answer
              const isC = result?.chosen === opt
              let cls = 'py-3 rounded-xl border-2 font-bold text-lg transition-all '
              if (!result) cls += 'border-gray-200 bg-white hover:border-primary-400 hover:bg-primary-50 text-gray-800'
              else if (isT) cls += 'border-green-500 bg-green-50 text-green-800'
              else if (isC) cls += 'border-red-400 bg-red-50 text-red-700'
              else cls += 'border-gray-200 bg-gray-50 text-gray-400'
              return <button key={opt} disabled={!!result} onClick={() => choose(opt)} className={cls}>{opt}</button>
            })}
          </div>

          <AnimatePresence>
            {result && (
              <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mt-4 space-y-2">
                <div className={`p-3 rounded-lg text-sm ${result.correct ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'}`}>
                  {result.correct
                    ? '정답! 🎉 문맥으로 잘 골랐어요.'
                    : `아쉬워요 — 정답은 "${item.answer}". 보기들은 입모양이 거의 같아서 문맥이 열쇠예요.`}
                </div>
                <button onClick={() => setI(i + 1)} className="btn-primary w-full py-2 text-sm">다음 문제 →</button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  )
}
