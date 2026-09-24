import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { learningAPI, speakAPI, curriculumAPI } from '../api'
import AppShell from '../components/AppShell'
import LoadingScreen from '../components/LoadingScreen'

/**
 * 분석 상세(분석 탭 하위 화면) — 활동 · 취약 입모양 · 점수 · 기록. Figma 프레임은 없고, 분석 탭 '전체 통계'
 * 모달의 링크로 들어온다. 다른 하위 화면처럼 AppShell 안에 두고 색은 토큰만 쓴다(9/24, 전에는 옛 LearnHeader 화면).
 * 예전 '개요' 모드는 /analysis/overview가 분석 탭으로 넘어가 보이지 않아 뺐고, '개요' 칩은 분석 탭으로 간다.
 */
const PAGE_META = {
  activity: { title: '학습 활동', description: '최근 90일 동안 언제, 얼마나 꾸준히 학습했는지 확인합니다.' },
  visemes: { title: '취약 입모양', description: '입모양 유형별 점수와 시도 횟수를 비교해 집중할 항목을 찾습니다.' },
  scores: { title: '평균 점수', description: '독화·말하기 영역의 현재 점수를 각각 비교합니다.' },
  history: { title: '학습 기록', description: '날짜별 학습량과 누적 성과를 시간순으로 확인합니다.' },
}

// 보기 전환 칩 — '개요'는 분석 탭 자체, 나머지는 이 화면의 모드
const ANALYSIS_TABS = [
  { to: '/analysis', label: '개요' },
  { mode: 'activity', label: '활동' },
  { mode: 'visemes', label: '취약 입모양' },
  { mode: 'scores', label: '점수' },
  { mode: 'history', label: '기록' },
]

// 90일 활동 칸 색(분석 탭 활동 캘린더와 같은 heat 토큰) — 0 · 1~2 · 3~5 · 6 이상
const dayTone = (n) => (n === 0 ? 'bg-heat-0' : n <= 2 ? 'bg-heat-1' : n <= 5 ? 'bg-heat-2' : 'bg-heat-4')

function Empty({ children }) {
  return <div className="card-flat py-16 text-center text-sm text-ink-muted">{children}</div>
}

function MetricCard({ label, value, description, tone = 'text-primary-700' }) {
  return (
    <article className="card-flat">
      <p className="text-xs font-bold text-ink-soft">{label}</p>
      <p className={`mt-2 text-3xl font-bold leading-figma ${tone}`}>{value}</p>
      <p className="mt-2 text-xs leading-relaxed text-ink-muted">{description}</p>
    </article>
  )
}

export default function AnalysisDetail({ mode = 'activity' }) {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [statistics, setStatistics] = useState(null)
  const [calendar, setCalendar] = useState({})
  const [speaking, setSpeaking] = useState(null)
  const [confusion, setConfusion] = useState(null)
  const meta = PAGE_META[mode] || PAGE_META.activity

  // 독화 학습 횟수·평균 점수는 /api/statistics로 충분하다. /api/analysis는 AI 추천 문구(LLM, 약 4초)를 만든 뒤에야
  // 응답하는데, 그 문구를 그리던 개요 모드는 /analysis/overview가 분석 탭으로 넘어가 이제 보이지 않는다(9/24).
  useEffect(() => {
    setLoading(true)
    const needsCalendar = ['activity', 'history'].includes(mode)
    Promise.all([
      learningAPI.getStatistics().catch(() => null),
      needsCalendar ? learningAPI.getCalendar().catch(() => ({})) : Promise.resolve({}),
      mode === 'scores' ? speakAPI.getAnalysis().catch(() => null) : Promise.resolve(null),
      mode === 'visemes' ? curriculumAPI.confusionMatrix().catch(() => null) : Promise.resolve(null),
    ]).then(([stats, activity, speakAnalysis, confusionMatrix]) => {
      setStatistics(stats)
      setCalendar(activity || {})
      setSpeaking(speakAnalysis)
      setConfusion(confusionMatrix)
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

  const renderActivity = () => (
    <>
      <div className="grid gap-3 sm:grid-cols-3">
        <MetricCard label="활동한 날" value={`${activeDays.length}일`} description="최근 90일 동안 학습한 날짜" />
        <MetricCard label="총 활동량" value={`${totalActivity}개`} description="기간 내 완료한 학습 항목" tone="text-stat-level" />
        <MetricCard label="하루 평균" value={`${activeDays.length ? (totalActivity / activeDays.length).toFixed(1) : 0}개`} description="학습한 날을 기준으로 계산" tone="text-stat-accuracy" />
      </div>
      <section className="card-flat">
        <h2 className="text-[17px] font-bold leading-figma text-ink">최근 90일 활동</h2>
        <div className="mt-5 flex flex-wrap gap-1.5">
          {activityDays.map((day) => (
            <span key={day.key} title={`${day.key}: ${day.count}개`} className={`size-5 rounded-[5px] ${dayTone(day.count)}`} />
          ))}
        </div>
        <div className="mt-4 flex items-center gap-2 text-xs text-ink-faint">
          <span>적음</span>
          {[0, 1, 3, 6].map((n) => <span key={n} className={`size-3 rounded ${dayTone(n)}`} />)}
          <span>많음</span>
        </div>
      </section>
    </>
  )

  const renderVisemes = () => {
    // 분석 탭 '전체 통계'와 같은 출처(weak_visemes 실제 오답률)로 순위를 낸다 — 화면끼리 순위가 어긋나지 않게
    const items = [...(statistics?.weak_visemes || [])].sort((a, b) => (b.error_rate || 0) - (a.error_rate || 0))
    const cf = confusion?.jamo_confusions || []
    const confusionCard = cf.length > 0 ? (
      <section className="card-flat">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="text-[17px] font-bold leading-figma text-ink">헷갈린 입모양 (혼동 지도)</h2>
            <p className="mt-1 text-sm text-ink-muted">무엇을 무엇으로 읽었는지 · 입모양이 같아 구별 불가한 비율 {Math.round((confusion.same_viseme_ratio || 0) * 100)}%</p>
          </div>
          <span className="shrink-0 text-xs text-ink-faint">{confusion.trials || 0}시행</span>
        </div>
        <div className="mt-4 flex flex-col gap-2">
          {cf.slice(0, 8).map((c, i) => (
            <div key={i} className="flex items-center gap-3 rounded-14 bg-surface-sunken p-3">
              <span className="text-lg font-bold text-ink">‘{c.target}’ → ‘{c.read}’</span>
              {c.same_viseme > 0 && <span className="rounded-full bg-warn-tint px-2 py-0.5 text-[11px] font-bold text-warn-text">입모양 동일</span>}
              <span className="ml-auto text-sm font-bold text-bad-text">{c.count}회</span>
            </div>
          ))}
        </div>
      </section>
    ) : null
    if (!items.length && !confusionCard) return <Empty>연습을 더 하면 입모양 유형별 취약도가 이곳에 표시됩니다.</Empty>
    return (
      <>
        {confusionCard}
        {items.map((item, index) => {
          const acc = Math.max(0, Math.round(100 - (item.error_rate || 0)))
          return (
            <article key={item.viseme_id} className="card-flat">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <span className="text-[11px] font-bold text-bad-text">집중 순위 {index + 1}</span>
                  <h2 className="mt-1 text-lg font-bold leading-figma text-ink">{item.feature}</h2>
                </div>
                <div className="text-right">
                  <strong className="text-2xl font-bold text-bad">오답률 {item.error_rate}%</strong>
                  <p className="text-xs text-ink-faint">정확도 {acc}%</p>
                </div>
              </div>
              <div className="mt-4 h-2.5 overflow-hidden rounded-full bg-fill">
                <div className="h-full rounded-full bg-bad" style={{ width: `${Math.min(item.error_rate || 0, 100)}%` }} />
              </div>
            </article>
          )
        })}
      </>
    )
  }

  const renderScores = () => {
    // 막대 색은 트랙 색(§3.1) — 독화 보라, 말하기 분홍
    const scores = [
      { label: '독화', value: Math.round(Number(statistics?.average_score || 0) * 10) / 10, description: `${statistics?.total_sessions || 0}회 학습`, tone: 'bg-primary-500' },
      { label: '말하기', value: Number(speaking?.avg_score || 0), description: `${speaking?.total || 0}회 발화`, tone: 'bg-speak' },
    ]
    return (
      <div className="grid gap-4 lg:grid-cols-2">
        {scores.map((score) => (
          <article key={score.label} className="card-flat">
            <p className="text-sm font-bold text-ink-muted">{score.label}</p>
            <p className="mt-3 text-4xl font-bold leading-figma text-ink">{score.value}<span className="text-base text-ink-faint">점</span></p>
            <p className="mt-1 text-xs text-ink-faint">{score.description}</p>
            <div className="mt-6 h-2 overflow-hidden rounded-full bg-fill">
              <div className={`h-full rounded-full ${score.tone}`} style={{ width: `${Math.min(score.value, 100)}%` }} />
            </div>
          </article>
        ))}
      </div>
    )
  }

  const renderHistory = () => recentActivity.length ? (
    <div className="flex flex-col gap-2">
      {recentActivity.map((day, index) => (
        <article key={day.key} className="card-flat flex items-center justify-between gap-4 !py-4">
          <div className="flex items-center gap-3">
            <span className="grid size-10 place-items-center rounded-13 bg-primary-100 text-xs font-bold text-primary-700">{String(index + 1).padStart(2, '0')}</span>
            <div>
              <h2 className="text-sm font-bold text-ink">{day.key}</h2>
              <p className="mt-0.5 text-xs text-ink-faint">학습 활동 기록</p>
            </div>
          </div>
          <strong className="text-lg font-bold text-primary-700">{day.count}개</strong>
        </article>
      ))}
    </div>
  ) : <Empty>아직 날짜별 학습 기록이 없습니다.</Empty>

  const content = () => {
    if (mode === 'visemes') return renderVisemes()
    if (mode === 'scores') return renderScores()
    if (mode === 'history') return renderHistory()
    return renderActivity()
  }

  return (
    <AppShell active="analysis" title={meta.title} description={meta.description}>
      <div className="flex w-full flex-col gap-5">
        <nav aria-label="분석 보기 전환" className="flex flex-wrap gap-2">
          {ANALYSIS_TABS.map((tab) => {
            const active = tab.mode === mode
            return (
              <button
                key={tab.label}
                type="button"
                aria-current={active ? 'page' : undefined}
                onClick={() => navigate(tab.to || `/analysis/${tab.mode}`)}
                className={`rounded-full px-4 py-2 text-[13.5px] font-bold leading-figma transition ${
                  active ? 'bg-primary-500 text-white' : 'bg-surface-sunken text-ink-muted hover:text-primary-700'
                }`}
              >
                {tab.label}
              </button>
            )
          })}
        </nav>
        {loading ? <LoadingScreen variant="inline" /> : content()}
      </div>
    </AppShell>
  )
}
