import { useState, useEffect, useCallback } from 'react'
import { curriculumAPI, learningAPI } from '../api'
import MouthAvatar from '../components/MouthAvatar'
import LearnHeader from '../components/LearnHeader'
import CueBadges, { CueLegend } from '../components/CueBadges'

/**
 * 다자 대화 독화(축 H) — 여러 화자가 번갈아 말하는 대화에서 '지금 누가 말하는지' + 그 사람
 * 입모양을 함께 읽는 실전 훈련. 화자마다 색·이름을 배정하고 발화 순서대로 입모양을 재생한다.
 */
const SPK_COLOR = ['bg-sky-500', 'bg-rose-500', 'bg-amber-500']
const SPK_SOFT = ['bg-sky-50 text-sky-700 border-sky-200', 'bg-rose-50 text-rose-700 border-rose-200', 'bg-amber-50 text-amber-700 border-amber-200']
const SPK_NAME = ['A', 'B', 'C']

export default function MultiConversation() {
  const [conv, setConv] = useState(null)
  const [idx, setIdx] = useState(0)
  const [frames, setFrames] = useState([])
  const [reveal, setReveal] = useState(false)
  const [loading, setLoading] = useState(true)
  const [guess, setGuess] = useState(null)   // 사용자가 고른 화자(누가 말했나 과제)
  const [seen, setSeen] = useState({})        // idx→화자(지나간 발화만 타임라인에 색 표시)
  const [spkScore, setSpkScore] = useState({ correct: 0, total: 0 })

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const c = await curriculumAPI.getMultiConversation(2, 6)
      setConv(c); setIdx(0); setReveal(false); setGuess(null); setSeen({}); setSpkScore({ correct: 0, total: 0 })
    } catch { /* ignore */ } finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (!conv) return
    const t = conv.turns[idx]
    setReveal(false); setGuess(null)
    setFrames([])
    if (t) learningAPI.getVisemes(t.text).then(setFrames).catch(() => {})
  }, [conv, idx])

  // 화자 식별 과제 — 입모양만 보고 누가 말했는지 고른다(정답은 고른 뒤 공개)
  const chooseSpeaker = (i) => {
    if (guess != null) return
    setGuess(i)
    const ok = i === conv.turns[idx].speaker
    setSpkScore((s) => ({ correct: s.correct + (ok ? 1 : 0), total: s.total + 1 }))
    setSeen((m) => ({ ...m, [idx]: conv.turns[idx].speaker }))
  }

  if (loading || !conv) {
    return <div className="p-8 text-center text-gray-400">대화를 불러오는 중…</div>
  }
  const turn = conv.turns[idx]
  const last = idx >= conv.turns.length - 1

  const answered = guess != null
  return (
    <div className="mx-auto max-w-3xl px-4 py-4">
      <LearnHeader title="다자 대화 독화" />
      <p className="mb-3 text-sm text-gray-500">장면: <b className="text-gray-700">{conv.scene}</b> · 화자 {conv.speakers}명 — 입모양만 보고 <b>누가 말했는지</b> 맞힌 뒤, 무슨 말인지 읽어보세요.</p>

      {/* 발화 순서 타임라인 — 지나간 발화는 화자색, 현재는 링, 이후는 회색(정답 미리보기 방지) */}
      <div className="mb-3 flex items-center gap-1.5 overflow-x-auto pb-1">
        {conv.turns.map((_, i) => {
          const spk = seen[i]
          const cls = i === idx ? 'ring-2 ring-slate-900' : ''
          const color = spk != null ? SPK_COLOR[spk] : (i < idx ? 'bg-gray-300' : 'bg-gray-200')
          return <span key={i} className={`h-3 w-6 shrink-0 rounded-full ${color} ${cls}`} title={`${i + 1}번째 발화`} />
        })}
        <span className="ml-2 shrink-0 text-xs text-gray-400">화자 맞힘 {spkScore.correct}/{spkScore.total}</span>
      </div>

      {/* 화자 식별 과제 — 답하기 전엔 현재 발화자를 숨긴다 */}
      <div className="mb-3">
        <p className="mb-1.5 text-xs font-semibold text-gray-500">누가 말했을까요? (입모양을 보고 고르세요)</p>
        <div className="flex gap-2">
          {Array.from({ length: conv.speakers }).map((_, i) => {
            const isAns = answered && i === turn.speaker
            const isWrongPick = answered && i === guess && guess !== turn.speaker
            const base = 'inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm font-bold transition'
            const cls = isAns ? SPK_COLOR[i] + ' border-transparent text-white'
              : isWrongPick ? 'border-rose-300 bg-rose-50 text-rose-600 line-through'
              : answered ? 'border-gray-200 bg-white text-gray-400'
              : 'border-gray-300 bg-white text-gray-700 hover:border-slate-400'
            return (
              <button key={i} disabled={answered} onClick={() => chooseSpeaker(i)} className={`${base} ${cls}`}>
                <span className="grid h-5 w-5 place-items-center rounded-full bg-black/10 text-xs">{SPK_NAME[i]}</span>
                화자 {SPK_NAME[i]}
              </button>
            )
          })}
          {answered && (
            <span className={`self-center text-sm font-bold ${guess === turn.speaker ? 'text-emerald-600' : 'text-rose-600'}`}>
              {guess === turn.speaker ? '정답!' : `아니에요 — 화자 ${SPK_NAME[turn.speaker]}`}
            </span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="card">
          <p className="mb-2 text-sm text-gray-500">{answered ? <>지금 <b className={`rounded px-1.5 py-0.5 text-white ${SPK_COLOR[turn.speaker]}`}>화자 {SPK_NAME[turn.speaker]}</b>가 말합니다</> : '입모양을 보고 화자를 먼저 맞혀보세요'}</p>
          <MouthAvatar frames={frames} />
        </div>
        <div className="card flex flex-col justify-between">
          <div>
            <p className="text-xs text-gray-400">입모양을 먼저 읽어본 뒤 확인하세요</p>
            {reveal ? (
              <div className="mt-2 space-y-2">
                <p className="text-lg font-bold text-gray-900">“{turn.text}”</p>
                <div className="rounded-lg border border-gray-100 bg-gray-50 p-2.5 overflow-x-auto">
                  <CueBadges text={turn.text} />
                  <div className="mt-1.5"><CueLegend /></div>
                </div>
              </div>
            ) : (
              <button onClick={() => setReveal(true)} disabled={!answered}
                className="mt-3 w-full rounded-lg border-2 border-dashed border-gray-300 py-3 text-sm font-bold text-gray-600 hover:border-gray-400 disabled:opacity-40 disabled:cursor-not-allowed">
                {answered ? '무슨 말인지 확인하기' : '먼저 화자를 맞혀 주세요'}
              </button>
            )}
          </div>
          <div className="mt-4 flex items-center justify-between">
            <span className="text-xs text-gray-400">{idx + 1} / {conv.turns.length}</span>
            <div className="flex gap-2">
              {idx > 0 && <button onClick={() => setIdx(idx - 1)} className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-bold text-gray-700 hover:bg-gray-50">이전</button>}
              {!last ? (
                <button onClick={() => setIdx(idx + 1)} className="rounded-lg bg-slate-900 px-3 py-1.5 text-sm font-bold text-white hover:bg-slate-700">다음 발화 →</button>
              ) : (
                <button onClick={load} className="rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-bold text-white hover:bg-emerald-700">새 대화 ↻</button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
