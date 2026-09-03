import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { learningAPI, speakAPI, tactileAPI } from '../api'
import LearnHeader from '../components/LearnHeader'

const PAGE_META = {
  overview: { title: '학습 분석', description: '독화·말하기·촉각 학습에서 쌓인 핵심 성과를 한눈에 확인합니다.' },
  activity: { title: '학습 활동', description: '최근 90일 동안 언제, 얼마나 꾸준히 학습했는지 확인합니다.' },
  visemes: { title: '취약 입모양', description: '입모양 유형별 점수와 시도 횟수를 비교해 집중할 항목을 찾습니다.' },
  scores: { title: '평균 점수', description: '독화·말하기·촉각 영역의 현재 점수를 각각 비교합니다.' },
  history: { title: '학습 기록', description: '날짜별 학습량과 누적 성과를 시간순으로 확인합니다.' },
}

// 다섯 분석 뷰 탭 — 예전엔 개요·취약입모양만 링크가 있어 활동·점수·기록 뷰가 URL 직접 입력
// 외에는 도달 불가능했다. 탭바로 완성된 세 뷰를 노출한다.
const ANALYSIS_TABS = [
  { mode: 'overview', label: '개요' },
  { mode: 'activity', label: '활동' },
  { mode: 'visemes', label: '취약 입모양' },
  { mode: 'scores', label: '점수' },
  { mode: 'history', label: '기록' },
]

function Loading() {
  return <div className="rounded-[24px] border border-slate-200 bg-white py-20 text-center text-sm text-slate-400">분석 데이터를 불러오는 중…</div>
}

function Empty({ children }) {
  return <div className="rounded-[24px] border border-slate-200 bg-white px-5 py-16 text-center text-sm text-slate-500">{children}</div>
}

function MetricCard({ label, value, description, tone = 'text-violet-700' }) {
  return (
    <article className="rounded-[22px] border border-slate-200 bg-white p-5">
      <p className="text-xs font-bold text-slate-400">{label}</p>
      <p className={`mt-2 text-3xl font-black ${tone}`}>{value}</p>
      <p className="mt-2 text-xs leading-relaxed text-slate-500">{description}</p>
    </article>
  )
}

export default function AnalysisDetail({ mode = 'overview' }) {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [statistics, setStatistics] = useState(null)
  const [analysis, setAnalysis] = useState(null)
  const [calendar, setCalendar] = useState({})
  const [speaking, setSpeaking] = useState(null)
  const [tactile, setTactile] = useState(null)
  const meta = PAGE_META[mode] || PAGE_META.overview

  useEffect(() => {
    setLoading(true)
    const needsAnalysis = ['overview', 'visemes', 'scores'].includes(mode)
    const needsCalendar = ['activity', 'history'].includes(mode)
    Promise.all([
      learningAPI.getStatistics().catch(() => null),
      needsAnalysis ? learningAPI.getAnalysis().catch(() => null) : Promise.resolve(null),
      needsCalendar ? learningAPI.getCalendar().catch(() => ({})) : Promise.resolve({}),
      mode === 'scores' ? speakAPI.getAnalysis().catch(() => null) : Promise.resolve(null),
      mode === 'scores' ? tactileAPI.getAnalysis().catch(() => null) : Promise.resolve(null),
    ]).then(([stats, readAnalysis, activity, speakAnalysis, tactileAnalysis]) => {
      setStatistics(stats)
      setAnalysis(readAnalysis)
      setCalendar(activity || {})
      setSpeaking(speakAnalysis)
      setTactile(tactileAnalysis)
    }).finally(() => setLoading(false))
  }, [mode])

  const activityDays = useMemo(() => {
    const today = new Date()
    return Array.from({ length: 90 }, (_, index) => {
      const date = new Date(today)
      date.setDate(today.getDate() - (89 - index))
      const key = date.toISOString().slice(0, 10)
      return { key, count: Number(calendar[key]) || 0 }
    })
  }, [calendar])

  const activeDays = activityDays.filter((day) => day.count > 0)
  const totalActivity = activeDays.reduce((sum, day) => sum + day.count, 0)
  const recentActivity = [...activeDays].reverse()

  const renderOverview = () => (
    <>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard label="총 학습" value={`${statistics?.total_sessions || 0}회`} description="완료한 독화 학습 세션" />
        <MetricCard label="평균 점수" value={`${statistics?.average_score || 0}점`} description="전체 독화 테스트 평균" tone="text-sky-700" />
        <MetricCard label="현재 레벨" value={`${statistics?.current_level || 1}`} description="현재 추천 학습 난이도" tone="text-emerald-700" />
        <MetricCard label="누적 XP" value={statistics?.total_xp || 0} description="학습으로 모은 경험치" tone="text-amber-700" />
      </div>
      <section className="mt-5 rounded-[24px] border border-slate-200 bg-white p-5 sm:p-7">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="text-lg font-black">지금 집중할 항목</h2>
            <p className="mt-1 text-sm text-slate-500">오답률이 높은 입모양부터 연습해 보세요.</p>
          </div>
          <button type="button" onClick={() => navigate('/analysis/visemes')} className="text-sm font-black text-violet-700">상세 보기 →</button>
        </div>
        {statistics?.weak_visemes?.length ? (
          <div className="mt-5 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {statistics.weak_visemes.slice(0, 5).map((item) => (
              <div key={item.viseme_id} className="rounded-2xl bg-rose-50 p-4">
                <p className="text-sm font-black text-rose-900">{item.feature}</p>
                <p className="mt-1 text-xs text-rose-700">오답률 {item.error_rate}%</p>
              </div>
            ))}
          </div>
        ) : <p className="mt-5 text-sm text-slate-400">아직 취약점을 판단할 기록이 충분하지 않아요.</p>}
      </section>
      {analysis?.recommendation && (
        <section className="mt-5 rounded-[24px] bg-violet-50 p-5 sm:p-7">
          <p className="text-xs font-black text-violet-700">AI 학습 제안</p>
          <p className="mt-2 whitespace-pre-line text-sm leading-relaxed text-violet-950">{analysis.recommendation}</p>
        </section>
      )}
    </>
  )

  const renderActivity = () => (
    <>
      <div className="grid gap-3 sm:grid-cols-3">
        <MetricCard label="활동한 날" value={`${activeDays.length}일`} description="최근 90일 동안 학습한 날짜" />
        <MetricCard label="총 활동량" value={`${totalActivity}개`} description="기간 내 완료한 학습 항목" tone="text-sky-700" />
        <MetricCard label="하루 평균" value={`${activeDays.length ? (totalActivity / activeDays.length).toFixed(1) : 0}개`} description="학습한 날을 기준으로 계산" tone="text-emerald-700" />
      </div>
      <section className="mt-5 rounded-[24px] border border-slate-200 bg-white p-5 sm:p-7">
        <h2 className="text-lg font-black">최근 90일 활동</h2>
        <div className="mt-5 flex flex-wrap gap-1.5">
          {activityDays.map((day) => {
            const tone = day.count === 0 ? 'bg-slate-100' : day.count <= 2 ? 'bg-violet-200' : day.count <= 5 ? 'bg-violet-400' : 'bg-violet-700'
            return <span key={day.key} title={`${day.key}: ${day.count}개`} className={`h-5 w-5 rounded-[5px] ${tone}`} />
          })}
        </div>
        <div className="mt-4 flex items-center gap-2 text-xs text-slate-400"><span>적음</span><span className="h-3 w-3 rounded bg-slate-100" /><span className="h-3 w-3 rounded bg-violet-200" /><span className="h-3 w-3 rounded bg-violet-400" /><span className="h-3 w-3 rounded bg-violet-700" /><span>많음</span></div>
      </section>
    </>
  )

  const renderVisemes = () => {
    // 개요탭('지금 집중할 항목')과 동일 소스(weak_visemes 실제 오답률)로 통일 — 순위 불일치 방지
    const items = [...(statistics?.weak_visemes || [])].sort((a, b) => (b.error_rate || 0) - (a.error_rate || 0))
    if (!items.length) return <Empty>연습을 더 하면 입모양 유형별 취약도가 이곳에 표시됩니다.</Empty>
    return (
      <div className="space-y-3">
        {items.map((item, index) => {
          const acc = Math.max(0, Math.round(100 - (item.error_rate || 0)))
          return (
            <article key={item.viseme_id} className="rounded-[20px] border border-slate-200 bg-white p-5">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <span className="text-[11px] font-black text-rose-600">집중 순위 {index + 1}</span>
                  <h2 className="mt-1 text-lg font-black">{item.feature}</h2>
                </div>
                <div className="text-right"><strong className="text-2xl font-black text-rose-600">오답률 {item.error_rate}%</strong><p className="text-xs text-slate-400">정확도 {acc}%</p></div>
              </div>
              <div className="mt-4 h-2.5 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-rose-500" style={{ width: `${Math.min(item.error_rate || 0, 100)}%` }} /></div>
            </article>
          )
        })}
      </div>
    )
  }

  const renderScores = () => {
    const scores = [
      { label: '독화', value: Number(analysis?.average_score || 0), description: `${analysis?.total_sessions || 0}회 학습`, tone: 'bg-sky-500' },
      { label: '말하기', value: Number(speaking?.avg_score || 0), description: `${speaking?.total || 0}회 발화`, tone: 'bg-rose-500' },
      { label: '촉각', value: Number(tactile?.accuracy || 0), description: `${tactile?.total || 0}회 문제`, tone: 'bg-violet-500' },
    ]
    return (
      <div className="grid gap-4 lg:grid-cols-3">
        {scores.map((score) => (
          <article key={score.label} className="rounded-[24px] border border-slate-200 bg-white p-6">
            <p className="text-sm font-black text-slate-500">{score.label}</p>
            <p className="mt-3 text-4xl font-black text-slate-950">{score.value}<span className="text-base text-slate-400">점</span></p>
            <p className="mt-1 text-xs text-slate-400">{score.description}</p>
            <div className="mt-6 h-2 overflow-hidden rounded-full bg-slate-100"><div className={`h-full rounded-full ${score.tone}`} style={{ width: `${Math.min(score.value, 100)}%` }} /></div>
          </article>
        ))}
      </div>
    )
  }

  const renderHistory = () => recentActivity.length ? (
    <div className="space-y-2">
      {recentActivity.map((day, index) => (
        <article key={day.key} className="flex items-center justify-between gap-4 rounded-[18px] border border-slate-200 bg-white px-5 py-4">
          <div className="flex items-center gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-violet-50 text-xs font-black text-violet-700">{String(index + 1).padStart(2, '0')}</span>
            <div><h2 className="text-sm font-black text-slate-900">{day.key}</h2><p className="mt-0.5 text-xs text-slate-400">학습 활동 기록</p></div>
          </div>
          <strong className="text-lg font-black text-violet-700">{day.count}개</strong>
        </article>
      ))}
    </div>
  ) : <Empty>아직 날짜별 학습 기록이 없습니다.</Empty>

  const content = () => {
    if (mode === 'activity') return renderActivity()
    if (mode === 'visemes') return renderVisemes()
    if (mode === 'scores') return renderScores()
    if (mode === 'history') return renderHistory()
    return renderOverview()
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-primary-50">
      <LearnHeader
        accent="etc"
        title={meta.title}
        description={meta.description}
        maxWidth="max-w-6xl"
        onExit={() => navigate('/dashboard')}
      />
      <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
        <nav aria-label="분석 보기 전환" className="mb-5 flex flex-wrap gap-2">
          {ANALYSIS_TABS.map((tab) => {
            const active = tab.mode === mode
            return (
              <button
                key={tab.mode}
                type="button"
                aria-current={active ? 'page' : undefined}
                onClick={() => navigate(`/analysis/${tab.mode}`)}
                className={`rounded-full px-4 py-1.5 text-sm font-black transition ${
                  active ? 'bg-violet-700 text-white' : 'bg-white text-slate-500 border border-slate-200 hover:text-violet-700'
                }`}
              >
                {tab.label}
              </button>
            )
          })}
        </nav>
        {loading ? <Loading /> : content()}
      </main>
    </div>
  )
}
