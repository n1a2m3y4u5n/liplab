import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { curriculumAPI, learningAPI } from '../api'
import MouthAvatar from '../components/MouthAvatar'
import AppShell from '../components/AppShell'
import CueBadges, { CueLegend } from '../components/CueBadges'

/**
 * 다자 대화 독화(축 H) — 여러 화자가 번갈아 말하는 대화에서 '지금 누가 말하는지' + 그 사람
 * 입모양을 함께 읽는 실전 훈련. 화자마다 색·이름을 배정하고 발화 순서대로 입모양을 재생한다.
 */
const SPK_COLOR = ['bg-sky-500', 'bg-rose-500', 'bg-amber-500']
const SPK_RING = ['ring-sky-400', 'ring-rose-400', 'ring-amber-400']  // 화자별 시각 구분(답 후)
const SPK_SOFT = ['bg-sky-50 text-sky-700 border-sky-200', 'bg-rose-50 text-rose-700 border-rose-200', 'bg-amber-50 text-amber-700 border-amber-200']
const SPK_TEXT = ['text-sky-600', 'text-rose-600', 'text-amber-600']  // 선택 전 화자별 글자색(Figma: 화자마다 색)
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
    <AppShell active="practice" title="다자 대화" description="입모양만 보고 누가 말했는지 맞혀보세요">
      {/* 안내 + 화자 수 토글(난이도) */}
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
        <p className="text-[15px] text-ink-muted">장면 <b className="text-ink">{conv.scene}</b> · 입모양만 보고 <b className="text-ink">누가 말했는지</b> 맞힌 뒤, 무슨 말인지 읽어보세요.</p>
        <div className="flex items-center gap-1.5 text-[13px]">
          <span className="text-ink-muted">화자</span>
          {[2, 3].map((n) => (
            <button key={n} onClick={() => setNumSpeakers(n)}
              className={`rounded-full px-3.5 py-1 font-bold transition ${numSpeakers === n ? 'bg-primary-500 text-white' : 'bg-[#f3f3f7] text-ink-muted hover:bg-gray-200'}`}>
              {n}명
            </button>
          ))}
        </div>
      </div>

      {/* 발화 순서 타임라인 — 지나간 발화는 화자색, 현재는 링, 이후는 회색(정답 미리보기 방지) */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-1">
        {conv.turns.map((_, i) => {
          const spk = seen[i]
          const cls = i === idx ? 'ring-2 ring-primary-500' : ''
          const color = spk != null ? SPK_COLOR[spk] : (i < idx ? 'bg-gray-300' : 'bg-gray-200')
          return <span key={i} className={`h-3 w-6 shrink-0 rounded-full ${color} ${cls}`} title={`${i + 1}번째 발화`} />
        })}
        <span className="ml-2 shrink-0 text-xs text-gray-400">화자 {spkScore.correct}/{spkScore.total} · 독해 {readScore.correct}/{readScore.total}</span>
      </div>

      {/* 세션 종합 채점(축 H) — 화자 식별 + 립리딩(문맥추론) 결합. 오독 비심은 지식추적에 반영됨. */}
      {result && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-[14px] border-2 border-emerald-200 bg-emerald-50/70 px-4 py-2.5">
          <span className="text-sm font-bold text-emerald-800">이번 대화 종합 {result.combined}점</span>
          <span className="text-xs text-emerald-700">화자 식별 {Math.round(result.speaker_accuracy * 100)}% · 독해 {Math.round(result.read_accuracy * 100)}%</span>
          {result.recorded_visemes?.length > 0 && (
            <span className="text-[11px] text-emerald-600">약점 입모양 {result.recorded_visemes.length}개를 복습에 반영했어요</span>
          )}
        </div>
      )}

      {/* 카드 1: 장면 무대 + 화자 식별 과제 */}
      <div className="card">
        <div className="mb-4 flex items-center justify-between">
          <p className="text-[17px] font-bold text-ink">{conv.scene}</p>
          <p className="text-[13px] font-bold text-ink-muted">{idx + 1} / {conv.turns.length}턴</p>
        </div>

        {/* 입모양 무대 — 답 후 현재 화자 색으로 아바타를 감싸 여러 화자 장면을 시각적으로 구분(축 H) */}
        <div className="rounded-[16px] bg-[#fafafc] p-4">
          <div className={answered ? `rounded-xl ring-2 ${SPK_RING[turn.speaker] || ''} transition` : ''}>
            <MouthAvatar frames={frames} />
          </div>
          <p className="mt-3 text-center text-[15px] font-bold text-ink-muted">
            {answered
              ? <>지금 <span className={`rounded px-1.5 py-0.5 text-white ${SPK_COLOR[turn.speaker]}`}>화자 {SPK_NAME[turn.speaker]}</span>가 말합니다</>
              : '지금 말하는 사람은 누구일까요?'}
          </p>
        </div>

        {/* 화자 식별 선택 — Figma 3D 하단테두리 버튼 */}
        <div className="mt-4 flex gap-3">
          {Array.from({ length: conv.speakers }).map((_, i) => {
            const isAns = answered && i === turn.speaker
            const isWrongPick = answered && i === guess && guess !== turn.speaker
            const base = 'flex flex-1 items-center justify-center gap-1.5 rounded-[14px] py-4 text-[17px] font-bold transition-all'
            const cls = isAns ? `${SPK_COLOR[i]} border-2 border-b-2 border-transparent text-white`
              : isWrongPick ? 'border-2 border-b-2 border-rose-300 bg-rose-50 text-rose-500 line-through'
              : answered ? 'border-2 border-b-[5px] border-line bg-white text-gray-300'
              : `border-2 border-b-[5px] border-line bg-white ${SPK_TEXT[i]} hover:border-primary-300 active:translate-y-[1px] active:border-b-2`
            return (
              <button key={i} disabled={answered} onClick={() => chooseSpeaker(i)} className={`${base} ${cls}`}>
                <span className="grid h-5 w-5 place-items-center rounded-full bg-black/10 text-xs">{SPK_NAME[i]}</span>
                화자 {SPK_NAME[i]}
              </button>
            )
          })}
        </div>
        {answered && (
          <p className={`mt-2 text-center text-sm font-bold ${guess === turn.speaker ? 'text-emerald-600' : 'text-rose-600'}`}>
            {guess === turn.speaker ? '정답!' : `아니에요 — 화자 ${SPK_NAME[turn.speaker]}`}
          </p>
        )}
      </div>

      {/* 카드 2: 무슨 말이었나요(독해) + 네비게이션 */}
      <div className="card flex flex-col">
        <div className="min-h-[120px] flex-1">
          {!answered ? (
            <p className="mt-2 rounded-[14px] border-2 border-dashed border-line py-10 text-center text-sm font-bold text-gray-400">
              먼저 화자를 맞혀 주세요
            </p>
          ) : readGuess == null ? (
            <div>
              <p className="mb-2 text-[13px] font-bold text-ink-muted">무슨 말이었나요? (입모양을 읽고 고르세요)</p>
              <div className="space-y-2">
                {readOptions.map((opt) => (
                  <button key={opt} onClick={() => chooseRead(opt)}
                    className="block w-full rounded-[12px] border-2 border-line bg-white px-4 py-3 text-left text-[15px] font-medium text-ink transition hover:border-primary-300 hover:bg-primary-50">
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
              <p className="text-lg font-bold text-ink">“{turn.text}”</p>
              <div className="overflow-x-auto rounded-[12px] border border-gray-100 bg-gray-50 p-2.5">
                <CueBadges text={turn.text} />
                <div className="mt-1.5"><CueLegend /></div>
              </div>
            </div>
          )}
        </div>
        <div className="mt-4 flex items-center justify-between">
          <span className="text-xs text-gray-400">{idx + 1} / {conv.turns.length}</span>
          <div className="flex gap-2">
            {idx > 0 && <button onClick={() => setIdx(idx - 1)} className="rounded-[12px] border-2 border-line px-3 py-1.5 text-sm font-bold text-ink hover:bg-gray-50">이전</button>}
            {!last ? (
              <button onClick={() => setIdx(idx + 1)} className="rounded-[12px] bg-primary-500 px-4 py-1.5 text-sm font-bold text-white hover:bg-primary-600">다음 발화 →</button>
            ) : (
              <button onClick={load} className="rounded-[12px] bg-emerald-600 px-4 py-1.5 text-sm font-bold text-white hover:bg-emerald-700">새 대화 ↻</button>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  )
}
