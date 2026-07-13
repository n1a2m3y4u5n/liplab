import { motion } from 'framer-motion'

const PHONEME_LABELS = {
  initial: '초성',
  medial: '중성',
  final: '종성',
}

function SummaryMetric({ label, value, tone = 'text-gray-900' }) {
  return (
    <div className="rounded-2xl border border-gray-100 bg-gray-50 p-4">
      <div className={`text-2xl font-bold ${tone}`}>{value}</div>
      <div className="mt-1 text-xs font-medium uppercase tracking-wide text-gray-500">{label}</div>
    </div>
  )
}

export default function SessionSummary({
  practiceMode,
  scenario,
  summary,
  onRetryIncorrect,
  onRestart,
  onOpenAnalysis,
  onExit,
}) {
  const hasScores = summary.totalItems > 0
  const hasIncorrect = summary.incorrectItems.length > 0

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-6"
    >
      <div className="card overflow-hidden bg-gradient-to-br from-slate-900 via-slate-800 to-slate-700 text-white">
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-sky-200">세션 요약</p>
            <h2 className="mt-2 text-3xl font-bold">
              {practiceMode === 'study' ? '워밍업을 마쳤습니다' : '연습 세션을 마쳤습니다'}
            </h2>
            <p className="mt-2 max-w-2xl text-sm text-slate-200">
              {(scenario?.situation || '현재 시나리오')} | 레벨 {scenario?.level || 1}
            </p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-slate-100">
            {hasScores
              ? `채점된 문장 ${summary.completedItems}개를 확인했습니다`
              : `학습 모드 문장 ${scenario?.sentences?.length || 0}개를 마쳤습니다`}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <SummaryMetric
          label="평균 점수"
          value={hasScores ? `${summary.averageScore}%` : '학습 모드'}
          tone={hasScores ? 'text-sky-700' : 'text-gray-900'}
        />
        <SummaryMetric
          label="총 XP"
          value={hasScores ? summary.totalXp : 0}
          tone="text-emerald-700"
        />
        <SummaryMetric
          label="평균 시간"
          value={hasScores ? `${summary.averageTimeSeconds}초` : '-'}
          tone="text-amber-700"
        />
        <SummaryMetric
          label="재도전 필요"
          value={hasScores ? summary.incorrectItems.length : 0}
          tone="text-rose-700"
        />
      </div>

      {hasScores && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1.2fr_0.8fr]">
          <div className="card">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-semibold text-gray-900">음운 포커스</h3>
                <p className="mt-1 text-sm text-gray-500">
                  다음에 어떤 훈련을 할지 결정할 때 참고하세요.
                </p>
              </div>
              <button
                onClick={onOpenAnalysis}
                className="rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-700 transition-colors hover:bg-gray-50"
              >
                분석 보기
              </button>
            </div>
            <div className="mt-5 space-y-4">
              {Object.entries(summary.phonemeAverages).map(([key, value]) => (
                <div key={key}>
                  <div className="mb-2 flex justify-between text-sm">
                    <span className="font-medium text-gray-700">{PHONEME_LABELS[key]}</span>
                    <span className="text-gray-500">{value}%</span>
                  </div>
                  <div className="h-3 overflow-hidden rounded-full bg-gray-100">
                    <div
                      className={`h-full rounded-full ${
                        key === summary.strongPhoneme
                          ? 'bg-emerald-500'
                          : key === summary.weakPhoneme
                          ? 'bg-rose-400'
                          : 'bg-sky-500'
                      }`}
                      style={{ width: `${Math.min(value, 100)}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="card">
            <h3 className="text-lg font-semibold text-gray-900">핵심 포인트</h3>
            <div className="mt-4 space-y-4 text-sm">
              <div className="rounded-2xl bg-emerald-50 p-4">
                <div className="text-xs font-semibold uppercase tracking-wide text-emerald-700">가장 잘한 문장</div>
                <div className="mt-2 font-medium text-emerald-900">
                  {summary.bestResult?.sentence || '아직 채점된 문장이 없습니다'}
                </div>
                <div className="mt-1 text-emerald-700">
                  {summary.bestResult ? `${summary.bestResult.score}%` : '채점 모드를 완료하면 이 정보가 표시됩니다'}
                </div>
              </div>
              <div className="rounded-2xl bg-rose-50 p-4">
                <div className="text-xs font-semibold uppercase tracking-wide text-rose-700">다음 재도전 대상</div>
                <div className="mt-2 font-medium text-rose-900">
                  {summary.weakestResult?.sentence || '아직 재도전 대상이 없습니다'}
                </div>
                <div className="mt-1 text-rose-700">
                  {summary.weakestResult
                    ? `${summary.weakestResult.score}%`
                    : '다음 채점 세션이 끝나면 이 정보가 채워집니다'}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="card">
        <div className="flex flex-col gap-3 md:flex-row">
          {hasIncorrect && (
            <button onClick={onRetryIncorrect} className="btn-primary md:flex-1">
              오답만 다시 풀기
            </button>
          )}
          <button
            onClick={onRestart}
            className={`${hasIncorrect ? 'btn-secondary md:flex-1' : 'btn-primary md:flex-1'}`}
          >
            이 시나리오 다시 시작
          </button>
          <button
            onClick={onExit}
            className="rounded-lg border border-gray-200 px-6 py-3 font-medium text-gray-700 transition-colors hover:bg-gray-50 md:flex-1"
          >
            대시보드로 돌아가기
          </button>
        </div>
      </div>
    </motion.div>
  )
}
