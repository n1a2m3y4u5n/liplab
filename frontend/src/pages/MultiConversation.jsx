import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { curriculumAPI, learningAPI } from '../api'
import MouthAvatar from '../components/MouthAvatar'
import LearnHeader from '../components/LearnHeader'
import CueBadges, { CueLegend } from '../components/CueBadges'

/**
 * 다자 대화 독화(축 H) — 여러 화자가 번갈아 말하는 대화에서 '지금 누가 말하는지' + 그 사람
 * 입모양을 함께 읽는 실전 훈련. 화자마다 색·이름을 배정하고 발화 순서대로 입모양을 재생한다.
 */
const SPK_COLOR = ['bg-sky-500', 'bg-rose-500', 'bg-amber-500']
const SPK_RING = ['ring-sky-400', 'ring-rose-400', 'ring-amber-400']  // 화자별 시각 구분(답 후)
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
  const [readGuess, setReadGuess] = useState(null)  // 사용자가 고른 발화 내용(립리딩 이해 과제)
  const [readScore, setReadScore] = useState({ correct: 0, total: 0 })
  const [readSeen, setReadSeen] = useState({})       // idx→채점됨(재방문 시 이중집계 방지)
  const [numSpeakers, setNumSpeakers] = useState(2)  // 화자 수(2~3) — 난이도 조절
  const [result, setResult] = useState(null)         // 서버 종합 채점(세션 종료 시)
  const readHitsRef = useRef([])                      // 립리딩 정답 발화(비심 지식추적용)
  const readMissesRef = useRef([])                    // 오독 발화
  const spkRef = useRef({ correct: 0, total: 0 })     // 화자식별 누적(제출용, 최신값 보장)
  const submittedRef = useRef(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const c = await curriculumAPI.getMultiConversation(numSpeakers, 6)
      setConv(c); setIdx(0); setReveal(false); setGuess(null); setSeen({}); setSpkScore({ correct: 0, total: 0 })
      setReadGuess(null); setReadScore({ correct: 0, total: 0 }); setReadSeen({})
      setResult(null); readHitsRef.current = []; readMissesRef.current = []
      spkRef.current = { correct: 0, total: 0 }; submittedRef.current = false
    } catch { /* ignore */ } finally { setLoading(false) }
  }, [numSpeakers])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (!conv) return
    const t = conv.turns[idx]
    setReveal(false); setGuess(null); setReadGuess(null)
    setFrames([])
    if (t) learningAPI.getVisemes(t.text).then(setFrames).catch(() => {})
  }, [conv, idx])

  // 립리딩 이해 과제 보기 — 정답(현재 발화) + 대화 내 다른 발화(오답보기), 발화마다 새로 섞음.
  const readOptions = useMemo(() => {
    if (!conv) return []
    const ans = conv.turns[idx]?.text
    if (!ans) return []
    const others = [...new Set(conv.turns.map((t) => t.text).filter((t) => t && t !== ans))]
    const picked = others.sort(() => Math.random() - 0.5).slice(0, 3)
    return [ans, ...picked].sort(() => Math.random() - 0.5)
  }, [conv, idx])

  // 화자 식별 과제 — 입모양만 보고 누가 말했는지 고른다(정답은 고른 뒤 공개)
  const chooseSpeaker = (i) => {
    if (guess != null) return
    setGuess(i)
    const firstTime = seen[idx] == null   // 재방문 재채점 방지: 이 발화를 처음 맞힐 때만 점수 누적
    setSeen((m) => ({ ...m, [idx]: conv.turns[idx].speaker }))
    if (firstTime) {
      const ok = i === conv.turns[idx].speaker
      setSpkScore((s) => ({ correct: s.correct + (ok ? 1 : 0), total: s.total + 1 }))
      spkRef.current = { correct: spkRef.current.correct + (ok ? 1 : 0), total: spkRef.current.total + 1 }
    }
  }

  // 세션 종료 시 서버에 결과를 기록·채점(화자식별+립리딩 결합, 오독 비심은 지식추적으로).
  const submitResult = useCallback(async () => {
    if (submittedRef.current) return
    submittedRef.current = true
    const hits = readHitsRef.current, misses = readMissesRef.current
    try {
      const r = await curriculumAPI.recordMultiConversation({
        speaker_correct: spkRef.current.correct, speaker_total: spkRef.current.total,
        read_correct: hits.length, read_total: hits.length + misses.length,
        read_hits: hits, read_misses: misses,
      })
      setResult(r)
    } catch { /* 기록 실패는 조용히 무시 */ }
  }, [])

  // 립리딩 이해 과제 — 입모양을 읽고 무슨 말이었는지 고른다(D 립리딩 + G 문맥추론 재조합).
  const chooseRead = (text) => {
    if (readGuess != null) return
    setReadGuess(text)
    setReveal(true)
    if (readSeen[idx] == null) {   // 재방문 재채점 방지: 처음 고를 때만 점수 누적
      setReadSeen((m) => ({ ...m, [idx]: 1 }))
      const ok = text === conv.turns[idx].text
      setReadScore((s) => ({ correct: s.correct + (ok ? 1 : 0), total: s.total + 1 }))
      if (ok) readHitsRef.current.push(conv.turns[idx].text)
      else readMissesRef.current.push(conv.turns[idx].text)
      // 모든 발화를 한 번씩 읽었으면 세션 종료 → 서버 기록·종합 채점(순서 무관)
      if (readHitsRef.current.length + readMissesRef.current.length >= conv.turns.length) {
        submitResult()
      }
    }
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
      <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <p className="text-sm text-gray-500">장면: <b className="text-gray-700">{conv.scene}</b> · 입모양만 보고 <b>누가 말했는지</b> 맞힌 뒤, 무슨 말인지 읽어보세요.</p>
        <div className="flex items-center gap-1 text-xs">
          <span className="text-gray-400">화자</span>
          {[2, 3].map((n) => (
            <button key={n} onClick={() => setNumSpeakers(n)}
              className={`rounded-full px-2.5 py-0.5 font-bold transition ${numSpeakers === n ? 'bg-slate-900 text-white' : 'border border-gray-300 text-gray-600 hover:bg-gray-50'}`}>
              {n}명
            </button>
          ))}
        </div>
      </div>

      {/* 발화 순서 타임라인 — 지나간 발화는 화자색, 현재는 링, 이후는 회색(정답 미리보기 방지) */}
      <div className="mb-3 flex items-center gap-1.5 overflow-x-auto pb-1">
        {conv.turns.map((_, i) => {
          const spk = seen[i]
          const cls = i === idx ? 'ring-2 ring-slate-900' : ''
          const color = spk != null ? SPK_COLOR[spk] : (i < idx ? 'bg-gray-300' : 'bg-gray-200')
          return <span key={i} className={`h-3 w-6 shrink-0 rounded-full ${color} ${cls}`} title={`${i + 1}번째 발화`} />
        })}
        <span className="ml-2 shrink-0 text-xs text-gray-400">화자 {spkScore.correct}/{spkScore.total} · 독해 {readScore.correct}/{readScore.total}</span>
      </div>

      {/* 세션 종합 채점(축 H) — 화자 식별 + 립리딩(문맥추론) 결합. 오독 비심은 지식추적에 반영됨. */}
      {result && (
        <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-xl border border-emerald-200 bg-emerald-50/70 px-4 py-2.5">
          <span className="text-sm font-bold text-emerald-800">이번 대화 종합 {result.combined}점</span>
          <span className="text-xs text-emerald-700">화자 식별 {Math.round(result.speaker_accuracy * 100)}% · 독해 {Math.round(result.read_accuracy * 100)}%</span>
          {result.recorded_visemes?.length > 0 && (
            <span className="text-[11px] text-emerald-600">약점 입모양 {result.recorded_visemes.length}개를 복습에 반영했어요</span>
          )}
        </div>
      )}

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
          {/* 답 후 현재 화자 색으로 아바타를 감싸 여러 화자 장면을 시각적으로 구분(축 H) */}
          <div className={answered ? `rounded-xl ring-2 ${SPK_RING[turn.speaker] || ''} transition` : ''}>
            <MouthAvatar frames={frames} />
          </div>
        </div>
        <div className="card flex flex-col justify-between">
          <div>
            {!answered ? (
              <p className="mt-2 rounded-lg border-2 border-dashed border-gray-200 py-6 text-center text-sm font-bold text-gray-400">
                먼저 화자를 맞혀 주세요
              </p>
            ) : readGuess == null ? (
              <div>
                <p className="mb-1.5 text-xs font-semibold text-gray-500">무슨 말이었나요? (입모양을 읽고 고르세요)</p>
                <div className="space-y-1.5">
                  {readOptions.map((opt) => (
                    <button key={opt} onClick={() => chooseRead(opt)}
                      className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-left text-sm font-medium text-gray-700 transition hover:border-slate-400 hover:bg-slate-50">
                      {opt}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="mt-1 space-y-2">
                <p className={`text-sm font-bold ${readGuess === turn.text ? 'text-emerald-600' : 'text-rose-600'}`}>
                  {readGuess === turn.text ? '정답! 잘 읽었어요' : '아쉬워요 — 실제로는'}
                </p>
                <p className="text-lg font-bold text-gray-900">“{turn.text}”</p>
                <div className="rounded-lg border border-gray-100 bg-gray-50 p-2.5 overflow-x-auto">
                  <CueBadges text={turn.text} />
                  <div className="mt-1.5"><CueLegend /></div>
                </div>
              </div>
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
