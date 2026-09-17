import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { speakAPI } from '../api'
import LearnHeader from '../components/LearnHeader'
import { getSpeakingStageMenuItem } from '../config/speakingNavigation'

const MODE_LABELS = {
  phoneme: '소리',
  word: '단어',
  sentence: '문장',
}

function mergeReviewDetails(data = {}) {
  const wrongByTarget = new Map((data.wrong || []).map((item) => [item.target, item]))
  return (data.items || []).map((item) => ({
    ...item,
    ...wrongByTarget.get(item.target),
  }))
}

export default function SpeakingReviewLanding() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [items, setItems] = useState([])
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(false)

    speakAPI.getReview()
      .then((data) => {
        if (!cancelled) setItems(mergeReviewDetails(data))
      })
      .catch(() => {
        if (!cancelled) {
          setItems([])
          setError(true)
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => { cancelled = true }
  }, [reloadKey])

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-primary-50">
      <LearnHeader
        accent="speaking"
        title="말하기 복습"
        description="다시 연습할 발음과 문장을 확인한 뒤 복습을 시작하세요"
        onExit={() => navigate('/dashboard')}
      />

      <main className="mx-auto max-w-5xl space-y-5 px-4 py-8 sm:px-6">
        {loading ? (
          <div className="card py-16 text-center text-sm text-gray-400">말하기 복습 항목을 불러오는 중…</div>
        ) : error ? (
          <div className="card py-16 text-center">
            <p className="text-lg font-bold text-gray-900">복습 항목을 불러오지 못했어요</p>
            <p className="mt-1 text-sm text-gray-500">잠시 후 다시 시도해 주세요.</p>
            <button type="button" onClick={() => setReloadKey((key) => key + 1)} className="btn-primary mt-5 px-6 py-2.5 text-sm">다시 불러오기</button>
          </div>
        ) : items.length ? (
          <>
            <section className="card flex flex-wrap items-center justify-between gap-4">
              <div>
                <p className="text-sm text-gray-600">복습할 말하기 항목이 <b className="text-gray-900">{items.length}개</b> 있어요.</p>
                <p className="mt-1 text-xs text-gray-400">목록 순서대로 발음과 억양을 다시 연습합니다.</p>
              </div>
              <button type="button" onClick={() => navigate('/review/speaking/session')} className="btn-primary py-2.5 text-sm">
                {items.length}개 복습 시작
              </button>
            </section>

            <ol className="grid gap-3 sm:grid-cols-2">
              {items.map((item, index) => {
                const stageNo = item.stage == null ? null : Number(item.stage)
                const stage = stageNo == null ? null : getSpeakingStageMenuItem(stageNo)
                const modeLabel = MODE_LABELS[item.mode]
                return (
                  <li key={`${item.target}-${index}`} className="card">
                    <div className="flex items-start justify-between gap-3">
                      <span className="rounded-full bg-rose-50 px-2.5 py-1 text-[11px] font-semibold text-rose-700">
                        복습 {String(index + 1).padStart(2, '0')}
                      </span>
                      <span className="text-xs text-gray-400">
                        {[stage?.label, modeLabel].filter(Boolean).join(' · ') || '말하기 복습'}
                      </span>
                    </div>
                    <p className="mt-4 text-lg font-bold leading-relaxed text-gray-900">{item.target}</p>
                    {item.last_score != null && Number.isFinite(Number(item.last_score)) && (
                      <p className="mt-2 text-sm text-gray-500">이전 점수: <b className="text-rose-600">{Number(item.last_score)}점</b></p>
                    )}
                  </li>
                )
              })}
            </ol>
          </>
        ) : (
          <div className="card py-16 text-center">
            <p className="mb-3 text-4xl">🎉</p>
            <h2 className="mb-1 text-xl font-bold text-gray-900">복습할 말하기 항목이 없어요</h2>
            <p className="mb-5 text-gray-500">새로운 말하기 학습을 완료하면 다시 연습할 항목이 이곳에 모입니다.</p>
            <button type="button" onClick={() => navigate('/learn/speaking?stage=0')} className="btn-primary">말하기 학습으로</button>
          </div>
        )}
      </main>
    </div>
  )
}
