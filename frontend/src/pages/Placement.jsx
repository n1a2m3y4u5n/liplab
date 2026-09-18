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
      <div className="mx-auto max-w-2xl px-4 py-6">
        <LearnHeader title="배치검사 결과" />
        <div className="card space-y-4">
          <div className="flex items-baseline gap-3">
            <span className="text-4xl font-black text-slate-900">Lv.{result.level}</span>
            <span className="text-sm text-gray-500">정확도 {Math.round(result.accuracy * 100)}% ({result.correct}/{result.total})</span>
          </div>
          <div>
            <p className="text-xs font-semibold text-gray-500">추천 시작 단계</p>
            <p className="mt-1 text-base font-bold text-slate-800">{result.recommended_start?.title || '입모양 인지'}</p>
          </div>
          {result.error_visemes?.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-gray-500">약한 입모양</p>
              <div className="mt-1 flex flex-wrap gap-2">
                {result.error_visemes.map((v) => (
                  <span key={v} className="rounded-full bg-rose-50 px-2.5 py-1 text-xs font-semibold text-rose-700">{VIS_NAME[v] || v}</span>
                ))}
              </div>
            </div>
          )}
          {result.error_phonemes?.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-gray-500">자주 놓친 소리(음소)</p>
              <div className="mt-1 flex flex-wrap gap-2">
                {result.error_phonemes.map((e) => (
                  <span key={e.phoneme} className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-700">{e.phoneme} ×{e.count}</span>
                ))}
              </div>
            </div>
          )}
          {mode !== 'placement' && (
            <p className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
              {MODE_LABEL[mode]} 결과를 저장했어요. 사전(A)·사후(B)를 모두 마치면 <b>학습 분석 → 통제 향상도</b>에서 변화가 보여요.
            </p>
          )}
          <div className="flex gap-2">
            <button onClick={async () => {
                // 표준검사(축 I) 진단 결과로 자동 배치: 추천 단계까지 열어 준 뒤 이동한다.
                if (mode === 'placement') {
                  try { await curriculumAPI.setTrack('perception', result.recommended_start?.stage) } catch { /* 배치 실패해도 이동은 함 */ }
                }
                navigate(STAGE_ROUTE[result.recommended_start?.key] || '/learn/viseme')
              }}
              className="flex-1 rounded-lg bg-slate-900 py-2.5 text-sm font-bold text-white hover:bg-slate-700">
              {result.recommended_start?.title || '입모양 인지'}부터 시작 →
            </button>
            <button onClick={() => start(mode)} className="rounded-lg border border-gray-300 px-4 py-2.5 text-sm font-bold text-gray-700 hover:bg-gray-50">다시 검사</button>
          </div>
        </div>
      </div>
    )
  }

  const it = items[idx]
  if (!it) return <div className="p-8 text-center text-gray-400">문항을 불러오지 못했어요. 다시 시도해 주세요.</div>
  return (
    <div className="mx-auto max-w-3xl px-4 py-4">
      <LearnHeader title="독화 배치검사" />
      <div className="mb-3 flex gap-1.5">
        {['placement', 'A', 'B'].map((m) => (
          <button key={m} onClick={() => switchMode(m)}
            className={`rounded-full px-3 py-1 text-xs font-semibold transition ${mode === m ? 'bg-slate-900 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}>
            {MODE_LABEL[m]}
          </button>
        ))}
        <span className="ml-auto self-center text-[11px] text-gray-400">사전(A)·사후(B)로 향상도 측정</span>
      </div>
      <div className="mb-3">
        <div className="flex justify-between text-xs text-gray-500"><span>진행{mode === 'placement' ? ' · 적응형' : ''}</span><span>{idx + 1} / {mode === 'placement' ? n : items.length}</span></div>
        <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-gray-200">
          <div className="h-full rounded-full bg-slate-500 transition-all" style={{ width: `${(idx / (mode === 'placement' ? n : items.length)) * 100}%` }} />
        </div>
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="card">
          <p className="mb-2 text-sm text-gray-500">이 입모양은 어떤 단어일까요?</p>
          <MouthAvatar frames={frames} />
        </div>
        <div className="card">
          <div className="grid grid-cols-2 gap-3">
            {it.options.map((w) => (
              <button key={w} onClick={() => choose(w)}
                className="rounded-xl border-2 border-gray-200 bg-white px-4 py-4 text-base font-bold text-gray-800 transition-all hover:border-primary-400 hover:bg-primary-50">
                {w}
              </button>
            ))}
          </div>
          <p className="mt-3 text-center text-xs text-gray-400">정답은 끝나면 결과로 알려드려요</p>
        </div>
      </div>
    </div>
  )
}
