import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { curriculumAPI, reviewAPI, learningAPI } from '../api'
import MouthAvatar from '../components/MouthAvatar'

/**
 * 오늘의 복습 (간격 반복 SRS)
 * 틀렸던 항목(입모양/단어)이 due_date에 다시 등장한다. 각 항목을 퀴즈로 풀고,
 * 정답이면 다음 등장을 더 멀리 미루고(간격 2배), 오답이면 내일 다시 만난다.
 */

const shuffle = (a) => [...a].sort(() => Math.random() - 0.5)

function Splash({ text }) {
  return <div className="min-h-screen flex items-center justify-center text-gray-500">{text}</div>
}

export default function Review() {
  const navigate = useNavigate()
  const [state, setState] = useState('loading') // loading | empty | active | done | error
  const [items, setItems] = useState([])
  const [lessons, setLessons] = useState([])
  const [words, setWords] = useState([])
  const [idx, setIdx] = useState(0)

  useEffect(() => {
    Promise.all([reviewAPI.getDue(), curriculumAPI.getVisemeLessons(), curriculumAPI.getWords()])
      .then(([due, vl, wd]) => {
        setLessons(vl.lessons)
        setWords(wd.words.map((w) => w.word))
        if (!due.items.length) { setState('empty'); return }
        setItems(due.items)
        setState('active')
      })
      .catch(() => setState('error'))
  }, [])

  const advance = () => {
    if (idx + 1 >= items.length) setState('done')
    else setIdx(idx + 1)
  }

  if (state === 'loading') return <Splash text="불러오는 중…" />
  if (state === 'error') return <Splash text="불러오지 못했어요." />

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-primary-50">
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">오늘의 복습</h1>
            <p className="text-sm text-gray-500">{state === 'active' ? `${idx + 1} / ${items.length}` : '틀렸던 항목을 다시 만나요'}</p>
          </div>
          <button onClick={() => navigate('/dashboard')} className="text-gray-500 hover:text-gray-800 text-sm">✕ 나가기</button>
        </div>
      </header>
      <main className="max-w-3xl mx-auto px-4 sm:px-6 py-8">
        {state === 'empty' && (
          <div className="card text-center py-14">
            <p className="text-5xl mb-3">🎉</p>
            <h2 className="text-xl font-bold text-gray-900 mb-1">복습할 항목이 없어요</h2>
            <p className="text-gray-500 mb-5">틀린 항목은 다음날부터 여기서 다시 만나요.</p>
            <button onClick={() => navigate('/dashboard')} className="btn-primary">대시보드로</button>
          </div>
        )}
        {state === 'done' && (
          <div className="card text-center py-14">
            <p className="text-5xl mb-3">✅</p>
            <h2 className="text-xl font-bold text-gray-900 mb-1">복습 완료!</h2>
            <p className="text-gray-500 mb-5">수고했어요. 맞힌 항목은 더 나중에 다시 나와요.</p>
            <button onClick={() => navigate('/dashboard')} className="btn-primary">대시보드로</button>
          </div>
        )}
        {state === 'active' && items[idx] && (
          <ReviewCard key={idx} item={items[idx]} lessons={lessons} words={words} onDone={advance} />
        )}
      </main>
    </div>
  )
}

function ReviewCard({ item, lessons, words, onDone }) {
  const isViseme = item.kind === 'viseme'
  const [frames, setFrames] = useState([])
  const [result, setResult] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  const { targetKey, choices } = useMemo(() => {
    if (isViseme) {
      const vid = parseInt(item.ref, 10)
      const t = lessons.find((l) => l.viseme_id === vid)
      const others = shuffle(lessons.filter((l) => l.viseme_id !== vid)).slice(0, 3)
      const opts = shuffle([t, ...others].filter(Boolean)).map((l) => ({ key: String(l.viseme_id), label: l.name }))
      return { targetKey: String(vid), choices: opts }
    }
    const others = shuffle(words.filter((w) => w !== item.ref)).slice(0, 3)
    const opts = shuffle([item.ref, ...others]).map((w) => ({ key: w, label: w }))
    return { targetKey: item.ref, choices: opts }
  }, [item, lessons, words, isViseme])

  useEffect(() => {
    if (!isViseme) learningAPI.getVisemes(item.ref).then(setFrames).catch(() => {})
  }, [item, isViseme])

  const choose = async (key) => {
    if (result || submitting) return
    setSubmitting(true)
    const correct = key === targetKey
    try { await reviewAPI.answer(item.kind, item.ref, correct) } catch { /* ignore */ } finally { setSubmitting(false) }
    setResult({ correct, chosen: key })
  }

  return (
    <div className="space-y-4">
      <div className="card">
        <p className="text-sm text-gray-500 mb-3">
          {isViseme ? '이 입모양은 어느 그룹일까요?' : '이 입모양은 어떤 단어일까요?'}
          <span className="ml-2 text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-700">복습</span>
        </p>
        <MouthAvatar
          frames={isViseme ? undefined : frames}
          visemeId={isViseme ? parseInt(item.ref, 10) : undefined}
          height={260}
        />
      </div>
      <div className="card">
        <div className={`grid ${isViseme ? 'grid-cols-1' : 'grid-cols-2'} gap-3`}>
          {choices.map((c) => {
            const isT = c.key === targetKey
            const isC = result?.chosen === c.key
            let cls = 'px-4 py-3 rounded-xl border-2 font-medium text-sm transition-all '
            if (!result) cls += 'border-gray-200 bg-white hover:border-primary-400 hover:bg-primary-50 text-gray-800'
            else if (isT) cls += 'border-green-500 bg-green-50 text-green-800'
            else if (isC) cls += 'border-red-400 bg-red-50 text-red-700'
            else cls += 'border-gray-200 bg-gray-50 text-gray-400'
            return (
              <button key={c.key} disabled={!!result || submitting} onClick={() => choose(c.key)} className={cls}>{c.label}</button>
            )
          })}
        </div>
        <AnimatePresence>
          {result && (
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mt-4 space-y-2">
              <div className={`p-3 rounded-lg text-sm ${result.correct ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'}`}>
                {result.correct ? '정답! 🎉 다음 복습은 더 나중에 나와요.' : '오답 — 내일 다시 만나요.'}
              </div>
              <button onClick={onDone} className="btn-primary w-full py-2 text-sm">다음 →</button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}
