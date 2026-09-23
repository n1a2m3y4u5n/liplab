import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { curriculumAPI, reviewAPI, learningAPI } from '../api'
import MouthAvatar from '../components/MouthAvatar'
import AppShell from '../components/AppShell'
import LoadingScreen from '../components/LoadingScreen'

/**
 * 오늘의 복습 (간격 반복 SRS)
 * 틀렸던 항목(입모양/단어)이 due_date에 다시 등장한다. 각 항목을 퀴즈로 풀고,
 * 정답이면 다음 등장을 더 멀리 미루고(간격 2배), 오답이면 내일 다시 만난다.
 */

const shuffle = (a) => [...a].sort(() => Math.random() - 0.5)


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

  // 데이터 로딩 = 기본 로딩(§4-10 256:34)
  if (state === 'loading') return <LoadingScreen />
  if (state === 'error') return <div className="flex min-h-[100dvh] items-center justify-center bg-page text-ink-muted">불러오지 못했어요.</div>

  return (
    <AppShell active="review" title="입모양·단어 복습" description={state === 'active' ? `${idx + 1} / ${items.length}` : '복습 일정이 된 항목을 다시 만나요'}>
      <div className="w-full">
        {state === 'empty' && (
          <div className="card py-14 text-center">
            <h2 className="mb-1 text-xl font-bold text-ink">복습할 항목이 없어요</h2>
            <p className="mb-5 text-ink-muted">틀린 항목은 다음날부터 여기서 다시 만나요.</p>
            <button onClick={() => navigate('/dashboard')} className="btn-primary">나가기</button>
          </div>
        )}
        {state === 'done' && (
          <div className="card py-14 text-center">
            <h2 className="mb-1 text-xl font-bold text-ink">복습 완료!</h2>
            <p className="mb-5 text-ink-muted">수고했어요. 맞힌 항목은 더 나중에 다시 나와요.</p>
            <button onClick={() => navigate('/dashboard')} className="btn-primary">나가기</button>
          </div>
        )}
        {state === 'active' && items[idx] && (
          <ReviewCard key={idx} item={items[idx]} lessons={lessons} words={words} onDone={advance} />
        )}
      </div>
    </AppShell>
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
        <p className="mb-3 text-sm text-ink-muted">
          {isViseme ? '이 입모양은 어느 그룹일까요?' : '이 입모양은 어떤 단어일까요?'}
          <span className="ml-2 rounded-full bg-warn-tint px-2 py-0.5 text-xs font-bold text-warn-text">복습</span>
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
            let cls = 'px-4 py-3 rounded-14 border-2 font-bold text-sm transition-all '
            if (!result) cls += 'border-b-5 border-line bg-white text-ink hover:border-primary-300 hover:bg-primary-50'
            else if (isT) cls += 'border-good bg-good-tint text-good-text'
            else if (isC) cls += 'border-bad bg-bad-tint text-bad-text'
            else cls += 'border-line bg-surface-muted text-ink-faint'
            return (
              <button key={c.key} disabled={!!result || submitting} onClick={() => choose(c.key)} className={cls}>{c.label}</button>
            )
          })}
        </div>
        <AnimatePresence>
          {result && (
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mt-4 space-y-2">
              <div role="status" aria-live="polite" className={`rounded-14 p-3 text-sm font-bold ${result.correct ? 'bg-good-tint text-good-text' : 'bg-bad-tint text-bad-text'}`}>
                {result.correct ? '정답! 다음 복습은 더 나중에 나와요.' : '오답 — 내일 다시 만나요.'}
              </div>
              <button type="button" onClick={onDone} className="btn-primary w-full py-2 text-sm">다음 →</button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}
