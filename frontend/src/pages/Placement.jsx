import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { curriculumAPI, learningAPI } from '../api'
import MouthAvatar from '../components/MouthAvatar'
import LearnHeader from '../components/LearnHeader'

/**
 * 디지털 독화 배치검사(축 I) — 난이도가 통제된 입모양→단어 4지선다로 현재 수준을 진단한다.
 * 문항마다 정답을 즉시 공개하지 않고, 끝나면 수준·음소별 오류·시작 단계를 리포트로 보여준다.
 */
const VIS_NAME = {
  1: '양순음', 2: '개방모음', 3: '전설모음', 4: '원순모음', 5: '중설모음',
  6: '치경음', 7: '연구개음', 8: '성문음', 9: '이중모음', 10: '경구개음',
}

const STAGE_ROUTE = { viseme: '/learn/viseme', word: '/learn/word', sentence: '/practice' }

const MODE_LABEL = { placement: '배치검사', A: '사전검사', B: '사후검사' }

export default function Placement() {
  const navigate = useNavigate()
  const [items, setItems] = useState(null)
  const [idx, setIdx] = useState(0)
  const [responses, setResponses] = useState({})
  const [frames, setFrames] = useState([])
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [mode, setMode] = useState('placement')  // placement | A(사전) | B(사후) — 향상도검사(축 I)
  const [n, setN] = useState(8)  // 목표 문항 수(적응형 배치검사)

  const start = useCallback(async (m = mode) => {
    setLoading(true); setResult(null); setResponses({}); setIdx(0)
    try {
      if (m === 'placement') {
        // 적응형: 첫 문항만 받고, 정오답에 따라 다음 문항을 서버가 고른다(축 I).
        const d = await curriculumAPI.nextPlacementItem([], {}, 8)
        setN(d.n || 8)
        setItems(d.item ? [d.item] : [])
      } else {
        // 향상도 동형폼(A 사전 / B 사후)은 통제 비교를 위해 고정 배치 유지.
        const d = await curriculumAPI.getPlacement(8, m)
        setItems(d.items)
      }
    } catch { /* ignore */ } finally { setLoading(false) }
  }, [mode])

  useEffect(() => { start('placement') }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!items || !items[idx]) return
    setFrames([])
    learningAPI.getVisemes(items[idx].word).then(setFrames).catch(() => {})
  }, [items, idx])

  const choose = async (word) => {
    if (submitting || result) return   // 마지막 문항 중복 클릭 시 이중 채점·저장 방지
    const it = items[idx]
    const next = { ...responses, [it.id]: word }
    setResponses(next)
    if (mode === 'placement') {
      // 적응형: 방금 정오답으로 다음 문항을 서버가 고른다. done이면 지금까지 문항으로 채점.
      setSubmitting(true)
      try {
        const d = await curriculumAPI.nextPlacementItem(items, next, n)
        if (d.done || !d.item) {
          const r = await curriculumAPI.scorePlacement(items, next, 'placement')
          setResult(r)
        } else {
          setItems([...items, d.item]); setIdx(idx + 1)
        }
      } finally { setSubmitting(false) }
      return
    }
    // 향상도 동형폼(A/B): 고정 배치 순차 진행 후 일괄 채점.
    if (idx < items.length - 1) {
      setIdx(idx + 1)
    } else {
      setSubmitting(true)
      try {
        const r = await curriculumAPI.scorePlacement(items, next, mode)
        setResult(r)
      } finally {
        setSubmitting(false)
      }
    }
  }

  const switchMode = (m) => { setMode(m); start(m) }

  if (loading || !items) return <div className="p-8 text-center text-gray-400">검사를 준비하는 중…</div>

  if (result) {
    return (
      <div className="mx-auto flex min-h-[100dvh] max-w-[560px] flex-col justify-center px-4 py-8">
        {/* 결과 리포트 카드 */}
        <div className="overflow-hidden rounded-[22px] border-2 border-b-[5px] border-[#6d3fc4]"
          style={{ backgroundImage: 'linear-gradient(166deg, #a78bfa 0%, #7d53de 71%)' }}>
          <div className="flex flex-col items-center gap-2 px-6 py-8 text-white">
            <img src="/ui/mascot.svg" alt="" className="h-16 w-16" />
            <p className="text-[13px] font-bold opacity-85">{mode === 'placement' ? '배치검사 결과' : `${MODE_LABEL[mode]} 결과`}</p>
            <p className="text-[40px] font-black leading-none tracking-[-1px]">Lv.{result.level}</p>
            <p className="text-sm font-bold opacity-90">정확도 {Math.round(result.accuracy * 100)}% ({result.correct}/{result.total})</p>
          </div>
        </div>

        <div className="mt-4 space-y-4">
          <div className="card-flat">
            <p className="text-xs font-bold text-ink-muted">추천 시작 단계</p>
            <p className="mt-1 text-[17px] font-bold text-ink">{result.recommended_start?.title || '입모양 인지'}</p>
          </div>
          {result.error_visemes?.length > 0 && (
            <div>
              <p className="text-xs font-bold text-ink-muted">약한 입모양</p>
              <div className="mt-1.5 flex flex-wrap gap-2">
                {result.error_visemes.map((v) => (
                  <span key={v} className="rounded-full bg-rose-50 px-3 py-1 text-xs font-bold text-rose-700">{VIS_NAME[v] || v}</span>
                ))}
              </div>
            </div>
          )}
          {result.error_phonemes?.length > 0 && (
            <div>
              <p className="text-xs font-bold text-ink-muted">자주 놓친 소리(음소)</p>
              <div className="mt-1.5 flex flex-wrap gap-2">
                {result.error_phonemes.map((e) => (
                  <span key={e.phoneme} className="rounded-full bg-amber-50 px-3 py-1 text-xs font-bold text-amber-700">{e.phoneme} ×{e.count}</span>
                ))}
              </div>
            </div>
          )}
          {mode !== 'placement' && (
            <p className="rounded-2xl bg-primary-100 px-4 py-3 text-xs text-primary-700">
              {MODE_LABEL[mode]} 결과를 저장했어요. 사전(A)·사후(B)를 모두 마치면 <b>학습 분석 → 통제 향상도</b>에서 변화가 보여요.
            </p>
          )}
          <div className="flex gap-2">
            <button onClick={async () => {
                if (mode === 'placement') {
                  try { await curriculumAPI.setTrack('perception', result.recommended_start?.stage) } catch { /* 배치 실패해도 이동은 함 */ }
                }
                navigate(STAGE_ROUTE[result.recommended_start?.key] || '/learn/viseme')
              }}
              className="btn-primary flex-1 !py-3.5 text-[17px]">
              {result.recommended_start?.title || '입모양 인지'}부터 시작 →
            </button>
            <button onClick={() => start(mode)} className="btn-secondary !px-5 !py-3.5 text-[15px]">다시 검사</button>
          </div>
        </div>
      </div>
    )
  }

  const it = items[idx]
  if (!it) return <div className="p-8 text-center text-gray-400">문항을 불러오지 못했어요. 다시 시도해 주세요.</div>
  const total = mode === 'placement' ? n : items.length
  return (
    <div className="mx-auto flex min-h-[100dvh] max-w-[680px] flex-col px-4 pb-10 pt-6 sm:px-6">
      {/* 진행 헤더 */}
      <div className="flex items-center gap-4">
        <button type="button" onClick={() => navigate('/dashboard')} aria-label="나가기" className="shrink-0 text-ink-muted hover:text-ink">
          <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"><path d="M6 6l12 12M18 6L6 18" /></svg>
        </button>
        <div className="h-3.5 flex-1 overflow-hidden rounded-full bg-line">
          <div className="h-full rounded-full bg-primary-500 transition-all" style={{ width: `${(idx / total) * 100}%` }} />
        </div>
        <span className="shrink-0 text-[15px] font-bold text-ink-muted">{idx + 1} / {total}</span>
      </div>

      {/* 모드 스위처 */}
      <div className="mt-5 flex gap-1 self-start rounded-[14px] bg-gray-100 p-1">
        {['placement', 'A', 'B'].map((m) => (
          <button key={m} onClick={() => switchMode(m)}
            className={`rounded-[10px] px-4 py-2 text-[13px] font-bold transition ${mode === m ? 'bg-white text-primary-500 shadow-sm' : 'text-gray-400'}`}>
            {MODE_LABEL[m]}
          </button>
        ))}
      </div>

      {/* 질문 */}
      <div className="mt-6">
        <p className="text-[13px] font-bold text-primary-500">{mode === 'placement' ? '적응형 배치검사' : MODE_LABEL[mode]}</p>
        <p className="mt-2 text-[26px] font-bold tracking-[-0.75px] text-ink sm:text-[30px]">이 입모양은 어떤 단어일까요?</p>
      </div>

      {/* 입모양 */}
      <div className="mt-6 rounded-[22px] border-2 border-line bg-white p-4">
        <MouthAvatar frames={frames} />
      </div>

      {/* 4지선다 */}
      <div className="mt-6 flex flex-col gap-3">
        {it.options.map((w, i) => (
          <button key={w} disabled={submitting} onClick={() => choose(w)}
            className="flex items-center gap-4 rounded-2xl border-2 border-b-[5px] border-line bg-white px-5 py-4 text-left text-[20px] font-bold text-ink transition-all hover:border-primary-400 hover:bg-primary-50 active:translate-y-[3px] active:border-b-2 disabled:opacity-60">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-gray-100 text-[13px] text-ink-muted">{i + 1}</span>
            <span className="flex-1">{w}</span>
          </button>
        ))}
      </div>
      <p className="mt-4 text-center text-xs text-gray-400">정답은 끝나면 결과로 알려드려요</p>
    </div>
  )
}
