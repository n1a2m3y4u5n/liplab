import { motion } from 'framer-motion'
import {
  buildDashboardRecommendation,
  formatFeatureLabel,
  getWeeklySnapshot,
  getXpToNextLevel,
} from '../utils/practiceInsights'

const MODE_PRESETS = [
  {
    id: 'study',
    title: '워밍업',
    description: '점수 부담 없이 입모를 익히는 준비 단계입니다.',
  },
  {
    id: 'test',
    title: '주관식 테스트',
    description: '실제 인식 정확도를 가장 직접적으로 확인할 수 있습니다.',
  },
  {
    id: 'test-multiple',
    title: '4지선다 훈련',
    description: '입모 패턴이 아직 불안정할 때 빠르게 반복하기 좋습니다.',
  },
  {
    id: 'review',
    title: '오답 복습',
    description: '이전에 틀린 문장을 다시 묶어서 연습합니다.',
  },
  {
    id: 'conversation',
    title: '대화 연습',
    description: '부담 없이 짧은 턴 기반 대화를 연습합니다.',
  },
]

export default function DashboardInsights({
  user,
  statistics,
  calendarData,
  currentMode,
  onSelectMode,
  onOpenAnalysis,
}) {
  const recommendation = buildDashboardRecommendation({ statistics, calendarData, user })
  const weekly = getWeeklySnapshot(calendarData)
  const xp = getXpToNextLevel(user?.total_xp || 0)
  const weakViseme = statistics?.weak_visemes?.[0] || null

  return (
    <div className="mb-8 grid grid-cols-1 gap-5 xl:grid-cols-[1.25fr_0.75fr]">
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        className="overflow-hidden rounded-[28px] bg-[radial-gradient(circle_at_top_left,_rgba(56,189,248,0.35),_transparent_36%),linear-gradient(135deg,_#0f172a,_#1e293b_55%,_#0f766e)] p-7 text-white shadow-xl"
      >
        <p className="text-xs uppercase tracking-[0.24em] text-sky-200">추천 다음 단계</p>
        <h2 className="mt-3 text-3xl font-bold">{recommendation.title}</h2>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-100">
          {recommendation.description}
        </p>

        <div className="mt-6 grid grid-cols-1 gap-3 md:grid-cols-3">
          {recommendation.stats.map((stat) => (
            <div key={stat} className="rounded-2xl border border-white/10 bg-white/10 px-4 py-3 text-sm text-slate-100 backdrop-blur-sm">
              {stat}
            </div>
          ))}
        </div>

        <div className="mt-6 flex flex-col gap-3 sm:flex-row">
          <button
            onClick={() => onSelectMode(recommendation.mode)}
            className="rounded-xl bg-white px-5 py-3 text-sm font-semibold text-slate-900 transition-transform hover:-translate-y-0.5"
          >
            {recommendation.actionLabel}
          </button>
          <button
            onClick={onOpenAnalysis}
            className="rounded-xl border border-white/15 bg-white/5 px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-white/10"
          >
            전체 분석 보기
          </button>
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.08 }}
        className="grid grid-cols-1 gap-5"
      >
        <div className="card">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.2em] text-gray-400">이번 주</p>
              <h3 className="mt-2 text-xl font-bold text-gray-900">학습 흐름 요약</h3>
            </div>
            <div className="rounded-full bg-sky-50 px-3 py-1 text-xs font-semibold text-sky-700">
              레벨 {xp.currentLevel}
            </div>
          </div>

          <div className="mt-5 grid grid-cols-3 gap-3">
            <div className="rounded-2xl bg-gray-50 p-4">
              <div className="text-2xl font-bold text-gray-900">{weekly.daysActive}</div>
              <div className="mt-1 text-xs uppercase tracking-wide text-gray-500">활동 일수</div>
            </div>
            <div className="rounded-2xl bg-gray-50 p-4">
              <div className="text-2xl font-bold text-gray-900">{weekly.sessions}</div>
              <div className="mt-1 text-xs uppercase tracking-wide text-gray-500">세션 수</div>
            </div>
            <div className="rounded-2xl bg-gray-50 p-4">
              <div className="text-2xl font-bold text-gray-900">{xp.xpRemaining}</div>
              <div className="mt-1 text-xs uppercase tracking-wide text-gray-500">다음 레벨까지</div>
            </div>
          </div>

          <div className="mt-4 rounded-2xl border border-gray-100 bg-slate-50 p-4 text-sm text-gray-600">
            {weakViseme
              ? `현재 집중 영역: ${formatFeatureLabel(weakViseme.feature)}`
              : '점수가 반영되는 세션을 몇 번 완료하면 약점 추적이 시작됩니다.'}
          </div>
        </div>

        <div className="card">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.2em] text-gray-400">빠른 시작</p>
              <h3 className="mt-2 text-xl font-bold text-gray-900">모드를 바로 고르기</h3>
            </div>
          </div>

          <div className="mt-4 space-y-3">
            {MODE_PRESETS.map((preset) => (
              <button
                key={preset.id}
                onClick={() => onSelectMode(preset.id)}
                className={`w-full rounded-2xl border px-4 py-3 text-left transition-all ${
                  currentMode === preset.id
                    ? 'border-sky-400 bg-sky-50 shadow-sm'
                    : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="font-semibold text-gray-900">{preset.title}</div>
                  {currentMode === preset.id && (
                    <div className="text-xs font-semibold uppercase tracking-wide text-sky-700">
                      선택됨
                    </div>
                  )}
                </div>
                <div className="mt-1 text-sm text-gray-500">{preset.description}</div>
              </button>
            ))}
          </div>
        </div>
      </motion.div>
    </div>
  )
}
