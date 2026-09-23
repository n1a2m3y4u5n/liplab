import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { curriculumAPI, learningAPI } from '../api'
import MouthAvatar from '../components/MouthAvatar'
import LearnHeader from '../components/LearnHeader'
import LoadingScreen from '../components/LoadingScreen'

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

  // 데이터 로딩 = 기본 로딩(§4-10 256:34)
  if (loading) return <LoadingScreen />
  if (!items || !items.length) return <div className="flex min-h-[100dvh] items-center justify-center bg-page text-ink-muted">불러오지 못했어요.</div>

  // 레슨 공통 템플릿(§4-03) 적용 여부는 사용자 확인 대기 — 지금은 예전 헤더를 두고 색·문구만 디자인 시스템에 맞춘다.
  return (
    <div className="min-h-[100dvh] bg-page">
      <LearnHeader
        accent="reading"
        title="문맥 추론"
        description="입모양만으론 헷갈리는 단어, 문맥으로 골라보세요"
        onExit={() => navigate('/learn/path')}
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

  const choose = async (opt) => {
    if (result) return
    const correct = opt === item.answer
    let confusions = []
    try { const r = await curriculumAPI.submitClosure(item.id, opt); confusions = r.confusions || [] }
    catch { /* 기록 실패해도 진행 */ }
    setResult({ correct, chosen: opt, confusions })
    setStat((s) => ({ n: s.n + 1, correct: s.correct + (correct ? 1 : 0) }))
  }

  return (
    <div className="space-y-5">
      <div className="card flex items-center justify-between text-sm">
        <span className="text-ink-muted">이번 세션 정확도</span>
        <span className="font-bold text-primary-600">{stat.n ? Math.round((stat.correct / stat.n) * 100) : 0}% · {stat.n}문제</span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <p className="mb-3 text-sm text-ink-muted">이 입모양은 무슨 말일까요? <span className="text-ink-faint">(같아 보이는 단어라 문맥이 열쇠!)</span></p>
          <MouthAvatar frames={frames} />
        </div>

        <div className="card flex flex-col">
          <div className="mb-4 rounded-14 bg-surface-muted p-4 text-center">
            <p className="text-2xl font-bold tracking-wide text-ink">
              {result ? full : item.display.replace('___', '◯◯')}
            </p>
          </div>

          {!result && (
            <button type="button" onClick={() => setHint(true)} className="mb-2 self-start rounded-full bg-warn-tint px-3 py-1 text-xs font-bold text-warn-text hover:brightness-95">
              힌트{hint ? '' : ' 보기'}
            </button>
          )}
          {hint && !result && <p className="mb-3 text-sm text-warn-text">{item.hint}</p>}

          <div className="grid grid-cols-3 gap-3">
            {choices.map((opt) => {
              const isT = opt === item.answer
              const isC = result?.chosen === opt
              let cls = 'py-3 rounded-14 border-2 font-bold text-lg transition-all '
              if (!result) cls += 'border-b-5 border-line bg-white text-ink hover:border-primary-300 hover:bg-primary-50'
              else if (isT) cls += 'border-good bg-good-tint text-good-text'
              else if (isC) cls += 'border-bad bg-bad-tint text-bad-text'
              else cls += 'border-line bg-surface-muted text-ink-faint'
              return <button key={opt} disabled={!!result} onClick={() => choose(opt)} className={cls}>{opt}</button>
            })}
          </div>

          <AnimatePresence>
            {result && (
              <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mt-4 space-y-2">
                <div role="status" aria-live="polite"
                  className={`rounded-14 p-3 text-sm font-bold ${result.correct ? 'bg-good-tint text-good-text' : 'bg-bad-tint text-bad-text'}`}>
                  {result.correct
                    ? '정답! 문맥으로 잘 골랐어요.'
                    : `아쉬워요 — 정답은 "${item.answer}". 보기들은 입모양이 거의 같아서 문맥이 열쇠예요.`}
                </div>
                {!result.correct && result.confusions?.length > 0 && (
                  <div className="space-y-1.5 rounded-14 border border-warn/40 bg-warn-tint p-3">
                    <p className="text-xs font-bold text-warn-text">왜 헷갈렸나요?</p>
                    {result.confusions.map((cf, k) => (
                      <p key={k} className="text-[13px] leading-snug text-warn-text">
                        {cf.position} <b>‘{cf.target}’</b>↔<b>‘{cf.read}’</b> —{' '}
                        {cf.same_viseme
                          ? <>둘 다 <b>{cf.viseme_name_ko}</b>이라 입모양만으론 구별 불가. 그래서 <b>문맥</b>이 열쇠예요.</>
                          : <>정답은 <b>{cf.viseme_name_ko}</b> 입모양입니다.</>}
                      </p>
                    ))}
                  </div>
                )}
                <button type="button" onClick={() => setI(i + 1)} className="btn-primary w-full py-2 text-sm">다음 문제 →</button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  )
}
