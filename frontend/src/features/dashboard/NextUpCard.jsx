import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { curriculumAPI } from '../../api'

// 지식추적 개인화 추천 — 취약 음소를 표적으로 다음에 연습할 콘텐츠를 안내(고도화 축 G)
export default function NextUpCard() {
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  useEffect(() => {
    let active = true
    curriculumAPI.getNext().then((d) => { if (active) setData(d) }).catch(() => {})
    return () => { active = false }
  }, [])
  if (!data) return null
  const hasData = data.coverage > 0
  return (
    <section className="mb-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-bold text-slate-900">
          다음 추천 <span className="ml-1 text-xs font-medium text-slate-500">지식추적 맞춤</span>
        </h2>
        {hasData && <span className="text-xs font-medium text-slate-500">추천 난이도 {data.level}</span>}
      </div>
      {hasData ? (
        <div className="mt-3 space-y-3">
          <div>
            <p className="text-xs font-semibold text-slate-500">집중할 입모양(약점)</p>
            <div className="mt-1 flex flex-wrap gap-2">
              {data.targets.map((t) => (
                <span key={t.viseme_id} className="inline-flex items-center gap-1 rounded-full bg-rose-50 px-2.5 py-1 text-xs font-semibold text-rose-700">
                  {t.name}
                  {typeof t.mastery === 'number' && <span className="text-rose-400">{Math.round(t.mastery * 100)}%</span>}
                </span>
              ))}
            </div>
          </div>
          {data.words?.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-slate-500">추천 단어</p>
              <p className="mt-1 text-sm font-medium text-slate-800">{data.words.slice(0, 6).map((w) => w.word).join(' · ')}</p>
            </div>
          )}
          <div className="flex gap-2 pt-1">
            <button type="button" onClick={() => navigate('/learn/word')} className="rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-bold text-white transition hover:bg-slate-700">단어 연습</button>
            <button type="button" onClick={() => navigate(`/learn/viseme${data.target_visemes?.[0] ? `?v=${data.target_visemes[0]}` : ''}`)} className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-bold text-slate-700 transition hover:bg-slate-50">약점 입모양 보기</button>
          </div>
        </div>
      ) : (
        <p className="mt-2 text-sm text-slate-600">학습을 시작하면 자주 틀리는 입모양을 분석해 맞춤 문제를 추천해요.</p>
      )}
    </section>
  )
}
