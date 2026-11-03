import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { speakAPI } from '../api'
import AppShell from '../components/AppShell'
import { getSpeakingStageMenuItem } from '../config/speakingNavigation'
import LoadingScreen from '../components/LoadingScreen'

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
    <AppShell backTo="/today" backLabel="오늘" active="today" title="말하기 복습" description="다시 연습할 발음과 문장을 확인한 뒤 복습을 시작하세요">
      <div className="w-full space-y-5">
        {loading ? (
          <LoadingScreen variant="inline" />
        ) : error ? (
          <div className="card py-16 text-center">
            <p className="text-lg font-bold text-ink">복습할 것을 가져오지 못했어요</p>
            <p className="mt-1 text-sm text-ink-muted">잠시 후 다시 시도해 주세요.</p>
            <button type="button" onClick={() => setReloadKey((key) => key + 1)} className="btn-primary mt-5 px-6 py-2.5 text-sm">다시 가져오기</button>
          </div>
        ) : items.length ? (
          <>
            <section className="card-flat flex flex-wrap items-center justify-between gap-4">
              <div>
                <p className="text-sm text-ink-muted">다시 말해 볼 것이 <b className="text-ink">{items.length}개</b> 있어요.</p>
                <p className="mt-1 text-xs text-ink-caption">목록 순서대로 발음과 억양을 다시 연습합니다.</p>
              </div>
              <button type="button" onClick={() => navigate('/review/speaking/session')} className="btn-primary py-2.5 text-sm">
                {items.length}개 복습 시작
              </button>
            </section>

            {/* 11/03: 낱말 하나에 큰 카드 하나씩이던 목록을 한 카드 안의 행 목록으로(점수는 오른쪽 숫자) */}
            <ol aria-label="복습할 말" className="divide-y divide-line overflow-hidden rounded-16 border border-line bg-white">
              {items.map((item, index) => {
                const stageNo = item.stage == null ? null : Number(item.stage)
                const stage = stageNo == null ? null : getSpeakingStageMenuItem(stageNo)
                const modeLabel = MODE_LABELS[item.mode]
                const score = item.last_score != null && Number.isFinite(Number(item.last_score)) ? Number(item.last_score) : null
                return (
                  <li key={`${item.target}-${index}`} className="flex min-h-[60px] items-center gap-3.5 px-4 py-3 lg:px-5">
                    <span className="w-6 shrink-0 text-right text-[13px] font-semibold tabular-nums text-ink-faint">{index + 1}</span>
                    <span className="flex min-w-0 flex-1 flex-col gap-0.5 leading-figma">
                      <span className="break-keep text-[16px] font-semibold text-ink lg:text-[17px]">{item.target}</span>
                      <span className="text-[13px] text-ink-muted">{[stage?.label, modeLabel].filter(Boolean).join(' · ') || '말하기 복습'}</span>
                    </span>
                    {score != null && <span className="shrink-0 text-right text-[13px] text-ink-muted">이전 점수 <b className="tabular-nums text-bad-text">{score}점</b></span>}
                  </li>
                )
              })}
            </ol>
          </>
        ) : (
          <div className="card py-16 text-center">
            <h2 className="mb-1 text-xl font-bold text-ink">다시 말해 볼 것이 없어요</h2>
            <p className="mb-5 text-ink-muted">새로운 말하기 학습을 마치면 다시 연습할 말이 이곳에 모입니다.</p>
            <button type="button" onClick={() => navigate('/learn/speaking?stage=0')} className="btn-primary">말하기 학습으로</button>
          </div>
        )}
      </div>
    </AppShell>
  )
}
