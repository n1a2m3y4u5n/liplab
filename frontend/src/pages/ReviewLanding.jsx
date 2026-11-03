import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { learningAPI, speakAPI } from '../api'
import useStore from '../store/useStore'
import AppShell from '../components/AppShell'
import LoadingScreen from '../components/LoadingScreen'
import { mistakeReviewScenario } from '../lib/reviewScenario'

const QUESTION_TYPES = ['test', 'test-multiple', 'essay']
const qTypes = (length) => Array.from({ length }, (_, index) => QUESTION_TYPES[index % QUESTION_TYPES.length]).sort(() => Math.random() - 0.5)

const REVIEW_LINKS = [
  { label: '독화', description: '입모양 읽기에서 놓친 문장', to: '/review/mistakes', tone: 'bg-bad-tint text-bad-dark' },
  { label: '말하기', description: '다르게 인식된 발음과 억양', to: '/review/speaking', tone: 'bg-warn-tint text-warn-text' },
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
    // 문장마다 원래 난이도(difficulty_level)를 levels에 담는다. 예전에는 level 1 고정이라 4·5단계 문장의 복습도 1로 저장됐다
    const scenario = mistakeReviewScenario(mistakes, qTypes)
    if (!scenario.sentences.length) return
    setScenario(scenario, 'test')
    navigate('/practice', { state: { review: true } })
  }

  if (mode === 'mistakes') {
    // 모바일은 카드 안쪽 여백을 줄여 오답 네댓 개가 한 화면에 들어오게 한다
    return (
      <AppShell backTo="/records?view=wrong" backLabel="틀린 문장" active="records" title="입모양 읽기 복습" description="입모양 읽기에서 놓친 문장만 모아 다시 확인합니다">
        <div className="w-full space-y-5">
          {loading ? (
            <LoadingScreen variant="inline" />
          ) : mistakes.length ? (
            <>
              <div className="card flex flex-wrap items-center justify-between gap-3 max-sm:p-4">
                <p className="text-sm text-ink-muted">틀린 문장 <b className="text-ink">{mistakes.length}개</b>를 모아 다시 연습해보세요.</p>
                <button type="button" onClick={startMistakes} className="btn-primary py-2.5 text-sm">
                  {mistakes.length}문장 복습 시작
                </button>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                {mistakes.map((item, index) => (
                  <article key={`${item.sentence}-${index}`} className="card max-sm:p-4">
                    <div className="flex items-start justify-between gap-3">
                      <span className="rounded-full bg-bad-tint px-2.5 py-1 text-[11px] font-semibold text-bad-dark">틀린 문장 {String(index + 1).padStart(2, '0')}</span>
                      <span className="text-xs text-ink-caption">{item.situation || '문장 독화'}</span>
                    </div>
                    <p className="mt-2 text-lg font-bold leading-relaxed text-ink sm:mt-4">{item.sentence}</p>
                    {item.user_answer && <p className="mt-2 text-sm text-ink-muted">내 답: {item.user_answer}</p>}
                  </article>
                ))}
              </div>
            </>
          ) : (
            <div className="card text-center py-16">
              <h2 className="text-xl font-bold text-ink mb-1">다시 풀 문장이 없어요</h2>
              <p className="text-ink-muted mb-5">새로운 문장 학습을 마치면 틀린 문장이 이곳에 모입니다.</p>
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
    <AppShell backTo="/records?view=wrong" backLabel="틀린 문장" active="records" title="오늘의 복습" description="독화·말하기별 복습 내용을 확인하고 원하는 영역으로 이동하세요">
      <div className="w-full space-y-5">
        <section className="rounded-16 border border-line bg-white p-6">
          <div>
            <p className="text-[12px] font-semibold text-track-dark">TODAY</p>
            <h2 className="mt-2 text-[22px] font-bold tracking-[-0.44px] text-ink">{loading ? '복습 항목을 확인하고 있어요' : `${total}개 항목이 기다리고 있어요`}</h2>
            <p className="mt-2 text-sm text-ink-muted">독화·말하기 중 필요한 복습을 골라서 진행하세요.</p>
          </div>
        </section>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {REVIEW_LINKS.map((item) => (
            <button key={item.to} type="button" onClick={() => navigate(item.to)} className="group rounded-[22px] border border-line bg-white p-5 text-left transition hover:-translate-y-0.5 hover:border-warn/40 hover:shadow-lg">
              <div className="flex items-center justify-between gap-3">
                <span className={`rounded-full px-3 py-1 text-[11px] font-black ${item.tone}`}>{item.label}</span>
                <span className="text-2xl font-black text-ink">{countFor(item.to)}</span>
              </div>
              <p className="mt-4 text-sm leading-relaxed text-ink-muted">{item.description}</p>
              <span className="mt-5 block text-sm font-black text-ink transition group-hover:text-warn-text">페이지 열기 →</span>
            </button>
          ))}
        </div>
      </div>
    </AppShell>
  )
}
