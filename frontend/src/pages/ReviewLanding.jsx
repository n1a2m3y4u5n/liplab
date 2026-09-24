import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { learningAPI, speakAPI } from '../api'
import useStore from '../store/useStore'
import AppShell from '../components/AppShell'
import LoadingScreen from '../components/LoadingScreen'

const QUESTION_TYPES = ['test', 'test-multiple', 'essay']
const qTypes = (length) => Array.from({ length }, (_, index) => QUESTION_TYPES[index % QUESTION_TYPES.length]).sort(() => Math.random() - 0.5)

const REVIEW_LINKS = [
  { label: '독화', description: '독화 테스트에서 놓친 문장', to: '/review/mistakes', tone: 'bg-rose-50 text-rose-700' },
  { label: '말하기', description: '다르게 인식된 발음과 억양', to: '/review/speaking', tone: 'bg-amber-50 text-amber-800' },
]

function sumBuckets(buckets = {}) {
  return Object.values(buckets).reduce((total, value) => total + (Number(value) || 0), 0)
}

function reviewCount(data = {}) {
  const count = Number(data.count)
  return data.count != null && Number.isFinite(count) ? count : sumBuckets(data.buckets)
}

export default function ReviewLanding({ mode = 'today' }) {
  const navigate = useNavigate()
  const setScenario = useStore((state) => state.setScenario)
  const [loading, setLoading] = useState(true)
  const [counts, setCounts] = useState(null)
  const [mistakes, setMistakes] = useState([])

  useEffect(() => {
    if (mode === 'mistakes') {
      learningAPI.getReviewSentences()
        .then((items) => setMistakes(items || []))
        .catch(() => setMistakes([]))
        .finally(() => setLoading(false))
      return
    }

    Promise.all([
      learningAPI.getReviewSentences().catch(() => []),
      speakAPI.getReview().catch(() => ({ buckets: {} })),
    ]).then(([wrong, speaking]) => {
      setCounts({
        mistakes: (wrong || []).length,
        speaking: reviewCount(speaking),
      })
    }).finally(() => setLoading(false))
  }, [mode])

  const startMistakes = () => {
    const sentences = mistakes.map((item) => item.sentence).filter(Boolean)
    if (!sentences.length) return
    setScenario({
      situation: '틀린 문장 복습',
      level: 1,
      sentences,
      qTypes: qTypes(sentences.length),
      scenario_id: `mistake_review_${Date.now()}`,
    }, 'test')
    navigate('/practice', { state: { review: true } })
  }

  if (mode === 'mistakes') {
    return (
      <AppShell active="review" title="독화 복습" description="독화 테스트에서 놓친 문장만 모아 다시 확인합니다">
        <div className="w-full space-y-5">
          {loading ? (
            <LoadingScreen variant="inline" />
          ) : mistakes.length ? (
            <>
              <div className="card flex flex-wrap items-center justify-between gap-3">
                <p className="text-sm text-gray-600">틀린 문장 <b className="text-gray-900">{mistakes.length}개</b>를 모아 다시 연습해보세요.</p>
                <button type="button" onClick={startMistakes} className="btn-primary py-2.5 text-sm">
                  {mistakes.length}문장 복습 시작
                </button>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                {mistakes.map((item, index) => (
                  <article key={`${item.sentence}-${index}`} className="card">
                    <div className="flex items-start justify-between gap-3">
                      <span className="rounded-full bg-red-50 px-2.5 py-1 text-[11px] font-semibold text-red-700">오답 {String(index + 1).padStart(2, '0')}</span>
                      <span className="text-xs text-gray-400">{item.situation || '문장 독화'}</span>
                    </div>
                    <p className="mt-4 text-lg font-bold leading-relaxed text-gray-900">{item.sentence}</p>
                    {item.user_answer && <p className="mt-2 text-sm text-gray-500">내 답: {item.user_answer}</p>}
                  </article>
                ))}
              </div>
            </>
          ) : (
            <div className="card text-center py-16">
              <h2 className="text-xl font-bold text-gray-900 mb-1">다시 풀 문장이 없어요</h2>
              <p className="text-gray-500 mb-5">새로운 문장 학습을 완료하면 오답이 이곳에 모입니다.</p>
              <button type="button" onClick={() => navigate('/learn/scenario')} className="btn-primary">문장 학습으로</button>
            </div>
          )}
        </div>
      </AppShell>
    )
  }

  const countFor = (to) => {
    if (!counts) return '—'
    if (to === '/review/mistakes') return counts.mistakes
    if (to === '/review/speaking') return counts.speaking
    return '—'
  }
  const total = counts ? Object.values(counts).reduce((sum, value) => sum + value, 0) : 0

  return (
    <AppShell active="review" title="오늘의 복습" description="독화·말하기별 복습 내용을 확인하고 원하는 영역으로 이동하세요">
      <div className="w-full space-y-5">
        <section className="rounded-[24px] p-6 text-white" style={{ backgroundImage: 'linear-gradient(160deg, #a78bfa 0%, #7d53de 71%)' }}>
          <div>
            <p className="text-xs font-bold tracking-[0.12em] text-white/80">TODAY</p>
            <h2 className="mt-2 text-2xl font-black">{loading ? '복습 항목을 확인하고 있어요' : `${total}개 항목이 기다리고 있어요`}</h2>
            <p className="mt-2 text-sm text-white/85">독화·말하기 중 필요한 복습을 골라서 진행하세요.</p>
          </div>
        </section>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {REVIEW_LINKS.map((item) => (
            <button key={item.to} type="button" onClick={() => navigate(item.to)} className="group rounded-[22px] border border-slate-200 bg-white p-5 text-left transition hover:-translate-y-0.5 hover:border-amber-300 hover:shadow-lg">
              <div className="flex items-center justify-between gap-3">
                <span className={`rounded-full px-3 py-1 text-[11px] font-black ${item.tone}`}>{item.label}</span>
                <span className="text-2xl font-black text-slate-900">{countFor(item.to)}</span>
              </div>
              <p className="mt-4 text-sm leading-relaxed text-slate-500">{item.description}</p>
              <span className="mt-5 block text-sm font-black text-slate-800 transition group-hover:text-amber-700">페이지 열기 →</span>
            </button>
          ))}
        </div>
      </div>
    </AppShell>
  )
}
