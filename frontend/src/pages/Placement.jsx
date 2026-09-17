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

export default function Placement() {
  const navigate = useNavigate()
  const [items, setItems] = useState(null)
  const [idx, setIdx] = useState(0)
  const [responses, setResponses] = useState({})
  const [frames, setFrames] = useState([])
  const [result, setResult] = useState(null)
  const [delta, setDelta] = useState(null) // 지난 검사(baseline) 대비 향상도
  const [loading, setLoading] = useState(true)

  const start = useCallback(async () => {
    setLoading(true); setResult(null); setResponses({}); setIdx(0)
    try {
      const d = await curriculumAPI.getPlacement(8)
      setItems(d.items)
    } catch { /* ignore */ } finally { setLoading(false) }
  }, [])

  useEffect(() => { start() }, [start])

  useEffect(() => {
    if (!items || !items[idx]) return
    setFrames([])
    learningAPI.getVisemes(items[idx].word).then(setFrames).catch(() => {})
  }, [items, idx])

  const choose = async (word) => {
    const it = items[idx]
    const next = { ...responses, [it.id]: word }
    setResponses(next)
    if (idx < items.length - 1) {
      setIdx(idx + 1)
    } else {
      const r = await curriculumAPI.scorePlacement(items, next)
      setResult(r)
      // 방금 결과가 저장됐으니, 첫 검사 대비 향상도(2회차부터)를 가져와 함께 보여준다
      curriculumAPI.getAssessmentHistory().then((h) => setDelta(h?.delta || null)).catch(() => {})
    }
  }

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
          {delta && (
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
              <p className="text-xs font-bold text-slate-600">지난 첫 검사 대비 향상도</p>
              <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-sm">
                <span className={`font-black ${delta.accuracy >= 0 ? 'text-emerald-700' : 'text-rose-600'}`}>
                  정확도 {delta.accuracy >= 0 ? '+' : ''}{Math.round(delta.accuracy * 100)}%p
                </span>
                <span className={`font-black ${delta.level >= 0 ? 'text-emerald-700' : 'text-rose-600'}`}>
                  수준 {delta.level >= 0 ? '+' : ''}{delta.level}
                </span>
              </div>
              {delta.resolved_visemes?.length > 0 && (
                <p className="mt-1.5 text-xs text-emerald-700">
                  이제 안 틀리는 입모양: {delta.resolved_visemes.map((v) => VIS_NAME[v] || v).join(', ')}
                </p>
              )}
            </div>
          )}
          <div className="flex gap-2">
            <button onClick={() => navigate(STAGE_ROUTE[result.recommended_start?.key] || '/learn/viseme')}
              className="flex-1 rounded-lg bg-slate-900 py-2.5 text-sm font-bold text-white hover:bg-slate-700">
              {result.recommended_start?.title || '입모양 인지'}부터 시작 →
            </button>
            <button onClick={start} className="rounded-lg border border-gray-300 px-4 py-2.5 text-sm font-bold text-gray-700 hover:bg-gray-50">다시 검사</button>
          </div>
        </div>
      </div>
    )
  }

  const it = items[idx]
  return (
    <div className="mx-auto max-w-3xl px-4 py-4">
      <LearnHeader title="독화 배치검사" />
      <div className="mb-3">
        <div className="flex justify-between text-xs text-gray-500"><span>진행</span><span>{idx + 1} / {items.length}</span></div>
        <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-gray-200">
          <div className="h-full rounded-full bg-slate-500 transition-all" style={{ width: `${((idx) / items.length) * 100}%` }} />
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
